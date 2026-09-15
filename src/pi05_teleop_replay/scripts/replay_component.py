#!/usr/bin/env python3
"""Run existing software components on the isolated synthetic replay Master."""
import argparse
import hashlib
import os
from pathlib import Path
import runpy
import sys

MASTER = 'http://localhost:11333'
BASE = '/pi05/teleop_replay'
URDF_SHA256 = 'c1a5c29ae9b91160557ed02bddd47365a71f0eb1653abb4997eb34f124021486'
UPSTREAM_HASHES = {
    'teleop_piper_publish.py': 'bb1a4e37a2694471cfc0bc51fc58295907205306fe374ea87330a1653f3fbac2',
    'piper_FK.py': '6045eef0ce46a765ecb0cd38288ecf6b8dee1858faa6a11edd92952bfc53c63a',
    'piper_IK.py': '7376f88d564d66afec3caeb88ddde78ae20f983b09cdbeaf1ecafeebdde20206',
    'forward_inverse_kinematics.py': '4e1821e599ebaa0d69b9faab086f9264b13590c2e4806cf7f0b329e3ef9269d3',
    'transformations.py': '309f8d1c276d0191a68bfc3e5b9f0b94276843e62f1f72655410649acab2e36b',
}
ROLES = {
    'teleop': ('pika_remote_piper', 'teleop_piper_publish.py'),
    'fk': ('pika_remote_piper', 'piper_FK.py'),
    'ik': ('pika_remote_piper', 'piper_IK.py'),
    'filter': ('pi05_control', 'arm_safety_filter_node.py'),
    'coordinator': ('pi05_control', 'dual_arm_safety_coordinator_node.py'),
}


class HeadlessViewer:
    """Suppress only upstream Meshcat rendering/server/browser operations."""
    def __init__(self, *args, **kwargs):
        self.viewer = self

    def __getitem__(self, key):
        return self

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=ROLES)
    args, remaining = parser.parse_known_args()
    # Check before importing ROS/upstream or starting any component.
    if os.environ.get('ROS_MASTER_URI') != MASTER:
        raise RuntimeError('Synthetic replay requires localhost Master on port 11333')
    mappings = dict(item.split(':=', 1) for item in remaining if ':=' in item)
    namespace = mappings.get('__ns', os.environ.get('ROS_NAMESPACE', '')).rstrip('/')
    if args.role == 'coordinator':
        if namespace != BASE:
            raise RuntimeError('Coordinator requires the contained replay namespace')
        for side in ('left', 'right'):
            for service in ('enable', 'stop'):
                if mappings.get('/'+side+'_arm/'+service+'_srv_raw') != BASE+'/mock/'+side+'/'+service:
                    raise RuntimeError('Coordinator actions must target synthetic services')
    else:
        sides={BASE+'/left_arm':'left',BASE+'/right_arm':'right'}
        if namespace not in sides:
            raise RuntimeError('Component requires a contained replay arm namespace')
        side=sides[namespace]
        suffix={'left':'l','right':'r'}[side]
        required={
            '/joint_states_single_'+suffix:namespace+'/feedback',
            '/joint_states_gripper_'+suffix:(namespace+'/filtered_target'
                if args.role=='filter' else namespace+'/feedback'),
        }
        if args.role in ('teleop','ik'):
            required['/joint_states_'+suffix]=namespace+'/raw_target'
        if args.role=='filter':
            required['/joint_states_gripper_raw_'+suffix]=namespace+'/raw_target'
            required['/pika_localization_status_'+suffix]='/pi05/pika_input/'+side+'/localization_status'
        for source,target in required.items():
            if mappings.get(source)!=target:
                raise RuntimeError('Component endpoint escaped replay mapping')
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    import rospkg
    package, filename = ROLES[args.role]
    scripts = Path(rospkg.RosPack().get_path(package)) / 'scripts'
    if package == 'pika_remote_piper':
        for name, expected in UPSTREAM_HASHES.items():
            if hashlib.sha256((scripts / name).read_bytes()).hexdigest() != expected:
                raise RuntimeError('Upstream replay source differs from reviewed baseline')
        model = Path(rospkg.RosPack().get_path('piper_description')) / 'urdf/piper_description.urdf'
        if hashlib.sha256(model.read_bytes()).hexdigest() != URDF_SHA256:
            raise RuntimeError('Replay requires the reviewed official Piper URDF; old install model rejected')
        # The upstream numerical solver remains unchanged. Its mandatory viewer
        # otherwise starts a server/browser and refers to absent frame IDs.
        import pinocchio.visualize
        pinocchio.visualize.MeshcatVisualizer = HeadlessViewer
    sys.path.insert(0, str(scripts))
    sys.argv = [str(scripts / filename)] + remaining
    runpy.run_path(str(scripts / filename), run_name='__main__')


if __name__ == '__main__':
    main()
