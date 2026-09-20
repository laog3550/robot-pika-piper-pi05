"""Load and strictly validate the PI05 data-collection role mapping."""

from pathlib import Path

import yaml

from pi05_data_collection.session import FEATURE_NAMES
from pi05_data_collection.storage import CAMERA_KEYS


SIDES = ("left", "right")
CAMERA_FIELDS = {
    "observation_key", "serial_config_key", "usb_port_config_key", "pixel_format"}
ARM_FIELDS = {
    "feedback_topic", "action_topic", "localization_topic", "pika_pose_topic",
    "status_topic", "feature_names"}
EXPECTED_CAMERAS = {
    "left_wrist": ("PI05_CAMERA_LEFT_WRIST_SERIAL", "PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT", "MJPG"),
    "right_wrist": ("PI05_CAMERA_RIGHT_WRIST_SERIAL", "PI05_CAMERA_RIGHT_WRIST_RGB_USB_PORT", "MJPG"),
    "top": ("PI05_CAMERA_TOP_SERIAL", "PI05_CAMERA_TOP_USB_PORT", "YUYV"),
}
EXPECTED_ARM_TOPICS = {
    "left": {
        "feedback_topic": "/joint_states_single_l",
        "action_topic": "/left_arm/joint_ctrl_raw",
        "localization_topic": "/pi05/pika_input/left/localization_status",
        "pika_pose_topic": "/pi05/pika_input/left/pose",
        "status_topic": "/left_arm/arm_status",
    },
    "right": {
        "feedback_topic": "/joint_states_single_r",
        "action_topic": "/right_arm/joint_ctrl_raw",
        "localization_topic": "/pi05/pika_input/right/localization_status",
        "pika_pose_topic": "/pi05/pika_input/right/pose",
        "status_topic": "/right_arm/arm_status",
    },
}


def _exact_keys(name, value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("%s keys must be exactly %s" % (name, ", ".join(expected)))


def load_collection_mapping(path):
    with Path(path).open("r", encoding="utf-8") as source:
        data = yaml.safe_load(source)
    _exact_keys("mapping", data, ("schema_version", "cameras", "arms", "vector_order"))
    if data["schema_version"] != 1:
        raise ValueError("unsupported data-collection mapping schema")
    _exact_keys("cameras", data["cameras"], CAMERA_KEYS)
    _exact_keys("arms", data["arms"], SIDES)

    observation_keys = []
    for role in CAMERA_KEYS:
        camera = data["cameras"][role]
        _exact_keys("camera %s" % role, camera, CAMERA_FIELDS)
        expected_key = "observation.images." + role
        if camera["observation_key"] != expected_key:
            raise ValueError("%s must map to %s" % (role, expected_key))
        expected_serial, expected_port, expected_format = EXPECTED_CAMERAS[role]
        if (camera["serial_config_key"], camera["usb_port_config_key"],
                camera["pixel_format"]) != (expected_serial, expected_port, expected_format):
            raise ValueError("%s machine-config mapping or pixel format is incorrect" % role)
        observation_keys.append(camera["observation_key"])
    if len(set(observation_keys)) != len(observation_keys):
        raise ValueError("camera observation keys must be unique")

    topics = []
    combined_features = []
    for side in SIDES:
        arm = data["arms"][side]
        _exact_keys("arm %s" % side, arm, ARM_FIELDS)
        expected_features = list(FEATURE_NAMES[:7] if side == "left" else FEATURE_NAMES[7:])
        if arm["feature_names"] != expected_features:
            raise ValueError("%s feature order does not match the 14-D contract" % side)
        combined_features.extend(arm["feature_names"])
        for field in ARM_FIELDS - {"feature_names"}:
            topic = arm[field]
            if topic != EXPECTED_ARM_TOPICS[side][field]:
                raise ValueError("%s %s mapping is incorrect" % (side, field))
            topics.append(topic)
    if len(set(topics)) != len(topics):
        raise ValueError("arm role topics must be unique")
    if data["vector_order"] != list(FEATURE_NAMES) or data["vector_order"] != combined_features:
        raise ValueError("vector_order must be left J1-J6/gripper then right J1-J6/gripper")
    return data
