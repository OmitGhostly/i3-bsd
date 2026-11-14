#!/usr/bin/env bash
# =============================================================================
#  i3wm-dots uninstaller (FreeBSD, GhostBSD, OpenBSD, NetBSD) - takes this desktop off again: the config, and if
#  you want, i3 itself and the programs the installer added. Your own files and the programs you already had are
#  left alone.
#
#  Usage:  ./uninstall.sh [options]          (also installed as:  i3dots-uninstall)
#    (default)        remove the config (and put your old configs back), then ask about i3 and the programs
#    --yes            no questions: the config, i3 itself and the programs the installer added
#    --config-only    only the config - keep i3 and every program
#    --all-programs   also offer the setup's programs that were already there before the installer ran
#                     (only ones nothing else needs; core packages - git, python, GTK, Xorg... - are always kept)
#    --no-restore     do not put your old configs (*.bak-*) back, leave them where they are
#    --force          remove i3 even if it is the only desktop on this computer
#    --dry-run        only show what would happen
#    -h, --help       this help
#
#  What it removes
#    config     ~/.config/{i3,polybar,picom,dunst,kitty,ghostty,fastfetch,cava,touchegg,swappy} (the copies the
#               installer made - your originals come back from *.bak-*), the dark style it merged into
#               ~/.config/gtk-3.0 (your theme and bookmarks stay), the greeting / prompt / asciiquarium lines in
#               ~/.bashrc and ~/.zshrc, the cursor files the Settings window wrote, the update checks (the line in
#               your crontab), pokescript, saved state and caches, and the wallpapers and font it copied
#    programs   i3 itself, and the packages the installer installed (it keeps a list since this version; for an older
#               install use --all-programs). A package that something else still needs is kept.
# =============================================================================
# shellcheck disable=SC2088   # (the ~ in the messages is text for you to read, not a path)
set -uo pipefail

do_restore=1; dry=0; mode=ask; force=0; all_programs=0
say()  { printf '\033[1;35m::\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
for arg in "$@"; do
  case "$arg" in
    --yes|-y)       mode=all ;;
    --config-only)  mode=config ;;
    --all-programs) all_programs=1 ;;
    --no-restore)   do_restore=0 ;;
    --force)        force=1 ;;
    --dry-run)      dry=1 ;;
    -h|--help)      sed -n '3,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $arg (try --help)" ;;
  esac
done
[ "$(id -u)" -eq 0 ] && [ "${I3DOTS_ALLOW_ROOT:-0}" != 1 ] && die "run this as your normal user, not with sudo (it asks for your password only to remove programs)"

# Run from a copy: this file may sit inside a folder that is about to be removed.
if [ -z "${I3DOTS_UNINSTALL_COPY:-}" ]; then
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo /)"
  tmp="$(mktemp "${TMPDIR:-/tmp}/i3dots-uninstall.XXXXXX")" || die "could not make a temporary copy of the uninstaller"
  cp "${BASH_SOURCE[0]}" "$tmp" && chmod 700 "$tmp"
  I3DOTS_UNINSTALL_COPY="$tmp" I3DOTS_UNINSTALL_HERE="$here" exec bash "$tmp" "$@"
fi
here="${I3DOTS_UNINSTALL_HERE:-/}"
trap 'rm -f "$I3DOTS_UNINSTALL_COPY"' EXIT

cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
state="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots"
cache="${XDG_CACHE_HOME:-$HOME/.cache}"
manifest="$state/installed"
# programs are removed as root: through sudo, else doas (with a rule in doas.conf), else su (asks for root's password)
as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  elif command -v doas >/dev/null 2>&1 && { [ -f /etc/doas.conf ] || [ -f /usr/local/etc/doas.conf ] || [ -f /usr/pkg/etc/doas.conf ]; }; then doas "$@"
  else su root -c "$(printf '%q ' "$@")"; fi
}
SUDO=as_root; [ "$(id -u)" -eq 0 ] && SUDO=""
removed=(); kept=()

