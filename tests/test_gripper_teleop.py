#!/usr/bin/env python3
import importlib.util
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/pi05_pika_input/scripts/gripper_input.py"
spec = importlib.util.spec_from_file_location("gripper_input", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GripperInputTest(unittest.TestCase):
    def test_encoder_endpoints_map_to_piper_travel(self):
        self.assertAlmostEqual(module.piper_target(0.0), 0.0)
        self.assertAlmostEqual(module.piper_target(1.67), 0.10)
        self.assertAlmostEqual(module.piper_target(99.0), 0.10)
        self.assertGreater(module.piper_target(0.8), 0.0)
        self.assertLess(module.piper_target(0.8), 0.10)
        self.assertAlmostEqual(module.piper_target(1.67, 0.10), 0.10)
        self.assertLess(module.piper_target(0.8, 0.10), 0.10)

    def test_invalid_mapping_values_are_rejected(self):
        for value in (math.nan, math.inf):
            with self.assertRaises(ValueError):
                module.piper_target(value)
        for maximum in (0.0, -0.1, 0.101):
            with self.assertRaises(ValueError):
                module.piper_target(0.5, maximum)

    def test_stream_parser_handles_fragmented_frames_and_errors(self):
        parser = module.FrameParser()
        self.assertEqual(parser.feed(b'noise{"Command":1,"AS50'), [])
        self.assertEqual(parser.feed(b'47":{"rad":0.5}}'), [0.5])
        self.assertEqual(parser.feed(
            b'{"Command":1,"AS5047":{"error":1,"rad":0.8}}'), [])

    def test_stream_parser_recovers_after_damaged_complete_frame(self):
        parser = module.FrameParser()
        self.assertEqual(parser.feed(
            b'{broken}{"AS5047":{"rad":0.5}}'), [0.5])
        self.assertEqual(parser.buffer, "")

    def test_stream_parser_ignores_braces_inside_strings(self):
        parser = module.FrameParser()
        self.assertEqual(parser.feed(
            b'{"note":"} {","AS5047":{"rad":0.6}}'), [0.6])

    def test_runtime_is_read_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("os.O_RDONLY", text)
        self.assertNotIn("os.write", text)
        self.assertIn("fcntl.LOCK_EX | fcntl.LOCK_NB", text)


if __name__ == "__main__":
    unittest.main()
