#!/usr/bin/env python3
"""Validate passive Piper CAN feedback without transmitting CAN frames."""

import argparse
import collections
import socket
import stat
import struct
import sys
import time
from pathlib import Path


CAN_FRAME = struct.Struct("=IB3x8s")
CAN_EFF_MASK = 0x1FFFFFFF
EXPECTED_IDS = frozenset(
    set(range(0x251, 0x257))
    | set(range(0x261, 0x267))
    | set(range(0x2A1, 0x2A9))
)
CONTROL_IDS = frozenset(
    {0x121, 0x422, 0x470, 0x471, 0x472, 0x474, 0x475, 0x477, 0x479, 0x47A, 0x47D, 0x4AF}
    | set(range(0x150, 0x160))
)


def bounded_duration(value):
    parsed = float(value)
    if not 0.1 <= parsed <= 60.0:
        raise argparse.ArgumentTypeError("duration must be between 0.1 and 60 seconds")
    return parsed


def positive_integer(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Passively validate Piper CAN feedback IDs. The checker never sends "
            "CAN frames and never prints or saves payload bytes."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--interface", help="configured SocketCAN interface")
    source.add_argument("--input-file", type=Path, help="offline fixture containing one CAN ID per line")
    parser.add_argument("--label", choices=("left", "right", "test"), default="test")
    parser.add_argument("--duration", type=bounded_duration, default=3.0)
    parser.add_argument("--min-count-per-id", type=positive_integer, default=2)
    return parser.parse_args()


def read_socketcan(interface, duration):
    if not interface or len(interface) > 15:
        raise ValueError("invalid SocketCAN interface name")
    can_socket = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    counts = collections.Counter()
    try:
        can_socket.bind((interface,))
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            can_socket.settimeout(remaining)
            try:
                frame = can_socket.recv(CAN_FRAME.size)
            except socket.timeout:
                break
            if len(frame) != CAN_FRAME.size:
                continue
            can_id, _, _ = CAN_FRAME.unpack(frame)
            counts[can_id & CAN_EFF_MASK] += 1
    finally:
        can_socket.close()
    return counts


def read_fixture(path):
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("input fixture must be a regular file")
    counts = collections.Counter()
    for line_number, raw_line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            can_id = int(line, 16)
        except ValueError as exc:
            raise ValueError("invalid CAN ID on fixture line %d" % line_number) from exc
        if not 0 <= can_id <= CAN_EFF_MASK:
            raise ValueError("out-of-range CAN ID on fixture line %d" % line_number)
        counts[can_id] += 1
    return counts


def format_ids(values):
    return ",".join("0x%03X" % value for value in sorted(values)) or "none"


def main():
    args = parse_args()
    try:
        counts = (
            read_socketcan(args.interface, args.duration)
            if args.interface
            else read_fixture(args.input_file)
        )
    except (OSError, ValueError) as exc:
        print("[PI05] ERROR: Piper CAN stream could not be read: %s" % exc, file=sys.stderr)
        return 3

    missing = {can_id for can_id in EXPECTED_IDS if counts[can_id] < args.min_count_per_id}
    control = {can_id for can_id in CONTROL_IDS if counts[can_id]}
    expected_frames = sum(counts[can_id] for can_id in EXPECTED_IDS)
    unexpected_frames = sum(
        count for can_id, count in counts.items() if can_id not in EXPECTED_IDS
    )
    print(
        "[PI05] %s Piper CAN stream: frames=%d expected_frames=%d "
        "expected_ids=%d/20 missing=%s control_ids=%s unexpected_frames=%d"
        % (
            args.label,
            sum(counts.values()),
            expected_frames,
            len(EXPECTED_IDS - missing),
            format_ids(missing),
            format_ids(control),
            unexpected_frames,
        )
    )

    if not counts:
        print("[PI05] ERROR: Piper CAN stream produced no frames", file=sys.stderr)
        return 1
    if control:
        print("[PI05] ERROR: control/configuration CAN IDs were observed", file=sys.stderr)
        return 1
    if missing:
        print("[PI05] ERROR: required Piper feedback CAN IDs are missing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
