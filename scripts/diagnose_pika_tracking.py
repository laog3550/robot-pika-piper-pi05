#!/usr/bin/env python3
"""Read-only, aggregate-only diagnosis of raw/relay Pika localization."""
import argparse
import collections
import json
import math
import sys
import threading
import time

from check_pika_localization import LocalizationStats, evaluate, ros_master_reachable


class Stream:
    def __init__(self, started):
        self.stats = LocalizationStats()
        self.started = started
        self.last_status = None
        self.last_pose = None
        self.status_gap = 0.0
        self.pose_gap = 0.0
        self.bad_start = None
        self.bad_runs = []
        self.leading_bad = False
        self.bad_near_pose_change = 0
        self.last_pose_change = None
        self.previous_pose = None
        self.pose_age_max = 0.0
        self.future_stamp_count = 0

    def observe_status(self, accurate, now):
        self.stats.observe_status(accurate)
        if self.last_status is not None:
            self.status_gap = max(self.status_gap, now - self.last_status)
        if not accurate:
            if self.bad_start is None:
                self.bad_start = now
                if self.last_status is None:
                    self.leading_bad = True
            if self.last_pose_change is not None and 0 <= now-self.last_pose_change <= 0.2:
                self.bad_near_pose_change += 1
        elif self.bad_start is not None:
            self.bad_runs.append(now-self.bad_start)
            self.bad_start = None
        self.last_status = now

    def observe_pose(self, position, orientation, stamp, frame, now, ros_now):
        self.stats.observe_pose(position, orientation, stamp, frame)
        if self.last_pose is not None:
            self.pose_gap = max(self.pose_gap, now-self.last_pose)
        values = tuple(position)+tuple(orientation)
        if self.previous_pose is not None and values != self.previous_pose:
            self.last_pose_change = now
        self.previous_pose = values
        if math.isfinite(ros_now-stamp):
            self.pose_age_max = max(self.pose_age_max, ros_now-stamp)
            self.future_stamp_count += int(stamp > ros_now+0.1)
        self.last_pose = now

    def snapshot(self, ended, phase):
        runs = self.bad_runs + ([ended-self.bad_start] if self.bad_start is not None else [])
        data = self.stats.snapshot()
        rate, failures = evaluate(data, ended-self.started, 30.0, 5,
                                 require_motion=phase == 'motion')
        if phase == 'static' and (data['max_translation'] >= .02 or data['max_rotation'] >= .10):
            failures.append('static phase contains motion; physical condition unconfirmed')
        return {
            'pose_samples': data['pose_count'], 'pose_rate_hz': round(rate, 1),
            'status_samples': data['status_count'], 'accurate_samples': data['accurate_count'],
            'inaccurate_samples': data['status_count']-data['accurate_count'],
            'invalid_runs': len(runs), 'longest_invalid_run_ms': round(max(runs, default=0)*1000, 2),
            'invalid_duration_observed_ms': round(sum(runs)*1000, 2),
            'first_run_left_censored': self.leading_bad,
            'last_run_right_censored': self.bad_start is not None,
            'bad_samples_with_recent_pose_change': self.bad_near_pose_change,
            'max_status_gap_ms': round(max(self.status_gap, ended-(self.last_status or self.started))*1000, 2),
            'max_pose_gap_ms': round(max(self.pose_gap, ended-(self.last_pose or self.started))*1000, 2),
            'max_published_pose_age_ms': round(self.pose_age_max*1000, 2),
            'future_stamp_samples': self.future_stamp_count,
            'motion': 'detected' if data['max_translation'] >= .02 or data['max_rotation'] >= .10 else 'not-detected',
            'failures': failures,
        }


class PoseMatch:
    """Bounded in-memory matching by stamp; never export signatures."""
    def __init__(self):
        self.pending = {'raw': collections.OrderedDict(), 'relay': collections.OrderedDict()}
        self.matched = 0
        self.mismatched = 0
        self.evicted = 0
        self.max_delay = 0.0

    def observe(self, layer, stamp, signature, now):
        other = 'relay' if layer == 'raw' else 'raw'
        if stamp in self.pending[other]:
            previous, arrived = self.pending[other].pop(stamp)
            if previous == signature:
                self.matched += 1
                self.max_delay = max(self.max_delay, abs(now-arrived))
            else:
                self.mismatched += 1
        else:
            self.pending[layer][stamp] = (signature, now)
            if len(self.pending[layer]) > 5000:
                self.pending[layer].popitem(last=False)
                self.evicted += 1

    def snapshot(self):
        return {'identical_pose_pairs': self.matched, 'different_pose_pairs': self.mismatched,
                'unpaired_boundary_or_missing': sum(map(len, self.pending.values())),
                'buffer_evictions': self.evicted, 'max_pair_arrival_difference_ms': round(self.max_delay*1000, 2)}


