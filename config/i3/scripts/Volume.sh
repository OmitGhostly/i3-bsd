#!/usr/bin/env bash
# ==================================================
#  KoolDots (2026)
#  Project URL: https://github.com/LinuxBeginnings
#  License: GNU GPLv3
#  SPDX-License-Identifier: GPL-3.0-or-later
# ==================================================
# Scripts for volume controls for audio and mic. The sound system is asked through Platform.sh: pamixer where a sound
# server runs (PulseAudio), else the system's own mixer (FreeBSD mixer, OpenBSD sndioctl, NetBSD mixerctl).

iDIR="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons"
sDIR="${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts"

P="$sDIR/Platform.sh"
vol() { "$P" volume "$@"; }
mic() { "$P" mic "$@"; }
# no sound control at all (no sound card, no mixer): say so instead of failing quietly
need_sound() {
    "$P" has volume && return 0
    notify-send -e -u low -i "$iDIR/volume-mute.png" " Volume" " no sound control found" 2>/dev/null
    exit 0
}

# Get Volume
get_volume() {
    if [[ "$(vol muted)" == "yes" ]]; then
        echo "Muted"
        return
    fi

    local volume
    volume=$(vol get)
    if [[ "${volume:-0}" -eq 0 ]]; then
        echo "Muted"
    else
        echo "$volume %"
    fi
}

# Get icons
get_icon() {
    if [[ "$(vol muted)" == "yes" ]]; then
        echo "$iDIR/volume-mute.png"
        return
    fi

    current=$(vol get)
    if [[ "${current:-0}" -le 30 ]]; then
        echo "$iDIR/volume-low.png"
    elif [[ "$current" -le 60 ]]; then
        echo "$iDIR/volume-mid.png"
    else
        echo "$iDIR/volume-high.png"
    fi
}

# Notify
notify_user() {
    local muted level
    muted="$(vol muted)"
    level="$(vol get)"

    if [[ "$muted" == "yes" || "${level:-0}" -eq 0 ]]; then
        notify-send -e -h string:x-canonical-private-synchronous:volume_notif \
            -u low -i "$(get_icon)" \
            " Volume:" " Muted"
    else
        notify-send -e -h int:value:"$level" -h string:x-canonical-private-synchronous:volume_notif \
            -u low -i "$(get_icon)" \
            " Volume Level:" " ${level}%" &&
            "$sDIR/Sounds.sh" --volume
    fi
}

# Increase Volume
inc_volume() {
    if [ "$(vol muted)" == "yes" ]; then
        toggle_mute
    else
        vol up "$1" && notify_user
    fi
}

# Decrease Volume
dec_volume() {
    if [ "$(vol muted)" == "yes" ]; then
        toggle_mute
    else
        vol down "$1" && notify_user
    fi
}

# Toggle Mute
toggle_mute() {
	if [ "$(vol muted)" == "no" ]; then
		vol mute && notify-send -e -u low -i "$iDIR/volume-mute.png" " Mute"
	elif [ "$(vol muted)" == "yes" ]; then
		vol unmute && notify-send -e -u low -i "$(get_icon)" " Volume:" " Switched ON"
	fi
}

# Toggle Mic
toggle_mic() {
	if [ "$(mic muted)" == "no" ]; then
		mic mute && notify-send -e -u low -i "$iDIR/microphone-mute.png" " Microphone:" " Switched OFF"
	elif [ "$(mic muted)" == "yes" ]; then
		mic unmute && notify-send -e -u low -i "$iDIR/microphone.png" " Microphone:" " Switched ON"
	fi
}
# Get Mic Icon
get_mic_icon() {
    local muted current
    muted="$(mic muted)"
    current="$(mic get)"
    if [[ "$muted" == "yes" || "${current:-0}" -eq "0" ]]; then
        echo "$iDIR/microphone-mute.png"
    else
        echo "$iDIR/microphone.png"
    fi
}

# Get Microphone Volume
get_mic_volume() {
    if [[ "$(mic muted)" == "yes" ]]; then
        echo "Muted"
        return
    fi

    local volume
    volume=$(mic get)
    if [[ "${volume:-0}" -eq 0 ]]; then
        echo "Muted"
    else
        echo "$volume %"
    fi
}

# Notify for Microphone
notify_mic_user() {
    local muted level
    muted="$(mic muted)"
    level="$(mic get)"
    local icon

    if [[ "$muted" == "yes" || "${level:-0}" -eq 0 ]]; then
        icon="$iDIR/microphone-mute.png"
        notify-send -e -h "string:x-canonical-private-synchronous:volume_notif" \
            -u low -i "$icon" \
            " Mic Level:" " Muted"
    else
        icon="$iDIR/microphone.png"
        notify-send -e -h int:value:"$level" -h "string:x-canonical-private-synchronous:volume_notif" \
            -u low -i "$icon" \
            " Mic Level:" " ${level}%"
    fi
}

# Increase MIC Volume
inc_mic_volume() {
    if [ "$(mic muted)" == "yes" ]; then
        toggle_mic
    else
        mic up 5 && notify_mic_user
    fi
}

# Decrease MIC Volume
dec_mic_volume() {
    if [ "$(mic muted)" == "yes" ]; then
        toggle_mic
    else
        mic down 5 && notify_mic_user
    fi
}

# Execute accordingly
case "$1" in
"--get")
  get_volume
  ;;
"--inc")
  need_sound
  inc_volume 5
  ;;
"--inc-precise")
  need_sound
  inc_volume 1
  ;;
"--dec")
  need_sound
  dec_volume 5
  ;;
"--dec-precise")
  need_sound
  dec_volume 1
  ;;
"--toggle")
  need_sound
  toggle_mute
  ;;
"--toggle-mic")
  need_sound
  toggle_mic
  ;;
"--get-icon")
  get_icon
  ;;
"--get-mic-icon")
  get_mic_icon
  ;;
"--mic-inc")
  need_sound
  inc_mic_volume
  ;;
"--mic-dec")
  need_sound
  dec_mic_volume
  ;;
*)
  get_volume
  ;;
esac
