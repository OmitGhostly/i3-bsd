#!/usr/bin/env bash
# Open the terminal from defaults.conf; if it is not installed, fall back to the next one that is.
#   LaunchTerminal.sh [TERMINAL]          a terminal window (TERMINAL: that one instead of the default)
#   LaunchTerminal.sh --run PROGRAM ARGS  PROGRAM in a terminal window (how yazi and other terminal apps open)
source "${XDG_CONFIG_HOME:-$HOME/.config}/i3/defaults.conf" 2>/dev/null
# (kitty's own installer puts it in ~/.local/bin, Snap puts Ghostty in /snap/bin)
PATH="$PATH:$HOME/.local/bin:/snap/bin"

if [ "${1:-}" = --run ]; then
  shift
  [ "$#" -gt 0 ] || exit 2
  for t in "${term:-ghostty}" ghostty kitty alacritty xterm; do
    command -v "${t%% *}" >/dev/null 2>&1 || continue
    # each terminal's own way to run a program (most take -e PROGRAM ARGS...)
    name="${t%% *}"; name="${name##*/}"
    case "$name" in
      kitty)                      exec $t "$@" ;;
      wezterm)                    exec $t start -- "$@" ;;
      gnome-terminal)             exec $t -- "$@" ;;
      xfce4-terminal|terminator)  exec $t -x "$@" ;;
      tilix|lxterminal|qterminal) exec $t -e "$(printf '%q ' "$@")" ;;     # (these take the command as one string)
      *)                          exec $t -e "$@" ;;                      # ghostty, alacritty, konsole, st, urxvt, xterm
    esac
  done
  notify-send -u critical "Terminal" "No terminal found to run $1 in (tried ${term:-ghostty}, ghostty, kitty, alacritty, xterm)" 2>/dev/null
  exit 1
fi

want="${1:-${term:-ghostty}}"
for t in "$want" ghostty kitty alacritty xterm; do
  if command -v "${t%% *}" >/dev/null 2>&1; then exec $t; fi
done
notify-send -u critical "Terminal" "No terminal found (tried $want, ghostty, kitty, alacritty, xterm)" 2>/dev/null
exit 1
