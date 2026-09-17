#!/usr/bin/python3
import importlib.util
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "joint_command_smoother",
    ROOT / "src/pi05_left_teleop/scripts/joint_command_smoother.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class JointCommandSmootherTest(unittest.TestCase):
    def make(self):
        result = module.JointCommandSmoother(0.12, 0.30, 0.50, 0.0005)
        result.reset([0.0] * 6)
        return result

    def test_step_limits_velocity_and_acceleration(self):
        smoother = self.make()
        previous = [0.0] * 6
        previous_velocity = [0.0] * 6
        for _ in range(100):
            current = smoother.step([1.0] * 6, 0.02)
            velocity = [(a - b) / 0.02 for a, b in zip(current, previous)]
            self.assertTrue(all(abs(value) <= 0.300001 for value in velocity))
            acceleration = [(a - b) / 0.02
                            for a, b in zip(velocity, previous_velocity)]
            self.assertTrue(all(abs(value) <= 0.500001 for value in acceleration))
            previous, previous_velocity = current, velocity

    def test_small_noise_stays_inside_deadband(self):
        smoother = self.make()
        for _ in range(20):
            result = smoother.step([0.0001, -0.0001, 0, 0, 0, 0], 0.02)
        self.assertEqual(result, [0.0] * 6)

    def test_invalid_input_is_rejected(self):
        smoother = self.make()
        with self.assertRaises(ValueError):
            smoother.step([math.nan] * 6, 0.02)
        with self.assertRaises(ValueError):
            smoother.step([0.0] * 6, 0.0)

    def test_runtime_exposes_explicit_output_gate(self):
        text = (ROOT / "src/pi05_left_teleop/scripts/joint_command_smoother.py").read_text(
            encoding="utf-8")
        self.assertIn('rospy.Service("~set_enabled", SetBool', text)
        self.assertIn("fresh = enabled and", text)

if __name__ == "__main__":
    unittest.main()
