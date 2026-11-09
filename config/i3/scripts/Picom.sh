#!/usr/bin/env bash
# Start the compositor. The config asks for the fast GPU backend (glx). On a software-only OpenGL driver
# (llvmpipe/softpipe: virtual machines without 3D) glx is slow and can draw windows black, so the software
# backend (xrender) is used there; and if glx cannot start at all, xrender is tried as a fallback.
command -v picom >/dev/null 2>&1 || exit 0
pgrep -u "$UID" -x picom >/dev/null && exit 0
conf="${XDG_CONFIG_HOME:-$HOME/.config}/picom/picom.conf"
if command -v glxinfo >/dev/null 2>&1; then
  case "$(timeout 5 glxinfo -B 2>/dev/null | grep -i 'renderer string')" in
    *llvmpipe*|*softpipe*|*"Software Rasterizer"*)
      exec picom --config "$conf" --backend xrender -b 2>/dev/null ;;
  esac
fi
picom --config "$conf" -b 2>/dev/null
sleep 1
pgrep -u "$UID" -x picom >/dev/null && exit 0
picom --config "$conf" --backend xrender -b 2>/dev/null
