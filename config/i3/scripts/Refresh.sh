#!/usr/bin/env bash
# Reload i3/bar/notifications/compositor. --colors = skip compositor restart.
cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
pkill -x rofi 2>/dev/null
pkill -USR1 -x kitty 2>/dev/null
pkill -USR2 -x ghostty 2>/dev/null
command -v dunstctl >/dev/null && dunstctl reload 2>/dev/null
i3-msg reload >/dev/null
[ "$1" = "--colors" ] || { pkill -u "$UID" -x picom; sleep 0.3; "$cfg/i3/scripts/Picom.sh"; }
