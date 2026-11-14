#!/usr/bin/env bash
# =============================================================================
#  i3wm-dots installer for FreeBSD, GhostBSD, OpenBSD and NetBSD
#  installs i3 + everything it needs + the dotfiles
#  Port of LinuxBeginnings/Hyprland-Dots (GPL-3.0-or-later)
#
#  Works from Xfce, MATE, KDE or any other desktop: it installs i3 next to your
#  current desktop, so you can pick "i3" at the login screen (or start it with startx).
#
#  Usage:  bash install.sh [options]
#    (default)       install i3 + dependencies, then the dotfiles
#    --no-packages   only copy the dotfiles (you already have the programs)
#    --wallpapers    also download the full KooL wallpaper bank (large)
#    --no-pokemon    skip pokescript and the shiny Mimikyu fastfetch greeting in the terminal
#    --no-ghostty    do not install Ghostty (kitty is used as the terminal instead)
#    --no-backup     overwrite existing configs instead of moving them aside
#    --no-auto-update do not check for a newer desktop config (cron looks every 30 minutes)
#    --update        quick re-install of the config files only (used by i3dots-update: no packages, no password)
#    --restore       put back the newest *.bak-* backups and exit
#    --dry-run       show what would happen without changing anything
#    -h, --help      show this help
#
#  Install bash and git first, then clone and run this script (README.md has the
#  command for each system):
#    git clone https://github.com/OmitGhostly/i3-bsd.git && cd i3-bsd && bash install.sh
#
#  Package managers: pkg (FreeBSD, GhostBSD), pkg_add (OpenBSD), pkgin (NetBSD).
#  Anything else: install the programs yourself, then run with --no-packages.
#  A log of every run is written to ~/.cache/i3wm-dots-install.log
# =============================================================================
set -uo pipefail

REPO_URL="${I3DOTS_REPO:-https://github.com/OmitGhostly/i3-bsd.git}"
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo /)"
cfg="${XDG_CONFIG_HOME:-$HOME/.config}"
stamp="$(date +%Y%m%d-%H%M%S)"
do_packages=1; do_wallpapers=0; do_pokemon=1; do_ghostty=1; do_backup=1; do_restore=0; dry=0
do_autoupdate=1; update_mode=0
orig_path="$PATH"
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

say()  { printf '\033[1;35m::\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
usage() { sed -n '3,29p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

for arg in "$@"; do
  case "$arg" in
    --no-packages) do_packages=0 ;;
    --packages)    do_packages=1 ;;           # kept for old instructions; now the default
    --wallpapers)  do_wallpapers=1 ;;
    --no-pokemon)  do_pokemon=0 ;;
    --no-ghostty)  do_ghostty=0 ;;
    --no-backup)   do_backup=0 ;;
    --restore)     do_restore=1 ;;
    --dry-run)     dry=1 ;;
    --no-auto-update) do_autoupdate=0 ;;
    --update)      update_mode=1; do_packages=0; do_pokemon=0 ;;   # (pokemon: keep whatever was chosen at install)
    -h|--help)     usage; exit 0 ;;
    *) die "unknown option: $arg (try --help)" ;;
  esac
done

# The config lives in ~/.config: i3's config and the scripts point there. A config folder moved elsewhere with
# XDG_CONFIG_HOME would leave a desktop whose keys and bar find nothing, so stop with what to do instead.
xdg_real="$(cd "${XDG_CONFIG_HOME:-/nonexistent/}" 2>/dev/null && pwd -P)"
if [ -n "${XDG_CONFIG_HOME:-}" ] && [ "${XDG_CONFIG_HOME%/}" != "$HOME/.config" ] \
   && { [ -z "$xdg_real" ] || [ "$xdg_real" != "$(cd "$HOME/.config" 2>/dev/null && pwd -P)" ]; }; then
  die "XDG_CONFIG_HOME is set to $XDG_CONFIG_HOME, but this config lives in ~/.config (i3 and its scripts look there).
   Run the installer with it pointing there:   XDG_CONFIG_HOME=\"\$HOME/.config\" $0 $*
   and remove the XDG_CONFIG_HOME line from your shell or session settings, so i3 finds its config too."
fi

# run a command, or just print it in --dry-run mode
run() { if [ "$dry" -eq 1 ]; then printf '   + %s\n' "$*"; return 0; fi; "$@"; }

# temporary files and folders: removed on the way out, also after Ctrl+C or a closed terminal
CLEANUP=()
cleanup() { [ "${#CLEANUP[@]}" -eq 0 ] || rm -rf -- "${CLEANUP[@]}" 2>/dev/null; return 0; }
trap cleanup EXIT

# ---- log everything (not in dry-run) -----------------------------------------
if [ "$dry" -eq 0 ]; then
  mkdir -p "$HOME/.cache" 2>/dev/null || true
  LOG="$HOME/.cache/i3wm-dots-install.log"
  exec > >(tee -a "$LOG") 2>&1
  say "log: $LOG"
fi

# ---- privileges ---------------------------------------------------------------
# Packages are installed as root: through sudo, else doas (it needs a rule in doas.conf), else su (asks
# for root's password). $SUDO is put in front of those commands.
as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  elif command -v doas >/dev/null 2>&1 && { [ -f /etc/doas.conf ] || [ -f /usr/local/etc/doas.conf ] || [ -f /usr/pkg/etc/doas.conf ]; }; then doas "$@"
  else su root -c "$(printf '%q ' "$@")"; fi
}
if [ "$(id -u)" -eq 0 ]; then
  [ "${I3DOTS_ALLOW_ROOT:-0}" = 1 ] || die "run as your normal user, not root (sudo is asked for only when installing packages)"
  SUDO=""
else
  SUDO="as_root"
  if [ "$do_packages" -eq 1 ] && ! command -v sudo >/dev/null 2>&1 && ! command -v doas >/dev/null 2>&1 && ! command -v su >/dev/null 2>&1; then
    die "sudo (or doas / su) is required to install packages. Install it, or run with --no-packages"
  fi
fi

# ---- which system ---------------------------------------------------------------
# (GhostBSD is FreeBSD with its own package repository; DragonFly and the rest: install the programs yourself)
detect_family() {
  case "${I3DOTS_OS:-$(uname -s)}" in
    FreeBSD) echo freebsd ;;
    OpenBSD) echo openbsd ;;
    NetBSD)  echo netbsd ;;
    *)       echo unknown ;;
  esac
}
FAMILY="$(detect_family)"
SYSNAME="${I3DOTS_OS:-$(uname -s)}"
if [ "$FAMILY" = freebsd ]; then
  { command -v ghostbsd-version >/dev/null 2>&1 || command -v update-station >/dev/null 2>&1 \
      || grep -qi ghostbsd /etc/os-release /var/run/os-release 2>/dev/null; } && SYSNAME=GhostBSD
fi

# ---- the BSDs only -------------------------------------------------------------------
case "${I3DOTS_OS:-$(uname -s)}" in Linux) die "This config is made for FreeBSD, GhostBSD, OpenBSD and NetBSD - it cannot be installed on Linux." ;; esac

# ---- bootstrap: script was run without the repo next to it (curl | bash) -------
# (piped from curl the script has no folder of its own: never treat the current directory as the repo by accident)
if [ ! -f "$here/install.sh" ] || [ ! -f "$here/config/i3/config" ]; then
  say "repository files not found next to the script - fetching them"
  if ! command -v git >/dev/null 2>&1; then
    case "$FAMILY" in
      freebsd) run $SUDO pkg install -y git ;;
      openbsd) run $SUDO pkg_add -I git ;;
      netbsd) run $SUDO pkgin -y install git ;;
      *) die "git is needed to download the dotfiles - install git and re-run" ;;
    esac
  fi
  dest="${XDG_DATA_HOME:-$HOME/.local/share}/i3wm-dots"
  if [ -d "$dest/.git" ]; then
    # (a copy made from the old repo address follows the new one)
    run git -C "$dest" pull --ff-only || warn "could not update $dest, using what is there"
  else run git clone --depth=1 "$REPO_URL" "$dest" || die "clone failed: $REPO_URL"; fi
  [ "$dry" -eq 1 ] && { say "dry-run: would continue with $dest/install.sh"; exit 0; }
  exec bash "$dest/install.sh" "$@"
fi

