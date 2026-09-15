"""ROS-independent guards for single-arm low-speed hardware acceptance."""

import math
import pathlib
import re


SIDES = ("left", "right")
JOINT_COUNT = 6
POSITION_COUNT = 7
MAX_ENABLE_SHIFT_RAD = 0.002
MOTION_CONFIRMATION_SAMPLES = 3
NON_SELECTED_DRIFT_LIMIT_RAD = 0.002
SINGLE_SAMPLE_HARD_DRIFT_RAD = 0.010
CLEARANCE_COMMON = (
    ("PI05_S12_INCIDENT_REVIEW", "pass"),
    ("PI05_S12_FALL_ARREST_SUPPORT", "pass"),
    ("PI05_S12_HARDWARE_ESTOP", "pass"),
    ("PI05_S12_TWO_PERSON_TEAM", "yes"),
)
PIPER_FIRMWARE_RE = re.compile(r"^S-V([0-9]+)\.([0-9]+)-([0-9]+)$")


class AcceptanceConfig(object):
    """Hard limits for the deliberately small S12 acceptance motion."""

    def __init__(self, side, joint, delta_rad=0.005, speed_percent=5.0,
                 baseline_samples=20, baseline_tolerance_rad=0.0005):
        if side not in SIDES:
            raise ValueError("side must be 'left' or 'right'")
        if not isinstance(joint, int) or isinstance(joint, bool) or not 1 <= joint <= 6:
            raise ValueError("joint must be an integer in [1, 6]")
        self.side = side
        self.joint = joint
        self.delta_rad = float(delta_rad)
        self.speed_percent = float(speed_percent)
        self.baseline_samples = int(baseline_samples)
        self.baseline_tolerance_rad = float(baseline_tolerance_rad)
        if not math.isfinite(self.delta_rad) or not 0.0 < abs(self.delta_rad) <= 0.005:
            raise ValueError("absolute delta_rad must be finite and in (0, 0.005]")
        if not math.isfinite(self.speed_percent) or not 0.0 < self.speed_percent <= 5.0:
            raise ValueError("speed_percent must be finite and in (0, 5]")
        if self.baseline_samples < 3:
            raise ValueError("baseline_samples must be at least 3")
        if (not math.isfinite(self.baseline_tolerance_rad)
                or self.baseline_tolerance_rad <= 0.0):
            raise ValueError("baseline_tolerance_rad must be finite and positive")


class StableBaseline(object):
    """Accept only stable feedback sampled after an explicit recovery epoch."""

    def __init__(self, sample_count=20, tolerance_rad=0.0005):
        self.sample_count = int(sample_count)
        self.tolerance_rad = float(tolerance_rad)
        if self.sample_count < 3:
            raise ValueError("sample_count must be at least 3")
        if not math.isfinite(self.tolerance_rad) or self.tolerance_rad <= 0.0:
            raise ValueError("tolerance_rad must be finite and positive")
        self.recovery_time = None
        self.samples = []

    def begin_after_recovery(self, recovery_time):
        recovery_time = float(recovery_time)
        if not math.isfinite(recovery_time):
            raise ValueError("recovery_time must be finite")
        self.recovery_time = recovery_time
        self.samples = []

    @staticmethod
    def _positions(values):
        if len(values) < POSITION_COUNT:
            raise ValueError("feedback must contain at least seven positions")
        selected = [float(value) for value in values[:POSITION_COUNT]]
        if not all(math.isfinite(value) for value in selected):
            raise ValueError("feedback positions must be finite")
        return selected

    def add(self, stamp, positions):
        if self.recovery_time is None:
            raise RuntimeError("begin_after_recovery must be called first")
        stamp = float(stamp)
        if not math.isfinite(stamp) or stamp <= self.recovery_time:
            return None
        selected = self._positions(positions)
        self.samples.append(selected)
        self.samples = self.samples[-self.sample_count:]
        if len(self.samples) < self.sample_count:
            return None
        for index in range(JOINT_COUNT):
            values = [sample[index] for sample in self.samples]
            if max(values) - min(values) > self.tolerance_rad:
                self.samples = [selected]
                return None
        return tuple(
            sum(sample[index] for sample in self.samples) / self.sample_count
            for index in range(POSITION_COUNT)
        )


