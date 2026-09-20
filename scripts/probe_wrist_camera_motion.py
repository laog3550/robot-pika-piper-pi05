#!/usr/bin/env python3
"""Log per-wrist-camera motion energy with wall-clock timestamps.

Used to prove which physical arm a wrist camera is mounted on: the operator
moves exactly one arm by hand, and only that arm's wrist camera shows motion.

Device resolution is by camera serial number (never by /dev/videoN order).
The colour stream of each Orbbec Gemini 305 is the YUYV/MJPG node on USB
interface 04.

Output: JSONL, one record per sample per camera:
    {"t": <epoch seconds>, "cam": "<serial>", "energy": <mean abs diff>}

This script never touches CAN and never commands an arm.
"""

import argparse
import json
import subprocess
import sys
import time

import cv2
import numpy as np


def udev_props(node):
    try:
        out = subprocess.run(
            ["udevadm", "info", "--query=property", "--name", node],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout
    except Exception:
        return {}
    props = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v
    return props


def find_colour_node(serial, interface="04"):
    """Return the /dev/videoN colour node for a Gemini 305 serial."""
    import glob
    for node in sorted(glob.glob("/dev/video*"), key=lambda p: int(p.replace("/dev/video", ""))):
        props = udev_props(node)
        if props.get("ID_SERIAL_SHORT") != serial:
            continue
        if props.get("ID_USB_INTERFACE_NUM") != interface:
            continue
        caps = subprocess.run(
            ["v4l2-ctl", "-d", node, "--list-formats"],
            capture_output=True, text=True, check=False,
        ).stdout
        if "YUYV" in caps or "MJPG" in caps:
            return node
    return None


def open_camera(node, fourcc="YUYV", width=640, height=480, fps=30):
    cap = cv2.VideoCapture(node, cv2.CAP_V4L2)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    # Generous warm-up: while the probe also reads three CAN buses the machine
    # is heavily loaded, and a UVC stream can take several seconds to deliver
    # its first decodable frame. A short retry budget silently loses the camera.
    for _ in range(80):
        ok, frame = cap.read()
        if ok and frame is not None and frame.size:
            return cap
        time.sleep(0.15)
    cap.release()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", action="append", required=True,
                    help="camera serial to watch (repeatable)")
    ap.add_argument("--label", action="append", default=None,
                    help="optional label matching --serial order")
    ap.add_argument("--duration", type=float, default=600.0,
                    help="seconds to log (default 600)")
    ap.add_argument("--interval", type=float, default=0.2,
                    help="seconds between samples per camera")
    ap.add_argument("--output", required=True)
    ap.add_argument("--ready-file", default=None,
                    help="touch this file once every requested camera is streaming, "
                         "so the caller can start CAN capture only when video is live")
    args = ap.parse_args()

    labels = args.label or args.serial

    cams = {}
    missing = []
    for serial, label in zip(args.serial, labels):
        node = find_colour_node(serial)
        if node is None:
            print(f"[warn] no colour node found for serial {serial}", file=sys.stderr)
            missing.append(serial)
            continue
        cap = open_camera(node)
        if cap is None:
            print(f"[warn] cannot open {node} for serial {serial}", file=sys.stderr)
            missing.append(serial)
            continue
        cams[label] = {"cap": cap, "node": node, "prev": None}
        print(f"[info] watching {label} serial={serial} node={node}", file=sys.stderr)

    if args.ready_file:
        try:
            with open(args.ready_file, "w") as rh:
                rh.write(f"opened={len(cams)} missing={len(missing)}\n")
        except OSError as exc:
            print(f"[warn] cannot write ready file: {exc}", file=sys.stderr)

    if not cams:
        print("[error] no camera could be opened", file=sys.stderr)
        return 1

    deadline = time.time() + args.duration
    with open(args.output, "a", buffering=1) as fh:
        while time.time() < deadline:
            for label, st in cams.items():
                ok, frame = st["cap"].read()
                if not ok or frame is None or not frame.size:
                    continue
                grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.int16)
                energy = None
                if st["prev"] is not None:
                    energy = float(np.abs(grey - st["prev"]).mean())
                st["prev"] = grey
                if energy is not None:
                    fh.write(json.dumps({
                        "t": round(time.time(), 4),
                        "cam": label,
                        "energy": round(energy, 3),
                    }) + "\n")
            time.sleep(args.interval)

    for st in cams.values():
        st["cap"].release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
