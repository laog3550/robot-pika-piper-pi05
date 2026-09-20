"""Crash-resistant raw episode storage and background LeRobot export."""

from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import uuid

import cv2


CAMERA_KEYS = ("left_wrist", "right_wrist", "top")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class EpisodeWriter:
    """Write one synchronized spool plus a ROS bag before it is classified."""

    def __init__(self, dataset_root, task, fps, width, height, rosbag_module,
                 compressed_image_type):
        self.dataset_root = Path(dataset_root)
        self.task = task
        self.fps = int(fps)
        self.width = int(width)
        self.height = int(height)
        self.rosbag_module = rosbag_module
        self.compressed_image_type = compressed_image_type
        self._bag_lock = threading.Lock()
        self._closed = False
        token = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.episode_id = "episode-" + token
        self.incomplete_root = self.dataset_root / "raw" / ".incomplete"
        self.path = self.incomplete_root / self.episode_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.frames_file = (self.path / "frames.jsonl").open("w", encoding="utf-8")
        self.bag = rosbag_module.Bag(str(self.path / "raw.bag"), "w")
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.videos = {
            key: cv2.VideoWriter(str(self.path / (key + ".avi")), fourcc,
                                 self.fps, (self.width, self.height))
            for key in CAMERA_KEYS
        }
        if not all(writer.isOpened() for writer in self.videos.values()):
            self.abort()
            raise RuntimeError("could not open all episode video writers")
        self.frame_count = 0
        self.started_at = utc_now()
        self._write_manifest({
            "episode_id": self.episode_id,
            "task": task,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "started_at": self.started_at,
            "status": "recording",
        })

    def _write_manifest(self, data):
        target = self.path / "manifest.json"
        temporary = self.path / "manifest.json.tmp"
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(target)

    def write_ros_message(self, topic, message, stamp):
        if self._closed:
            return
        with self._bag_lock:
            self.bag.write(topic, message, t=stamp)

    def add_sample(self, stamp, elapsed, phase, images, state, action, ages):
        if self._closed:
            raise RuntimeError("episode writer is closed")
        for key in CAMERA_KEYS:
            frame = images[key]
            if frame.shape[:2] != (self.height, self.width):
                raise ValueError("%s frame has unexpected shape %r" % (key, frame.shape))
            self.videos[key].write(frame)
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                raise RuntimeError("JPEG encoding failed for %s" % key)
            message = self.compressed_image_type()
            message.header.stamp = stamp
            message.format = "jpeg"
            message.data = encoded.tobytes()
            self.write_ros_message(
                "/pi05/data_collection/%s/image/compressed" % key, message, stamp)
        record = {
            "frame_index": self.frame_count,
            "timestamp": float(elapsed),
            "phase": phase,
            "state": list(state),
            "action": list(action),
            "source_age_s": {key: float(value) for key, value in ages.items()},
        }
        self.frames_file.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.frames_file.flush()
        self.frame_count += 1

    def close(self, outcome, reason="", home_confirmed=False):
        if self._closed:
            raise RuntimeError("episode writer was already closed")
        self._close_handles()
        manifest = {
            "episode_id": self.episode_id,
            "task": self.task,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "started_at": self.started_at,
            "finished_at": utc_now(),
            "frames": self.frame_count,
            "outcome": outcome,
            "reason": reason,
            "home_confirmed": bool(home_confirmed),
            "status": "complete",
        }
        self._write_manifest(manifest)
        if outcome == "discard":
            shutil.rmtree(str(self.path))
            return None
        destination = self.dataset_root / "raw" / outcome / self.episode_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.path.replace(destination)
        self.path = destination
        return destination

    def _close_handles(self):
        if self._closed:
            return
        self._closed = True
        self.frames_file.close()
        for writer in self.videos.values():
            writer.release()
        with self._bag_lock:
            self.bag.close()

    def abort(self):
        try:
            self._close_handles()
        finally:
            if self.path.exists():
                failed = self.dataset_root / "raw" / "failed" / self.episode_id
                failed.parent.mkdir(parents=True, exist_ok=True)
                if not failed.exists():
                    self.path.replace(failed)


class ExportWorker:
    """Serialize dataset appends in the dedicated Python 3.10 environment."""

    def __init__(self, python, exporter, dataset_root, repo_id):
        self.python = str(python)
        self.exporter = str(exporter)
        self.dataset_root = str(dataset_root)
        self.repo_id = repo_id
        self.items = queue.Queue()
        self.last_error = ""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def enqueue(self, episode_path):
        self.items.put(str(episode_path))

    def pending(self):
        return self.items.unfinished_tasks

    def close(self):
        self.items.put(None)
        self.thread.join()

    def _run(self):
        while True:
            item = self.items.get()
            try:
                if item is None:
                    return
                command = [
                    self.python, self.exporter,
                    "--episode", item,
                    "--dataset-root", self.dataset_root,
                    "--repo-id", self.repo_id,
                ]
                outputs = []
                result = None
                for attempt in range(2):
                    result = subprocess.run(command, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True)
                    outputs.append("attempt %d:\n%s" % (attempt + 1, result.stdout))
                    if result.returncode == 0:
                        break
                status = {
                    "returncode": result.returncode,
                    "attempts": len(outputs),
                    "output": "\n".join(outputs)[-8000:],
                    "finished_at": utc_now(),
                }
                Path(item, "conversion.json").write_text(
                    json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
                if result.returncode:
                    self.last_error = result.stdout.strip() or "export failed"
                else:
                    self.last_error = ""
            finally:
                self.items.task_done()
