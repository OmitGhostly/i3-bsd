#!/usr/bin/env bash
cfg="${XDG_CONFIG_HOME:-$HOME/.config}/i3/rofi/config.rasi"
s="${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts"
# A short one-column list under every rofi theme: the grid themes would otherwise squeeze their
# columns of big cards into this narrow box (unreadable) and make it taller than a laptop screen,
# and the full-screen themes would spread six rows over the whole screen.
list='window {fullscreen: false;} mainbox {padding: 15px; spacing: 12px;} inputbar {margin: 0px;} listview {columns: 1; fixed-height: false; spacing: 4px;} element {orientation: horizontal; margin: 0px; padding: 8px 12px;} element-icon {size: 0px;} element-text {horizontal-align: 0.0; padding: 0px; margin: 0px;}'
choice=$(printf '  Lock\n  Logout\n  Suspend\n  Hibernate\n  Reboot\n  Shutdown' | rofi -dmenu -i -p "Power" -config "$cfg" -theme-str "$list window {width: 18em;} listview {lines: 6;}")
confirm() { [ "$(printf 'No\nYes' | rofi -dmenu -i -p "$1?" -config "$cfg" -theme-str "$list window {width: 14em;} listview {lines: 2;}")" = "Yes" ]; }
case "$choice" in
  *Lock)      "$s/LockScreen.sh" ;;
  *Logout)    confirm Logout    && i3-msg exit ;;
  # (Platform.sh: shutdown / zzz / acpiconf)
  *Suspend)   "$s/Platform.sh" power suspend ;;
  *Hibernate) confirm Hibernate && "$s/Platform.sh" power hibernate ;;
  *Reboot)    confirm Reboot    && "$s/Platform.sh" power reboot ;;
  *Shutdown)  confirm Shutdown  && "$s/Platform.sh" power poweroff ;;
esac