run() { if [ "$dry" -eq 1 ]; then printf '   + %s\n' "$*"; return 0; fi; "$@"; }
gone() { removed+=("$1"); }
ask() {   # ask "question" default(y|n) -> 0 for yes
  local def="$2" a=""
  if [ "$mode" = all ]; then return 0; fi
  if [ ! -t 0 ] && [ ! -r /dev/tty ]; then [ "$def" = y ]; return; fi
  printf '\033[1;36m??\033[0m %s %s ' "$1" "$([ "$def" = y ] && echo '[Y/n]' || echo '[y/N]')"
  read -r a </dev/tty 2>/dev/null || a=""
  case "${a:-$def}" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

detect_family() {
  case "${I3DOTS_OS:-$(uname -s)}" in
    FreeBSD) echo freebsd ;;
    OpenBSD) echo openbsd ;;
    NetBSD)  echo netbsd ;;
    *)       echo unknown ;;
  esac
}
FAMILY="$(detect_family)"
if [ "${I3DOTS_OS:-$(uname -s)}" = Linux ]; then
  die "This uninstaller is made for FreeBSD, GhostBSD, OpenBSD and NetBSD - it does not run on Linux."
fi

# =============================================================================
#  1. what is there
# =============================================================================
ours=()
for d in "$cfg"/*/; do
  d="${d%/}"
  [ -f "$d/.i3wm-dots-installed" ] && [ ! -L "$d" ] && ours+=("$d")
done
in_i3=0
{ [ -n "${I3SOCK:-}" ] || [ "${XDG_CURRENT_DESKTOP:-}" = i3 ] || [ "${DESKTOP_SESSION:-}" = i3 ]; } && in_i3=1

if [ "${#ours[@]}" -eq 0 ] && [ ! -f "$manifest" ] && [ ! -d "$data/i3wm-dots-updater" ] \
   && ! compgen -G "$cfg/.i3dots-removing-*" >/dev/null; then
  say "the i3wm-dots config is not installed for $(id -un) (nothing in $cfg carries its mark)"
fi
say "this removes the i3wm-dots desktop config$( [ "$mode" = config ] && echo '' || echo ', and if you say so, i3 and the programs the installer added')"
[ "$in_i3" -eq 1 ] && warn "you are in an i3 session right now - it keeps running until you log out; then pick your other desktop at the login screen"

do_config=1
if [ "$mode" = ask ] && [ "$dry" -eq 0 ]; then
  ask "Remove the i3wm-dots config$( [ "$do_restore" -eq 1 ] && echo ' and put your old configs back')?" y || do_config=0
fi

# =============================================================================
#  2. the config
# =============================================================================
remove_rc_lines() {   # take the installer's lines (marker + the line after it) out of ~/.bashrc and ~/.zshrc
  local rc real
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [ -f "$rc" ] || continue
    grep -qE '^(# i3wm-dots: (pokemon fastfetch|see-through asciiquarium|black / grey / white prompt)|#i3wm-dots-off# )' "$rc" || continue
    if [ "$dry" -eq 1 ]; then echo "   + remove the i3wm-dots lines from $rc"; continue; fi
    # (written into the real file through a copy that keeps its permissions: a ~/.zshrc linked from a dotfiles
    #  folder stays a link)
    real="$(readlink -f -- "$rc" 2>/dev/null)"; [ -n "$real" ] || real="$rc"
    cp -p -- "$real" "$real.i3tmp" || continue
    awk 'skip { skip = 0; next }
         /^# i3wm-dots: (pokemon fastfetch|see-through asciiquarium|black \/ grey \/ white prompt)/ { skip = 1; if (blank) blank = 0; next }
         index($0, "#i3wm-dots-off# ") == 1 { $0 = substr($0, 17) }   # (a greeting of yours the installer turned off)
         { if (blank) print ""; blank = 0 }
         /^$/ { blank = 1; next }
         { print }
         END { if (blank) print "" }' "$real" >"$real.i3tmp" && mv -f -- "$real.i3tmp" "$real"
    gone "the greeting, prompt and asciiquarium lines in ~/${rc##*/}"
    # a file the installer created that now holds nothing of yours
    if grep -qxF "rc $rc" "$manifest" 2>/dev/null && ! grep -qvE '^[[:space:]]*$|^# ~/\.(bash|zsh)rc - created by the i3wm-dots installer$' "$rc"; then
      rm -f "$rc"; gone "~/${rc##*/} (the installer had created it)"
    fi
  done
}

