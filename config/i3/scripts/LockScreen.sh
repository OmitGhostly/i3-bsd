#!/usr/bin/env bash
# i3lock / i3lock-color; foreground so xss-lock can track it.
pgrep -x i3lock >/dev/null && exit 0
ACCENT=ffffff; ACCENT_MUTED=8c8c8c; . "${XDG_CONFIG_HOME:-$HOME/.config}/i3/accent.conf" 2>/dev/null   # colour chosen in Settings > Colors
[[ $ACCENT =~ ^[0-9a-fA-F]{6}$ ]] || ACCENT=ffffff; [[ $ACCENT_MUTED =~ ^[0-9a-fA-F]{6}$ ]] || ACCENT_MUTED=8c8c8c
cache="${XDG_CACHE_HOME:-$HOME/.cache}/i3"; mkdir -p "$cache"
wall="$cache/current_wallpaper"; img="$cache/lock.png"
args=(-n -c 010102)
im=$(command -v magick || command -v convert)
if [ -e "$wall" ] && [ -n "$im" ]; then
  if [ ! -f "$img" ] || [ "$wall" -nt "$img" ]; then
    res=$(xdpyinfo 2>/dev/null | awk '/dimensions:/{print $2}'); res=${res:-1920x1080}
    "$im" "$wall" -resize "${res}^" -gravity center -extent "$res" -blur 0x6 "$img" 2>/dev/null
  fi
  [ -f "$img" ] && args=(-n -i "$img")
fi
if i3lock --version 2>&1 | grep -qi 'color'; then
  args+=(--clock --indicator --time-str="%H:%M" --date-str="%A, %d %B" --radius 90 --ring-width 6
    --inside-color=00000066 "--ring-color=${ACCENT}ff" --line-color=00000000 "--keyhl-color=${ACCENT_MUTED}ff"
    "--bshl-color=${ACCENT}55" "--time-color=${ACCENT}ff" "--date-color=${ACCENT}ff")
fi
exec i3lock "${args[@]}"
