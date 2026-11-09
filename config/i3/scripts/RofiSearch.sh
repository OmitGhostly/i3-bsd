#!/usr/bin/env bash
search_engine="https://www.google.com/search?q={}"      # (defaults.conf can change it)
# shellcheck disable=SC1091
source "${XDG_CONFIG_HOME:-$HOME/.config}/i3/defaults.conf" 2>/dev/null
command -v jq >/dev/null || { notify-send "Rofi Search" "jq is required (URL encoding)"; exit 1; }
pkill -x rofi 2>/dev/null
q=$(printf '' | rofi -dmenu -config "${XDG_CONFIG_HOME:-$HOME/.config}/i3/rofi/config-search.rasi" -mesg "search via default web browser")
[ -z "$q" ] && exit 0
enc=$(printf '%s' "$q" | jq -sRr @uri)
xdg-open "${search_engine//\{\}/$enc}"
