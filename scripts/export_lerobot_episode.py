#!/usr/bin/env python3
"""Append one completed PI05 raw episode to a local LeRobotDataset v3 dataset."""

import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

import cv2
import numpy as np


CAMERA_KEYS = ("left_wrist", "right_wrist", "top")
FEATURE_NAMES = (
    ["left_joint%d" % index for index in range(1, 7)] + ["left_gripper"] +
    ["right_joint%d" % index for index in range(1, 7)] + ["right_gripper"])


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--repo-id", required=True)
    return parser.parse_args(argv)


def features(height, width):
    result = {
        "observation.state": {
            "dtype": "float32", "shape": (14,), "names": FEATURE_NAMES,
        },
        "action": {
            "dtype": "float32", "shape": (14,), "names": FEATURE_NAMES,
        },
    }
    for key in CAMERA_KEYS:
        result["observation.images." + key] = {
            "dtype": "video",
            "shape": (height, width, 3),
            "names": ["height", "width", "channels"],
        }
    return result


def load_episode(path):
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("outcome") != "success" or not manifest.get("home_confirmed"):
        raise ValueError("only successful home-confirmed episodes may enter the training dataset")
    rows = [json.loads(line) for line in
            (path / "frames.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError("episode has no frames")
    if not any(row["phase"] == "return_home" for row in rows):
        raise ValueError("episode has no recorded return-home segment")
    expected = list(range(len(rows)))
    if [row["frame_index"] for row in rows] != expected:
        raise ValueError("frame indices are not contiguous")
    captures = {key: cv2.VideoCapture(str(path / (key + ".avi"))) for key in CAMERA_KEYS}
    if not all(capture.isOpened() for capture in captures.values()):
        raise RuntimeError("could not open all raw episode videos")
    return manifest, rows, captures


def verify_lerobot():
    import lerobot
    from lerobot.datasets.lerobot_dataset import CODEBASE_VERSION
    version = getattr(lerobot, "__version__", "unknown")
    if version != "0.4.2":
        raise RuntimeError("LeRobot 0.4.2 required, found %s" % version)
    if CODEBASE_VERSION != "v3.0":
        raise RuntimeError("LeRobot dataset schema v3.0 required, found %s" % CODEBASE_VERSION)


def append_episode(args):
    verify_lerobot()
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    marker = args.episode / "lerobot-exported.json"
    if marker.exists():
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if (previous.get("repo_id") == args.repo_id and
                Path(previous.get("dataset_root", "")) == args.dataset_root):
            print("Episode already exported to %s" % args.dataset_root)
            return
        raise ValueError("episode has an export marker for a different dataset")

    manifest, rows, captures = load_episode(args.episode)
    dataset = None
    creating = not (args.dataset_root / "meta" / "info.json").exists()
    working_root = args.dataset_root
    if creating:
        working_root = args.dataset_root.with_name(
            args.dataset_root.name + ".creating-" + uuid.uuid4().hex[:8])
    try:
        if not creating:
            dataset = LeRobotDataset(args.repo_id, root=args.dataset_root)
            if dataset.fps != manifest["fps"]:
                raise ValueError("dataset FPS differs from episode FPS")
            expected_user = features(manifest["height"], manifest["width"])
            for key, expected in expected_user.items():
                actual = dataset.features.get(key)
                if actual is None:
                    raise ValueError("existing dataset is missing feature: %s" % key)
                if (actual.get("dtype") != expected["dtype"] or
                        tuple(actual.get("shape", ())) != tuple(expected["shape"]) or
                        list(actual.get("names", [])) != list(expected["names"])):
                    raise ValueError("existing dataset feature mismatch: %s" % key)
        else:
            args.dataset_root.parent.mkdir(parents=True, exist_ok=True)
            dataset = LeRobotDataset.create(
                repo_id=args.repo_id,
                fps=manifest["fps"],
                features=features(manifest["height"], manifest["width"]),
                robot_type="pi05_dual_piper",
                root=working_root,
                use_videos=True,
                image_writer_threads=6,
            )
        for row in rows:
            frame = {
                "task": manifest["task"],
                "observation.state": np.asarray(row["state"], dtype=np.float32),
                "action": np.asarray(row["action"], dtype=np.float32),
            }
            if frame["observation.state"].shape != (14,) or frame["action"].shape != (14,):
                raise ValueError("state/action must both contain 14 values")
            for key, capture in captures.items():
                ok, image = capture.read()
                if not ok:
                    raise ValueError("%s video ended before frame %d" % (key, row["frame_index"]))
                frame["observation.images." + key] = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            dataset.add_frame(frame)
        for key, capture in captures.items():
            ok, _ = capture.read()
            if ok:
                raise ValueError("%s video contains more frames than frames.jsonl" % key)
        dataset.save_episode()
        dataset.finalize()
        if creating:
            if args.dataset_root.exists():
                raise RuntimeError("dataset root appeared while creating it")
            working_root.replace(args.dataset_root)
    finally:
        for capture in captures.values():
            capture.release()
        if dataset is not None:
            try:
                dataset.finalize()
            except Exception:
                pass
        if creating and working_root.exists():
            shutil.rmtree(str(working_root))
    marker.write_text(json.dumps({
        "repo_id": args.repo_id,
        "dataset_root": str(args.dataset_root),
        "frames": len(rows),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Exported %s (%d frames) to %s" %
          (manifest["episode_id"], len(rows), args.dataset_root))


def main(argv=None):
    args = parse_args(argv)
    try:
        append_episode(args)
    except Exception as error:
        print("LeRobot export failed: %s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
