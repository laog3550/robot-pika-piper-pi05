"""ROS-independent coordination state for the PI05 dual-arm safety boundary."""

import math


SIDES = ("left", "right")
FILTER_STATES = (
    "DISCONNECTED",
    "DISABLED",
    "ENABLED_HOLD",
    "TELEOP_ACTIVE",
    "FAULT_LATCHED",
)


class CoordinatorConfig(object):
    def __init__(self, status_timeout_s=0.35, authorization_ack_timeout_s=0.5,
                 session_sync_timeout_s=0.2):
        self.status_timeout_s = float(status_timeout_s)
        self.authorization_ack_timeout_s = float(authorization_ack_timeout_s)
        self.session_sync_timeout_s = float(session_sync_timeout_s)
        for name in (
            "status_timeout_s",
            "authorization_ack_timeout_s",
            "session_sync_timeout_s",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("{} must be finite and positive".format(name))


class SideSnapshot(object):
    def __init__(self):
        self.filter_time = None
        self.filter_state = "DISCONNECTED"
        self.filter_level = 1
        self.filter_message = "not received"
        self.filter_authorized = False
        self.feedback_fresh = False
        self.localization_fresh = False
        self.ik_over_limit = None
        self.driver_time = None
        self.driver_fault = False
        self.driver_message = "not received"


class DualArmSafetyCoordinator(object):
    def __init__(self, config=None):
        self.config = config or CoordinatorConfig()
        self.sides = {side: SideSnapshot() for side in SIDES}
        self.authorized = False
        self.enabled_at = None
        self.fault_reason = ""
        self.last_time = None
        self.session_mismatch_since = None

    def _observe_time(self, now):
        now = float(now)
        if not math.isfinite(now):
            self._latch("non-finite clock")
            return False
        if self.last_time is not None and now < self.last_time:
            self._latch("clock moved backwards")
            self.last_time = now
            return False
        self.last_time = now
        return True

    def _latch(self, reason):
        if not self.fault_reason:
            self.fault_reason = str(reason)

    def latch_fault(self, reason, now):
        if not self._observe_time(now):
            return False
        self._latch(reason)
        return False

    @staticmethod
    def _side(side):
        if side not in SIDES:
            raise ValueError("side must be 'left' or 'right'")
        return side

    def update_filter(self, side, state, level, message, authorized,
                      feedback_fresh, localization_fresh, ik_over_limit, now):
        side = self._side(side)
        if not self._observe_time(now):
            return False
        snapshot = self.sides[side]
        snapshot.filter_time = float(now)
        snapshot.filter_level = int(level)
        snapshot.filter_message = str(message)
        snapshot.filter_authorized = bool(authorized)
        snapshot.feedback_fresh = bool(feedback_fresh)
        snapshot.localization_fresh = bool(localization_fresh)
        snapshot.ik_over_limit = ik_over_limit
        if state not in FILTER_STATES:
            snapshot.filter_state = "DISCONNECTED"
            self._latch("{} filter reported an invalid state".format(side))
            return False
        snapshot.filter_state = state
        if snapshot.filter_level >= 2 or state == "FAULT_LATCHED":
            self._latch("{} filter fault: {}".format(side, snapshot.filter_message))
            return False
        return not self.fault_reason

    def update_driver(self, side, fault, message, now):
        side = self._side(side)
        if not self._observe_time(now):
            return False
        snapshot = self.sides[side]
        snapshot.driver_time = float(now)
        snapshot.driver_fault = bool(fault)
        snapshot.driver_message = str(message)
        if snapshot.driver_fault:
            self._latch("{} driver fault: {}".format(side, snapshot.driver_message))
            return False
        return not self.fault_reason

    def _fresh(self, stamp, now):
        return stamp is not None and 0.0 <= now - stamp <= self.config.status_timeout_s

    def _prerequisites_ready(self, now, ignore_fault=False):
        now = float(now)
        if self.authorized or (self.fault_reason and not ignore_fault):
            return False
        for snapshot in self.sides.values():
            if not self._fresh(snapshot.filter_time, now):
                return False
            if not self._fresh(snapshot.driver_time, now):
                return False
            if snapshot.filter_state != "DISABLED" or snapshot.filter_level >= 2:
                return False
            if snapshot.filter_authorized:
                return False
            if not snapshot.feedback_fresh or not snapshot.localization_fresh:
                return False
            if snapshot.ik_over_limit is not False or snapshot.driver_fault:
                return False
        return True

    def can_enable(self, now):
        if not self._observe_time(now):
            return False
        return self._prerequisites_ready(float(now))

    def mark_enabled(self, now):
        if not self._observe_time(now):
            return False
        now = float(now)
        if not self._prerequisites_ready(now):
            self._latch("enable prerequisites changed during transition")
            return False
        self.authorized = True
        self.enabled_at = now
        self.session_mismatch_since = None
        return True

    def deauthorize(self, now):
        if not self._observe_time(now):
            return False
        self.authorized = False
        self.enabled_at = None
        self.session_mismatch_since = None
        return True

    def watchdog(self, now):
        if not self._observe_time(now):
            return False
        now = float(now)
        if not self.authorized:
            return not self.fault_reason
        for side, snapshot in self.sides.items():
            if not self._fresh(snapshot.filter_time, now):
                self._latch("{} filter status timed out".format(side))
                return False
            if not self._fresh(snapshot.driver_time, now):
                self._latch("{} driver status timed out".format(side))
                return False
            if snapshot.driver_fault or snapshot.filter_level >= 2:
                self._latch("{} status fault".format(side))
                return False
        if now - self.enabled_at > self.config.authorization_ack_timeout_s:
            for side, snapshot in self.sides.items():
                if not snapshot.filter_authorized or snapshot.filter_state not in (
                    "ENABLED_HOLD", "TELEOP_ACTIVE"
                ):
                    self._latch("{} filter did not acknowledge authorization".format(side))
                    return False

        states = {snapshot.filter_state for snapshot in self.sides.values()}
        mismatch = states == {"ENABLED_HOLD", "TELEOP_ACTIVE"}
        if mismatch:
            if self.session_mismatch_since is None:
                self.session_mismatch_since = now
            elif now - self.session_mismatch_since > self.config.session_sync_timeout_s:
                self._latch("left/right teleoperation session mismatch")
                return False
        else:
            self.session_mismatch_since = None
        return not self.fault_reason

    def reset_fault(self, now):
        if not self._observe_time(now) or self.authorized:
            return False
        now = float(now)
        if not self._prerequisites_ready(now, ignore_fault=True):
            return False
        self.fault_reason = ""
        self.session_mismatch_since = None
        return True

    def state(self, now):
        now = float(now)
        if self.fault_reason:
            return "FAULT_LATCHED"
        if self.authorized:
            states = {snapshot.filter_state for snapshot in self.sides.values()}
            if states == {"TELEOP_ACTIVE"}:
                return "TELEOP_ACTIVE"
            return "ENABLED_HOLD"
        if self._prerequisites_ready(now):
            return "READY"
        return "DISABLED"
