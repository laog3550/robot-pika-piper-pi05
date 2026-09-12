#!/usr/bin/env python3
"""Fail-closed ROS coordinator for the PI05 dual-arm control boundary."""

import math
import threading

import rospy
from diagnostic_msgs.msg import DiagnosticStatus, KeyValue
from piper_msgs.msg import PiperStatusMsg
from piper_msgs.srv import Enable, EnableResponse
from std_msgs.msg import Bool
from std_srvs.srv import Trigger, TriggerResponse

from pi05_control.dual_arm_safety import CoordinatorConfig, DualArmSafetyCoordinator, SIDES


class DualArmSafetyCoordinatorNode(object):
    def __init__(self):
        self.lock = threading.RLock()
        self.actions_lock = threading.Lock()
        self.fault_worker_running = False
        hardware_actions_enabled = rospy.get_param("~hardware_actions_enabled", False)
        if not isinstance(hardware_actions_enabled, bool):
            raise ValueError("hardware_actions_enabled must be a boolean")
        self.hardware_actions_enabled = hardware_actions_enabled
        self.service_timeout_s = float(rospy.get_param("~service_timeout_s", 1.0))
        heartbeat_hz = float(rospy.get_param("~authorization_heartbeat_hz", 20.0))
        if (not math.isfinite(self.service_timeout_s) or self.service_timeout_s <= 0.0
                or not math.isfinite(heartbeat_hz) or heartbeat_hz <= 0.0):
            raise ValueError("service timeout and authorization heartbeat must be positive")
        self.coordinator = DualArmSafetyCoordinator(CoordinatorConfig(
            status_timeout_s=rospy.get_param("~status_timeout_s", 0.35),
            authorization_ack_timeout_s=rospy.get_param(
                "~authorization_ack_timeout_s", 0.5),
            session_sync_timeout_s=rospy.get_param("~session_sync_timeout_s", 0.2),
        ))
        self.last_action_summary = "none"

        self.authorization_pubs = {
            side: rospy.Publisher(
                "/{}_arm/control_authorized".format(side), Bool,
                queue_size=1, latch=True)
            for side in SIDES
        }
        self.status_pub = rospy.Publisher(
            "/dual_arm/status", DiagnosticStatus, queue_size=1, latch=True)
        for side in SIDES:
            rospy.Subscriber(
                "/{}_arm/safety_filter_status".format(side), DiagnosticStatus,
                self.filter_status_callback, callback_args=side,
                queue_size=1, tcp_nodelay=True)
            rospy.Subscriber(
                "/{}_arm/arm_status".format(side), PiperStatusMsg,
                self.driver_status_callback, callback_args=side,
                queue_size=1, tcp_nodelay=True)

        rospy.Service("/dual_arm/enable_srv", Enable, self.enable_callback)
        rospy.Service("/dual_arm/stop_srv", Trigger, self.stop_callback)
        rospy.Service("/dual_arm/reset_fault", Trigger, self.reset_fault_callback)
        self.publish_authorization(False)
        self.publish_status()
        self.watchdog_timer = rospy.Timer(
            rospy.Duration(1.0 / heartbeat_hz), self.watchdog_callback)

    @staticmethod
    def now():
        return rospy.Time.now().to_sec()

    @staticmethod
    def _parse_bool(values, key):
        if key not in values or values[key] not in ("true", "false"):
            raise ValueError("missing or invalid {}".format(key))
        return values[key] == "true"

    def filter_status_callback(self, message, side):
        values = {item.key: item.value for item in message.values}
        with self.lock:
            before = bool(self.coordinator.fault_reason)
        try:
            state = values["state"]
            authorized = self._parse_bool(values, "authorized")
            feedback_fresh = self._parse_bool(values, "feedback_fresh")
            localization_fresh = self._parse_bool(values, "localization_fresh")
            raw_ik = values.get("ik_over_limit")
            if raw_ik == "none":
                ik_over_limit = None
            elif raw_ik in ("true", "false"):
                ik_over_limit = raw_ik == "true"
            else:
                raise ValueError("missing or invalid ik_over_limit")
            with self.lock:
                self.coordinator.update_filter(
                    side, state, message.level, message.message, authorized,
                    feedback_fresh, localization_fresh, ik_over_limit, self.now())
                self.publish_status()
        except (KeyError, TypeError, ValueError) as error:
            with self.lock:
                self.coordinator.latch_fault(
                    "{} filter status malformed: {}".format(side, error), self.now())
                self.publish_status()
        self._start_fault_response_if_new(before)

    @staticmethod
    def _driver_fault(message):
        angle_limits = [
            message.joint_1_angle_limit,
            message.joint_2_angle_limit,
            message.joint_3_angle_limit,
            message.joint_4_angle_limit,
            message.joint_5_angle_limit,
            message.joint_6_angle_limit,
        ]
        communication_faults = [
            message.communication_status_joint_1,
            message.communication_status_joint_2,
            message.communication_status_joint_3,
            message.communication_status_joint_4,
            message.communication_status_joint_5,
            message.communication_status_joint_6,
        ]
        if message.err_code != 0:
            return True, "err_code is nonzero"
        if any(angle_limits):
            return True, "joint angle limit reported"
        if any(communication_faults):
            return True, "joint communication fault reported"
        return False, "driver status clear"

    def driver_status_callback(self, message, side):
        fault, description = self._driver_fault(message)
        with self.lock:
            before = bool(self.coordinator.fault_reason)
            self.coordinator.update_driver(side, fault, description, self.now())
            self.publish_status()
        self._start_fault_response_if_new(before)

    def _start_fault_response_if_new(self, previously_faulted):
        with self.lock:
            newly_faulted = not previously_faulted and bool(self.coordinator.fault_reason)
            if not newly_faulted or self.fault_worker_running:
                return
            self.fault_worker_running = True
            # Revoke both leases synchronously; service calls run in the worker.
            self.coordinator.deauthorize(self.now())
            self.publish_authorization(False)
            self.publish_status()
        worker = threading.Thread(target=self._fault_response_worker)
        worker.daemon = True
        worker.start()

    def _fault_response_worker(self):
        try:
            with self.actions_lock:
                with self.lock:
                    self.coordinator.deauthorize(self.now())
                    self.publish_authorization(False)
                    self.publish_status()
                if not self.hardware_actions_enabled:
                    self.last_action_summary = "authorization revoked; hardware actions inhibited"
                else:
                    stop_results = [self._call_stop(side) for side in SIDES]
                    disable_results = [self._call_enable(side, False) for side in SIDES]
                    self.last_action_summary = "stop={} disable={}".format(
                        stop_results, disable_results)
        finally:
            with self.lock:
                self.fault_worker_running = False
                self.publish_status()

    def _call_enable(self, side, enabled):
        service_name = "/{}_arm/enable_srv_raw".format(side)
        try:
            rospy.wait_for_service(service_name, timeout=self.service_timeout_s)
            response = rospy.ServiceProxy(service_name, Enable)(enabled)
            return bool(response.enable_response)
        except (rospy.ROSException, rospy.ServiceException) as error:
            rospy.logerr("%s call failed: %s", service_name, error)
            return False

    def _call_stop(self, side):
        service_name = "/{}_arm/stop_srv_raw".format(side)
        try:
            rospy.wait_for_service(service_name, timeout=self.service_timeout_s)
            response = rospy.ServiceProxy(service_name, Trigger)()
            return bool(response.success)
        except (rospy.ROSException, rospy.ServiceException) as error:
            rospy.logerr("%s call failed: %s", service_name, error)
            return False

    def enable_callback(self, request):
        if not request.enable_request:
            return EnableResponse(self._manual_disable())
        if not self.hardware_actions_enabled:
            return EnableResponse(False)
        with self.actions_lock:
            with self.lock:
                if not self.coordinator.can_enable(self.now()):
                    return EnableResponse(False)
            results = [self._call_enable(side, True) for side in SIDES]
            if not all(results):
                with self.lock:
                    self.coordinator.latch_fault(
                        "dual enable failed; rollback requested", self.now())
                    self.coordinator.deauthorize(self.now())
                    self.publish_authorization(False)
                stop_results = [self._call_stop(side) for side in SIDES]
                disable_results = [self._call_enable(side, False) for side in SIDES]
                self.last_action_summary = "enable={} rollback_stop={} rollback_disable={}".format(
                    results, stop_results, disable_results)
                with self.lock:
                    self.publish_status()
                return EnableResponse(False)
            with self.lock:
                if not self.coordinator.mark_enabled(self.now()):
                    accepted = False
                else:
                    accepted = True
                    self.publish_authorization(True)
                    self.last_action_summary = "both raw enable services accepted"
                self.publish_status()
            if not accepted:
                for side in SIDES:
                    self._call_stop(side)
                for side in SIDES:
                    self._call_enable(side, False)
            return EnableResponse(accepted)

    def _manual_disable(self):
        with self.actions_lock:
            with self.lock:
                self.coordinator.deauthorize(self.now())
                self.publish_authorization(False)
            if not self.hardware_actions_enabled:
                self.last_action_summary = "authorization revoked; hardware actions inhibited"
                with self.lock:
                    self.publish_status()
                return False
            results = [self._call_enable(side, False) for side in SIDES]
            self.last_action_summary = "disable={}".format(results)
            if not all(results):
                with self.lock:
                    self.coordinator.latch_fault("dual disable did not complete", self.now())
            with self.lock:
                self.publish_status()
            return all(results)

    def stop_callback(self, _request):
        with self.actions_lock:
            with self.lock:
                self.coordinator.deauthorize(self.now())
                self.publish_authorization(False)
            if not self.hardware_actions_enabled:
                self.last_action_summary = "authorization revoked; hardware stop inhibited"
                with self.lock:
                    self.publish_status()
                return TriggerResponse(False, self.last_action_summary)
            results = [self._call_stop(side) for side in SIDES]
            self.last_action_summary = "stop={}".format(results)
            if not all(results):
                with self.lock:
                    self.coordinator.latch_fault("dual software stop did not complete", self.now())
            with self.lock:
                self.publish_status()
            return TriggerResponse(all(results), self.last_action_summary)

    def reset_fault_callback(self, _request):
        with self.lock:
            reset = not self.fault_worker_running and self.coordinator.reset_fault(self.now())
            self.publish_status()
        if reset:
            return TriggerResponse(True, "fault reset; both arms remain unauthorized")
        return TriggerResponse(
            False, "reset requires both arms unauthorized with fresh, clear status")

    def watchdog_callback(self, _event):
        with self.lock:
            before = bool(self.coordinator.fault_reason)
            self.coordinator.watchdog(self.now())
            authorized = self.coordinator.authorized and not self.coordinator.fault_reason
            self.publish_authorization(authorized)
            self.publish_status()
        self._start_fault_response_if_new(before)

    def publish_authorization(self, authorized):
        message = Bool(data=bool(authorized))
        for publisher in self.authorization_pubs.values():
            publisher.publish(message)

    def publish_status(self):
        now = self.now()
        state = self.coordinator.state(now)
        status = DiagnosticStatus()
        status.name = "pi05/dual_arm/safety_coordinator"
        status.hardware_id = "none"
        if state == "FAULT_LATCHED":
            status.level = DiagnosticStatus.ERROR
            status.message = self.coordinator.fault_reason
        elif state in ("DISABLED", "READY"):
            status.level = DiagnosticStatus.WARN
            status.message = state
        else:
            status.level = DiagnosticStatus.OK
            status.message = state
        status.values = [
            KeyValue("state", state),
            KeyValue("authorized", str(self.coordinator.authorized).lower()),
            KeyValue("hardware_actions_enabled", str(self.hardware_actions_enabled).lower()),
            KeyValue("last_action", self.last_action_summary),
        ]
        self.status_pub.publish(status)


def main():
    rospy.init_node("dual_arm_safety_coordinator")
    try:
        DualArmSafetyCoordinatorNode()
    except (TypeError, ValueError) as error:
        rospy.logfatal("invalid dual-arm coordinator configuration: %s", error)
        raise SystemExit(2)
    rospy.spin()


if __name__ == "__main__":
    main()
