#!/bin/sh
# Platform.sh - the things that work differently on FreeBSD (and GhostBSD), OpenBSD and NetBSD, in one place.
# The scripts, the bar and the settings window ask this instead of calling a system's own tools themselves.
#
#   Platform.sh os                         freebsd | openbsd | netbsd | other
#   Platform.sh distro                     the system's name: FreeBSD, GhostBSD, OpenBSD, NetBSD ...
#   Platform.sh volume [get|muted|up N|down N|mute|unmute|toggle]      N in percent; get prints 0-100, muted yes|no
#   Platform.sh mic    [get|muted|up N|down N|toggle]
#   Platform.sh brightness [get|set N|up N|down N]
#   Platform.sh battery                    "PERCENT STATE" (charging | discharging | full); nothing: no battery
#   Platform.sh cpu | memory               percent in use
#   Platform.sh wifi                       "SSID<tab>SIGNAL" while connected (SIGNAL can be empty); nothing if not
#   Platform.sh has battery|backlight|wifi|volume     answers with the exit status
#   Platform.sh power suspend|hibernate|reboot|poweroff
#   Platform.sh airplane [state|toggle|on|off]   airplane mode (no Wi-Fi): prints on | off
#   Platform.sh bar ITEM                   an item's text for polybar (polybar's own modules for these read
#                                          Linux's /proc and /sys): network volume backlight battery cpu memory
#   Platform.sh plain ITEM...              the same without polybar's colour tags (for i3's own bar); several
#                                          items: one "ITEM<tab>TEXT" line each
#   Platform.sh nproc                      number of CPUs
#
# Volume: pamixer when a sound server answers it, else FreeBSD's mixer, OpenBSD's sndioctl, NetBSD's mixerctl.
# Brightness: FreeBSD's backlight, else xbacklight (screens that RandR can dim), OpenBSD's wsconsctl.
# Power: shutdown / zzz / acpiconf - as you, else through doas or sudo when a rule lets you run them without a
# password.

case "${I3DOTS_OS:-$(uname -s 2>/dev/null)}" in
  FreeBSD|freebsd|GhostBSD|ghostbsd) OS=freebsd ;;
  OpenBSD|openbsd) OS=openbsd ;;
  NetBSD|netbsd) OS=netbsd ;;
  *) OS=other ;;
esac

have() { command -v "$1" >/dev/null 2>&1; }
# a whole number from a decimal ("0.502" * 100 = 50), clamped to 0..100
pct_of() { awk -v v="$1" -v m="${2:-1}" 'BEGIN { p = v * 100 / m; if (p < 0) p = 0; if (p > 100) p = 100; printf "%d\n", p + 0.5 }'; }
first_number() { tr -c '0-9.\n' ' ' | awk '{ for (i = 1; i <= NF; i++) if ($i ~ /^[0-9]+(\.[0-9]+)?$/) { print $i; exit } }'; }
state_dir() {
  d="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
  [ -d "$d" ] && [ -w "$d" ] || d=/tmp
  printf '%s\n' "$d"
}

distro() {
  case "$OS" in
    freebsd)
      if have ghostbsd-version || grep -qi '^ID=.*ghostbsd' /etc/os-release /var/run/os-release 2>/dev/null; then
        echo GhostBSD
      else echo FreeBSD; fi ;;
    openbsd) echo OpenBSD ;;
    netbsd) echo NetBSD ;;
    *) uname -s 2>/dev/null || echo unknown ;;
  esac
}

# ------------------------------------------------------------------ privileges (power off, suspend)
# as you if the system allows it (FreeBSD and NetBSD: the "operator" group may shut down), else doas / sudo, but
# only when a rule lets you do it without typing a password - a key binding has nowhere to ask for one
as_root() {
  "$@" >/dev/null 2>&1 && return 0
  have doas && doas -n "$@" >/dev/null 2>&1 && return 0
  have sudo && sudo -n "$@" >/dev/null 2>&1 && return 0
  return 1
}

