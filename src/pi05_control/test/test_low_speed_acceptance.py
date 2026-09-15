#!/usr/bin/env python3

import pathlib
import sys
import tempfile
import unittest


PACKAGE = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(PACKAGE / "src"))

from pi05_control.low_speed_acceptance import (  # noqa: E402
    AcceptanceConfig,
    MotionEvidence,
    ReturnEvidence,
    StableBaseline,
    failure_actions,
    maximum_joint_shift,
    require_enable_settle_clearance,
    require_move_clearance,
    require_legacy_stack_compatible_firmware,
)


class AcceptanceConfigTest(unittest.TestCase):
    def test_allows_only_single_side_small_slow_motion(self):
        item = AcceptanceConfig("left", 2)
        self.assertEqual(item.delta_rad, 0.005)
        for values in (
            ("center", 2, 0.005, 5.0),
            ("left", 0, 0.005, 5.0),
            ("left", 2, 0.006, 5.0),
            ("left", 2, 0.005, 5.1),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                AcceptanceConfig(*values)


class StableBaselineTest(unittest.TestCase):
    def test_ignores_pre_recovery_and_averages_stable_post_recovery_samples(self):
        item = StableBaseline(sample_count=3, tolerance_rad=0.001)
        item.begin_after_recovery(10.0)
        self.assertIsNone(item.add(9.9, [9.0] * 7))
        self.assertIsNone(item.add(10.1, [1.0] * 7))
        self.assertIsNone(item.add(10.2, [1.0002] * 7))
        result = item.add(10.3, [1.0004] * 7)
        self.assertAlmostEqual(result[1], 1.0002)

    def test_unstable_window_must_be_recollected(self):
        item = StableBaseline(sample_count=3, tolerance_rad=0.001)
        item.begin_after_recovery(0.0)
        item.add(0.1, [0.0] * 7)
        item.add(0.2, [0.0] * 7)
        self.assertIsNone(item.add(0.3, [0.01] * 7))
        self.assertIsNone(item.add(0.4, [0.01] * 7))
        result = item.add(0.5, [0.01] * 7)
        self.assertEqual(result, (0.01,) * 7)

    def test_recovery_resets_existing_samples(self):
        item = StableBaseline(sample_count=3)
        item.begin_after_recovery(0.0)
        item.add(0.1, [0.0] * 7)
        item.add(0.2, [0.0] * 7)
        item.begin_after_recovery(1.0)
        self.assertIsNone(item.add(1.1, [1.0] * 7))


class JointShiftTest(unittest.TestCase):
    def test_reports_largest_signed_joint_shift(self):
        before = [0.0] * 7
        after = [0.001, -0.003, 0.002, 0.0, 0.0, 0.0, 0.04]
        self.assertEqual(maximum_joint_shift(before, after), (2, -0.003))

    def test_can_exclude_commanded_joint(self):
        before = [0.0] * 7
        after = [0.001, 0.005, -0.002, 0.0, 0.0, 0.0, 0.0]
        self.assertEqual(maximum_joint_shift(before, after, excluded_joint=2), (3, -0.002))


class MotionEvidenceTest(unittest.TestCase):
    def test_selected_joint_window_error_includes_relative_motion(self):
        item = MotionEvidence([0.0] * 7, 2, 0.005)
        with self.assertRaisesRegex(
                RuntimeError, r"selected J2.*delta=0.021000"):
            item.add([0.0, 0.021, 0.0, 0.0, 0.0, 0.0, 0.0])

    def test_rejects_boolean_joint_number(self):
        with self.assertRaises(ValueError):
            MotionEvidence([0.0] * 7, True, 0.005)

    def test_requires_three_clean_motion_samples(self):
        item = MotionEvidence([0.0] * 7, 2, 0.005)
        moved = [0.0, 0.003, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.assertFalse(item.add(moved))
        self.assertFalse(item.add(moved))
        self.assertTrue(item.add(moved))

    def test_one_ordinary_drift_sample_does_not_fail_motion(self):
        item = MotionEvidence([0.0] * 7, 2, 0.005)
        transient = [0.0, 0.003, -0.005094, 0.0, 0.0, 0.0, 0.0]
        self.assertFalse(item.add(transient))
        clean = [0.0, 0.003, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.assertFalse(item.add(clean))
        self.assertFalse(item.add(clean))
        self.assertTrue(item.add(clean))

    def test_repeated_drift_still_fails_at_original_limit(self):
        item = MotionEvidence([0.0] * 7, 2, 0.005)
        drift = [0.0, 0.003, -0.0021, 0.0, 0.0, 0.0, 0.0]
        self.assertFalse(item.add(drift))
        self.assertFalse(item.add(drift))
        with self.assertRaisesRegex(
                RuntimeError, r"J3 drift exceeded 0.002 rad.*selected J2 delta="):
            item.add(drift)

    def test_hard_drift_fails_on_first_sample(self):
        item = MotionEvidence([0.0] * 7, 2, 0.005)
        with self.assertRaisesRegex(RuntimeError, "single-sample hard drift"):
            item.add([0.0, 0.003, -0.011, 0.0, 0.0, 0.0, 0.0])


class ReturnEvidenceTest(unittest.TestCase):
    def test_requires_three_consecutive_return_samples(self):
        item = ReturnEvidence([0.0] * 7)
        self.assertFalse(item.add([0.0005] * 6 + [0.0]))
        self.assertFalse(item.add([0.002] + [0.0] * 6))
        self.assertFalse(item.add([0.0005] * 6 + [0.0]))
        self.assertFalse(item.add([0.0005] * 6 + [0.0]))
        self.assertTrue(item.add([0.0005] * 6 + [0.0]))


class FailurePolicyTest(unittest.TestCase):
    def test_failure_never_requests_disable(self):
        self.assertEqual(
            failure_actions(),
            ("software_stop", "hold_enabled", "operator_support_required"),
        )
        self.assertNotIn("disable", failure_actions())

    def test_move_path_cannot_call_disable(self):
        source = (PACKAGE / "scripts" / "single_arm_low_speed_acceptance.py").read_text(
            encoding="utf-8")
        move_start = source.index("    def run_move(")
        disable_start = source.index("    def run_supported_disable(")
        move_source = source[move_start:disable_start]
        self.assertIn("self._stop_only()", move_source)
        self.assertIn("enable_attempted = True", move_source)
        self.assertNotIn("enable(False)", move_source)
        self.assertNotIn("run_supported_disable", move_source)
        disable_source = source[disable_start:source.index("\ndef main(", disable_start)]
        self.assertIn("Enable)(False)", disable_source)

    def test_passive_can_source_has_no_transmit_api(self):
        source = (PACKAGE / "scripts" / "single_arm_low_speed_acceptance.py").read_text(
            encoding="utf-8")
        start = source.index("class PassiveCanFeedbackSource")
        end = source.index("\ndef parser", start)
        passive_source = source[start:end]
        self.assertIn(".recv(", passive_source)
        self.assertNotIn(".send(", passive_source)
        self.assertNotIn("sendmsg", passive_source)

    def test_ros_dependencies_load_only_after_dry_run_returns(self):
        source = (PACKAGE / "scripts" / "single_arm_low_speed_acceptance.py").read_text(
            encoding="utf-8")
        main_start = source.index("def main(")
        main_source = source[main_start:]
        dry_run_return = main_source.index("if not args.apply:\n            return 0")
        dependency_load = main_source.index("load_ros_dependencies()")
        self.assertLess(dry_run_return, dependency_load)

    def test_resume_precedes_new_stable_baseline(self):
        source = (PACKAGE / "scripts" / "single_arm_low_speed_acceptance.py").read_text(
            encoding="utf-8")
        move_start = source.index("    def run_move(")
        disable_start = source.index("    def run_supported_disable(")
        move_source = source[move_start:disable_start]
        resume = move_source.index("response = rospy.ServiceProxy(self.reset_service")
        new_epoch = move_source.index("recovery_time = rospy.Time.now().to_sec()", resume)
        baseline = move_source.index("baseline = self._stable_baseline", new_epoch)
        self.assertLess(resume, new_epoch)
        self.assertLess(new_epoch, baseline)


class MoveClearanceTest(unittest.TestCase):
    @staticmethod
    def write_record(directory, body):
        path = pathlib.Path(directory) / "s12.env"
        path.write_text(body, encoding="utf-8")
        return path

    def test_missing_record_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            require_move_clearance("/definitely/missing/pi05-s12.env", "left")

    def test_incomplete_record_lists_required_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_record(directory, "PI05_S12_INCIDENT_REVIEW=pass\n")
            with self.assertRaisesRegex(ValueError, "FALL_ARREST_SUPPORT=pass"):
                require_move_clearance(path, "left")

    def test_side_specific_inspection_cannot_be_substituted(self):
        body = """\
PI05_S12_INCIDENT_REVIEW=pass
PI05_S12_FALL_ARREST_SUPPORT=pass
PI05_S12_HARDWARE_ESTOP=pass
PI05_S12_TWO_PERSON_TEAM=yes
PI05_S12_RETEST_APPROVED=yes
PI05_S12_RIGHT_ENABLE_SETTLE=pass
PI05_S12_RIGHT_MECHANICAL_INSPECTION=pass
"""
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_record(directory, body)
            with self.assertRaisesRegex(ValueError, "LEFT_MECHANICAL_INSPECTION=pass"):
                require_move_clearance(path, "left")
            self.assertTrue(require_move_clearance(path, "right"))

    def test_complete_record_passes_without_identity_fields(self):
        body = """\
# No names or hardware identifiers.
PI05_S12_INCIDENT_REVIEW=pass
PI05_S12_FALL_ARREST_SUPPORT=pass
PI05_S12_HARDWARE_ESTOP=pass
PI05_S12_TWO_PERSON_TEAM=yes
PI05_S12_RETEST_APPROVED=yes
PI05_S12_LEFT_ENABLE_SETTLE=pass
PI05_S12_LEFT_MECHANICAL_INSPECTION=pass
"""
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(require_move_clearance(
                self.write_record(directory, body), "left"))


class FirmwareRouteGateTest(unittest.TestCase):
    @staticmethod
    def write_record(directory, body):
        path = pathlib.Path(directory) / "hardware.env"
        path.write_text(body, encoding="utf-8")
        return path

    def test_accepts_current_firmware_on_vendor_legacy_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_record(
                directory, "PI05_LEFT_PIPER_FIRMWARE=S-V1.8-2\n")
            self.assertEqual(
                require_legacy_stack_compatible_firmware(path, "left"), "S-V1.8-2")

    def test_rejects_new_stack_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_record(
                directory, "PI05_RIGHT_PIPER_FIRMWARE=S-V1.8-8\n")
            with self.assertRaisesRegex(ValueError, "outside the reviewed legacy"):
                require_legacy_stack_compatible_firmware(path, "right")

    def test_rejects_unreviewed_future_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_record(
                directory, "PI05_RIGHT_PIPER_FIRMWARE=S-V1.9-0\n")
            with self.assertRaisesRegex(ValueError, "outside the reviewed legacy"):
                require_legacy_stack_compatible_firmware(path, "right")

    def test_missing_or_partial_version_fails_closed(self):
        for body in ("", "PI05_LEFT_PIPER_FIRMWARE=S-V1\n"):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                path = self.write_record(directory, body)
                with self.assertRaisesRegex(ValueError, "complete S-Vx.y-z"):
                    require_legacy_stack_compatible_firmware(path, "left")


class EnableSettleClearanceTest(unittest.TestCase):
    def test_separate_approval_does_not_require_prior_settle_result(self):
        body = """\
PI05_S12_INCIDENT_REVIEW=pass
PI05_S12_FALL_ARREST_SUPPORT=pass
PI05_S12_HARDWARE_ESTOP=pass
PI05_S12_TWO_PERSON_TEAM=yes
PI05_S12_LEFT_MECHANICAL_INSPECTION=pass
PI05_S12_ENABLE_SETTLE_APPROVED=yes
"""
        with tempfile.TemporaryDirectory() as directory:
            path = MoveClearanceTest.write_record(directory, body)
            self.assertTrue(require_enable_settle_clearance(path, "left"))

    def test_move_requires_completed_enable_settle(self):
        body = """\
PI05_S12_INCIDENT_REVIEW=pass
PI05_S12_FALL_ARREST_SUPPORT=pass
PI05_S12_HARDWARE_ESTOP=pass
PI05_S12_TWO_PERSON_TEAM=yes
PI05_S12_LEFT_MECHANICAL_INSPECTION=pass
PI05_S12_RETEST_APPROVED=yes
"""
        with tempfile.TemporaryDirectory() as directory:
            path = MoveClearanceTest.write_record(directory, body)
            with self.assertRaisesRegex(ValueError, "LEFT_ENABLE_SETTLE=pass"):
                require_move_clearance(path, "left")


if __name__ == "__main__":
    unittest.main()
