#!/usr/bin/env python3
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LAUNCH = ROOT / "src" / "pi05_left_teleop" / "launch"


class DirectTeleopTest(unittest.TestCase):
    def test_launch_files_are_valid_xml(self):
        for name in ("side_teleop.launch", "left_teleop.launch",
                     "right_teleop.launch", "dual_teleop.launch"):
            ET.parse(str(LAUNCH / name))

    def test_side_launch_connects_ik_directly_to_driver(self):
        text = (LAUNCH / "side_teleop.launch").read_text(encoding="utf-8")
        self.assertIn("_arm/joint_ctrl_raw", text)
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


if __name__ == "__main__":
    unittest.main()
