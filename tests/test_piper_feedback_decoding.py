#!/usr/bin/env python3
"""Offline protocol cross-checks; no SDK interface or CAN connection."""
import importlib.util
import math
from pathlib import Path
import struct
import unittest

import can
from piper_sdk.protocol.protocol_v2.piper_protocol_v2 import C_PiperParserV2
from piper_sdk.piper_msgs.msg_v2 import PiperMessage, ArmMsgType, ArmMsgJointCtrl

spec = importlib.util.spec_from_file_location(
    'feedback_check', Path(__file__).resolve().parents[1] / 'scripts/check_piper_feedback_decoding.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class DecoderCrossCheck(unittest.TestCase):
    def test_signed_and_endian_vectors(self):
        parser = C_PiperParserV2()
        for cid in (0x2A5, 0x2A6, 0x2A7):
            for pair in ((0, 0), (1000, -1000), (180000, -180000),
                         (2147483647, -2147483648)):
                error = checker.compare_frame(cid, struct.pack('>ii', *pair), parser)
                # Different floating-point multiplication order at int32 extremes.
                self.assertLessEqual(error, 1e-10)

    def test_vendor_command_encoding_preserves_six_joint_targets(self):
        parser = C_PiperParserV2()
        values = (57, 12345, -54321, 1000, -1000, 0)
        self.assertAlmostEqual(values[0] * math.pi / 180000, 0.000994837673636768)
        joints = ArmMsgJointCtrl(*values)
        for i, kind in enumerate((ArmMsgType.PiperMsgJointCtrl_12,
                                  ArmMsgType.PiperMsgJointCtrl_34,
                                  ArmMsgType.PiperMsgJointCtrl_56)):
            message = PiperMessage(type_=kind, arm_joint_ctrl=joints)
            tx = can.Message()
            self.assertTrue(parser.EncodeMessage(message, tx))
            self.assertEqual(tx.arbitration_id, 0x155 + i)
            self.assertEqual(struct.unpack('>ii', bytes(tx.data)), values[i*2:i*2+2])


if __name__ == '__main__':
    unittest.main()
