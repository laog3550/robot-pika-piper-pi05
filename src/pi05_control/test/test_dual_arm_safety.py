#!/usr/bin/env python3

import math
import pathlib
import sys
import unittest


PACKAGE_SRC = pathlib.Path(__file__).parents[1] / "src"
sys.path.insert(0, str(PACKAGE_SRC))

from pi05_control.dual_arm_safety import (  # noqa: E402
    CoordinatorConfig,
    DualArmSafetyCoordinator,
)


def update_ready(item, now=1.0):
    for side in ("left", "right"):
        item.update_filter(
            side=side,
            state="DISABLED",
            level=1,
            message="DISABLED",
            authorized=False,
            feedback_fresh=True,
            localization_fresh=True,
            ik_over_limit=False,
            now=now,
        )
        item.update_driver(side, False, "driver status clear", now)


def acknowledge_enabled(item, now):
    for side in ("left", "right"):
        item.update_filter(
            side=side,
            state="ENABLED_HOLD",
            level=0,
            message="ENABLED_HOLD",
            authorized=True,
            feedback_fresh=True,
            localization_fresh=True,
            ik_over_limit=False,
            now=now,
        )
        item.update_driver(side, False, "driver status clear", now)


class CoordinatorConfigTest(unittest.TestCase):
    def test_rejects_invalid_timing(self):
        for values in (
            {"status_timeout_s": 0.0},
            {"authorization_ack_timeout_s": math.inf},
            {"session_sync_timeout_s": -1.0},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                CoordinatorConfig(**values)


class DualArmSafetyCoordinatorTest(unittest.TestCase):
    def test_requires_both_complete_sides_before_enable(self):
        item = DualArmSafetyCoordinator()
        item.update_filter("left", "DISABLED", 1, "DISABLED", False,
                           True, True, False, 1.0)
        item.update_driver("left", False, "clear", 1.0)
        self.assertFalse(item.can_enable(1.0))
        update_ready(item, 1.1)
        self.assertTrue(item.can_enable(1.1))
        self.assertEqual(item.state(1.1), "READY")

    def test_enable_requires_dual_acknowledgement(self):
        item = DualArmSafetyCoordinator()
        update_ready(item)
        self.assertTrue(item.mark_enabled(1.0))
        self.assertEqual(item.state(1.0), "ENABLED_HOLD")
        acknowledge_enabled(item, 1.1)
        self.assertTrue(item.watchdog(1.1))

        item.update_filter("left", "ENABLED_HOLD", 0, "hold", True,
                           True, True, False, 1.6)
        item.update_driver("left", False, "clear", 1.6)
        item.update_driver("right", False, "clear", 1.6)
        self.assertFalse(item.watchdog(1.6))
        self.assertEqual(
            item.fault_reason, "right filter status timed out")

    def test_one_side_filter_fault_latches_the_pair(self):
        item = DualArmSafetyCoordinator()
        update_ready(item)
        item.mark_enabled(1.0)
        acknowledge_enabled(item, 1.1)
        self.assertFalse(item.update_filter(
            "right", "FAULT_LATCHED", 2, "localization invalid", True,
            True, False, False, 1.2))
        self.assertEqual(
            item.fault_reason,
            "right filter fault: localization invalid",
        )
        self.assertEqual(item.state(1.2), "FAULT_LATCHED")

    def test_one_side_driver_fault_latches_the_pair(self):
        item = DualArmSafetyCoordinator()
        update_ready(item)
        self.assertFalse(item.update_driver(
            "left", True, "err_code is nonzero", 1.1))
        self.assertEqual(
            item.fault_reason, "left driver fault: err_code is nonzero")
        self.assertFalse(item.can_enable(1.1))

    def test_mixed_teleoperation_sessions_must_converge(self):
        item = DualArmSafetyCoordinator()
        update_ready(item)
        item.mark_enabled(1.0)
        acknowledge_enabled(item, 1.1)
        item.update_filter("left", "TELEOP_ACTIVE", 0, "active", True,
                           True, True, False, 1.2)
        item.update_filter("right", "ENABLED_HOLD", 0, "hold", True,
                           True, True, False, 1.2)
        for side in ("left", "right"):
            item.update_driver(side, False, "clear", 1.2)
        self.assertTrue(item.watchdog(1.2))
        acknowledge_enabled(item, 1.31)
        item.update_filter("left", "TELEOP_ACTIVE", 0, "active", True,
                           True, True, False, 1.31)
        self.assertTrue(item.watchdog(1.31))

        item.update_filter("left", "TELEOP_ACTIVE", 0, "active", True,
                           True, True, False, 1.4)
        item.update_filter("right", "ENABLED_HOLD", 0, "hold", True,
                           True, True, False, 1.4)
        for side in ("left", "right"):
            item.update_driver(side, False, "clear", 1.4)
        self.assertTrue(item.watchdog(1.4))
        item.update_filter("left", "TELEOP_ACTIVE", 0, "active", True,
                           True, True, False, 1.61)
        item.update_filter("right", "ENABLED_HOLD", 0, "hold", True,
                           True, True, False, 1.61)
        for side in ("left", "right"):
            item.update_driver(side, False, "clear", 1.61)
        self.assertFalse(item.watchdog(1.61))
        self.assertEqual(
            item.fault_reason, "left/right teleoperation session mismatch")

    def test_fault_reset_requires_fresh_dual_disabled_status(self):
        item = DualArmSafetyCoordinator()
        update_ready(item)
        item.latch_fault("injected", 1.0)
        self.assertFalse(item.reset_fault(1.4))
        update_ready(item, 1.4)
        self.assertTrue(item.reset_fault(1.4))
        self.assertEqual(item.state(1.4), "READY")

    def test_clock_regression_is_latched(self):
        item = DualArmSafetyCoordinator()
        update_ready(item, 5.0)
        self.assertFalse(item.watchdog(4.9))
        self.assertEqual(item.fault_reason, "clock moved backwards")

    def test_side_and_filter_state_are_closed_sets(self):
        item = DualArmSafetyCoordinator()
        with self.assertRaises(ValueError):
            item.update_driver("center", False, "clear", 1.0)
        self.assertFalse(item.update_filter(
            "left", "UNKNOWN", 0, "unknown", False,
            True, True, False, 1.0))
        self.assertEqual(
            item.fault_reason, "left filter reported an invalid state")


if __name__ == "__main__":
    unittest.main()