remove_block() {   # remove_block FILE START-LINE END-LINE: the block Settings wrote (between its marks)
  local f="$1"
  [ -f "$f" ] && grep -qF "$2" "$f" || return 0
  if [ "$dry" -eq 1 ]; then echo "   + remove the i3wm-dots block from $f"; return 0; fi
  awk -v s="$2" -v e="$3" 'index($0, s) == 1 { skip = 1; next } skip && index($0, e) == 1 { skip = 0; next } !skip { print }' \
    "$f" >"$f.i3tmp" && mv -f "$f.i3tmp" "$f"
  grep -q '[^[:space:]]' "$f" || rm -f "$f"           # nothing else was in it
  gone "the Settings block (${2#* >>> i3wm-dots }) in ~/${f##*/}"
}

# the default program for folders the installer set (~/.config/mimeapps.list): back to what it was before - only
# while it is still the installer's (a default you picked since then stays)
restore_mime_defaults() {
  local f="$cfg/mimeapps.list" real kind type prev seen=" " cur changed=0
  [ -f "$manifest" ] && [ -f "$f" ] || return 0
  real="$(readlink -f -- "$f" 2>/dev/null)"; [ -n "$real" ] || real="$f"
  while read -r kind type prev; do
    [ "$kind" = mime ] && [ -n "$type" ] || continue
    case "$seen" in *" $type "*) continue ;; esac           # (the first record is what was there originally)
    seen="$seen$type "
    cur="$(awk -v t="$type" '/^\[/ { s = ($0 == "[Default Applications]") }
                            s && index($0, t "=") == 1 { print substr($0, length(t) + 2); exit }' "$real")"
    case "$cur" in i3wm-dots-folders.desktop*) ;; *) continue ;; esac
    [ "$prev" = - ] && prev=""
    if [ "$dry" -eq 1 ]; then echo "   + $type in ~/.config/mimeapps.list: ${prev:-(the system default)}"; continue; fi
    cp -p -- "$real" "$real.i3tmp" || continue
    awk -v t="$type" -v p="$prev" '/^\[/ { s = ($0 == "[Default Applications]") }
         s && index($0, t "=") == 1 { if (p != "") print t "=" p; next } { print }' "$real" >"$real.i3tmp" \
      && mv -f -- "$real.i3tmp" "$real" && changed=1
    gone "the default for folders (${prev:-the system default} again)"
  done <"$manifest"
  # it held nothing but our line: the file goes (the installer made it)
  if [ "$changed" -eq 1 ] && ! grep -qvE '^[[:space:]]*$|^\[Default Applications\]$' "$real" 2>/dev/null; then
    [ -L "$f" ] || rm -f "$f"
  fi
  return 0
}

remove_ini_key_if() {   # remove_ini_key_if FILE KEY VALUE: only when it still has the value the installer set
  local f="$1"
  [ -f "$f" ] || return 0
  grep -qE "^[[:space:]]*$2[[:space:]]*=[[:space:]]*$3[[:space:]]*\$" "$f" || return 0
  # (written through a temporary file: GNU sed -i and BSD sed -i differ)
  [ "$dry" -eq 1 ] && { printf '   + remove "%s=%s" from %s\n' "$2" "$3" "$f"; return 0; }
  sed -E "/^[[:space:]]*$2[[:space:]]*=[[:space:]]*$3[[:space:]]*\$/d" "$f" >"$f.i3tmp" && cat "$f.i3tmp" >"$f"
  rm -f "$f.i3tmp"
}

