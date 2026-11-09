#!/usr/bin/env python3
"""Print the keybind tables for README.md from config/i3/config (every bindsym with its "## description").

    python3 tools/make_readme_keys.py > /tmp/keys.md      (then paste it into the Keybinds section of README.md)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config", "i3", "config")

SECTION_TITLES = {                      # config section header -> README heading
    "apps / launchers": "Apps",
    "wallpaper / look toggles": "Look",
    "session": "Session",
    "screenshots (maim)": "Screenshots",
    "window / layout": "Windows",
    "workspaces": "Workspaces",
    "media / hardware keys (holding a key repeats)": "Media",
}
KEY_NAMES = {
    "$mod": "SUPER", "$alt": "ALT", "Mod4": "SUPER", "Mod1": "ALT", "Ctrl": "CTRL", "Control": "CTRL", "Shift": "SHIFT",
    "Return": "Enter", "space": "Space", "Escape": "Esc", "Tab": "Tab", "Print": "Print", "Delete": "Delete",
    "period": ".", "comma": ",", "bracketleft": "[", "bracketright": "]", "minus": "-", "equal": "=", "plus": "+",
    "grave": "`", "slash": "/", "backslash": "\\", "semicolon": ";", "apostrophe": "'",
    "KP_Add": "Numpad +", "KP_Subtract": "Numpad -", "button4": "scroll up", "button5": "scroll down",
    "Left": "←", "Right": "→", "Up": "↑", "Down": "↓",
    "XF86AudioRaiseVolume": "Volume up key", "XF86AudioLowerVolume": "Volume down key", "XF86AudioMute": "Mute key",
    "XF86AudioMicMute": "Mic mute key", "XF86AudioPlay": "Play key", "XF86AudioPause": "Pause key",
    "XF86AudioNext": "Next track key", "XF86AudioPrev": "Previous track key", "XF86AudioStop": "Stop key",
    "XF86MonBrightnessUp": "Brightness up key", "XF86MonBrightnessDown": "Brightness down key",
    "XF86KbdBrightnessUp": "Keyboard light up key", "XF86KbdBrightnessDown": "Keyboard light down key",
    "XF86KbdLightOnOff": "Keyboard light key", "XF86TouchpadToggle": "Touchpad key", "XF86WLAN": "Wi-Fi key",
    "XF86RFKill": "Airplane key", "XF86Sleep": "Sleep key", "XF86Calculator": "Calculator key",
}


def nice_key(combo):
    parts = []
    for p in combo.split("+"):
        if p in KEY_NAMES:
            parts.append(KEY_NAMES[p])
        elif len(p) == 1:
            parts.append(p.upper())
        else:
            parts.append(p)
    return " + ".join(parts)


def main():
    lines = open(CONFIG, encoding="utf-8").read().split("\n")
    section, desc, rows = None, None, []
    for line in lines:
        m = re.match(r"^# ---- (.+?) -+\s*$", line)
        if m:
            section = m.group(1)
            continue
        m = re.match(r"^##\s*(.+?)\s*$", line)
        if m:
            desc = m.group(1)
            continue
        m = re.match(r"^bindsym(?:\s+--\S+)*\s+(\S+)\s+", line)
        if m and section in SECTION_TITLES:
            rows.append((section, m.group(1), desc or ""))
        if line.strip():
            desc = None                 # a description belongs to the bindsym right below it
    # fold numbered series (workspace 1 ... workspace 10) into one row
    out, i = [], 0
    while i < len(rows):
        sec, key, d = rows[i]
        m = re.match(r"^(.*\+)([1-9])$", key)
        dm = re.match(r"^(.*?)\b1\b(.*)$", d)
        if m and m.group(2) == "1" and dm:
            j = i
            while (j + 1 < len(rows) and rows[j + 1][0] == sec
                   and re.match(r"^" + re.escape(m.group(1)) + r"[0-9]$", rows[j + 1][1])):
                j += 1
            if j - i >= 8:
                out.append((sec, "%s1 … %s0" % (m.group(1), m.group(1)), "%s1 - 10%s" % (dm.group(1), dm.group(2))))
                i = j + 1
                continue
        out.append(rows[i])
        i += 1
    current = None
    for sec, key, d in out:
        if sec != current:
            if current is not None:
                print()
            print("### %s\n" % SECTION_TITLES[sec])
            print("| Key | Action |\n|---|---|")
            current = sec
        k = nice_key(key.split(" … ")[0]) + (" … 0" if " … " in key else "")
        print("| `%s` | %s |" % (k, d[0].upper() + d[1:] if d else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
