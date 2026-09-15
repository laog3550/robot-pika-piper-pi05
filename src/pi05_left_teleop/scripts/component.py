#!/usr/bin/env python3
"""Run reviewed numerical components with left-only endpoints and official model."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', required=True, choices=('fk','ik','teleop'))
    args, remaining = parser.parse_known_args()
    mappings = dict(x.split(':=',1) for x in remaining if ':=' in x)
    if mappings.get('__ns',os.environ.get('ROS_NAMESPACE','')).rstrip('/') != '/left_arm/teleop':
        raise RuntimeError('left-only component namespace required')
    for source,target in {
        '/joint_states_single_l':'/joint_states_single_l',
        '/joint_states_gripper_l':'/joint_states_single_l',
        '/joint_states_l':'/left_arm/teleop/raw_target',
        '/pika_pose_l':'/pi05/pika_input/left/pose',
    }.items():
        if mappings.get(source) != target:
            raise RuntimeError('left teleoperation endpoint mapping missing')
    import rospkg
    packages = rospkg.RosPack()
    reviewed = Path(packages.get_path('pi05_teleop_replay'))/'scripts/replay_component.py'
    spec = importlib.util.spec_from_file_location('reviewed_components',str(reviewed))
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    scripts = Path(packages.get_path('pika_remote_piper'))/'scripts'
    for name,expected in baseline.UPSTREAM_HASHES.items():
        if hashlib.sha256((scripts/name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('numerical source differs from reviewed baseline')
    model = Path(packages.get_path('piper_description'))/'urdf/piper_description.urdf'
    if hashlib.sha256(model.read_bytes()).hexdigest() != baseline.URDF_SHA256:
        raise RuntimeError('reviewed official model required')
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[key] = '1'
    import pinocchio.visualize
    pinocchio.visualize.MeshcatVisualizer = baseline.HeadlessViewer
    filename = baseline.ROLES[args.role][1]
    sys.path.insert(0,str(scripts))
    sys.argv = [str(scripts/filename)]+remaining
    runpy.run_path(str(scripts/filename),run_name='__main__')


if __name__ == '__main__':
    main()
