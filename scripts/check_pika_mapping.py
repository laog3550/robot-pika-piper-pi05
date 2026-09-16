#!/usr/bin/env python3
"""现场确认 Pika 手柄与 ROS 左右的对应关系，避免左右串侧。

判据（自洽、不依赖操作员的记忆）：
  在一次采样窗口内，由 IMU 峰值找出【正在被移动的那一侧】，再检查该侧的位姿是否
  同步响应。
    - 同一侧同时响应  -> 被移动手柄的数据完整地落在它当前被分配的侧，可用于遥操作
    - 位姿不响应      -> 光学定位没跟上这只手柄，遥操作会表现为“手柄动了臂不动”
    - 两侧都在动      -> 无法区分，提示操作员分次移动

用法：
  scripts/check_pika_mapping.py --duration 10     # 采样窗口内只移动一只手柄
  scripts/check_pika_mapping.py --duration 10 --record   # 通过后写入本机映射配置

辅助用法：先让操作员只动【某一只】手柄，工具据此得出该手柄被分配到了哪一侧；
换另一只手柄重复一次，就能确认左右是否与操作直觉一致（即 mapping_order 取值）。
"""
import argparse
import math
import sys
import threading
import time

EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3

IMU_MOVING = 0.30      # rad/s：明显转动
IMU_STILL = 0.10       # rad/s：判定为静止
POSE_MOVING = 0.02     # m：与 check_pika_localization --require-motion 一致
MAPPING_CONFIG = "config/pika-mapping.env"
UNIT_CONFIG = "config/pi05.env"


class Observation:
    """只保存统计量，不保存原始数值，避免把设备数据写进日志。"""
    def __init__(self):
        self.lock = threading.Lock()
        self.count = 0
        self.peak = 0.0
        self.first = None
        self.last = None

    def add(self, magnitude, stamp):
        with self.lock:
            self.count += 1
            self.peak = max(self.peak, abs(magnitude))
            if self.first is None:
                self.first = stamp
            self.last = stamp

    def snapshot(self):
        with self.lock:
            return self.count, self.peak, self.first, self.last