config_step() {
  local d name latest rest
  # the update checks first: the line in your crontab
  if command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -qF '# i3wm-dots: update the desktop config'; then
    if [ "$dry" -eq 1 ]; then echo "   + remove the i3wm-dots line from your crontab"
    else
      rest="$(crontab -l 2>/dev/null | grep -vF '# i3wm-dots: update the desktop config')"
      if [ -n "$rest" ]; then printf '%s\n' "$rest" | crontab -; else crontab -r 2>/dev/null || printf '' | crontab -; fi
    fi
    gone "the crontab line for the update checks"
  fi
  # the wallpaper slideshow (Settings > Wallpaper), if it runs
  [ "$dry" -eq 0 ] && [ -x "$cfg/i3/scripts/WallCycle.sh" ] && bash "$cfg/i3/scripts/WallCycle.sh" --stop >/dev/null 2>&1

  # the config folders the installer made; your originals come back from the newest *.bak-*.
  # Ours is first moved aside as .i3dots-removing-NAME, then your backup goes in its place, then the aside copy is
  # deleted: an uninstall stopped anywhere in between (Ctrl+C) leaves that folder, and the next run finishes the job.
  put_back() {   # put_back NAME: your newest backup of ~/.config/NAME back in place (when there is one, and wanted)
    local latest
    latest="$(find "$cfg" -maxdepth 1 -name "$1.bak-*" ! -name '*.part' 2>/dev/null | sort | tail -n1)"
    if [ "$do_restore" -eq 1 ] && [ -n "$latest" ] && [ ! -e "$cfg/$1" ]; then
      run mv "$latest" "$cfg/$1"; gone "~/.config/$1 (your own one from ${latest##*/} is back)"
    else
      gone "~/.config/$1"
    fi
  }
  for d in "$cfg"/.i3dots-removing-*; do        # (an uninstall that was stopped halfway)
    [ -d "$d" ] || continue
    name="${d##*/.i3dots-removing-}"
    [ -e "$cfg/$name" ] || put_back "$name"
    run rm -rf "$d"
  done
  for d in "${ours[@]}"; do
    name="${d##*/}"
    [ "$name" = gtk-3.0 ] && continue
    run rm -rf "$cfg/.i3dots-removing-$name"
    run mv "$d" "$cfg/.i3dots-removing-$name"
    put_back "$name"
    run rm -rf "$cfg/.i3dots-removing-$name"
  done

  # ~/.config/gtk-3.0 is shared: put the old settings.ini back (or take out the two settings the installer added),
  # keep your bookmarks and everything else
  if [ -f "$cfg/gtk-3.0/.i3wm-dots-installed" ]; then
    latest="$(find "$cfg" -maxdepth 1 -name 'gtk-3.0.bak-*' ! -name '*.part' 2>/dev/null | sort | tail -n1)"
    if [ "$do_restore" -eq 1 ] && [ -n "$latest" ] && [ -f "$latest/settings.ini" ]; then
      run cp -f "$latest/settings.ini" "$cfg/gtk-3.0/settings.ini"
      run rm -rf "$latest"
      gone "the dark style in ~/.config/gtk-3.0 (your old settings.ini is back, bookmarks kept)"
    else
      remove_ini_key_if "$cfg/gtk-3.0/settings.ini" gtk-application-prefer-dark-theme 1
      remove_ini_key_if "$cfg/gtk-3.0/settings.ini" gtk-font-name 'Sans 10'
      # the cursor the Settings window set there (Capitaine is removed with the config); a file with nothing else
      # left in it but a cursor size was the installer's own
      remove_ini_key_if "$cfg/gtk-3.0/settings.ini" gtk-cursor-theme-name capitaine-cursors
      if [ -f "$cfg/gtk-3.0/settings.ini" ] \
         && ! grep -qvE '^[[:space:]]*$|^\[Settings\]$|^gtk-cursor-theme-size=' "$cfg/gtk-3.0/settings.ini"; then
        run rm -f "$cfg/gtk-3.0/settings.ini"
      fi
      gone "the dark style in ~/.config/gtk-3.0 (bookmarks kept)"
    fi
    run rm -f "$cfg/gtk-3.0/.i3wm-dots-installed"
    # nothing left in it but the [Settings] heading (the installer had made it): remove it, and the folder if empty
    if [ -f "$cfg/gtk-3.0/settings.ini" ] && ! grep -qvE '^[[:space:]]*$|^\[Settings\]$' "$cfg/gtk-3.0/settings.ini"; then
      run rm -f "$cfg/gtk-3.0/settings.ini"
    fi
    [ -d "$cfg/gtk-3.0" ] && run rmdir "$cfg/gtk-3.0" 2>/dev/null
  fi

  remove_rc_lines

  # what the Settings window wrote for the mouse cursor (only files that are clearly its own)
  local f
  for f in "$HOME/.icons/default/index.theme" "$data/icons/default/index.theme"; do
    [ -f "$f" ] && grep -qx 'Comment=Default cursor theme' "$f" && grep -qx 'Name=Default' "$f" \
      && [ "$(grep -c . "$f")" -le 4 ] && { run rm -f "$f"; run rmdir "${f%/*}" 2>/dev/null; gone "${f/#$HOME/\~}"; }
  done
  f="$cfg/xsettingsd/xsettingsd.conf"
  [ -f "$f" ] && head -n1 "$f" | grep -q 'written by the i3 settings window' && { run rm -f "$f"; run rmdir "$cfg/xsettingsd" 2>/dev/null; gone "~/.config/xsettingsd/xsettingsd.conf"; }
  f="$cfg/environment.d/90-i3dots-cursor.conf"
  [ -f "$f" ] && { run rm -f "$f"; gone "~/.config/environment.d/90-i3dots-cursor.conf"; }
  # GTK 4: a settings.ini that holds nothing but the cursor the Settings window set
  f="$cfg/gtk-4.0/settings.ini"
  if [ -f "$f" ] && ! grep -qvE '^[[:space:]]*$|^\[Settings\]$|^gtk-cursor-theme-(name|size)=' "$f"; then
    run rm -f "$f"; gone "~/.config/gtk-4.0/settings.ini (only the cursor was in it)"
  fi
  remove_block "$HOME/.xprofile" "# >>> i3wm-dots cursor" "# <<< i3wm-dots cursor <<<"
  remove_block "$HOME/.Xresources" "! >>> i3wm-dots cursor" "! <<< i3wm-dots cursor <<<"
  # the proxy the Settings window set (Network > Proxy): its lines, and GNOME's proxy setting only when it set one
  if [ -f "$HOME/.xprofile" ] && grep -q '^# >>> i3wm-dots proxy' "$HOME/.xprofile" 2>/dev/null; then
    # (only in a desktop session: without its D-Bus, gsettings would just leave a stray cache file)
    [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] && command -v gsettings >/dev/null 2>&1 \
      && gsettings list-schemas 2>/dev/null | grep -qx 'org.gnome.system.proxy' \
      && run gsettings set org.gnome.system.proxy mode none
    remove_block "$HOME/.xprofile" "# >>> i3wm-dots proxy" "# <<< i3wm-dots proxy <<<"
  fi
  f="$cfg/environment.d/90-i3dots-proxy.conf"
  [ -f "$f" ] && { run rm -f "$f"; gone "~/.config/environment.d/90-i3dots-proxy.conf"; }

  restore_mime_defaults
  # files the installer recorded (wallpapers and the font it copied, a kitty from kitty's own installer...)
  local kind path
  if [ -f "$manifest" ]; then
    while read -r kind path; do
      [ "$kind" = path ] && [ -n "$path" ] || continue
      case "$path" in "$HOME"/*) ;; *) continue ;; esac          # only ever inside your home folder
      [ -e "$path" ] || [ -L "$path" ] || continue
      run rm -rf "$path"; gone "${path/#$HOME/\~}"
    done <"$manifest"
  elif [ -d "$here/wallpapers" ]; then
    # an older install has no list: the bundled wallpapers go only where they are still exactly the same file
    for f in "$here"/wallpapers/*; do
      [ -f "$f" ] && cmp -s "$f" "$HOME/Pictures/wallpapers/${f##*/}" && { run rm -f "$HOME/Pictures/wallpapers/${f##*/}"; gone "~/Pictures/wallpapers/${f##*/}"; }
    done
  fi

  # downloads, saved state and caches
  for d in "$data/i3wm-dots-updater" "$data/i3wm-dots" "$data/pokescript" "$cache/i3" \
           "$cache/i3wm-dots-install.log" "$cache/i3wm-dots-update.log" "$HOME/.local/bin/i3dots-update"; do
    [ -e "$d" ] || [ -L "$d" ] || continue
    run rm -rf "$d"; gone "${d/#$HOME/\~}"
  done
  [ -f "$cache/i3dots-bar-restart-$(id -u)" ] && run rm -f "$cache/i3dots-bar-restart-$(id -u)"   # (polybar/launch.sh)
  # the cursor theme half-unpacked by an install that was stopped (Ctrl+C) before it could clean up
  for d in "$data"/icons/.i3dots-cursor.??????; do
    [ -d "$d" ] && { run rm -rf "$d"; gone "${d/#$HOME/\~}"; }
  done

  # folders that are left empty now (rmdir only ever removes an empty one)
  for d in "$HOME/Pictures/wallpapers" "$HOME/Pictures/Screenshots" "$HOME/.icons" "$data/icons" "$data/applications" "$cfg/gtk-4.0" \
           "$cfg/environment.d" "$cfg/xsettingsd"; do
    [ -d "$d" ] && run rmdir "$d" 2>/dev/null
  done
  return 0
}