# ------------------------------------------------------------------ sound
vol_backend() {
  if have pamixer && pamixer --get-volume >/dev/null 2>&1; then echo pamixer; return; fi
  case "$OS" in
    freebsd) have mixer && mixer -o vol.volume >/dev/null 2>&1 && echo mixer ;;
    openbsd) have sndioctl && sndioctl -n output.level >/dev/null 2>&1 && echo sndio ;;
    netbsd)  have mixerctl && mixerctl -n outputs.master >/dev/null 2>&1 && echo mixerctl ;;
  esac
}

# sound KIND ACTION [N]   KIND: out | in (the microphone)
sound() {
  kind=$1; action=${2:-get}; n=${3:-5}
  case "$n" in ''|*[!0-9]*) n=5 ;; esac
  b=$(vol_backend)
  [ -n "$b" ] || return 1
  case "$b" in
    pamixer)
      src=""; [ "$kind" = in ] && src=--default-source
      case "$action" in
        get) pamixer $src --get-volume 2>/dev/null ;;
        muted) if [ "$(pamixer $src --get-mute 2>/dev/null)" = true ]; then echo yes; else echo no; fi ;;
        up) if [ "$kind" = out ]; then pamixer -i "$n" --allow-boost --set-limit 150; else pamixer $src -i "$n"; fi ;;
        down) pamixer $src -d "$n" ;;
        mute) pamixer $src -m ;;
        unmute) pamixer $src -u ;;
        toggle) pamixer $src -t ;;
      esac ;;
    mixer)          # FreeBSD: vol (the output) and mic, 0.00-1.00 per channel
      dev=vol
      if [ "$kind" = in ]; then
        dev=mic; mixer -o mic.volume >/dev/null 2>&1 || dev=rec
      fi
      case "$action" in
        get) pct_of "$(mixer -o "$dev.volume" 2>/dev/null | sed 's/.*=//; s/:.*//')" ;;
        muted) case "$(mixer -o "$dev.mute" 2>/dev/null)" in *=on) echo yes ;; *) echo no ;; esac ;;
        up) mixer "$dev.volume=+$n%" >/dev/null ;;
        down) mixer "$dev.volume=-$n%" >/dev/null ;;
        mute) mixer "$dev.mute=on" >/dev/null ;;
        unmute) mixer "$dev.mute=off" >/dev/null ;;
        toggle) mixer "$dev.mute=toggle" >/dev/null ;;
      esac ;;
    sndio)          # OpenBSD: output.* and input.*, 0.000-1.000
      c=output; [ "$kind" = in ] && c=input
      step=$(LC_ALL=C awk -v n="$n" 'BEGIN { printf "%.2f", n / 100 }')   # (a decimal point in any language)
      case "$action" in
        get) pct_of "$(sndioctl -n "$c.level" 2>/dev/null | head -n1)" ;;
        muted) if [ "$(sndioctl -n "$c.mute" 2>/dev/null | head -n1)" = 1 ]; then echo yes; else echo no; fi ;;
        up) sndioctl -q "$c.level=+$step" ;;
        down) sndioctl -q "$c.level=-$step" ;;
        mute) sndioctl -q "$c.mute=1" ;;
        unmute) sndioctl -q "$c.mute=0" ;;
        toggle) sndioctl -q "$c.mute=!" ;;
      esac ;;
    mixerctl)       # NetBSD: outputs.master / inputs.mic, 0-255 per channel
      ctl=outputs.master; [ "$kind" = in ] && ctl=inputs.mic
      cur=$(mixerctl -n "$ctl" 2>/dev/null)
      [ -n "$cur" ] || return 1
      left=${cur%%,*}
      case "$action" in
        get) pct_of "$left" 255 ;;
        muted) if [ "$(mixerctl -n "$ctl.mute" 2>/dev/null)" = on ]; then echo yes; else echo no; fi ;;
        up|down)
          new=$(awk -v l="$left" -v n="$n" -v d="$action" 'BEGIN { s = n * 255 / 100; v = (d == "up") ? l + s : l - s;
                if (v < 0) v = 0; if (v > 255) v = 255; printf "%d", v + 0.5 }')
          case "$cur" in *,*) new="$new,$new" ;; esac
          mixerctl -w "$ctl=$new" >/dev/null ;;
        mute) mixerctl -w "$ctl.mute=on" >/dev/null ;;
        unmute) mixerctl -w "$ctl.mute=off" >/dev/null ;;
        toggle) if [ "$(mixerctl -n "$ctl.mute" 2>/dev/null)" = on ]; then mixerctl -w "$ctl.mute=off" >/dev/null
                else mixerctl -w "$ctl.mute=on" >/dev/null; fi ;;
      esac ;;
  esac
}

