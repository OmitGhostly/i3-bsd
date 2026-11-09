#!/usr/bin/env bash
# GPU usage % for polybar. NVIDIA (nvidia-smi), AMD (sysfs), Intel (best effort via frequency).
# Prints nothing if no GPU sensor is found, so the module simply disappears.
icon="󰢮"
if command -v nvidia-smi >/dev/null 2>&1; then
  u=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr -d ' ')
  [ -n "$u" ] && { echo "$icon GPU ${u}%"; exit 0; }
fi
for f in /sys/class/drm/card*/device/gpu_busy_percent; do
  [ -r "$f" ] && { echo "$icon GPU $(cat "$f")%"; exit 0; }
done
for d in /sys/class/drm/card*; do
  cur="$d/gt_cur_freq_mhz"; max="$d/gt_max_freq_mhz"
  if [ -r "$cur" ] && [ -r "$max" ]; then
    echo "$icon GPU $(( $(cat "$cur") * 100 / $(cat "$max") ))%"; exit 0
  fi
done
exit 0