# ---- restore --------------------------------------------------------------------
if [ "$do_restore" -eq 1 ]; then
  restored=0
  for d in "$here"/config/*/; do
    name="$(basename "$d")"
    latest="$(find "$cfg" -maxdepth 1 -name "$name.bak-*" ! -name '*.part' 2>/dev/null | sort | tail -n1)"
    if [ -n "$latest" ]; then
      # (the current one moved aside first and deleted last: stopped halfway, nothing is lost)
      run rm -rf "${cfg:?}/.i3dots-removing-$name"
      if [ -e "$cfg/$name" ] || [ -L "$cfg/$name" ]; then run mv "$cfg/$name" "$cfg/.i3dots-removing-$name"; fi
      run mv "$latest" "$cfg/$name" && run rm -rf "${cfg:?}/.i3dots-removing-$name"
      say "restored $name from $(basename "$latest")"
      restored=$((restored + 1))
    fi
  done
  [ "$restored" -gt 0 ] || say "no backups (*.bak-*) found in $cfg - nothing to restore"
  exit 0
fi

# =============================================================================
#  Packages.  "a|b" = use a if the repository has it, otherwise b.  Every entry
#  is checked against the repository first; entries that do not exist on your
#  system are skipped and reported at the end, so one bad name can never abort
#  the installation of everything else.
# =============================================================================
packages_for() {
  case "$FAMILY" in
    # No brightnessctl / pamixer / BlueZ / NetworkManager / touchegg (Linux only): Platform.sh uses the system's own
    # mixer, backlight and battery tools instead. Names checked against each ports tree.
    # (The Python GTK bindings follow the python3 that gets installed: see python_gtk)
    freebsd) echo "i3 xorg polybar picom dunst rofi feh maim xdotool xclip xss-lock i3lock ImageMagick7 playerctl redshift
                   numlockx jq curl arandr git mpv xdg-utils lxappearance fastfetch python3 gtk3 libnotify libqalculate
                   noto-emoji freedesktop-sound-theme adwaita-icon-theme xsettingsd thunar polkit-gnome dbus xbacklight
                   networkmgr swappy clipmenu|copyq nerd-fonts-fantasquesansmono xinput xrandr xprop xset xrdb xsetroot
                   xdpyinfo setxkbmap mesa-demos bash" ;;
    # (X and its programs - xrandr, xbacklight, glxinfo ... - come with OpenBSD itself: the xenocara sets)
    openbsd) echo "i3 polybar picom dunst rofi feh maim xdotool xclip xss-lock i3lock ImageMagick playerctl redshift numlockx
                   jq curl unzip arandr git mpv xdg-utils lxappearance fastfetch python%3 py3-gobject3 py3-cairo gtk+3
                   libnotify libqalculate noto-emoji sound-theme-freedesktop adwaita-icon-theme xsettingsd thunar dbus
                   clipmenu|copyq fantasquesansmono-nerd-fonts bash" ;;
    # (NetBSD: X comes with the system's X sets; no polybar package - i3's own bar is used, see polybar/launch.sh)
    netbsd)  echo "i3 i3status picom dunst rofi feh maim xdotool xclip xss-lock i3lock ImageMagick redshift numlockx jq curl
                   unzip arandr git mpv xdg-utils lxappearance fastfetch pkg_alternatives python314|python313|python312
                   gtk3+ libnotify qalculate noto-emoji-ttf sound-theme-freedesktop adwaita-icon-theme xfce4-thunar dbus
                   xbacklight copyq nerd-fonts-FantasqueSansMono bash" ;;
  esac
}

# the Python GTK bindings for the settings window: for the python3 that is installed (FreeBSD: py311-pygobject for
# Python 3.11; NetBSD: py314-gobject3 for 3.14), else for the newest Python the repository has them for - the settings
# window then runs with that Python. OpenBSD's py3-* follow its python%3 by themselves. Prints "PYGOBJECT PYCAIRO".
python_gtk() {
  local v vs g c
  v="$(python3 -c 'import sys; print("%d%d" % sys.version_info[:2])' 2>/dev/null)"
  vs="$v 314 313 312 311 310"
  for v in $vs; do
    case "$FAMILY" in
      freebsd) g="py$v-pygobject"; c="py$v-pycairo" ;;
      netbsd)  g="py$v-gobject3"; c="py$v-cairo" ;;
      *) return 0 ;;
    esac
    if [ "$dry" -eq 1 ] || { pkg_available "$g" && pkg_available "$c"; }; then echo "$g $c"; return 0; fi
  done
}

# the package's own name for a name with a version or flavour mark (OpenBSD: python%3 -> python)
pkg_stem() { printf '%s\n' "${1%%%*}"; }
# is this exactly a package name at the start of a "name-version ..." line? (names like gtk+3 are no regex)
first_word_is() { awk -v s="$1" 'index($0, s "-") == 1 && substr($0, length(s) + 2, 1) ~ /[0-9]/ { f = 1 } END { exit !f }'; }

# Every package name the repository offers, read ONCE - instead of asking the package manager about each of the
# ~60 packages one by one. (OpenBSD has no such list on the computer: there each one is still asked about.)
PKG_INDEX="" pkg_index_read=0
read_pkg_index() {
  [ "$pkg_index_read" -eq 0 ] || return 0
  pkg_index_read=1
  PKG_INDEX="$(mktemp)"; CLEANUP+=("$PKG_INDEX")
  case "$FAMILY" in
    freebsd) pkg rquery -a '%n' 2>/dev/null ;;
    netbsd)  pkgin avail 2>/dev/null | awk -F'[ ;\t]' '{ n = $1; sub(/-[0-9][^-]*$/, "", n); print n }' ;;
  esac | sort -u >"$PKG_INDEX"
}

pkg_available() {
  read_pkg_index
  [ -s "$PKG_INDEX" ] && grep -qxF -- "$1" "$PKG_INDEX" && return 0
  case "$FAMILY" in
    freebsd) pkg rquery '%n' "$1" 2>/dev/null | grep -qxF "$1" ;;
    openbsd) pkg_info -Q "$(pkg_stem "$1")" 2>/dev/null | first_word_is "$(pkg_stem "$1")" ;;
    netbsd)  pkgin search "^$(printf '%s' "$1" | sed 's/[][+.*?(){}|^$\\]/\\&/g')-[0-9]" 2>/dev/null | first_word_is "$1" ;;
    *)      return 1 ;;
  esac
}

# Another program installing or updating packages right now (GhostBSD's Update Station, a terminal): the package
# manager would stop at its lock, so the wait is said out loud. Up to 15 minutes.
other_installs() {
  local p
  for p in pkg pkg-static pkg_add pkg_delete pkgin; do
    pgrep -x "$p" >/dev/null 2>&1 && printf '%s\n' "$p"
  done | paste -sd ' ' -
}
wait_for_other_installs() {
  [ "$dry" -eq 1 ] && return 0
  local busy waited=0
  busy="$(other_installs)"
  [ -n "$busy" ] || return 0
  say "another program is installing or updating packages right now ($busy). Waiting for it to finish (up to 15 minutes)..."
  while [ -n "$busy" ] && [ "$waited" -lt 900 ]; do
    sleep 10; waited=$((waited + 10))
    busy="$(other_installs)"
    [ $((waited % 60)) -eq 0 ] && [ -n "$busy" ] && say "  still waiting for: $busy ($((waited / 60)) min)"
  done
  [ -n "$busy" ] && warn "still busy ($busy) - trying anyway; if the install fails, close it and run this again"
  return 0
}

pkg_install() {   # pkg_install pkg...
  case "$FAMILY" in
    freebsd) run $SUDO pkg install -y "$@" ;;
    openbsd) run $SUDO pkg_add -I "$@" ;;
    netbsd) run $SUDO pkgin -y install "$@" ;;
  esac
}

missing=()

# ---- what the installer added: uninstall.sh reads this, so it only removes what was not there before ---------------
MANIFEST="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots/installed"
record() {   # record KIND VALUE   (pkg NAME | path PATH | rc PATH | mime TYPE OLD)
  [ "$dry" -eq 1 ] && return 0
  mkdir -p "$(dirname "$MANIFEST")" 2>/dev/null || return 0
  grep -qxF "$1 $2" "$MANIFEST" 2>/dev/null || printf '%s %s\n' "$1" "$2" >>"$MANIFEST"
}
pkg_installed() {   # is it installed?
  case "$FAMILY" in
    freebsd) pkg info -e "$1" 2>/dev/null ;;
    openbsd) pkg_info -q -e "$(pkg_stem "$1")-*" >/dev/null 2>&1 ;;
    netbsd)  pkg_info -q -e "$1" >/dev/null 2>&1 ;;
    *)      return 1 ;;
  esac
}
pkg_name() { printf '%s\n' "$1"; }   # (the name written down for the uninstaller)
record_new_pkgs() {   # record_new_pkgs PKG...  (the ones that were missing before: those now installed are ours)
  local p
  [ "$dry" -eq 1 ] && return 0
  for p in "$@"; do pkg_installed "$p" && record pkg "$(pkg_name "$p")"; done
  return 0
}

# pinned to a reviewed commit: the sprite is printed straight into your terminal, so it must not change under you
POKESCRIPT_REV="efb573d81beacf629d981b4997ed304ce3c34b8c"
install_pokemon() {   # acxz/pokescript: the shiny Mimikyu sprite shown by fastfetch in the terminal
  [ "$do_pokemon" -eq 1 ] || return 0
  command -v git >/dev/null 2>&1 || return 0
  local dest="${XDG_DATA_HOME:-$HOME/.local/share}/pokescript"
  if [ "$dry" -eq 0 ] && [ "$(git -C "$dest" rev-parse HEAD 2>/dev/null)" = "$POKESCRIPT_REV" ]; then return 0; fi
  say "installing pokescript (acxz/pokescript @ ${POKESCRIPT_REV:0:7}) for the Mimikyu greeting"
  run rm -rf "$dest"
  run mkdir -p "$dest"
  if run git -C "$dest" init -q \
     && run git -C "$dest" fetch -q --depth 1 https://github.com/acxz/pokescript.git "$POKESCRIPT_REV" \
     && run git -C "$dest" checkout -q FETCH_HEAD; then :
  else
    warn "could not download pokescript - the bundled Mimikyu sprite is used instead"
    run rm -rf "$dest"
  fi
}

# ---- which shell: the greeting, the prompt and the asciiquarium line go into ~/.bashrc and/or ~/.zshrc ---------
# Every rc file you already have gets them, and so does the one of your login shell (from /etc/passwd) - created if
# it does not exist yet (a new zsh user has no ~/.zshrc), so the greeting always shows in your own shell.
RC_FILES=()
login_shell() {
  local s="${I3DOTS_SHELL:-}"
  [ -n "$s" ] || s="$(getent passwd "$(id -un)" 2>/dev/null | cut -d: -f7)"
  [ -n "$s" ] || s="${SHELL:-}"
  basename "${s:-bash}"
}
prepare_shell_rc() {
  local sh rc
  sh="$(login_shell)"
  case "$sh" in
    zsh|bash)
      rc="$HOME/.${sh}rc"
      if [ ! -f "$rc" ] && [ "$update_mode" -eq 0 ]; then
        say "your shell is $sh and there is no ~/.${sh}rc yet - creating it"
        if [ "$dry" -eq 0 ]; then
          if [ -f "/etc/skel/.${sh}rc" ]; then cp "/etc/skel/.${sh}rc" "$rc"      # the system's default one
          else printf '# ~/.%src - created by the i3wm-dots installer\n' "$sh" >"$rc"; fi
          record rc "$rc"
        fi
      fi
      say "your shell is $sh: the fastfetch greeting, the prompt and asciiquarium are set up in ~/.${sh}rc" ;;
    fish)      # (GhostBSD's default shell) the greeting goes into fish's own conf.d; the prompt is for bash / zsh
      say "your shell is fish: the fastfetch greeting is set up in ~/.config/fish/conf.d (the prompt is for bash and zsh)" ;;
    *)
      warn "your shell is $sh: the fastfetch greeting and the prompt are made for bash and zsh"
      warn "  (they are still added to ~/.bashrc / ~/.zshrc if you have them; in $sh run ~/.config/i3/scripts/PokeFetch.sh yourself)" ;;
  esac
  RC_FILES=()
  for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
    [ -f "$rc" ] && RC_FILES+=("$rc")
  done
  # (dry run: the rc file that would be created)
  [ "$dry" -eq 1 ] && case "$sh" in zsh|bash) [ -f "$HOME/.${sh}rc" ] || RC_FILES+=("$HOME/.${sh}rc") ;; esac
  return 0
}

# add the Pokemon fastfetch line to the shell rc files (once; an older kitty-only line is upgraded).
# In ~/.zshrc it goes on the very first lines: prompt themes with an "instant prompt" (Powerlevel10k, many
# oh-my-zsh ones) draw the prompt before the rest of ~/.zshrc runs and warn about anything
# printed after that, and fastfetch also asks the terminal things, which only works above that point.
# An update (--update) moves a greeting you already have to the top, but never adds one you did not choose.
install_shell_hook() {
  [ "$do_pokemon" -eq 1 ] || [ "$update_mode" -eq 1 ] || return 0
  local rc real tmp top marker='# i3wm-dots: pokemon fastfetch'
  # I3DOTS_POKEFETCH (not exported) makes sure the greeting shows only once per shell, even if the line is sourced twice
  # another greeting the shell file runs itself (KoolDots' .zshrc: "pokemon-colorscripts ... | fastfetch ...", or a
  # plain "fastfetch" line) would show a second one: it is turned off, marked so the uninstaller can put it back
  local other='^[[:space:]]*(fastfetch|pokemon-colorscripts[^#]*[|][[:space:]]*fastfetch)([[:space:]]|$)' off='#i3wm-dots-off# '
  local line='[ -z "$I3DOTS_POKEFETCH" ] && { [ -n "$KITTY_WINDOW_ID" ] || [ "$TERM_PROGRAM" = ghostty ]; } && [ -x "$HOME/.config/i3/scripts/PokeFetch.sh" ] && { I3DOTS_POKEFETCH=1; "$HOME/.config/i3/scripts/PokeFetch.sh"; }'
  for rc in "${RC_FILES[@]}"; do
    top=0; [ "${rc##*/}" = .zshrc ] && top=1
    if grep -qF "$marker" "$rc" 2>/dev/null; then
      # already there, once, the current version, and (zsh) on the first line: nothing to do
      if grep -qF 'I3DOTS_POKEFETCH' "$rc" && [ "$(grep -cF "$marker" "$rc")" -eq 1 ] \
         && { [ "$top" -eq 0 ] || [ "$(head -n 1 "$rc")" = "$marker" ]; } && ! grep -qE "$other" "$rc"; then
        continue
      fi
      if grep -qE "$other" "$rc"; then
        say "turning off the other fastfetch greeting in $rc (it showed a second one; i3dots-uninstall puts it back):"
        grep -nE "$other" "$rc" | sed 's/^/     line /'
      elif [ "$top" -eq 1 ]; then say "moving the pokemon fastfetch greeting to the top of $rc (before the prompt theme starts)"
      else say "refreshing the pokemon fastfetch greeting in $rc (one greeting per terminal)"; fi
    else
      [ "$update_mode" -eq 1 ] && continue
      say "adding the pokemon fastfetch greeting to $rc (kitty and ghostty only)"
    fi
    [ "$dry" -eq 1 ] && continue
    # write the real file (a ~/.zshrc linked from a dotfiles folder stays a link), through a copy that keeps its
    # permissions; every old copy of the greeting (marker line + the line after it, and the blank line before it)
    # goes, and a single fresh one is added: first thing in ~/.zshrc, last thing in ~/.bashrc
    real="$(readlink -f -- "$rc" 2>/dev/null)"; [ -n "$real" ] || real="$rc"
    tmp="$real.i3tmp"; CLEANUP+=("$tmp")
    cp -p -- "$real" "$tmp" || continue
    {
      [ "$top" -eq 1 ] && printf '%s\n%s\n' "$marker" "$line"
      awk -v m="$marker" -v o="$other" -v off="$off" 'skip { skip = 0; next }
           index($0, m) == 1 { skip = 1; blank = 0; next }
           $0 ~ o { $0 = off $0 }
           { if (blank) print ""; blank = 0 }
           /^$/ { blank = 1; next }
           { print }
           END { if (blank) print "" }' "$real"
      [ "$top" -eq 1 ] || printf '\n%s\n%s\n' "$marker" "$line"
    } >"$tmp" && mv -f -- "$tmp" "$real"
  done
}

