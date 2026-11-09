#!/usr/bin/env bash
# Point ~/.config/i3/rofi/.current_wallpaper_focused at the current wallpaper (rofi themes use it as a background).
cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
cur="${XDG_CACHE_HOME:-$HOME/.cache}/i3/current_wallpaper"
[ -e "$cur" ] || exit 0
mkdir -p "$cfg/i3/rofi"
ln -sf "$(readlink -f "$cur")" "$cfg/i3/rofi/.current_wallpaper_focused"
