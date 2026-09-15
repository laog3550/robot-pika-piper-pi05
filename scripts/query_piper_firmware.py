#!/usr/bin/env python3
"""Query one Piper firmware version without enabling or commanding motion."""

import argparse
import re
import sys
import time


INTERFACE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}$")
# Piper firmware responses are assembled byte-by-byte by piper_sdk.  The SDK
# exposes the in-progress prefix too, so accepting a generic ``S-V...`` value
# can return before all eight protocol bytes have arrived (for example S-V1).
FIRMWARE_RE = re.compile(r"^S-V[0-9]\.[0-9]-[0-9]$")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Use the pinned piper_sdk initialization queries to read one firmware "
            "version. This opens SocketCAN and transmits query IDs 0x472 and 0x4AF; "
            "it never enables the arm or sends motion/gripper commands."
        )
    )
    parser.add_argument("--interface", required=True)
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser.parse_args(argv)


def query(interface, timeout):
    if not INTERFACE_RE.fullmatch(interface):
        raise ValueError("invalid SocketCAN interface name")
    if not 0.1 <= timeout <= 5.0:
        raise ValueError("timeout must be between 0.1 and 5 seconds")

    from piper_sdk import C_PiperInterface

    piper = C_PiperInterface(can_name=interface)
    try:
        # PiperInit sends only the documented limit and firmware queries.
        piper.ConnectPort(piper_init=True, start_thread=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            version = piper.GetPiperFirmwareVersion()
            if isinstance(version, str) and FIRMWARE_RE.fullmatch(version):
                return version
            time.sleep(0.02)
        raise RuntimeError("firmware response timed out")
    finally:
        piper.DisconnectPort()


def main(argv=None):
    args = parse_args(argv)
    try:
        version = query(args.interface, args.timeout)
    except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
        print("[PI05] ERROR: Piper firmware query failed: %s" % exc, file=sys.stderr)
        return 1
    print("[PI05] Piper firmware: %s" % version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
