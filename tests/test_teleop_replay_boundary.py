"""Check physical-output containment and startup guards for replay wiring."""
import os
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'src/pi05_teleop_replay'
BASE='/pi05/teleop_replay'


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.launch=ET.parse(str(PACKAGE/'launch/teleop_replay.launch')).getroot()

    def test_off_by_default_and_only_guarded_components(self):
        self.assertEqual(self.launch.find('arg').attrib,{'name':'start','default':'false'})
        nodes=self.launch.findall('.//node')
        self.assertEqual(len(nodes),9)
        self.assertTrue(all(n.get('pkg')=='pi05_teleop_replay' and n.get('type')=='replay_component.py' and n.get('required')=='true' for n in nodes))

    def test_feedback_and_filtered_output_separate(self):
        for group in self.launch.findall('./group/group'):
            ns=group.get('ns');s='l' if 'left_arm' in ns else 'r'
            mappings={n.get('from'):n.get('to') for n in group.findall('remap')}
            self.assertEqual(mappings['/joint_states_single_'+s],ns+'/feedback')
            self.assertEqual(mappings['/joint_states_gripper_'+s],ns+'/feedback')
            node=next(n for n in group.findall('node') if n.get('name')=='filter')
            self.assertEqual(node.find('remap').get('to'),ns+'/filtered_target')

    def test_contained_endpoints_and_no_driver_connection(self):
        for mapping in self.launch.findall('.//remap'):
            self.assertTrue(mapping.get('to').startswith((BASE+'/', '/pi05/pika_input/')))
            self.assertNotIn('joint_ctrl_raw',mapping.get('to'))
        for node in self.launch.findall('.//node'):
            if node.get('name')=='teleop':
                p=next(p for p in node.findall('param') if p.get('name')=='return_zero_position')
                self.assertEqual((p.get('value'),p.get('type')),('False','str'))

    def test_coordinator_actions_only_mock_services(self):
        coord=next(n for n in self.launch.findall('.//node') if n.get('name')=='coordinator')
        mappings={n.get('from'):n.get('to') for n in coord.findall('remap')}
        for side in ('left','right'):
            for service in ('enable','stop'):
                self.assertEqual(mappings['/'+side+'_arm/'+service+'_srv_raw'],BASE+'/mock/'+side+'/'+service)

    def test_wrong_master_rejected_before_importing_ros(self):
        env=dict(os.environ,ROS_MASTER_URI='http://localhost:11311')
        for role in ('fk','ik','teleop','filter','coordinator'):
            result=subprocess.run(['/usr/bin/python3',str(PACKAGE/'scripts/replay_component.py'),'--role',role],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'requires localhost Master',result.stderr)

    def test_naked_role_rejected_on_replay_master(self):
        env=dict(os.environ,ROS_MASTER_URI='http://localhost:11333',ROS_NAMESPACE='')
        for role in ('fk','ik','teleop','filter','coordinator'):
            result=subprocess.run(['/usr/bin/python3',str(PACKAGE/'scripts/replay_component.py'),'--role',role],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b'namespace',result.stderr)


if __name__=='__main__':
    unittest.main()
