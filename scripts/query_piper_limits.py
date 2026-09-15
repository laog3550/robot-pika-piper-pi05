#!/usr/bin/env python3
"""Query and validate Piper joint limits without enabling or commanding motion."""

import argparse
import re
import sys
import time


INTERFACE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}$")
JOINTS = range(1, 7)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Use pinned piper_sdk initialization queries to read six joint angle, "
            "speed and acceleration limits. This transmits query IDs 0x472 and "
            "0x4AF; it never enables the arm or sends control/configuration commands."
        )
    )
    parser.add_argument("--interface", required=True)
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser.parse_args(argv)


def extract_limits(angle_state, acceleration_state):
    """Return complete, structurally valid raw limit tuples for joints 1-6."""
    angles = angle_state.all_motor_angle_limit_max_spd.motor
    accelerations = acceleration_state.all_motor_max_acc_limit.motor
    result = []
    for joint in JOINTS:
        angle = angles[joint]
        acceleration = accelerations[joint]
        if angle.motor_num != joint or acceleration.joint_motor_num != joint:
            raise ValueError("incomplete limit response for J%d" % joint)
        if angle.max_angle_limit <= angle.min_angle_limit:
            raise ValueError("invalid angle limit ordering for J%d" % joint)
        if angle.max_joint_spd <= 0 or acceleration.max_joint_acc <= 0:
            raise ValueError("non-positive speed or acceleration limit for J%d" % joint)
        result.append((
            angle.min_angle_limit,
            angle.max_angle_limit,
            angle.max_joint_spd,
            acceleration.max_joint_acc,
        ))
    return result


def query(interface, timeout):
    if not INTERFACE_RE.fullmatch(interface):
        raise ValueError("invalid SocketCAN interface name")
    if not 0.1 <= timeout <= 5.0:
        raise ValueError("timeout must be between 0.1 and 5 seconds")

    from piper_sdk import C_PiperInterface

    piper = C_PiperInterface(can_name=interface)
    try:
        # PiperInit sends the documented limit and firmware queries only.
        piper.ConnectPort(piper_init=True, start_thread=True)
        deadline = time.monotonic() + timeout
        last_error = "limit response timed out"
        while time.monotonic() < deadline:
            try:
                return extract_limits(
                    piper.GetAllMotorAngleLimitMaxSpd(),
                    piper.GetAllMotorMaxAccLimit(),
                )
            except (AttributeError, IndexError, ValueError) as exc:
                last_error = str(exc)
            time.sleep(0.02)
        raise RuntimeError(last_error)
    finally:
        piper.DisconnectPort()


def main(argv=None):
    args = parse_args(argv)
    try:
        limits = query(args.interface, args.timeout)
    except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
        print("[PI05] ERROR: Piper limit query failed: %s" % exc, file=sys.stderr)
        return 1

    for joint, values in enumerate(limits, 1):
        minimum, maximum, speed, acceleration = values
        print(
            "[PI05] J%d limits: min=%.1fdeg max=%.1fdeg "
            "speed=%.3frad/s acceleration=%.3frad/s^2"
            % (joint, minimum * 0.1, maximum * 0.1,
               speed * 0.001, acceleration * 0.001)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
