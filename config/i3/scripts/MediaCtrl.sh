#!/usr/bin/env bash
# ==================================================
#  KoolDots (2026)
#  Project URL: https://github.com/LinuxBeginnings
#  License: GNU GPLv3
#  SPDX-License-Identifier: GPL-3.0-or-later
# ==================================================
# The media keys: playerctl (any player that speaks MPRIS). Where playerctl is missing (NetBSD has no package of
# it) or sees no player, the music menu's mpv (RofiBeats.sh) through its control socket.

music_icon="${XDG_CONFIG_HOME:-$HOME/.config}/i3/icons/music.png"
mpv_sock="${XDG_RUNTIME_DIR:-/tmp}/i3dots-mpv-$(id -u).sock"

# playerctl is there and has a player to talk to
use_playerctl() { command -v playerctl >/dev/null 2>&1 && playerctl status >/dev/null 2>&1; }

# mpv_cmd COMMAND [ARG...]: one command to mpv's control socket (JSON IPC); prints the answer's value, if any.
# Fails when no mpv is listening.
mpv_cmd() {
  [ -S "$mpv_sock" ] && command -v python3 >/dev/null 2>&1 || return 1
  python3 - "$mpv_sock" "$@" <<'EOF'
import json, socket, sys
s = socket.socket(socket.AF_UNIX)
s.settimeout(1)
try:
    s.connect(sys.argv[1])
    s.sendall((json.dumps({"command": sys.argv[2:]}) + "\n").encode())
    buf = b""
    while True:                                   # (mpv may send event lines before the answer)
        while b"\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                sys.exit(1)
            buf += chunk
        line, buf = buf.split(b"\n", 1)
        reply = json.loads(line or b"{}")
        if "event" not in reply:
            break
except (OSError, ValueError):
    sys.exit(1)
value = reply.get("data")
if isinstance(value, bool):
    print("yes" if value else "no")
elif value is not None and not isinstance(value, (dict, list)):
    print(value)
sys.exit(0 if reply.get("error") == "success" else 1)
EOF
}

nothing_playing() { notify-send -e -u low -i "$music_icon" " Playback:" " Nothing to control"; }

# Play the next track
play_next() {
  if use_playerctl; then playerctl next
  elif ! mpv_cmd playlist-next weak >/dev/null; then nothing_playing; return; fi
  show_music_notification
}

# Play the previous track
play_previous() {
  if use_playerctl; then playerctl previous
  elif ! mpv_cmd playlist-prev weak >/dev/null; then nothing_playing; return; fi
  show_music_notification
}

# Toggle play/pause
toggle_play_pause() {
  if use_playerctl; then playerctl play-pause
  elif ! mpv_cmd cycle pause >/dev/null; then nothing_playing; return; fi
  sleep 0.1
  show_music_notification
}

# Stop playback
stop_playback() {
  if use_playerctl; then playerctl stop
  elif ! mpv_cmd stop >/dev/null; then nothing_playing; return; fi
  notify-send -e -u low -i "$music_icon" " Playback:" " Stopped"
}

# Display notification with song information
show_music_notification() {
  local status song_title song_artist
  if use_playerctl; then
    status=$(playerctl status)
    song_title=$(playerctl metadata title)
    song_artist=$(playerctl metadata artist)
  else
    sleep 0.2                                     # (the next track has a moment to start)
    case "$(mpv_cmd get_property pause)" in
      no) status=Playing ;;
      yes) status=Paused ;;
    esac
    song_title=$(mpv_cmd get_property media-title)
    song_artist=$(mpv_cmd get_property metadata/by-key/artist 2>/dev/null)
  fi
  if [[ "$status" == "Playing" ]]; then
    notify-send -e -u low -i "$music_icon" "Now Playing:" "$song_title${song_artist:+ by $song_artist}"
  elif [[ "$status" == "Paused" ]]; then
    notify-send -e -u low -i "$music_icon" " Playback:" " Paused"
  fi
}

# Get media control action from command line argument
case "$1" in
"--nxt")
  play_next
  ;;
"--prv")
  play_previous
  ;;
"--pause")
  toggle_play_pause
  ;;
"--stop")
  stop_playback
  ;;
*)
  echo "Usage: $0 [--nxt|--prv|--pause|--stop]"
  exit 1
  ;;
esac
