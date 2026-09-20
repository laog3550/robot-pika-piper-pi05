#!/usr/bin/env python3
"""Collect continuous dual-arm episodes whose recorded tail is automatic return-home."""

import argparse
from collections import deque
import math
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk
import yaml

from pi05_data_collection.camera_devices import resolve_camera_devices
from pi05_data_collection.mapping import load_collection_mapping
from pi05_data_collection.session import (
    EpisodeStateMachine, HomeProgress, Outcome, Phase, SessionError, dual_vector)
from pi05_data_collection.storage import CAMERA_KEYS, EpisodeWriter, ExportWorker


SIDES = ("left", "right")
SUFFIX = {"left": "l", "right": "r"}
MIN_DECODED_CAMERA_FPS = 25.0
UI_REFRESH_SECONDS = 1.0 / 20.0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--task")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--camera-config", type=Path,
                        default=Path(__file__).resolve().parents[3] / "config/cameras.env")
    parser.add_argument("--mapping-config", type=Path,
                        default=Path(__file__).resolve().parents[3] /
                        "config/data-collection-mapping.yaml")
    parser.add_argument("--top-rotation", choices=("none", "cw", "ccw", "180"), default="cw")
    parser.add_argument("--output-root", type=Path, default=Path("/home/mips/datasets/pi05"))
    parser.add_argument("--home-config", type=Path,
                        default=Path(__file__).resolve().parents[3] / "config/arm-home.yaml")
    parser.add_argument("--home-timeout", type=float, default=180.0)
    parser.add_argument("--home-tolerance", type=float, default=0.02)
    parser.add_argument("--stable-seconds", type=float, default=1.0)
    parser.add_argument("--freshness", type=float, default=0.10)
    parser.add_argument("--minimum-free-gb", type=float, default=20.0)
    parser.add_argument("--lerobot-python", default="/home/mips/miniconda3/envs/lerobot/bin/python")
    parser.add_argument("--exporter", type=Path,
                        default=Path(__file__).resolve().parents[3] / "scripts/export_lerobot_episode.py")
    parser.add_argument("--repo-id")
    parser.add_argument("--startup-only", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("this program moves hardware; add --apply after checking the workspace")
    if args.fps != 30 or args.width != 640 or args.height != 480:
        parser.error("formal PI05 datasets are fixed at 640x480 and 30 FPS")
    for name in ("duration", "home_timeout", "home_tolerance", "stable_seconds",
                 "freshness", "minimum_free_gb"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error("--%s must be positive and finite" % name.replace("_", "-"))
    if not args.dataset_name.replace("-", "").replace("_", "").isalnum():
        parser.error("--dataset-name may only contain letters, numbers, '-' and '_'")
    return args


def load_home(path):
    with Path(path).open("r", encoding="utf-8") as source:
        data = yaml.safe_load(source)
    result = {}
    for side in SIDES:
        value = data[side + "_arm_home"]
        positions = tuple(float(item) for item in value["positions_rad"])
        speed = int(value["speed_percent"])
        if len(positions) != 6 or not all(math.isfinite(item) for item in positions):
            raise ValueError("%s home must contain six finite positions" % side)
        if not 1 <= speed <= 100:
            raise ValueError("home speed must be in 1..100")
        result[side] = (positions, speed)
    return result


class CameraStream:
    def __init__(self, name, device, width, height, fps, rotation="none",
                 pixel_format="MJPG"):
        self.name = name
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.rotation = rotation
        self.lock = threading.Lock()
        self.frame = None
        self.updated_at = 0.0
        self.timestamps = deque(maxlen=fps * 3)
        self.error = ""
        self.stop_event = threading.Event()
        if name in ("left_wrist", "right_wrist"):
            result = subprocess.run(
                ["v4l2-ctl", "--device=" + str(device),
                 "--set-ctrl=exposure_dynamic_framerate=0"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if result.returncode:
                raise RuntimeError("could not disable dynamic camera FPS: %s" %
                                   result.stdout.strip())
        self.capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
        self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*pixel_format))
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.capture.set(cv2.CAP_PROP_FPS, fps)
        # A single V4L2 buffer cuts Dabai DC1 delivery to roughly 17 FPS on
        # this host. Two buffers retain low latency while sustaining the
        # camera's nominal 30 FPS stream through OpenCV decoding.
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError("could not open %s camera at %s" % (name, device))
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        failures = 0
        while not self.stop_event.is_set():
            ok, frame = self.capture.read()
            now = time.monotonic()
            if not ok or frame is None:
                failures += 1
                if failures >= 10:
                    self.error = "camera read failed repeatedly"
                time.sleep(0.01)
                continue
            failures = 0
            if self.rotation == "cw":
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation == "ccw":
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif self.rotation == "180":
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)
            with self.lock:
                self.frame = frame
                self.updated_at = now
                self.timestamps.append(now)
                self.error = ""

    def latest(self):
        with self.lock:
            if self.frame is None:
                return None, math.inf
            return self.frame.copy(), time.monotonic() - self.updated_at

    def measured_fps(self):
        with self.lock:
            values = tuple(self.timestamps)
        if len(values) < 2 or values[-1] == values[0]:
            return 0.0
        return (len(values) - 1) / (values[-1] - values[0])

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=2.0)
        self.capture.release()


