#!/usr/bin/env bash
# Keep the desktop config (i3, bar, Settings window...) up to date with the GitHub repo.
#
# A line in your crontab looks every 30 minutes whether packages were installed or updated (pkg, pkg_add, pkgin);
# when they were, it CHECKS for a newer version: the newest version of the repo is fetched into a private copy
# (~/.local/share/i3wm-dots-updater/repo) and, when there is a newer one, a notification says so - once per new
# version. Nothing is installed until you run "i3dots-update" yourself.
# Installing re-installs the config files the quick way (install.sh --update: no packages, no password). What you
# set in the Settings window (colours, bar style, keybindings, mouse, monitors...) is kept; files you edited by hand
# in ~/.config/i3, ghostty, polybar, ... are replaced - the version before the update is kept, and
# "i3dots-update --undo" puts it back.
# If you were not logged in when packages changed, the check runs at your next login instead.
#
#   i3dots-update                 install the newest version now
#   i3dots-update --check         only say whether there is a newer version
#   i3dots-update --undo          go back to the config from before the last update
#   i3dots-update --off / --on    turn the checks off / on again
#   i3dots-update --status        show the settings and the last update
#   i3dots-update --install-hook  set up the crontab line (no password)
#   i3dots-update --remove-hook   take it away again
#   (--cron and --login are what cron and i3 use; --auto checks right away, quietly)
# flock, setsid, sed_inplace, pick_random: the copy next to this script (also when it runs from a repository
# folder), else the installed one (when started through the i3dots-update link)
# shellcheck disable=SC1091
. "$(dirname "${BASH_SOURCE[0]}")/compat.sh" 2>/dev/null || . "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/compat.sh"
set -uo pipefail

cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
state="${XDG_DATA_HOME:-$HOME/.local/share}/i3wm-dots-updater"
repo="$state/repo"
log="${XDG_CACHE_HOME:-$HOME/.cache}/i3wm-dots-update.log"
default_url="https://github.com/OmitGhostly/i3-bsd.git"
# system files (I3DOTS_TEST_ROOT puts them in a test folder instead)
root="${I3DOTS_TEST_ROOT:-}"

mode="${1:-now}"
quiet=0
case "$mode" in --auto|--login|--cron) quiet=1 ;; esac
cron_mark="# i3wm-dots: update the desktop config after a system update"

# the package database, which changes whenever packages are installed or updated
pkg_db() {
  local d
  for d in "$root/var/db/pkg/local.sqlite" "$root/usr/pkg/pkgdb" "$root/var/db/pkg"; do
    [ -e "$d" ] && { printf '%s\n' "$d"; return 0; }
  done
  return 1
}
# packages changed since the last check? (the package database is newer than the last check)
system_updated() {
  local db
  db="$(pkg_db)" || return 1
  [ -f "$state/last-run" ] || return 0
  [ -n "$(find "$db" -prune -newer "$state/last-run" 2>/dev/null)" ]
}

say() { if [ "$quiet" -eq 1 ]; then printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$log"; else printf '%s\n' "$*"; fi; }
# note [notify-send options] TITLE TEXT: a desktop notification; fails when none could be shown (no notification
# daemon, or cron without the session's D-Bus address - the login run saves it in $state/session)
note() {
  command -v notify-send >/dev/null 2>&1 || return 1
  if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -r "$state/session" ]; then
    DBUS_SESSION_BUS_ADDRESS="$(head -n1 "$state/session")"; export DBUS_SESSION_BUS_ADDRESS
  fi
  notify-send -a "i3wm-dots" "$@" 2>/dev/null
}

if [ "$(id -u)" -eq 0 ] && [ -z "$root" ]; then
  echo "run this as your normal user, not root" >&2
  exit 1
fi
mkdir -p "$state" "$(dirname "$log")"
if [ "$quiet" -eq 1 ] && [ -f "$log" ] && [ "$(wc -l <"$log")" -gt 1000 ]; then
  tail -n 500 "$log" >"$log.tmp" && mv "$log.tmp" "$log"          # keep the log small
fi

