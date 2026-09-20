#!/usr/bin/env bash
# Guided side mapping for the PI05 master/slave (随动主从) rig.
#
# The operator moves ONE arm per phase, each phase in its own marked window.
# A powered arm's own joint feedback reflects its pose, so the phase in which
# a CAN bus starts reporting travel IS that arm's bus; comparing the same
# windows against the wrist cameras gives the camera sides in the same pass.
#
# READ-ONLY: not a single CAN frame is transmitted. The operator supplies all
# motion by hand, so the arms cannot be commanded by this script.
#
# Usage (as root):
#   sudo scripts/probe_arm_sides.sh --serials <SER1>,<SER2>
#   sudo scripts/probe_arm_sides.sh --serials <SER1>,<SER2> \
#        --phases LEFT_MASTER,LEFT_SLAVE,RIGHT_MASTER,RIGHT_SLAVE
#
# --phases names the arms to move, in order; the report labels each window
# with those names. Default is "LEFT,RIGHT".
#
# An arm that shows NO travel on ANY bus during its own phase has no working
# CAN link (unpowered, unplugged, or its adapter is not enumerated) -- which
# is itself the answer you need before trusting the rig.
#
# NOTE on master/slave roles: a passive scan CANNOT tell a master from a slave
# while both sit in normal mode, because both report feedback identically.
# Only a master in teaching-input (linkage) mode is distinguishable, since it
# transmits control frames 0x151/0x155/0x156/0x157/0x159 and stops reporting.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO/.venv/bin/python"
BITRATE=1000000
BASELINE=8
PHASE=12
GAP=3
OUTDIR=/tmp/pi05-arm-sides
SERIALS=""
USE_CAMERA=1
PHASES="LEFT,RIGHT"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --serials)  SERIALS="$2"; shift 2 ;;
    --baseline) BASELINE="$2"; shift 2 ;;
    --phase)    PHASE="$2"; shift 2 ;;
    --phases)   PHASES="$2"; shift 2 ;;
    --outdir)   OUTDIR="$2"; shift 2 ;;
    --no-camera) USE_CAMERA=0; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