class Span:
    """记录三维量的范围，用于表示位移大小。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.count = 0
        self.low = None
        self.high = None

    def add(self, values):
        with self.lock:
            self.count += 1
            if self.low is None:
                self.low = list(values)
                self.high = list(values)
                return
            for index, value in enumerate(values):
                self.low[index] = min(self.low[index], value)
                self.high[index] = max(self.high[index], value)

    def range(self):
        with self.lock:
            if self.count < 5 or self.low is None:
                return None
            return max(high - low for low, high in zip(self.low, self.high))


def collect(duration, ros):
    rospy, PoseStamped, Imu = ros
    imu = {"left": Observation(), "right": Observation()}
    pose = {"left": Span(), "right": Span()}
    subscribers = []
    for side in ("left", "right"):
        subscribers.append(rospy.Subscriber(
            "/pika_%s/imu/data" % side[0], Imu,
            lambda message, key=side: imu[key].add(
                math.sqrt(message.angular_velocity.x ** 2 +
                          message.angular_velocity.y ** 2 +
                          message.angular_velocity.z ** 2),
                rospy.Time.now().to_sec()),
            queue_size=500))
        subscribers.append(rospy.Subscriber(
            "/pi05/pika_input/raw/%s/pose" % side, PoseStamped,
            lambda message, key=side: pose[key].add(
                (message.pose.position.x, message.pose.position.y,
                 message.pose.position.z)),
            queue_size=200))

    started = time.monotonic()
    while not rospy.is_shutdown() and time.monotonic() - started < duration:
        time.sleep(0.1)
    finished = time.monotonic()
    for subscriber in subscribers:
        subscriber.unregister()
    return imu, pose, started, finished


def decide(imu, pose, started, finished):
    """返回 (状态, 正在移动的侧或 None, 说明)。"""
    spans = {side: pose[side].range() for side in ("left", "right")}
    moving_imu = []
    still_imu = []
    for side in ("left", "right"):
        count, peak, first, last = imu[side].snapshot()
        if count < 10 or first is None:
            return "nodata", None, "%s 侧 IMU 没有样本" % side
        # IMU 必须覆盖整个窗口，否则可能只是启动瞬间的抖动
        if last - first < (finished - started) * 0.8:
            return "nodata", None, "%s 侧 IMU 只覆盖了部分时间窗口" % side
        if peak >= IMU_MOVING:
            moving_imu.append(side)
        elif peak <= IMU_STILL:
            still_imu.append(side)
    if not moving_imu:
        return "no_motion", None, "两侧 IMU 都没有检测到转动（峰值低于 %.2f rad/s）" % IMU_MOVING
    if len(moving_imu) == 2:
        return "both_moving", None, "两侧 IMU 同时在转动，无法区分"
    side = moving_imu[0]
    if spans[side] is None:
        return "nodata", side, "%s 侧位姿样本不足" % side
    if spans[side] < POSE_MOVING:
        return "pose_frozen", side, (
            "%s 侧 IMU 在动但位姿只有 %.4f m（低于 %.2f m）：光学定位没跟上这只手柄"
            % (side, spans[side], POSE_MOVING))
    return "ok", side, "只有 %s 侧在动，且位姿同步响应 %.4f m" % (side, spans[side])


def report(imu, pose, started, finished):
    print("%-8s %-8s %-18s %s" % ("侧别", "样本", "IMU 峰值(rad/s)", "位姿范围(m)"))
    print("-" * 58)
    for side in ("left", "right"):
        count, peak, _first, _last = imu[side].snapshot()
        span = pose[side].range()
        print("%-8s %-8d %-18.4f %s" % (
            side, count, peak, "样本不足" if span is None else "%.6f" % span))
    print()


def master_reachable(timeout=3.0):
    """rospy.init_node 默认会无限等待 master，这里先快速判断一次。"""
    import xmlrpc.client
    import rosgraph
    uri = rosgraph.get_master_uri()
    try:
        proxy = xmlrpc.client.ServerProxy(uri, allow_none=True)
        proxy.getUri("/pi05_mapping_preflight")
        return True
    except Exception:
        return False


def record(moving_side):
    """把确认结果写入本机配置。"""
    from pathlib import Path
    path = Path(MAPPING_CONFIG)
    if not path.parent.is_dir():
        print("找不到配置目录：%s" % path.parent, file=sys.stderr)
        return False
    if path.exists():
        backup = Path(str(path) + ".save")
        print("已存在 %s，备份为 %s" % (path, backup))
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(
        "# 由 scripts/check_pika_mapping.py --record 生成，含机器相关取值，不要提交。\n"
        "# 现场实测：移动 %s 侧手柄时，%s 侧 IMU 与位姿同步响应。\n"
        "# 启动 input-only 时应显式使用下面这个 mapping_order，不要再靠记忆试错。\n"
        "# PI05_PIKA_MAPPING_ORDER=direct|swapped\n"
        % (moving_side, moving_side),
        encoding="utf-8")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--record", action="store_true",
                        help="通过后写入 %s" % MAPPING_CONFIG)
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be positive and finite")

    try:
        import rospy
        from geometry_msgs.msg import PoseStamped
        from sensor_msgs.msg import Imu
    except ImportError:
        print("ros python packages unavailable；先加载 ROS 环境再运行", file=sys.stderr)
        return EXIT_ENVIRONMENT

    if not master_reachable():
        import rosgraph
        print("连不上 ROS master（%s）：请先启动 input-only 或 roscore。"
              % rosgraph.get_master_uri(), file=sys.stderr)
        return EXIT_ENVIRONMENT

    try:
        rospy.init_node("pi05_pika_mapping_check", anonymous=True,
                        disable_signals=True, timeout=10.0)
    except rospy.exceptions.ROSException as error:
        print("无法在 10 秒内注册到 master：%s" % error, file=sys.stderr)
        return EXIT_ENVIRONMENT
    print("采样 %.0f 秒。请【只移动一只手柄】（来回平移并翻转手腕），另一只完全不动。"
          % args.duration)
    print("开始。\n")

    imu, pose, started, finished = collect(args.duration, (rospy, PoseStamped, Imu))
    report(imu, pose, started, finished)
    status, side, message = decide(imu, pose, started, finished)
    print("结论：%s" % message)

    if status == "ok":
        print()
        print("这只被移动的手柄当前被分配为【%s】侧。" % side)
        print("请用它和遥操作对照：若它就是你操作 %s 臂时想用的那只，则左右映射正确；"
              % side)
        print("若它其实是另一只手的设备，说明 mapping_order 需要取反后重启 input-only。")
        print("两只手柄各测一次（分开测），即可确认 direct / swapped 哪个取值正确。")
        if args.record:
            if record(side):
                print("已写入 %s（当前为空模板，请按实测填入 mapping_order）。" % MAPPING_CONFIG)
        return 0

    if status in ("pose_frozen", "both_moving", "no_motion", "nodata"):
        if args.record:
            print("未通过，未写配置。", file=sys.stderr)
        return EXIT_FAILED
    return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
