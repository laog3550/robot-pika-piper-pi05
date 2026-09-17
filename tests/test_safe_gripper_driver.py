#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


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


def fake_rospy(services, subscribers, logins):
    rospy = types.ModuleType("rospy")
    rospy.loginfo = lambda *args, **kwargs: logins.append(args)
    rospy.logwarn = lambda *args, **kwargs: logins.append(args)

    class Service:
        def __init__(self, name, srvtype, handler):
            self.name, self.handler = name, handler
            services.append(self)

        def shutdown(self, _reason=""):
            pass

    rospy.Service = Service

    class Subscriber:
        def __init__(self, name, datatype, handler, **_kwargs):
            self.name, self.handler = name, handler
            subscribers.append(self)

    rospy.Subscriber = Subscriber
    return rospy


class SafeGripperDriverTest(unittest.TestCase):
    def vendor(self, services, subscribers, logins):
        """复刻厂商结构：构造时就捕获服务和话题回调。"""
        rospy = fake_rospy(services, subscribers, logins)

        class Node:
            def __init__(self):
                self.piper = Piper()
                self.gripper_exist = True
                self.gripper_val_mutiple = 1
                self.block_ctrl_flag = False
                self._C_PiperRosNode__enable_flag = True
                self.enable_service = rospy.Service(
                    "enable_srv", Response, self.handle_enable_service)
                self.enable_subscriber = rospy.Subscriber(
                    "enable_flag", object, self.enable_callback)

            def handle_enable_service(self, request):
                raise AssertionError("厂商原始 enable 实现被调用：安装未生效")

            def enable_callback(self, flag):
                raise AssertionError("厂商原始 enable_callback 被调用：安装未生效")

            def joint_callback(self, message):
                raise AssertionError("厂商原始 joint_callback 被调用：安装未生效")

            def GetEnableFlag(self):
                return self._C_PiperRosNode__enable_flag

        return rospy, type("Vendor", (), {
            "C_PiperRosNode": Node, "EnableResponse": Response})

    def test_installed_service_uses_hold_position_semantics(self):
        services, subscribers, logins = [], [], []
        rospy, vendor = self.vendor(services, subscribers, logins)
        with patch.dict(sys.modules, {"rospy": rospy}):
            module.install_safe_callbacks(vendor)
            node = vendor.C_PiperRosNode()
            self.assertEqual(len(services), 1)
            response = services[-1].handler(
                type("Request", (), {"enable_request": True})())
        self.assertTrue(response.enable_response)
        gripper_calls = [v for n, v in node.piper.calls if n == "gripper"]
        self.assertEqual(gripper_calls, [(42000, 1000, 1, 0), (42000, 1000, 1, 0)],
                         "使能时应保持实测开度 42000，不得下发 0（闭合）")
        self.assertNotIn(0, [v[0] for v in gripper_calls])
        self.assertIn(("enable", 7), node.piper.calls)
        mode_calls = [v for n, v in node.piper.calls if n == "mode"]
        self.assertEqual(mode_calls, [(0x01, 0x01, 10, 0x00)] * 2,
                         "JointCtrl 使能保持必须使用位置速度模式，不得进入 MIT 模式")
        self.assertTrue(any("enable result" in str(a) for a in logins),
                        "使能结果必须写入日志，便于排查'指令在发但机械臂不动'")

    def test_installed_callback_uses_hold_position_semantics(self):
        services, subscribers, logins = [], [], []
        rospy, vendor = self.vendor(services, subscribers, logins)
        with patch.dict(sys.modules, {"rospy": rospy}):
            module.install_safe_callbacks(vendor)
            node = vendor.C_PiperRosNode()
            self.assertEqual(len(subscribers), 1)
            # 调用构造时已捕获的回调，而不是事后查找实例属性。
            subscribers[-1].handler(type("Flag", (), {"data": True})())
        gripper_calls = [v for n, v in node.piper.calls if n == "gripper"]
        self.assertEqual(gripper_calls, [(42000, 1000, 1, 0), (42000, 1000, 1, 0)])

    def test_enable_failure_is_logged_as_warning(self):
        services, subscribers, logins = [], [], []
        rospy, vendor = self.vendor(services, subscribers, logins)

        class Stuck(Piper):
            def GetArmLowSpdInfoMsgs(self):
                motor = type("Motor", (), {"foc_status": type(
                    "Status", (), {"driver_enable_status": False})()})
                return type("Feedback", (), {"motor_%d" % i: motor
                                             for i in range(1, 7)})()

        with patch.dict(sys.modules, {"rospy": rospy}), \
                patch.object(module.time, "sleep", lambda _s: None):
            module.install_safe_callbacks(vendor)
            node = vendor.C_PiperRosNode()
            node.piper = Stuck()
            response = services[-1].handler(
                type("Request", (), {"enable_request": True})())
        self.assertFalse(response.enable_response)
        warnings = [a for a in logins if "enable result" in str(a) and "NOT" in str(a)]
        self.assertTrue(warnings, "使能失败必须留下警告，指出电机未就绪")

    def test_joint_callback_allows_configured_100mm_target(self):
        services, subscribers, logins = [], [], []
        rospy, vendor = self.vendor(services, subscribers, logins)
        with patch.dict(sys.modules, {"rospy": rospy}):
            module.install_safe_callbacks(vendor, 100000)
            node = vendor.C_PiperRosNode()
            node.joint_callback(type("JointState", (), {
                "position": [0.0] * 6 + [0.10],
                "velocity": [0.0] * 6 + [20.0],
                "effort": [0.0] * 6 + [1.0],
            })())
        self.assertIn(("mode", (0x01, 0x01, 20, 0x00)), node.piper.calls)
        self.assertIn(("joints", (0, 0, 0, 0, 0, 0)), node.piper.calls)
        self.assertIn(("gripper", (100000, 1000, 0x01, 0)), node.piper.calls)

    def test_joint_callback_clamps_to_configured_maximum(self):
        services, subscribers, logins = [], [], []
        rospy, vendor = self.vendor(services, subscribers, logins)
        with patch.dict(sys.modules, {"rospy": rospy}):
            module.install_safe_callbacks(vendor, 70000)
            node = vendor.C_PiperRosNode()
            node.joint_callback(type("JointState", (), {
                "position": [0.0] * 6 + [0.10],
                "velocity": [],
                "effort": [],
            })())
        self.assertIn(("gripper", (70000, 1000, 0x01, 0)), node.piper.calls)
        self.assertIn(("mode", (0x01, 0x01, 50, 0x00)), node.piper.calls)

    def test_configured_gripper_maximum_converts_metres_to_raw_units(self):
        rospy = types.SimpleNamespace(get_param=lambda _name, _default: 0.10)
        self.assertEqual(module.configured_gripper_maximum(rospy), 100000)
        for value in (0.0, 0.101, float("nan")):
            rospy = types.SimpleNamespace(
                get_param=lambda _name, _default, value=value: value)
            with self.assertRaisesRegex(ValueError, "gripper maximum"):
                module.configured_gripper_maximum(rospy)

    def test_auto_enable_is_checked_only_after_ros_initialization(self):
        events = []
        rospy = types.SimpleNamespace(
            init_node=lambda *args, **kwargs: events.append("init"),
            get_param=lambda name, default: (
                events.append(("get", name, default)) or True),
        )
        with self.assertRaisesRegex(ValueError, "auto_enable=false"):
            module.initialize_ros(rospy)
        self.assertEqual(events, ["init", ("get", "~auto_enable", False)])

    def test_source_rejects_auto_enable_and_has_no_enable_close_command(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("safe gripper driver requires auto_enable=false", text)
        self.assertNotIn("GripperCtrl(0, 1000, 0x01", text)


if __name__ == "__main__":
    unittest.main()
