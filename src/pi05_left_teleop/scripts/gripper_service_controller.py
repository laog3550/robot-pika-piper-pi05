#!/usr/bin/env python3
"""Rate-limit Pika gripper targets and send them through Piper's gripper service."""
import math
import threading
import time


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


class ScalarRateLimiter:
    def __init__(self, maximum_rate, lower, upper):
        if not all(math.isfinite(value) for value in (maximum_rate, lower, upper)):
            raise ValueError("rate limiter parameters must be finite")
        if maximum_rate <= 0 or lower >= upper:
            raise ValueError("invalid rate limiter parameters")
        self.maximum_rate = maximum_rate
        self.lower = lower
        self.upper = upper
        self.value = None

    def reset(self, value):
        if not math.isfinite(value):
            raise ValueError("rate limiter value must be finite")
        self.value = clamp(value, self.lower, self.upper)

    def step(self, target, dt):
        if self.value is None:
            raise ValueError("rate limiter must be reset before use")
        if not math.isfinite(target) or not math.isfinite(dt) or dt <= 0:
            raise ValueError("target and dt must be finite; dt must be positive")
        limit = self.maximum_rate * min(dt, 0.1)
        target = clamp(target, self.lower, self.upper)
        self.value += clamp(target - self.value, -limit, limit)
        return self.value


def main():
    import rospy
    from piper_msgs.srv import Gripper
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Float64
    from std_srvs.srv import SetBool, SetBoolResponse

    rospy.init_node("gripper_service_controller")
    maximum = float(rospy.get_param("~maximum", 0.07))
    maximum_rate = float(rospy.get_param("~max_velocity", 0.04))
    timeout = float(rospy.get_param("~target_timeout", 0.25))
    effort = float(rospy.get_param("~effort", 1.0))
    rate_hz = float(rospy.get_param("~rate_hz", 20.0))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("target_timeout must be positive")
    if not math.isfinite(effort) or not 0.5 <= effort <= 2.0:
        raise ValueError("effort must be in [0.5, 2.0]")
    if not math.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError("rate_hz must be positive")

    limiter = ScalarRateLimiter(maximum_rate, 0.0, maximum)
    lock = threading.Lock()
    target = None
    received = None
    feedback = None
    enabled = False

    def feedback_callback(message):
        nonlocal feedback
        if len(message.position) >= 7 and math.isfinite(message.position[6]):
            with lock:
                feedback = clamp(float(message.position[6]), 0.0, maximum)

    def target_callback(message):
        nonlocal target, received
        value = float(message.data)
        if math.isfinite(value):
            with lock:
                target = clamp(value, 0.0, maximum)
                received = time.monotonic()

    def set_enabled_callback(request):
        nonlocal enabled
        with lock:
            enabled = bool(request.data)
            if enabled:
                initial = feedback if feedback is not None else target
                if initial is not None:
                    limiter.reset(initial)
        return SetBoolResponse(success=True,
                               message="gripper output enabled" if enabled
                               else "gripper output disabled")

    subscribers = [
        rospy.Subscriber("joint_feedback", JointState, feedback_callback, queue_size=1),
        rospy.Subscriber("gripper_target", Float64, target_callback, queue_size=1),
    ]
    output_service = rospy.Service("~set_enabled", SetBool, set_enabled_callback)
    command = rospy.ServiceProxy("gripper_command", Gripper)
    rate = rospy.Rate(rate_hz)
    last = time.monotonic()
    last_sent = None
    while not rospy.is_shutdown():
        now = time.monotonic()
        with lock:
            current_target = target
            current_received = received
            current_enabled = enabled
        fresh = (current_enabled and current_target is not None and
                 current_received is not None and now - current_received <= timeout)
        if fresh:
            if limiter.value is None:
                limiter.reset(current_target)
            value = limiter.step(current_target, max(now - last, 1.0 / rate_hz))
            if last_sent is None or abs(value - last_sent) >= 1e-5:
                try:
                    response = command(value, effort, 0x01, 0x00)
                    if not response.status:
                        rospy.logwarn_throttle(1.0, "Piper rejected gripper command")
                    else:
                        last_sent = value
                except rospy.ServiceException as error:
                    rospy.logwarn_throttle(1.0, "gripper service failed: %s", error)
        last = now
        rate.sleep()
    del subscribers
    del output_service


if __name__ == "__main__":
    main()