class OperatorDashboard:
    """Single-window controls and visualization; callbacks only enqueue commands."""

    def __init__(self, dataset_name, task, duration, startup_only=False):
        self.root = tk.Tk()
        self.root.title("PI05 双臂连续数据采集")
        self.root.geometry("1500x900")
        self.root.minsize(1100, 680)
        self.command = None
        self.closed = False
        self.startup_only = startup_only
        self.task_var = tk.StringVar(value=task)
        self.duration_var = tk.StringVar(value=str(duration))
        self.phase_var = tk.StringVar(value="启动中")
        self.status_var = tk.StringVar(value="正在检查设备……")
        self.countdown_var = tk.StringVar(value="--")
        self.left_angles_var = tk.StringVar(value="左臂 J2/J3：等待反馈")
        self.right_angles_var = tk.StringVar(value="右臂 J2/J3：等待反馈")
        self.device_var = tk.StringVar(value="相机：正在检测")
        self.image_labels = {}
        self.image_refs = {}
        self.joint_vars = {}
        self.joint_canvases = {}
        self.joint_history = {side: deque(maxlen=600) for side in SIDES}
        self.last_joint_sample = 0.0
        self.joint_record_var = tk.StringVar(value="○ 未录制")
        self._build(dataset_name)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.enqueue("quit"))
        bindings = {
            "<space>": "start", "<Key-s>": "success", "<Key-S>": "success",
            "<Key-f>": "failure", "<Key-F>": "failure",
            "<Key-d>": "discard", "<Key-D>": "discard",
            "<Key-e>": "disable", "<Key-E>": "disable",
            "<Key-q>": "quit", "<Key-Q>": "quit",
            "<Key-x>": "stop", "<Key-X>": "stop",
            "<F5>": "retry_cameras",
        }
        for sequence, command in bindings.items():
            self.root.bind(sequence, lambda event, value=command: self._handle_key(event, value))

    def _build(self, dataset_name):
        root = self.root
        style = ttk.Style(root)
        style.configure("Action.TButton", font=("Sans", 12, "bold"), padding=9)
        style.configure("Danger.TButton", font=("Sans", 12, "bold"), padding=9)
        header = ttk.Frame(root, padding=10)
        header.pack(fill=tk.X)
        ttk.Label(header, text="PI05 双臂连续数据采集", font=("Sans", 18, "bold")).grid(
            row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(header, text="数据集：%s" % dataset_name).grid(row=1, column=0, sticky="w", pady=8)
        ttk.Label(header, text="任务描述：").grid(row=1, column=1, sticky="e")
        self.task_entry = ttk.Entry(header, textvariable=self.task_var, width=62)
        self.task_entry.grid(row=1, column=2, columnspan=2, sticky="ew", padx=5)
        ttk.Label(header, text="操作时长(秒)：").grid(row=1, column=4, sticky="e")
        self.duration_entry = ttk.Entry(header, textvariable=self.duration_var, width=9)
        self.duration_entry.grid(row=1, column=5, sticky="w")
        header.columnconfigure(2, weight=1)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10)
        images = ttk.Frame(notebook, padding=(0, 6))
        notebook.add(images, text="三路相机")
        titles = {"left_wrist": "左腕相机", "right_wrist": "右腕相机", "top": "顶部相机"}
        for column, key in enumerate(CAMERA_KEYS):
            panel = ttk.LabelFrame(images, text=titles[key], padding=4)
            panel.grid(row=0, column=column, sticky="nsew", padx=4)
            label = ttk.Label(panel, anchor="center")
            label.pack(fill=tk.BOTH, expand=True)
            self.image_labels[key] = label
            images.columnconfigure(column, weight=1)
        images.rowconfigure(0, weight=1)

        joints = ttk.Frame(notebook, padding=10)
        notebook.add(joints, text="关节姿态 / 肘关节曲线")
        record_label = tk.Label(joints, textvariable=self.joint_record_var,
                                anchor="w", font=("Sans", 12, "bold"))
        record_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.joint_record_label = record_label
        for column, side in enumerate(SIDES):
            label = "左臂" if side == "left" else "右臂"
            panel = ttk.LabelFrame(joints, text=label + "：反馈 / action 目标", padding=8)
            panel.grid(row=1, column=column, sticky="nsew", padx=5)
            variable = tk.StringVar(value="等待关节反馈……")
            ttk.Label(panel, textvariable=variable, font=("Monospace", 11),
                      justify=tk.LEFT).pack(fill=tk.X)
            canvas = tk.Canvas(panel, width=680, height=280, bg="#111820",
                               highlightthickness=1, highlightbackground="#455a64")
            canvas.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            ttk.Label(panel, text="肘关节 J3：绿色=实际反馈，橙色虚线=action 目标；窗口=最近 10 秒").pack(
                anchor="w", pady=(5, 0))
            self.joint_vars[side] = variable
            self.joint_canvases[side] = canvas
            joints.columnconfigure(column, weight=1)
        joints.rowconfigure(1, weight=1)

        info = ttk.Frame(root, padding=10)
        info.pack(fill=tk.X)
        ttk.Label(info, textvariable=self.phase_var, font=("Sans", 14, "bold")).grid(
            row=0, column=0, sticky="w")
        ttk.Label(info, text="剩余：", font=("Sans", 12)).grid(row=0, column=1, sticky="e")
        ttk.Label(info, textvariable=self.countdown_var, font=("Sans", 14, "bold")).grid(
            row=0, column=2, sticky="w")
        ttk.Label(info, textvariable=self.left_angles_var, font=("Monospace", 12)).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(info, textvariable=self.right_angles_var, font=("Monospace", 12)).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=3)
        ttk.Label(info, textvariable=self.device_var).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=3)
        self.status_label = tk.Label(info, textvariable=self.status_var, anchor="w",
                                     bg="#222222", fg="#ffe082", padx=8, pady=7)
        self.status_label.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(5, 0))
        info.columnconfigure(0, weight=1)
        info.columnconfigure(2, weight=1)

        controls = ttk.Frame(root, padding=(10, 0, 10, 12))
        controls.pack(fill=tk.X)
        definitions = (
            ("retry", "重新检测相机  F5", "retry_cameras"),
            ("start", "开始采集  Space", "start"),
            ("success", "提前成功并回位  S", "success"),
            ("failure", "标记失败并继续计时  F", "failure"),
            ("discard", "丢弃并回位  D", "discard"),
            ("disable", "手动失能  E", "disable"),
            ("stop", "软件急停  X", "stop"),
            ("quit", "退出  Q", "quit"),
        )
        self.buttons = {}
        for column, (key, text, command) in enumerate(definitions):
            button = ttk.Button(controls, text=text, command=lambda value=command: self.enqueue(value),
                                style="Danger.TButton" if key == "stop" else "Action.TButton")
            button.grid(row=0, column=column, sticky="ew", padx=3)
            controls.columnconfigure(column, weight=1)
            self.buttons[key] = button
        if self.startup_only:
            self.buttons["start"].state(["disabled"])

    def enqueue(self, command):
        if self.command is None:
            self.command = command

    def _handle_key(self, event, command):
        # Letters and spaces typed into the task field must remain text, not
        # accidentally operate the robot.
        if event.widget in (self.task_entry, self.duration_entry):
            return None
        self.enqueue(command)
        return "break"

    def take_command(self):
        command, self.command = self.command, None
        return command

    def values(self):
        task = self.task_var.get().strip()
        try:
            duration = float(self.duration_var.get())
        except ValueError:
            raise ValueError("操作时长必须是数字")
        if not task:
            raise ValueError("任务描述不能为空")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("操作时长必须大于 0")
        return task, duration

    def set_controls(self, phase, system_ready, arms_enabled):
        editable = phase == Phase.IDLE
        self.task_entry.configure(state="normal" if editable else "disabled")
        self.duration_entry.configure(state="normal" if editable else "disabled")
        if editable and system_ready and not self.startup_only:
            self.buttons["start"].state(["!disabled"])
        else:
            self.buttons["start"].state(["disabled"])
        active = phase == Phase.MANIPULATION
        for key in ("success", "failure", "discard"):
            self.buttons[key].state(["!disabled"] if active else ["disabled"])
        self.buttons["retry"].state(["!disabled"] if editable else ["disabled"])
        self.buttons["disable"].state(
            ["!disabled"] if phase in (Phase.IDLE, Phase.LOCKED) and arms_enabled
            else ["disabled"])

    def update(self, cameras, runtime, machine, episode_number, duration, started_at,
               status, camera_errors, readiness_errors, export_pending, arms_enabled):
        for key in CAMERA_KEYS:
            camera = cameras.get(key)
            frame, age = camera.latest() if camera is not None else (None, math.inf)
            if frame is None:
                frame = np.zeros((360, 480, 3), dtype=np.uint8)
                text = "NO VIDEO - " + key
                cv2.putText(frame, text[:48], (15, 180), cv2.FONT_HERSHEY_SIMPLEX,
                            0.58, (0, 100, 255), 2, cv2.LINE_AA)
            else:
                frame = cv2.resize(frame, (480, 360), interpolation=cv2.INTER_AREA)
                cv2.putText(frame, "age %.0f ms" % (age * 1000), (10, 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                            (0, 255, 0) if age < 0.1 else (0, 0, 255), 2)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ppm = ("P6\n%d %d\n255\n" % (rgb.shape[1], rgb.shape[0])).encode("ascii")
            image = tk.PhotoImage(data=ppm + rgb.tobytes(), format="PPM")
            self.image_labels[key].configure(image=image)
            self.image_refs[key] = image
        latest, _, _ = runtime.snapshot()
        self._update_joint_visualization(latest, machine)
        for side, variable in (("left", self.left_angles_var), ("right", self.right_angles_var)):
            state = latest.get(side + "_state")
            label = "左臂" if side == "left" else "右臂"
            if state is not None and len(state.position) >= 3:
                variable.set("%s J2=%+.3f rad   J3(肘)=%+.3f rad" %
                             (label, state.position[1], state.position[2]))
            else:
                variable.set("%s J2/J3：等待反馈" % label)
        phase_text = machine.phase.value
        if machine.marked_failed:
            phase_text += "（已标记失败，继续采集至时限）"
        self.phase_var.set("Episode %d   状态：%s   双臂：%s   转换队列：%d" %
                           (episode_number, phase_text,
                            "保持使能" if arms_enabled else "失能", export_pending))
        if machine.phase == Phase.MANIPULATION and started_at is not None:
            self.countdown_var.set("%.1f 秒" % max(0.0, duration - (time.monotonic() - started_at)))
        elif machine.phase == Phase.RETURN_HOME:
            self.countdown_var.set("正在录制回位")
        else:
            self.countdown_var.set("--")
        self.status_var.set(status)
        if readiness_errors:
            self.device_var.set("预检未通过：" + "；".join(readiness_errors))
        else:
            rates = ", ".join("%s %.1f FPS" % (key, cameras[key].measured_fps())
                              for key in CAMERA_KEYS)
            self.device_var.set("设备已就绪（配置 30 FPS）：" + rates)
        self.set_controls(machine.phase, not readiness_errors, arms_enabled)
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            self.closed = True
            self.enqueue("quit")

    def _update_joint_visualization(self, latest, machine):
        now = time.monotonic()
        if machine.recording:
            self.joint_record_var.set("● REC  正在写入 state/action 和相机帧")
            self.joint_record_label.configure(fg="#c62828")
        else:
            self.joint_record_var.set("○ 未录制  当前数值仅用于预检")
            self.joint_record_label.configure(fg="#455a64")
        sample_history = now - self.last_joint_sample >= 1.0 / 30.0
        if sample_history:
            self.last_joint_sample = now
        for side in SIDES:
            state_message = latest.get(side + "_state")
            action_message = latest.get(side + "_action")
            state = list(state_message.position[:7]) if state_message is not None else []
            action = list(action_message.position[:7]) if action_message is not None else []
            rows = ["关节       反馈值       action       误差"]
            names = ("J1(rad)", "J2(rad)", "J3(rad)", "J4(rad)",
                     "J5(rad)", "J6(rad)", "Gripper")
            for index, name in enumerate(names):
                actual = float(state[index]) if index < len(state) else math.nan
                target = float(action[index]) if index < len(action) else math.nan
                error = target - actual if math.isfinite(actual) and math.isfinite(target) else math.nan
                rows.append("%-8s %+.5f   %+.5f   %+.5f" %
                            (name, actual, target, error))
            self.joint_vars[side].set("\n".join(rows))
            if sample_history and len(state) >= 3 and math.isfinite(float(state[2])):
                target = float(action[2]) if len(action) >= 3 else math.nan
                self.joint_history[side].append((now, float(state[2]), target))
            self._draw_elbow_plot(side, now)

    def _draw_elbow_plot(self, side, now):
        canvas = self.joint_canvases[side]
        canvas.delete("all")
        width = max(canvas.winfo_width(), 640)
        height = max(canvas.winfo_height(), 260)
        left, right, top, bottom = 58, width - 18, 18, height - 34
        values = [value for stamp, actual, target in self.joint_history[side]
                  if stamp >= now - 10.0 for value in (actual, target) if math.isfinite(value)]
        if not values:
            canvas.create_text(width / 2, height / 2, text="等待 J3 反馈",
                               fill="#b0bec5", font=("Sans", 13))
            return
        low, high = min(values), max(values)
        span = max(high - low, 0.1)
        low -= span * 0.15
        high += span * 0.15

        def point(stamp, value):
            x = left + (stamp - (now - 10.0)) / 10.0 * (right - left)
            y = bottom - (value - low) / (high - low) * (bottom - top)
            return x, y

        for index in range(5):
            y = top + index * (bottom - top) / 4.0
            value = high - index * (high - low) / 4.0
            canvas.create_line(left, y, right, y, fill="#263845")
            canvas.create_text(left - 7, y, text="%+.2f" % value,
                               fill="#90a4ae", anchor="e", font=("Monospace", 9))
        for seconds in (0, 2, 4, 6, 8, 10):
            x = left + seconds / 10.0 * (right - left)
            canvas.create_line(x, top, x, bottom, fill="#1d2b34")
            canvas.create_text(x, bottom + 16, text="-%d" % (10 - seconds),
                               fill="#90a4ae", font=("Monospace", 9))
        history = [row for row in self.joint_history[side] if row[0] >= now - 10.0]
        actual_points = [coordinate for stamp, actual, _target in history
                         if math.isfinite(actual)
                         for coordinate in point(stamp, actual)]
        target_points = [coordinate for stamp, _actual, target in history
                         if math.isfinite(target) for coordinate in point(stamp, target)]
        if len(actual_points) >= 4:
            canvas.create_line(*actual_points, fill="#4caf50", width=2, smooth=True)
        if len(target_points) >= 4:
            canvas.create_line(*target_points, fill="#ff9800", width=2, dash=(6, 4), smooth=True)
        latest = history[-1]
        target_text = "%+.4f" % latest[2] if math.isfinite(latest[2]) else "--"
        canvas.create_text(left + 8, top + 8,
                           text="J3 feedback %+.4f rad    action %s rad" %
                           (latest[1], target_text), fill="#eceff1", anchor="nw",
                           font=("Monospace", 10, "bold"))

    def destroy(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass


class RosRuntime:
    def __init__(self, rospy, types, mapping):
        self.rospy = rospy
        self.types = types
        self.mapping = mapping
        self.lock = threading.Lock()
        self.latest = {}
        self.latest_at = {}
        self.localization_since = {side: None for side in SIDES}
        self.writer = None
        self.services = {side: {} for side in SIDES}
        self.publishers = {}
        self.subscribers = []
        self._connect()

    def _connect(self):
        rospy = self.rospy
        JointState = self.types["JointState"]
        LocalizationStatus = self.types["LocalizationStatus"]
        PiperStatusMsg = self.types["PiperStatusMsg"]
        for side in SIDES:
            arm = self.mapping["arms"][side]
            topics = (
                ("%s_state" % side, arm["feedback_topic"], JointState),
                ("%s_action" % side, arm["action_topic"], JointState),
                ("%s_localization" % side, arm["localization_topic"], LocalizationStatus),
                ("%s_status" % side, arm["status_topic"], PiperStatusMsg),
            )
            for key, topic, message_type in topics:
                self.subscribers.append(rospy.Subscriber(
                    topic, message_type, self._callback,
                    callback_args=(key, topic), queue_size=100))
            self.publishers[side] = rospy.Publisher(
                arm["action_topic"], JointState, queue_size=1)

    def bind_services(self):
        for side in SIDES:
            suffix = SUFFIX[side]
            names = {
                "enable": ("/%s_arm/enable_srv_raw" % side, self.types["Enable"]),
                "reset": ("/%s_arm/reset_srv_raw" % side, self.types["Trigger"]),
                "stop": ("/%s_arm/stop_srv_raw" % side, self.types["Trigger"]),
                "gate": ("/%s_arm/teleop/joint_command_smoother/set_enabled" % side,
                         self.types["SetBool"]),
                "trigger": ("/teleop_trigger_%s" % suffix, self.types["Trigger"]),
            }
            for key, (name, service_type) in names.items():
                self.rospy.wait_for_service(name, timeout=20.0)
                self.services[side][key] = self.rospy.ServiceProxy(name, service_type)

    def _callback(self, message, callback_args):
        key, topic = callback_args
        now = time.monotonic()
        with self.lock:
            self.latest[key] = message
            self.latest_at[key] = now
            if key.endswith("_localization"):
                side = key.split("_", 1)[0]
                if message.accurate:
                    self.localization_since[side] = self.localization_since[side] or now
                else:
                    self.localization_since[side] = None
            writer = self.writer
        if writer is not None:
            stamp = getattr(getattr(message, "header", None), "stamp", None)
            if stamp is None or stamp.to_sec() <= 0:
                stamp = self.rospy.Time.now()
            writer.write_ros_message(topic, message, stamp)

    def snapshot(self):
        with self.lock:
            return dict(self.latest), dict(self.latest_at), dict(self.localization_since)

    def attach_writer(self, writer):
        with self.lock:
            self.writer = writer

    def detach_writer(self):
        with self.lock:
            self.writer = None

    def begin_teleop(self, already_enabled=False):
        enabled = []
        try:
            for side in SIDES:
                response = self.services[side]["gate"](True)
                if not response.success:
                    raise RuntimeError("%s smoother refused enable" % side)
            if not already_enabled:
                for side in SIDES:
                    response = self.services[side]["reset"]()
                    if not response.success:
                        raise RuntimeError("%s reset rejected" % side)
                self.rospy.sleep(1.0)
                for side in SIDES:
                    response = self.services[side]["enable"](True)
                    if not response.enable_response:
                        raise RuntimeError("%s enable rejected" % side)
                    enabled.append(side)
            for side in SIDES:
                self.services[side]["trigger"]()
        except Exception:
            for side in enabled:
                try:
                    self.services[side]["enable"](False)
                except Exception:
                    pass
            raise

    def begin_home(self):
        errors = []
        for side in SIDES:
            try:
                response = self.services[side]["gate"](False)
                if not response.success:
                    errors.append("%s smoother gate rejected close" % side)
            except Exception as error:
                errors.append("%s gate: %s" % (side, error))
        for side in SIDES:
            try:
                self.services[side]["trigger"]()
            except Exception as error:
                errors.append("%s trigger: %s" % (side, error))
        if errors:
            raise RuntimeError("; ".join(errors))

    def publish_home(self, side, target, speed, gripper):
        JointState = self.types["JointState"]
        message = JointState()
        message.header.stamp = self.rospy.Time.now()
        message.name = ["joint%d" % index for index in range(1, 7)]
        # The configured support pose intentionally specifies only the arm.
        # Preserve the latest measured gripper opening while still recording a
        # complete seven-value action vector.
        message.position = list(target) + [float(gripper)]
        message.velocity = [0.0] * 6 + [float(speed)]
        self.publishers[side].publish(message)
        with self.lock:
            self.latest[side + "_action"] = message
            self.latest_at[side + "_action"] = time.monotonic()

    def disable_both(self):
        errors = []
        for side in SIDES:
            try:
                response = self.services[side]["enable"](False)
                if not response.enable_response:
                    errors.append("%s disable rejected" % side)
            except Exception as error:
                errors.append("%s disable: %s" % (side, error))
        if errors:
            raise RuntimeError("; ".join(errors))

    def stop_both(self):
        for side in SIDES:
            try:
                self.services[side]["gate"](False)
            except Exception:
                pass
            try:
                self.services[side]["stop"]()
            except Exception:
                pass

    def recover(self, side):
        response = self.services[side]["reset"]()
        if not response.success:
            return False
        self.rospy.sleep(1.0)
        response = self.services[side]["enable"](True)
        return bool(response.enable_response)


def wait_for_cameras(cameras, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(camera.latest()[0] is not None for camera in cameras.values()):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("not all cameras produced a frame")
    time.sleep(2.2)
    rates = {key: camera.measured_fps() for key, camera in cameras.items()}
    slow = {key: value for key, value in rates.items() if value < 27.0}
    if slow:
        raise RuntimeError("cameras did not sustain 30 FPS: %r" % slow)
    return rates


def verify_topology(rospy, mapping):
    import rosgraph
    master = rosgraph.Master("/pi05_data_collection_preflight")
    publishers, subscribers, _ = master.getSystemState()
    publishers = {topic: sorted(nodes) for topic, nodes in publishers}
    subscribers = {topic: sorted(nodes) for topic, nodes in subscribers}
    for side in SIDES:
        arm = mapping["arms"][side]
        ik = "/%s_arm/teleop/ik_target_raw" % side
        command = arm["action_topic"]
        expected_ik = ["/%s_arm/teleop/ik" % side]
        expected_command = sorted([
            "/%s_arm/teleop/joint_command_smoother" % side,
            "/pi05_data_collection",
        ])
        if publishers.get(ik) != expected_ik:
            raise RuntimeError("unexpected IK publishers on %s: %r" % (ik, publishers.get(ik)))
        if publishers.get(command) != expected_command:
            raise RuntimeError("unexpected command publishers on %s: %r" %
                               (command, publishers.get(command)))
        driver = "/%s_arm/piper_driver_raw" % side
        if driver not in subscribers.get(command, []):
            raise RuntimeError("driver is not subscribed to %s" % command)
        pose = arm["pika_pose_topic"]
        teleop = "/%s_arm/teleop/teleop" % side
        if teleop not in subscribers.get(pose, []):
            raise RuntimeError("teleop is not subscribed to %s" % pose)


def data_snapshot(runtime, cameras, freshness, require_action=True):
    now = time.monotonic()
    latest, updated, localization_since = runtime.snapshot()
    images = {}
    ages = {}
    missing = [key for key in CAMERA_KEYS if key not in cameras]
    if missing:
        raise RuntimeError("missing cameras: %s" % ", ".join(missing))
    for key in CAMERA_KEYS:
        camera = cameras[key]
        image, age = camera.latest()
        if image is None or age > freshness:
            raise RuntimeError("%s camera is stale (%.3fs)" % (key, age))
        images[key] = image
        ages["camera_" + key] = age
    for side in SIDES:
        for suffix in ("state", "action"):
            key = side + "_" + suffix
            if suffix == "action" and not require_action:
                continue
            age = now - updated.get(key, -math.inf)
            if key not in latest or age > freshness:
                raise RuntimeError("%s is stale" % key)
            ages[key] = age
        loc_key = side + "_localization"
        loc_age = now - updated.get(loc_key, -math.inf)
        if loc_key not in latest or loc_age > max(freshness, 0.25):
            raise RuntimeError("%s localization is stale" % side)
        if not latest[loc_key].accurate:
            raise RuntimeError("%s localization is inaccurate" % side)
        ages[loc_key] = loc_age
    state = dual_vector(latest["left_state"], latest["right_state"])
    action = None
    if require_action:
        action = dual_vector(latest["left_action"], latest["right_action"])
    return images, state, action, ages, localization_since


def feedback_readiness(runtime, freshness):
    """Return user-facing readiness errors without raising or moving hardware."""
    now = time.monotonic()
    latest, updated, localization_since = runtime.snapshot()
    errors = []
    for side, label in (("left", "左臂"), ("right", "右臂")):
        state_key = side + "_state"
        if state_key not in latest or now - updated.get(state_key, -math.inf) > freshness:
            errors.append(label + "反馈未就绪")
        elif len(latest[state_key].position) < 7:
            errors.append(label + "反馈不足 7 维")
        localization_key = side + "_localization"
        if (localization_key not in latest or
                now - updated.get(localization_key, -math.inf) > max(freshness, 0.25)):
            errors.append(label + " Pika 定位无新数据")
        elif not latest[localization_key].accurate:
            errors.append(label + " Pika 定位不准确")
        elif (localization_since[side] is None or
              now - localization_since[side] < 0.5):
            errors.append(label + " Pika 定位尚未连续稳定 0.5 秒")
    return errors


def camera_readiness(cameras, base_errors, opened_at, freshness):
    errors = dict(base_errors)
    now = time.monotonic()
    for key in CAMERA_KEYS:
        camera = cameras.get(key)
        if camera is None:
            errors.setdefault(key, "%s：未发现彩色 UVC 节点" % key)
            continue
        frame, age = camera.latest()
        if camera.error:
            errors[key] = "%s：%s" % (key, camera.error)
        elif frame is None:
            errors[key] = "%s：等待首帧" % key
        elif age > freshness:
            errors[key] = "%s：画面已中断 %.2f 秒" % (key, age)
        elif now - opened_at < 2.2:
            errors[key] = "%s：正在测量实际帧率" % key
        elif now - opened_at >= 2.2 and camera.measured_fps() < MIN_DECODED_CAMERA_FPS:
            errors[key] = "%s：帧率仅 %.1f FPS" % (key, camera.measured_fps())
        else:
            errors.pop(key, None)
    return errors


def main(argv=None):
    args = parse_args(argv)
    task = (args.task or "").strip()
    dataset_root = args.output_root / args.dataset_name
    dataset_root.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(str(dataset_root)).free / (1024 ** 3)
    if free_gb < args.minimum_free_gb:
        print("only %.1f GiB free; %.1f GiB required" % (free_gb, args.minimum_free_gb),
              file=sys.stderr)
        return 3
    try:
        homes = load_home(args.home_config)
        mapping = load_collection_mapping(args.mapping_config)
    except Exception as error:
        print("invalid home or collection mapping: %s" % error, file=sys.stderr)
        return 2

    import rosbag
    import rospy
    from data_msgs.msg import LocalizationStatus
    from piper_msgs.msg import PiperStatusMsg
    from piper_msgs.srv import Enable
    from sensor_msgs.msg import CompressedImage, JointState
    from std_srvs.srv import SetBool, Trigger

    types = locals()
    rospy.init_node("pi05_data_collection", anonymous=False, disable_signals=True)
    runtime = RosRuntime(rospy, types, mapping)
    try:
        dashboard = OperatorDashboard(
            args.dataset_name, task, args.duration, startup_only=args.startup_only)
    except tk.TclError as error:
        print("could not open data-collection UI: %s" % error, file=sys.stderr)
        return 3
    exporter = ExportWorker(
        args.lerobot_python, args.exporter, dataset_root / "lerobot",
        args.repo_id or ("local/" + args.dataset_name))
    machine = EpisodeStateMachine()
    episode_writer = None
    episode_number = 1
    message = "正在检查相机、机械臂反馈和 Pika 定位……"
    requested_exit = False
    home_started_at = None
    home_progress = {
        side: HomeProgress(homes[side][0], args.home_tolerance, args.stable_seconds)
        for side in SIDES
    }
    recovery_threads = {}
    episode_fault_reason = ""
    sampling_disabled = False
    locked_hazard = False
    arms_enabled = False
    episode_duration = args.duration
    cameras = {}
    camera_open_errors = {}
    cameras_opened_at = time.monotonic()
    control_error = ""

    def reload_cameras():
        nonlocal cameras, camera_open_errors, cameras_opened_at, message
        for camera in cameras.values():
            camera.close()
        cameras = {}
        try:
            devices, camera_open_errors = resolve_camera_devices(args.camera_config)
        except Exception as error:
            camera_open_errors = {key: "相机配置错误：%s" % error for key in CAMERA_KEYS}
            devices = {}
        for key, device in devices.items():
            try:
                cameras[key] = CameraStream(
                    key, device, args.width, args.height, args.fps,
                    args.top_rotation if key == "top" else "none",
                    mapping["cameras"][key]["pixel_format"])
            except Exception as error:
                camera_open_errors[key] = "%s：%s" % (key, error)
        cameras_opened_at = time.monotonic()
        if camera_open_errors:
            message = "相机未全部就绪；处理占用或重新插拔后点击“重新检测相机”"
        else:
            message = "相机已打开，正在测量实际帧率……"

    def close_episode(outcome, reason, home_confirmed):
        nonlocal episode_writer, episode_number, message
        runtime.detach_writer()
        path = episode_writer.close(outcome.value, reason, home_confirmed)
        if outcome == Outcome.SUCCESS and path is not None:
            exporter.enqueue(path)
            message = "%s saved; LeRobot conversion queued" % episode_writer.episode_id
        elif outcome == Outcome.FAILURE:
            message = "%s retained as failure" % episode_writer.episode_id
        else:
            message = "episode discarded after safe home"
        episode_writer = None
        episode_number += 1

    try:
        reload_cameras()
        try:
            verify_topology(rospy, mapping)
            runtime.bind_services()
        except Exception as error:
            control_error = "控制拓扑/服务未就绪：%s" % error
            message = control_error
        next_sample = time.monotonic()
        next_ui = time.monotonic()
        while not rospy.is_shutdown() and machine.phase != Phase.STOPPED:
            now = time.monotonic()
            current_camera_errors = camera_readiness(
                cameras, camera_open_errors, cameras_opened_at, args.freshness)
            readiness_errors = list(current_camera_errors.values())
            if control_error:
                readiness_errors.append(control_error)
            else:
                readiness_errors.extend(feedback_readiness(runtime, args.freshness))
            if (not readiness_errors and machine.phase == Phase.IDLE and
                    (message.startswith("正在检查") or
                     message.startswith("相机已打开"))):
                message = ("可视化预检通过；startup-only 禁止运动，按 Q 退出" if
                           args.startup_only else "预检通过；可编辑任务和时长，然后开始采集")

            if machine.duration_expired(now, episode_duration):
                try:
                    machine.request_return(Outcome.SUCCESS)
                    timed_outcome = machine.requested_outcome
                    runtime.begin_home()
                    home_started_at = now
                    for tracker in home_progress.values():
                        tracker.reset(now)
                    message = ("已到设定时长；本条按%s归档，继续录制自动回位" %
                               ("失败" if timed_outcome == Outcome.FAILURE else "成功"))
                except Exception as error:
                    locked_hazard = True
                    machine.fail_home()
                    close_episode(Outcome.FAILURE, "could not begin timed return: %s" % error,
                                  False)
                    message = "锁定：无法安全切换到自动回位：%s" % error

            if machine.phase == Phase.RETURN_HOME:
                if now - home_started_at > args.home_timeout:
                    locked_hazard = True
                    machine.fail_home()
                    runtime.detach_writer()
                    close_episode(Outcome.FAILURE, "return-home timeout", False)
                    message = "锁定：自动回位超时，机械臂可能仍使能"
                else:
                    latest, updated, _ = runtime.snapshot()
                    home_failure = None
                    for side in SIDES:
                        target, speed = homes[side]
                        state_key = side + "_state"
                        if state_key not in latest or now - updated.get(state_key, -math.inf) > 1.0:
                            home_failure = "%s feedback lost during return-home" % side
                            break
                        try:
                            if len(latest[state_key].position) < 7:
                                raise ValueError("feedback has no gripper position")
                            runtime.publish_home(
                                side, target, speed, latest[state_key].position[6])
                            home_progress[side].observe(latest[state_key].position, now)
                            if home_progress[side].needs_recovery(now):
                                home_progress[side].begin_recovery(now)
                                def recover(which=side):
                                    ok = runtime.recover(which)
                                    try:
                                        home_progress[which].finish_recovery(time.monotonic(), ok)
                                    except SessionError:
                                        pass
                                recovery_threads[side] = threading.Thread(target=recover, daemon=True)
                                recovery_threads[side].start()
                        except (ValueError, SessionError) as error:
                            home_failure = "%s: %s" % (side, error)
                            break
                    if home_failure:
                        locked_hazard = True
                        machine.fail_home()
                        close_episode(Outcome.FAILURE, home_failure, False)
                        message = "锁定：" + home_failure
                    elif all(tracker.complete for tracker in home_progress.values()):
                        outcome = machine.complete_home()
                        close_episode(outcome, episode_fault_reason, True)
                        if requested_exit:
                            message += "；双臂仍保持使能，请按 E 手动失能后退出"
                        else:
                            message += "；双臂保持使能，可以采集下一条"

            if machine.recording and now >= next_sample and not sampling_disabled:
                next_sample += 1.0 / args.fps
                if next_sample < now - 1.0 / args.fps:
                    next_sample = now + 1.0 / args.fps
                try:
                    images, state, action, ages, _ = data_snapshot(
                        runtime, cameras, args.freshness, require_action=True)
                    episode_writer.add_sample(
                        rospy.Time.now(), now - machine.started_at,
                        machine.phase.value, images, state, action, ages)
                except Exception as error:
                    episode_fault_reason = "data fault: %s" % error
                    sampling_disabled = True
                    machine.requested_outcome = Outcome.FAILURE
                    if machine.phase == Phase.MANIPULATION:
                        machine.request_return(Outcome.FAILURE)
                        runtime.begin_home()
                        home_started_at = now
                        for tracker in home_progress.values():
                            tracker.reset(now)
                        message = "数据异常；保留原始消息并继续安全回位：%s" % error
                    else:
                        message = "回位录制发生数据异常；安全回位继续：%s" % error

            command = None
            if now >= next_ui:
                next_ui = now + UI_REFRESH_SECONDS
                dashboard.update(
                    cameras, runtime, machine, episode_number, episode_duration,
                    machine.started_at, message, current_camera_errors,
                    readiness_errors, exporter.pending(), arms_enabled)
                command = dashboard.take_command()
            if command is None:
                time.sleep(0.002)
                continue
            if command == "stop":
                locked_hazard = True
                runtime.stop_both()
                if episode_writer is not None:
                    machine.emergency_stop()
                    close_episode(Outcome.FAILURE, "operator emergency software stop", False)
                else:
                    machine.emergency_stop()
                message = "锁定：已发送软件急停，请原地检查双臂"
            elif machine.phase == Phase.RETURN_HOME:
                message = "正在录制自动回位；只有 X 软件急停可以中断"
            elif command == "retry_cameras" and machine.phase == Phase.IDLE:
                reload_cameras()
            elif command == "disable":
                if machine.phase in (Phase.IDLE, Phase.LOCKED) and arms_enabled:
                    try:
                        runtime.disable_both()
                        arms_enabled = False
                        message = "双臂已由操作员手动失能"
                        if requested_exit and machine.phase == Phase.IDLE:
                            machine.stop()
                    except Exception as error:
                        locked_hazard = True
                        machine.emergency_stop()
                        message = "锁定：手动失能失败：%s" % error
            elif command == "start" and machine.phase == Phase.IDLE:
                if args.startup_only:
                    message = "当前是 startup-only，只做可视化预检，不允许使能或运动"
                    continue
                if requested_exit:
                    message = "已经请求退出；请先按 E 手动失能"
                    continue
                free_gb = shutil.disk_usage(str(dataset_root)).free / (1024 ** 3)
                if free_gb < args.minimum_free_gb:
                    message = "未开始：磁盘仅剩 %.1f GiB" % free_gb
                    continue
                try:
                    control_attempted = False
                    task, episode_duration = dashboard.values()
                    current_camera_errors = camera_readiness(
                        cameras, camera_open_errors, cameras_opened_at, args.freshness)
                    if current_camera_errors:
                        raise RuntimeError("三路相机尚未就绪")
                    if control_error:
                        raise RuntimeError(control_error)
                    control_readiness = feedback_readiness(runtime, args.freshness)
                    if control_readiness:
                        raise RuntimeError("；".join(control_readiness))
                    verify_topology(rospy, mapping)
                    _, _, _, _, loc_since = data_snapshot(
                        runtime, cameras, args.freshness, require_action=False)
                    if not all(loc_since[side] is not None and now - loc_since[side] >= 0.5
                               for side in SIDES):
                        raise RuntimeError("localization was not continuously accurate for 0.5s")
                    control_attempted = True
                    runtime.begin_teleop(already_enabled=arms_enabled)
                    arms_enabled = True
                    deadline = time.monotonic() + 3.0
                    while time.monotonic() < deadline:
                        try:
                            data_snapshot(runtime, cameras, args.freshness, require_action=True)
                            break
                        except RuntimeError:
                            time.sleep(0.03)
                    else:
                        raise RuntimeError("fresh dual-arm actions did not appear after trigger")
                    episode_writer = EpisodeWriter(
                        dataset_root, task, args.fps, args.width, args.height,
                        rosbag, CompressedImage)
                    runtime.attach_writer(episode_writer)
                    machine.start(task, time.monotonic())
                    episode_fault_reason = ""
                    sampling_disabled = False
                    next_sample = time.monotonic()
                    message = "正在录制人工操作；默认到时成功，按 F 可标记本条失败"
                except Exception as error:
                    if control_attempted or episode_writer is not None or machine.phase != Phase.IDLE:
                        locked_hazard = True
                        runtime.stop_both()
                        machine.emergency_stop()
                        message = "锁定：启动 episode 后发生故障：%s" % error
                    else:
                        message = "未开始：%s" % error
            elif command == "failure" and machine.phase == Phase.MANIPULATION:
                machine.mark_failure()
                if not episode_fault_reason:
                    episode_fault_reason = "operator marked failure"
                message = "本条已标记失败；继续采集到设定时长后自动回位并进入失败目录"
            elif command in ("success", "discard"):
                if machine.phase == Phase.MANIPULATION:
                    outcome = {"success": Outcome.SUCCESS, "discard": Outcome.DISCARD}[command]
                    machine.request_return(outcome)
                    outcome = machine.requested_outcome
                    try:
                        runtime.begin_home()
                        home_started_at = time.monotonic()
                        for tracker in home_progress.values():
                            tracker.reset(home_started_at)
                        message = "%s；正在把自动回位录入同一条 episode" % outcome.value
                    except Exception as error:
                        locked_hazard = True
                        machine.fail_home()
                        close_episode(Outcome.FAILURE, "could not isolate home command: %s" % error,
                                      False)
                        message = "锁定：无法进入自动回位"
            elif command == "quit":
                if machine.phase == Phase.MANIPULATION:
                    requested_exit = True
                    machine.request_return(Outcome.DISCARD)
                    runtime.begin_home()
                    home_started_at = time.monotonic()
                    for tracker in home_progress.values():
                        tracker.reset(home_started_at)
                    message = "已请求退出；先把安全回位录完再退出"
                elif machine.phase == Phase.IDLE and arms_enabled:
                    requested_exit = True
                    message = "双臂仍保持使能；请按 E 手动失能后退出"
                elif machine.phase in (Phase.IDLE, Phase.LOCKED):
                    machine.stop()
    except KeyboardInterrupt:
        if machine.phase == Phase.IDLE:
            machine.stop()
        else:
            locked_hazard = True
            runtime.stop_both()
            machine.emergency_stop()
            if episode_writer is not None:
                close_episode(Outcome.FAILURE, "keyboard interrupt; software stop sent", False)
    except Exception as error:
        print("data collection failed: %s" % error, file=sys.stderr)
        runtime.stop_both()
        if episode_writer is not None:
            runtime.detach_writer()
            try:
                close_episode(Outcome.FAILURE, "collector exception: %s" % error, False)
            except Exception:
                episode_writer.abort()
        return 4
    finally:
        dashboard.destroy()
        for camera in cameras.values():
            camera.close()
        exporter.close()
    return 4 if locked_hazard or machine.phase == Phase.LOCKED or arms_enabled else 0


if __name__ == "__main__":
    sys.exit(main())
