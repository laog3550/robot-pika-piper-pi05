#!/usr/bin/env python3
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/pi05_pika_input/scripts/gripper_input.py"
spec = importlib.util.spec_from_file_location("gripper_input", SOURCE)
module = importlib.util.module_from_spec(spec)
missing_modules = {}
for dependency in ("fcntl", "termios", "tty"):
    if dependency not in sys.modules:
        try:
            __import__(dependency)
        except (ImportError, NameError):
            missing_modules[dependency] = types.ModuleType(dependency)
sys.modules.update(missing_modules)
spec.loader.exec_module(module)
CONTROLLER = ROOT / "src/pi05_left_teleop/scripts/gripper_service_controller.py"
controller_spec = importlib.util.spec_from_file_location("gripper_controller", CONTROLLER)
controller = importlib.util.module_from_spec(controller_spec)
controller_spec.loader.exec_module(controller)


class GripperInputTest(unittest.TestCase):
    def test_encoder_endpoints_map_to_piper_travel(self):
        self.assertAlmostEqual(module.piper_target(0.0), 0.0)
        self.assertAlmostEqual(module.piper_target(1.67), 0.07)
        self.assertAlmostEqual(module.piper_target(99.0), 0.07)
        self.assertGreater(module.piper_target(0.8), 0.0)
        self.assertLess(module.piper_target(0.8), 0.07)

    def test_invalid_mapping_values_are_rejected(self):
        for value in (math.nan, math.inf):
            with self.assertRaises(ValueError):
                module.piper_target(value)
        for maximum in (0.0, -0.1, 0.081):
            with self.assertRaises(ValueError):
                module.piper_target(0.5, maximum)

    def test_stream_parser_handles_fragmented_frames_and_errors(self):
        parser = module.FrameParser()
        self.assertEqual(parser.feed(b'noise{"Command":1,"AS50'), [])
        self.assertEqual(parser.feed(b'47":{"rad":0.5}}'), [0.5])
        self.assertEqual(parser.feed(
            b'{"Command":1,"AS5047":{"error":1,"rad":0.8}}'), [])

    def test_runtime_is_read_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("os.O_RDONLY", text)
        self.assertNotIn("os.write", text)
        self.assertIn("fcntl.LOCK_EX | fcntl.LOCK_NB", text)

    def test_gripper_has_an_independent_rate_limiter_and_service(self):
        limiter = controller.ScalarRateLimiter(0.04, 0.0, 0.07)
        limiter.reset(0.02)
        self.assertAlmostEqual(limiter.step(0.07, 0.1), 0.024)
        self.assertAlmostEqual(limiter.step(-1.0, 0.1), 0.020)
        with self.assertRaises(ValueError):
            limiter.step(math.nan, 0.1)
        text = CONTROLLER.read_text(encoding="utf-8")
        self.assertIn('ServiceProxy("gripper_command", Gripper)', text)
        self.assertIn('Service("~set_enabled", SetBool', text)
        self.assertIn('Subscriber("joint_feedback", JointState', text)
        self.assertNotIn('Publisher(', text)


if __name__ == "__main__":
    unittest.main()
