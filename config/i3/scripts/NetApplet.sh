#!/usr/bin/env bash
# FreeBSD / GhostBSD: NetworkMgr's tray icon, which joins Wi-Fi networks (started once; i3 runs this).
#   NetApplet.sh           start it if it is not running
#   NetApplet.sh restart   restart it
# OpenBSD and NetBSD join networks with ifconfig / wpa_supplicant (Settings > Wi-Fi says how): nothing to start.
case "${1:-}" in restart|'') ;; *) echo "usage: $0 [restart]" >&2; exit 2 ;; esac
command -v networkmgr >/dev/null 2>&1 || exit 0
[ "${1:-}" = restart ] && { pkill -u "$UID" -f 'networkmgr' 2>/dev/null; sleep 0.5; }
pgrep -u "$UID" -f 'networkmgr' >/dev/null 2>&1 && exit 0
networkmgr >/dev/null 2>&1 </dev/null &
exit 0
