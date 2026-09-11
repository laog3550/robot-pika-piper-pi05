#!/usr/bin/env python3
"""Publish Piper feedback from a receive-only SocketCAN socket."""

import re
import socket
import struct

import rospy
from sensor_msgs.msg import JointState

from pi05_control.piper_feedback import FeedbackAssembler


CAN_FRAME = struct.Struct("=IB3x8s")
CAN_EFF_MASK = 0x1FFFFFFF
INTERFACE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}$")


def main():
    rospy.init_node("piper_readonly_feedback")
    side = rospy.get_param("~side", "")
    can_interface = rospy.get_param("~can_interface", "")
    if side not in ("left", "right"):
        raise rospy.ROSInitException("~side must be left or right")
    if not INTERFACE_RE.fullmatch(can_interface):
        raise rospy.ROSInitException("~can_interface is invalid")

    topic = rospy.get_param("~joint_state_topic", "joint_states_raw")
    publisher = rospy.Publisher(topic, JointState, queue_size=10)
    names = ["%s_joint%d" % (side, index) for index in range(1, 7)]
    names.append("%s_gripper_stroke" % side)
    assembler = FeedbackAssembler()

    can_socket = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    can_socket.settimeout(0.2)
    can_socket.bind((can_interface,))
    rospy.loginfo(
        "%s Piper receive-only feedback started on %s; no CAN transmit API is used",
        side,
        can_interface,
    )
    try:
        while not rospy.is_shutdown():
            try:
                frame = can_socket.recv(CAN_FRAME.size)
            except socket.timeout:
                continue
            if len(frame) != CAN_FRAME.size:
                continue
            can_id, dlc, payload = CAN_FRAME.unpack(frame)
            if dlc != 8:
                continue
            positions = assembler.update(can_id & CAN_EFF_MASK, payload)
            if positions is None:
                continue
            message = JointState()
            message.header.stamp = rospy.Time.now()
            message.name = names
            message.position = positions
            publisher.publish(message)
    finally:
        can_socket.close()


if __name__ == "__main__":
    main()