# fish: the same greeting as a fish conf.d file (written for the login shell fish, or a fish set up already)
install_fish_hook() {
  [ "$do_pokemon" -eq 1 ] || return 0
  local d="$cfg/fish/conf.d" f
  f="$d/i3wm-dots.fish"
  [ "$(login_shell)" = fish ] || [ -d "$d" ] || return 0
  [ -f "$f" ] && grep -qF 'I3DOTS_POKEFETCH' "$f" && return 0
  say "adding the pokemon fastfetch greeting for fish ($f, kitty and ghostty only)"
  [ "$dry" -eq 1 ] && return 0
  mkdir -p "$d" || return 0
  record path "$f"
  cat >"$f" <<'FISH'
# i3wm-dots: pokemon fastfetch greeting (kitty and ghostty, once per terminal). Remove this file to turn it off.
if status is-interactive; and not set -q I3DOTS_POKEFETCH
    if set -q KITTY_WINDOW_ID; or test "$TERM_PROGRAM" = ghostty
        set -g I3DOTS_POKEFETCH 1
        test -x "$HOME/.config/i3/scripts/PokeFetch.sh"; and "$HOME/.config/i3/scripts/PokeFetch.sh"
    end
end
FISH
}

# "asciiquarium" in the terminal: run it see-through (its own background is solid black) - once per rc file
install_aquarium_alias() {
  local rc marker='# i3wm-dots: see-through asciiquarium'
  local line='[ -x "$HOME/.config/i3/scripts/Aquarium.sh" ] && alias asciiquarium="$HOME/.config/i3/scripts/Aquarium.sh"'
  for rc in "${RC_FILES[@]}"; do
    grep -qF "$marker" "$rc" 2>/dev/null && continue
    say "making asciiquarium see-through in $rc"
    [ "$dry" -eq 1 ] || printf '\n%s\n%s\n' "$marker" "$line" >> "$rc"
  done
}

