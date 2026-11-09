#!/usr/bin/env bash
# ==================================================
#  KoolDots (2026)
#  Project URL: https://github.com/LinuxBeginnings
#  License: GNU GPLv3
#  SPDX-License-Identifier: GPL-3.0-or-later
# ==================================================
# This script is used to play system sounds.
# Script is used by Volume.Sh and ScreenShots.sh 

theme="freedesktop" # Set the theme for the system sounds.
mute=false          # Set to true to mute the system sounds.
directSoundDir="${XDG_CONFIG_HOME:-$HOME/.config}/i3/sounds"

# Mute individual sounds here.
muteScreenshots=false
muteVolume=false
# switches from the Settings window (Sound tab); only plain true/false values are taken from the file
if [[ -r "${XDG_CONFIG_HOME:-$HOME/.config}/i3/sounds.conf" ]]; then
    while IFS='=' read -r key value; do
        case "$key=$value" in
            muteVolume=true|muteVolume=false) muteVolume="$value" ;;
            muteScreenshots=true|muteScreenshots=false) muteScreenshots="$value" ;;
        esac
    done < "${XDG_CONFIG_HOME:-$HOME/.config}/i3/sounds.conf"
fi

# Exit if the system sounds are muted.
if [[ "$mute" = true ]]; then
    exit 0
fi

# Choose the sound to play.
if [[ "$1" == "--screenshot" ]]; then
    if [[ "$muteScreenshots" = true ]]; then
        exit 0
    fi
    directSound="$directSoundDir/screenshot.ogg"
    soundoption="screen-capture.*"
elif [[ "$1" == "--volume" ]]; then
    if [[ "$muteVolume" = true ]]; then
        exit 0
    fi
    directSound="$directSoundDir/volume.ogg"
    soundoption="audio-volume-change.*"
elif [[ "$1" == "--error" ]]; then
    if [[ "$muteScreenshots" = true ]]; then
        exit 0
    fi
    directSound="$directSoundDir/error.ogg"
    soundoption="dialog-error.*"
else
    echo -e "Available sounds: --screenshot, --volume, --error"
    exit 0
fi

# Set the directory defaults for system sounds.
if [ -d "/usr/local/share/sounds" ]; then
    systemDIR="/usr/local/share/sounds"             # FreeBSD, GhostBSD, OpenBSD
elif [ -d "/usr/pkg/share/sounds" ]; then
    systemDIR="/usr/pkg/share/sounds"               # NetBSD
else
    systemDIR="/usr/share/sounds"
fi
userDIR="$HOME/.local/share/sounds"
defaultTheme="freedesktop"

# Prefer the user's theme, but use the system's if it doesn't exist.
sDIR="$systemDIR/$defaultTheme"
if [ -d "$userDIR/$theme" ]; then
    sDIR="$userDIR/$theme"
elif [ -d "$systemDIR/$theme" ]; then
    sDIR="$systemDIR/$theme"
fi

# Get the theme that it inherits.
iTheme=$(cat "$sDIR/index.theme" | grep -i "inherits" | cut -d "=" -f 2)
iDIR="$sDIR/../$iTheme"

# Helper to play in the background (fast return).
play_sound() {
    if command -v paplay >/dev/null 2>&1; then
        paplay "$1" >/dev/null 2>&1 &
        exit 0
    fi
    if command -v pw-play >/dev/null 2>&1; then
        pw-play "$1" >/dev/null 2>&1 &
        exit 0
    fi
    if command -v aplay >/dev/null 2>&1; then
        aplay "$1" >/dev/null 2>&1 &
        exit 0
    fi
    # (the BSDs: no PulseAudio / PipeWire / ALSA tools by default - mpv plays through the system's own sound)
    if command -v mpv >/dev/null 2>&1; then
        mpv --no-video --really-quiet --no-terminal "$1" >/dev/null 2>&1 &
        exit 0
    fi
    echo "Error: No suitable audio player found. Install paplay (pulseaudio-utils), PipeWire/ALSA tools or mpv."
    exit 1
}

# If a direct sound file exists, play it immediately to avoid lookup delay.
if [[ -n "$directSound" && -f "$directSound" ]]; then
    play_sound "$directSound"
fi

# The first file in a folder matching the sound's name pattern (find -quit is not on OpenBSD).
first_match() {
    local f
    # shellcheck disable=SC2206
    for f in "$1"/$2; do
        [ -f "$f" ] && { printf '%s\n' "$f"; return 0; }
    done
    return 1
}

# Find the sound file and play it.
sound_file=$(first_match "$sDIR/stereo" "$soundoption")
if ! test -f "$sound_file"; then
    sound_file=$(first_match "$iDIR/stereo" "$soundoption")
    if ! test -f "$sound_file"; then
        sound_file=$(first_match "$userDIR/$defaultTheme/stereo" "$soundoption")
        if ! test -f "$sound_file"; then
            sound_file=$(first_match "$systemDIR/$defaultTheme/stereo" "$soundoption")
            if ! test -f "$sound_file"; then
                echo "Error: Sound file not found."
                exit 1
            fi
        fi
    fi
fi
# Play the sound (background for quick return).
play_sound "$sound_file"
