#!/usr/bin/env bash
#  KoolDots (2026)
# Airplane Mode: all Wi-Fi off, or back on: the wireless interface down or up (Platform.sh - that needs root: a
# doas or sudo rule that lets you run ifconfig without a password).

notif="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons/airplane.png"
P="${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/Platform.sh"

if state=$("$P" airplane toggle); then
    if [ "$state" = on ]; then
        notify-send -u low -i "$notif" " Airplane" " mode: ON"
    else
        notify-send -u low -i "$notif" " Airplane" " mode: OFF"
    fi
else
    notify-send -u low -i "$notif" " Airplane" " could not switch Wi-Fi (no Wi-Fi, or no permission)"
fi