# where to get updates: the repo this desktop was installed from (written by install.sh). An ssh address is
# turned into https: the update runs in the background, where no ssh key password can be typed.
# The BSD version used to live with the Linux one (OmitGhostly/i3, before that OmitGhostly/i3wm-config): those
# addresses are switched to this repo (once).
repo_url() {
  local u
  u="$(head -n1 "$state/repo-url" 2>/dev/null)"
  case "$u" in git@github.com:*) u="https://github.com/${u#git@github.com:}" ;; esac
  case "$(printf '%s' "$u" | tr '[:upper:]' '[:lower:]')" in
    https://github.com/omitghostly/i3wm-config|https://github.com/omitghostly/i3wm-config.git|https://github.com/omitghostly/i3wm-config/ \
    |https://github.com/omitghostly/i3|https://github.com/omitghostly/i3.git|https://github.com/omitghostly/i3/)
      u="$default_url"
      printf '%s\n' "$u" >"$state/repo-url" 2>/dev/null || true ;;
  esac
  case "$u" in
    https://*|file://*|/*) ;;
    *) u="$default_url" ;;
  esac
  printf '%s\n' "$u"
}

# ------------------------------------------------------------------ the crontab line
install_cron() {
  command -v crontab >/dev/null 2>&1 || { echo "no crontab command: updates then only run when you type i3dots-update" >&2; return 1; }
  local cur
  cur="$(crontab -l 2>/dev/null | grep -vF "$cron_mark")"
  { [ -n "$cur" ] && printf '%s\n' "$cur"; printf '*/30 * * * * "%s" --cron >/dev/null 2>&1 %s\n' "$cfg/i3/scripts/Update.sh" "$cron_mark"; } | crontab - \
    || { echo "could not change your crontab" >&2; return 1; }
  echo "Done: every 30 minutes cron looks whether packages were installed or updated, and then checks GitHub for a newer desktop config."
}

remove_cron() {
  command -v crontab >/dev/null 2>&1 || return 0
  crontab -l 2>/dev/null | grep -qF "$cron_mark" || return 0
  local rest
  rest="$(crontab -l 2>/dev/null | grep -vF "$cron_mark")"
  if [ -n "$rest" ]; then printf '%s\n' "$rest" | crontab -; else crontab -r 2>/dev/null || printf '' | crontab -; fi
}

install_hook() { install_cron; }

remove_hook() {
  remove_cron
  echo "Your desktop config is no longer checked for updates (i3dots-update still works by hand)."
}

# ------------------------------------------------------------------ the update itself
fetch() {   # bring the private copy of the repo up to date; prints the newest commit
  local url
  url="$(repo_url)"
  command -v git >/dev/null 2>&1 || { say "git is not installed" >&2; return 1; }
  export GIT_TERMINAL_PROMPT=0
  if [ -d "$repo/.git" ] && [ "$(git -C "$repo" config --get remote.origin.url 2>/dev/null)" = "$url" ]; then
    timeout 120 git -C "$repo" fetch -q --depth 1 origin HEAD >/dev/null 2>&1 || { say "could not reach $url" >&2; return 1; }
  else
    rm -rf "$repo"
    timeout 300 git clone -q --depth 1 "$url" "$repo" >/dev/null 2>&1 || { rm -rf "$repo"; say "could not download $url" >&2; return 1; }
    git -C "$repo" fetch -q --depth 1 origin HEAD >/dev/null 2>&1 || true
  fi
  git -C "$repo" rev-parse FETCH_HEAD 2>/dev/null || git -C "$repo" rev-parse HEAD
}

reload_desktop() {
  command -v i3-msg >/dev/null 2>&1 || return 0
  # (from cron there is no display to find i3 by: its socket is in /tmp/i3-USER.*/ or $XDG_RUNTIME_DIR/i3/)
  if [ -z "${I3SOCK:-}" ] && [ -z "${DISPLAY:-}" ]; then
    I3SOCK="$(ls -t /tmp/i3-"$(id -un)".*/ipc-socket.* "${XDG_RUNTIME_DIR:-/nonexistent}"/i3/ipc-socket.* 2>/dev/null | head -n1)"
    [ -n "$I3SOCK" ] || return 0
    export I3SOCK
  fi
  i3-msg -q reload >/dev/null 2>&1 || true   # (also restarts the bar)
}

# A desktop that has just moved between the Linux and the BSD version of these dots (their installers hand over to
# each other): the version it got there is the one installed now
take_handoff() {
  [ -s "$state/handoff" ] || return 0
  mv -f "$state/handoff" "$state/applied" 2>/dev/null || true
}

