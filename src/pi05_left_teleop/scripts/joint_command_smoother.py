#!/usr/bin/env python3
"""Smooth IK and optional Pika gripper targets for a Piper driver."""
import math
import threading
import time


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


class JointCommandSmoother:
    """First-order target filtering with velocity and acceleration limits."""

    def __init__(self, time_constant, max_velocity, max_acceleration, deadband):
        values = (time_constant, max_velocity, max_acceleration, deadband)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("smoother parameters must be finite")
        if time_constant <= 0 or max_velocity <= 0 or max_acceleration <= 0 or deadband < 0:
            raise ValueError("invalid smoother parameters")
        self.time_constant = time_constant
        self.max_velocity = max_velocity
        self.max_acceleration = max_acceleration
        self.deadband = deadband
        self.position = None
        self.filtered_target = None
        self.velocity = [0.0] * 6

    def reset(self, position):
        if len(position) < 6 or not all(math.isfinite(value) for value in position[:6]):
            raise ValueError("reset position must contain six finite values")
        self.position = list(position[:6])
        self.filtered_target = list(position[:6])
        self.velocity = [0.0] * 6

    def step(self, target, dt):
        if self.position is None:
            raise ValueError("smoother must be reset from feedback before use")
        if len(target) < 6 or not all(math.isfinite(value) for value in target[:6]):
            raise ValueError("target must contain six finite values")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be positive and finite")
        dt = min(dt, 0.1)
        alpha = dt / (self.time_constant + dt)
        result = []
        for index in range(6):
            self.filtered_target[index] += alpha * (
                target[index] - self.filtered_target[index])
            error = self.filtered_target[index] - self.position[index]
            desired_velocity = 0.0 if abs(error) <= self.deadband else clamp(
                error / self.time_constant, -self.max_velocity, self.max_velocity)
            max_velocity_change = self.max_acceleration * dt
            self.velocity[index] += clamp(
                desired_velocity - self.velocity[index],
                -max_velocity_change, max_velocity_change)
            increment = self.velocity[index] * dt
            if error and increment * error > 0 and abs(increment) > abs(error):
                increment = error
                self.velocity[index] = 0.0
            self.position[index] += increment
            result.append(self.position[index])
        return result


class ScalarRateLimiter:
    """Bound the rate of a scalar target such as gripper opening."""

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
        target = clamp(target, self.lower, self.upper)
        limit = self.maximum_rate * min(dt, 0.1)
        self.value += clamp(target - self.value, -limit, limit)
        return self.value


def main():
    import rospy
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Float64
    from std_srvs.srv import SetBool, SetBoolResponse

    rospy.init_node("joint_command_smoother")
    rate_hz = float(rospy.get_param("~rate_hz", 50.0))
    speed_percent = int(rospy.get_param("~driver_speed_percent", 20))
    timeout = float(rospy.get_param("~target_timeout", 0.25))
    gripper_enabled = bool(rospy.get_param("~gripper_enabled", False))
    gripper_timeout = float(rospy.get_param("~gripper_timeout", 0.25))
    gripper_maximum = float(rospy.get_param("~gripper_maximum", 0.07))
    if not math.isfinite(rate_hz) or rate_hz <= 0:
        raise ValueError("rate_hz must be positive")
    if not 1 <= speed_percent <= 100:
        raise ValueError("driver_speed_percent must be in 1..100")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("target_timeout must be positive")
    if not math.isfinite(gripper_timeout) or gripper_timeout <= 0:
        raise ValueError("gripper_timeout must be positive")
    smoother = JointCommandSmoother(
        float(rospy.get_param("~time_constant", 0.12)),
        float(rospy.get_param("~max_velocity", 0.30)),
        float(rospy.get_param("~max_acceleration", 0.50)),
        float(rospy.get_param("~deadband", 0.0005)),
    )
    gripper_limiter = ScalarRateLimiter(
        float(rospy.get_param("~gripper_max_velocity", 0.04)), 0.0, gripper_maximum)
    lock = threading.Lock()
    feedback = None
    gripper_feedback = None
    target = None
    target_received = None
    gripper_target = None
    gripper_received = None
    output_enabled = True

    def feedback_callback(message):
        nonlocal feedback, gripper_feedback
        if len(message.position) >= 6:
            with lock:
                feedback = list(message.position[:6])
                if len(message.position) >= 7 and math.isfinite(message.position[6]):
                    gripper_feedback = float(message.position[6])

    def target_callback(message):
        nonlocal target, target_received
        if len(message.position) >= 6 and all(
                math.isfinite(value) for value in message.position[:6]):
            with lock:
                target = list(message.position[:6])
                target_received = time.monotonic()

    def gripper_callback(message):
        nonlocal gripper_target, gripper_received
        value = float(message.data)
        if math.isfinite(value):
            with lock:
                gripper_target = clamp(value, 0.0, gripper_maximum)
                gripper_received = time.monotonic()

    def set_enabled_callback(request):
        nonlocal output_enabled, target, target_received
        with lock:
            output_enabled = bool(request.data)
            if not output_enabled:
                target = None
                target_received = None
        return SetBoolResponse(success=True,
                               message="smoother output enabled" if output_enabled
                               else "smoother output disabled")

    publisher = rospy.Publisher("smoothed_target", JointState, queue_size=1)
    subscribers = [
        rospy.Subscriber("joint_feedback", JointState, feedback_callback, queue_size=1),
        rospy.Subscriber("ik_target", JointState, target_callback, queue_size=1),
    ]
    if gripper_enabled:
        subscribers.append(
            rospy.Subscriber("gripper_target", Float64, gripper_callback, queue_size=1))
    output_service = rospy.Service("~set_enabled", SetBool, set_enabled_callback)
    rate = rospy.Rate(rate_hz)
    last = time.monotonic()
    active = False
    while not rospy.is_shutdown():
        now = time.monotonic()
        with lock:
            current_feedback = None if feedback is None else list(feedback)
            current_target = None if target is None else list(target)
            received = target_received
            current_gripper_feedback = gripper_feedback
            current_gripper_target = gripper_target
            current_gripper_received = gripper_received
            enabled = output_enabled
        fresh = enabled and received is not None and now - received <= timeout
        if gripper_enabled:
            fresh = (fresh and current_gripper_target is not None and
                     current_gripper_received is not None and
                     now - current_gripper_received <= gripper_timeout)
        if not fresh or current_feedback is None:
            active = False
            last = now
            rate.sleep()
            continue
        if not active:
            smoother.reset(current_feedback)
            if gripper_enabled:
                initial_gripper = (current_gripper_feedback if current_gripper_feedback is not None
                                   else current_gripper_target)
                gripper_limiter.reset(initial_gripper)
            active = True
            last = now
        positions = smoother.step(current_target, max(now - last, 1.0 / rate_hz))
        if gripper_enabled:
            positions.append(gripper_limiter.step(
                current_gripper_target, max(now - last, 1.0 / rate_hz)))
        last = now
        message = JointState()
        message.header.stamp = rospy.Time.now()
        message.name = ["joint%d" % number for number in range(1, len(positions) + 1)]
        message.position = positions
        # The pinned vendor driver reads velocity[6] as a global percentage.
        message.velocity = [0.0] * 6 + [float(speed_percent)]
        if gripper_enabled:
            message.effort = [0.0] * 6 + [1.0]
        publisher.publish(message)
        rate.sleep()
    del subscribers
    del output_service


if __name__ == "__main__":
    main()