[ "$do_config" -eq 1 ] && { say "removing the config"; config_step; }

# =============================================================================
#  3. i3 itself and the programs
# =============================================================================
# never removed: other programs and desktops need them
PROTECTED=" git curl unzip python3 python gtk3 gtk+3 gtk3+ fontconfig xdg-utils xorg xset xrdb xsetroot xrandr xprop
 xdpyinfo setxkbmap xinput sound-theme-freedesktop freedesktop-sound-theme libnotify adwaita-icon-theme noto-emoji
 noto-emoji-ttf dbus bash pkg_alternatives mesa-demos xbacklight networkmgr polkit-gnome mate-polkit sudo doas "
PROTECTED=" ${PROTECTED//$'\n'/ } "           # (one line, so every name has a space on both sides)

i3_pkgs() { case "$FAMILY" in freebsd|openbsd|netbsd) echo i3 ;; esac; }
installed() {
  case "$FAMILY" in
    freebsd) pkg info -e "$1" 2>/dev/null ;;
    openbsd) pkg_info -q -e "${1%%%*}-*" >/dev/null 2>&1 ;;
    netbsd)  pkg_info -q -e "$1" >/dev/null 2>&1 ;;
    *)      return 1 ;;
  esac
}
other_desktops() {   # the login sessions that are not i3
  local f n=0 w
  # (OpenBSD and NetBSD come with window managers of their own - fvwm, cwm, ctwm, twm - to log in to)
  if [ -z "${I3DOTS_TEST_ROOT:-}" ]; then
    for w in fvwm cwm ctwm twm; do command -v "$w" >/dev/null 2>&1 && n=$((n + 1)); done
  fi
  for f in "${I3DOTS_TEST_ROOT:-}"/usr/local/share/xsessions/*.desktop "${I3DOTS_TEST_ROOT:-}"/usr/pkg/share/xsessions/*.desktop \
           "${I3DOTS_TEST_ROOT:-}"/usr/share/xsessions/*.desktop; do
    [ -e "$f" ] || continue
    case "${f##*/}" in i3.desktop|i3-with-shmlog.desktop|i3wm.desktop) continue ;; esac
    n=$((n + 1))
  done
  echo "$n"
}