def duration(value):
    value = float(value)
    if not math.isfinite(value) or not 1 <= value <= 120:
        raise argparse.ArgumentTypeError('duration must be between 1 and 120 seconds')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=duration, default=30.0)
    parser.add_argument('--phase', choices=('static', 'motion'), required=True)
    args = parser.parse_args(argv)
    try:
        import os
        import rospy
        from geometry_msgs.msg import PoseStamped
        from data_msgs.msg import LocalizationStatus
        if not ros_master_reachable(os.environ.get('ROS_MASTER_URI', 'http://localhost:11311')):
            print('[PI05] ERROR: diagnostic ROS Master unavailable', file=sys.stderr)
            return 3
        rospy.init_node('pi05_tracking_diagnostic', anonymous=True, disable_signals=True)
        started = time.monotonic()
        streams = {(s,l):Stream(started) for s in ('left','right') for l in ('raw','relay')}
        matches = {s:PoseMatch() for s in ('left','right')}
        lock = threading.Lock()
        accepting = True
        def pose(side, layer, message):
            p=message.pose.position; q=message.pose.orientation
            position=(p.x,p.y,p.z); orientation=(q.x,q.y,q.z,q.w)
            now=time.monotonic()
            with lock:
                if not accepting:
                    return
                streams[(side,layer)].observe_pose(position,orientation,message.header.stamp.to_sec(),
                    message.header.frame_id,now,rospy.Time.now().to_sec())
                matches[side].observe(layer,message.header.stamp.to_nsec(),
                    (position,orientation,message.header.frame_id),now)
        def status(side, layer, message):
            with lock:
                if accepting:
                    streams[(side,layer)].observe_status(message.accurate,time.monotonic())
        subscribers=[]
        for side,layer in streams:
            topic='/pi05/pika_input/'+('raw/' if layer=='raw' else '')+side
            subscribers.extend([
                rospy.Subscriber(topic+'/pose',PoseStamped,lambda m,s=side,l=layer:pose(s,l,m),queue_size=100),
                rospy.Subscriber(topic+'/localization_status',LocalizationStatus,
                    lambda m,s=side,l=layer:status(s,l,m),queue_size=100),
            ])
        while time.monotonic()-started < args.duration and not rospy.is_shutdown():
            time.sleep(.05)
        ended=time.monotonic()
        with lock:
            accepting=False
            report={'phase':args.phase, 'elapsed_s':round(ended-started,2), 'sides':{}}
            failed=False
            for side in matches:
                raw=streams[(side,'raw')].snapshot(ended,args.phase)
                relay=streams[(side,'relay')].snapshot(ended,args.phase)
                pair=matches[side].snapshot()
                tags=[]
                if raw['inaccurate_samples']:tags.append('upstream_reported_invalid')
                if pair['different_pose_pairs']:tags.append('relay_content_mismatch')
                if not pair['identical_pose_pairs']:tags.append('relay_equivalence_unconfirmed')
                if not raw['inaccurate_samples'] and relay['inaccurate_samples']:
                    tags.append('raw_relay_status_disagreement_requires_review')
                report['sides'][side]={'raw':raw,'relay':relay,'pose_match':pair,'diagnostic_tags':tags}
                failed=failed or bool(raw['failures'] or relay['failures'] or tags)
            report['result']='FAIL' if failed else 'PASS'
        print(json.dumps(report,sort_keys=True))
        del subscribers
        return 1 if failed else 0
    except KeyboardInterrupt:
        print('[PI05] ERROR: diagnostic interrupted',file=sys.stderr)
        return 1
    except Exception:
        print('[PI05] ERROR: diagnostic environment or ROS subscription failed',file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
