#!/usr/bin/env bash
# dunst as this session's notification daemon (i3 runs this at login).
# Other desktops installed next to i3 bring their own (Xfce, MATE, Cinnamon, LXQt, Budgie, KDE ...). D-Bus starts
# whichever it likes for the first notification, and that one then keeps the job for the whole session - with its
# own look, and without the history and the Do-Not-Disturb the keys here use. So: theirs is stopped (for this
# session only - their own desktops start them again), then dunst starts.
pgrep -u "$UID" -x dunst >/dev/null 2>&1 && exit 0
command -v dunst >/dev/null 2>&1 || exit 0
for d in xfce4-notifyd mate-notification-daemon notify-osd lxqt-notificationd notification-daemon \
         plasma_waitforname budgie-daemon-notifications deepin-notifications mako; do
  pkill -u "$UID" -f "(^|/)$d( |\$)" 2>/dev/null
done
exec dunst