# ------------------------------------------------------------------ screen brightness
xbl_ok() { have xbacklight && [ -n "$(xbacklight -get 2>/dev/null | first_number)" ]; }
bl_backend() {
  case "$OS" in
    freebsd) have backlight && [ -n "$(backlight -q 2>/dev/null | first_number)" ] && { echo backlight; return; } ;;
  esac
  xbl_ok && { echo xbacklight; return; }
  [ "$OS" = openbsd ] && have wsconsctl && [ -n "$(wsconsctl -n display.brightness 2>/dev/null | first_number)" ] && echo wsconsctl
}
bl_read() {   # (a function, not a case inside $(...): older ksh shells cannot parse that)
  case "$1" in
    backlight) backlight -q 2>/dev/null ;;
    xbacklight) xbacklight -get 2>/dev/null ;;
    wsconsctl) wsconsctl -n display.brightness 2>/dev/null ;;
  esac
}
brightness() {
  action=${1:-get}; n=${2:-10}
  case "$n" in ''|*[!0-9]*) n=10 ;; esac
  b=$(bl_backend)
  [ -n "$b" ] || return 1
  cur=$(bl_read "$b" | first_number)
  cur=$(pct_of "${cur:-0}" 100)
  case "$action" in
    get) echo "$cur"; return 0 ;;
    set) new=$n ;;
    up) new=$((cur + n)) ;;
    down) new=$((cur - n)) ;;
    *) return 2 ;;
  esac
  [ "$new" -lt 5 ] && new=5          # never all the way to black
  [ "$new" -gt 100 ] && new=100
  case "$b" in
    backlight) backlight "$new" ;;
    xbacklight) xbacklight -set "$new" ;;
    wsconsctl) as_root wsconsctl "display.brightness=$new" ;;
  esac
}

# ------------------------------------------------------------------ battery
battery() {
  case "$OS" in
    freebsd)
      units=$(sysctl -n hw.acpi.battery.units 2>/dev/null)
      case "$units" in ''|0|*[!0-9]*) return 1 ;; esac
      p=$(sysctl -n hw.acpi.battery.life 2>/dev/null); st=$(sysctl -n hw.acpi.battery.state 2>/dev/null)
      ac=$(sysctl -n hw.acpi.acline 2>/dev/null)
      case "$p" in ''|-*|*[!0-9]*) return 1 ;; esac
      st=${st:-0}; case "$st" in *[!0-9]*) st=0 ;; esac
      if [ $((st & 2)) -ne 0 ]; then s=charging
      elif [ $((st & 1)) -ne 0 ]; then s=discharging
      elif [ "$ac" = 1 ]; then s=full
      else s=discharging; fi
      echo "$p $s" ;;
    openbsd)
      bs=$(apm -b 2>/dev/null); p=$(apm -l 2>/dev/null); ac=$(apm -a 2>/dev/null)
      case "$bs" in ''|4|255) return 1 ;; esac
      case "$p" in ''|-*|*[!0-9]*) return 1 ;; esac
      [ "$p" -gt 100 ] && return 1
      if [ "$bs" = 3 ]; then s=charging; elif [ "$ac" = 1 ]; then s=full; else s=discharging; fi
      echo "$p $s" ;;
    netbsd)
      for dev in acpibat0 acpibat1; do
        out=$(envstat -d "$dev" 2>/dev/null) || continue
        p=$(printf '%s\n' "$out" | awk '/^[[:space:]]*charge:/ { if (match($0, /\([[:space:]]*[0-9.]+%\)/)) {
              v = substr($0, RSTART + 1, RLENGTH - 3); gsub(/[[:space:]]/, "", v); printf "%d\n", v + 0.5; exit } }')
        [ -n "$p" ] || continue
        if printf '%s\n' "$out" | grep -qE '^[[:space:]]*charging:[[:space:]]*TRUE'; then s=charging
        elif envstat -d acpiacad0 2>/dev/null | grep -qE '^[[:space:]]*connected:[[:space:]]*TRUE'; then s=full
        else s=discharging; fi
        echo "$p $s"; return 0
      done
      return 1 ;;
    *) return 1 ;;
  esac
}

