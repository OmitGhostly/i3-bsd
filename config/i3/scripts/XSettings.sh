#!/usr/bin/env bash
# xsettingsd tells GTK programs - also Flatpak ones, and ones that are already open - which cursor theme and size
# to use (Settings > Mouse > Mouse cursor writes its file), so the pointer looks the same over every window.
# i3 runs this at login; the settings window runs it after a change (it makes a running copy re-read its file).
# shellcheck disable=SC1091
. "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/compat.sh"   # flock, setsid, sed_inplace, pick_random everywhere
command -v xsettingsd >/dev/null 2>&1 || exit 0
conf="${XDG_CONFIG_HOME:-$HOME/.config}/xsettingsd/xsettingsd.conf"
[ -f "$conf" ] || exit 0                       # no cursor chosen yet: GTK uses its settings.ini
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/i3dots-xsettings-$UID.lock"
flock -w 5 9 || exit 0
if pgrep -u "$UID" -x xsettingsd >/dev/null 2>&1; then
  pkill -HUP -u "$UID" -x xsettingsd           # re-read the file
  exit 0
fi
setsid xsettingsd -c "$conf" >/dev/null 2>&1 9>&- </dev/null &
for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -u "$UID" -x xsettingsd >/dev/null 2>&1 && break; sleep 0.1; done
exit 0
