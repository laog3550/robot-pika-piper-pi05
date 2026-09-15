#!/usr/bin/env python3
"""Wall-clock single-arm authorization and motion envelope; no ROS or CAN."""
import math


class SafetyGate:
    def __init__(self):
        self.phase = 'DISARMED'
        self.reason = ''
        self.feedback = None
        self.feedback_time = None
        self.localization_time = None
        self.localization_ok = False
        self.ik_ok = False
        self.ik_time = None
        self.reference = None
        self.settle_start = None
        self.feedback_count = 0
        self.settle_count = 0

    def fail(self, reason):
        self.phase = 'FAULT'
        self.reason = reason
        return False

    def fresh(self, now):
        return (self.feedback_time is not None and now-self.feedback_time < .35
                and self.localization_time is not None and now-self.localization_time < .35
                and self.localization_ok and self.ik_ok and self.ik_time is not None
                and now-self.ik_time < .35)

    def blockers(self, now):
        reasons=[]
        if self.phase != 'DISARMED':
            reasons.append('phase='+self.phase+((': '+self.reason) if self.reason else ''))
        for name,stamp in (('feedback',self.feedback_time),('localization',self.localization_time),('IK',self.ik_time)):
            if stamp is None:
                reasons.append(name+' missing')
            elif not 0 <= now-stamp < .35:
                reasons.append(name+' stale')
        if not self.localization_ok:reasons.append('localization invalid')
        if not self.ik_ok:reasons.append('IK not clear')
        return reasons

    def begin(self, now):
        if self.phase != 'DISARMED' or not self.fresh(now):
            return False
        self.reference = list(self.feedback)
        self.phase = 'ENABLING'
        return True

    def enabled(self, now):
        if self.phase != 'ENABLING':
            return False
        self.phase = 'SETTLING'
        self.settle_start = now
        self.settle_count = self.feedback_count
        return True

    def observe_feedback(self, positions, now):
        if len(positions) < 7 or not all(math.isfinite(x) for x in positions[:7]):
            self.feedback=None
            self.feedback_time=None
            if self.phase=='DISARMED':
                return False
            return self.fail('invalid feedback')
        self.feedback = list(positions[:7])
        self.feedback_time = now
        self.feedback_count += 1
        if self.phase in ('ENABLING', 'SETTLING'):
            if max(abs(a-b) for a,b in zip(self.feedback[:6],self.reference[:6])) > .002:
                return self.fail('enable transition joint drift exceeded 0.002 rad')
        if self.phase == 'READY':
            if max(abs(a-b) for a,b in zip(self.feedback[:6],self.reference[:6])) > .025:
                return self.fail('feedback exceeded session envelope')
        return True

    def tick(self, now):
        if self.phase in ('ENABLING','SETTLING','READY') and not self.fresh(now):
            return self.fail('feedback, localization or IK unavailable')
        if self.phase == 'SETTLING' and now-self.settle_start >= 2:
            if self.feedback_count-self.settle_count < 20:
                return self.fail('insufficient post-enable feedback')
            self.phase = 'READY'
        return self.phase == 'READY'

    def accept_target(self, positions, now):
        if self.phase != 'READY' or not self.fresh(now):
            return False
        if len(positions) != 7 or not all(math.isfinite(x) for x in positions):
            return self.fail('invalid target')
        if max(abs(a-b) for a,b in zip(positions[:6],self.reference[:6])) > 1.0:
            return self.fail('target exceeded 0.02 rad session envelope')
        if max(abs(a-b) for a,b in zip(positions[:6],self.feedback[:6])) > 1    :
            return self.fail('target/feedback difference exceeded 0.01 rad')
        return True
