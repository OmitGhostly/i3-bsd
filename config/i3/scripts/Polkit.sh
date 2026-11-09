#!/usr/bin/env bash
# the polkit agent that asks for your password when a program needs root (FreeBSD, GhostBSD: polkit-gnome or
# mate-polkit; NetBSD from pkgsrc)
pgrep -u "$UID" -f 'polkit-gnome-authentication-agent-1|polkit-kde-authentication-agent-1|polkit-mate-authentication-agent-1|lxpolkit|xfce-polkit' >/dev/null && exit 0
for p in /usr/local/libexec/polkit-gnome-authentication-agent-1 /usr/local/lib/polkit-gnome/polkit-gnome-authentication-agent-1 \
  /usr/local/libexec/polkit-mate-authentication-agent-1 /usr/local/lib/mate-polkit/polkit-mate-authentication-agent-1 \
  /usr/local/bin/lxpolkit /usr/local/libexec/xfce-polkit /usr/local/libexec/polkit-kde-authentication-agent-1 \
  /usr/pkg/libexec/polkit-gnome-authentication-agent-1 /usr/pkg/libexec/polkit-mate-authentication-agent-1; do
  [ -x "$p" ] && { "$p" & exit 0; }
done
# (OpenBSD and NetBSD do without polkit: nothing to say there)
case "${I3DOTS_OS:-$(uname -s)}" in FreeBSD) notify-send "Polkit" "No polkit agent found (install mate-polkit or polkit-gnome)" ;; esac
