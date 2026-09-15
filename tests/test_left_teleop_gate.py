import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('left_gate',str(ROOT/'src/pi05_left_teleop/scripts/safety_gate.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GateTests(unittest.TestCase):
    def sample(self,g,t,positions=None):
        g.observe_feedback(positions or [0.0]*7,t)
        g.localization_ok=True;g.localization_time=t
        g.ik_ok=True;g.ik_time=t

    def ready(self):
        g=module.SafetyGate();self.sample(g,0)
        self.assertTrue(g.begin(0));self.assertTrue(g.enabled(0))
        for i in range(1,42):
            self.sample(g,i*.05);g.tick(i*.05)
        self.assertEqual(g.phase,'READY')
        return g

    def test_no_input_no_enable(self):
        self.assertFalse(module.SafetyGate().begin(0))

    def test_initial_incomplete_feedback_waits_for_valid_input(self):
        g=module.SafetyGate()
        self.assertFalse(g.observe_feedback([],0))
        self.assertEqual(g.phase,'DISARMED')
        self.sample(g,.1)
        self.assertTrue(g.begin(.1))

    def test_invalid_feedback_after_enable_is_latched(self):
        g=self.ready()
        self.assertFalse(g.observe_feedback([],2.1))
        self.sample(g,2.2)
        self.assertEqual(g.phase,'FAULT')

    def test_blockers_distinguish_state_and_input(self):
        g=module.SafetyGate()
        self.assertIn('feedback missing',g.blockers(0))
        self.sample(g,0)
        self.assertEqual(g.blockers(0),[])
        g.fail('operator stop')
        self.assertIn('phase=FAULT: operator stop',g.blockers(0))

    def test_no_output_before_enable(self):
        g=module.SafetyGate();self.sample(g,0)
        self.assertFalse(g.accept_target([0.0]*7,0))

    def test_settling_disallows_output(self):
        g=module.SafetyGate();self.sample(g,0);g.begin(0);g.enabled(0)
        self.assertFalse(g.accept_target([0.0]*7,0))

    def test_enable_drift_latched(self):
        g=module.SafetyGate();self.sample(g,0);g.begin(0)
        self.sample(g,.1,[0,0,.0024,0,0,0,0])
        self.assertEqual(g.phase,'FAULT');self.assertFalse(g.enabled(.1))

    def test_valid_small_target(self):
        g=self.ready();self.assertTrue(g.accept_target([.005,0,0,0,0,0,0],2.05))

    def test_target_envelope(self):
        g=self.ready();self.assertFalse(g.accept_target([.021,0,0,0,0,0,0],2.05))
        self.assertEqual(g.phase,'FAULT')

    def test_tracking_difference(self):
        g=self.ready();self.assertFalse(g.accept_target([.011,0,0,0,0,0,0],2.05))

    def test_localization_loss_no_automatic_recovery(self):
        g=self.ready();g.localization_ok=False;self.assertFalse(g.tick(2.1))
        self.sample(g,2.2);self.assertFalse(g.tick(2.2));self.assertFalse(g.begin(2.2))

    def test_wall_clock_stale(self):
        g=self.ready();self.assertFalse(g.tick(2.5));self.assertEqual(g.phase,'FAULT')

    def test_nonfinite(self):
        g=self.ready();self.assertFalse(g.accept_target([float('nan')]*7,2.05))

    def test_sparse_settling(self):
        g=module.SafetyGate();self.sample(g,0);g.begin(0);g.enabled(0)
        self.sample(g,2.1);self.assertFalse(g.tick(2.1));self.assertEqual(g.phase,'FAULT')

    def test_launch_default_off_left_only(self):
        root=ET.parse(ROOT/'src/pi05_left_teleop/launch/left_teleop.launch').getroot()
        args={e.get('name'):e.get('default') for e in root.findall('arg')}
        self.assertEqual(args['start'],'false');self.assertEqual(args['connect_driver'],'false')
        text=ET.tostring(root).decode();self.assertNotIn('right',text)
        self.assertIn('5.0',text);self.assertIn('return_zero_position',text)


if __name__=='__main__':unittest.main()
