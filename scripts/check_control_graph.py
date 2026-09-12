#!/usr/bin/env python3
"""Read-only ownership audit for the managed PI05 dual-arm ROS graph."""

import argparse
import os
import sys


SIDES = ("left", "right")


def _members(mapping, name):
    return set(mapping.get(name, ()))


def validate_graph(mode, nodes, publishers, subscribers, services):
    if mode not in ("simulation", "hardware"):
        raise ValueError("mode must be simulation or hardware")
    errors = []
    coordinator = "/dual_arm_safety_coordinator"
    expected_nodes = {coordinator}
    for side in SIDES:
        expected_nodes.add("/{}_arm/safety_filter".format(side))
        if mode == "hardware":
            expected_nodes.add("/{}_arm/piper_driver_raw".format(side))
    missing = expected_nodes - set(nodes)
    if missing:
        errors.append("missing managed nodes: {}".format(", ".join(sorted(missing))))

    forbidden_names = (
        "/enable_srv",
        "/stop_srv",
        "/gripper_srv",
        "/reset_srv",
        "/go_zero_srv",
        "/joint_ctrl_single",
        "/pos_cmd",
        "/enable_flag",
    )
    graph_names = set(publishers) | set(subscribers) | set(services)
    present_forbidden = set(forbidden_names) & graph_names
    if present_forbidden:
        errors.append("ambiguous global control interfaces: {}".format(
            ", ".join(sorted(present_forbidden))))

    for public_service in ("/dual_arm/enable_srv", "/dual_arm/stop_srv",
                           "/dual_arm/reset_fault"):
        providers = _members(services, public_service)
        if providers != {coordinator}:
            errors.append("{} providers are {}".format(
                public_service, ", ".join(sorted(providers)) or "none"))

    for side, suffix in (("left", "l"), ("right", "r")):
        safety_filter = "/{}_arm/safety_filter".format(side)
        driver = "/{}_arm/piper_driver_raw".format(side)
        authorization = "/{}_arm/control_authorized".format(side)
        raw_command = "/{}_arm/joint_ctrl_raw".format(side)
        business_command = "/joint_states_gripper_{}".format(suffix)
        feedback = "/joint_states_single_{}".format(suffix)

        if _members(publishers, authorization) != {coordinator}:
            errors.append("{} must have only the coordinator publisher".format(authorization))
        if _members(subscribers, authorization) != {safety_filter}:
            errors.append("{} must have only its filter subscriber".format(authorization))
        if _members(publishers, raw_command) != {safety_filter}:
            errors.append("{} must have only its filter publisher".format(raw_command))
        expected_raw_subscribers = {driver} if mode == "hardware" else set()
        if _members(subscribers, raw_command) != expected_raw_subscribers:
            errors.append("{} subscribers do not match mode {}".format(raw_command, mode))
        if _members(publishers, business_command) or _members(subscribers, business_command):
            errors.append("{} bypasses the integrated command remap".format(business_command))
        if _members(subscribers, feedback) != {safety_filter}:
            errors.append("{} must have only its filter subscriber".format(feedback))
        expected_feedback_publishers = {driver} if mode == "hardware" else set()
        if _members(publishers, feedback) != expected_feedback_publishers:
            errors.append("{} publishers do not match mode {}".format(feedback, mode))

        for unused_command in (
            "/{}_arm/pos_cmd_raw".format(side),
            "/{}_arm/enable_flag_raw".format(side),
        ):
            if _members(publishers, unused_command):
                errors.append("unexpected publisher on {}".format(unused_command))

        for service_leaf in ("enable_srv_raw", "stop_srv_raw", "gripper_srv_raw",
                             "reset_srv_raw", "go_zero_srv_raw", "block_arm_raw"):
            service_name = "/{}_arm/{}".format(side, service_leaf)
            expected_providers = {driver} if mode == "hardware" else set()
            if _members(services, service_name) != expected_providers:
                errors.append("{} providers do not match mode {}".format(
                    service_name, mode))
    return errors


def _system_state_to_map(items):
    return {name: set(members) for name, members in items}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit PI05 control ownership without publishing or calling services.")
    parser.add_argument("--mode", choices=("simulation", "hardware"), required=True)
    args = parser.parse_args(argv)

    try:
        import rosgraph
        master = rosgraph.Master("/pi05_control_graph_check")
        publishers_raw, subscribers_raw, services_raw = master.getSystemState()
        nodes = set()
        publishers = _system_state_to_map(publishers_raw)
        subscribers = _system_state_to_map(subscribers_raw)
        services = _system_state_to_map(services_raw)
        for members in list(publishers.values()) + list(subscribers.values()) + list(services.values()):
            nodes.update(members)
    except Exception as error:
        print("[PI05] ERROR: cannot read ROS master {}: {}".format(
            os.environ.get("ROS_MASTER_URI", "(default)"), error), file=sys.stderr)
        return 2

    errors = validate_graph(args.mode, nodes, publishers, subscribers, services)
    if errors:
        for error in errors:
            print("[PI05] ERROR: {}".format(error), file=sys.stderr)
        print("[PI05] control graph check failed", file=sys.stderr)
        return 1
    print("[PI05] {} control graph ownership check passed".format(args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