# which packages are ours to remove
candidates=()
add_candidate() {
  local p="$1" c
  [ -n "$p" ] || return 0
  case "$PROTECTED" in *" $p "*) kept+=("$p (other programs need it)"); return 0 ;; esac
  # (any Python and its GTK bindings: FreeBSD py311-pygobject, NetBSD python314 / py314-cairo, OpenBSD python%3, ...)
  case "$p" in python3*|python%3|py3[0-9]*-*|py3-*) kept+=("$p (other programs need it)"); return 0 ;; esac
  for c in "${candidates[@]}"; do [ "$c" = "$p" ] && return 0; done
  installed "$p" && candidates+=("$p")
}
if [ -f "$manifest" ]; then
  while read -r kind value; do [ "$kind" = pkg ] && add_candidate "$value"; done <"$manifest"
fi
if [ "$all_programs" -eq 1 ]; then
  # the installer's own package list (from install.sh next to this file, or the copy the updater keeps)
  for src in "$here/install.sh" "$data/i3wm-dots-updater/repo/install.sh"; do
    [ -f "$src" ] || continue
    eval "$(sed -n '/^packages_for() {/,/^}/p' "$src")"
    # shellcheck disable=SC2046
    for item in $(packages_for 2>/dev/null); do
      IFS='|' read -ra alts <<<"$item"
      for a in "${alts[@]}"; do
        add_candidate "$a"
      done
    done
    break
  done
fi

# keep only what nothing else needs, so removing a program never takes other software with it
removable=(); needed=()
safe_set() {
  local -a S=("$@") next
  local p stable
  case "$FAMILY" in
    openbsd|netbsd) ;;   # pkg_delete refuses to break anything itself (see remove_pkgs)
    freebsd)
      # pkg delete would take everything that needs these with it: keep the ones another installed package needs
      # (again until nothing changes: keeping one can make another one needed)
      for _ in 1 2 3 4 5 6 7 8 9 10; do
        next=(); stable=1
        for p in "${S[@]}"; do
          if pkg query '%rn' "$p" 2>/dev/null | grep -qvxF -f <(printf '%s\n' "${S[@]}"); then needed+=("$p"); stable=0
          else next+=("$p"); fi
        done
        S=("${next[@]}")
        [ "$stable" -eq 1 ] && break
      done ;;
  esac
  removable=("${S[@]}")
}

