#!/usr/bin/env python3

import importlib.util
import pathlib
import sys
import types
import unittest


PACKAGE = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(PACKAGE / "src"))

# The production package is an external pinned dependency. Supply only the names
# needed to import the node so this replay remains hardware- and workspace-independent.
fake_piper = types.ModuleType("piper_msgs")
fake_piper_msg = types.ModuleType("piper_msgs.msg")
fake_piper_srv = types.ModuleType("piper_msgs.srv")
fake_piper_msg.PiperStatusMsg = type("PiperStatusMsg", (), {})
fake_piper_srv.Enable = type("Enable", (), {})
fake_piper.msg = fake_piper_msg
fake_piper.srv = fake_piper_srv
sys.modules["piper_msgs"] = fake_piper
sys.modules["piper_msgs.msg"] = fake_piper_msg
sys.modules["piper_msgs.srv"] = fake_piper_srv

NODE_PATH = PACKAGE / "scripts" / "single_arm_low_speed_acceptance.py"
SPEC = importlib.util.spec_from_file_location("s12_acceptance_node", str(NODE_PATH))
NODE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NODE)

from pi05_control.low_speed_acceptance import AcceptanceConfig  # noqa: E402


class Response(object):
    def __init__(self, success=True, enable_response=True):
        self.success = success
        self.enable_response = enable_response


class Stamp(object):
    def __init__(self, value):
        self.value = value

    def to_sec(self):
        return self.value


class TimeSource(object):
    @staticmethod
    def now():
        return Stamp(100.0)


class Publisher(object):
    @staticmethod
    def get_num_connections():
        return 1


class FakeRospy(object):
    Time = TimeSource

    def __init__(self, events, enable_result=True):
        self.events = events
        self.enable_result = enable_result
        self.service_calls = []

    @staticmethod
    def wait_for_service(_name, timeout=None):
        del timeout

    @staticmethod
    def sleep(_duration):
        pass

    def Publisher(self, _topic, _kind, queue_size=None):
        del queue_size
        self.events.append("publisher")
        return Publisher()

    @staticmethod
    def logerr(*_args):
        pass

    @staticmethod
    def loginfo(*_args):
        pass

    @staticmethod
    def logfatal(*_args):
        pass

    def ServiceProxy(self, name, _kind):
        def call(*args):
            self.service_calls.append((name, args))
            if name.endswith("/reset_srv_raw"):
                self.events.append("reset")
                return Response(success=True)
            if name.endswith("/enable_srv_raw"):
                if args == (False,):
                    self.events.append("disable")
                    return Response(enable_response=True)
                self.events.append("enable")
                return Response(enable_response=self.enable_result)
            raise AssertionError("unexpected service {}".format(name))
        return call


class Feedback(object):
    def __init__(self, positions):
        self.position = positions


class FakeCanSource(object):
    def __init__(self, events):
        self.events = events

    def close(self):
        self.events.append("raw close")

    @staticmethod
    def telemetry_summary():
        return tuple((joint, 0, 0.0, 0.0) for joint in range(1, 7))


class ReplayRunner(NODE.AcceptanceRunner):
    def __init__(self, events, outcomes, baselines=None, raw_baseline=None):
        super(ReplayRunner, self).__init__("left")
        self.events = events
        self.outcomes = list(outcomes)
        self.baselines = list(baselines or [[0.0] * 7, [0.0] * 7])
        self.raw_baseline = list(raw_baseline or [0.0] * 7)
        self.command_vectors = []
        self.stop_count = 0

    def _require_isolated_graph(self):
        self.events.append("graph")

    def _fresh_status(self):
        self.events.append("status")

    def _stable_baseline(self, recovery_time, config):
        del recovery_time, config
        self.events.append("baseline")
        return self.baselines.pop(0)

    def _publish_until(self, publisher, positions, predicate, label):
        del publisher, positions, predicate
        self.events.append(label)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def _open_can_feedback(self):
        self.events.append("raw open")
        return FakeCanSource(self.events)

    def _stable_can_baseline(self, source, config):
        del source, config
        self.events.append("raw baseline")
        return self.raw_baseline

    def _publish_until_can(self, publisher, positions, source, predicate, label):
        del publisher, source, predicate
        self.events.append(label)
        self.command_vectors.append(list(positions))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return list(outcome.position)

    def _stop_only(self):
        self.stop_count += 1
        self.events.append("stop")


