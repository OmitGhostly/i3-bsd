#!/usr/bin/env bash
# Drop-down terminal via i3 scratchpad (window rules in the i3 config float/size it).
# Uses ghostty when installed, otherwise kitty.
if command -v ghostty >/dev/null 2>&1; then
  cls="com.i3dots.dropterm"
  if xdotool search --class "$cls" >/dev/null 2>&1; then
    i3-msg "[class=\"$cls\"] scratchpad show" >/dev/null
  else
    ghostty --class="$cls" --gtk-single-instance=false &
  fi
else
  if xdotool search --class kitty-dropterm >/dev/null 2>&1; then
    i3-msg '[class="kitty-dropterm"] scratchpad show' >/dev/null
  else
    kitty --class kitty-dropterm &
  fi
fi