# the black / grey / white prompt (~/.config/i3/scripts/Prompt.sh) in bash and zsh - once per rc file.
# It steps aside by itself when another prompt theme (starship, oh-my-zsh, powerlevel10k...) is in charge.
install_prompt() {
  local rc marker='# i3wm-dots: black / grey / white prompt (turn off: export I3DOTS_PROMPT=off above this line)'
  local line='[ -r "$HOME/.config/i3/scripts/Prompt.sh" ] && . "$HOME/.config/i3/scripts/Prompt.sh"'
  for rc in "${RC_FILES[@]}"; do
    grep -qF '# i3wm-dots: black / grey / white prompt' "$rc" 2>/dev/null && continue
    say "adding the black / grey / white prompt to $rc"
    [ "$dry" -eq 1 ] || printf '\n%s\n%s\n' "$marker" "$line" >> "$rc"
  done
}

# ---- terminals: Ghostty (the default) and kitty (the fallback) ----------------------------------------------
# Both are checked; whichever is missing is installed from the system's repository (there are no other builds for
# the BSDs: where a terminal is not packaged, the other one is used).
install_ghostty() {
  local had=0
  pkg_installed ghostty && had=1          # (installed, but not on PATH: never record it as ours)
  pkg_available ghostty || return 1
  say "installing Ghostty from the $SYSNAME packages"
  pkg_install ghostty && { [ "$had" -eq 1 ] || record_new_pkgs ghostty; return 0; }
  return 1
}

install_kitty() {
  local had=0
  pkg_installed kitty && had=1
  pkg_available kitty || return 1
  say "installing kitty from the $SYSNAME packages"
  pkg_install kitty && { [ "$had" -eq 1 ] || record_new_pkgs kitty; return 0; }
  return 1
}

ensure_terminals() {
  local t
  say "checking the terminals: Ghostty (the default) and kitty (the fallback)"
  for t in ghostty kitty; do
    if [ "$t" = ghostty ] && [ "$do_ghostty" -eq 0 ]; then
      echo "   ghostty: skipped (--no-ghostty)"
    elif command -v "$t" >/dev/null 2>&1; then
      # (asked with a throwaway config folder: kitty creates ~/.config/kitty just by starting, which would then
      #  look like a config of your own and be backed up)
      local vt; vt="$(mktemp -d)"; CLEANUP+=("$vt")
      echo "   $t: already installed ($(env XDG_CONFIG_HOME="$vt" XDG_CACHE_HOME="$vt" XDG_STATE_HOME="$vt" KITTY_CONFIG_DIRECTORY="$vt" \
        "$t" --version 2>/dev/null | head -n1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -n1))"
      rm -rf "$vt"
    elif [ "$do_packages" -eq 0 ]; then
      echo "   $t: not installed (--no-packages: install it yourself with your package manager)"
    elif "install_$t" && { [ "$dry" -eq 1 ] || command -v "$t" >/dev/null 2>&1; }; then
      echo "   $t: installed"
    elif [ "$t" = ghostty ] && ! pkg_available ghostty; then
      echo "   ghostty: not packaged for $SYSNAME - kitty will be your terminal"
    elif [ "$t" = ghostty ]; then
      warn "Ghostty could not be installed - kitty will be your terminal"
    elif ! pkg_available kitty; then
      echo "   kitty: not packaged for $SYSNAME"
    else
      warn "kitty could not be installed - install it yourself (pkg / pkg_add / pkgin: kitty)"
    fi
  done
}

# ---- the file manager: yazi (opens in the terminal; Thunar stays installed as the graphical one) -------------------
# From the system's repository, where it has it (FreeBSD, NetBSD, OpenBSD ...): yazi has no other BSD builds.
have_yazi() { command -v yazi >/dev/null 2>&1 || [ -x "$HOME/.local/bin/yazi" ]; }
yazi_version() {
  local y; y="$(command -v yazi 2>/dev/null || echo "$HOME/.local/bin/yazi")"
  "$y" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1
}

install_yazi() {
  local had=0
  pkg_installed yazi && had=1
  pkg_available yazi || return 1
  say "installing yazi from the $SYSNAME packages"
  pkg_install yazi && { [ "$had" -eq 1 ] || record_new_pkgs yazi; return 0; }
  return 1
}

# what makes yazi's previews and search work: PDFs (poppler), archives (7-Zip), find (fd), search in files (ripgrep),
# fuzzy find and jump to folders (fzf, zoxide). Best effort: whatever your repos have; none of it is required.
yazi_extras() {
  case "$FAMILY" in
    freebsd) echo "poppler-utils 7-zip|p7zip fd-find|fd ripgrep fzf zoxide" ;;
    openbsd) echo "poppler-utils|poppler 7zip|p7zip fd ripgrep fzf zoxide" ;;
    netbsd)  echo "poppler-utils|poppler 7-zip|p7zip fd|fd-find ripgrep fzf zoxide" ;;
  esac
}

install_yazi_extras() {
  local item alt pick want=() new=() skipped=() p alts=()
  for item in $(yazi_extras); do
    IFS='|' read -ra alts <<<"$item"; pick=""
    for alt in "${alts[@]}"; do pkg_installed "$alt" && { pick="$alt"; break; }; done
    if [ -z "$pick" ]; then
      for alt in "${alts[@]}"; do
        if [ "$dry" -eq 1 ] || pkg_available "$alt"; then pick="$alt"; break; fi
      done
    fi
    if [ -n "$pick" ]; then want+=("$pick"); else skipped+=("${alts[0]}"); fi
  done
  [ "${#skipped[@]}" -gt 0 ] && echo "   yazi extras not in your repos (fine - yazi works without them): ${skipped[*]}"
  for p in "${want[@]}"; do pkg_installed "$p" || new+=("$p"); done
  [ "${#new[@]}" -gt 0 ] || return 0
  say "installing yazi's preview and search helpers: ${new[*]}"
  if ! pkg_install "${new[@]}"; then
    for p in "${new[@]}"; do pkg_install "$p" >/dev/null 2>&1 || echo "   (could not install $p - yazi works without it)"; done
  fi
  record_new_pkgs "${new[@]}"
}

ensure_file_manager() {
  say "checking the file manager: yazi (the default - it opens in the terminal)"
  if have_yazi; then
    echo "   yazi: already installed ($(yazi_version))"
  elif [ "$do_packages" -eq 0 ]; then
    echo "   yazi: not installed (--no-packages: Thunar opens instead until you install yazi)"
    return 0
  elif [ "$dry" -eq 0 ] && ! pkg_available yazi; then
    echo "   yazi: not packaged for $SYSNAME - Thunar is your file manager"
    return 0
  elif install_yazi && { [ "$dry" -eq 1 ] || have_yazi; }; then
    echo "   yazi: installed"
  else
    warn "yazi could not be installed - Thunar is your file manager"
    return 0
  fi
  [ "$do_packages" -eq 1 ] && install_yazi_extras
  return 0
}

