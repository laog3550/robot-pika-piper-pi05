#!/usr/bin/env python3
"""Receive-only, aggregate-only Piper command/feedback correlation."""
import argparse
import collections
import json
import math
import socket
import struct
import sys
import time

FRAME = struct.Struct('=IB3x8s')
SCALE = math.pi / 180000.0
COMMAND_IDS = (0x155, 0x156, 0x157)
FEEDBACK_IDS = (0x2A5, 0x2A6, 0x2A7)
RELEVANT_IDS = COMMAND_IDS + FEEDBACK_IDS + tuple(range(0x251, 0x257)) + (0x2A1,)
PAIR_WINDOW = 0.020
FRESH_WINDOW = 0.100
CORRELATION_WINDOW = 0.200
COMMAND_TOLERANCE = 0.00005  # Quantization/alignment tolerance, not a motion gate.
DRIFT_LIMIT = 0.002


class Diagnostic:
    def __init__(self, joint):
        if isinstance(joint, bool) or joint not in range(1, 7):
            raise ValueError('joint must be in 1..6')
        self.selected = joint - 1
        self.baseline = None
        self.baseline_samples = collections.deque(maxlen=20)
        self.feedback_parts = {}
        self.feedback_started = None
        self.last_feedback = None
        self.first_command_seen = False
        self.command_parts = []
        self.command_started = None
        self.latest_command = None
        self.latest_command_time = None
        self.counts = collections.Counter()
        self.tags = set()
        self.command_peak = [0.0] * 6
        self.feedback_peak = [0.0] * 6
        self.motor_peak = [0.0] * 6
        self.motor_counts = [0] * 6
        self.correlated = [0] * 6
        self.unchanged_target_drift = [0] * 6
        self.changed_target_drift = [0] * 6
        self.last_joint_feedback = [None] * 6
        self.feedback_gap = [0.0] * 6
        self.status_states = collections.Counter()
        self.last_time = None

    def _incomplete(self):
        self.counts['incomplete_command_groups'] += 1
        self.tags.add('command_group_incomplete_or_out_of_order')
        self.command_parts = []
        self.command_started = None
        self.latest_command = None
        self.latest_command_time = None

    def observe(self, now, can_id, payload):
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            raise ValueError('receive times must be finite and monotonic')
        self.last_time = now
        if self.command_parts and now - self.command_started > PAIR_WINDOW:
            self._incomplete()
        if can_id not in RELEVANT_IDS:
            return  # Never decode firmware/identity responses or other payloads.
        if len(payload) != 8:
            self.counts['malformed_relevant_frames'] += 1
            self.tags.add('malformed_relevant_frame')
            return
        if can_id in COMMAND_IDS:
            self._command(now, can_id, payload)
        elif can_id in FEEDBACK_IDS:
            self._feedback(now, can_id, payload)
        elif 0x251 <= can_id <= 0x256:
            if self.first_command_seen:
                index = can_id - 0x251
                speed = struct.unpack('>h', payload[:2])[0] * .001
                self.motor_peak[index] = max(self.motor_peak[index], abs(speed))
                self.motor_counts[index] += 1
        elif can_id == 0x2A1 and self.first_command_seen:
            state = tuple(payload[:5]) + (int.from_bytes(payload[6:8], 'big'),)
            if state in self.status_states or len(self.status_states) < 64:
                self.status_states[state] += 1
            else:
                self.counts['status_states_excluded_at_capacity'] += 1
                self.tags.add('status_state_capacity_exceeded')

    def _command(self, now, can_id, payload):
        if not self.first_command_seen:
            self.first_command_seen = True
            if self.baseline is None or self.last_feedback is None or now-self.last_feedback > FRESH_WINDOW:
                self.baseline = None
                self.tags.add('stable_precommand_baseline_unconfirmed')
        self.counts['command_frames'] += 1
        expected = COMMAND_IDS[len(self.command_parts)//2]
        if can_id != expected:
            self._incomplete()
            if can_id != COMMAND_IDS[0]:
                return
        if not self.command_parts:
            self.command_started = now
        self.command_parts.extend(struct.unpack('>ii', payload))
        # Two joint values per frame; expected ID index is frame index.
        if len(self.command_parts) == 6:
            self.latest_command = tuple(v*SCALE for v in self.command_parts)
            self.latest_command_time = now
            self.counts['complete_command_groups'] += 1
            if self.baseline is not None:
                for i, value in enumerate(self.latest_command):
                    delta = abs(value-self.baseline[i])
                    self.command_peak[i] = max(self.command_peak[i], delta)
                    if i != self.selected and delta > COMMAND_TOLERANCE:
                        self.tags.add('nonselected_target_differs_from_baseline')
            self.command_parts = []
            self.command_started = None

    def _feedback(self, now, can_id, payload):
        self.counts['feedback_frames'] += 1
        values = tuple(v*SCALE for v in struct.unpack('>ii', payload))
        index = FEEDBACK_IDS.index(can_id)*2
        if self.baseline is not None and self.first_command_seen:
            for i, value in zip((index, index+1), values):
                if self.last_joint_feedback[i] is not None:
                    gap = now-self.last_joint_feedback[i]
                    self.feedback_gap[i] = max(self.feedback_gap[i], gap)
                    if gap > FRESH_WINDOW:
                        self.tags.add('feedback_receive_gap_over_100ms')
                self.last_joint_feedback[i] = now
                delta = abs(value-self.baseline[i])
                self.feedback_peak[i] = max(self.feedback_peak[i], delta)
                if self.latest_command_time is not None and now-self.latest_command_time <= CORRELATION_WINDOW:
                    self.correlated[i] += 1
                    if i != self.selected and delta > DRIFT_LIMIT:
                        if abs(self.latest_command[i]-self.baseline[i]) <= COMMAND_TOLERANCE:
                            self.unchanged_target_drift[i] += 1
                            self.tags.add('drift_observed_with_recent_unchanged_target')
                        else:
                            self.changed_target_drift[i] += 1
                            self.tags.add('drift_observed_with_recent_changed_target')
                else:
                    self.counts['feedback_joint_samples_without_recent_complete_target'] += 1
        if self.first_command_seen:
            return
        if (self.feedback_started is not None and now-self.feedback_started > PAIR_WINDOW) or can_id in self.feedback_parts:
            self.feedback_parts = {}
            self.feedback_started = None
        if not self.feedback_parts:
            self.feedback_started = now
        self.feedback_parts[can_id] = values
        if len(self.feedback_parts) == 3:
            positions = sum((self.feedback_parts[cid] for cid in FEEDBACK_IDS), ())
            if self.last_feedback is not None and now-self.last_feedback > FRESH_WINDOW:
                self.baseline_samples.clear()
                self.baseline = None
            self.last_feedback = now
            self.baseline_samples.append(positions)
            self.feedback_parts = {}
            self.feedback_started = None
            if len(self.baseline_samples) == 20:
                if all(max(s[i] for s in self.baseline_samples)-min(s[i] for s in self.baseline_samples) <= .0005 for i in range(6)):
                    self.baseline = tuple(sum(s[i] for s in self.baseline_samples)/20 for i in range(6))
                else:
                    self.baseline = None
                    self.baseline_samples.clear()
                    self.baseline_samples.append(positions)

    def snapshot(self, ended):
        boundary_partial = bool(self.command_parts)
        if self.command_parts:
            self._incomplete()  # May be a capture-end boundary, not a proven send failure.
        tags = set(self.tags)
        if not self.counts['complete_command_groups']:
            tags.add('no_complete_command_observed')
        if self.baseline is None:
            tags.add('stable_precommand_baseline_unconfirmed')
        if not all(count >= 3 for count in self.correlated):
            tags.add('command_feedback_correlation_incomplete')
        if not all(count >= 10 for count in self.motor_counts):
            tags.add('motor_feedback_incomplete')
        if not self.status_states:
            tags.add('mode_status_unobserved')
        elif not any(state[0] == 1 and state[2] == 1 for state in self.status_states):
            tags.add('CAN_MOVE_J_status_unconfirmed')
        if self.counts['feedback_joint_samples_without_recent_complete_target']:
            tags.add('feedback_without_recent_complete_target')
        return {
            'result': 'REVIEW_REQUIRED' if tags else 'OBSERVATION_COMPLETE',
            'diagnostic_tags': sorted(tags), 'counts': dict(self.counts),
            'stable_baseline_before_first_command': self.baseline is not None and self.first_command_seen,
            'capture_end_partial_command_group': boundary_partial,
            'joints': {'J'+str(i+1): {
                'peak_target_delta_rad': round(self.command_peak[i], 6),
                'peak_feedback_delta_rad': round(self.feedback_peak[i], 6),
                'peak_motor_speed_rad_s': round(self.motor_peak[i], 3),
                'motor_samples': self.motor_counts[i], 'correlated_joint_samples': self.correlated[i],
                'max_observed_feedback_gap_ms': round(self.feedback_gap[i]*1000, 3),
                'drift_samples_with_recent_unchanged_target': self.unchanged_target_drift[i],
                'drift_samples_with_recent_changed_target': self.changed_target_drift[i],
            } for i in range(6)},
            'mode_status': [dict(zip(('ctrl_mode','arm_status','mode_feed','teach_status','motion_status','err_code'),state), samples=count)
                            for state,count in sorted(self.status_states.items())],
            'interpretation': 'Receive-time correlation only; not controller acknowledgement, causal proof, safety acceptance, or automatic stop.',
        }


def duration(value):
    result = float(value)
    if not math.isfinite(result) or not 1 <= result <= 60:
        raise argparse.ArgumentTypeError('duration must be in 1..60 seconds')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--side', required=True, choices=('left','right'))
    parser.add_argument('--joint', required=True, type=int, choices=range(1,7))
    parser.add_argument('--duration', type=duration, default=15)
    args = parser.parse_args(argv)
    diagnostic = Diagnostic(args.joint)
    try:
        with socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW) as source:
            source.bind((args.side+'_piper',))
            started = time.monotonic()
            ended = started+args.duration
            while time.monotonic() < ended:
                source.settimeout(max(.001, ended-time.monotonic()))
                try:
                    frame = source.recv(FRAME.size)
                except socket.timeout:
                    break
                if len(frame) != FRAME.size:
                    continue
                can_id, dlc, payload = FRAME.unpack(frame)
                if can_id & 0xE0000000:  # Ignore extended/RTR/error frames, never treat as commands.
                    continue
                diagnostic.observe(time.monotonic(),can_id,payload if dlc == 8 else b'')
        report = diagnostic.snapshot(time.monotonic())
        report.update(side=args.side,selected_joint=args.joint)
        print(json.dumps(report,sort_keys=True))
        return 1 if report['diagnostic_tags'] else 0
    except (OSError,ValueError,KeyboardInterrupt):
        print('[PI05] ERROR: passive diagnostic unavailable or interrupted',file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
