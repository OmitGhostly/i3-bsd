#!/usr/bin/env bash
# ==================================================
#  KoolDots (2026)
#  Project URL: https://github.com/LinuxBeginnings
#  License: GNU GPLv3
#  SPDX-License-Identifier: GPL-3.0-or-later
# ==================================================
# Rofi SSH menu - list SSH hosts from ~/.ssh/config and connect.

set -euo pipefail

SSH_CONFIG="${HOME}/.ssh/config"
ROFI_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/i3/rofi/config.rasi"
MSG='Select a host to connect via SSH'

notify() {
  if command -v notify-send >/dev/null 2>&1; then
    notify-send -u low "Rofi SSH" "$1"
  else
    printf '%s\n' "$1" >&2
  fi
}

if [[ ! -f "${SSH_CONFIG}" ]]; then
  notify "SSH config not found: ${SSH_CONFIG}"
  exit 1
fi

# Build list: host|user|hostname
host_entries="$(
  awk '
    function is_wildcard(h) { return (h ~ /[*?]/ || h ~ /^!/); }
    function remember_hosts(list,   i, n, h) {
      delete current
      n = split(list, parts, /[ \t]+/)
      for (i = 1; i <= n; i++) {
        h = parts[i]
        if (h == "") continue
        if (is_wildcard(h)) continue
        current[h] = 1
        if (!(h in seen)) {
          seen[h] = 1
          order[++count] = h
        }
      }
    }
    {
      sub(/[ \t]*#.*/, "", $0)
      if ($0 ~ /^[ \t]*$/) next
      if ($1 == "Host") {
        $1 = ""
        sub(/^[ \t]+/, "", $0)
        remember_hosts($0)
        next
      }
      if ($1 == "HostName") {
        for (h in current) hostname[h] = $2
        next
      }
      if ($1 == "User") {
        for (h in current) user[h] = $2
        next
      }
    }
    END {
      for (i = 1; i <= count; i++) {
        h = order[i]
        print h "|" (h in user ? user[h] : "") "|" (h in hostname ? hostname[h] : "")
      }
    }
  ' "${SSH_CONFIG}"
)"

if [[ -z "${host_entries}" ]]; then
  notify "No SSH hosts found in ${SSH_CONFIG}"
  exit 1
fi

menu_entries="$(
  while IFS='|' read -r host user hostname; do
    [[ -n "${host}" ]] || continue
    [[ -n "${user}" ]] || user="${USER:-$(id -un)}"
    [[ -n "${hostname}" ]] || hostname="${host}"
    printf '%s | %s@%s\n' "${host}" "${user}" "${hostname}"
  done <<< "${host_entries}"
)"

# Close any existing rofi before launching
if pgrep -x "rofi" >/dev/null 2>&1; then
  pkill -x rofi
fi

"${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/RofiFocusedWallpaperLink.sh" >/dev/null 2>&1 || true
selection="$(printf '%s\n' "${menu_entries}" | rofi -dmenu -i -p "SSH" -mesg "${MSG}" -config "${ROFI_CONFIG}")"

if [[ -z "${selection}" ]]; then
  exit 0
fi

selected_host="${selection%% | *}"
if [[ -z "${selected_host}" ]]; then
  exit 0
fi

# the name comes from ~/.ssh/config: accept only plain host names (no shell characters, never an ssh option)
if [[ ! "${selected_host}" =~ ^[A-Za-z0-9][A-Za-z0-9._@:-]*$ ]]; then
  notify "Refusing to connect: unusual host name '${selected_host}'"
  exit 1
fi

if command -v ghostty >/dev/null 2>&1; then
  exec ghostty --title="SSH ${selected_host}" -e ssh -- "${selected_host}"
fi

if command -v kitty >/dev/null 2>&1; then
  exec kitty --title "SSH ${selected_host}" ssh -- "${selected_host}"
fi

if command -v alacritty >/dev/null 2>&1; then
  exec alacritty -e ssh -- "${selected_host}"
fi

notify "No supported terminal found (kitty, ghostty, alacritty). Unable to start SSH session."
exit 1