# sed_file SED-ARGUMENTS... FILE: edit a file in place with any sed (GNU sed -i and BSD sed -i '' differ)
sed_file() {
  local f="${*: -1}" t rc
  t="$f.i3tmp.$$"; CLEANUP+=("$t")
  sed "${@:1:$#-1}" "$f" >"$t" 2>/dev/null && cat "$t" >"$f"
  rc=$?
  rm -f "$t"
  return $rc
}

# use ghostty as the terminal when it is installed, otherwise kitty (the configs ship with ghostty)
choose_terminal() {
  local t=ghostty
  command -v ghostty >/dev/null 2>&1 || t=kitty
  [ "$dry" -eq 1 ] && { say "terminal: ghostty if it installs, otherwise kitty"; return 0; }
  say "default terminal: $t"
  sed_file "s/^term=.*/term=\"$t\"/" "$cfg/i3/defaults.conf" 2>/dev/null || true
  sed_file "s/^\( *terminal: \).*/\1\"$t\";/" "$cfg/i3/rofi/00-terminal.rasi" 2>/dev/null || true
}

# yazi as the file manager when it is installed, otherwise Thunar (Settings > Keybindings changes it)
choose_file_manager() {
  [ "$dry" -eq 1 ] && { say "file manager: yazi if it is installed, otherwise Thunar"; return 0; }
  if have_yazi; then say "default file manager: yazi (opens in the terminal)"; return 0; fi
  command -v thunar >/dev/null 2>&1 || return 0
  say "default file manager: Thunar (yazi is not installed)"
  sed_file 's/^files=.*/files="thunar"/' "$cfg/i3/defaults.conf" 2>/dev/null || true
}

# Folders opened from other programs (xdg-open, a browser's "Show in folder"...) go to the same file manager
# (yazi by default), through a small launcher entry. It becomes the default for folders on a first install, or
# when you had not picked one yourself; uninstall puts back what was set before.
FOLDERS_DESKTOP=i3wm-dots-folders.desktop
mime_default() {   # mime_default TYPE: the program ~/.config/mimeapps.list sets for it (nothing: none set there)
  awk -v t="$1" '/^\[/ { s = ($0 == "[Default Applications]") }
                 s && index($0, t "=") == 1 { print substr($0, length(t) + 2); exit }' "$cfg/mimeapps.list" 2>/dev/null
}
set_mime_default() {   # set_mime_default TYPE DESKTOP-ID  (in [Default Applications] of ~/.config/mimeapps.list)
  local f="$cfg/mimeapps.list" real tmp src=/dev/null
  real="$(readlink -f -- "$f" 2>/dev/null)"; [ -n "$real" ] || real="$f"     # (a linked file stays a link)
  tmp="$real.i3tmp"; CLEANUP+=("$tmp")
  if [ -f "$real" ]; then cp -p -- "$real" "$tmp" || return 1; src="$real"; fi
  awk -v t="$1" -v d="$2" '
    /^\[/ { if (s && !done) { print t "=" d ";"; done = 1 }
            s = ($0 == "[Default Applications]"); if (s) seen = 1 }
    s && index($0, t "=") == 1 { if (!done) { print t "=" d ";"; done = 1 } next }
    { print }
    END { if (!done) { if (!seen) { if (NR) print ""; print "[Default Applications]" } print t "=" d ";" } }' "$src" >"$tmp" \
    && mv -f -- "$tmp" "$real"
}
install_folder_handler() {
  local apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications" launcher="$cfg/i3/scripts/LaunchFileManager.sh" cur exec
  case "$launcher" in
    *[\"\`\$\\%]*|*$'\n'*) warn "folders from other programs keep opening as before (your home folder's name has characters a launcher entry cannot hold)"; return 0 ;;
  esac
  [ -f "$apps/$FOLDERS_DESKTOP" ] || record path "$apps/$FOLDERS_DESKTOP"
  # quoted only when it has to be (a space in the path): xdg-open before 1.2 cannot run a quoted program path
  exec="$launcher"; case "$launcher" in *[!A-Za-z0-9/._+-]*) exec="\"$launcher\"" ;; esac
  cur="$(mime_default inode/directory)"
  if [ "$dry" -eq 1 ]; then
    say "folders from other programs open in your file manager ($apps/$FOLDERS_DESKTOP)"; return 0
  fi
  mkdir -p "$apps" && printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=Folders (i3wm-dots)' \
    'Comment=Opens folders in the file manager chosen in the i3 Settings window (yazi by default)' \
    "Exec=$exec --open %u" 'Icon=system-file-manager' 'Terminal=false' 'NoDisplay=true' \
    'MimeType=inode/directory;' >"$apps/$FOLDERS_DESKTOP" || return 0
  case "$cur" in "$FOLDERS_DESKTOP"*) return 0 ;; esac
  if [ "$first_install" -eq 1 ] || [ -z "$cur" ]; then
    say "folders opened from other programs now go to your file manager too (before: ${cur:-the system default})"
    record mime "inode/directory ${cur:--}"
    set_mime_default inode/directory "$FOLDERS_DESKTOP" || warn "could not set the default for folders in $cfg/mimeapps.list"
  fi
}

# what goes into the one big package run besides the list (see install_packages)
bulk_extras() {
  [ "$update_mode" -eq 1 ] && return 0
  [ "$do_ghostty" -eq 1 ] && ! command -v ghostty >/dev/null 2>&1 && echo ghostty
  have_yazi || echo yazi
  yazi_extras
}

install_packages() {
  if [ "$FAMILY" = unknown ]; then
    warn "$SYSNAME: no automatic package install (automated: FreeBSD / GhostBSD, OpenBSD, NetBSD)."
    warn "Install yourself:  i3 (>=4.22) xorg polybar picom dunst rofi kitty feh maim xdotool xclip xss-lock i3lock"
    warn "  imagemagick playerctl redshift clipmenu|copyq numlockx xinput xrandr xprop xdpyinfo setxkbmap libnotify mpv"
    warn "  qalc jq curl arandr thunar lxappearance fastfetch dbus python3 with GTK 3 (PyGObject) yazi bash"
    warn "then re-run with --no-packages"
    return 0
  fi
  say "$SYSNAME detected - checking which packages your repository provides"
  wait_for_other_installs
  [ "$FAMILY" = freebsd ] && run $SUDO pkg update
  [ "$FAMILY" = netbsd ] && run $SUDO pkgin -y update

  local have=() item pick alt alts
  # shellcheck disable=SC2046
  for item in $(packages_for); do
    pick=""
    IFS='|' read -ra alts <<<"$item"
    # one of the choices you already have (copyq instead of clipmenu, your polkit agent...) - else the first there is
    if [ "${#alts[@]}" -gt 1 ]; then
      for alt in "${alts[@]}"; do pkg_installed "$alt" && { pick="$alt"; break; }; done
    fi
    if [ -z "$pick" ]; then
      for alt in "${alts[@]}"; do
        if [ "$dry" -eq 1 ] || pkg_available "$alt"; then pick="$alt"; break; fi
      done
    fi
    if [ -n "$pick" ]; then have+=("$pick"); else missing+=("${item//|/ or }"); fi
  done

  # Asked for in the same run, so the package manager works once instead of three times: Ghostty and yazi where
  # the repository has them, and yazi's helpers.
  local extras=()
  for item in $(bulk_extras); do
    pick=""
    IFS='|' read -ra alts <<<"$item"
    for alt in "${alts[@]}"; do pkg_installed "$alt" && { pick=-; break; }; done      # (there already)
    if [ -z "$pick" ]; then
      for alt in "${alts[@]}"; do
        if [ "$dry" -eq 0 ] && pkg_available "$alt"; then pick="$alt"; break; fi
      done
    fi
    [ -n "$pick" ] && [ "$pick" != - ] && extras+=("$pick")
  done

  local new=() p
  for p in "${have[@]}" "${extras[@]}"; do pkg_installed "$p" || new+=("$p"); done   # (not installed yet: ours if it gets installed)
  say "installing $(( ${#have[@]} + ${#extras[@]} )) packages"
  if ! pkg_install "${have[@]}" "${extras[@]}"; then
    warn "bulk install failed - retrying one package at a time so a single problem cannot block the rest"
    for p in "${have[@]}"; do pkg_install "$p" || missing+=("$p"); done
    for p in "${extras[@]}"; do pkg_install "$p" >/dev/null 2>&1 || true; done
  fi
  record_new_pkgs "${new[@]}"

  # the settings window's Python GTK bindings, for the python3 that is now installed (FreeBSD, NetBSD)
  if [ "$FAMILY" = freebsd ] || [ "$FAMILY" = netbsd ]; then
    local gtk=() bnew=() g
    read -ra gtk <<<"$(python_gtk)"
    for g in "${gtk[@]}"; do pkg_installed "$g" || bnew+=("$g"); done
    [ "${#gtk[@]}" -gt 0 ] || missing+=("GTK for Python (the settings window)")
    if [ "${#gtk[@]}" -gt 0 ]; then
      say "installing the settings window's GTK for Python: ${gtk[*]}"
      pkg_install "${gtk[@]}" || missing+=("${gtk[@]}")
      record_new_pkgs "${bnew[@]}"
    fi
  fi

  # notifications, the settings window's helpers ... need D-Bus, whose system service is not always on
  enable_dbus
}

# D-Bus: started at boot from now on, and now (programs find their session bus through it - see
# bsd_session for the session itself)
enable_dbus() {
  case "$FAMILY" in
    freebsd)
      if ! grep -qE '^dbus_enable="?(YES|yes)"?' /etc/rc.conf 2>/dev/null; then
        say "turning on D-Bus (sysrc dbus_enable=YES)"
        run $SUDO sysrc dbus_enable=YES >/dev/null || warn "could not turn on D-Bus - run: sudo sysrc dbus_enable=YES"
      fi
      run $SUDO service dbus status >/dev/null 2>&1 || run $SUDO service dbus start >/dev/null 2>&1 || true ;;
    openbsd)
      if ! grep -q 'messagebus' /etc/rc.conf.local 2>/dev/null; then
        say "turning on D-Bus (rcctl enable messagebus)"
        run $SUDO rcctl enable messagebus || warn "could not turn on D-Bus - run: doas rcctl enable messagebus"
      fi
      run $SUDO rcctl start messagebus >/dev/null 2>&1 || true ;;
    netbsd)
      if [ ! -e /etc/rc.d/dbus ] && [ -e /usr/pkg/share/examples/rc.d/dbus ]; then
        run $SUDO cp /usr/pkg/share/examples/rc.d/dbus /etc/rc.d/dbus || true
      fi
      if ! grep -qE '^dbus=(YES|yes)' /etc/rc.conf 2>/dev/null; then
        say "turning on D-Bus (dbus=YES in /etc/rc.conf)"
        run $SUDO sh -c 'echo dbus=YES >> /etc/rc.conf' || warn "could not turn on D-Bus - add dbus=YES to /etc/rc.conf"
      fi
      [ -x /etc/rc.d/dbus ] && { run $SUDO /etc/rc.d/dbus start >/dev/null 2>&1 || true; } ;;
  esac
}

