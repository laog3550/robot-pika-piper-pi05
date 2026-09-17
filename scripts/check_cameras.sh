#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/check_cameras.sh [--discover] [--config PATH]
                                [--sysfs-root PATH] [--udev-root PATH]

只读校验 PI05 的角色相机映射：左右腕部为 Orbbec Dabai DC1（UVC 彩色半边 +
OpenNI 协议深度半边），顶部为 Intel RealSense。脚本不打开 /dev 节点、不加载
Orbbec SDK、不调用 sudo、不写任何设备。

默认读取 Git 忽略的 config/cameras.env。未填写的角色跳过并给出警告，因此
只追了一条线的现场也能检查。序列号只做比对，输出始终脱敏（形如 ***CW）。

--discover 列出当前在线候选相机（脱敏），用于填写 config/cameras.env。

判断依据（现场已核实）：
  * Dabai DC1 的深度半边 2bc5:0657 没有 USB 序列号，分左右必须靠彩色半边
    2bc5:0557 的序列号或 USB 物理端口；
  * 使用 Orbbec SDK 期间它会接管彩色接口，此时 uvcvideo 会解绑、/dev/videoN
    消失，本脚本只把它记为警告，不算失败；
  * D455/D405 必须挂在 USB3 端口，USB2 上深度带宽不足，默认判为失败。

Exit codes: 0 通过（允许警告）；1 存在不匹配；2 参数错误；
3 配置或环境错误；4 缺少命令。
EOF
}

repo_root=$(pi05_repo_root)
config_file="$repo_root/config/cameras.env"
sysfs_root=/sys
udev_root=/run/udev/data
discover=false

