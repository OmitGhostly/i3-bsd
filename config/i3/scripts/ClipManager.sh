#!/usr/bin/env bash
# Clipboard history: clipmenu in rofi if installed, otherwise CopyQ.
pkill -x rofi 2>/dev/null
if command -v clipmenu >/dev/null 2>&1; then
  CM_LAUNCHER=rofi clipmenu -p "Clipboard" -config "${XDG_CONFIG_HOME:-$HOME/.config}/i3/rofi/config-clipboard.rasi"
elif command -v copyq >/dev/null 2>&1; then
  copyq toggle
else
  notify-send "Clipboard" "install clipmenu or copyq"
fi