update() {
  if [ ! -f "$cfg/i3/.i3wm-dots-installed" ]; then
    say "the i3 config in $cfg/i3 was not installed by i3wm-dots - nothing to update"
    return 0
  fi
  local new old subject
  take_handoff
  new="$(fetch)" || return 1
  old="$(cat "$state/applied" 2>/dev/null)"
  if [ -n "$new" ] && [ "$new" = "$old" ]; then
    say "already up to date (${new:0:7})"
    date +%s >"$state/last-run"
    rm -f "$state/available"
    return 0
  fi
  git -C "$repo" reset -q --hard "$new" || { say "could not use the downloaded version"; return 1; }
  [ -f "$repo/install.sh" ] && [ -f "$repo/config/i3/config" ] || { say "the download does not look like i3wm-dots"; return 1; }
  # keep the current version, for --undo
  rm -rf "$state/previous.tmp" && mkdir -p "$state/previous.tmp"
  local d name
  for d in "$repo"/config/*/; do
    name="$(basename "$d")"
    [ "$name" = gtk-3.0 ] && continue      # shared with other apps (GTK theme, bookmarks): updates only merge into it
    [ -e "$cfg/$name" ] && cp -a "$cfg/$name" "$state/previous.tmp/$name"
  done
  rm -rf "$state/previous" && mv "$state/previous.tmp" "$state/previous"
  subject="$(git -C "$repo" log -1 --format=%s 2>/dev/null)"
  say "updating to ${new:0:7}: $subject"
  say "(your Settings are kept; files you changed by hand in $cfg are replaced - i3dots-update --undo puts them back)"
  if ! bash "$repo/install.sh" --update >>"$log" 2>&1; then
    say "the update failed (see $log) - putting the previous version back"
    undo >/dev/null
    note "Desktop config update failed" "Your previous config was put back. Details: $log"
    return 1
  fi
  printf '%s\n' "$new" >"$state/applied"
  date +%s >"$state/last-run"
  rm -f "$state/available" "$state/notified"
  reload_desktop
  say "updated to ${new:0:7}"
  note -u low "Desktop config updated" "${subject:-new version} (${new:0:7}). Undo: i3dots-update --undo"
  return 0
}

# ------------------------------------------------------------------ after a system update: check and tell
# tell_available: the notification about the version in $state/available, unless it was shown already
tell_available() {
  local new subject
  new="$(cat "$state/available" 2>/dev/null)"
  [ -n "$new" ] || return 0
  [ "$new" = "$(cat "$state/applied" 2>/dev/null)" ] && { rm -f "$state/available"; return 0; }
  [ "$new" = "$(cat "$state/notified" 2>/dev/null)" ] && return 0
  subject="$(git -C "$repo" log -1 --format=%s "$new" 2>/dev/null)"
  if note -u normal -i software-update-available "Desktop config update available" \
      "${subject:-A new version} (${new:0:7}). To install it, run:  i3dots-update
Your Settings are kept; files you changed by hand in ~/.config are replaced (i3dots-update --undo puts them back)."; then
    printf '%s\n' "$new" >"$state/notified"
  else
    say "could not show the notification (no notification service?) - it is shown at your next login"
  fi
}

# check: is there a newer version than the one installed? Installs nothing - only says so
check() {
  if [ ! -f "$cfg/i3/.i3wm-dots-installed" ]; then
    say "the i3 config in $cfg/i3 was not installed by i3wm-dots - nothing to check"
    return 0
  fi
  local new
  take_handoff
  new="$(fetch)" || return 1
  date +%s >"$state/last-run"
  if [ -z "$new" ] || [ "$new" = "$(cat "$state/applied" 2>/dev/null)" ]; then
    say "already up to date (${new:0:7})"
    rm -f "$state/available"
    return 0
  fi
  printf '%s\n' "$new" >"$state/available"
  say "a newer version is available: ${new:0:7} $(git -C "$repo" log -1 --format=%s "$new" 2>/dev/null) (install it with: i3dots-update)"
  tell_available
}

# (the login run: the session's D-Bus address, so the cron check can show its notification)
remember_session() {
  [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] || return 0
  printf '%s\n' "$DBUS_SESSION_BUS_ADDRESS" >"$state/session.tmp" 2>/dev/null && mv -f "$state/session.tmp" "$state/session"
}

undo() {
  [ -d "$state/previous" ] || { echo "nothing to undo (no update has replaced your config yet)"; return 1; }
  local d name
  for d in "$state/previous"/*/; do
    name="$(basename "$d")"
    [ "$name" = gtk-3.0 ] && continue      # (older snapshots: never put back a stale copy of the shared GTK folder)
    rm -rf "${cfg:?}/$name" && cp -a "$d" "$cfg/$name"
  done
  rm -f "$state/applied"          # the next update installs the newest version again
  reload_desktop
  echo "put back the config from before the last update"
}

