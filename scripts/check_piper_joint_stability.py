#!/usr/bin/env python3
"""Passively check Piper joint feedback ranges without exposing positions."""

import argparse
import socket
import stat
import struct
import sys
import time
from pathlib import Path


CAN_FRAME = struct.Struct("=IB3x8s")
CAN_EFF_MASK = 0x1FFFFFFF
JOINT_IDS = {0x2A5: (0, 1), 0x2A6: (2, 3), 0x2A7: (4, 5)}
MILLI_DEG_TO_RAD = 3.141592653589793 / 180000.0
DRIFT_LIMIT_RAD = 0.002
MIN_SAMPLES_PER_JOINT = 10


def bounded_duration(value):
    parsed = float(value)
    if not 0.1 <= parsed <= 60.0:
        raise argparse.ArgumentTypeError("duration must be between 0.1 and 60 seconds")
    return parsed


def joint_number(value):
    parsed = int(value)
    if not 1 <= parsed <= 6:
        raise argparse.ArgumentTypeError("joint must be in [1, 6]")
    return parsed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Receive Piper joint feedback only and report per-joint ranges. "
            "Absolute positions and CAN payloads are never printed or saved."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--interface")
    source.add_argument("--input-file", type=Path)
    parser.add_argument("--label", choices=("left", "right", "test"), default="test")
    parser.add_argument("--duration", type=bounded_duration, default=5.0)
    parser.add_argument("--exclude-joint", type=joint_number)
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


def collect(samples):
    values = [[] for _ in range(6)]
    for can_id, payload in samples:
        indices = JOINT_IDS.get(can_id)
        if indices is None:
            continue
        first, second = struct.unpack(">ii", payload)
        values[indices[0]].append(first * MILLI_DEG_TO_RAD)
        values[indices[1]].append(second * MILLI_DEG_TO_RAD)
    return values


def main(argv=None):
    args = parse_args(argv)
    try:
        samples = (
            socket_samples(args.interface, args.duration)
            if args.interface else fixture_samples(args.input_file)
        )
        values = collect(samples)
    except (OSError, ValueError) as exc:
        print("[PI05] ERROR: joint feedback could not be read: %s" % exc, file=sys.stderr)
        return 3

    failed = False
    summaries = []
    for index, sequence in enumerate(values, 1):
        if len(sequence) < MIN_SAMPLES_PER_JOINT:
            failed = True
            summaries.append("J%d=insufficient(%d)" % (index, len(sequence)))
            continue
        joint_range = max(sequence) - min(sequence)
        suffix = "(excluded)" if args.exclude_joint == index else ""
        summaries.append("J%d=%.6f%s" % (index, joint_range, suffix))
        if args.exclude_joint != index and joint_range > DRIFT_LIMIT_RAD:
            failed = True
    print(
        "[PI05] %s passive joint ranges rad: %s; limit=%.3f"
        % (args.label, " ".join(summaries), DRIFT_LIMIT_RAD)
    )
    if failed:
        print("[PI05] ERROR: joint feedback stability check failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
