#!/usr/bin/env bash
# One-shot, READ-ONLY probe that resolves, for the PI05 master/slave (随动主从) rig:
#
#   1. which CAN bus carries which master+slave PAIR,
#   2. which physical side (left/right) each CAN bus belongs to,
#   3. which wrist camera is mounted on which side.
#
# It NEVER transmits a single CAN frame. It cannot move an arm.
# The operator performs the motion, by hand, on one back-drivable master arm.
#
# Principle
#   AgileX piper_sdk (asserts/double_piper.MD): both arms of one master/slave
#   pair share ONE USB-CAN adapter. The master (teaching input, 0x470<-0xFA)
#   transmits only control frames 0x151/0x155/0x156/0x157/0x159; the slave
#   (motion output, 0x470<-0xFC, also the factory default) transmits the
#   periodic joint feedback 0x2A5/0x2A6/0x2A7 (0.001 deg units).
#   So: moving one master arm makes exactly one bus's slave feedback change,
#   and exactly one wrist camera's image change -> both mappings fall out.
#
# Usage (as root):
#   sudo scripts/probe_arm_can_mapping.sh --serials <SER1>,<SER2>
#
# Requires the operator to physically move ONE master arm during the marked
# window. Nothing is written to the arms.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
BITRATE=1000000
BASELINE=8
MOVE=15
OUTDIR=/tmp/pi05-arm-probe
SERIALS=""
USE_CAMERA=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serials)  SERIALS="$2"; shift 2 ;;
    --baseline) BASELINE="$2"; shift 2 ;;
    --move)     MOVE="$2"; shift 2 ;;
    --outdir)   OUTDIR="$2"; shift 2 ;;
    --no-camera) USE_CAMERA=0; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This probe must run as root (CAN raw sockets need CAP_NET_RAW)." >&2
  echo "Run: sudo $0 --serials <SER1>,<SER2>" >&2
  exit 1
fi

# ------------------------------------------------------------------ safety
if pgrep -af 'rosmaster|roscore|piper_ctrl|piper_single|joint_command_smoother|run_data_collection|run_smoothed_teleop' >/dev/null 2>&1; then
  echo "Refusing to run: a PI05 control process is active." >&2
  pgrep -af 'rosmaster|roscore|piper_ctrl|piper_single|joint_command_smoother|run_data_collection|run_smoothed_teleop' >&2
  exit 3
fi

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/*.log "$OUTDIR"/*.jsonl 2>/dev/null || true

mapfile -t IFACES < <(ip -brief link show type can 2>/dev/null | awk '{print $1}')
if [[ ${#IFACES[@]} -eq 0 ]]; then
  echo "No CAN interfaces present." >&2
  exit 1
fi

echo "=============================================================="
echo " PI05 arm probe (passive; no CAN frames are transmitted)"
echo "=============================================================="
echo

# ------------------------------------------------------------- bring up CAN
echo "--- CAN interfaces ---"
for i in "${IFACES[@]}"; do
  state=$(ip -brief link show "$i" | awk '{print $2}')
  businfo=$(ethtool -i "$i" 2>/dev/null | awk -F': ' '/bus-info/{print $2}')
  if [[ "$state" != "UP" ]]; then
    ip link set "$i" type can bitrate "$BITRATE"
    ip link set "$i" up
    state=$(ip -brief link show "$i" | awk '{print $2}')
  fi
  printf '  %-8s state=%-5s usb=%-12s %s\n' "$i" "$state" "$businfo" \
    "$(ip -details link show "$i" | grep -oE 'bitrate [0-9]+' || echo 'bitrate ?')"
done
echo

# -------------------------------------------------- passive classification
echo "--- passive classification (${#IFACES[@]} x 5s) ---"
for i in "${IFACES[@]}"; do
  log="$OUTDIR/passive-$i.log"
  timeout 7 candump -L -T 5000 "$i" >"$log" 2>&1 || true
  n=$(wc -l <"$log")
  ids=$(awk -F'#' '{print $1}' "$log" | awk '{print $NF}' | sort -u | tr '\n' ' ')
  printf '  %-8s frames=%-6s ids: %s\n' "$i" "$n" "${ids:-<none>}"
done
echo

# ------------------------------------------- baseline + guided motion run
CANLOG="$OUTDIR/can-motion.log"
CAMLOG="$OUTDIR/camera.jsonl"
TOTAL=$((BASELINE + MOVE + 10))

rm -f "$CANLOG" "$CAMLOG"
# stdbuf -oL matters: candump's stdout is fully buffered when redirected to a
# file, so a SIGTERM would otherwise discard the last (unflushed) frames.
stdbuf -oL candump -L "${IFACES[@]}" >"$CANLOG" 2>&1 &
CANDUMP_PID=$!

CAM_PID=""
if [[ "$USE_CAMERA" -eq 1 && -n "$SERIALS" ]]; then
  IFS=',' read -r -a SER_ARR <<<"$SERIALS"
  cam_args=()
  idx=0
  for s in "${SER_ARR[@]}"; do
    cam_args+=(--serial "$s" --label "CAM_$s")
    idx=$((idx + 1))
  done
  if [[ -x "$PY" ]]; then
    "$PY" "$REPO/scripts/probe_wrist_camera_motion.py" "${cam_args[@]}" \
      --duration "$TOTAL" --output "$CAMLOG" 2>"$OUTDIR/camera.err" &
    CAM_PID=$!
  else
    echo "[warn] $PY not found; skipping camera capture" >&2
  fi
fi

sleep 4
echo "--- BASELINE ${BASELINE}s : do NOT touch any arm ---"
sleep "$BASELINE"

MARK_BASE_END=$(date +%s.%N)
echo
echo "##############################################################"
echo "#  NOW: take ONE master arm and move it gently by hand,"
echo "#  back and forth, for about ${MOVE} seconds."
echo "#  (Master arms are back-drivable in teaching-input mode.)"
echo "##############################################################"
sleep "$MOVE"
MARK_MOVE_END=$(date +%s.%N)

echo
echo "--- capture complete, stopping loggers ---"
kill "$CANDUMP_PID" 2>/dev/null || true
[[ -n "$CAM_PID" ]] && kill "$CAM_PID" 2>/dev/null || true
sleep 1
kill -9 "$CANDUMP_PID" 2>/dev/null || true
[[ -n "$CAM_PID" ]] && kill -9 "$CAM_PID" 2>/dev/null || true
wait 2>/dev/null || true

# ------------------------------------------------------------- analysis
python3 "$REPO/scripts/analyze_arm_probe.py" \
  --can-log "$CANLOG" --cam-log "$CAMLOG" \
  --baseline-end "$MARK_BASE_END" \
  --window "MOVE:${MARK_BASE_END}:${MARK_MOVE_END}" \
  --json "$OUTDIR/report.json" || true

echo
echo "Raw logs kept in $OUTDIR"
