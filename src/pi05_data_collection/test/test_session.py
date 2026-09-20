#!/usr/bin/env python3

import unittest

from pi05_data_collection.session import (
    EpisodeStateMachine, HomeProgress, Outcome, Phase, SessionError)


class EpisodeStateMachineTest(unittest.TestCase):
    def test_success_does_not_finish_until_home_is_confirmed(self):
        machine = EpisodeStateMachine()
        machine.start("put the apple in the basket", 10.0)
        machine.request_return(Outcome.SUCCESS)
        self.assertEqual(machine.phase, Phase.RETURN_HOME)
        self.assertTrue(machine.recording)
        self.assertEqual(machine.task, "put the apple in the basket")
        self.assertEqual(machine.complete_home(), Outcome.SUCCESS)
        self.assertEqual(machine.phase, Phase.IDLE)
        self.assertFalse(machine.recording)

    def test_timeout_only_requests_return(self):
        machine = EpisodeStateMachine()
        machine.start("task", 1.0)
        self.assertFalse(machine.duration_expired(30.9, 30.0))
        self.assertTrue(machine.duration_expired(31.0, 30.0))
        self.assertEqual(machine.phase, Phase.MANIPULATION)

    def test_timeout_is_success_without_failure_mark(self):
        machine = EpisodeStateMachine()
        machine.start("task", 0.0)
        machine.request_return(Outcome.SUCCESS)
        self.assertEqual(machine.complete_home(), Outcome.SUCCESS)

    def test_operator_failure_mark_continues_until_timer_and_is_sticky(self):
        machine = EpisodeStateMachine()
        machine.start("task", 0.0)
        machine.mark_failure()
        self.assertEqual(machine.phase, Phase.MANIPULATION)
        self.assertTrue(machine.recording)
        self.assertTrue(machine.marked_failed)
        self.assertTrue(machine.duration_expired(30.0, 30.0))
        machine.request_return(Outcome.SUCCESS)
        self.assertEqual(machine.phase, Phase.RETURN_HOME)
        self.assertEqual(machine.complete_home(), Outcome.FAILURE)

    def test_discard_overrides_operator_failure_mark(self):
        machine = EpisodeStateMachine()
        machine.start("task", 0.0)
        machine.mark_failure()
        machine.request_return(Outcome.DISCARD)
        self.assertEqual(machine.complete_home(), Outcome.DISCARD)

    def test_normal_end_keys_are_invalid_while_returning(self):
        machine = EpisodeStateMachine()
        machine.start("task", 0.0)
        machine.request_return(Outcome.FAILURE)
        with self.assertRaises(SessionError):
            machine.request_return(Outcome.DISCARD)

    def test_home_failure_locks_next_episode(self):
        machine = EpisodeStateMachine()
        machine.start("task", 0.0)
        machine.request_return(Outcome.SUCCESS)
        machine.fail_home()
        self.assertEqual(machine.phase, Phase.LOCKED)
        with self.assertRaises(SessionError):
            machine.start("another", 1.0)


class HomeProgressTest(unittest.TestCase):
    def test_requires_continuous_stability(self):
        tracker = HomeProgress((0.0,) * 6, tolerance=0.02, stable_seconds=1.0)
        tracker.reset(0.0)
        self.assertFalse(tracker.observe((0.01,) * 6, 0.1))
        self.assertFalse(tracker.observe((0.03,) * 6, 0.5))
        self.assertFalse(tracker.observe((0.01,) * 6, 1.0))
        self.assertTrue(tracker.observe((0.01,) * 6, 2.0))

    def test_recovery_is_bounded(self):
        tracker = HomeProgress((0.0,) * 6, stall_seconds=1.0, max_recoveries=1)
        tracker.reset(0.0)
        tracker.observe((1.0,) * 6, 0.0)
        self.assertTrue(tracker.needs_recovery(1.0))
        tracker.begin_recovery(1.0)
        tracker.finish_recovery(1.1, True)
        self.assertTrue(tracker.needs_recovery(2.2))
        with self.assertRaises(SessionError):
            tracker.begin_recovery(2.2)


if __name__ == "__main__":
    unittest.main()
