#!/usr/bin/env bash
if pgrep -u "$UID" -x picom >/dev/null; then pkill -u "$UID" -x picom; notify-send -u low "Compositor" "off"
else "$(dirname "$0")/Picom.sh"; notify-send -u low "Compositor" "on"; fi
