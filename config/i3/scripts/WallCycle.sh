#!/usr/bin/env bash
# Wallpaper slideshow: the wallpaper changes to the next picture of a folder every so often (Settings > Wallpaper).
#
#   WallCycle.sh --start    (re)start it with the saved choice (i3 runs this at login; the Settings window on Apply)
#   WallCycle.sh --stop     stop it
#   WallCycle.sh --next     the next picture now
#   WallCycle.sh --status   on / off, the folder, how often
#
# The choice is in ~/.local/state/i3wm-dots/wallcycle.conf (written by the Settings window):
#   enabled=1   folder=/path/to/pictures   interval=SECONDS (0 = at every login)   order=random | name
# The time of the last change is remembered, so "every day" also counts the time you were logged out; picking a
# wallpaper yourself (SUPER+W, or in the Settings window) starts the wait again.
# shellcheck disable=SC1091
. "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/compat.sh"   # flock, setsid, sed_inplace, pick_random
scripts="${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts"
state="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots"; mkdir -p "$state"
conf="$state/wallcycle.conf"
last="$state/wallcycle-last"          # when the wallpaper last changed (seconds since 1970)
deck="$state/wallcycle-deck"          # random order: the pictures still to come, so none repeats before all were shown
pidf="${XDG_RUNTIME_DIR:-/tmp}/i3dots-wallcycle-$(id -u).pid"

enabled=0 folder="$HOME/Pictures/wallpapers" interval=0 order=random
if [ -f "$conf" ]; then
  while IFS='=' read -r k v; do
    case "$k" in
      enabled) [ "$v" = 1 ] && enabled=1 ;;
      folder) [ -n "$v" ] && folder="$v" ;;
      interval) case "$v" in ''|*[!0-9]*) ;; *) interval="$v" ;; esac ;;
      order) [ "$v" = name ] && order=name ;;
    esac
  done <"$conf"
fi
# (the Settings window's "Next picture now" passes the folder and order shown there, before Apply)
folder="${WALLCYCLE_FOLDER:-$folder}"
case "${WALLCYCLE_ORDER:-}" in name|random) order="$WALLCYCLE_ORDER" ;; esac

pictures() { find -L "$folder" -maxdepth 3 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) 2>/dev/null | sort; }
current() { head -n1 "$state/wallpaper" 2>/dev/null; }
now() { date +%s; }

pick_next() {   # the picture after the current one
  local cur list n
  cur="$(current)"
  list="$(pictures)"
  [ -n "$list" ] || return 1
  if [ "$order" = name ]; then
    # the next one by name, after the last one the first again (or the first, when the current one is not in there)
    n="$(printf '%s\n' "$list" | awk -v c="$cur" 'NR == 1 { first = $0 } found { print; exit } $0 == c { found = 1 }
                                                  END { if (!found || NR == 1) print first }' | head -n1)"
    [ -z "$n" ] && n="$(printf '%s\n' "$list" | head -n1)"
  else
    # shuffled: the next one from the deck; a new shuffle once all were shown (never the current one twice in a row)
    n=""
    while [ -z "$n" ]; do
      if [ ! -s "$deck" ]; then
        # (the one showing now is never first: it goes somewhere later, so it is not left out of this round)
        printf '%s\n' "$list" | awk -v s="$((RANDOM * 32768 + RANDOM))" 'BEGIN { srand(s) } { printf "%.9f\t%s\n", rand(), $0 }' \
          | sort -n | cut -f2- | awk -v c="$cur" -v s="$((RANDOM * 32768 + RANDOM))" '
              BEGIN { srand(s) } $0 == c { have = 1; next } { a[++n] = $0 }
              END { k = have && n ? int(rand() * n) + 2 : 0
                    for (i = 1; i <= n; i++) { if (i == k) print c; print a[i] } if (have && (k > n || !n)) print c }' \
          >"$deck.tmp" && mv -f "$deck.tmp" "$deck"
        [ "$(printf '%s\n' "$list" | wc -l)" -le 1 ] && { n="$(head -n1 "$deck")"; : >"$deck"; break; }
      fi
      n="$(head -n1 "$deck")"
      tail -n +2 "$deck" >"$deck.tmp" && mv -f "$deck.tmp" "$deck"
      # (a picture deleted since the shuffle, or the one showing now: the next one)
      if [ ! -f "$n" ] || [ "$n" = "$cur" ] || ! printf '%s\n' "$list" | grep -qxF -- "$n"; then n=""; fi
    done
  fi
  printf '%s\n' "$n"
}

next() {
  local n
  n="$(pick_next)" || { notify-send -u low "Wallpaper" "No pictures in $folder" 2>/dev/null; return 1; }
  [ -n "$n" ] || return 1
  "$scripts/Wallpaper.sh" --set "$n"          # (it also writes the time into $last)
}

stop() {
  local p
  p="$(cat "$pidf" 2>/dev/null)"
  case "$p" in ''|*[!0-9]*) rm -f "$pidf"; return 0 ;; esac
  ps -p "$p" -o args= 2>/dev/null | grep -q 'WallCycle' && kill "$p" 2>/dev/null
  rm -f "$pidf"
  for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 0.1; done   # (gone before a new one starts)
}

forget_pid() { [ "$(cat "$pidf" 2>/dev/null)" = "$$" ] && rm -f "$pidf"; }   # (only our own: a new one may be there)

daemon() {
  echo $$ >"$pidf"
  trap 'kill "$sl" 2>/dev/null; forget_pid; exit 0' TERM INT
  sl=""
  [ -s "$last" ] || now >"$last"
  while :; do
    i3-msg -t get_version >/dev/null 2>&1 || break       # i3 is gone (logged out): so is the slideshow
    l="$(cat "$last" 2>/dev/null)"; case "$l" in ''|*[!0-9]*) l=0 ;; esac
    left=$(( l + interval - $(now) ))
    if [ "$left" -le 0 ]; then
      next || now >"$last"                                # (an empty folder: try again after the next wait)
      left="$interval"
    fi
    # wake up at least every 30 seconds: after a suspend, or a picture picked by hand, the wait is counted again
    [ "$left" -gt 30 ] && left=30
    sleep "$left" & sl=$!; wait "$sl"
  done
  forget_pid
}

case "${1:-}" in
  --start)
    stop
    [ "$enabled" = 1 ] || exit 0
    if [ "$interval" -eq 0 ]; then
      next                                                # "at every login": once, now
    else
      [ "$interval" -lt 10 ] && interval=10
      nohup "$0" --daemon >/dev/null 2>&1 </dev/null &
    fi ;;
  --daemon) [ "$enabled" = 1 ] && [ "$interval" -gt 0 ] && daemon ;;
  --stop) stop ;;
  --next) next ;;
  --status)
    if [ "$enabled" = 1 ]; then
      if [ "$interval" -eq 0 ]; then how="at every login"; else how="every $interval seconds"; fi
      run="not running"; [ -s "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null && run="running"
      [ "$interval" -eq 0 ] && run="-"
      echo "on: $folder, $how, ${order} order ($run)"
    else
      echo "off"
    fi ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
