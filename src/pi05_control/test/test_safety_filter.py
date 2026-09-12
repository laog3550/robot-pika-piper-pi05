#!/usr/bin/env python3

import math
import pathlib
import sys
import unittest


PACKAGE_SRC = pathlib.Path(__file__).parents[1] / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from pi05_control.safety_filter import ArmSafetyFilter, FilterConfig  # noqa: E402


NAMES = ["joint{}".format(index) for index in range(1, 8)]
ZERO = [0.0] * 7


def make_ready(side="left", now=1.0):
    safety_filter = ArmSafetyFilter(side)
    assert safety_filter.update_feedback(ZERO, NAMES, now)
    assert safety_filter.update_localization(True, now)
    assert safety_filter.update_arm_status(False, now)
    assert safety_filter.set_authorized(True, now)
    assert safety_filter.update_teleop_status(False, False, now)
    return safety_filter


class FilterConfigTest(unittest.TestCase):
    def test_rejects_unsafe_or_non_finite_parameters(self):
        invalid = (
            {"arm_alpha": 0.0},
            {"gripper_alpha": 1.01},
            {"max_arm_step_rad": 0.0},
            {"command_timeout_s": math.inf},
            {"authorization_timeout_s": 0.0},
            {"speed_percent": 101.0},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                FilterConfig(**values)


class ArmSafetyFilterTest(unittest.TestCase):
    def test_side_is_a_closed_set(self):
        for side in ("left", "right"):
            self.assertEqual(ArmSafetyFilter(side).side, side)
        with self.assertRaises(ValueError):
            ArmSafetyFilter("arm")

    def test_requires_all_gates_and_new_session(self):
        item = ArmSafetyFilter("left")
        self.assertIsNone(item.command([1.0] * 7, NAMES, 1.0))
        item.update_feedback(ZERO, NAMES, 1.1)
        item.update_localization(True, 1.1)
        item.update_arm_status(False, 1.1)
        self.assertIsNone(item.command([1.0] * 7, NAMES, 1.1))
        self.assertTrue(item.set_authorized(True, 1.1))
        self.assertIsNone(item.command([1.0] * 7, NAMES, 1.1))
        self.assertTrue(item.update_teleop_status(False, False, 1.1))
        self.assertIsNotNone(item.command([1.0] * 7, NAMES, 1.11))

    def test_conditions_from_feedback_with_deadband_and_step_caps(self):
        item = make_ready()
        self.assertTrue(item.set_authorized(True, 1.005))
        self.assertTrue(item.session_active)
        first = item.command([1.0] * 6 + [0.05], NAMES, 1.01)
        self.assertEqual(first.names, NAMES)
        self.assertEqual(first.speed_percent, 15.0)
        for value in first.positions[:6]:
            self.assertAlmostEqual(value, 0.012)
        self.assertAlmostEqual(first.positions[6], 0.0006)

        second_target = list(first.positions)
        second_target[0] += 0.001
        second_target[6] += 0.001
        second = item.command(second_target, NAMES, 1.02)
        self.assertAlmostEqual(second.positions[0], first.positions[0])
        self.assertAlmostEqual(second.positions[6], first.positions[6])

    def test_invalid_command_latches_and_never_replays_old_target(self):
        item = make_ready()
        self.assertIsNotNone(item.command([1.0] * 7, NAMES, 1.01))
        invalid = [0.0] * 6 + [float("nan")]
        self.assertIsNone(item.command(invalid, NAMES, 1.02))
        self.assertEqual(item.state(1.02), "FAULT_LATCHED")
        self.assertIsNone(item.command(ZERO, NAMES, 1.03))

        self.assertTrue(item.set_authorized(False, 1.04))
        item.update_feedback([0.2] * 7, NAMES, 1.05)
        item.update_localization(True, 1.05)
        item.update_arm_status(False, 1.05)
        self.assertTrue(item.reset_fault(1.05))
        self.assertTrue(item.set_authorized(True, 1.05))
        self.assertIsNone(item.command(ZERO, NAMES, 1.06))
        self.assertTrue(item.update_teleop_status(False, False, 1.06))
        output = item.command(ZERO, NAMES, 1.07)
        self.assertAlmostEqual(output.positions[0], 0.188)

    def test_localization_loss_and_timeouts_latch(self):
        item = make_ready()
        self.assertFalse(item.update_localization(False, 1.01))
        self.assertEqual(item.fault_reason, "localization invalid")
        self.assertIsNone(item.command(ZERO, NAMES, 1.02))
        item.watchdog(2.0)
        self.assertEqual(item.fault_reason, "localization invalid")

        command_timeout = make_ready("right", 2.0)
        command_timeout.update_feedback(ZERO, NAMES, 2.36)
        command_timeout.update_localization(True, 2.36)
        command_timeout.set_authorized(True, 2.36)
        self.assertFalse(command_timeout.watchdog(2.36))
        self.assertEqual(command_timeout.fault_reason, "command timed out")

        feedback_timeout = make_ready("right", 3.0)
        feedback_timeout.update_localization(True, 3.36)
        feedback_timeout.set_authorized(True, 3.36)
        self.assertFalse(feedback_timeout.watchdog(3.36))
        self.assertEqual(feedback_timeout.fault_reason, "feedback timed out")

    def test_clock_regression_latches(self):
        item = make_ready(now=5.0)
        self.assertIsNone(item.command(ZERO, NAMES, 4.9))
        self.assertEqual(item.fault_reason, "clock moved backwards")

    def test_authorization_requires_fresh_inputs_and_clear_ik(self):
        item = ArmSafetyFilter("left")
        self.assertFalse(item.set_authorized(True, 1.0))
        self.assertFalse(item.authorized)
        self.assertEqual(item.state(1.0), "FAULT_LATCHED")

        waiting = ArmSafetyFilter("right")
        waiting.update_feedback(ZERO, NAMES, 1.0)
        waiting.update_localization(True, 1.0)
        waiting.update_arm_status(False, 1.0)
        self.assertFalse(waiting.update_teleop_status(True, False, 1.0))
        self.assertFalse(waiting.fault_reason)

    def test_authorization_heartbeat_is_a_lease(self):
        item = make_ready()
        item.update_feedback(ZERO, NAMES, 1.2)
        item.update_localization(True, 1.2)
        self.assertTrue(item.set_authorized(True, 1.2))
        self.assertTrue(item.session_active)
        self.assertTrue(item.set_authorized(True, 1.3))
        self.assertTrue(item.session_active)
        item.update_feedback(ZERO, NAMES, 1.54)
        item.update_localization(True, 1.54)
        self.assertIsNotNone(item.command(ZERO, NAMES, 1.54))
        self.assertTrue(item.watchdog(1.54))
        item.update_feedback(ZERO, NAMES, 1.56)
        item.update_localization(True, 1.56)
        self.assertFalse(item.watchdog(1.56))
        self.assertEqual(item.fault_reason, "authorization heartbeat timed out")

    def test_left_and_right_replay_are_identical(self):
        outputs = []
        for side in ("left", "right"):
            item = make_ready(side)
            replay = []
            for index in range(5):
                now = 1.01 + index * 0.02
                item.update_feedback(ZERO, NAMES, now)
                item.update_localization(True, now)
                replay.append(item.command([0.1] * 6 + [0.02], NAMES, now).positions)
            outputs.append(replay)
        self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