IFS=',' read -r -a PHASE_LABELS <<<"$PHASES"
if [[ ${#PHASE_LABELS[@]} -eq 0 ]]; then
  echo "--phases must list at least one label" >&2
  exit 2
fi

if pgrep -af 'rosmaster|roscore|piper_ctrl|piper_single|joint_command_smoother|run_data_collection|run_smoothed_teleop' >/dev/null 2>&1; then
  echo "Refusing to run: a PI05 control process is active." >&2
  pgrep -af 'rosmaster|roscore|piper_ctrl|piper_single|joint_command_smoother|run_data_collection|run_smoothed_teleop' >&2
  exit 3
fi

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/*.log "$OUTDIR"/*.jsonl "$OUTDIR"/*.json 2>/dev/null || true

mapfile -t IFACES < <(ip -brief link show type can 2>/dev/null | awk '{print $1}')
if [[ ${#IFACES[@]} -eq 0 ]]; then
  echo "No CAN interfaces present." >&2
  exit 1
fi

# root is only needed to bring a DOWN bus up and set its bitrate. If every bus
# is already UP, a plain user can run the whole probe (candump works for the
# 'mips' user on this host).
IS_ROOT=0
[[ "$(id -u)" -eq 0 ]] && IS_ROOT=1
DOWN_IFACES=()
for i in "${IFACES[@]}"; do
  [[ "$(ip -brief link show "$i" | awk '{print $2}')" == "UP" ]] || DOWN_IFACES+=("$i")
done
if [[ ${#DOWN_IFACES[@]} -gt 0 && "$IS_ROOT" -eq 0 ]]; then
  echo "These CAN interfaces are DOWN and I cannot raise them without root:" >&2
  printf '  %s\n' "${DOWN_IFACES[@]}" >&2
  echo >&2
  echo "Run this once, then re-run the probe as your normal user:" >&2
  for i in "${DOWN_IFACES[@]}"; do
    echo "  sudo ip link set $i up type can bitrate $BITRATE" >&2
  done
  exit 1
fi

echo "=============================================================="
echo " PI05 arm side probe  (passive; transmits NO CAN frames)"
echo "=============================================================="
echo
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
echo "--- passive check before touching anything (5s) ---"
for i in "${IFACES[@]}"; do
  log="$OUTDIR/passive-$i.log"
  timeout 7 candump -L -T 5000 "$i" >"$log" 2>&1 || true
  n=$(wc -l <"$log")
  ids=$(awk -F'#' '{print $1}' "$log" | awk '{print $NF}' | sort -u | tr '\n' ' ')
  printf '  %-8s frames=%-7s ids: %s\n' "$i" "$n" "${ids:-<none>}"
done

CANLOG="$OUTDIR/can-all.log"
CAMLOG="$OUTDIR/camera.jsonl"
READY="$OUTDIR/camera.ready"
TOTAL=$((BASELINE + (PHASE + GAP) * ${#PHASE_LABELS[@]} + 20))

rm -f "$CANLOG" "$CAMLOG" "$READY"

# Start the cameras FIRST and wait until they are actually streaming. Opening a
# UVC stream under the CPU load of three full CAN buses is slow, and starting
# both at once is what previously lost the camera entirely.
CAM_PID=""
if [[ "$USE_CAMERA" -eq 1 && -n "$SERIALS" ]]; then
  IFS=',' read -r -a SER_ARR <<<"$SERIALS"
  cam_args=()
  for s in "${SER_ARR[@]}"; do
    cam_args+=(--serial "$s" --label "CAM_$s")
  done
  if [[ -x "$PY" ]]; then
    "$PY" "$REPO/scripts/probe_wrist_camera_motion.py" "${cam_args[@]}" \
      --duration "$TOTAL" --output "$CAMLOG" --ready-file "$READY" \
      2>"$OUTDIR/camera.err" &
    CAM_PID=$!
    echo
    echo "--- waiting for wrist cameras to start streaming (up to 25s) ---"
    for _ in $(seq 1 50); do
      [[ -f "$READY" ]] && break
      sleep 0.5
    done
    if [[ -f "$READY" ]]; then
      echo "  camera probe ready: $(cat "$READY")"
      if grep -q 'opened=0' "$READY"; then
        echo "  [error] NO camera could be opened:" >&2
        sed 's/^/    /' "$OUTDIR/camera.err" >&2
        echo "  Fix the camera and re-run; CAN capture would otherwise be wasted." >&2
        kill "$CAM_PID" 2>/dev/null || true
        exit 4
      fi
    else
      echo "  [warn] camera probe did not report ready in time; continuing with CAN only" >&2
    fi
  else
    echo "[warn] $PY not found; camera capture skipped" >&2
  fi
fi

# Capture only the IDs the analysis needs (joint feedback + master control
# frames). Three unfiltered buses produce ~9000 frames/s, which starves the
# camera thread and bloats the log for no extra information; the full ID
# inventory was already taken by the passive scan above.
CAN_FILTER_IDS=(2A1 2A5 2A6 2A7 151 155 156 157 159 2B5 2B6 2B7 2C5 2C6 2C7)
CAN_ARGS=()
for i in "${IFACES[@]}"; do
  spec="$i"
  for id in "${CAN_FILTER_IDS[@]}"; do spec+=",$id:7FF"; done
  CAN_ARGS+=("$spec")
done

# stdbuf -oL: candump's stdout is fully buffered when redirected, so SIGTERM
# would otherwise discard unflushed frames.
stdbuf -oL candump -L "${CAN_ARGS[@]}" >"$CANLOG" 2>&1 &
CANDUMP_PID=$!

sleep 4
echo
echo "--- BASELINE ${BASELINE}s : hands off ALL arms ---"
sleep "$BASELINE"
T_BASE=$(date +%s.%N)

WINDOW_ARGS=()
PREV=""
T_PREV="$T_BASE"
idx=0
for label in "${PHASE_LABELS[@]}"; do
  idx=$((idx + 1))
  echo
  echo "##############################################################"
  echo "#  PHASE ${idx}/${#PHASE_LABELS[@]} : move the ${label} arm by hand for ${PHASE}s."
  echo "#  Move ONLY that one arm."
  [[ -n "$PREV" ]] && echo "#  Release the ${PREV} arm completely first."
  echo "##############################################################"
  sleep "$PHASE"
  T_NOW=$(date +%s.%N)
  WINDOW_ARGS+=(--window "${label}:${T_PREV}:${T_NOW}")
  PREV="$label"
  # Excluded settle gap: without it, an operator still moving the previous arm
  # when the phase flips makes that bus look like it moved in the NEXT window.
  if [[ "$idx" -lt "${#PHASE_LABELS[@]}" ]]; then
    echo
    echo "--- hands off for ${GAP}s (settle) ---"
    sleep "$GAP"
  fi
  T_PREV=$(date +%s.%N)
done

echo
echo "--- capture complete, stopping loggers ---"
kill "$CANDUMP_PID" 2>/dev/null || true
[[ -n "$CAM_PID" ]] && kill "$CAM_PID" 2>/dev/null || true
sleep 1
kill -9 "$CANDUMP_PID" 2>/dev/null || true
[[ -n "$CAM_PID" ]] && kill -9 "$CAM_PID" 2>/dev/null || true
wait 2>/dev/null || true

python3 "$REPO/scripts/analyze_arm_probe.py" \
  --can-log "$CANLOG" --cam-log "$CAMLOG" \
  --baseline-end "$T_BASE" \
  "${WINDOW_ARGS[@]}" \
  --json "$OUTDIR/report.json" || true

echo
echo "Raw logs kept in $OUTDIR"