# ------------------------------------------------------------------ cpu / memory
cpu_sample() {   # "TOTAL IDLE" since boot
  case "$OS" in
    # FreeBSD "user nice sys intr idle", OpenBSD "user,nice,sys,spin,intr,idle", NetBSD "user = 1, ..., idle = 5":
    # every number added up, the last one is the idle time
    *) sysctl -n kern.cp_time 2>/dev/null | tr -c '0-9\n' ' ' | awk '{ t = 0; for (i = 1; i <= NF; i++) t += $i; if (NF) print t, $NF }' ;;
  esac
}
cpu() {
  f="$(state_dir)/i3dots-cpu-$(id -u)${1:+-$1}"
  now=$(cpu_sample)
  [ -n "$now" ] || return 1
  prev=$(cat "$f" 2>/dev/null)
  if [ -z "$prev" ]; then prev=$now; sleep 0.4; now=$(cpu_sample); fi
  printf '%s\n' "$now" >"$f" 2>/dev/null
  printf '%s %s\n' "$prev" "$now" | awk '{ dt = $3 - $1; di = $4 - $2; if (dt <= 0) { print 0; exit }
    p = (dt - di) * 100 / dt; if (p < 0) p = 0; printf "%d\n", p + 0.5 }'
}
memory() {
  case "$OS" in
    freebsd)
      sysctl -n vm.stats.vm.v_page_count vm.stats.vm.v_active_count vm.stats.vm.v_wire_count 2>/dev/null |
        awk 'NR == 1 { t = $1 } NR == 2 { a = $1 } NR == 3 { w = $1 } END { if (t) printf "%d\n", (a + w) * 100 / t + 0.5 }' ;;
    openbsd|netbsd)
      vmstat -s 2>/dev/null | awk '/ pages managed$/ { t = $1 } / pages active$/ { a = $1 } / pages wired$/ { w = $1 }
        END { if (t) printf "%d\n", (a + w) * 100 / t + 0.5 }' ;;
    *) return 1 ;;
  esac
}