remove_pkgs() {
  local p failed=()
  case "$FAMILY" in
    freebsd) run $SUDO pkg delete -y "$@" || failed=("$@") ;;
    openbsd|netbsd)
      # pkg_delete refuses a package something else needs: one by one, twice (one needed only by another on the list
      # goes in the second round)
      if ! run $SUDO pkg_delete "$@" >/dev/null 2>&1; then
        local left=("$@") again
        for _ in 1 2; do
          again=()
          for p in "${left[@]}"; do installed "$p" || continue; run $SUDO pkg_delete "$p" >/dev/null 2>&1 || again+=("$p"); done
          left=("${again[@]}")
        done
        failed=("${left[@]}")
      fi ;;
  esac
  for p in "${failed[@]}"; do needed+=("$p"); done
  for p in "$@"; do
    printf '%s\n' "${failed[@]}" | grep -qxF "$p" || gone "$p"
  done
}

programs_step() {
  local p want_i3=() list=()
  for p in $(i3_pkgs); do installed "$p" && want_i3+=("$p"); done
  if [ "${#want_i3[@]}" -gt 0 ] && [ "$(other_desktops)" -eq 0 ] && [ "$force" -eq 0 ]; then
    warn "i3 is the only desktop on this computer - removing it would leave you nothing to log in to."
    warn "  i3 stays. Install another desktop first, or run again with --force."
    kept+=("${want_i3[@]/%/ (your only desktop)}"); want_i3=()
  fi
  for p in "${want_i3[@]}"; do add_candidate "$p"; done
  for p in "${candidates[@]}"; do
    case " $(i3_pkgs) " in *" $p "*) printf '%s\n' "${want_i3[@]}" | grep -qxF "$p" || continue ;; esac   # (i3 kept above)
    list+=("$p")
  done
  if [ ! -f "$manifest" ] && [ "$all_programs" -eq 0 ]; then
    say "this install is older than the list of programs the installer keeps - only i3 itself is offered."
    say "  to also go through the setup's other programs:  ./uninstall.sh --all-programs"
  fi
  [ "${#list[@]}" -gt 0 ] || return 0
  [ "$FAMILY" = unknown ] && { warn "unknown package manager - remove these yourself: ${list[*]}"; return 0; }
  say "programs to remove: ${list[*]}"
  say "  (any of them that other software still needs is kept - that is checked next, with your password)"
  ask "Remove these programs?" n || { kept+=("${list[@]}"); return 0; }
  safe_set "${list[@]}"
  [ "${#removable[@]}" -gt 0 ] && remove_pkgs "${removable[@]}"
  if [ "${#needed[@]}" -gt 0 ]; then
    say "kept, because other software needs them: ${needed[*]}"
    for p in "${needed[@]}"; do kept+=("$p (other software needs it)"); done
  fi
}

if [ "$mode" != config ]; then
  if [ "$mode" = all ] || [ "$dry" -eq 1 ] || ask "Also remove i3 itself and the programs the installer added? (the list comes first)" n; then
    programs_step
  fi
fi

# the list of what the installer added goes last (the steps above read it), and the state folder with it
if [ "$do_config" -eq 1 ]; then
  for d in "$state" "$HOME/.local/bin/i3dots-uninstall"; do
    [ -e "$d" ] && { run rm -rf "$d"; gone "${d/#$HOME/\~}"; }
  done
fi

# =============================================================================
#  4. summary
# =============================================================================
echo
if [ "${#removed[@]}" -gt 0 ]; then
  say "$( [ "$dry" -eq 1 ] && echo 'would remove' || echo 'removed'):"
  printf '     - %s\n' "${removed[@]}"
else
  say "nothing was removed"
fi
[ "${#kept[@]}" -gt 0 ] && { say "kept:"; printf '     - %s\n' "${kept[@]}"; }
cat <<MSG

Done. Log out and pick your other desktop at the login screen.$(case "$FAMILY" in freebsd) echo "
  - Libraries the removed programs pulled in can go too:  sudo pkg autoremove" ;; openbsd) echo "
  - Libraries the removed programs pulled in can go too:  doas pkg_delete -a" ;; netbsd) echo "
  - Libraries the removed programs pulled in can go too:  pkgin autoremove" ;; esac)
  - Your copy of the repo (the folder with this script) is still there - delete it when you no longer need it.
  - Programs you already had before installing, and your own files, were not touched.
MSG
[ "$do_restore" -eq 0 ] && echo "  - Your old configs are still in ~/.config/*.bak-* (--no-restore)."
exit 0
