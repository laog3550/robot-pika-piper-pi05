#!/usr/bin/python3
import importlib.util
import contextlib
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "publish_arm_home", ROOT / "scripts/publish_arm_home.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.insert(0, str(ROOT / "scripts"))
session_spec = importlib.util.spec_from_file_location(
    "run_smoothed_teleop", ROOT / "scripts/run_smoothed_teleop.py")
session = importlib.util.module_from_spec(session_spec)
session_spec.loader.exec_module(session)


class ArmHomeTest(unittest.TestCase):
    def test_both_arms_use_confirmed_support_pose(self):
        expected = (["joint%d" % i for i in range(1, 7)],
                    [0.0, 0.0, 0.0, 0.0, 0.567, 0.0], 5)
        for side in ("left", "right"):
            self.assertEqual(
                module.load_home(ROOT / "config/arm-home.yaml", side), expected)

    def test_smoothed_session_requires_explicit_apply(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                session.parse_args(["right", "--duration", "20"])
        args = session.parse_args(["right", "--apply", "--duration", "20"])
        self.assertEqual(args.side, "right")
        self.assertEqual(args.duration, 20.0)

    def test_startup_only_does_not_require_interactive_terminal(self):
        args = session.parse_args(
            ["left", "--apply", "--startup-only", "--with-gripper"])
        self.assertEqual(args.side, "left")
        self.assertTrue(args.startup_only)
        self.assertTrue(args.with_gripper)
        self.assertIsNone(args.duration)

    def test_wrapper_enables_smoothing_and_disables_auto_enable(self):
        text = (ROOT / "scripts/run_smoothed_teleop.sh").read_text(encoding="utf-8")
        self.assertIn("auto_enable:=false smooth_commands:=true", text)
        self.assertIn("enable_gripper_teleop:=true", text)
        self.assertIn("configure_pika_serial.sh", text)
        self.assertIn("run_smoothed_teleop.py", text)
        self.assertIn("stop_launch", text)
        launch = text.index('setsid "$script_dir/start_teleop.sh"')
        readiness = text.index('grep -Fxq "$gate_service"')
        controller = text.index('(trap - INT; python "$script_dir/run_smoothed_teleop.py"')
        self.assertLess(launch, readiness)
        self.assertLess(readiness, controller)

    def test_reset_waits_before_enabling(self):
        text = (ROOT / "scripts/run_smoothed_teleop.py").read_text(encoding="utf-8")
        helper_start = text.index("def reset_then_enable")
        reset_call = text.index("reset_response = reset()", helper_start)
        settle = text.index("rospy.sleep(1.0)", reset_call)
        enable_call = text.index("enable_response = enable(True)", settle)
        self.assertLess(reset_call, settle)
        self.assertLess(settle, enable_call)
        self.assertIn('reset_then_enable(rospy, reset, enable, "before teleop")', text)
        self.assertIn('reset_then_enable(rospy, reset, enable, "during return")', text)

        events = []
        response = type("Response", (), {"success": True, "enable_response": True})()
        ros = type("Ros", (), {"sleep": staticmethod(
            lambda seconds: events.append(("sleep", seconds)))})
        session.reset_then_enable(
            ros,
            lambda: events.append(("reset", None)) or response,
            lambda value: events.append(("enable", value)) or response,
            "in test")
        self.assertEqual(events, [("reset", None), ("sleep", 1.0), ("enable", True)])

    def test_session_requires_stable_accurate_pika_localization(self):
        class Clock:
            now = 0.0

            def monotonic(self):
                return self.now

        clock = Clock()
        samples = iter([False, True, False, True, True, True, True])

        class Ros:
            ROSException = RuntimeError

            @staticmethod
            def is_shutdown():
                return False

            @staticmethod
            def wait_for_message(_topic, _message_type, timeout):
                del timeout
                return type("Status", (), {"accurate": next(samples)})()

            @staticmethod
            def sleep(duration):
                clock.now += max(duration, 0.1)

        original_monotonic = session.time.monotonic
        session.time.monotonic = clock.monotonic
        try:
            session.wait_for_accurate_localization(
                Ros, object, "/status", timeout=2.0, stable_seconds=0.2)
        finally:
            session.time.monotonic = original_monotonic
        self.assertGreaterEqual(clock.now, 0.4)

    def test_home_wait_recovers_after_motion_stalls(self):
        class Clock:
            now = 0.0

            def monotonic(self):
                return self.now

        class Message:
            def __init__(self):
                self.header = type("Header", (), {})()
                self.name = []
                self.position = []
                self.velocity = []

        class Publisher:
            def publish(self, _message):
                pass

        clock = Clock()
        recovered = []

        class Ros:
            ROSException = RuntimeError
            Time = type("Time", (), {"now": staticmethod(lambda: 0.0)})

            @staticmethod
            def is_shutdown():
                return False

            @staticmethod
            def wait_for_message(_topic, _message_type, timeout):
                del timeout
                result = Message()
                result.position = [0.0] * 6 if recovered else [0.1] + [0.0] * 5
                return result

            @staticmethod
            def sleep(duration):
                clock.now += max(duration, 1.0)

        original_monotonic = session.time.monotonic
        session.time.monotonic = clock.monotonic
        try:
            error = session.wait_for_home(
                Ros, Publisher(), Message, "/feedback",
                ["joint%d" % i for i in range(1, 7)], [0.0] * 6,
                5, 30, 0.02, 1.0,
                recover_motion=lambda attempt, _error: recovered.append(attempt),
                stall_seconds=5.0)
        finally:
            session.time.monotonic = original_monotonic
        self.assertEqual(recovered, [1])
        self.assertEqual(error, 0.0)


if __name__ == "__main__":
    unittest.main()
