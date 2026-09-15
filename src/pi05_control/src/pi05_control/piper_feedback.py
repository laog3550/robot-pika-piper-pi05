"""Pure decoding helpers for passive Piper feedback frames."""

import math
import struct


JOINT_FRAME_IDS = {
    0x2A5: (0, 1),
    0x2A6: (2, 3),
    0x2A7: (4, 5),
}
GRIPPER_FRAME_ID = 0x2A8
REQUIRED_FRAME_IDS = frozenset(JOINT_FRAME_IDS) | {GRIPPER_FRAME_ID}
MOTOR_HIGH_SPEED_FRAME_IDS = {
    0x251: 0,
    0x252: 1,
    0x253: 2,
    0x254: 3,
    0x255: 4,
    0x256: 5,
}
MILLI_DEG_TO_RAD = math.pi / 180000.0
MICROMETER_TO_METER = 1.0 / 1000000.0
MILLI_UNIT = 1.0 / 1000.0


def decode_feedback_frame(can_id, payload):
    """Return decoded positions for one joint/gripper feedback frame."""
    if can_id not in REQUIRED_FRAME_IDS:
        return None
    if len(payload) != 8:
        raise ValueError("Piper feedback payload must contain exactly 8 bytes")
    if can_id in JOINT_FRAME_IDS:
        first, second = struct.unpack(">ii", payload)
        return (
            "joints",
            JOINT_FRAME_IDS[can_id],
            (first * MILLI_DEG_TO_RAD, second * MILLI_DEG_TO_RAD),
        )
    gripper_raw = struct.unpack(">i", payload[:4])[0]
    return ("gripper", gripper_raw * MICROMETER_TO_METER)


def decode_motor_high_speed_frame(can_id, payload):
    """Return joint, speed and current from a 0x251..0x256 feedback frame."""
    index = MOTOR_HIGH_SPEED_FRAME_IDS.get(can_id)
    if index is None:
        return None
    if len(payload) != 8:
        raise ValueError("Piper high-speed payload must contain exactly 8 bytes")
    speed_raw, current_raw, _position_raw = struct.unpack(">hhi", payload)
    return index, speed_raw * MILLI_UNIT, current_raw * MILLI_UNIT


class MotorTelemetryWindow(object):
    """Aggregate non-sensitive per-motor speed/current evidence."""

    def __init__(self):
        self.counts = [0] * 6
        self.peak_speed = [0.0] * 6
        self.peak_current = [0.0] * 6

    def update(self, can_id, payload):
        decoded = decode_motor_high_speed_frame(can_id, payload)
        if decoded is None:
            return False
        index, speed, current = decoded
        self.counts[index] += 1
        self.peak_speed[index] = max(self.peak_speed[index], abs(speed))
        self.peak_current[index] = max(self.peak_current[index], abs(current))
        return True

    def summary(self):
        return tuple(
            (index + 1, self.counts[index], self.peak_speed[index],
             self.peak_current[index])
            for index in range(6)
        )


class FeedbackAssembler:
    """Publish only coherent samples containing all four feedback frame IDs."""

    def __init__(self):
        self._joints = [0.0] * 6
        self._gripper = 0.0
        self._seen = set()

    def update(self, can_id, payload):
        decoded = decode_feedback_frame(can_id, payload)
        if decoded is None:
            return None
        if decoded[0] == "joints":
            indices, values = decoded[1], decoded[2]
            self._joints[indices[0]] = values[0]
            self._joints[indices[1]] = values[1]
        else:
            self._gripper = decoded[1]
        self._seen.add(can_id)
        if not REQUIRED_FRAME_IDS.issubset(self._seen):
            return None
        self._seen.clear()
        return tuple(self._joints + [self._gripper])