class MotionEvidence(object):
    """Require repeated feedback before accepting motion or ordinary drift."""

    def __init__(self, baseline, selected_joint, delta_rad,
                 confirmation_samples=MOTION_CONFIRMATION_SAMPLES,
                 drift_limit_rad=NON_SELECTED_DRIFT_LIMIT_RAD,
                 hard_drift_rad=SINGLE_SAMPLE_HARD_DRIFT_RAD):
        self.baseline = StableBaseline._positions(baseline)
        if (not isinstance(selected_joint, int) or isinstance(selected_joint, bool)
                or not 1 <= selected_joint <= JOINT_COUNT):
            raise ValueError("selected_joint must be an integer in [1, 6]")
        self.selected_joint = selected_joint
        self.selected_index = selected_joint - 1
        self.delta_rad = float(delta_rad)
        self.direction = 1.0 if self.delta_rad > 0.0 else -1.0
        self.minimum_rad = abs(self.delta_rad) * 0.4
        self.confirmation_samples = int(confirmation_samples)
        self.drift_limit_rad = float(drift_limit_rad)
        self.hard_drift_rad = float(hard_drift_rad)
        if self.confirmation_samples < 2:
            raise ValueError("confirmation_samples must be at least 2")
        if not 0.0 < self.drift_limit_rad < self.hard_drift_rad:
            raise ValueError("drift limits must be positive and ordered")
        self.motion_count = 0
        self.drift_count = 0
        self.drift_joint = None
        self.last_positions = None

    def add(self, positions):
        current = StableBaseline._positions(positions)
        self.last_positions = current
        selected_delta = current[self.selected_index] - self.baseline[self.selected_index]
        if abs(selected_delta) > 0.020:
            raise RuntimeError(
                "selected J{} moved beyond the 0.020 rad acceptance window: "
                "delta={:.6f}".format(self.selected_joint, selected_delta))

        drift_joint, drift = maximum_joint_shift(
            self.baseline, current, excluded_joint=self.selected_joint)
        if abs(drift) >= self.hard_drift_rad:
            raise RuntimeError(
                "non-selected J{} single-sample hard drift exceeded {:.3f} rad: "
                "delta={:.6f}".format(
                    drift_joint, self.hard_drift_rad, drift))
        if abs(drift) > self.drift_limit_rad:
            if drift_joint == self.drift_joint:
                self.drift_count += 1
            else:
                self.drift_joint = drift_joint
                self.drift_count = 1
            self.motion_count = 0
            if self.drift_count >= self.confirmation_samples:
                raise RuntimeError(
                    "non-selected J{} drift exceeded {:.3f} rad for {} consecutive "
                    "samples: delta={:.6f}; selected J{} delta={:.6f}".format(
                        drift_joint, self.drift_limit_rad,
                        self.confirmation_samples, drift,
                        self.selected_joint, selected_delta))
            return False

        self.drift_count = 0
        self.drift_joint = None
        if self.direction * selected_delta >= self.minimum_rad:
            self.motion_count += 1
        else:
            self.motion_count = 0
        return self.motion_count >= self.confirmation_samples


class ReturnEvidence(object):
    """Require repeated all-joint feedback inside the return tolerance."""

    def __init__(self, baseline, tolerance_rad=0.001,
                 confirmation_samples=MOTION_CONFIRMATION_SAMPLES):
        self.baseline = StableBaseline._positions(baseline)
        self.tolerance_rad = float(tolerance_rad)
        self.confirmation_samples = int(confirmation_samples)
        if self.tolerance_rad <= 0.0 or self.confirmation_samples < 2:
            raise ValueError("return evidence limits are invalid")
        self.count = 0

    def add(self, positions):
        current = StableBaseline._positions(positions)
        error = max(
            abs(current[index] - self.baseline[index])
            for index in range(JOINT_COUNT))
        self.count = self.count + 1 if error <= self.tolerance_rad else 0
        return self.count >= self.confirmation_samples


