"""Pure state and home-tracking logic used by the hardware collector."""

from dataclasses import dataclass
from enum import Enum
import math


class Phase(str, Enum):
    IDLE = "idle"
    MANIPULATION = "manipulation"
    RETURN_HOME = "return_home"
    LOCKED = "locked"
    STOPPED = "stopped"


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DISCARD = "discard"


class SessionError(RuntimeError):
    pass


class EpisodeStateMachine:
    """Keep recording active until the return-home segment is complete."""

    def __init__(self):
        self.phase = Phase.IDLE
        self.requested_outcome = None
        self.task = ""
        self.started_at = None

    def start(self, task, now):
        if self.phase != Phase.IDLE:
            raise SessionError("an episode can only start from idle")
        task = task.strip()
        if not task:
            raise SessionError("task text must not be empty")
        self.task = task
        self.started_at = float(now)
        self.requested_outcome = None
        self.phase = Phase.MANIPULATION

    def request_return(self, outcome):
        if self.phase != Phase.MANIPULATION:
            raise SessionError("return can only start during manipulation")
        outcome = Outcome(outcome)
        # An operator failure mark is sticky. A later timer/success request
        # starts return-home but cannot silently reclassify the episode.
        if self.requested_outcome == Outcome.FAILURE and outcome != Outcome.DISCARD:
            outcome = Outcome.FAILURE
        self.requested_outcome = outcome
        self.phase = Phase.RETURN_HOME

    def mark_failure(self):
        if self.phase != Phase.MANIPULATION:
            raise SessionError("failure can only be marked during manipulation")
        self.requested_outcome = Outcome.FAILURE

    @property
    def marked_failed(self):
        return self.phase == Phase.MANIPULATION and self.requested_outcome == Outcome.FAILURE

    def complete_home(self):
        if self.phase != Phase.RETURN_HOME:
            raise SessionError("home completion is only valid while returning")
        outcome = self.requested_outcome
        self.phase = Phase.IDLE
        self.requested_outcome = None
        self.started_at = None
        return outcome

    def fail_home(self):
        if self.phase != Phase.RETURN_HOME:
            raise SessionError("home failure is only valid while returning")
        self.phase = Phase.LOCKED
        self.requested_outcome = Outcome.FAILURE

    def emergency_stop(self):
        self.phase = Phase.LOCKED
        self.requested_outcome = Outcome.FAILURE

    def stop(self):
        if self.phase not in (Phase.IDLE, Phase.LOCKED):
            raise SessionError("active episodes must return home before stopping")
        self.phase = Phase.STOPPED

    def duration_expired(self, now, duration):
        return (self.phase == Phase.MANIPULATION and self.started_at is not None and
                float(now) - self.started_at >= float(duration))

    @property
    def recording(self):
        return self.phase in (Phase.MANIPULATION, Phase.RETURN_HOME)


@dataclass
class HomeProgress:
    target: tuple
    tolerance: float = 0.02
    stable_seconds: float = 1.0
    stall_seconds: float = 5.0
    max_recoveries: int = 5
    best_error: float = math.inf
    last_error: float = math.inf
    last_progress_at: float = 0.0
    stable_since: float = None
    recoveries: int = 0
    recovery_pending: bool = False
    complete: bool = False

    def reset(self, now):
        self.best_error = math.inf
        self.last_error = math.inf
        self.last_progress_at = float(now)
        self.stable_since = None
        self.recoveries = 0
        self.recovery_pending = False
        self.complete = False

    def observe(self, positions, now):
        now = float(now)
        if len(positions) < 6:
            raise ValueError("home feedback must contain six joints")
        values = tuple(float(value) for value in positions[:6])
        if not all(math.isfinite(value) for value in values):
            raise ValueError("home feedback must be finite")
        self.last_error = max(abs(actual - expected)
                              for actual, expected in zip(values, self.target))
        if self.last_error < self.best_error - 0.002:
            self.best_error = self.last_error
            self.last_progress_at = now
        if self.last_error <= self.tolerance:
            self.stable_since = self.stable_since or now
            self.complete = now - self.stable_since >= self.stable_seconds
        else:
            self.stable_since = None
            self.complete = False
        return self.complete

    def needs_recovery(self, now):
        if self.complete or self.recovery_pending:
            return False
        return float(now) - self.last_progress_at >= self.stall_seconds

    def begin_recovery(self, now):
        if self.recoveries >= self.max_recoveries:
            raise SessionError("home motion exhausted recovery attempts")
        self.recoveries += 1
        self.recovery_pending = True
        self.last_progress_at = float(now)

    def finish_recovery(self, now, succeeded):
        self.recovery_pending = False
        self.last_progress_at = float(now)
        if not succeeded:
            raise SessionError("reset/enable recovery was rejected")


JOINT_NAMES = tuple("joint%d" % index for index in range(1, 7))
FEATURE_NAMES = tuple(
    ["left_%s" % name for name in JOINT_NAMES] + ["left_gripper"] +
    ["right_%s" % name for name in JOINT_NAMES] + ["right_gripper"])


def joint_vector(message):
    """Return the seven commanded/observed values, rejecting partial data."""
    values = tuple(float(value) for value in message.position)
    if len(values) < 7:
        raise ValueError("joint message must contain six joints and one gripper")
    values = values[:7]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("joint values must be finite")
    return values


def dual_vector(left, right):
    return tuple(joint_vector(left) + joint_vector(right))
