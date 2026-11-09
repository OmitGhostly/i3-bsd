#!/usr/bin/env bash
# Bluetooth status for polybar: off / on / connected device name. Prints nothing without an adapter.
command -v bluetoothctl >/dev/null 2>&1 || exit 0
show=$(bluetoothctl show 2>/dev/null) || exit 0
[ -n "$show" ] || exit 0
if ! grep -q 'Powered: yes' <<<"$show"; then echo "󰂲"; exit 0; fi
name=$(bluetoothctl devices Connected 2>/dev/null | head -n1 | cut -d' ' -f3-)
if [ -n "$name" ]; then echo "󰂱 ${name:0:18}"; else echo "󰂯"; fi
