#!/usr/bin/env bash
# Stay awake: stops the screen from blanking / locking until you turn it off or log out.
# Usage: toggle | on | off | status   (the polybar coffee button calls this)
ACCENT=ffffff; . "${XDG_CONFIG_HOME:-$HOME/.config}/i3/accent.conf" 2>/dev/null   # colour chosen in Settings > Colors
[[ $ACCENT =~ ^[0-9a-fA-F]{6}$ ]] || ACCENT=ffffff
is_on() { [ "$(cat "${XDG_RUNTIME_DIR:-/tmp}/i3dots-caffeine" 2>/dev/null)" = on ]; }
on() {
  is_on && return 0
  xset s off -dpms 2>/dev/null                  # no screensaver blanking / auto-lock, no monitor power-off
  echo on > "${XDG_RUNTIME_DIR:-/tmp}/i3dots-caffeine"
}
off() {
  xset s 600 5 +dpms 2>/dev/null; xset dpms 0 0 720 2>/dev/null   # back to the timers Input.sh sets at login
  rm -f "${XDG_RUNTIME_DIR:-/tmp}/i3dots-caffeine"
}
case "$1" in
  toggle) icon="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons/coffee.png"
          if is_on; then off; notify-send -u low -i "$icon" "Stay awake" "off - the screen can sleep again" 2>/dev/null
          else on; notify-send -u low -i "$icon" "Stay awake" "on - the screen will not sleep or lock" 2>/dev/null; fi ;;
  on)  on ;;
  off) off ;;
  status)
    # the bar's block styles colour the whole block; the Flat and Underline styles colour the mug itself
    case "${BAR_STYLE:-flat}" in flat|underline) plain=false ;; *) plain=true ;; esac
    if [ "$plain" = true ]; then
      if is_on; then echo "%{T2}󰅶%{T-} awake"; else echo "%{T2}󰛊%{T-}"; fi
    elif is_on; then echo "%{T2}%{F#$ACCENT}󰅶%{F-}%{T-}%{F#$ACCENT} awake%{F-}"; else echo "%{T2}%{F#6e6e6e}󰛊%{F-}%{T-}"; fi ;;
  *) echo "usage: $0 toggle|on|off|status" >&2; exit 1 ;;
esac
