#!/usr/bin/env bash
f="${XDG_CACHE_HOME:-$HOME/.cache}/i3/gamemode"; mkdir -p "$(dirname "$f")"
icon="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons/gamepad.png"
if [ -e "$f" ]; then
  rm "$f"; i3-msg reload >/dev/null     # reload brings back your gaps from the config / Settings window
  "$(dirname "$0")/Picom.sh"
  polybar-msg cmd show >/dev/null 2>&1; notify-send -u low -i "$icon" "Game mode" "off"
else
  touch "$f"; i3-msg 'gaps inner all set 0; gaps outer all set 0' >/dev/null
  pkill -u "$UID" -x picom; polybar-msg cmd hide >/dev/null 2>&1; notify-send -u low -i "$icon" "Game mode" "on"
fi
