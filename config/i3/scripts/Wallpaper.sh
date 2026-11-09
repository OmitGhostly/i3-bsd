#!/usr/bin/env bash
# feh replacement for swww/awww. Usage: Wallpaper.sh --select | --random | --restore | --set FILE
#
# The wallpaper you pick is remembered in ~/.local/state/i3wm-dots/wallpaper (not in ~/.cache, which cleaners and
# some systems empty at boot - then a random picture used to come back). --restore puts it back: at login, after
# the screens are set up (Settings > Displays), and whenever a screen is plugged in, unplugged or rearranged
# (AutoTiling.py watches i3 for that), so it is drawn for the real layout and never ends up misaligned.
# The same picture fills every monitor.
# shellcheck disable=SC1091
. "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/compat.sh"   # flock, setsid, sed_inplace, pick_random everywhere
WALL_DIR="${WALL_DIR:-$HOME/Pictures/wallpapers}"
cache="${XDG_CACHE_HOME:-$HOME/.cache}/i3"; mkdir -p "$cache"
state="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots"; mkdir -p "$state"
saved="$state/wallpaper"
cfg="${XDG_CONFIG_HOME:-$HOME/.config}/i3"

list() { find -L "$WALL_DIR" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) | sort; }

draw() {   # draw FILE on every monitor, and point the lock screen and the rofi themes at it
  local f="$1"
  # one at a time: login and a screen change can ask together
  exec 8>"$cache/wallpaper.lock"; flock -w 10 8
  feh --no-fehbg --bg-fill "$f"
  ln -sfn "$f" "$cache/current_wallpaper"
  "$cfg/scripts/RofiFocusedWallpaperLink.sh" >/dev/null 2>&1 || true
}

set_wall() {
  local f
  f=$(readlink -f "$1") || exit 1
  [ -f "$f" ] || { notify-send "Wallpaper" "not found: $f"; exit 1; }
  printf '%s\n' "$f" >"$saved.tmp" && mv -f "$saved.tmp" "$saved"     # remember it (written whole, never half)
  draw "$f"
}

chosen() {   # the remembered wallpaper, if it still exists
  local f=""
  [ -f "$saved" ] && f=$(head -n1 "$saved")
  # (older versions kept it only as a link in ~/.cache)
  [ -z "$f" ] && [ -e "$cache/current_wallpaper" ] && f=$(readlink -f "$cache/current_wallpaper")
  [ -n "$f" ] && [ -f "$f" ] && printf '%s\n' "$f"
}

case "$1" in
  --set)     set_wall "$2" ;;
  --restore)
    f=$(chosen)
    if [ -n "$f" ]; then
      [ -f "$saved" ] || printf '%s\n' "$f" >"$saved"
      draw "$f"
    else
      # nothing picked yet (or the picture was deleted): the default one, else any
      f="$WALL_DIR/night-streetlights.jpg"
      [ -f "$f" ] || f=$(list | pick_random)
      [ -n "$f" ] && set_wall "$f"
    fi ;;
  --random)  f=$(list | pick_random); if [ -n "$f" ]; then set_wall "$f"; else notify-send "Wallpaper" "no images in $WALL_DIR"; fi ;;
  --select|"")
    pkill -x rofi 2>/dev/null
    sel=$(list | while read -r p; do printf '%s\0icon\x1f%s\n' "$(basename "$p")" "$p"; done |
          rofi -dmenu -i -show-icons -p "Wallpaper" -config "$cfg/rofi/config-wallpaper.rasi")
    [ -n "$sel" ] && set_wall "$(list | awk -F/ -v s="$sel" '$NF==s{print; exit}')" ;;
esac
