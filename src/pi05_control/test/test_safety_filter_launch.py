#!/usr/bin/env python3

import pathlib
import unittest
import xml.etree.ElementTree as ET


PACKAGE_PATH = pathlib.Path(__file__).parents[1]
LAUNCH_PATH = PACKAGE_PATH / "launch" / "s10_arm_safety_filter.launch"
NODE_PATH = PACKAGE_PATH / "scripts" / "arm_safety_filter_node.py"


class SafetyFilterLaunchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(str(LAUNCH_PATH)).getroot()
        cls.args = {item.attrib["name"]: item.attrib for item in cls.root.findall("arg")}
        cls.group = cls.root.find("group")
        cls.node = cls.group.find("node")
        cls.source = NODE_PATH.read_text(encoding="utf-8")

    def test_side_is_required_and_start_is_opt_in(self):
        self.assertEqual(set(self.args), {"side", "start_filter"})
        self.assertNotIn("default", self.args["side"])
        self.assertEqual(self.args["start_filter"].get("default"), "false")
        self.assertIn("{'left': 'left_arm', 'right': 'right_arm'}", self.group.attrib["ns"])
        self.assertEqual(self.node.attrib.get("if"), "$(arg start_filter)")
        self.assertEqual(self.node.attrib.get("type"), "arm_safety_filter_node.py")

    def test_node_loads_one_shared_configuration(self):
        params = {item.attrib["name"]: item.attrib["value"] for item in self.node.findall("param")}
        self.assertEqual(params, {"side": "$(arg side)"})
        rosparam = self.node.find("rosparam")
        self.assertIn("pi05_bringup", rosparam.attrib["file"])
        self.assertTrue(rosparam.attrib["file"].endswith("/config/arm_filter.yaml"))

    def test_no_driver_service_or_raw_driver_publisher(self):
        forbidden = (
            "enable_srv_raw",
            "stop_srv_raw",
            "joint_ctrl_raw",
            "pos_cmd_raw",
            "ServiceProxy",
        )
        for token in forbidden:
            self.assertNotIn(token, self.source)
        self.assertIn("/control_authorized", self.source)
        self.assertIn("/safety_filter_status", self.source)


if __name__ == "__main__":
    unittest.main()
