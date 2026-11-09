#!/usr/bin/env bash
# Open the browser from defaults.conf; empty = your system default browser.
source "${XDG_CONFIG_HOME:-$HOME/.config}/i3/defaults.conf" 2>/dev/null
if [ -n "${browser:-}" ] && command -v "${browser%% *}" >/dev/null 2>&1; then exec $browser; fi
exec xdg-open "https://www.google.com"
