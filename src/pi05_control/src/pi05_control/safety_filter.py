"""Deterministic, ROS-independent safety filter for one PI05 arm."""

from __future__ import division

import math


class FilterConfig(object):
    def __init__(
        self,
        arm_alpha=0.35,
        arm_deadband_rad=0.002,
        max_arm_step_rad=0.012,
        gripper_alpha=0.25,
        gripper_deadband_m=0.0015,
        max_gripper_step_m=0.0006,
        speed_percent=15.0,
        command_timeout_s=0.35,
        feedback_timeout_s=0.35,
        localization_timeout_s=0.35,
        authorization_timeout_s=0.25,
    ):
        self.arm_alpha = float(arm_alpha)
        self.arm_deadband_rad = float(arm_deadband_rad)
        self.max_arm_step_rad = float(max_arm_step_rad)
        self.gripper_alpha = float(gripper_alpha)
        self.gripper_deadband_m = float(gripper_deadband_m)
        self.max_gripper_step_m = float(max_gripper_step_m)
        self.speed_percent = float(speed_percent)
        self.command_timeout_s = float(command_timeout_s)
        self.feedback_timeout_s = float(feedback_timeout_s)
        self.localization_timeout_s = float(localization_timeout_s)
        self.authorization_timeout_s = float(authorization_timeout_s)
        self.validate()

    def validate(self):
        for name in ("arm_alpha", "gripper_alpha"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0 or value > 1.0:
                raise ValueError("{} must be finite and in (0, 1]".format(name))
        for name in (
            "arm_deadband_rad",
            "gripper_deadband_m",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError("{} must be finite and non-negative".format(name))
        for name in (
            "max_arm_step_rad",
            "max_gripper_step_m",
            "command_timeout_s",
            "feedback_timeout_s",
            "localization_timeout_s",
            "authorization_timeout_s",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError("{} must be finite and positive".format(name))
        if not math.isfinite(self.speed_percent) or not 0.0 < self.speed_percent <= 100.0:
            raise ValueError("speed_percent must be finite and in (0, 100]")


class FilterOutput(object):
    def __init__(self, names, positions, speed_percent):
        self.names = list(names)
        self.positions = list(positions)
        self.speed_percent = float(speed_percent)


class ArmSafetyFilter(object):
    STATES = (
        "DISCONNECTED",
        "DISABLED",
        "ENABLED_HOLD",
        "TELEOP_ACTIVE",
        "FAULT_LATCHED",
    )

    def __init__(self, side, config=None):
        if side not in ("left", "right"):
            raise ValueError("side must be 'left' or 'right'")
        self.side = side
        self.config = config or FilterConfig()
        self.authorized = False
        self.localization_accurate = False
        self.ik_over_limit = None
        self.session_active = False
        self.fault_reason = ""
        self.feedback = None
        self.feedback_names = None
        self.last_feedback_time = None
        self.last_localization_time = None
        self.last_command_time = None
        self.last_authorization_time = None
        self.last_time = None
        self.filtered = None

    @staticmethod
    def _valid_positions(values):
        return len(values) >= 7 and all(math.isfinite(float(value)) for value in values[:7])

    @staticmethod
    def _valid_names(names):
        if not names:
            return True
        selected = list(names[:7])
        return len(selected) == 7 and all(selected) and len(set(selected)) == 7

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
        self.session_active = False
        self.last_command_time = None
        self.filtered = list(self.feedback) if self.feedback is not None else None

    def _feedback_fresh(self, now):
        return (
            self.feedback is not None
            and self.last_feedback_time is not None
            and 0.0 <= now - self.last_feedback_time <= self.config.feedback_timeout_s
        )

    def _localization_fresh(self, now):
        return (
            self.localization_accurate
            and self.last_localization_time is not None
            and 0.0 <= now - self.last_localization_time
            <= self.config.localization_timeout_s
        )

    def update_feedback(self, positions, names, now):
        if not self._observe_time(now):
            return False
        if not self._valid_positions(positions) or not self._valid_names(names):
            self.feedback = None
            self.last_feedback_time = None
            if self.authorized:
                self._latch("invalid feedback")
            return False
        self.feedback = [float(value) for value in positions[:7]]
        self.feedback_names = list(names[:7]) if names else ["joint{}".format(i) for i in range(1, 8)]
        self.last_feedback_time = float(now)
        if not self.authorized or not self.session_active:
            self.filtered = list(self.feedback)
        return True

    def update_localization(self, accurate, now):
        if not self._observe_time(now):
            return False
        self.last_localization_time = float(now)
        self.localization_accurate = bool(accurate)
        if not self.localization_accurate:
            self.session_active = False
            self.last_command_time = None
            if self.authorized:
                self._latch("localization invalid")
            return False
        return True

    def update_arm_status(self, over_limit, now):
        if not self._observe_time(now):
            return False
        self.ik_over_limit = bool(over_limit)
        if self.ik_over_limit:
            self.session_active = False
            self.last_command_time = None
            if self.authorized:
                self._latch("IK limit exceeded")
            return False
        return True

    def set_authorized(self, authorized, now):
        if not self._observe_time(now):
            return False
        requested = bool(authorized)
        if requested == self.authorized:
            if requested and not self.fault_reason:
                self.last_authorization_time = float(now)
            return not requested or not self.fault_reason
        self.authorized = False
        self.last_authorization_time = None
        self.session_active = False
        self.last_command_time = None
        self.filtered = list(self.feedback) if self.feedback is not None else None
        if not requested:
            return True
        now = float(now)
        if self.fault_reason:
            return False
        if not self._feedback_fresh(now):
            self._latch("authorization rejected: feedback unavailable")
            return False
        if not self._localization_fresh(now):
            self._latch("authorization rejected: localization unavailable")
            return False
        if self.ik_over_limit is not False:
            self._latch("authorization rejected: IK status unavailable")
            return False
        self.authorized = True
        self.last_authorization_time = now
        return True

    def update_teleop_status(self, fail, quit_session, now):
        if not self._observe_time(now):
            return False
        if fail:
            self.session_active = False
            self.last_command_time = None
            self.filtered = list(self.feedback) if self.feedback is not None else None
            return False
        if quit_session:
            self.session_active = False
            self.last_command_time = None
            self.filtered = list(self.feedback) if self.feedback is not None else None
            return True
        if self.fault_reason or not self.authorized:
            return False
        now = float(now)
        if not self._feedback_fresh(now):
            self._latch("feedback unavailable at session start")
            return False
        if not self._localization_fresh(now):
            self._latch("localization unavailable at session start")
            return False
        if self.ik_over_limit is not False:
            self._latch("IK status unavailable at session start")
            return False
        if not self.session_active:
            self.filtered = list(self.feedback)
            self.last_command_time = now
            self.session_active = True
        return True

    @staticmethod
    def _condition(previous, target, alpha, deadband, maximum_step):
        delta = target - previous
        if abs(delta) <= deadband:
            return previous
        proposed = previous + alpha * delta
        step = max(-maximum_step, min(maximum_step, proposed - previous))
        return previous + step

    def command(self, positions, names, now):
        if not self._observe_time(now):
            return None
        now = float(now)
        if self.fault_reason or not self.authorized or not self.session_active:
            return None
        if not self._feedback_fresh(now):
            self._latch("feedback timed out")
            return None
        if not self._localization_fresh(now):
            self._latch("localization timed out")
            return None
        if self.ik_over_limit is not False:
            self._latch("IK status invalid")
            return None
        if not self._valid_positions(positions) or not self._valid_names(names):
            self._latch("invalid command")
            return None
        target = [float(value) for value in positions[:7]]
        if self.filtered is None:
            self._latch("missing feedback baseline")
            return None
        for index in range(6):
            self.filtered[index] = self._condition(
                self.filtered[index],
                target[index],
                self.config.arm_alpha,
                self.config.arm_deadband_rad,
                self.config.max_arm_step_rad,
            )
        self.filtered[6] = self._condition(
            self.filtered[6],
            target[6],
            self.config.gripper_alpha,
            self.config.gripper_deadband_m,
            self.config.max_gripper_step_m,
        )
        self.last_command_time = now
        output_names = list(names[:7]) if names else list(self.feedback_names)
        return FilterOutput(output_names, self.filtered, self.config.speed_percent)

    def watchdog(self, now):
        if not self._observe_time(now):
            return False
        now = float(now)
        if (
            self.authorized
            and self.last_authorization_time is not None
            and now - self.last_authorization_time > self.config.authorization_timeout_s
        ):
            self._latch("authorization heartbeat timed out")
            return False
        if self.authorized and not self._feedback_fresh(now):
            self._latch("feedback timed out")
            return False
        if self.authorized and not self._localization_fresh(now):
            self._latch("localization timed out")
            return False
        if (
            self.session_active
            and self.last_command_time is not None
            and now - self.last_command_time > self.config.command_timeout_s
        ):
            self._latch("command timed out")
            return False
        return not self.fault_reason

    def reset_fault(self, now):
        if not self._observe_time(now) or self.authorized:
            return False
        now = float(now)
        if not self._feedback_fresh(now) or not self._localization_fresh(now):
            return False
        if self.ik_over_limit is not False:
            return False
        self.fault_reason = ""
        self.session_active = False
        self.last_command_time = None
        self.filtered = list(self.feedback)
        return True

    def state(self, now):
        now = float(now)
        if self.fault_reason:
            return "FAULT_LATCHED"
        if not self._feedback_fresh(now):
            return "DISCONNECTED"
        if not self.authorized:
            return "DISABLED"
        if self.session_active:
            return "TELEOP_ACTIVE"
        return "ENABLED_HOLD"
