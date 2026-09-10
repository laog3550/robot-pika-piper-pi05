#!/usr/bin/env bash

# Safe parser and identity helpers for PI05 device configuration scripts.
# Callers enable strict mode and source common.sh first.

pi05_load_device_config() {
  local config_file="$1" line key value
  [[ -r "$config_file" ]] || pi05_die 3 "configuration file not readable: $config_file"

  PI05_CAN_INTERFACE=''
  PI05_CAN_BITRATE=''
  PI05_CAN_USB_BUS_INFO=''
  PI05_PIKA_SERIAL_ALIAS=''
  PI05_PIKA_SERIAL_BAUD=''
  PI05_PIKA_SERIAL_ID_PATH=''
  PI05_PIKA_SERIAL_VENDOR_ID=''
  PI05_PIKA_SERIAL_MODEL_ID=''

  while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%%#*}
    line=${line//$'\r'/}
    [[ -n "${line//[[:space:]]/}" ]] || continue
    [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=([-A-Za-z0-9_./:+]*)$ ]] ||
      pi05_die 3 "unsafe or invalid configuration line in $config_file"
    key=${BASH_REMATCH[1]}
    value=${BASH_REMATCH[2]}
    case "$key" in
      PI05_CAN_INTERFACE|PI05_CAN_BITRATE|PI05_CAN_USB_BUS_INFO|PI05_PIKA_SERIAL_ALIAS|PI05_PIKA_SERIAL_BAUD|PI05_PIKA_SERIAL_ID_PATH|PI05_PIKA_SERIAL_VENDOR_ID|PI05_PIKA_SERIAL_MODEL_ID)
        printf -v "$key" '%s' "$value"
        ;;
      PI05_ROS_DISTRO|PI05_ARM_SIDE|PI05_AUTO_ENABLE) ;;
      *) pi05_die 3 "unknown configuration key: $key" ;;
    esac
  done <"$config_file"
}

pi05_validate_can_config() {
  [[ "$PI05_CAN_INTERFACE" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,14}$ ]] ||
    pi05_die 3 'PI05_CAN_INTERFACE must be a non-empty Linux interface name (maximum 15 characters)'
  [[ "$PI05_CAN_BITRATE" == 1000000 ]] ||
    pi05_die 3 'PI05_CAN_BITRATE must be exactly 1000000 for Piper'
  [[ -n "$PI05_CAN_USB_BUS_INFO" ]] ||
    pi05_die 3 'PI05_CAN_USB_BUS_INFO is empty; discover and confirm the physical USB port first'
}

pi05_validate_serial_config() {
  [[ "$PI05_PIKA_SERIAL_ALIAS" =~ ^/dev/([A-Za-z0-9][A-Za-z0-9_.-]{0,63})$ ]] ||
    pi05_die 3 'PI05_PIKA_SERIAL_ALIAS must be a simple absolute /dev alias'
  PI05_PIKA_SERIAL_ALIAS_NAME=${BASH_REMATCH[1]}
  [[ "$PI05_PIKA_SERIAL_ALIAS_NAME" != ttyUSB* && "$PI05_PIKA_SERIAL_ALIAS_NAME" != ttyACM* ]] ||
    pi05_die 3 'PI05_PIKA_SERIAL_ALIAS must not imitate a kernel ttyUSB/ttyACM name'
  [[ "$PI05_PIKA_SERIAL_BAUD" == 460800 ]] ||
    pi05_die 3 'PI05_PIKA_SERIAL_BAUD must be exactly 460800 for the current Pika sensor_tools protocol'
  [[ -n "$PI05_PIKA_SERIAL_ID_PATH" ]] ||
    pi05_die 3 'PI05_PIKA_SERIAL_ID_PATH is empty; discover and confirm the physical USB port first'
  [[ "$PI05_PIKA_SERIAL_VENDOR_ID" =~ ^[0-9A-Fa-f]{4}$ ]] ||
    pi05_die 3 'PI05_PIKA_SERIAL_VENDOR_ID must contain four hexadecimal digits'
  [[ "$PI05_PIKA_SERIAL_MODEL_ID" =~ ^[0-9A-Fa-f]{4}$ ]] ||
    pi05_die 3 'PI05_PIKA_SERIAL_MODEL_ID must contain four hexadecimal digits'
}

pi05_can_interfaces() {
  ip -brief link show type can 2>/dev/null | awk '{print $1}'
}

pi05_can_bus_info() {
  ethtool -i "$1" 2>/dev/null | awk -F':[[:space:]]*' '$1 == "bus-info" {print $2; exit}'
}

pi05_can_driver() {
  ethtool -i "$1" 2>/dev/null | awk -F':[[:space:]]*' '$1 == "driver" {print $2; exit}'
}

pi05_can_bus_info_is_udev_ancestor() {
  local interface="$1" bus_info="$2" device_path
  device_path=$(readlink -f -- "/sys/class/net/$interface/device" 2>/dev/null) || return 1
  [[ "/$device_path/" == *"/$bus_info/"* ]]
}

pi05_serial_devices() {
  find /dev -maxdepth 1 -type c \( -name 'ttyUSB*' -o -name 'ttyACM*' \) -print 2>/dev/null | sort
}

pi05_udev_property() {
  local device="$1" property="$2"
  udevadm info --query=property --name="$device" 2>/dev/null |
    awk -F= -v wanted="$property" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}'
}
