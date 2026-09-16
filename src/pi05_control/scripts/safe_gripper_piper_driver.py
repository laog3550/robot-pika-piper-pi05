#!/usr/bin/env python3
"""Run the pinned Piper driver with hold-position gripper enable semantics."""
import importlib.util
from pathlib import Path
import time


def current_targets(node):
    joints = node.piper.GetArmJointMsgs().joint_state
    gripper = node.piper.GetArmGripperMsgs().gripper_state
    return ([joints.joint_1, joints.joint_2, joints.joint_3,
             joints.joint_4, joints.joint_5, joints.joint_6],
            max(0, min(abs(gripper.grippers_angle), 80000)))


def command_current_position(node):
    joints, gripper = current_targets(node)
    node.piper.MotionCtrl_2(0x01, 0x01, 10, 0xad)
    node.piper.JointCtrl(*joints)
    if node.gripper_exist:
        node.piper.GripperCtrl(gripper, 1000, 0x01, 0)


def install_safe_callbacks(vendor):
    def handle_enable_service(node, request):
        started = time.monotonic()
        while True:
            feedback = node.piper.GetArmLowSpdInfoMsgs()
            states = [getattr(feedback, "motor_%d" % number)
                      .foc_status.driver_enable_status for number in range(1, 7)]
            if request.enable_request:
                command_current_position(node)
                node.piper.EnableArm(7)
                command_current_position(node)
                matches = all(states)
            else:
                node.piper.DisableArm(7)
                if node.gripper_exist:
                    node.piper.GripperCtrl(0, 1000, 0x02, 0)
                matches = not any(states)
            node._C_PiperRosNode__enable_flag = bool(request.enable_request and matches)
            if matches:
                return vendor.EnableResponse(True)
            if time.monotonic() - started > 5.0:
                return vendor.EnableResponse(False)
            time.sleep(0.5)

    def enable_callback(node, enable_flag):
        if enable_flag.data:
            command_current_position(node)
            node.piper.EnableArm(7)
            command_current_position(node)
            node._C_PiperRosNode__enable_flag = True
        else:
            node.piper.DisableArm(7)
            if node.gripper_exist:
                node.piper.GripperCtrl(0, 1000, 0x00, 0)
            node._C_PiperRosNode__enable_flag = False

    vendor.C_PiperRosNode.handle_enable_service = handle_enable_service
    vendor.C_PiperRosNode.enable_callback = enable_callback


def load_vendor_driver():
    import rospkg
    source = Path(rospkg.RosPack().get_path("piper")) / "scripts/piper_ctrl_single_node.py"
    spec = importlib.util.spec_from_file_location("pi05_pinned_piper_driver", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    import rospy
    if rospy.get_param("~auto_enable", False):
        raise ValueError("safe gripper driver requires auto_enable=false")
    vendor = load_vendor_driver()
    install_safe_callbacks(vendor)
    node = vendor.C_PiperRosNode()
    node.Pubilsh()


if __name__ == "__main__":
    main()
