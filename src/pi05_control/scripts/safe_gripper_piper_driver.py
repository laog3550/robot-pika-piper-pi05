#!/usr/bin/env python3
"""Run the pinned Piper driver with hold-position gripper enable semantics."""
import importlib.util
import math
from pathlib import Path
import time


def current_targets(node, gripper_maximum_raw):
    joints = node.piper.GetArmJointMsgs().joint_state
    gripper = node.piper.GetArmGripperMsgs().gripper_state
    return ([joints.joint_1, joints.joint_2, joints.joint_3,
             joints.joint_4, joints.joint_5, joints.joint_6],
            max(0, min(abs(gripper.grippers_angle), gripper_maximum_raw)))


def command_current_position(node, gripper_maximum_raw):
    joints, gripper = current_targets(node, gripper_maximum_raw)
    # JointCtrl is a position target. Keep the controller in the same
    # position-speed mode used by the pinned vendor joint callback; 0xAD would
    # select MIT mode and can leave J1-J6 ignoring these position commands.
    node.piper.MotionCtrl_2(0x01, 0x01, 10, 0x00)
    node.piper.JointCtrl(*joints)
    if node.gripper_exist:
        node.piper.GripperCtrl(gripper, 1000, 0x01, 0)


def install_safe_callbacks(vendor, gripper_maximum_raw=100000):
    import rospy

    def motor_states(node):
        feedback = node.piper.GetArmLowSpdInfoMsgs()
        return [bool(getattr(feedback, "motor_%d" % number)
                     .foc_status.driver_enable_status) for number in range(1, 7)]

    def handle_enable_service(node, request):
        started = time.monotonic()
        rospy.loginfo("enable request: enable_request=%s", request.enable_request)
        while True:
            states = motor_states(node)
            if request.enable_request:
                command_current_position(node, gripper_maximum_raw)
                node.piper.EnableArm(7)
                command_current_position(node, gripper_maximum_raw)
                matches = all(states)
            else:
                node.piper.DisableArm(7)
                if node.gripper_exist:
                    node.piper.GripperCtrl(0, 1000, 0x02, 0)
                matches = not any(states)
            node._C_PiperRosNode__enable_flag = bool(request.enable_request and matches)
            if matches:
                rospy.loginfo("enable result: %s confirmed in %.1fs (motors=%s)",
                              "enabled" if request.enable_request else "disabled",
                              time.monotonic() - started,
                              "".join("1" if s else "0" for s in states))
                return vendor.EnableResponse(True)
            if time.monotonic() - started > 5.0:
                # 这正是“指令在发但机械臂不动”时最需要看到的记录。
                rospy.logwarn(
                    "enable result: %s NOT confirmed after %.1fs; motors=%s "
                    "(1=enabled). Check hardware e-stop, controller mode and power.",
                    "enable" if request.enable_request else "disable",
                    time.monotonic() - started,
                    "".join("1" if s else "0" for s in states))
                return vendor.EnableResponse(False)
            time.sleep(0.5)

    def enable_callback(node, enable_flag):
        if enable_flag.data:
            command_current_position(node, gripper_maximum_raw)
            node.piper.EnableArm(7)
            command_current_position(node, gripper_maximum_raw)
            node._C_PiperRosNode__enable_flag = True
        else:
            node.piper.DisableArm(7)
            if node.gripper_exist:
                node.piper.GripperCtrl(0, 1000, 0x00, 0)
            node._C_PiperRosNode__enable_flag = False
        rospy.loginfo("enable_flag topic: requested %s; motors=%s",
                      bool(enable_flag.data),
                      "".join("1" if s else "0" for s in motor_states(node)))

    def joint_callback(node, joint_data):
        """Forward J1-J6 and allow the configured seventh-axis travel."""
        if node.block_ctrl_flag:
            return
        if len(joint_data.position) < 6:
            rospy.logwarn("joint target ignored: expected at least six positions")
            return
        positions = joint_data.position[:6]
        if not all(math.isfinite(value) for value in positions):
            rospy.logwarn("joint target ignored: J1-J6 must be finite")
            return

        factor = 1000.0 * 180.0 / math.pi
        joints = [round(value * factor) for value in positions]
        gripper = None
        if len(joint_data.position) >= 7:
            value = joint_data.position[6]
            if not math.isfinite(value):
                rospy.logwarn("joint target ignored: gripper target must be finite")
                return
            gripper = round(value * 1000000.0 * node.gripper_val_mutiple)
            gripper = max(0, min(gripper, gripper_maximum_raw))
            if abs(gripper) < 200:
                gripper = 0

        if not node.GetEnableFlag():
            return
        speed = 50
        if (len(joint_data.velocity) >= 7 and
                any(value != 0 for value in joint_data.velocity) and
                math.isfinite(joint_data.velocity[6])):
            speed = max(0, min(round(joint_data.velocity[6]), 100))
        node.piper.MotionCtrl_2(0x01, 0x01, speed, 0x00)
        node.piper.JointCtrl(*joints)
        if node.gripper_exist and gripper is not None:
            effort = 1.0
            if len(joint_data.effort) >= 7 and math.isfinite(joint_data.effort[6]):
                effort = max(0.5, min(joint_data.effort[6], 3.0))
            node.piper.GripperCtrl(gripper, round(effort * 1000), 0x01, 0)

    # 厂商 __init__ 会立即注册服务并启动 joint/enable 订阅线程。必须在构造实例
    # 之前替换类方法，否则线程可能捕获厂商的原始回调（使能时闭合夹爪，且第七轴
    # 被硬限制为 80000）。
    if getattr(vendor.C_PiperRosNode, "_pi05_safe_callbacks", False):
        return
    vendor.C_PiperRosNode.handle_enable_service = handle_enable_service
    vendor.C_PiperRosNode.enable_callback = enable_callback
    vendor.C_PiperRosNode.joint_callback = joint_callback
    vendor.C_PiperRosNode._pi05_safe_callbacks = True


def load_vendor_driver():
    import rospkg
    source = Path(rospkg.RosPack().get_path("piper")) / "scripts/piper_ctrl_single_node.py"
    spec = importlib.util.spec_from_file_location("pi05_pinned_piper_driver", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def initialize_ros(rospy):
    """Initialize the final node name before resolving private parameters."""
    rospy.init_node("piper_ctrl_single_node", anonymous=True)
    if rospy.get_param("~auto_enable", False):
        raise ValueError("safe gripper driver requires auto_enable=false")


def configured_gripper_maximum(rospy):
    maximum = float(rospy.get_param("~gripper_maximum", 0.10))
    if not math.isfinite(maximum) or maximum <= 0 or maximum > 0.10:
        raise ValueError("gripper maximum must be in (0, 0.10]")
    return round(maximum * 1000000.0)


def main():
    import rospy
    # 先初始化后才能正确解析 roslaunch 中的私有参数。厂商构造器
    # 会以相同参数再调用一次 init_node，rospy 对这种重复初始化是幂等的。
    initialize_ros(rospy)
    gripper_maximum_raw = configured_gripper_maximum(rospy)
    vendor = load_vendor_driver()
    install_safe_callbacks(vendor, gripper_maximum_raw)
    node = vendor.C_PiperRosNode()
    node.Pubilsh()


if __name__ == "__main__":
    main()
