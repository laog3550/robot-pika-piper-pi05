#!/usr/bin/env python3
"""Run against an isolated ROS Master, with synthetic poses only."""
import os
import subprocess
import time
import threading


def main():
    import rospy
    import rosgraph
    from geometry_msgs.msg import PoseStamped
    from data_msgs.msg import LocalizationStatus
    uri = os.environ.get('ROS_MASTER_URI', '')
    if uri not in ('http://localhost:11331', 'http://127.0.0.1:11331'):
        raise RuntimeError('replay requires an isolated Master on localhost:11331')
    rospy.init_node('pi05_pika_input_replay', anonymous=True)
    seen = {'left': [], 'right': []}
    statuses = {'left': [], 'right': []}
    lock = threading.Lock()
    def callback(side, table, value):
        with lock:
            table[side].append(value)
    subs = []
    pubs = {}
    for side in seen:
        target = '/pi05/pika_input/' + side
        source = '/pi05/pika_input/raw/' + side
        subs.extend([
            rospy.Subscriber(target+'/pose', PoseStamped,
                lambda m, s=side: callback(s, seen, m.pose.position.x)),
            rospy.Subscriber(target+'/localization_status', LocalizationStatus,
                lambda m, s=side: callback(s, statuses, m.accurate)),
        ])
        pubs[side] = (rospy.Publisher(source+'/pose', PoseStamped, queue_size=10),
                      rospy.Publisher(source+'/localization_status', LocalizationStatus, queue_size=10))
    with open(os.devnull, 'wb') as sink:
        child = subprocess.Popen(['roslaunch','pi05_pika_input','pika_input_only.launch',
                                  'left:=true','right:=true','start_locator:=false'],
                                 stdout=sink, stderr=sink)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if all(p.get_num_connections() for pair in pubs.values() for p in pair):
                    break
                if child.poll() is not None:
                    raise RuntimeError('input launch exited')
                time.sleep(.1)
            else: raise RuntimeError('relay subscriptions did not appear')
            for _ in range(30):
                for side, x in (('left', 1.), ('right', 2.)):
                    pose = PoseStamped()
                    pose.header.stamp = rospy.Time.now()
                    pose.header.frame_id = 'synthetic_replay'
                    pose.pose.position.x = x
                    pose.pose.orientation.w = 1.
                    status = LocalizationStatus()
                    status.accurate = side == 'left'
                    pubs[side][0].publish(pose)
                    pubs[side][1].publish(status)
                time.sleep(.05)
            with lock:
                assert seen['left'] and set(seen['left']) == {1.}
                assert seen['right'] and set(seen['right']) == {2.}
                assert statuses['left'] and all(statuses['left'])
                assert statuses['right'] and not any(statuses['right'])
            publishers, subscribers, services = rosgraph.Master(rospy.get_name()).getSystemState()
            for topic, nodes in publishers + subscribers:
                if any(n.endswith('/side_input') for n in nodes):
                    assert topic == '/rosout' or topic.startswith('/pi05/pika_input/'), topic
            for service, nodes in services:
                if any(n.endswith('/side_input') for n in nodes):
                    assert service.endswith('/get_loggers') or service.endswith('/set_logger_level')
            print('Pika input-only replay: PASS (side isolation, status isolation, no control interfaces)')
        finally:
            child.terminate()
            try: child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    del subs


if __name__ == '__main__':
    main()
