#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
/usr/bin/python3 - <<'PY'
import ast
import importlib.util
import json
import pathlib
import struct
import unittest

path=pathlib.Path('scripts/diagnose_piper_command_feedback.py')
spec=importlib.util.spec_from_file_location('diagnostic',path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Replay:
    def __init__(self):
        self.d=m.Diagnostic(2)
        self.now=0.0
        self.base=[10000,30000,-40000,0,5000,-1000]
    def feed(self,cid,payload,dt=.001):
        self.now+=dt
        self.d.observe(self.now,cid,payload)
    def vector(self,ids,values):
        for i,cid in enumerate(ids):self.feed(cid,struct.pack('>ii',*values[i*2:i*2+2]))
    def baseline(self):
        for _ in range(20):self.vector(m.FEEDBACK_IDS,self.base)
    def command(self,values=None):self.vector(m.COMMAND_IDS,values or self.base)
    def feedback(self,values=None):self.vector(m.FEEDBACK_IDS,values or self.base)
    def report(self):return self.d.snapshot(self.now)

class Tests(unittest.TestCase):
    def test_complete_observation_not_safety_pass(self):
        r=Replay();r.baseline()
        for _ in range(10):
            r.command();r.feedback()
            for cid in range(0x251,0x257):r.feed(cid,struct.pack('>hhi',0,0,0))
            r.feed(0x2A1,bytes([1,0,1,0,0,0,0,0]))
        report=r.report()
        self.assertEqual(report['result'],'OBSERVATION_COMPLETE')
        self.assertEqual(report['diagnostic_tags'],[])
        self.assertIn('not controller acknowledgement',report['interpretation'])
        self.assertEqual(report['mode_status'][0]['mode_feed'],1)

    def test_unchanged_target_drift_detected(self):
        r=Replay();r.baseline();target=r.base[:];target[1]+=286;r.command(target)
        feedback=target[:];feedback[2]-=300;r.feedback(feedback)
        report=r.report()
        self.assertIn('drift_observed_with_recent_unchanged_target',report['diagnostic_tags'])
        self.assertEqual(report['joints']['J3']['peak_target_delta_rad'],0)
        self.assertEqual(report['joints']['J3']['drift_samples_with_recent_unchanged_target'],1)

    def test_changed_nonselected_target_detected(self):
        r=Replay();r.baseline();target=r.base[:];target[2]-=300;r.command(target);r.feedback(target)
        tags=r.report()['diagnostic_tags']
        self.assertIn('nonselected_target_differs_from_baseline',tags)
        self.assertIn('drift_observed_with_recent_changed_target',tags)

    def test_missing_or_duplicate_frame_not_complete(self):
        for ids in ((0x155,0x157),(0x155,0x155,0x157),(0x156,0x155,0x157)):
            r=Replay();r.baseline()
            for cid in ids:r.feed(cid,bytes(8))
            report=r.report()
            self.assertEqual(report['counts'].get('complete_command_groups',0),0)
            self.assertIn('command_group_incomplete_or_out_of_order',report['diagnostic_tags'])

    def test_slow_frame_group_unconfirmed(self):
        r=Replay();r.baseline();r.feed(0x155,bytes(8));r.feed(0x156,bytes(8),dt=.03);r.feed(0x157,bytes(8))
        self.assertIn('no_complete_command_observed',r.report()['diagnostic_tags'])

    def test_delayed_feedback_not_associated_to_old_target(self):
        r=Replay();r.baseline();r.command();r.now+=.3;r.feedback()
        report=r.report()
        self.assertIn('feedback_without_recent_complete_target',report['diagnostic_tags'])
        self.assertEqual(report['joints']['J3']['correlated_joint_samples'],0)

    def test_feedback_gap_with_new_command_detected(self):
        r=Replay();r.baseline();r.command();r.feedback();r.now+=.15;r.command();r.feedback()
        self.assertIn('feedback_receive_gap_over_100ms',r.report()['diagnostic_tags'])

    def test_command_before_baseline_never_retroactively_verified(self):
        r=Replay();r.command();r.baseline();r.command();r.feedback()
        self.assertFalse(r.report()['stable_baseline_before_first_command'])

    def test_stale_precommand_baseline_rejected(self):
        r=Replay();r.baseline();r.now+=.2;r.command()
        self.assertFalse(r.report()['stable_baseline_before_first_command'])

    def test_unstable_baseline_rejected(self):
        r=Replay()
        for i in range(20):
            values=r.base[:];values[2]+=100 if i%2 else 0;r.feedback(values)
        r.command()
        self.assertFalse(r.report()['stable_baseline_before_first_command'])

    def test_boundary_group_requires_review(self):
        r=Replay();r.baseline();r.feed(0x155,bytes(8))
        self.assertIn('command_group_incomplete_or_out_of_order',r.report()['diagnostic_tags'])

    def test_malformed_and_nonmonotonic(self):
        r=Replay();r.feed(0x155,b'x')
        self.assertIn('malformed_relevant_frame',r.report()['diagnostic_tags'])
        with self.assertRaises(ValueError):r.d.observe(-1,0x155,bytes(8))

    def test_unsigned_identity_payload_never_exported(self):
        r=Replay();r.d.observe(0,0x4AF,b'PRIVATE!')
        output=json.dumps(r.report())
        self.assertNotIn('PRIVATE',output)
        self.assertNotIn('payload',output)

    def test_motor_speed_sign_and_mode(self):
        r=Replay();r.baseline();r.command()
        r.feed(0x253,struct.pack('>hhi',-186,282,123456))
        report=r.report()
        self.assertEqual(report['joints']['J3']['peak_motor_speed_rad_s'],.186)
        self.assertNotIn('123456',json.dumps(report))

    def test_incomplete_new_group_invalidates_previous_target(self):
        r=Replay();r.baseline();r.command();r.feed(0x155,bytes(8));r.feed(0x157,bytes(8));r.feedback()
        self.assertIn('feedback_without_recent_complete_target',r.report()['diagnostic_tags'])

    def test_wrong_mode_and_bounded_status_storage(self):
        r=Replay();r.baseline();r.command()
        for i in range(70):r.feed(0x2A1,bytes([0,i,0,0,0,0,0,0]))
        report=r.report()
        self.assertEqual(len(report['mode_status']),64)
        self.assertIn('status_state_capacity_exceeded',report['diagnostic_tags'])
        self.assertIn('CAN_MOVE_J_status_unconfirmed',report['diagnostic_tags'])

    def test_no_write_or_control_apis(self):
        tree=ast.parse(path.read_text())
        calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertFalse(set(calls)&{'send','sendto','sendall','publish','JointCtrl','EnableArm','DisableArm','ConnectPort','write_text','write_bytes'})
        with self.assertRaises(SystemExit):m.main(['--side','left','--joint','2','--duration','nan'])

unittest.main()
PY
