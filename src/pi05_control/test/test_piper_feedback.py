#!/usr/bin/env python3

import math
import struct
import unittest

from pi05_control.piper_feedback import (
    FeedbackAssembler,
    MotorTelemetryWindow,
    decode_feedback_frame,
    decode_motor_high_speed_frame,
)


class PiperFeedbackTest(unittest.TestCase):
    def test_decodes_motor_speed_and_current_without_exposing_position(self):
        decoded = decode_motor_high_speed_frame(
            0x253, struct.pack(">hhi", -125, 2345, 123456789))
        self.assertEqual(decoded[0], 2)
        self.assertAlmostEqual(decoded[1], -0.125)
        self.assertAlmostEqual(decoded[2], 2.345)

    def test_motor_telemetry_aggregates_peak_magnitudes(self):
        telemetry = MotorTelemetryWindow()
        telemetry.update(0x253, struct.pack(">hhi", -125, 2000, 1))
        telemetry.update(0x253, struct.pack(">hhi", 50, -2500, 2))
        self.assertEqual(telemetry.summary()[2], (3, 2, 0.125, 2.5))

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
