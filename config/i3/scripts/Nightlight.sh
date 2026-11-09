#!/usr/bin/env bash
# Night light: redshift, one shot (replaces hyprsunset). Usage: toggle | init | status | apply
# It shares the screens' colour ramp with the software brightness of screens without a backlight (Brightness.sh),
# so the two are always applied together: "apply" sets both from what is saved (Brightness.sh calls it).
state="${XDG_CACHE_HOME:-$HOME/.cache}/i3/nightlight"; mkdir -p "$(dirname "$state")"
bright="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots/brightness"
temp="${NIGHT_TEMP:-4000}"

apply() {
  local t=6500 b f
  [ "$(cat "$state" 2>/dev/null)" = on ] && t="$temp"
  b="$(cat "$bright" 2>/dev/null)"
  case "$b" in ''|*[!0-9]*) b=100 ;; esac
  [ "$b" -lt 5 ] && b=5
  [ "$b" -gt 100 ] && b=100
  f="$(awk -v b="$b" 'BEGIN { printf "%.2f", b / 100 }')"
  if command -v redshift >/dev/null 2>&1; then
    if [ "$t" = 6500 ] && [ "$b" -eq 100 ]; then redshift -x >/dev/null 2>&1
    else redshift -P -O "$t" -b "$f" >/dev/null 2>&1; fi
  elif command -v xrandr >/dev/null 2>&1; then
    # (no redshift: xrandr can still dim the picture, but not make it warmer)
    xrandr --query 2>/dev/null | awk '$2 == "connected" { print $1 }' | while read -r o; do
      xrandr --output "$o" --brightness "$f" >/dev/null 2>&1
    done
  fi
}

case "$1" in
  toggle) icon="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons/moon.png"
          if [ "$(cat "$state" 2>/dev/null)" = on ]; then echo off > "$state"; apply; notify-send -u low -i "$icon" "Night light" "off"
          else echo on > "$state"; apply; notify-send -u low -i "$icon" "Night light" "on (${temp}K)"; fi ;;
  init)   # (login: put back the night light and the software brightness, if either is in use)
          if [ "$(cat "$state" 2>/dev/null)" = on ] || [ -s "$bright" ]; then apply; fi ;;
  apply)  apply ;;
  status) if [ "$(cat "$state" 2>/dev/null)" = on ]; then echo "󰖔 ${temp}K"; else echo "󰖙"; fi ;;
esac
