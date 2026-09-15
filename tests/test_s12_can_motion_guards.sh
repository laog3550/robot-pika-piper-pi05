#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
/usr/bin/python3 - <<'PY'
import importlib.util
import collections
import threading
import time
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('replay', 'src/pi05_control/test/test_low_speed_acceptance_runner.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
node = replay.NODE

class GuardedReplay(replay.ReplayRunner):
    def _publish_until_can(self, publisher, positions, source, predicate, label):
        if label == 'outward move':
            return super()._publish_until_can(publisher, positions, source, predicate, label)
        for _ in range(3):
            predicate(self.return_positions)
        raise AssertionError('unsafe return accepted')

class Tests(unittest.TestCase):
    def test_return_drift_and_selected_overshoot_stop_without_disable(self):
        for joint, delta in ((2, .003), (2, .010), (1, .021)):
            events = []
            ros = replay.FakeRospy(events)
            with patch.object(node, 'rospy', ros):
                runner = GuardedReplay(events, [replay.Feedback([0, .003, 0, 0, 0, 0, 0])])
                runner.return_positions = [0.0] * 7
                runner.return_positions[joint] = delta
                with self.assertRaises(RuntimeError):
                    runner.run_move(replay.AcceptanceConfig('left', 2), False)
                self.assertEqual(runner.stop_count, 1)
                self.assertFalse(any(args == (False,) for _, args in ros.service_calls))

    def source(self):
        source = node.PassiveCanFeedbackSource.__new__(node.PassiveCanFeedbackSource)
        source.pending = collections.deque()
        source.condition = threading.Condition()
        source.failure = None
        source.closed = False
        return source

    def test_fifo_does_not_skip_transient_and_stale_fails(self):
        source = self.source()
        source.pending.extend([(time.monotonic(), [i] * 7) for i in (0, 1, 0)])
        self.assertEqual([source.next_positions(.1)[0] for _ in range(3)], [0, 1, 0])
        source.pending.append((time.monotonic() - .2, [0] * 7))
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            source.next_positions(.1)

    def test_receiver_failure_precedes_queued_feedback(self):
        source = self.source()
        source.pending.append((time.monotonic(), [0] * 7))
        source.failure = 'queue overflow'
        with self.assertRaisesRegex(RuntimeError, 'overflow'):
            source.next_positions(.1)

    def test_continuous_receiver_stops_on_overflow(self):
        source = self.source()
        class Socket:
            def settimeout(self, timeout):
                pass
            def recv(self, size):
                return node.CAN_FRAME.pack(0x2A5, 8, bytes(8))
        class Assembler:
            def update(self, can_id, payload):
                return [0] * 7
        source.source = Socket()
        source.assembler = Assembler()
        source.motor_telemetry = node.MotorTelemetryWindow()
        source._receive()
        self.assertEqual(len(source.pending), 256)
        self.assertIsNotNone(source.failure)
        with self.assertRaises(RuntimeError):
            source.next_positions(.1)

    def test_every_feedback_checked_without_ros_sleep(self):
        class Publisher:
            count = 0
            def publish(self, command):
                self.count += 1
        class Source:
            def next_positions(self, timeout):
                return [0] * 7
        class Ros:
            Time = replay.TimeSource
            def sleep(self, duration):
                raise AssertionError('feedback processing must not sleep')
        runner = node.AcceptanceRunner('left')
        runner.config = replay.AcceptanceConfig('left', 2)
        publisher = Publisher()
        seen = []
        def predicate(positions):
            seen.append(positions)
            return len(seen) == 20
        command = lambda: types.SimpleNamespace(header=types.SimpleNamespace())
        with patch.object(node, 'rospy', Ros()), patch.object(node, 'JointState', command):
            runner._publish_until_can(publisher, [0] * 7, Source(), predicate, 'replay')
        self.assertEqual(len(seen), 20)
        self.assertEqual(publisher.count, 1)

unittest.main()
PY