# The font is downloaded while the packages install (it needs no package manager): started here, used by
# install_font below - which downloads it itself when this did not happen or did not work.
FONT_URL="https://github.com/ryanoasis/nerd-fonts/releases/latest/download/FantasqueSansMono.zip"
font_pre="" font_pre_pid=""
have_font() { fc-list 2>/dev/null | grep -iE 'fantasque.*nerd|nerd.*fantasque' >/dev/null; }
prefetch_font() {
  [ "$dry" -eq 0 ] && command -v curl >/dev/null 2>&1 || return 0
  command -v fc-list >/dev/null 2>&1 && have_font && return 0
  font_pre="$(mktemp -d)"; CLEANUP+=("$font_pre")
  ( curl -fsSL --retry 2 -o "$font_pre/f.part" "$FONT_URL" && mv -f "$font_pre/f.part" "$font_pre/f.zip" ) >/dev/null 2>&1 &
  font_pre_pid=$!
}

install_font() {
  [ -n "$font_pre_pid" ] && { wait "$font_pre_pid" 2>/dev/null; font_pre_pid=""; }
  command -v fc-list >/dev/null 2>&1 || return 0
  # (grep reads all of fc-list's output: with -q it would stop early, and pipefail would count that as a failure)
  if have_font; then return 0; fi
  if command -v curl >/dev/null 2>&1 && command -v unzip >/dev/null 2>&1; then
    say "installing FantasqueSansM Nerd Font (icons in the bar and terminal)"
    local fd="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/FantasqueSansMNerd" tmp
    tmp="$(mktemp -d)"; CLEANUP+=("$tmp")
    # (the folder is written down before unpacking into it, so a stopped install still leaves it recorded)
    if { { [ -n "$font_pre" ] && [ -s "$font_pre/f.zip" ] && run mv -f "$font_pre/f.zip" "$tmp/f.zip"; } \
         || run curl -fsSL --retry 2 -o "$tmp/f.zip" "$FONT_URL"; } \
       && { [ -e "$fd" ] || record path "$fd"; } && run mkdir -p "$fd" && run unzip -qo "$tmp/f.zip" -d "$fd"; then
      run fc-cache -f "$fd" >/dev/null 2>&1
    else
      warn "font download failed - install 'FantasqueSansM Nerd Font' yourself (nerdfonts.com) or icons will look broken"
    fi
    rm -rf "$tmp"
  else
    warn "FantasqueSansM Nerd Font missing and curl/unzip not available - install it from nerdfonts.com"
  fi
}

# (the font and the greeting's sprite download while the packages install; their messages follow afterwards)
poke_out="" poke_pid=""
if [ "$do_packages" -eq 1 ]; then
  prefetch_font
  if [ "$dry" -eq 0 ] && [ "$do_pokemon" -eq 1 ] && command -v git >/dev/null 2>&1; then
    poke_out="$(mktemp)"; CLEANUP+=("$poke_out")
    install_pokemon >"$poke_out" 2>&1 &
    poke_pid=$!
  fi
  install_packages; install_font
fi
[ "$update_mode" -eq 1 ] || ensure_terminals
[ "$update_mode" -eq 1 ] || ensure_file_manager
if [ -n "$poke_pid" ]; then wait "$poke_pid" 2>/dev/null; cat "$poke_out" 2>/dev/null; rm -f "$poke_out"; fi
install_pokemon          # (nothing to do when it is there already: also the way in without git before the packages)


# ---- copy configs ---------------------------------------------------------------
# a first install (not a re-install over our own files): only then does the first login pick a wallpaper
first_install=1
[ -f "$cfg/i3/.i3wm-dots-installed" ] && first_install=0
say "installing configs into $cfg"
run mkdir -p "$cfg"

# ~/.config/gtk-3.0 is shared: lxappearance keeps your GTK theme there and file managers keep their sidebar
# bookmarks there. It is never replaced - our settings (dark style, font) are merged into settings.ini instead.
# First install: they are set (a copy of your folder is kept as a backup); later installs and updates only add
# a setting that is missing, so a theme or font you picked yourself stays.
merge_gtk() {   # merge_gtk SRC_DIR TARGET_DIR
  local src="$1" target="$2" ini="$2/settings.ini" first=1 resumed=0 line key val
  [ -f "$target/.i3wm-dots-installed" ] && first=0
  # (the mark says "merging" while this runs: an install stopped halfway is finished by the next one, which then
  # neither makes a second backup nor treats the folder as already done)
  [ "$(cat "$target/.i3wm-dots-installed" 2>/dev/null)" = merging ] && { first=1; resumed=1; }
  rm -rf "$target".bak-*.part 2>/dev/null                # (a backup copy that a stopped install left unfinished)
  if [ "$first" -eq 1 ] && [ "$resumed" -eq 0 ] && [ -e "$target" ] && [ "$do_backup" -eq 1 ]; then
    # copied under a temporary name and renamed when complete: a half-made copy never looks like a backup
    run cp -a "$target" "$target.bak-$stamp.part" && run mv "$target.bak-$stamp.part" "$target.bak-$stamp" \
      && echo "   backup: $(basename "$target") -> $(basename "$target").bak-$stamp (copied; your bookmarks stay)"
  fi
  [ -L "$target" ] && run rm -f "$target"
  run mkdir -p "$target"
  [ "$dry" -eq 1 ] && return 0
  [ "$first" -eq 1 ] && printf 'merging\n' >"$target/.i3wm-dots-installed"
  [ -f "$src/settings.ini" ] || { : >"$target/.i3wm-dots-installed"; return 0; }
  [ -f "$ini" ] || printf '[Settings]\n' >"$ini"
  [ -s "$ini" ] && [ -n "$(tail -c1 "$ini")" ] && printf '\n' >>"$ini"      # (a last line without a newline)
  grep -q '^\[Settings\]' "$ini" || printf '[Settings]\n' >>"$ini"
  CLEANUP+=("$ini.tmp")
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*|';'*|'['*) continue ;; esac
    key="${line%%=*}"; key="${key%"${key##*[! ]}"}"; val="${line#*=}"
    [ -n "$key" ] || continue
    if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$ini"; then
      [ "$first" -eq 1 ] && KEY="$key" VAL="$val" awk 'BEGIN{k=ENVIRON["KEY"]; v=ENVIRON["VAL"]}
        { t=$0; sub(/^[ \t]*/,"",t); split(t,a,"="); s=a[1]; sub(/[ \t]*$/,"",s); if (s==k) { print k "=" v; next } } {print}' \
        "$ini" >"$ini.tmp" && mv -f "$ini.tmp" "$ini"
    else
      KEY="$key" VAL="$val" awk 'BEGIN{k=ENVIRON["KEY"]; v=ENVIRON["VAL"]} {print} /^\[Settings\]/ && !d {print k "=" v; d=1}' \
        "$ini" >"$ini.tmp" && mv -f "$ini.tmp" "$ini"
    fi
  done <"$src/settings.ini"
  : >"$target/.i3wm-dots-installed"
}