def failure_actions():
    """Return the only automatic actions allowed after an acceptance failure."""
    return ("software_stop", "hold_enabled", "operator_support_required")


def maximum_joint_shift(before, after, excluded_joint=None):
    """Return one-based joint index and signed largest arm-joint displacement."""
    first = StableBaseline._positions(before)
    second = StableBaseline._positions(after)
    excluded_index = None
    if excluded_joint is not None:
        if (not isinstance(excluded_joint, int) or isinstance(excluded_joint, bool)
                or not 1 <= excluded_joint <= JOINT_COUNT):
            raise ValueError("excluded_joint must be an integer in [1, 6]")
        excluded_index = excluded_joint - 1
    candidates = [
        (abs(second[index] - first[index]), index + 1, second[index] - first[index])
        for index in range(JOINT_COUNT) if index != excluded_index
    ]
    _magnitude, joint, signed = max(candidates)
    return joint, signed


def load_clearance(path):
    """Load a minimal non-sensitive key=value field record."""
    source = pathlib.Path(path)
    if not source.is_file():
        raise ValueError("S12 clearance file does not exist: {}".format(source))
    values = {}
    for number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("invalid clearance line {}".format(number))
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or key in values:
            raise ValueError("invalid or duplicate clearance key on line {}".format(number))
        values[key] = value
    return values


def require_legacy_stack_compatible_firmware(path, side):
    """Require firmware covered by the vendor's legacy ROS 1 software route."""
    if side not in SIDES:
        raise ValueError("side must be 'left' or 'right'")
    values = load_clearance(path)
    key = "PI05_{}_PIPER_FIRMWARE".format(side.upper())
    raw_version = values.get(key, "")
    match = PIPER_FIRMWARE_RE.fullmatch(raw_version)
    if match is None:
        raise ValueError(
            "{} must contain a complete S-Vx.y-z firmware version".format(key))
    version = tuple(int(part) for part in match.groups())
    if not ((1, 8, 0) <= version < (1, 8, 8)):
        raise ValueError(
            "{}={} is outside the reviewed legacy piper_sdk/piper_ros Noetic "
            "route (S-V1.8-0 through S-V1.8-7); select the vendor-documented "
            "software route before enable or motion".format(key, raw_version))
    return raw_version


def require_move_clearance(path, side):
    """Fail closed until the incident and side-specific field gates are recorded."""
    if side not in SIDES:
        raise ValueError("side must be 'left' or 'right'")
    values = load_clearance(path)
    required = list(CLEARANCE_COMMON) + [
        ("PI05_S12_{}_MECHANICAL_INSPECTION".format(side.upper()), "pass"),
        ("PI05_S12_{}_ENABLE_SETTLE".format(side.upper()), "pass"),
        ("PI05_S12_RETEST_APPROVED", "yes"),
    ]
    failures = [
        "{}={}".format(key, expected)
        for key, expected in required if values.get(key) != expected
    ]
    if failures:
        raise ValueError(
            "S12 move clearance is incomplete; required: {}".format(
                ", ".join(failures)
            )
        )
    return True


def require_enable_settle_clearance(path, side):
    """Require incident gates and one-shot approval for an enable-only check."""
    if side not in SIDES:
        raise ValueError("side must be 'left' or 'right'")
    values = load_clearance(path)
    required = list(CLEARANCE_COMMON) + [
        ("PI05_S12_{}_MECHANICAL_INSPECTION".format(side.upper()), "pass"),
        ("PI05_S12_ENABLE_SETTLE_APPROVED", "yes"),
    ]
    failures = [
        "{}={}".format(key, expected)
        for key, expected in required if values.get(key) != expected
    ]
    if failures:
        raise ValueError(
            "S12 enable-settle clearance is incomplete; required: {}".format(
                ", ".join(failures)
            )
        )
    return True
