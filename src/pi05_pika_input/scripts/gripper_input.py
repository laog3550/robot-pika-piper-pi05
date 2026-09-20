#!/usr/bin/env python3
"""Read a Pika encoder without transmitting serial commands."""
import fcntl
import json
import math
import os
import select
import stat
import termios
import tty


PIKA_MAX_ANGLE = 1.67
PIKA_MAX_DISTANCE = 0.09670703693547789


def pika_distance(angle):
    """Convert the Pika AS5047 angle to its measured opening in metres."""
    if not math.isfinite(angle):
        raise ValueError("Pika angle must be finite")
    angle = max(0.0, min(PIKA_MAX_ANGLE, angle))

    def linkage_width(value):
        value = (180.0 - 43.99) / 180.0 * math.pi - value
        height = 0.0325 * math.sin(value)
        horizontal = 0.0325 * math.cos(value)
        return math.sqrt(0.058 ** 2 - (height - 0.01456) ** 2) + horizontal

    return 2.0 * (linkage_width(angle) - linkage_width(0.0))


def piper_target(angle, maximum=0.10):
    """Scale the full Pika travel to the configured Piper gripper travel."""
    if not math.isfinite(maximum) or maximum <= 0 or maximum > 0.10:
        raise ValueError("Piper gripper maximum must be in (0, 0.10]")
    return max(0.0, min(maximum, pika_distance(angle) / PIKA_MAX_DISTANCE * maximum))


class FrameParser:
    def __init__(self):
        self.buffer = ""

    @staticmethod
    def object_end(value):
        """Return the end of the first brace-delimited object, if complete."""
        depth = 0
        in_string = False
        escaped = False
        for index, character in enumerate(value):
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return index + 1
        return None

    def feed(self, chunk):
        self.buffer += chunk.decode("ascii", errors="ignore")
        values = []
        while True:
            start = self.buffer.find("{")
            if start < 0:
                self.buffer = ""
                break
            if start:
                self.buffer = self.buffer[start:]
            end = self.object_end(self.buffer)
            if end is None:
                if len(self.buffer) > 8192:
                    self.buffer = self.buffer[-4096:]
                break
            frame = self.buffer[:end]
            self.buffer = self.buffer[end:]
            try:
                value = json.loads(frame)
            except json.JSONDecodeError:
                # A complete but damaged frame must not permanently block all
                # valid frames that follow it on the serial stream.
                continue
            sensor = value.get("AS5047") if isinstance(value, dict) else None
            if isinstance(sensor, dict) and "error" not in sensor:
                try:
                    angle = float(sensor["rad"])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(angle):
                    values.append(angle)
        return values


def configure_serial(fd):
    tty.setraw(fd, termios.TCSANOW)
    configured = termios.tcgetattr(fd)
    configured[4] = termios.B460800
    configured[5] = termios.B460800
    configured[2] &= ~termios.CSTOPB
    configured[2] &= ~termios.PARENB
    configured[2] = (configured[2] & ~termios.CSIZE) | termios.CS8
    if hasattr(termios, "CRTSCTS"):
        configured[2] &= ~termios.CRTSCTS
    termios.tcsetattr(fd, termios.TCSANOW, configured)


def main():
    import rospy
    from std_msgs.msg import Float64

    rospy.init_node("pika_gripper_input")
    device = rospy.get_param("~device")
    maximum = float(rospy.get_param("~piper_maximum", 0.10))
    resolved = os.path.realpath(device)
    if not resolved.startswith("/dev/") or not stat.S_ISCHR(os.stat(resolved).st_mode):
        raise ValueError("Pika device must resolve to a character device below /dev")
    # O_RDONLY and the absence of serial write calls are deliberate: this node
    # only reads the handheld encoder and cannot actuate the Pika hardware.
    fd = os.open(device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    original = None
    publisher = rospy.Publisher("gripper_target", Float64, queue_size=1)
    parser = FrameParser()
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "Pika device is already locked by another gripper-input session: %s" %
                device) from error
        original = termios.tcgetattr(fd)
        configure_serial(fd)
        while not rospy.is_shutdown():
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            for angle in parser.feed(chunk):
                publisher.publish(Float64(data=piper_target(angle, maximum)))
    finally:
        if original is not None:
            termios.tcsetattr(fd, termios.TCSANOW, original)
        os.close(fd)


if __name__ == "__main__":
    main()