while (($#)); do
  case "$1" in
    --discover)
      discover=true
      shift
      ;;
    --config)
      (($# >= 2)) || pi05_die 2 '--config requires a path'
      config_file="$2"
      shift 2
      ;;
    --sysfs-root)
      (($# >= 2)) || pi05_die 2 '--sysfs-root requires a path'
      sysfs_root="$2"
      shift 2
      ;;
    --udev-root)
      (($# >= 2)) || pi05_die 2 '--udev-root requires a path'
      udev_root="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      pi05_die 2 "unknown argument: $1"
      ;;
  esac
done

[[ -d "$sysfs_root/bus/usb/devices" ]] ||
  pi05_die 3 "USB sysfs tree not readable: $sysfs_root/bus/usb/devices"

# ---------------------------------------------------------------- helpers ----

usb_dir() { printf '%s/bus/usb/devices/%s' "$sysfs_root" "$1"; }

usb_attr() {
  local attribute
  attribute="$(usb_dir "$1")/$2"
  [[ -r "$attribute" ]] && cat "$attribute" 2>/dev/null || true
}

usb_present() { [[ -d "$(usb_dir "$1")" ]]; }

parent_port() {
  local port="$1"
  if [[ "$port" == *.* ]]; then
    printf '%s' "${port%.*}"
  else
    printf '%s' "$port"
  fi
}

mask_serial() {
  local value="$1"
  if [[ -z "$value" ]]; then
    printf '(空)'
  elif ((${#value} <= 2)); then
    printf '**'
  else
    printf '***%s' "${value: -2}"
  fi
}

interface_drivers() {
  local port="$1" iface target
  for iface in "$sysfs_root"/bus/usb/devices/"$port":*; do
    [[ -d "$iface" ]] || continue
    [[ -L "$iface/driver" ]] || continue
    target=$(readlink "$iface/driver" 2>/dev/null || true)
    [[ -n "$target" ]] && printf '%s\n' "$(basename "$target")"
  done
}

interface_driver_summary() {
  local summary
  summary=$(interface_drivers "$1" | sort -u | paste -sd, - 2>/dev/null || true)
  printf '%s' "${summary:--}"
}

video_node_count() {
  local port="$1" iface total=0 found
  for iface in "$sysfs_root"/bus/usb/devices/"$port":*; do
    [[ -d "$iface/video4linux" ]] || continue
    found=$(find "$iface/video4linux" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l)
    total=$((total + found))
  done
  printf '%s' "$total"
}

udev_db_files_for_serial() {
  local serial="$1" f
  [[ -d "$udev_root" ]] || return 0
  for f in "$udev_root"/*; do
    [[ -f "$f" ]] || continue
    if grep -q "E:ID_SERIAL_SHORT=$serial\$" "$f" 2>/dev/null; then
      printf '%s\n' "$f"
    fi
  done
}

# Prints one of: by-id | no-by-id | absent. Always returns 0 so callers stay
# compatible with set -e/pipefail (do not test this through a pipe).
serial_udev_state() {
  local serial="$1" f seen=0
  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    seen=1
    if grep -qE '^S:v4l/by-id/.*-video-index0$' "$f"; then
      printf 'by-id'
      return 0
    fi
  done < <(udev_db_files_for_serial "$serial")
  if ((seen)); then
    printf 'no-by-id'
  else
    printf 'absent'
  fi
  return 0
}

realsense_product_id() {
  case "$1" in
    realsense_d455) printf '0b5c' ;;
    realsense_d405) printf '0b5b' ;;
    realsense_d435i) printf '0b3a' ;;
    *) return 1 ;;
  esac
}

# ----------------------------------------------------------------- config ----

declare -A cfg=()

camera_config_keys='PI05_CAMERA_LEFT_WRIST_MODEL PI05_CAMERA_LEFT_WRIST_RGB_USB_PORT
PI05_CAMERA_LEFT_WRIST_DEPTH_USB_PORT PI05_CAMERA_LEFT_WRIST_SERIAL
PI05_CAMERA_RIGHT_WRIST_MODEL PI05_CAMERA_RIGHT_WRIST_RGB_USB_PORT
PI05_CAMERA_RIGHT_WRIST_DEPTH_USB_PORT PI05_CAMERA_RIGHT_WRIST_SERIAL
PI05_CAMERA_TOP_MODEL PI05_CAMERA_TOP_USB_PORT PI05_CAMERA_TOP_SERIAL
PI05_CAMERA_TOP_REQUIRE_USB3'

load_camera_config() {
  local file="$1" line key value allowed
  local -A known=()
  for allowed in $camera_config_keys; do known["$allowed"]=1; done

  while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%%#*}
    line=${line//$'\r'/}
    [[ -n "${line//[[:space:]]/}" ]] || continue
    [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=([-A-Za-z0-9_./:+]*)$ ]] ||
      pi05_die 3 "unsafe or invalid configuration line in $file"
    key=${BASH_REMATCH[1]}
    value=${BASH_REMATCH[2]}
    [[ -n "${known[$key]:-}" ]] || pi05_die 3 "unknown configuration key: $key"
    cfg["$key"]="$value"
  done <"$file"
}

# --------------------------------------------------------------- discovery ----

discover_cameras() {
  local dir port vid pid product speed serial nodes
  printf '%-10s %-11s %-29s %-7s %-13s %-9s %s\n' \
    PORT VID:PID PRODUCT SPEED SERIAL NODES DRIVER
  for dir in "$sysfs_root"/bus/usb/devices/*/; do
    [[ -r "$dir/idVendor" ]] || continue
    port=$(basename "$dir")
    vid=$(cat "$dir/idVendor" 2>/dev/null || true)
    pid=$(cat "$dir/idProduct" 2>/dev/null || true)
    product=$(cat "$dir/product" 2>/dev/null || true)
    case "$vid" in
      2bc5) ;;
      8086)
        [[ "$product" == *RealSense* ]] || continue
        ;;
      1bcf) ;;
      *) continue ;;
    esac
    speed=$(cat "$dir/speed" 2>/dev/null || true)
    serial=$(cat "$dir/serial" 2>/dev/null || true)
    nodes=$(video_node_count "$port")
    printf '%-10s %-11s %-29s %-7s %-13s %-9s %s\n' \
      "$port" "$vid:$pid" "${product:0:29}" "${speed:-?}" \
      "$(mask_serial "$serial")" "$nodes" "$(interface_driver_summary "$port")"
  done
  pi05_log 'SERIAL 列已脱敏；完整序列号只在设备侧可见，不要写入仓库。'
}

# ------------------------------------------------------------------ checks ----

failures=0
warnings=0

pass() { pi05_log "  OK   $*"; }
fail() {
  failures=$((failures + 1))
  pi05_log "  FAIL $*"
}
warn() {
  warnings=$((warnings + 1))
  pi05_warn "$*"
}

check_wrist() {
  local side="$1" upper label model rgb_port depth_port serial
  local ok=true vid pid found_serial drivers nodes

  upper=${side^^}
  case "$side" in
    left) label=左 ;;
    right) label=右 ;;
    *) pi05_die 2 "unsupported side: $side" ;;
  esac
  model=${cfg[PI05_CAMERA_${upper}_WRIST_MODEL]:-}
  rgb_port=${cfg[PI05_CAMERA_${upper}_WRIST_RGB_USB_PORT]:-}
  depth_port=${cfg[PI05_CAMERA_${upper}_WRIST_DEPTH_USB_PORT]:-}
  serial=${cfg[PI05_CAMERA_${upper}_WRIST_SERIAL]:-}

  if [[ -z "$model" && -z "$rgb_port" && -z "$depth_port" ]]; then
    warn "$label腕：config/cameras.env 未填写，已跳过"
    return 0
  fi

  pi05_log "$label腕部相机（Dabai DC1）"
  [[ "$model" == dabai_dc1 ]] ||
    pi05_die 3 "$label腕：PI05_CAMERA_${upper}_WRIST_MODEL 必须是 dabai_dc1"
  [[ -n "$rgb_port" && -n "$depth_port" ]] ||
    pi05_die 3 "$label腕：彩色与深度 USB 端口必须同时填写"

  if usb_present "$rgb_port"; then
    vid=$(usb_attr "$rgb_port" idVendor)
    pid=$(usb_attr "$rgb_port" idProduct)
    if [[ "$vid:$pid" == 2bc5:0557 ]]; then
      pass "彩色半边 $rgb_port 为 2bc5:0557"
    else
      fail "彩色半边 $rgb_port 是 $vid:$pid，期望 2bc5:0557"
      ok=false
    fi
    found_serial=$(usb_attr "$rgb_port" serial)
    if [[ -n "$serial" ]]; then
      if [[ "$found_serial" == "$serial" ]]; then
        pass "彩色半边序列号匹配（$(mask_serial "$found_serial")）"
      else
        fail "彩色半边序列号不匹配：板上 $(mask_serial "$found_serial")，记录 $(mask_serial "$serial")"
        ok=false
      fi
    else
      warn "$label腕：PI05_CAMERA_${upper}_WRIST_SERIAL 为空，无法核对左右序列号"
    fi
  else
    fail "彩色半边端口 $rgb_port 上没有设备"
    ok=false
  fi

  if usb_present "$depth_port"; then
    vid=$(usb_attr "$depth_port" idVendor)
    pid=$(usb_attr "$depth_port" idProduct)
    if [[ "$vid:$pid" == 2bc5:0657 ]]; then
      pass "深度半边 $depth_port 为 2bc5:0657"
    else
      fail "深度半边 $depth_port 是 $vid:$pid，期望 2bc5:0657"
      ok=false
    fi
  else
    fail "深度半边端口 $depth_port 上没有设备"
    ok=false
  fi

  if usb_present "$rgb_port" && usb_present "$depth_port"; then
    if [[ "$(parent_port "$rgb_port")" == "$(parent_port "$depth_port")" ]]; then
      pass "彩色与深度挂在同一父 hub（$(parent_port "$rgb_port")）"
    else
      fail "彩色 $(parent_port "$rgb_port") 与深度 $(parent_port "$depth_port") 不在同一父 hub，可能跨相机接线"
      ok=false
    fi
  fi

  drivers=$(interface_driver_summary "$rgb_port")
  nodes=$(video_node_count "$rgb_port")
  if [[ "$drivers" == *uvcvideo* ]]; then
    pass "彩色半边已绑定 uvcvideo，$nodes 个 UVC 节点"
  else
    warn "$label腕：彩色半边当前未绑定 uvcvideo（drivers=$drivers，节点=$nodes）；Orbbec SDK 使用期间会接管该接口，或需要重新插拔"
  fi

  if [[ -n "$serial" && -d "$udev_root" ]]; then
    case "$(serial_udev_state "$serial")" in
      by-id)
        pass '存在按序列号的稳定 UVC 名称（v4l/by-id …-video-index0）'
        ;;
      no-by-id)
        warn "$label腕：udev 里有该相机，但没有 v4l/by-id 稳定名称"
        ;;
      *)
        warn "$label腕：udev 数据库里没有该序列号（刚插拔或 udev 尚未处理）"
        ;;
    esac
  fi

  $ok
}