class LowSpeedAcceptanceRunnerReplayTest(unittest.TestCase):
    def setUp(self):
        self.original_rospy = NODE.rospy
        self.events = []
        self.fake_rospy = FakeRospy(self.events)
        NODE.rospy = self.fake_rospy
        self.config = AcceptanceConfig("left", 2)

    def tearDown(self):
        NODE.rospy = self.original_rospy

    def assert_no_disable(self):
        self.assertFalse(any(args == (False,) for _name, args in self.fake_rospy.service_calls))
        self.assertNotIn("disable", self.events)

    def test_success_returns_then_stops_without_disable(self):
        runner = ReplayRunner(self.events, [
            Feedback([0.0, 0.003, 0.0, 0.0, 0.0, 0.0, 0.0]),
            Feedback([0.0] * 7),
        ])
        observed, error = runner.run_move(self.config, resume_stop=False)
        self.assertAlmostEqual(observed, 0.003)
        self.assertEqual(error, 0.0)
        self.assertEqual(runner.stop_count, 1)
        self.assertLess(self.events.index("return move"), self.events.index("stop"))
        self.assertLess(self.events.index("raw open"), self.events.index("outward move"))
        self.assertLess(self.events.index("raw close"), self.events.index("stop"))
        self.assert_no_disable()

    def test_ros_and_raw_baselines_must_agree_before_command(self):
        runner = ReplayRunner(
            self.events, [], raw_baseline=[0.0, 0.0, 0.003, 0.0, 0.0, 0.0, 0.0])
        with self.assertRaisesRegex(RuntimeError, "ROS/raw CAN baseline mismatch"):
            runner.run_move(self.config, resume_stop=False)
        self.assertNotIn("outward move", self.events)
        self.assertIn("raw close", self.events)
        self.assertEqual(runner.stop_count, 1)
        self.assert_no_disable()

    def test_commands_are_derived_from_the_raw_can_baseline(self):
        ros_baseline = [0.0] * 7
        raw_baseline = [0.0004, 0.0008, 0.0015, -0.0003, 0.0, 0.0, 0.002]
        outward = list(raw_baseline)
        outward[1] += 0.003
        runner = ReplayRunner(
            self.events,
            [Feedback(outward), Feedback(raw_baseline)],
            baselines=[[0.0] * 7, ros_baseline],
            raw_baseline=raw_baseline,
        )

        observed, error = runner.run_move(self.config, resume_stop=False)

        expected_outward = list(raw_baseline)
        expected_outward[1] += self.config.delta_rad
        self.assertEqual(runner.command_vectors, [expected_outward, raw_baseline])
        self.assertAlmostEqual(observed, 0.003)
        self.assertEqual(error, 0.0)
        self.assertEqual(runner.stop_count, 1)
        self.assert_no_disable()

    def test_outward_failure_stops_without_disable(self):
        runner = ReplayRunner(self.events, [RuntimeError("outward timeout")])
        with self.assertRaisesRegex(RuntimeError, "outward timeout"):
            runner.run_move(self.config, resume_stop=False)
        self.assertEqual(runner.stop_count, 1)
        self.assert_no_disable()

    def test_return_failure_stops_without_disable(self):
        runner = ReplayRunner(self.events, [
            Feedback([0.0, 0.003, 0.0, 0.0, 0.0, 0.0, 0.0]),
            RuntimeError("return timeout"),
        ])
        with self.assertRaisesRegex(RuntimeError, "return timeout"):
            runner.run_move(self.config, resume_stop=False)
        self.assertEqual(runner.stop_count, 1)
        self.assert_no_disable()

    def test_failed_enable_attempt_still_stops_without_disable(self):
        self.fake_rospy.enable_result = False
        runner = ReplayRunner(self.events, [])
        with self.assertRaisesRegex(RuntimeError, "enable service returned false"):
            runner.run_move(self.config, resume_stop=False)
        self.assertEqual(runner.stop_count, 1)
        self.assert_no_disable()

    def test_enable_settling_over_limit_stops_before_joint_command(self):
        runner = ReplayRunner(
            self.events,
            [],
            baselines=[
                [0.0] * 7,
                [0.0, 0.003, 0.0, 0.0, 0.0, 0.0, 0.0],
            ],
        )
        with self.assertRaisesRegex(RuntimeError, "J2 delta=0.003000"):
            runner.run_move(self.config, resume_stop=False)
        self.assertNotIn("outward move", self.events)
        self.assertEqual(runner.stop_count, 1)
        self.assert_no_disable()

    def test_enable_settle_check_never_creates_command_publisher(self):
        runner = ReplayRunner(self.events, [])
        joint, shift = runner.run_enable_settle(self.config, resume_stop=True)
        self.assertEqual((joint, shift), (6, 0.0))
        self.assertNotIn("publisher", self.events)
        self.assertNotIn("outward move", self.events)
        self.assertEqual(runner.stop_count, 1)
        self.assert_no_disable()

    def test_resume_happens_before_new_baseline(self):
        runner = ReplayRunner(self.events, [
            Feedback([0.0, 0.003, 0.0, 0.0, 0.0, 0.0, 0.0]),
            Feedback([0.0] * 7),
        ])
        runner.run_move(self.config, resume_stop=True)
        baselines = [index for index, value in enumerate(self.events) if value == "baseline"]
        self.assertEqual(len(baselines), 2)
        self.assertLess(self.events.index("reset"), baselines[0])
        self.assertLess(self.events.index("enable"), baselines[1])
        self.assert_no_disable()

    def test_supported_disable_is_separate_and_explicit(self):
        runner = ReplayRunner(self.events, [])
        runner.run_supported_disable()
        self.assertIn("disable", self.events)
        self.assertEqual(
            [args for name, args in self.fake_rospy.service_calls
             if name.endswith("/enable_srv_raw")],
            [(False,)],
        )


if __name__ == "__main__":
    unittest.main()
