#!/usr/bin/env python3

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/pi05_data_collection/src"))

from pi05_data_collection.session import dual_vector, FEATURE_NAMES  # noqa: E402
from pi05_data_collection.storage import EpisodeWriter  # noqa: E402
from pi05_data_collection.camera_devices import resolve_camera_devices  # noqa: E402
from pi05_data_collection.mapping import load_collection_mapping  # noqa: E402


class Header:
    def __init__(self):
        self.stamp = None


class CompressedImage:
    def __init__(self):
        self.header = Header()
        self.format = ""
        self.data = b""


class FakeBag:
    def __init__(self, path, mode):
        self.path = Path(path)
        self.path.touch()
        self.rows = []

    def write(self, topic, message, t=None):
        self.rows.append((topic, message, t))

    def close(self):
        pass


class FakeRosbag:
    Bag = FakeBag


class Message:
    def __init__(self, values):
        self.position = values


class DataCollectionStorageTest(unittest.TestCase):
    def test_success_spool_contains_recorded_home_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = EpisodeWriter(directory, "pick object", 30, 64, 48,
                                   FakeRosbag, CompressedImage)
            image = np.zeros((48, 64, 3), dtype=np.uint8)
            values = tuple(float(index) for index in range(14))
            writer.add_sample(1.0, 0.0, "manipulation",
                              {key: image for key in ("left_wrist", "right_wrist", "top")},
                              values, values, {"state": 0.01})
            writer.add_sample(2.0, 1 / 30, "return_home",
                              {key: image for key in ("left_wrist", "right_wrist", "top")},
                              values, values, {"state": 0.01})
            path = writer.close("success", home_confirmed=True)
            manifest = json.loads((path / "manifest.json").read_text())
            rows = [json.loads(line) for line in (path / "frames.jsonl").read_text().splitlines()]
            self.assertTrue(manifest["home_confirmed"])
            self.assertEqual([row["phase"] for row in rows],
                             ["manipulation", "return_home"])
            for key in ("left_wrist", "right_wrist", "top"):
                capture = cv2.VideoCapture(str(path / (key + ".avi")))
                count = 0
                while capture.read()[0]:
                    count += 1
                capture.release()
                self.assertEqual(count, 2)

    def test_discard_removes_spool_after_home(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = EpisodeWriter(directory, "task", 30, 64, 48,
                                   FakeRosbag, CompressedImage)
            path = writer.path
            self.assertIsNone(writer.close("discard", home_confirmed=True))
            self.assertFalse(path.exists())

    def test_success_and_failure_are_stored_in_separate_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            success = EpisodeWriter(directory, "task", 30, 64, 48,
                                    FakeRosbag, CompressedImage)
            success_path = success.close("success", home_confirmed=True)
            failure = EpisodeWriter(directory, "task", 30, 64, 48,
                                    FakeRosbag, CompressedImage)
            failure_path = failure.close(
                "failure", reason="operator marked failure", home_confirmed=True)
            self.assertEqual(success_path.parent, Path(directory) / "raw" / "success")
            self.assertEqual(failure_path.parent, Path(directory) / "raw" / "failure")
            self.assertNotEqual(success_path.parent, failure_path.parent)

    def test_dual_vector_has_documented_order(self):
        vector = dual_vector(Message(range(7)), Message(range(10, 17)))
        self.assertEqual(vector, tuple(range(7)) + tuple(range(10, 17)))
        self.assertEqual(len(FEATURE_NAMES), 14)


class ExportContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "export_lerobot_episode", ROOT / "scripts/export_lerobot_episode.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_features_are_fixed_to_three_rgb_and_fourteen_values(self):
        values = self.module.features(480, 640)
        self.assertEqual(values["observation.state"]["shape"], (14,))
        self.assertEqual(values["action"]["shape"], (14,))
        self.assertEqual(
            sorted(key for key in values if key.startswith("observation.images.")),
            ["observation.images.left_wrist", "observation.images.right_wrist",
             "observation.images.top"],
        )


class CameraResolutionTest(unittest.TestCase):
    def _config(self, directory):
        path = Path(directory) / "cameras.env"
        path.write_text(
            "PI05_CAMERA_LEFT_WRIST_SERIAL=LEFT\n"
            "PI05_CAMERA_RIGHT_WRIST_SERIAL=RIGHT\n"
            "PI05_CAMERA_TOP_SERIAL=TOP\n",
            encoding="utf-8")
        return path

    def test_missing_camera_is_reported_without_aborting_resolution(self):
        identities = {
            Path("/dev/video0"): ("LEFT", "[0]: 'MJPG'"),
            Path("/dev/video2"): ("TOP", "[0]: 'YUYV'"),
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch(
                "pi05_data_collection.camera_devices.device_identity",
                side_effect=lambda path: identities[path]):
            resolved, errors = resolve_camera_devices(
                self._config(directory), identities.keys())
        self.assertEqual(resolved["left_wrist"], "/dev/video0")
        self.assertEqual(resolved["top"], "/dev/video2")
        self.assertNotIn("right_wrist", resolved)
        self.assertIn("right_wrist", errors)

    def test_all_three_roles_resolve_by_serial_and_format(self):
        identities = {
            Path("/dev/video8"): ("RIGHT", "[0]: 'MJPG'"),
            Path("/dev/video1"): ("LEFT", "[0]: 'MJPG'"),
            Path("/dev/video4"): ("TOP", "[0]: 'YUYV'"),
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch(
                "pi05_data_collection.camera_devices.device_identity",
                side_effect=lambda path: identities[path]):
            resolved, errors = resolve_camera_devices(
                self._config(directory), identities.keys())
        self.assertFalse(errors)
        self.assertEqual(set(resolved), {"left_wrist", "right_wrist", "top"})

    def test_alias_and_real_node_are_not_treated_as_two_cameras(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "video16"
            alias = Path(directory) / "video60"
            target.touch()
            alias.symlink_to(target)
            identities = {
                target: ("RIGHT", "[0]: 'MJPG'"),
            }
            with mock.patch(
                    "pi05_data_collection.camera_devices.device_identity",
                    side_effect=lambda path: identities[path]):
                resolved, errors = resolve_camera_devices(
                    self._config(directory), [target, alias])
        self.assertEqual(resolved["right_wrist"], str(target))
        self.assertNotIn("right_wrist", errors)


class CollectionMappingTest(unittest.TestCase):
    def test_committed_mapping_matches_dataset_contract(self):
        mapping = load_collection_mapping(ROOT / "config/data-collection-mapping.yaml")
        self.assertEqual(mapping["arms"]["left"]["feedback_topic"],
                         "/joint_states_single_l")
        self.assertEqual(mapping["arms"]["right"]["feedback_topic"],
                         "/joint_states_single_r")
        self.assertEqual(mapping["arms"]["left"]["action_topic"],
                         "/left_arm/joint_ctrl_raw")
        self.assertEqual(mapping["arms"]["right"]["action_topic"],
                         "/right_arm/joint_ctrl_raw")
        self.assertEqual(tuple(mapping["vector_order"]), FEATURE_NAMES)

    def test_mapping_rejects_swapped_joint_order(self):
        source = ROOT / "config/data-collection-mapping.yaml"
        with tempfile.TemporaryDirectory() as directory:
            data = source.read_text(encoding="utf-8")
            data = data.replace("  - left_joint1\n  - left_joint2\n",
                                "  - left_joint2\n  - left_joint1\n", 1)
            path = Path(directory) / "mapping.yaml"
            path.write_text(data, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_collection_mapping(path)


if __name__ == "__main__":
    unittest.main()