auto_on() { [ ! -f "$state/off" ]; }

# ------------------------------------------------------------------ commands
exec 9>"$state/lock"
case "$mode" in
  --install-hook) install_hook; exit $? ;;
  --remove-hook)  remove_hook; exit $? ;;
  --off)    : >"$state/off"; echo "no more checks for a newer version (i3dots-update still updates by hand)"; exit 0 ;;
  --on)     rm -f "$state/off"; echo "after packages change you get a notification when a newer version is out"; exit 0 ;;
  --status)
    take_handoff
    echo "checks for a newer version: $(auto_on && echo "on (a notification when one is out; installing is up to you)" || echo off)"
    echo "repo:              $(repo_url)"
    a="$(cat "$state/applied" 2>/dev/null)"; echo "installed version: ${a:0:7}${a:+ }$( [ -n "$a" ] && git -C "$repo" log -1 --format='(%cd) %s' --date=short "$a" 2>/dev/null)"
    n="$(cat "$state/available" 2>/dev/null)"
    [ -n "$n" ] && [ "$n" != "$a" ] && echo "newer version:     ${n:0:7} $(git -C "$repo" log -1 --format='(%cd) %s' --date=short "$n" 2>/dev/null) - install it with: i3dots-update"
    # (GNU date -d @SECONDS, BSD date -r SECONDS)
    t="$(cat "$state/last-run" 2>/dev/null)"
    [ -n "$t" ] && echo "last check:        $(date -d "@$t" '+%F %H:%M' 2>/dev/null || date -r "$t" '+%F %H:%M' 2>/dev/null)"
    if crontab -l 2>/dev/null | grep -qF "$cron_mark"; then echo "cron:              set up (looks every 30 minutes)"
    else echo "cron:              not set up (run: i3dots-update --install-hook)"; fi
    exit 0 ;;
  --check)
    flock -w 300 9 || exit 1
    take_handoff
    new="$(fetch)" || exit 1
    if [ "$new" = "$(cat "$state/applied" 2>/dev/null)" ]; then echo "up to date (${new:0:7})"
    else echo "a newer version is available: ${new:0:7} $(git -C "$repo" log -1 --format=%s FETCH_HEAD 2>/dev/null)"; fi
    exit 0 ;;
  --undo)   flock -w 300 9 || exit 1; undo; exit $? ;;
  --auto)
    # (check and tell right away - installing is up to you)
    auto_on || { say "checks for a newer version are off"; exit 0; }
    flock -n 9 || exit 0            # one is already running
    check; exit $? ;;
  --login)
    auto_on || exit 0
    remember_session
    # catch up on packages that changed while you were logged out; else a notification that could not
    # be shown before (no notification service at the time) comes now
    if system_updated; then todo=check
    elif [ -s "$state/available" ] && [ "$(cat "$state/available")" != "$(cat "$state/notified" 2>/dev/null)" ]; then todo=tell_available
    else exit 0; fi
    sleep "${I3DOTS_LOGIN_DELAY:-20}"  # let the network and the notification service come up first
    flock -n 9 || exit 0
    "$todo"; exit $? ;;
  --cron)
    # cron asks every 30 minutes; only changed packages (a newer package database) lead to a check
    auto_on || exit 0
    system_updated || exit 0
    flock -n 9 || exit 0
    check; exit $? ;;
  now|--now)
    flock -w 300 9 || { echo "another update is running"; exit 1; }
    update; exit $? ;;
  -h|--help) sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $mode (try --help)" >&2; exit 2 ;;
esac
