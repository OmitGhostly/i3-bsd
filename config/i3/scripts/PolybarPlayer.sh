#!/usr/bin/env bash
s=$(playerctl status 2>/dev/null) || exit 0
[ "$s" = Stopped ] && exit 0
icon="󰐊"; [ "$s" = Playing ] && icon="󰏤"
printf '%s %s - %s\n' "$icon" "$(playerctl metadata artist 2>/dev/null)" "$(playerctl metadata title 2>/dev/null)"
