#!/usr/bin/env bash
# Touchpad gestures: three fingers left / right go to the next / previous workspace (Workspace.py).
# Touchégg reads the touchpad in a system service; this script runs its
# client in your session, which does the actions in ~/.config/touchegg/touchegg.conf (written by the settings
# window: Settings > Mouse & touchpad > Touchpad gestures).
#   Gestures.sh           start the client if gestures are on and it is not running yet (i3 runs this at start)
#   Gestures.sh restart   restart it (the settings window does this after a change)
#   Gestures.sh stop      stop it
# (Touchégg is made for Linux only: elsewhere there is nothing to do)
command -v touchegg >/dev/null 2>&1 || exit 0
# shellcheck disable=SC1091
. "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/compat.sh"   # flock, setsid, sed_inplace, pick_random everywhere
# is it running? (ps, not pgrep: a just-killed copy that has not been cleaned up yet must not count)
running() { ps -U "$(id -un)" -o stat=,comm= 2>/dev/null | awk -v n="touchegg" '$2 == n && $1 !~ /^Z/ {f = 1} END {exit !f}'; }
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/i3dots-gestures-$UID.lock"
flock -w 10 9 || exit 0          # one at a time (login and the settings window may both ask)
stop() {
  pkill -u "$UID" -x touchegg 2>/dev/null       # only your client: the service runs as root
  for _ in 1 2 3 4 5 6 7 8 9 10; do running || return 0; sleep 0.1; done
  pkill -KILL -u "$UID" -x touchegg 2>/dev/null
}
case "${1:-}" in
  stop) stop; exit 0 ;;
  restart) stop ;;
  '') ;;
  *) echo "usage: $0 [restart|stop]" >&2; exit 2 ;;
esac
state=$(python3 "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/SettingsGUI.py" --gestures 2>/dev/null)
if [ "$state" = off ]; then stop; exit 0; fi
running && exit 0
setsid touchegg >/dev/null 2>&1 9>&- </dev/null &
# hold the lock until it shows up, so a second call right after this one does not start another copy
for _ in 1 2 3 4 5 6 7 8 9 10; do running && break; sleep 0.1; done
exit 0
