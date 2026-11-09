#!/usr/bin/env bash
# Runs at every login; does real work only once: the first wallpaper (the night street-lights photo, which suits
# the black bar) - unless you already picked one, which is never replaced. The "done" mark lives in
# ~/.local/state, not ~/.cache (cleaners and some systems empty that at boot).
cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
state="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots"; flag="$state/first-run-done"
old_flag="${XDG_CACHE_HOME:-$HOME/.cache}/i3/first-run-done"
mkdir -p "$state" "$HOME/Pictures/Screenshots"
[ -e "$flag" ] && exit 0
if [ -e "$old_flag" ] || [ -s "$state/wallpaper" ]; then touch "$flag"; exit 0; fi   # (an older install / a picked one)
sleep 2
first="${WALL_DIR:-$HOME/Pictures/wallpapers}/night-streetlights.jpg"
if [ -f "$first" ]; then "$cfg/i3/scripts/Wallpaper.sh" --set "$first"; else "$cfg/i3/scripts/Wallpaper.sh" --random; fi
touch "$flag"
