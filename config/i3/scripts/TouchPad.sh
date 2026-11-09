#!/usr/bin/env bash
icon="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons/touchpad.png"
dev=$(xinput list --name-only | grep -iE 'touchpad|trackpad' | head -n1)
[ -z "$dev" ] && { notify-send -i "$icon" "Touchpad" "none found"; exit 1; }
en=$(xinput list-props "$dev" | awk '/Device Enabled/{print $NF}')
if [ "$en" = 1 ]; then xinput disable "$dev"; notify-send -u low -i "$icon" "Touchpad" "disabled"; else xinput enable "$dev"; notify-send -u low -i "$icon" "Touchpad" "enabled"; fi
