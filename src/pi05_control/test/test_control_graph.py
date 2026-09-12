#!/usr/bin/env python3

import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).parents[3] / "scripts" / "check_control_graph.py"
SPEC = importlib.util.spec_from_file_location("check_control_graph", str(SCRIPT))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_graph(mode):
    coordinator = "/dual_arm_safety_coordinator"
    nodes = {coordinator, "/left_arm/safety_filter", "/right_arm/safety_filter"}
    publishers = {}
    subscribers = {}
    services = {
        "/dual_arm/enable_srv": {coordinator},
        "/dual_arm/stop_srv": {coordinator},
        "/dual_arm/reset_fault": {coordinator},
    }
    for side, suffix in (("left", "l"), ("right", "r")):
        safety_filter = "/{}_arm/safety_filter".format(side)
        driver = "/{}_arm/piper_driver_raw".format(side)
        authorization = "/{}_arm/control_authorized".format(side)
        command = "/{}_arm/joint_ctrl_raw".format(side)
        feedback = "/joint_states_single_{}".format(suffix)
        publishers[authorization] = {coordinator}
        subscribers[authorization] = {safety_filter}
        publishers[command] = {safety_filter}
        subscribers[feedback] = {safety_filter}
        if mode == "hardware":
            nodes.add(driver)
            subscribers[command] = {driver}
            publishers[feedback] = {driver}
            for leaf in ("enable_srv_raw", "stop_srv_raw", "gripper_srv_raw",
                         "reset_srv_raw", "go_zero_srv_raw", "block_arm_raw"):
                services["/{}_arm/{}".format(side, leaf)] = {driver}
    return nodes, publishers, subscribers, services


class ControlGraphTest(unittest.TestCase):
    def test_accepts_expected_simulation_and_hardware_graphs(self):
        for mode in ("simulation", "hardware"):
            with self.subTest(mode=mode):
                self.assertEqual(MODULE.validate_graph(mode, *valid_graph(mode)), [])

    def test_rejects_command_and_authorization_bypasses(self):
        graph = valid_graph("hardware")
        graph[1]["/left_arm/joint_ctrl_raw"].add("/rogue_command")
        graph[1]["/right_arm/control_authorized"].add("/rogue_enable")
        errors = MODULE.validate_graph("hardware", *graph)
        self.assertTrue(any("joint_ctrl_raw" in item for item in errors))
        self.assertTrue(any("control_authorized" in item for item in errors))

    def test_rejects_global_legacy_control_interfaces(self):
        graph = valid_graph("simulation")
        graph[2]["/pos_cmd"] = {"/legacy_driver"}
        errors = MODULE.validate_graph("simulation", *graph)
        self.assertTrue(any("ambiguous global" in item for item in errors))

    def test_rejects_partial_side_and_wrong_service_owner(self):
        graph = valid_graph("hardware")
        graph[0].remove("/right_arm/piper_driver_raw")
        graph[3]["/dual_arm/enable_srv"] = {"/other"}
        errors = MODULE.validate_graph("hardware", *graph)
        self.assertTrue(any("missing managed nodes" in item for item in errors))
        self.assertTrue(any("enable_srv providers" in item for item in errors))

    def test_checker_source_is_read_only(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for token in ("rospy.Publisher", "rospy.ServiceProxy", "cansend", "socket.CAN_RAW"):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
