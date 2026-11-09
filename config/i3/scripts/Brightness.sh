#!/usr/bin/env bash
# ==================================================
#  KoolDots (2026)
#  Project URL: https://github.com/LinuxBeginnings
#  License: GNU GPLv3
#  SPDX-License-Identifier: GPL-3.0-or-later
# ==================================================
# Screen brightness. A backlight (laptops) through Platform.sh: FreeBSD's backlight, xbacklight (screens RandR can
# dim: OpenBSD, NetBSD, ...), OpenBSD's wsconsctl.
# Screens without one - most desktop monitors - get their picture dimmed instead (software brightness: the colour
# ramp, through redshift together with the night light, see Nightlight.sh). It is saved, and put back at login.
#   Brightness.sh --inc | --dec    10% brighter / darker, with a notification (the brightness keys, the bar)
#   Brightness.sh --set N          N% (5 to 100), without a notification (the slider in Settings > Displays)
#   Brightness.sh --get            the brightness now, in %
#   Brightness.sh --kind           backlight | software

iDIR="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons"
step=10  # INCREASE/DECREASE BY THIS VALUE
P="${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/Platform.sh"
N="${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/Nightlight.sh"
soft="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots/brightness"

kind() { if "$P" has backlight; then echo backlight; else echo software; fi; }

# Get current brightness as an integer (without %)
get_brightness() {
    local b
    if [ "$(kind)" = backlight ]; then
        "$P" brightness get
    else
        b="$(cat "$soft" 2>/dev/null)"
        case "$b" in ''|*[!0-9]*) b=100 ;; esac
        echo "$b"
    fi
}

# set_brightness N: clamped to 5-100 (never fully dark)
set_brightness() {
    local new=$1
    case "$new" in ''|*[!0-9]*) return 1 ;; esac
    (( new < 5 )) && new=5
    (( new > 100 )) && new=100
    if [ "$(kind)" = backlight ]; then
        "$P" brightness set "$new"
    else
        mkdir -p "$(dirname "$soft")" && printf '%s\n' "$new" > "$soft.tmp" && mv -f "$soft.tmp" "$soft"
        "$N" apply
    fi
    echo "$new"
}

# Determine the icon based on brightness level
get_icon_path() {
    local brightness=$1
    local level=$(( (brightness + 19) / 20 * 20 ))  # Round up to next 20
    if (( level > 100 )); then
        level=100
    fi
    echo "$iDIR/brightness-${level}.png"
}

# Send notification
send_notification() {
    local brightness=$1
    local icon_path=$2

    notify-send -e \
        -h string:x-canonical-private-synchronous:brightness_notif \
        -h int:value:"$brightness" \
        -u low \
        -i "$icon_path" \
        "Screen" "Brightness: ${brightness}%"
}

# Change brightness and notify
change_brightness() {
    local delta=$1
    local current new icon

    current=$(get_brightness)
    if [ -z "$current" ]; then
        notify-send -e -u low "Screen" "This screen's brightness cannot be changed from here" 2>/dev/null
        return 1
    fi
    new=$(set_brightness "$((current + delta))") || return 1

    icon=$(get_icon_path "$new")
    send_notification "$new" "$icon"
}

# Main
case "$1" in
    "--get")
        get_brightness
        ;;
    "--set")
        set_brightness "${2:-}" >/dev/null
        ;;
    "--kind")
        kind
        ;;
    "--inc")
        change_brightness "$step"
        ;;
    "--dec")
        change_brightness "-$step"
        ;;
    *)
        get_brightness
        ;;
esac
