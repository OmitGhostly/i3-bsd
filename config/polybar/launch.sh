#!/usr/bin/env bash
# One polybar per chosen monitor; the system tray (a module, first in the right-hand list) on the primary monitor
# (or the first chosen one).
# Position (top/bottom) and monitor choice come from the settings window (~/.config/i3/settings.json).
# shellcheck disable=SC1091
. "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/compat.sh"   # flock, setsid, sed_inplace, pick_random
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/polybar-launch-$(id -u).lock"
flock 9   # one launch at a time (the settings window and i3 may both ask)
# stop the running bar(s). A bar that is still starting up can miss the first signal (two restarts in a row,
# e.g. a colour change reloads i3 while the settings window also restarts the bar), so ask again and after
# 3 seconds force it - never wait forever with no bar on screen
for ((try = 0; try < 15; try++)); do
  pgrep -u "$UID" -x polybar >/dev/null || break
  pkill -u "$UID" -x polybar 2>/dev/null
  sleep 0.2
done
pkill -KILL -u "$UID" -x polybar 2>/dev/null
while pgrep -u "$UID" -x polybar >/dev/null; do sleep 0.1; done
# defaults (the Large size, one-colour blocks), used as they are if the settings window cannot be asked
# (python missing, a damaged settings file)
F="FantasqueSansM Nerd Font Mono"
BAR_BOTTOM=false; BAR_MONITORS=""; BAR_HEIGHT=38; BAR_STYLE=solid; BAR_NAME=blocks
BAR_FONT_SPEC="$F:size=13.5;3"; BAR_ICON_SPEC="$F:size=16.5;4"; BAR_CAP_SPEC="$F:size=27.277;5"
BAR_LEFT="i3"
BAR_RIGHT="network pulseaudio backlight caffeine nightlight battery cpu memory gpu date powermenu"
BAR_RIGHT_B=""; BAR_LEFT_B=""
# crisp text: grayscale anti-aliasing with light hinting (applies to programs started afterwards too)
command -v xrdb >/dev/null 2>&1 && printf 'Xft.antialias: 1\nXft.hinting: 1\nXft.hintstyle: hintslight\nXft.rgba: none\n' | xrdb -merge 2>/dev/null
# the saved choices (Settings > Appearance > Bar): position, size (the font lines, in exact whole pixels so the text
# is sharp), style, which items to show (an item the computer has no hardware for is left out). This also writes
# style.ini: the colours, block ends and spacing of the chosen style
# If that cannot be asked right now (in the middle of an update, a python problem), use what it said last time
# instead of the defaults - so the bar never comes back different from how you left it.
state="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots"; mkdir -p "$state"
bar_env=$(python3 "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/SettingsGUI.py" --bar-env 2>/dev/null)
if printf '%s\n' "$bar_env" | grep -q '^BAR_NAME='; then
  printf '%s\n' "$bar_env" >"$state/bar-env.tmp" && mv -f "$state/bar-env.tmp" "$state/bar-env"
elif [ -f "$state/bar-env" ]; then
  bar_env=$(cat "$state/bar-env")
fi
eval "$bar_env"
# (a bar saved before the BSD version had its own repo named these items network-sys, cpu-sys ...)
r=""; for m in $BAR_RIGHT; do r="$r ${m%-sys}"; done; BAR_RIGHT="${r# }"
r=""; for m in $BAR_RIGHT_B; do r="$r ${m%-sys}"; done; BAR_RIGHT_B="${r# }"
if [ "$BAR_BOTTOM" = true ]; then BORDER_BOTTOM=0; BORDER_TOP=1; else BORDER_BOTTOM=1; BORDER_TOP=0; fi
case "$BAR_HEIGHT" in ''|*[!0-9]*) BAR_HEIGHT=38 ;; esac
case "$BAR_NAME" in main|blocks) ;; *) BAR_NAME=blocks ;; esac
[ -n "$BAR_RIGHT_B" ] || BAR_RIGHT_B=$(for m in $BAR_RIGHT; do printf 'b-%s ' "$m"; done)
# (the block bar's workspaces are blocks too: b-i3; an older saved setting only has BAR_LEFT)
[ -n "$BAR_LEFT_B" ] || BAR_LEFT_B=$(for m in $BAR_LEFT; do [ "$m" = i3 ] && printf 'b-i3 ' || printf '%s ' "$m"; done)
# (the joined-up styles' workspace strip is a python script: without a working python3, polybar's own module)
python3 -c 'import json, socket, struct' >/dev/null 2>&1 || BAR_LEFT_B=$(printf '%s' "$BAR_LEFT_B" | sed 's/b-wsj/b-i3/')
export BAR_BOTTOM BAR_HEIGHT BAR_FONT_SPEC BAR_ICON_SPEC BAR_CAP_SPEC BORDER_BOTTOM BORDER_TOP BAR_STYLE \
       BAR_LEFT BAR_LEFT_B BAR_RIGHT BAR_RIGHT_B