# ------------------------------------------------------------------ Wi-Fi
wifi_ifaces() {   # the wireless network interfaces
  for i in $(ifconfig -l 2>/dev/null || ifconfig -a 2>/dev/null | awk -F: '/^[a-z]/ { print $1 }'); do
    case "$OS" in
      openbsd) ifconfig "$i" 2>/dev/null | grep -q 'ieee80211:' && echo "$i" ;;
      *) ifconfig "$i" 2>/dev/null | grep -qE '^[[:space:]]+ssid ' && echo "$i" ;;
    esac
  done
}
wifi() {
  case "$OS" in
    freebsd|openbsd|netbsd)
      for i in $(wifi_ifaces); do
        out=$(ifconfig "$i" 2>/dev/null)
        printf '%s\n' "$out" | grep -qE 'status: (associated|active)' || continue
        # FreeBSD / NetBSD: "ssid NAME ...", OpenBSD: "ieee80211: join NAME ... 72%" (a name with spaces is quoted)
        printf '%s\n' "$out" | awk -v os="$OS" '
          { line = $0 }
          (os == "openbsd" && line ~ /ieee80211:/) || (os != "openbsd" && line ~ /^[[:space:]]+ssid /) {
            key = (os == "openbsd") ? "(join|nwid) " : "ssid "
            if (!match(line, key)) next
            rest = substr(line, RSTART + RLENGTH)
            if (substr(rest, 1, 1) == "\"") { rest = substr(rest, 2); name = substr(rest, 1, index(rest, "\"") - 1) }
            else { split(rest, w, " "); name = w[1] }
            sig = ""
            if (match(line, / [0-9]+%/)) sig = substr(line, RSTART + 1, RLENGTH - 2)
            printf "%s\t%s\n", name, sig; exit
          }'
        return 0
      done ;;
    *) return 1 ;;
  esac
}
has_wifi() {
  case "$OS" in
    freebsd) [ -n "$(sysctl -n net.wlan.devices 2>/dev/null | tr -d ' ')" ] || [ -n "$(wifi_ifaces)" ] ;;
    openbsd|netbsd) [ -n "$(wifi_ifaces)" ] ;;
    *) return 1 ;;
  esac
}

# airplane: Wi-Fi off / on - the wireless interface down / up (as root: a doas / sudo rule)
airplane() {
  ifs=$(wifi_ifaces)
  [ -n "$ifs" ] || return 1
  st=on
  for i in $ifs; do ifconfig "$i" 2>/dev/null | head -n1 | grep -q '[<,]UP[,>]' && st=off; done
  case "${1:-state}" in
    state) echo "$st"; return 0 ;;
    toggle) if [ "$st" = on ]; then want=off; else want=on; fi ;;
    on|off) want=$1 ;;
    *) return 2 ;;
  esac
  for i in $ifs; do if [ "$want" = on ]; then as_root ifconfig "$i" down; else as_root ifconfig "$i" up; fi || return 1; done
  echo "$want"
}

# ------------------------------------------------------------------ power
lock_first() {   # no logind here to lock the screen before sleeping: lock it first
  s="${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/LockScreen.sh"
  [ -x "$s" ] && { "$s" >/dev/null 2>&1 & sleep 1; }
}
power() {
  case "$OS:$1" in
    freebsd:suspend) lock_first; as_root zzz || as_root acpiconf -s 3 ;;
    freebsd:hibernate) lock_first; as_root acpiconf -s 4 ;;
    openbsd:suspend) lock_first; zzz >/dev/null 2>&1 || as_root zzz ;;
    openbsd:hibernate) lock_first; ZZZ >/dev/null 2>&1 || as_root ZZZ ;;
    netbsd:suspend) lock_first; as_root sysctl -w hw.acpi.sleep.state=3 ;;
    *:reboot) as_root shutdown -r now ;;
    *:poweroff) as_root shutdown -p now ;;
    *) return 1 ;;
  esac && return 0
  # could not: say how to allow it
  if have notify-send; then
    notify-send -u normal "Power" "Could not $1: allow it with a doas rule, e.g.
permit nopass :wheel cmd shutdown
(FreeBSD / NetBSD: or join the operator group)" 2>/dev/null
  fi
  return 1
}

