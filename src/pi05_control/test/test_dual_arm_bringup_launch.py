#!/usr/bin/env python3

import pathlib
import unittest
import xml.etree.ElementTree as ET


PACKAGE_PATH = pathlib.Path(__file__).parents[1]
LAUNCH_PATH = PACKAGE_PATH / "launch" / "s11_dual_arm_bringup.launch"
NODE_PATH = PACKAGE_PATH / "scripts" / "dual_arm_safety_coordinator_node.py"


class DualArmBringupLaunchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(str(LAUNCH_PATH)).getroot()
        cls.args = {item.attrib["name"]: item.attrib for item in cls.root.findall("arg")}
        cls.includes = cls.root.findall("include")
        cls.node = cls.root.find("node")
        cls.source = NODE_PATH.read_text(encoding="utf-8")

    def test_mode_is_one_closed_selector(self):
        self.assertEqual(self.args, {"mode": {"name": "mode", "default": "off"}})
        source = LAUNCH_PATH.read_text(encoding="utf-8")
        mapping_tokens = (
            "{'off': 'false', 'simulation': 'false', 'hardware': 'true'}",
            "{'off': 'false', 'simulation': 'true', 'hardware': 'true'}",
        )
        for token in mapping_tokens:
            self.assertIn(token, source)
        self.assertNotIn("start_left", source)
        self.assertNotIn("start_right", source)

    def test_both_sides_use_same_driver_and_filter_launches(self):
        self.assertEqual(len(self.includes), 4)
        driver_includes = self.includes[:2]
        filter_includes = self.includes[2:]
        self.assertTrue(all("s09_single_arm_driver.launch" in item.attrib["file"]
                            for item in driver_includes))
        self.assertTrue(all("s10_arm_safety_filter.launch" in item.attrib["file"]
                            for item in filter_includes))
        for expected_side, item in zip(("left", "right"), driver_includes):
            args = {child.attrib["name"]: child.attrib["value"]
                    for child in item.findall("arg")}
            self.assertEqual(args["side"], expected_side)
        for expected_side, item in zip(("left", "right"), filter_includes):
            args = {child.attrib["name"]: child.attrib["value"]
                    for child in item.findall("arg")}
            self.assertEqual(args["side"], expected_side)

    def test_feedback_and_commands_have_one_explicit_path_per_side(self):
        for item in self.includes[:2]:
            args = {child.attrib["name"]: child.attrib["value"]
                    for child in item.findall("arg")}
            self.assertEqual(args["publish_business_feedback"], "true")
        for item in self.includes[2:]:
            args = {child.attrib["name"]: child.attrib["value"]
                    for child in item.findall("arg")}
            self.assertEqual(args["connect_driver"], "true")
        self.assertFalse(any(item.findall("remap") for item in self.includes))

    def test_coordinator_owns_public_services_and_raw_service_calls(self):
        self.assertEqual(self.node.attrib["name"], "dual_arm_safety_coordinator")
        self.assertIn('/dual_arm/enable_srv', self.source)
        self.assertIn('/dual_arm/stop_srv', self.source)
        self.assertIn('/dual_arm/reset_fault', self.source)
        self.assertIn('"/{}_arm/enable_srv_raw".format(side)', self.source)
        self.assertIn('"/{}_arm/stop_srv_raw".format(side)', self.source)
        self.assertIn("for side in SIDES", self.source)
        fault_worker = self.source.index("def _fault_response_worker")
        revoke = self.source.index("self.publish_authorization(False)", fault_worker)
        stop = self.source.index("stop_results", revoke)
        disable = self.source.index("disable_results", stop)
        self.assertLess(revoke, stop)
        self.assertLess(stop, disable)


if __name__ == "__main__":
    unittest.main()