# What the Settings window saved is parked here while ~/.config/i3 is replaced (not in /tmp: an install or update
# stopped right then - Ctrl+C, a closed terminal - leaves it where the next run finds and puts it back)
keep_settings="${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots/settings.json.keep"
for d in "$here"/config/*/; do
  name="$(basename "$d")"
  target="$cfg/$name"
  if [ "$name" = gtk-3.0 ]; then merge_gtk "$d" "$target"; continue; fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    if [ -f "$target/.i3wm-dots-installed" ] && [ ! -L "$target" ]; then
      # Our own earlier install: replace it in place. Do NOT make another backup, or
      # --restore would give back the previous install instead of your original config.
      if [ "$dry" -eq 0 ] && [ "$name" = i3 ] && [ -f "$target/settings.json" ]; then
        { mkdir -p "${keep_settings%/*}" && cp -a "$target/settings.json" "$keep_settings.new" \
            && mv -f "$keep_settings.new" "$keep_settings"; } \
          || die "could not keep a copy of your Settings ($target/settings.json) - nothing was changed"
      fi
      run rm -rf "$target"
    elif [ "$do_backup" -eq 1 ]; then
      run mv "$target" "$target.bak-$stamp"; echo "   backup: $name -> $name.bak-$stamp"
    else
      run rm -rf "$target"
    fi
  fi
  run mkdir -p "$target"
  # marked as ours before anything is copied in: an install stopped halfway (Ctrl+C) then leaves a folder the next
  # run knows is its own - it replaces it, instead of backing it up as yours, so the backup of YOUR config stays the
  # one that uninstall / --restore gives back
  [ "$dry" -eq 0 ] && : > "$target/.i3wm-dots-installed"
  run cp -a "$d." "$target/" || die "could not copy $name to $target"
  # keep what the settings window saved (mouse, monitors, opacity, gaps, bar) across re-installs
  if [ "$name" = i3 ] && [ "$dry" -eq 0 ]; then
    if [ -f "$keep_settings" ]; then
      cp -a "$keep_settings" "$target/settings.json" && rm -f "$keep_settings"
    elif [ -f "$target.bak-$stamp/settings.json" ]; then
      cp -a "$target.bak-$stamp/settings.json" "$target/settings.json"
    fi
  fi
done

# the default terminal first (ghostty if installed, else kitty): the saved settings below come after it, so a
# terminal you picked in Settings > Apps is never reset by a re-install or an update
choose_terminal
choose_file_manager

if [ "$dry" -eq 0 ]; then
  find "$cfg/i3/scripts" -type f \( -name '*.sh' -o -name '*.py' \) -exec chmod +x {} + 2>/dev/null || true
  chmod +x "$cfg/polybar/launch.sh" 2>/dev/null || true
  # the fresh files have the default look: write your saved settings (accent colour, gaps, keybinds, opacity,
  # terminal theme and text size, cursor, apps) back into them, so restarting i3 (SUPER+SHIFT+R) shows them at once
  if [ -f "$cfg/i3/settings.json" ] && command -v python3 >/dev/null 2>&1; then
    if python3 "$cfg/i3/scripts/SettingsGUI.py" --refresh-files >/dev/null 2>&1; then
      say "kept your saved settings (Settings window) in the new files"
    else
      warn "could not re-apply your saved settings now - they come back at your next login"
    fi
  fi
fi
prepare_shell_rc
install_shell_hook
install_fish_hook
install_aquarium_alias
install_prompt
install_folder_handler

# ---- how i3 starts ------------------------------------------------------------------
# startx reads ~/.xinitrc; OpenBSD's xenodm and NetBSD's xdm read ~/.xsession. i3 is started inside a D-Bus session
# there (notifications and the settings window's helpers need one). A file you already have is left alone.
bsd_session() {
  [ "$update_mode" -eq 0 ] || return 0
  local f
  for f in "$HOME/.xinitrc" "$HOME/.xsession"; do
    if [ -e "$f" ]; then
      grep -q 'i3' "$f" 2>/dev/null || warn "$(basename "$f") exists and does not start i3 - to use i3, put this line last in it:  exec dbus-launch --exit-with-session i3"
      continue
    fi
    say "creating ~/$(basename "$f"): starts i3 (with a D-Bus session)"
    [ "$dry" -eq 1 ] && continue
    # (~/.xprofile: the cursor and proxy the Settings window chose - some display managers read it themselves;
    # ~/.Xresources: the cursor for X itself, so i3 starts with it and needs no restart to pick it up)
    record path "$f"
    printf '#!/bin/sh\n# created by the i3wm-dots installer: start i3 with a D-Bus session\n[ -r "$HOME/.profile" ] && . "$HOME/.profile"\n[ -r "$HOME/.xprofile" ] && . "$HOME/.xprofile"\n[ -r "$HOME/.Xresources" ] && command -v xrdb >/dev/null 2>&1 && xrdb -merge "$HOME/.Xresources"\nexec dbus-launch --exit-with-session i3\n' >"$f"
    chmod 755 "$f"
  done
}
bsd_session

# ---- wallpapers / folders ---------------------------------------------------------
run mkdir -p "$HOME/Pictures/wallpapers" "$HOME/Pictures/Screenshots"
if [ -d "$here/wallpapers" ]; then
  for w in "$here"/wallpapers/*; do
    [ -f "$w" ] || continue
    t="$HOME/Pictures/wallpapers/${w##*/}"
    [ -e "$t" ] && continue                          # (yours, or copied earlier: never overwritten)
    record path "$t" && run cp "$w" "$t"           # (written down first: a stopped install still has it listed)
  done
  say "copied bundled wallpapers to ~/Pictures/wallpapers"
fi
if [ "$do_wallpapers" -eq 1 ]; then
  command -v git >/dev/null 2>&1 || die "git is required for --wallpapers"
  say "downloading wallpaper bank (this can take a while)"
  tmp="$(mktemp -d)"; CLEANUP+=("$tmp")
  if run git clone --depth=1 https://github.com/LinuxBeginnings/Wallpaper-Bank.git "$tmp/wb"; then
    for w in "$tmp"/wb/wallpapers/*; do
      [ -f "$w" ] && [ ! -e "$HOME/Pictures/wallpapers/${w##*/}" ] || continue
      record path "$HOME/Pictures/wallpapers/${w##*/}" && run cp "$w" "$HOME/Pictures/wallpapers/${w##*/}"
    done
  else
    warn "wallpaper download failed"
  fi
  rm -rf "$tmp"
fi

