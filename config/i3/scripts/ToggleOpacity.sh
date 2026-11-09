#!/usr/bin/env bash
id=$(xdotool getwindowfocus) || exit 1
if xprop -id "$id" _NET_WM_WINDOW_OPACITY 2>/dev/null | grep -q '= '; then xprop -id "$id" -remove _NET_WM_WINDOW_OPACITY
else xprop -id "$id" -f _NET_WM_WINDOW_OPACITY 32c -set _NET_WM_WINDOW_OPACITY 0xD9999999; fi
