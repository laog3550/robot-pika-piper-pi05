"""Resolve configured camera roles to current V4L2 color capture nodes."""

from pathlib import Path
import re
import subprocess


ALLOWED_KEYS = {
    "PI05_CAMERA_LEFT_WRIST_SERIAL",
    "PI05_CAMERA_RIGHT_WRIST_SERIAL",
    "PI05_CAMERA_TOP_SERIAL",
}


def load_serials(path):
    values = {}
    pattern = re.compile(r"^([A-Z][A-Z0-9_]*)=([-A-Za-z0-9_./:+]*)$")
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = pattern.fullmatch(line)
        if match and match.group(1) in ALLOWED_KEYS:
            values[match.group(1)] = match.group(2)
    missing = sorted(key for key in ALLOWED_KEYS if not values.get(key))
    if missing:
        raise ValueError("camera serial configuration missing: %s" % ", ".join(missing))
    return {
        "left_wrist": (values["PI05_CAMERA_LEFT_WRIST_SERIAL"], "MJPG"),
        "right_wrist": (values["PI05_CAMERA_RIGHT_WRIST_SERIAL"], "MJPG"),
        "top": (values["PI05_CAMERA_TOP_SERIAL"], "YUYV"),
    }


def _command(args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, check=False).stdout


def device_identity(path):
    properties = _command(["udevadm", "info", "--query=property", "--name=" + str(path)])
    serial = ""
    for line in properties.splitlines():
        if line.startswith("ID_SERIAL_SHORT="):
            serial = line.split("=", 1)[1]
            break
    formats = _command(["v4l2-ctl", "--device=" + str(path), "--list-formats"])
    return serial, formats


def resolve_camera_devices(config_path, device_paths=None):
    roles = load_serials(config_path)
    raw_candidates = (list(device_paths) if device_paths is not None else
                      sorted(Path("/dev").glob("video*")))
    # Custom udev aliases such as /dev/video60 may point to /dev/video16.
    # Resolve and deduplicate them so one capture device is never reported as
    # multiple role candidates.
    candidates = []
    seen = set()
    for candidate in raw_candidates:
        canonical = Path(candidate).resolve()
        if canonical in seen:
            continue
        seen.add(canonical)
        candidates.append(canonical)
    identities = {}
    for candidate in candidates:
        candidate = Path(candidate)
        if device_paths is None and not candidate.exists():
            continue
        identities[candidate] = device_identity(candidate)
    resolved = {}
    errors = {}
    for role, (wanted_serial, wanted_format) in roles.items():
        matches = [path for path, (serial, formats) in identities.items()
                   if serial == wanted_serial and ("'%s'" % wanted_format) in formats]
        if len(matches) == 1:
            resolved[role] = str(matches[0])
        elif not matches:
            errors[role] = "%s color interface is unavailable; reconnect it and retry" % role
        else:
            errors[role] = "%s maps to multiple %s nodes" % (role, wanted_format)
    return resolved, errors
