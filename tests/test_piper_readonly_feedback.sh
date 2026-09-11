#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
node_path="${repo_root}/src/pi05_control/scripts/piper_readonly_feedback_node.py"
launch_path="${repo_root}/src/pi05_control/launch/s08_readonly_feedback.launch"

PYTHONPATH="${repo_root}/src/pi05_control/src${PYTHONPATH:+:${PYTHONPATH}}" \
  /usr/bin/python3 -m unittest \
  "${repo_root}/src/pi05_control/test/test_piper_feedback.py"

/usr/bin/python3 - "${node_path}" "${launch_path}" <<'PY'
import ast
import sys
import xml.etree.ElementTree as ET

node_path, launch_path = sys.argv[1:]
with open(node_path, "r", encoding="utf-8") as stream:
    source = stream.read()
tree = ast.parse(source, filename=node_path)

for item in ast.walk(tree):
    if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute):
        if item.func.attr in {"send", "sendall", "sendmsg", "sendto"}:
            raise SystemExit("CAN transmit API is forbidden in the S08 receive-only node")

for forbidden in ("MotionCtrl", "EnableArm", "GripperCtrl", "rospy.Subscriber", "rospy.Service"):
    if forbidden in source:
        raise SystemExit("forbidden control surface found: %s" % forbidden)

if ".recv(" not in source:
    raise SystemExit("receive-only node must read SocketCAN with recv")

launch = ET.parse(launch_path).getroot()
groups = {group.attrib.get("ns"): group for group in launch.findall("group")}
if set(groups) != {"left_arm", "right_arm"}:
    raise SystemExit("launch must contain exactly left_arm and right_arm groups")

expected = {"left_arm": ("left", "left_piper"), "right_arm": ("right", "right_piper")}
for namespace, (side, interface) in expected.items():
    nodes = groups[namespace].findall("node")
    if len(nodes) != 1 or nodes[0].attrib.get("type") != "piper_readonly_feedback_node.py":
        raise SystemExit("%s must contain exactly one receive-only node" % namespace)
    params = {param.attrib["name"]: param.attrib["value"] for param in nodes[0].findall("param")}
    if params.get("side") != side:
        raise SystemExit("%s has incorrect side" % namespace)
    if params.get("joint_state_topic") != "joint_states_raw":
        raise SystemExit("%s must publish the explicit raw feedback topic" % namespace)
    arg_name = "%s_can_interface" % side
    if params.get("can_interface") != "$(arg %s)" % arg_name:
        raise SystemExit("%s has incorrect CAN argument mapping" % namespace)

args = {arg.attrib["name"]: arg.attrib.get("default") for arg in launch.findall("arg")}
if args != {"left_can_interface": "left_piper", "right_can_interface": "right_piper"}:
    raise SystemExit("launch CAN defaults must remain explicitly separated by side")

print("[PASS] Piper receive-only ROS feedback contracts")
PY
