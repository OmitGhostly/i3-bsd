#!/usr/bin/env bash
# Monochrome fastfetch with a shiny Mimikyu sprite from acxz/pokescript (https://github.com/acxz/pokescript).
# A small (half-height) copy of the sprite ships with the config and is shown by default; the large one comes from
# the pokescript clone the installer makes (a copy of that ships too).
cfgdir="${XDG_CONFIG_HOME:-$HOME/.config}"
cfg="$cfgdir/fastfetch/config-pokemon.jsonc"
command -v fastfetch >/dev/null || exit 0
# Greet only once per terminal window, no matter how many times this is called (a duplicated line in .zshrc,
# a shell that restarts itself, a prompt theme that re-reads the rc file...). The key is the terminal's session.
# (OpenBSD's ps has no "sid": its "sess" names the session too)
sid=$(ps -o sid= -p $$ 2>/dev/null | tr -d ' ')
started=""
if [ -n "$sid" ] && [ "$sid" != 0 ]; then
  started=$(ps -o lstart= -p "$sid" 2>/dev/null | tr -c 'A-Za-z0-9' '_')
else
  sid=$(ps -o sess= -p $$ 2>/dev/null | tr -cd 'A-Za-z0-9')
fi
if [ -n "$sid" ]; then
  lockdir="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/i3dots-pokefetch-$UID"
  mkdir -p "$lockdir" 2>/dev/null && chmod 700 "$lockdir" 2>/dev/null
  find "$lockdir" -type f -mtime +1 -delete 2>/dev/null
  mark="$lockdir/$sid-$started"
  [ -e "$mark" ] && exit 0
  : > "$mark"
fi
# The small sprite (half-height blocks, about a quarter of the size) is the default; set I3DOTS_POKEFETCH_SIZE=large
# (e.g. in ~/.zshrc) for the big pokescript one.
small="$cfgdir/fastfetch/shiny-mimikyu-small.txt"
if [ "${I3DOTS_POKEFETCH_SIZE:-small}" = large ]; then
  sprites=("${POKESCRIPT_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/pokescript}/colorscripts/shiny/mimikyu.txt"
           "$cfgdir/fastfetch/shiny-mimikyu.txt" "$small")
else
  sprites=("$small" "$cfgdir/fastfetch/shiny-mimikyu.txt")
fi
for sprite in "${sprites[@]}"; do
  if [ -r "$sprite" ]; then
    # file-raw logos need their size: rows = lines, columns = widest line without colour codes (each block = 1 column)
    h=$(wc -l < "$sprite")
    esc=$(printf '\033')
    w=$(sed "s/${esc}\\[[0-9;]*m//g; s/█/X/g; s/▀/X/g; s/▄/X/g" "$sprite" | awk '{ if (length($0) > m) m = length($0) } END { print m + 0 }')
    exec fastfetch -c "$cfg" --logo-type file-raw --logo "$sprite" --logo-width "$w" --logo-height "$h" --logo-padding-right 3 2>/dev/null
  fi
done
exec fastfetch -c "$cfg"
