#!/usr/bin/env python3
"""Check ROS startup conflicts without starting nodes or contacting hardware."""
import argparse


def check_start(side, state):
    publishers, subscribers, services = state
    required = ('left', 'right') if side == 'dual' else (side,)
    other = {'left': 'right', 'right': 'left'}.get(side)
    nodes = {node for _, owners in publishers + subscribers + services for node in owners}
    readonly_nodes = {"/" + item + "_arm/piper_readonly_feedback" for item in required}
    conflicts = set()
    for node in nodes:
        # An explicitly namespaced opposite arm can keep running. Legacy nodes
        # without an arm namespace cannot be assigned to a side reliably.
        if node in readonly_nodes:
            continue
        if other and node.startswith('/' + other + '_arm/'):
            continue
        if ('piper' in node.lower() or 'teleop' in node.lower()
                or any(node.startswith('/' + item + '_arm/') for item in required)):
            conflicts.add(node)
    # Detect command owners even when their node names do not identify a driver.
    for topic, owners in publishers + subscribers + services:
        if owners and all(node in readonly_nodes for node in owners) and any(
                topic in ('/' + item + '_arm/joint_states_raw',
                          '/' + item + '_arm/piper_readonly_feedback/get_loggers',
                          '/' + item + '_arm/piper_readonly_feedback/set_logger_level')
                for item in required):
            continue
        if any(topic.startswith('/' + item + '_arm/') or topic in (
                '/joint_states_single_' + suffix,
                '/joint_states_' + suffix,
                '/teleop_trigger_' + suffix,
                '/piper_IK_' + suffix + '/ctrl_end_pose',
                '/piper_FK_' + suffix + '/urdf_end_pose_orient',
        ) for item in required for suffix in ({'left': 'l', 'right': 'r'}[item],)):
            conflicts.update(owners)
    if conflicts:
        raise ValueError('Stop conflicting arm drivers/teleoperation before starting: '
                         + ', '.join(sorted(conflicts)))
    missing = [item for item in required if not any(
        topic == '/pi05/pika_input/' + item + '/pose' and owners
        for topic, owners in publishers)]
    if missing:
        raise ValueError('Start Pika input-only first; missing pose: ' + ','.join(missing))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('side', choices=('left', 'right', 'dual'))
    args = parser.parse_args()
    import rosgraph
    try:
        state = rosgraph.Master('/pi05_teleop_start_check').getSystemState()
        check_start(args.side, state)
    except (ValueError, OSError, rosgraph.MasterException) as error:
        parser.exit(1, 'Teleoperation startup check failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
