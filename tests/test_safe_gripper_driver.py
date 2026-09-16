#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/pi05_control/scripts/safe_gripper_piper_driver.py"
spec = importlib.util.spec_from_file_location("safe_gripper_driver", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Response:
    def __init__(self, value):
        self.enable_response = value


class Piper:
    def __init__(self):
        self.calls = []

    def GetArmJointMsgs(self):
        state = type("Joint", (), {"joint_%d" % i: i * 100 for i in range(1, 7)})()
        return type("Joints", (), {"joint_state": state})()

    def GetArmGripperMsgs(self):
        state = type("Gripper", (), {"grippers_angle": 42000})()
        return type("GripperMessage", (), {"gripper_state": state})()

    def GetArmLowSpdInfoMsgs(self):
        motor = type("Motor", (), {"foc_status": type(
            "Status", (), {"driver_enable_status": True})()})
        return type("Feedback", (), {"motor_%d" % i: motor for i in range(1, 7)})()

    def MotionCtrl_2(self, *values):
        self.calls.append(("mode", values))

    def JointCtrl(self, *values):
        self.calls.append(("joints", values))

    def GripperCtrl(self, *values):
        self.calls.append(("gripper", values))

    def EnableArm(self, value):
        self.calls.append(("enable", value))

    def DisableArm(self, value):
        self.calls.append(("disable", value))


class SafeGripperDriverTest(unittest.TestCase):
    def test_enable_holds_measured_gripper_instead_of_closing(self):
        vendor = type("Vendor", (), {
            "C_PiperRosNode": type("NodeClass", (), {}),
            "EnableResponse": Response,
        })
        module.install_safe_callbacks(vendor)
        node = vendor.C_PiperRosNode()
        node.piper = Piper()
        node.gripper_exist = True
        response = node.handle_enable_service(
            type("Request", (), {"enable_request": True})())
        self.assertTrue(response.enable_response)
        gripper_calls = [values for name, values in node.piper.calls if name == "gripper"]
        self.assertEqual(gripper_calls, [(42000, 1000, 1, 0), (42000, 1000, 1, 0)])
        self.assertIn(("enable", 7), node.piper.calls)

    def test_source_rejects_auto_enable_and_has_no_enable_close_command(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("safe gripper driver requires auto_enable=false", text)
        self.assertNotIn("GripperCtrl(0, 1000, 0x01", text)


if __name__ == "__main__":
    unittest.main()