# ---- the mouse cursor: Capitaine Cursors, the default (Settings > Mouse > Mouse cursor picks another) --------------
# Unpacked into your home folder on every system (no package, no password); also linked into ~/.icons for programs
# that only look there. A copy that is already there (yours, or from an earlier install) is kept as it is.
install_cursor() {
  local tarball="$here/assets/cursors/capitaine-cursors.tar.gz"
  local icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons" tmp
  local dest="$icons/capitaine-cursors"
  [ -f "$tarball" ] || return 0
  if [ ! -e "$dest" ] && [ ! -L "$dest" ]; then
    if [ "$dry" -eq 1 ]; then
      printf '   + unpack %s into %s\n' "${tarball#"$here"/}" "$dest"
    else
      mkdir -p "$icons" || { warn "could not create $icons - the default cursor is not installed"; return 0; }
      rm -rf "$icons"/.i3dots-cursor.??????        # (left by an install that was stopped halfway)
      tmp=$(mktemp -d "$icons/.i3dots-cursor.XXXXXX") || return 0
      CLEANUP+=("$tmp")
      # (gzip + tar: every system's tar reads this, OpenBSD's too; written down before it is moved into place, so a
      # stopped install can never leave it there unrecorded)
      if gzip -dc "$tarball" | (cd "$tmp" && tar -xf -) && [ -f "$tmp/capitaine-cursors/index.theme" ] \
         && [ -e "$tmp/capitaine-cursors/cursors/left_ptr" ] && record path "$dest" && mv "$tmp/capitaine-cursors" "$dest"; then
        say "installed the Capitaine Cursors theme (the default cursor)"
      else
        warn "could not unpack the cursor theme - the cursor stays as it is"
      fi
      rm -rf "$tmp"
    fi
  fi
  if [ -d "$dest" ] && [ ! -e "$HOME/.icons/capitaine-cursors" ] && [ ! -L "$HOME/.icons/capitaine-cursors" ]; then
    run mkdir -p "$HOME/.icons" && record path "$HOME/.icons/capitaine-cursors" \
      && run ln -s "$dest" "$HOME/.icons/capitaine-cursors"
  fi
  # write the cursor (the one picked in Settings, else this default) into the files now, so the next login already
  # starts with it - i3 then needs no restart to pick it up (files only: the running session is not touched)
  if [ "$dry" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
    python3 "$cfg/i3/scripts/SettingsGUI.py" --cursor-files >/dev/null 2>&1 || true
  fi
}
install_cursor

# first login picks a wallpaper and generates colors (a re-install or update keeps your wallpaper)
[ "$first_install" -eq 1 ] && run rm -f "${XDG_CACHE_HOME:-$HOME/.cache}/i3/first-run-done" \
  "${XDG_STATE_HOME:-$HOME/.local/state}/i3wm-dots/first-run-done"

# ---- updates: a check for a newer config every 30 minutes (a notification; installing is up to you) ---------------
# (i3dots-update = ~/.config/i3/scripts/Update.sh; a line in your crontab asks it to check)
setup_updates() {
  local state="${XDG_DATA_HOME:-$HOME/.local/share}/i3wm-dots-updater" url=""
  if [ "$dry" -eq 1 ]; then
    say "would set up i3dots-update$( [ "$do_autoupdate" -eq 1 ] && [ "$do_packages" -eq 1 ] && echo " and its cron check")"
    return 0
  fi
  mkdir -p "$state" "$HOME/.local/bin"
  if [ "$update_mode" -eq 0 ]; then
    # where updates come from: the repo this was installed from (its GitHub address), else the main repo
    url="$(git -C "$here" config --get remote.origin.url 2>/dev/null || true)"
    case "$url" in https://*|git@*) ;; *) url="$REPO_URL" ;; esac
    printf '%s\n' "$url" >"$state/repo-url"
    git -C "$here" rev-parse HEAD >"$state/applied" 2>/dev/null || rm -f "$state/applied"
    [ "$do_autoupdate" -eq 1 ] && rm -f "$state/off"
    [ "$do_autoupdate" -eq 0 ] && : >"$state/off"
  fi
  ln -sfn "$cfg/i3/scripts/Update.sh" "$HOME/.local/bin/i3dots-update"
  # the uninstaller, as a copy that outlives ~/.config/i3:  i3dots-uninstall
  [ -f "$here/uninstall.sh" ] && install -m 755 "$here/uninstall.sh" "$HOME/.local/bin/i3dots-uninstall"
  [ "$update_mode" -eq 1 ] && return 0
  case ":$orig_path:" in
    *":$HOME/.local/bin:"*) ;;
    *) say "note: ~/.local/bin is not in your PATH - run the updater as ~/.local/bin/i3dots-update (or add that folder to PATH)" ;;
  esac
  if [ "$do_autoupdate" -eq 0 ]; then
    say "no update checks (update by hand with: i3dots-update)"
  elif [ "$do_packages" -eq 1 ] && [ "$FAMILY" != unknown ]; then
    say "setting up a check for a newer config (cron looks every 30 minutes)"
    bash "$cfg/i3/scripts/Update.sh" --install-hook || warn "could not set up the update check - run later: i3dots-update --install-hook"
  else
    say "to check for a newer config every 30 minutes, run once:  i3dots-update --install-hook"
  fi
}
setup_updates

# ---- sanity checks -----------------------------------------------------------------
if [ "$dry" -eq 0 ]; then
  # (no brightnessctl / pamixer here - Platform.sh asks the system's own tools; NetBSD: i3's bar for polybar)
  checks="i3 polybar picom dunst rofi feh maim xdotool xclip i3lock playerctl notify-send xrandr xprop"
  [ "$FAMILY" = netbsd ] && checks="i3 i3bar picom dunst rofi feh maim xdotool xclip i3lock notify-send xrandr xprop"
  for c in $checks; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
  done
  command -v ghostty >/dev/null 2>&1 || command -v kitty >/dev/null 2>&1 || missing+=("a terminal (ghostty or kitty)")
  command -v clipmenu >/dev/null 2>&1 || command -v copyq >/dev/null 2>&1 || missing+=("clipmenu or copyq")
  [ "$do_pokemon" -eq 0 ] || command -v fastfetch >/dev/null 2>&1 || missing+=("fastfetch (the Mimikyu greeting in the terminal)")
  if command -v i3 >/dev/null 2>&1; then
    ver="$(i3 --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -n1)"
    if [ -n "$ver" ] && awk -v v="$ver" 'BEGIN { split(v, a, "."); exit !(a[1] < 4 || (a[1] == 4 && a[2] < 22)) }'; then
      warn "i3 $ver is older than 4.22 - the 'gaps' lines in the config need >= 4.22 (update your packages)"
    fi
    if i3 -C -c "$cfg/i3/config" >/dev/null 2>&1; then say "i3 config validated OK"
    else warn "i3 rejected the config - see:  i3 -C -c ~/.config/i3/config"; fi
  fi
fi

# ---- summary -------------------------------------------------------------------------
if [ "$update_mode" -eq 1 ]; then
  say "config updated"
  exit 0
fi
if [ "${#missing[@]}" -gt 0 ]; then
  echo
  warn "could not be installed automatically: $(printf '%s\n' "${missing[@]}" | sort -u | tr '\n' ' ')"
  warn "install them manually, or the matching keybinds/modules will do nothing (log: ~/.cache/i3wm-dots-install.log)"
fi

case "$FAMILY" in
  freebsd) how="Log out and pick \"i3\" at the login screen (GhostBSD: the session menu), or type startx on a console." ;;
  openbsd) how="Log out: xenodm starts i3 through ~/.xsession (or type startx on a console)." ;;
  netbsd)  how="Log out: xdm starts i3 through ~/.xsession (or type startx on a console). The bar is i3's own here: NetBSD has no polybar package." ;;
  *)       how='Log out and choose the "i3" session at your login screen (or put "exec i3" in ~/.xinitrc).' ;;
esac
cat <<MSG

Done.  $how
  - SUPER+H shows every keybind.  SUPER+W picks a wallpaper.
  - SUPER+ALT+M opens Settings (mouse and touchpad gestures, displays, appearance and bar styles, accent colour,
    terminal themes, keybindings, sound, Bluetooth, Wi-Fi).
  - Terminal: Ghostty (kitty if Ghostty could not be installed). Change it in Settings > Keybindings (the terminal row).
  - New terminal windows greet you with the Mimikyu fastfetch and the black / grey / white prompt
    (bash and zsh; open a new terminal to see them).
  - Your old desktop is untouched - pick it again at the login screen any time.
  - Undo the dotfiles:  ./install.sh --restore
  - Remove it all again (the config, and if you want i3 and the programs it added):  ./uninstall.sh  or  i3dots-uninstall
  - Updates: you get a notification when a newer config is out on GitHub (cron looks every 30 minutes) - nothing
    changes until you run:  i3dots-update   (keeps your Settings; files you edited by hand are replaced - undo:
    i3dots-update --undo)   No more checks: i3dots-update --off

$SYSNAME notes: volume, brightness and battery use the system's own tools (mixer / sndioctl / mixerctl, backlight /
xbacklight, acpi / apm / envstat). Power off and suspend from the power menu need permission: join the operator
group (FreeBSD, NetBSD) or add a doas rule, e.g.  permit nopass :wheel cmd shutdown . The Sound, Bluetooth and Wi-Fi
tabs of the settings window and the touchpad swipes use Linux-only tools; the bar's items and the keys work without.
MSG
