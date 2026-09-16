#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LAUNCH = ROOT / "src" / "pi05_left_teleop" / "launch"


class DirectTeleopTest(unittest.TestCase):
    def test_launch_files_are_valid_xml(self):
        for name in ("side_teleop.launch", "left_teleop.launch",
                     "right_teleop.launch", "dual_teleop.launch"):
            ET.parse(str(LAUNCH / name))

    def test_side_launch_supports_direct_and_smoothed_commands(self):
        text = (LAUNCH / "side_teleop.launch").read_text(encoding="utf-8")
        self.assertIn("_arm/joint_ctrl_raw", text)
        self.assertEqual(text.count('to="$(arg feedback_topic)"'), 4)
        self.assertIn("joint_command_smoother.py", text)
        self.assertIn("ik_target_raw", text)
        self.assertIn("if arg('smooth_commands') else arg('command_topic')", text)
        self.assertIn("left_piper", text)
        self.assertIn("right_piper", text)
        self.assertNotIn("safety_filter", text)
        self.assertNotIn("control_authorized", text)
        self.assertNotIn("supervisor.py", text)

    def test_compatibility_entrypoints_keep_fixed_can_names(self):
        left = (LAUNCH / "left_teleop.launch").read_text(encoding="utf-8")
        right = (LAUNCH / "right_teleop.launch").read_text(encoding="utf-8")
        dual = (LAUNCH / "dual_teleop.launch").read_text(encoding="utf-8")
        self.assertIn('default="left_piper"', left)
        self.assertIn('default="right_piper"', right)
        self.assertIn('default="left_piper"', dual)
        self.assertIn('default="right_piper"', dual)

    def test_component_has_no_review_hash_gate(self):
        text = (ROOT / "src" / "pi05_left_teleop" / "scripts" /
                "component.py").read_text(encoding="utf-8")
        self.assertNotIn("sha256", text)
        self.assertNotIn("reviewed baseline", text)
        self.assertIn("choices=('left', 'right')", text)

    def test_existing_environment_and_overlay_names_are_preserved(self):
        env = (ROOT / "config" / "pi05.env.example").read_text(encoding="utf-8")
        for name in (
            "PI05_LEFT_CAN_INTERFACE", "PI05_LEFT_CAN_USB_BUS_INFO",
            "PI05_RIGHT_CAN_INTERFACE", "PI05_RIGHT_CAN_USB_BUS_INFO",
            "PI05_LEFT_PIKA_SERIAL_ALIAS", "PI05_RIGHT_PIKA_SERIAL_ALIAS",
            "PI05_ARM_MODE", "PI05_AUTO_ENABLE",
        ):
            self.assertIn(name + "=", env)
        start = (ROOT / "scripts" / "start_teleop.sh").read_text(encoding="utf-8")
        self.assertIn("/home/mips/pika_ros/install/setup.bash", start)
        self.assertIn("/home/mips/robot/pi05-upstream-ws/devel/setup.bash", start)
        self.assertIn('configure_can.sh\" check', start)


class StartupCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "check_teleop_start", ROOT / "scripts/check_teleop_start.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.check = staticmethod(module.check_start)

    def state(self, extra_publishers=None, subscribers=None, services=None):
        return ([('/pi05/pika_input/left/pose', ['/left_input']),
                 ('/pi05/pika_input/right/pose', ['/right_input'])]
                + (extra_publishers or []), subscribers or [], services or [])

    def test_each_entry_accepts_input_only(self):
        for side in ('left', 'right', 'dual'):
            self.check(side, self.state())

    def test_opposite_arm_can_continue_running(self):
        for side, other, suffix in (('left', 'right', 'r'), ('right', 'left', 'l')):
            state = self.state(
                [('/joint_states_single_' + suffix,
                  ['/' + other + '_arm/piper_driver_raw'])],
                [('/' + other + '_arm/joint_ctrl_raw',
                  ['/' + other + '_arm/piper_driver_raw'])],
                [('/teleop_trigger_' + suffix, ['/' + other + '_arm/teleop/teleop'])])
            self.check(side, state)
            with self.assertRaisesRegex(ValueError, 'conflicting'):
                self.check('dual', state)

    def test_same_side_and_legacy_drivers_are_rejected(self):
        for node in ('/left_arm/piper_driver_raw', '/piper_ctrl_single_node',
                     '/teleop_publisher'):
            with self.assertRaisesRegex(ValueError, 'conflicting'):
                self.check('left', self.state([('/some_topic', [node])]))

    def test_command_owner_with_unrelated_name_is_rejected(self):
        for field in ('extra_publishers', 'subscribers', 'services'):
            with self.assertRaisesRegex(ValueError, 'conflicting'):
                self.check('left', self.state(**{
                    field: [('/left_arm/joint_ctrl_raw', ['/custom_node'])]}))
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            self.check('right', self.state(services=[
                ('/teleop_trigger_r', ['/custom_node'])]))

    def test_readonly_feedback_can_keep_running(self):
        state = self.state(extra_publishers=[
            ('/left_arm/joint_states_raw', ['/left_arm/piper_readonly_feedback']),
            ('/right_arm/joint_states_raw', ['/right_arm/piper_readonly_feedback'])],
            services=[('/left_arm/piper_readonly_feedback/get_loggers',
                       ['/left_arm/piper_readonly_feedback'])])
        for side in ('left', 'right', 'dual'):
            self.check(side, state)

    def test_readonly_named_node_cannot_own_commands(self):
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            self.check('left', self.state(subscribers=[
                ('/left_arm/joint_ctrl_raw', ['/left_arm/piper_readonly_feedback'])]))

    def test_missing_or_ownerless_pose_is_rejected(self):
        for publishers in ([], [('/pi05/pika_input/left/pose', [])]):
            with self.assertRaisesRegex(ValueError, 'missing pose: left'):
                self.check('left', (publishers, [], []))
        with self.assertRaisesRegex(ValueError, 'missing pose: right'):
            self.check('dual', ([('/pi05/pika_input/left/pose', ['/input'])], [], []))


if __name__ == "__main__":
    unittest.main()
