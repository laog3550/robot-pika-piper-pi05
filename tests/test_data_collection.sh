#!/usr/bin/env bash
set -Eeuo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH="$repo_root/src/pi05_data_collection/src${PYTHONPATH:+:$PYTHONPATH}"
"$repo_root/.venv/bin/python" -m unittest -v \
  "$repo_root/src/pi05_data_collection/test/test_session.py" \
  "$repo_root/tests/test_data_collection.py"

source /opt/ros/noetic/setup.bash
export ROS_PACKAGE_PATH="$repo_root/src${ROS_PACKAGE_PATH:+:$ROS_PACKAGE_PATH}"
/usr/bin/python3 - "$repo_root" <<'PY'
import sys
import xml.etree.ElementTree as ET

root = sys.argv[1]
ET.parse(root + "/src/pi05_data_collection/package.xml")
text = open(root + "/scripts/run_data_collection.sh", encoding="utf-8").read()
assert "auto_enable:=false smooth_commands:=true enable_gripper_teleop:=true" in text
assert '--camera-config "$config_file"' in text
assert "check_pika_device_free left /dev/pi05-pika-left" in text
assert "check_pika_device_free right /dev/pi05-pika-right" in text
collector = open(root + "/src/pi05_data_collection/scripts/collector_node.py",
                 encoding="utf-8").read()
assert "class OperatorDashboard" in collector
assert "重新检测相机  F5" in collector
assert "关节姿态 / 肘关节曲线" in collector
assert "J3 feedback" in collector and "action %s rad" in collector
assert "CAP_PROP_BUFFERSIZE, 2" in collector
assert "exposure_dynamic_framerate=0" in collector
assert "手动失能  E" in collector
assert "runtime.begin_teleop(already_enabled=arms_enabled)" in collector
assert "双臂保持使能，可以采集下一条" in collector
assert "cv2.imshow" not in collector and "cv2.waitKey" not in collector
restore = open(root + "/scripts/restore_wrist_uvc.sh", encoding="utf-8").read()
assert '[[ "$(<"$device/idVendor")" == 2bc5' in restore
assert 'PI05_CAMERA_RIGHT_WRIST_RGB_USB_PORT' in restore
assert '/sys/bus/usb/drivers/uvcvideo/bind' in restore
print("Data collection package and wrapper contracts: PASS")
PY