check_top() {
  local label="顶部" model port serial require3 expected vid pid speed found_serial
  local ok=true

  model=${cfg[PI05_CAMERA_TOP_MODEL]:-}
  port=${cfg[PI05_CAMERA_TOP_USB_PORT]:-}
  serial=${cfg[PI05_CAMERA_TOP_SERIAL]:-}
  require3=${cfg[PI05_CAMERA_TOP_REQUIRE_USB3]:-true}

  if [[ -z "$model" && -z "$port" && -z "$serial" ]]; then
    warn "$label：config/cameras.env 未填写，已跳过（先确认是哪一台 RealSense）"
    return 0
  fi

  pi05_log "$label相机（Intel RealSense）"
  [[ -n "$model" ]] || pi05_die 3 '顶部：PI05_CAMERA_TOP_MODEL 不能为空'
  expected=$(realsense_product_id "$model") ||
    pi05_die 3 "顶部：未知型号 $model"
  [[ "$require3" == true || "$require3" == false ]] ||
    pi05_die 3 '顶部：PI05_CAMERA_TOP_REQUIRE_USB3 只能是 true 或 false'

  if [[ -z "$port" ]]; then
    warn "$label：PI05_CAMERA_TOP_USB_PORT 为空，未做在线核对"
    return 0
  fi

  if usb_present "$port"; then
    vid=$(usb_attr "$port" idVendor)
    pid=$(usb_attr "$port" idProduct)
    if [[ "$vid:$pid" == "8086:$expected" ]]; then
      pass "$port 为 8086:$expected（$model）"
    else
      fail "$port 是 $vid:$pid，期望 8086:$expected（$model）"
      ok=false
    fi
    speed=$(usb_attr "$port" speed)
    if [[ "$speed" == 5000 ]]; then
      pass "$port 运行在 USB3（speed=5000）"
    elif [[ "$require3" == true ]]; then
      fail "$port 速率是 ${speed:-未知}，不是 USB3；USB2 上深度带宽不足，必须换到 USB3 端口"
      ok=false
    else
      warn "$label：$port 速率是 ${speed:-未知}，不是 USB3（已按要求放行）"
    fi
    found_serial=$(usb_attr "$port" serial)
    if [[ -n "$serial" ]]; then
      if [[ "$found_serial" == "$serial" ]]; then
        pass "序列号匹配（$(mask_serial "$found_serial")）"
      else
        fail "序列号不匹配：板上 $(mask_serial "$found_serial")，记录 $(mask_serial "$serial")"
        ok=false
      fi
    else
      warn "$label：PI05_CAMERA_TOP_SERIAL 为空，realsense2_camera 将无法按序列号选择该相机"
    fi
  else
    fail "端口 $port 上没有设备"
    ok=false
  fi

  $ok
}

# -------------------------------------------------------------------- main ----

if $discover; then
  discover_cameras
  exit 0
fi

[[ -r "$config_file" ]] ||
  pi05_die 3 "camera mapping record not readable: $config_file (copy config/cameras.env.example and trace the ports)"

load_camera_config "$config_file"

check_wrist left || true
check_wrist right || true
check_top || true

if ((failures > 0)); then
  pi05_warn "相机映射检查：$failures 项不匹配，$warnings 项警告"
  exit 1
fi

pi05_log "相机映射检查：通过（$warnings 项警告）"
exit 0