# ------------------------------------------------------------------ text for the bar
# polybar: the Flat style shows the prefixes dimmed (like its built-in modules); the block styles colour the block
bar_text() {
  mode=$1; item=$2
  dim() {
    if [ "$mode" = bar ] && [ "${BAR_STYLE:-flat}" = flat ]; then printf '%%{F#6e6e6e}%s%%{F-}' "$1"; else printf '%s' "$1"; fi
  }
  flat=no; [ "$mode" = bar ] && [ "${BAR_STYLE:-flat}" = flat ] && flat=yes
  case "$item" in
    network|wifi)
      has_wifi || return 0
      w=$(wifi)
      if [ -z "$w" ]; then dim "󰖪"; echo; return 0; fi
      ssid=$(printf '%s' "$w" | cut -f1); sig=$(printf '%s' "$w" | cut -f2)
      icon="󰤨"
      case "$sig" in [0-9]*) if [ "$sig" -lt 25 ]; then icon="󰤯"; elif [ "$sig" -lt 50 ]; then icon="󰤟"
                             elif [ "$sig" -lt 75 ]; then icon="󰤢"; fi ;; esac
      printf '%s %s%s\n' "$icon" "$ssid" "${sig:+ $sig%}" ;;
    volume|pulseaudio)
      v=$(sound out get) || return 0
      [ -n "$v" ] || return 0
      if [ "$(sound out muted)" = yes ]; then dim "󰝟 muted"; echo; return 0; fi
      if [ "$v" -lt 34 ]; then icon="󰕿"; elif [ "$v" -lt 67 ]; then icon="󰖀"; else icon="󰕾"; fi
      printf '%s %s%%\n' "$icon" "$v" ;;
    backlight|brightness)
      v=$(brightness get) || return 0
      printf '󰃟 %s%%\n' "$v" ;;
    battery)
      b=$(battery) || return 0
      p=${b%% *}; s=${b#* }
      if [ "$s" = charging ]; then icon="󰂄"
      elif [ "$s" = full ] || [ "$p" -ge 99 ]; then icon="󰁹"
      elif [ "$p" -le 15 ]; then icon="󰂃"
      elif [ "$p" -lt 30 ]; then icon="󰁺"
      elif [ "$p" -lt 50 ]; then icon="󰁼"
      elif [ "$p" -lt 70 ]; then icon="󰁾"
      elif [ "$p" -lt 90 ]; then icon="󰂀"
      else icon="󰁹"; fi
      printf '%s %s%%\n' "$icon" "$p" ;;
    cpu)
      v=$(cpu "$mode") || return 0
      if [ "$flat" = yes ]; then dim "󰻠 CPU "; printf '%2d%%\n' "$v"; else printf '󰻠 %2d%%\n' "$v"; fi ;;
    memory)
      v=$(memory) || return 0
      [ -n "$v" ] || return 0
      if [ "$flat" = yes ]; then dim "󰍛 RAM "; printf '%2d%%\n' "$v"; else printf '󰍛 %2d%%\n' "$v"; fi ;;
    *) return 2 ;;
  esac
}

# ------------------------------------------------------------------ main
cmd=${1:-os}
[ $# -gt 0 ] && shift
case "$cmd" in
  os) echo "$OS" ;;
  distro) distro ;;
  volume) sound out "$@" ;;
  mic) sound in "$@" ;;
  brightness) brightness "$@" ;;
  battery) battery ;;
  cpu) cpu ;;
  memory) memory ;;
  wifi) wifi ;;
  nproc) getconf _NPROCESSORS_ONLN 2>/dev/null || getconf NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1 ;;
  has)
    case "${1:-}" in
      battery) battery >/dev/null ;;
      backlight) [ -n "$(bl_backend)" ] ;;
      wifi) has_wifi ;;
      volume) [ -n "$(vol_backend)" ] ;;
      *) exit 2 ;;
    esac || exit 1 ;;
  power) power "${1:-}" ;;
  airplane) airplane "${1:-state}" ;;
  bar|plain)
    if [ $# -le 1 ]; then bar_text "$cmd" "${1:-}"
    else                            # several items: "ITEM<tab>TEXT" lines (one call for i3's own bar)
      for it in "$@"; do t=$(bar_text "$cmd" "$it" 2>/dev/null); printf '%s\t%s\n' "$it" "$t"; done
    fi ;;
  *) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
esac
