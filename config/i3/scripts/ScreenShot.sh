#!/usr/bin/env bash
# X11 version of the grim/slurp script. Needs: maim xdotool xclip (optional: swappy/flameshot)
dir="$HOME/Pictures/Screenshots"; mkdir -p "$dir"
f="$dir/Screenshot_$(date +%d-%b_%H-%M-%S)_$RANDOM.png"
finish() {
  [ -s "$f" ] || { notify-send -u low "Screenshot" "cancelled"; exit 1; }
  xclip -selection clipboard -t image/png -i "$f"
  "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/Sounds.sh" --screenshot 2>/dev/null
  notify-send -i "$f" "Screenshot saved" "$f (also copied to clipboard)"
}
countdown() { for ((i=$1;i>0;i--)); do notify-send -t 900 -h string:x-dunst-stack-tag:shot "Screenshot in $i"; sleep 1; done; }
# While you drag a box, picom (version 10 and others) counts the window under it as unfocused and dims it
# (inactive-dim in picom.conf), and it takes about 0.2 s to fade back. maim takes the picture the moment you
# let go, so wait 0.3 s first or the snip comes out darker than the screen. (maim prints its countdown on
# stderr, not into the picture.)
snip_wait=0.3
# center_editor PID: center swappy's window once it has its size. i3 centers a floating window the moment it
# opens, but swappy (1.8) opens small and then grows to fit the picture - to the right and down, so a big snip
# ran off the screen, Save button and all.
center_editor() {
  command -v xdotool >/dev/null && command -v i3-msg >/dev/null || return 0
  local w="" geo="" last="" i
  for i in $(seq 1 50); do               # (up to 5 s for it to open)
    w="$(xdotool search --all --onlyvisible --pid "$1" --class swappy 2>/dev/null | tail -1)"
    [ -n "$w" ] && break; kill -0 "$1" 2>/dev/null || return 0; sleep 0.1
  done
  [ -n "$w" ] || return 0
  for i in $(seq 1 20); do               # (until its size holds for 0.2 s)
    sleep 0.1; geo="$(xdotool getwindowgeometry "$w" 2>/dev/null | tail -1)"
    [ -n "$geo" ] && [ "$geo" = "$last" ] && [ "$i" -ge 3 ] && break; last="$geo"
  done
  i3-msg -q "[id=$w] move position center" >/dev/null 2>&1
}
case "$1" in
  --now)    maim "$f"; finish ;;
  --in5)    countdown 5;  maim "$f"; finish ;;
  --in10)   countdown 10; maim "$f"; finish ;;
  --active) maim -i "$(xdotool getactivewindow)" "$f"; finish ;;
  --area)   maim -s -u -b 2 -d "$snip_wait" "$f" 2>/dev/null; finish ;;
  --swappy)
    if command -v swappy >/dev/null; then
      # (the snip goes to a file first, so swappy - and the centering - start only once you have let go)
      snap="$(mktemp "${TMPDIR:-/tmp}/snip.XXXXXX")" || exit 1
      trap 'rm -f "$snap"' EXIT
      maim -s -u -d "$snip_wait" -f png "$snap" 2>/dev/null
      [ -s "$snap" ] || exit 0               # (cancelled: Esc or right-click)
      swappy -f "$snap" & editor=$!
      center_editor "$editor"
      wait "$editor"
    elif command -v flameshot >/dev/null; then flameshot gui
    else notify-send "Screenshot" "install swappy or flameshot"; fi ;;
  *) echo "usage: $0 --now|--area|--active|--in5|--in10|--swappy"; exit 1 ;;
esac
