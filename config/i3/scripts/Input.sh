#!/usr/bin/env bash
# What Hyprland's [input] block did. Edit layout here (e.g. "us,de").
#   Input.sh            everything (i3 runs this at login)
#   Input.sh --devices  only the keyboard and touchpad settings: InputWatch.py runs this when a keyboard, mouse or
#                       touchpad is plugged in or reconnects, since a new device starts with the defaults
setxkbmap -layout us -option grp:alt_shift_toggle
xset r rate 300 50
if [ "${1:-}" != --devices ]; then
  command -v numlockx >/dev/null && numlockx on
  # screen blanking (not on a device change: that would undo "stay awake")
  xset s 600 5; xset +dpms 2>/dev/null; xset dpms 0 0 720 2>/dev/null   # (no DPMS on some servers: VMs, Xvfb)
fi
if command -v xinput >/dev/null; then
  # by id: two devices can share a name, and xinput refuses an ambiguous name
  xinput list --short | grep -iE 'touchpad|trackpad' | grep -iE 'slave +pointer' | grep -o 'id=[0-9]*' | cut -d= -f2 | while read -r dev; do
    for p in "libinput Tapping Enabled" "libinput Natural Scrolling Enabled" "libinput Disable While Typing Enabled"; do
      xinput set-prop "$dev" "$p" 1 2>/dev/null
    done
  done
fi
