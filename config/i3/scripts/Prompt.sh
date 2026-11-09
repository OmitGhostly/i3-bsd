# shellcheck shell=bash
# i3wm-dots prompt: white, grey and black blocks with rounded ends - the same look as the bar - for bash and zsh.
#
#     user@host   ~/folder   branch   ❯          (the last block shows the exit code when a command failed)
#
# ~/.bashrc and ~/.zshrc load this file (the installer adds one line). It stays out of the way when another prompt
# theme is in charge (starship, an oh-my-zsh / oh-my-bash theme, powerlevel10k) and on the text console.
# Turn it off:  export I3DOTS_PROMPT=off      (put it above the i3wm-dots line in ~/.bashrc or ~/.zshrc)
case $- in *i*) ;; *) return 0 ;; esac
case "${I3DOTS_PROMPT:-on}" in off|0|no|false) return 0 ;; esac
case "${TERM:-dumb}" in dumb|linux|vt*) return 0 ;; esac
[ -n "${STARSHIP_SHELL:-}" ] && return 0

# The rounded ends and icons need the Nerd Font that the Ghostty and kitty configs use; elsewhere (an ssh login,
# another terminal) the blocks are drawn square and without icons.
if [ "${TERM_PROGRAM:-}" = ghostty ] || [ -n "${KITTY_WINDOW_ID:-}" ] || [ "${I3DOTS_PROMPT:-}" = nerd ]; then
  __i3dots_nerd=1
  __i3dots_icons=($' ' $' ' $' ' $' ')     # user, folder, branch, failed
  __i3dots_shapes=($'' $'' $'')                  # left end, joint / right end, arrow
else
  __i3dots_nerd=0
  __i3dots_icons=('' '' '' 'x ')
  __i3dots_shapes=('' '' '>')
fi
if [ -n "${ZSH_VERSION:-}" ]; then __i3dots_o=1; else __i3dots_o=0; fi    # zsh arrays start at 1
__i3dots_icon() { REPLY="${__i3dots_icons[$(( $1 + __i3dots_o ))]}"; }
__i3dots_shape() { REPLY="${__i3dots_shapes[$(( $1 + __i3dots_o ))]}"; }

# the git branch of the current folder, in REPLY - read straight from .git, so no git process runs per prompt
__i3dots_branch() {
  local d="$PWD" g="" h=""
  REPLY=""
  while [ -n "$d" ]; do
    if [ -e "$d/.git" ]; then g="$d/.git"; break; fi
    d="${d%/*}"
  done
  [ -n "$g" ] || return 1
  if [ -f "$g" ]; then                                  # a worktree or submodule: ".git" is a file pointing elsewhere
    [ -r "$g" ] || return 1
    read -r h <"$g"
    h="${h#gitdir: }"
    case "$h" in /*) g="$h" ;; *) g="$d/$h" ;; esac
  fi
  [ -r "$g/HEAD" ] || return 1
  read -r h <"$g/HEAD"
  case "$h" in
    "ref: refs/heads/"*) REPLY="${h#ref: refs/heads/}" ;;
    "ref: "*) REPLY="${h#ref: }" ;;
    *) REPLY="${h:0:7}" ;;                              # detached: the short commit id
  esac
  [ -n "$REPLY" ]
}

# __i3dots_build OPEN CLOSE  BG FG TEXT  [BG FG TEXT ...]  -> the prompt string in REPLY
# (OPEN / CLOSE mark the colour codes as zero-width: \[ \] for bash, %{ %} for zsh; colours are 256-colour numbers)
__i3dots_build() {
  local o="$1" c="$2" e=$'\033' out="" prev="" bg fg txt cap joint arrow
  shift 2
  __i3dots_shape 0; cap="$REPLY"; __i3dots_shape 1; joint="$REPLY"; __i3dots_shape 2; arrow="$REPLY"
  while [ $# -ge 3 ]; do
    bg="$1" fg="$2" txt="$3"
    shift 3
    if [ -z "$prev" ]; then
      [ "$__i3dots_nerd" = 1 ] && out="$o${e}[0;38;5;${bg}m$c$cap"
    elif [ "$__i3dots_nerd" = 1 ]; then
      out="$out$o${e}[0;38;5;${prev};48;5;${bg}m$c$joint"
    fi
    out="$out$o${e}[0;38;5;${fg};48;5;${bg}m$c ${txt} "
    prev="$bg"
  done
  if [ "$__i3dots_nerd" = 1 ]; then out="$out$o${e}[0;38;5;${prev}m$c$joint"; else out="$out$o${e}[0m$c"; fi
  REPLY="$out$o${e}[0;1;38;5;255m$c ${arrow}$o${e}[0m$c "
}

if [ -n "${BASH_VERSION:-}" ]; then
  [ -n "${OSH_THEME:-}" ] && return 0                 # oh-my-bash has a theme
  PROMPT_DIRTRIM=3
  __i3dots_ps1() {
    local rc=$? iu id ib ie
    local -a s
    __i3dots_icon 0; iu="$REPLY"; __i3dots_icon 1; id="$REPLY"; __i3dots_icon 2; ib="$REPLY"; __i3dots_icon 3; ie="$REPLY"
    s=(255 16 "$iu"'\u@\h' 248 16 "$id"'\w')
    # the branch goes in as ${__i3dots_b}: bash fills it in when it draws the prompt but never runs what is in it,
    # so a branch named like a command stays plain text
    if __i3dots_branch && shopt -q promptvars; then __i3dots_b="$REPLY"; s+=(240 255 "$ib"'${__i3dots_b}'); fi
    [ "$rc" -ne 0 ] && s+=(255 16 "$ie$rc")
    __i3dots_build '\[' '\]' "${s[@]}"
    PS1="$REPLY"
    return $rc                                          # keep $? for whatever else runs before the prompt
  }
  case ";${PROMPT_COMMAND:-};" in
    *";__i3dots_ps1;"*) ;;
    *) PROMPT_COMMAND="__i3dots_ps1${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
  esac
elif [ -n "${ZSH_VERSION:-}" ]; then
  [ -n "${ZSH_THEME:-}" ] && [ -n "${ZSH:-}" ] && return 0    # oh-my-zsh has a theme
  (( ${+functions[p10k]} )) && return 0                         # powerlevel10k
  setopt prompt_subst
  autoload -Uz add-zsh-hook
  __i3dots_precmd() {
    local rc=$? iu id ib ie
    local -a s
    __i3dots_icon 0; iu="$REPLY"; __i3dots_icon 1; id="$REPLY"; __i3dots_icon 2; ib="$REPLY"; __i3dots_icon 3; ie="$REPLY"
    s=(255 16 "${iu}%n@%m" 248 16 "${id}%3~")
    # the branch is filled in from ${__i3dots_b} (never run); a % in it is doubled so it cannot change the prompt
    if __i3dots_branch; then __i3dots_b="${REPLY//\%/%%}"; s+=(240 255 "${ib}"'${__i3dots_b}'); fi
    (( rc != 0 )) && s+=(255 16 "${ie}${rc}")
    __i3dots_build '%{' '%}' "${s[@]}"
    # shellcheck disable=SC2034 # (zsh reads PROMPT)
    PROMPT="$REPLY"
  }
  add-zsh-hook precmd __i3dots_precmd
fi
