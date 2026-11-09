#!/usr/bin/env bash
# Open the file manager from defaults.conf (Settings > Keybindings, the file manager row; yazi by default).
#   LaunchFileManager.sh               the default one (SUPER+E)
#   LaunchFileManager.sh APP           that one instead, e.g. thunar
#   LaunchFileManager.sh --open PATH   the default one at PATH: a folder, a file (shown in its folder) or a file://
#                                      address - how folders open from other apps (xdg-open, "Show in folder"...)
# Terminal file managers (yazi, ranger, lf, nnn, mc, vifm...) open in your terminal. If the chosen one is not
# installed, the next one that is: yazi, then the usual graphical ones.
source "${XDG_CONFIG_HOME:-$HOME/.config}/i3/defaults.conf" 2>/dev/null
# (yazi from its own download lives in ~/.local/bin, from the Snap Store in /snap/bin)
PATH="$PATH:$HOME/.local/bin:/snap/bin"
# what yazi uses to edit a text file (e): the editor from defaults.conf when none is set
export EDITOR="${EDITOR:-${editor:-nano}}"
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

fm="${files:-yazi}" where=""
if [ "${1:-}" = --open ]; then
  where="${2:-}"
  case "$where" in
    file://*)       # file:///home/me/My%20Files -> /home/me/My Files
      where="${where#file://}"; where="${where#localhost}"
      where="${where//\\/\\\\}"; where="$(printf '%b' "${where//%/\\x}")" ;;
  esac
  [ -e "$where" ] || where=""            # (gone, or not a local path: the home folder)
elif [ -n "${1:-}" ]; then
  fm="$1"
fi

is_terminal_app() {
  case "${1##*/}" in yazi|ranger|lf|nnn|mc|vifm|joshuto|xplr|broot|superfile|spf) return 0 ;; esac
  return 1
}

# open_with COMMAND: start it (at $where when there is one); returns only when it is not installed
open_with() {
  local bin="${1%% *}" at="$where"
  command -v "$bin" >/dev/null 2>&1 || return 1
  if is_terminal_app "$bin"; then
    # (yazi given a file opens its folder with the file selected; $1 unquoted: a command can have arguments)
    # shellcheck disable=SC2086
    exec "$here/LaunchTerminal.sh" --run $1 ${at:+"$at"}
  fi
  [ -n "$at" ] && [ ! -d "$at" ] && at="$(dirname -- "$at")"     # (graphical ones: the file's folder)
  exec $1 ${at:+"$at"}
}

# (no folder given: start in your home folder, wherever i3 itself was started from)
[ -n "$where" ] || cd "$HOME" 2>/dev/null || true
open_with "$fm"
for alt in yazi thunar nautilus pcmanfm dolphin nemo; do
  [ "$alt" = "${fm%% *}" ] || open_with "$alt"
done
notify-send -u critical "File manager" "None found (tried ${fm%% *}, yazi, thunar, nautilus, pcmanfm, dolphin, nemo)" 2>/dev/null
exit 1
