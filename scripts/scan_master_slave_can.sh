#!/usr/bin/env bash
# Passive identification of PI05 arm buses for the master/slave (随动主从) scheme.
#
# This script NEVER transmits. It only listens, so it cannot move an arm.
#
# Rationale (AgileX piper_sdk, asserts/double_piper.MD):
#   Both arms of one master/slave pair share ONE CAN module (one USB-CAN adapter).
#   - Master arm (teaching input, 0x470 <- 0xFA): transmits ONLY control frames
#     on 0x151, 0x155, 0x156, 0x157, 0x159.
#   - Slave arm  (motion output, 0x470 <- 0xFC or factory default): transmits the
#     periodic feedback frames 0x2A1..0x2A8 (plus high-speed feedback 0x251..0x257).
#   So a bus carrying both ID families is a complete master+slave pair.
#
# Usage:
#   scripts/scan_master_slave_can.sh [duration_seconds] [iface ...]
#
# Requires the CAN interfaces to be UP at 1 Mbps. Bring them up first, e.g.:
#   sudo ip link set can0 up type can bitrate 1000000
#   sudo ip link set can1 up type can bitrate 1000000

set -euo pipefail

duration="${1:-5}"
shift || true

if [[ $# -gt 0 ]]; then
  ifaces=("$@")
else
  mapfile -t ifaces < <(ip -brief link show type can 2>/dev/null | awk '{print $1}')
fi

if [[ ${#ifaces[@]} -eq 0 ]]; then
  echo "No CAN interfaces found. Bring them up at 1 Mbps first." >&2
  exit 1
fi

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

declare -A MASTER_TX=( [151]=1 [155]=1 [156]=1 [157]=1 [159]=1 )
declare -A SLAVE_FB=( [2A1]=1 [2A2]=1 [2A3]=1 [2A4]=1 [2A5]=1 [2A6]=1 [2A7]=1 [2A8]=1 )
declare -A MASTER_FB_B=( [2B1]=1 [2B2]=1 [2B3]=1 [2B4]=1 [2B5]=1 [2B6]=1 [2B7]=1 [2B8]=1 )
declare -A MASTER_FB_C=( [2C1]=1 [2C2]=1 [2C3]=1 [2C4]=1 [2C5]=1 [2C6]=1 [2C7]=1 [2C8]=1 )

printf 'Passive CAN scan: %ss per interface. Nothing is transmitted.\n\n' "$duration"

for iface in "${ifaces[@]}"; do
  state=$(ip -brief link show "$iface" 2>/dev/null | awk '{print $2}')
  businfo=$(ethtool -i "$iface" 2>/dev/null | awk -F': ' '/bus-info/{print $2}')
  detail=$(ip -details link show "$iface" 2>/dev/null | grep -oE 'bitrate [0-9]+' || true)

  printf '================ %s ================\n' "$iface"
  printf '  state=%s  %s  usb=%s\n' "${state:-unknown}" "${detail:-bitrate unknown}" "${businfo:-unknown}"

  if [[ "$state" != "UP" ]]; then
    printf '  -> interface is DOWN, skipped.\n\n'
    continue
  fi

  log="$workdir/$iface.log"
  timeout $((duration + 2)) candump -T $((duration * 1000)) "$iface" >"$log" 2>&1 || true
  total=$(wc -l <"$log")

  if [[ "$total" -eq 0 ]]; then
    printf '  -> NO frames received. No powered arm on this bus, or wrong bitrate.\n\n'
    continue
  fi

  printf '  frames=%s\n' "$total"

  n_master_tx=0; n_slave_fb=0; n_mfb_b=0; n_mfb_c=0
  declare -A seen=()
  while read -r id _; do
    [[ -z "$id" ]] && continue
    id=${id^^}
    [[ -n "${seen[$id]:-}" ]] && continue
    seen[$id]=1
    [[ -n "${MASTER_TX[$id]:-}"   ]] && n_master_tx=$((n_master_tx + 1))
    [[ -n "${SLAVE_FB[$id]:-}"    ]] && n_slave_fb=$((n_slave_fb + 1))
    [[ -n "${MASTER_FB_B[$id]:-}" ]] && n_mfb_b=$((n_mfb_b + 1))
    [[ -n "${MASTER_FB_C[$id]:-}" ]] && n_mfb_c=$((n_mfb_c + 1))
  done < <(awk '{print $2}' "$log")

  printf '  distinct IDs: %s\n' "$(printf '%s\n' "${!seen[@]}" | sort | tr '\n' ' ')"
  printf '    master control frames (151/155/156/157/159): %s\n' "$n_master_tx"
  printf '    slave feedback frames  (2A1..2A8)          : %s\n' "$n_slave_fb"
  printf '    master feedback 2Bx / 2Cx (offset mode)    : %s / %s\n' "$n_mfb_b" "$n_mfb_c"

  if [[ $n_master_tx -gt 0 && $n_slave_fb -gt 0 ]]; then
    printf '  => PAIR: one master (teaching input) + one slave (motion output) on this bus.\n'
  elif [[ $n_master_tx -gt 0 ]]; then
    printf '  => MASTER ONLY detected (teaching input arm; slave missing or unpowered).\n'
  elif [[ $n_slave_fb -gt 0 ]]; then
    printf '  => SLAVE ONLY detected (motion output arm; master missing or unpowered).\n'
  else
    printf '  => Unrecognised Piper traffic. Inspect raw log manually.\n'
  fi
  printf '\n'
done
