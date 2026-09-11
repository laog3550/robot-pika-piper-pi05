#!/usr/bin/env python3

import math
import struct
import unittest

from pi05_control.piper_feedback import FeedbackAssembler, decode_feedback_frame


class PiperFeedbackTest(unittest.TestCase):
    def test_joint_units_and_endianness(self):
        decoded = decode_feedback_frame(0x2A5, struct.pack(">ii", 180000, -90000))
        self.assertEqual(decoded[0], "joints")
        self.assertEqual(decoded[1], (0, 1))
        self.assertAlmostEqual(decoded[2][0], math.pi)
        self.assertAlmostEqual(decoded[2][1], -math.pi / 2.0)

    def test_gripper_units(self):
        decoded = decode_feedback_frame(0x2A8, struct.pack(">ihBB", 50000, 0, 0, 0))
        self.assertEqual(decoded[0], "gripper")
        self.assertAlmostEqual(decoded[1], 0.05)

    def test_complete_cycle_required(self):
        assembler = FeedbackAssembler()
        self.assertIsNone(assembler.update(0x2A5, struct.pack(">ii", 1000, 2000)))
        self.assertIsNone(assembler.update(0x2A6, struct.pack(">ii", 3000, 4000)))
        self.assertIsNone(assembler.update(0x2A7, struct.pack(">ii", 5000, 6000)))
        positions = assembler.update(0x2A8, struct.pack(">ihBB", 7000, 0, 0, 0))
        self.assertEqual(len(positions), 7)
        self.assertAlmostEqual(positions[6], 0.007)
        self.assertIsNone(assembler.update(0x2A8, struct.pack(">ihBB", 8000, 0, 0, 0)))

    def test_unknown_id_and_invalid_payload(self):
        self.assertIsNone(decode_feedback_frame(0x123, b"12345678"))
        with self.assertRaises(ValueError):
            decode_feedback_frame(0x2A5, b"short")


if __name__ == "__main__":
    unittest.main()
