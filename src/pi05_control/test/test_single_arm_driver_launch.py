#!/usr/bin/env python3

import pathlib
import unittest
import xml.etree.ElementTree as ET


LAUNCH_PATH = pathlib.Path(__file__).parents[1] / "launch" / "s09_single_arm_driver.launch"


class SingleArmDriverLaunchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(str(LAUNCH_PATH)).getroot()
        cls.args = {item.attrib["name"]: item.attrib for item in cls.root.findall("arg")}
        cls.group = cls.root.find("group")
        cls.node = cls.group.find("node")

    def test_side_is_required_and_mappings_are_closed(self):
        self.assertNotIn("default", self.args["side"])
        self.assertEqual(self.args["start_driver"].get("default"), "false")
        self.assertEqual(set(self.args), {"side", "start_driver"})
        namespace = self.group.attrib["ns"]
        self.assertIn("{'left': 'left_arm', 'right': 'right_arm'}", namespace)
        self.assertIn("[arg('side')]", namespace)

    def test_driver_start_is_explicit_and_never_auto_enables(self):
        self.assertEqual(self.node.attrib.get("if"), "$(arg start_driver)")
        self.assertEqual(self.node.attrib.get("pkg"), "piper")
        self.assertEqual(self.node.attrib.get("type"), "piper_ctrl_single_node.py")
        self.assertEqual(self.node.attrib.get("name"), "piper_driver_raw")
        params = {item.attrib["name"]: item.attrib["value"] for item in self.node.findall("param")}
        self.assertIn("{'left': 'left_piper', 'right': 'right_piper'}", params["can_port"])
        self.assertIn("[arg('side')]", params["can_port"])
        self.assertEqual(params["auto_enable"], "false")
        self.assertNotIn("hold_position_on_enable", params)

    def test_every_driver_interface_is_relative_and_remapped(self):
        remaps = {item.attrib["from"]: item.attrib["to"] for item in self.node.findall("remap")}
        self.assertEqual(
            remaps,
            {
                "joint_ctrl_single": "joint_ctrl_raw",
                "pos_cmd": "pos_cmd_raw",
                "enable_flag": "enable_flag_raw",
                "joint_states_single": "joint_states_driver_raw",
                "arm_status": "arm_status",
                "end_pose_euler": "end_pose_euler_raw",
                "end_pose": "end_pose_raw",
                "enable_srv": "enable_srv_raw",
                "stop_srv": "stop_srv_raw",
                "gripper_srv": "gripper_srv_raw",
                "reset_srv": "reset_srv_raw",
                "go_zero_srv": "go_zero_srv_raw",
                "block_arm": "block_arm_raw",
            },
        )
        for source, target in remaps.items():
            self.assertFalse(source.startswith("/"), source)
            self.assertFalse(target.startswith("/"), target)


if __name__ == "__main__":
    unittest.main()
