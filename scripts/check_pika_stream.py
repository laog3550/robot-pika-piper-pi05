#!/usr/bin/env python3
"""Validate a Pika JSON stream without writing to the serial device."""

import argparse
import json
import os
import re
import select
import stat
import sys
import termios
import time
import tty
from pathlib import Path


FRAME_START = re.compile(r'\{\s*"Command"\s*:')
EXPECTED_KEYS = frozenset(("Command", "AS5047"))


def positive_duration(value):
    parsed = float(value)
    if not 0.1 <= parsed <= 60.0:
        raise argparse.ArgumentTypeError("duration must be between 0.1 and 60 seconds")
    return parsed


def non_negative_integer(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def ratio(value):
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("ratio must be between 0 and 1")
    return parsed


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Read and validate Pika JSON frames without transmitting serial data. "
            "Raw bytes and sensor values are never printed or saved."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--device", help="Pika character device below /dev")
    source.add_argument("--input-file", type=Path, help="offline stream fixture")
    parser.add_argument("--label", choices=("left", "right", "test"), default="test")
    parser.add_argument("--duration", type=positive_duration, default=5.0)
    parser.add_argument("--min-complete-frames", type=non_negative_integer, default=10)
    parser.add_argument("--min-complete-ratio", type=ratio, default=0.95)
    return parser.parse_args()


def configure_read_only_serial(fd):
    tty.setraw(fd, termios.TCSANOW)
    configured = termios.tcgetattr(fd)
    configured[4] = termios.B460800
    configured[5] = termios.B460800
    configured[2] &= ~termios.CSTOPB
    configured[2] &= ~termios.PARENB
    configured[2] = (configured[2] & ~termios.CSIZE) | termios.CS8
    if hasattr(termios, "CRTSCTS"):
        configured[2] &= ~termios.CRTSCTS
    termios.tcsetattr(fd, termios.TCSANOW, configured)


def read_device(device, duration):
    resolved = os.path.realpath(device)
    if not resolved.startswith("/dev/"):
        raise ValueError("device must resolve below /dev")
    if not stat.S_ISCHR(os.stat(resolved).st_mode):
        raise ValueError("device must resolve to a character device")

    fd = os.open(device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    original = None
    chunks = []
    try:
        original = termios.tcgetattr(fd)
        configure_read_only_serial(fd)
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if chunk:
                chunks.append(chunk)
    finally:
        if original is not None:
            termios.tcsetattr(fd, termios.TCSANOW, original)
        os.close(fd)
    return b"".join(chunks)


def inspect_stream(data):
    text = data.decode("ascii", errors="replace")
    starts = [match.start() for match in FRAME_START.finditer(text)]
    decoder = json.JSONDecoder()
    parsed = 0
    complete = 0
    for start in starts:
        try:
            value, _ = decoder.raw_decode(text, start)
        except (json.JSONDecodeError, ValueError):
            continue
        parsed += 1
        if isinstance(value, dict) and EXPECTED_KEYS.issubset(value):
            complete += 1
    return len(starts), parsed, complete


def main():
    args = parse_args()
    try:
        if args.device:
            data = read_device(args.device, args.duration)
        else:
            data = args.input_file.read_bytes()
    except (OSError, ValueError) as exc:
        print("[PI05] ERROR: Pika stream could not be read: %s" % exc, file=sys.stderr)
        return 3

    candidates, parsed, complete = inspect_stream(data)
    complete_ratio = complete / candidates if candidates else 0.0
    candidate_rate = candidates / args.duration
    print(
        "[PI05] %s Pika stream: bytes=%d candidates=%d parsed=%d complete=%d "
        "complete_ratio=%.3f candidate_rate_hz=%.1f"
        % (
            args.label,
            len(data),
            candidates,
            parsed,
            complete,
            complete_ratio,
            candidate_rate,
        )
    )

    if not data:
        print("[PI05] ERROR: Pika stream produced no bytes", file=sys.stderr)
        return 1
    if candidates == 0:
        print("[PI05] ERROR: no Pika frame starts were found", file=sys.stderr)
        return 1
    if complete < args.min_complete_frames:
        print("[PI05] ERROR: too few complete Pika frames", file=sys.stderr)
        return 1
    if complete_ratio < args.min_complete_ratio:
        print("[PI05] ERROR: Pika complete-frame ratio is below the required threshold", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
