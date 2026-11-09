#!/usr/bin/env bash
# asciiquarium with a see-through background: the terminal's own (see-through) background behind the fish instead
# of a black box (perl/I3dotsAquarium.pm). The shell's "asciiquarium" runs this (an alias the installer adds).
here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
real=""
IFS=: read -ra dirs <<<"$PATH"
for d in "${dirs[@]}" /usr/local/bin /usr/pkg/bin /usr/games; do
  if [ -x "$d/asciiquarium" ] && [ "$(readlink -f "$d/asciiquarium")" != "$(readlink -f "${BASH_SOURCE[0]}")" ]; then
    real="$d/asciiquarium"; break
  fi
done
[ -n "$real" ] || { echo "asciiquarium is not installed (FreeBSD: sudo pkg install asciiquarium   OpenBSD: doas pkg_add asciiquarium   NetBSD: pkgin install asciiquarium)" >&2; exit 127; }
# if the helper cannot be loaded (another asciiquarium version), run it as it is
if PERL5LIB="$here/perl${PERL5LIB:+:$PERL5LIB}" perl -MI3dotsAquarium -e 1 2>/dev/null; then
  export PERL5LIB="$here/perl${PERL5LIB:+:$PERL5LIB}" PERL5OPT="-MI3dotsAquarium${PERL5OPT:+ $PERL5OPT}"
fi
exec "$real" "$@"
