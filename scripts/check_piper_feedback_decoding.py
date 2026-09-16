#!/usr/bin/env python3
"""Compare identical passive CAN frames with the local and vendor decoders."""
import argparse
import collections
import json
import math
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/pi05_control/src'))
from pi05_control.piper_feedback import decode_feedback_frame, JOINT_FRAME_IDS


def compare_frame(can_id, payload, parser):
    import can
    from piper_sdk.piper_msgs.msg_v2 import PiperMessage
    message = PiperMessage()
    if not parser.DecodeMessage(can.Message(arbitration_id=can_id, data=payload,
                                           is_extended_id=False), message):
        raise ValueError('vendor parser rejected joint feedback')
    local = decode_feedback_frame(can_id, payload)
    vendor = tuple(getattr(message.arm_joint_feedback, 'joint_' + str(j + 1))
                   * math.pi / 180000 for j in JOINT_FRAME_IDS[can_id])
    return max(abs(a - b) for a, b in zip(local[2], vendor))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('side', choices=('left', 'right'))
    parser.add_argument('--duration', type=float, default=5)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 1 <= args.duration <= 60:
        parser.error('duration must be between 1 and 60 seconds')
    from piper_sdk.protocol.protocol_v2.piper_protocol_v2 import C_PiperParserV2
    decoder = C_PiperParserV2()
    counts = collections.Counter()
    mismatches = 0
    malformed = 0
    max_error = 0.0
    low_states = {}
    status = None
    ranges = [[] for _ in range(6)]
    fmt = struct.Struct('=IB3x8s')
    with socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW) as source:
        source.bind((args.side + '_piper',))
        source.settimeout(0.1)
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            try:
                frame = source.recv(fmt.size)
            except socket.timeout:
                continue
            if len(frame) != fmt.size:
                continue
            cid, dlc, payload = fmt.unpack(frame)
            if cid & 0xE0000000:
                continue
            if cid in JOINT_FRAME_IDS:
                if dlc != 8:
                    malformed += 1
                    continue
                error = compare_frame(cid, payload, decoder)
                max_error = max(max_error, error)
                mismatches += int(error > 1e-12)
                counts[cid] += 1
                decoded = decode_feedback_frame(cid, payload)
                for j, value in zip(decoded[1], decoded[2]):
                    ranges[j].append(value)
            elif 0x261 <= cid <= 0x266 and dlc == 8:
                low_states[cid] = bool(payload[5] & 0x40)
            elif cid == 0x2A1 and dlc == 8:
                status = dict(zip(('ctrl_mode', 'arm_status', 'mode_feed',
                                   'teach_status', 'motion_status'), payload[:5]))
    complete = all(counts[cid] >= 10 for cid in JOINT_FRAME_IDS)
    print(json.dumps({'side': args.side, 'same_frame_comparison': True,
                      'joint_frame_samples': {hex(cid): counts[cid] for cid in JOINT_FRAME_IDS},
                      'decoder_mismatches': mismatches, 'malformed_joint_frames': malformed,
                      'max_decoder_difference_rad': max_error,
                      'joint_feedback_range_rad': [round(max(v)-min(v), 9) if v else None for v in ranges],
                      'enabled_motors': sum(low_states.values()) if len(low_states) == 6 else None,
                      'status': status,
                      'interpretation': 'Decoder agreement does not verify physical motion or firmware references.'},
                     sort_keys=True))
    return 0 if complete and not mismatches and not malformed else 1


if __name__ == '__main__':
    sys.exit(main())