# No polybar (NetBSD has no package of it): i3's own bar takes its place. i3 reads its bar from its config, so the
# bar goes into bar-fallback.conf (the i3 config includes it) and i3 restarts in place once (windows stay where they
# are; a reload would not start the bar - i3 starts i3bar only when it starts) - which runs this script again; it
# then finds the bar in place and stops here. Where polybar is installed the file is emptied again the same way.
fallback="${XDG_CONFIG_HOME:-$HOME/.config}/i3/bar-fallback.conf"
# Does the running i3 have that bar? 0 yes, 1 no, 2 i3 cannot be asked right now (it is restarting - and runs this
# script again when it is back)
i3_has_bar() {
  local b
  b=$(i3-msg -t get_bar_config 2>/dev/null) || return 2
  case "$b" in *'"i3dots"'*) return 0 ;; esac
  return 1
}
# The file is right but i3 read its config before the file was written (another restart got in between, e.g. the
# Settings window applying the cursor at login): restart once more. Not again within 20 seconds, so a bar that i3
# will not take can never make it restart over and over.
bar_recheck_restart() {
  local dir stamp now last
  dir="${XDG_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}}"; stamp="$dir/i3dots-bar-restart-$(id -u)"
  now=$(date +%s); last=$(cat "$stamp" 2>/dev/null)
  case "$last" in ''|*[!0-9]*) last=0 ;; esac
  [ $((now - last)) -ge 0 ] && [ $((now - last)) -lt 20 ] && return 0
  # (the time is written down first: without it, no restart at all)
  mkdir -p "$dir" 2>/dev/null; printf '%s\n' "$now" >"$stamp" 2>/dev/null || return 0
  i3-msg -q restart >/dev/null 2>&1
  return 0
}
if ! command -v polybar >/dev/null 2>&1; then
  want=$(python3 "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/SettingsGUI.py" --i3bar-conf 2>/dev/null)
  # shellcheck disable=SC2016
  case "$want" in
    *"bar {"*) ;;
    *) want=$(printf 'bar {\n    id i3dots\n    status_command exec "$HOME/.config/i3/scripts/I3barStatus.py"\n    font pango:%s 13.5\n}' "$F") ;;
  esac
  if [ "$(cat "$fallback" 2>/dev/null)" != "$want" ]; then
    printf '%s\n' "$want" >"$fallback" && i3-msg -q restart >/dev/null 2>&1
  else
    i3_has_bar; [ $? -eq 1 ] && bar_recheck_restart
  fi
  exit 0
fi
if grep -q '^bar' "$fallback" 2>/dev/null; then
  printf "# i3's own bar goes here only when polybar is not installed (NetBSD has no package of it): polybar/launch.sh\n# writes it from the bar you chose in Settings > Appearance. With polybar this file stays like this.\n" >"$fallback" \
    && i3-msg -q restart >/dev/null 2>&1
else
  i3_has_bar && bar_recheck_restart       # (i3's bar still up next to polybar)
fi
all=$(polybar --list-monitors | cut -d: -f1)
sel=""
if [ -n "$BAR_MONITORS" ]; then
  for m in $all; do case " $BAR_MONITORS " in *" $m "*) sel="$sel $m" ;; esac; done
fi
[ -n "$sel" ] || sel=$all   # "all monitors", or none of the chosen ones is connected
primary=$(xrandr --query | awk '/ primary/{print $1; exit}')
sel=$(echo "$sel" | xargs)
read -r first _ <<<"$sel"
traymon=$first
[ -n "$primary" ] && case " $sel " in *" $primary "*) traymon=$primary ;; esac
for m in $sel; do
  if [ "$m" = "$traymon" ]; then right="tray $BAR_RIGHT"; right_b="tray $BAR_RIGHT_B"; else right=$BAR_RIGHT; right_b=$BAR_RIGHT_B; fi
  MONITOR=$m BAR_RIGHT="$right" BAR_RIGHT_B="$right_b" polybar --reload "$BAR_NAME" >"${XDG_RUNTIME_DIR:-$HOME/.cache}/polybar-$m.log" 2>&1 9>&- &
done
