#!/usr/bin/env python3
"""Passively summarize Piper high-speed motor feedback."""

import argparse
import socket
import stat
import struct
import sys
import time
from pathlib import Path

from pi05_control.piper_feedback import MotorTelemetryWindow


CAN_FRAME = struct.Struct("=IB3x8s")
CAN_EFF_MASK = 0x1FFFFFFF
MIN_SAMPLES_PER_MOTOR = 10


def bounded_duration(value):
    parsed = float(value)
    if not 0.1 <= parsed <= 60.0:
        raise argparse.ArgumentTypeError("duration must be between 0.1 and 60 seconds")
    return parsed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Receive Piper 0x251..0x256 feedback only and report sample counts, "
            "peak absolute speed and peak absolute current. No CAN frames are sent."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--interface")
    source.add_argument("--input-file", type=Path)
    parser.add_argument("--label", choices=("left", "right", "test"), default="test")
    parser.add_argument("--duration", type=bounded_duration, default=5.0)
    return parser.parse_args(argv)


def socket_samples(interface, duration):
    if not interface or len(interface) > 15:
        raise ValueError("invalid SocketCAN interface name")
    source = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    source.bind((interface,))
    source.settimeout(0.5)
    deadline = time.monotonic() + duration
    try:
        while time.monotonic() < deadline:
            try:
                frame = source.recv(CAN_FRAME.size)
            except socket.timeout:
                continue
            if len(frame) != CAN_FRAME.size:
                continue
            can_id, dlc, payload = CAN_FRAME.unpack(frame)
            if dlc == 8:
                yield can_id & CAN_EFF_MASK, payload
    finally:
        source.close()


def fixture_samples(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("input fixture must be a regular file")
    for line_number, raw in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ValueError("fixture line %d must contain CAN_ID DATA_HEX" % line_number)
        try:
            can_id = int(fields[0], 16)
            payload = bytes.fromhex(fields[1])
        except ValueError as exc:
            raise ValueError("invalid fixture line %d" % line_number) from exc
        if len(payload) != 8:
            raise ValueError("fixture payload on line %d must be 8 bytes" % line_number)
        yield can_id, payload


def main(argv=None):
    args = parse_args(argv)
    telemetry = MotorTelemetryWindow()
    try:
        samples = (
            socket_samples(args.interface, args.duration)
            if args.interface else fixture_samples(args.input_file)
        )
        for can_id, payload in samples:
            telemetry.update(can_id, payload)
    except (OSError, ValueError) as exc:
        print("[PI05] ERROR: motor telemetry could not be read: %s" % exc, file=sys.stderr)
        return 3

    failed = False
    summaries = []
    for joint, count, peak_speed, peak_current in telemetry.summary():
        if count < MIN_SAMPLES_PER_MOTOR:
            failed = True
            summaries.append("J%d=insufficient(%d)" % (joint, count))
        else:
            summaries.append(
                "J%d[n=%d speed=%.3frad/s current=%.3fA]"
                % (joint, count, peak_speed, peak_current)
            )
    print("[PI05] %s passive motor telemetry: %s" % (args.label, " ".join(summaries)))
    if failed:
        print("[PI05] ERROR: high-speed motor feedback is incomplete", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
