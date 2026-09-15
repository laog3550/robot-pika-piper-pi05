#!/usr/bin/env python3
"""Run the pinned vendor teleoperation components without opening Meshcat."""
import argparse
import os
from pathlib import Path
import runpy
import sys


class HeadlessViewer:
    """Satisfy the vendor solver's viewer API on the headless PI05 host."""

    def __init__(self, *args, **kwargs):
        self.viewer = self

    def __getitem__(self, _key):
        return self

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', required=True, choices=('fk','ik','teleop'))
    parser.add_argument('--side', required=True, choices=('left', 'right'))
    args, remaining = parser.parse_known_args()
    import rospkg
    packages = rospkg.RosPack()
    scripts = Path(packages.get_path('pika_remote_piper'))/'scripts'
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[key] = '1'
    import pinocchio.visualize
    pinocchio.visualize.MeshcatVisualizer = HeadlessViewer
    filename = {'fk': 'piper_FK.py', 'ik': 'piper_IK.py',
                'teleop': 'teleop_piper_publish.py'}[args.role]
    sys.path.insert(0,str(scripts))
    sys.argv = [str(scripts/filename)]+remaining
    runpy.run_path(str(scripts/filename),run_name='__main__')


if __name__ == '__main__':
    main()
