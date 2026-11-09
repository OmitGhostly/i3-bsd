# Sourced by the scripts (". .../compat.sh"): stand-ins for the commands FreeBSD (GhostBSD), OpenBSD and NetBSD do
# not have (flock, setsid), and small helpers they share. A real command is used as it is where there is one.

# flock: FreeBSD and OpenBSD have none - FdLock.py takes the same lock (no python either: carry on without a lock)
if ! command -v flock >/dev/null 2>&1; then
  flock() {
    if command -v python3 >/dev/null 2>&1; then
      python3 "${XDG_CONFIG_HOME:-$HOME/.config}/i3/scripts/FdLock.py" "$@"
    else
      return 0
    fi
  }
fi

# setsid: not on the BSDs; started with "&" the program carries on after the script anyway
command -v setsid >/dev/null 2>&1 || setsid() { "$@"; }

# sed_inplace SED-ARGUMENTS... FILE: edit a file in place with any sed (GNU sed -i, BSD sed -i '', ...), keeping the
# file itself (its permissions, a symlink to it). Fails, and leaves the file alone, if sed fails.
sed_inplace() {
  _f=$(eval "printf '%s' \"\${$#}\"")
  _n=$(($# - 1))
  _args=""
  _i=1
  while [ "$_i" -le "$_n" ]; do _args="$_args \"\${$_i}\""; _i=$((_i + 1)); done
  _t="$_f.i3dots-tmp.$$"
  if eval "sed $_args \"\$_f\"" >"$_t" 2>/dev/null; then
    cat "$_t" >"$_f" && rm -f "$_t"
  else
    rm -f "$_t"
    return 1
  fi
}

# pick_random: one line of standard input at random (shuf -n1 is GNU only)
pick_random() { awk -v s="$$" 'BEGIN { srand(); t = srand(); srand(s + t) } { a[NR] = $0 } END { if (NR) print a[int(rand() * NR) + 1] }'; }
