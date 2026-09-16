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


def piper_target(angle, maximum=0.07):
    """Scale the full Pika travel to the configured Piper gripper travel."""
    if not math.isfinite(maximum) or maximum <= 0 or maximum > 0.08:
        raise ValueError("Piper gripper maximum must be in (0, 0.08]")
    return max(0.0, min(maximum, pika_distance(angle) / PIKA_MAX_DISTANCE * maximum))


class FrameParser:
    def __init__(self):
        self.buffer = ""
        self.decoder = json.JSONDecoder()

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
            try:
                value, end = self.decoder.raw_decode(self.buffer)
            except json.JSONDecodeError:
                if len(self.buffer) > 8192:
                    self.buffer = self.buffer[-4096:]
                break
            self.buffer = self.buffer[end:]
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
    maximum = float(rospy.get_param("~piper_maximum", 0.07))
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
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
