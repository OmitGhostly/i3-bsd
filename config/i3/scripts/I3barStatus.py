#!/usr/bin/env python3
"""The items on the right of i3's own bar (i3bar), used where polybar is not installed - NetBSD has no package of it
(polybar/launch.sh then turns i3bar on). The same items as polybar's, in the same order and with the same clicks:
Wi-Fi, volume, brightness, stay awake, night light, battery, CPU, memory, GPU, the date and the power button.
The values come from Platform.sh (and the scripts polybar runs).
Speaks i3bar's protocol on standard output and reads the clicks from standard input."""
import json
import os
import re
import select
import shlex
import subprocess
import sys
import time

CFG = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
SCRIPTS = os.path.join(CFG, "i3", "scripts")
STATE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"),
                     "i3wm-dots")
DEFAULT_ITEMS = ["network", "pulseaudio", "backlight", "caffeine", "nightlight", "battery", "cpu", "memory", "date",
                 "powermenu"]
# items Platform.sh measures, and its name for each
PLATFORM = {"network": "network", "pulseaudio": "volume", "backlight": "backlight", "battery": "battery",
            "cpu": "cpu", "memory": "memory"}
# items a script of their own prints (the one polybar runs)
SCRIPT = {"caffeine": ["Caffeine.sh", "status"], "nightlight": ["Nightlight.sh", "status"], "gpu": ["PolybarGpu.sh"],
          "bluetooth": ["PolybarBluetooth.sh"], "playerctl": ["PolybarPlayer.sh"]}
# (item, mouse button) -> what to run: 1 left, 3 right, 4 scroll up, 5 scroll down
CLICKS = {("pulseaudio", 1): ["Volume.sh", "--toggle"], ("pulseaudio", 3): ["SettingsGUI.py", "--tab", "sound"],
          ("pulseaudio", 4): ["Volume.sh", "--inc"], ("pulseaudio", 5): ["Volume.sh", "--dec"],
          ("backlight", 4): ["Brightness.sh", "--inc"], ("backlight", 5): ["Brightness.sh", "--dec"],
          ("network", 1): ["SettingsGUI.py", "--tab", "wifi"],
          ("caffeine", 1): ["Caffeine.sh", "toggle"], ("nightlight", 1): ["Nightlight.sh", "toggle"],
          ("bluetooth", 1): ["BluetoothToggle.sh"], ("bluetooth", 3): ["SettingsGUI.py", "--tab", "bluetooth"],
          ("playerctl", 1): ["@playerctl", "play-pause"], ("playerctl", 3): ["@playerctl", "next"],
          ("powermenu", 1): ["Powermenu.sh"]}
TAGS = re.compile(r"%\{[^}]*\}")


def items():
    """The bar's items, as the settings window last chose them for polybar (launch.sh keeps that in bar-env)."""
    try:
        with open(os.path.join(STATE, "bar-env"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("BAR_RIGHT="):
                    # (BAR_RIGHT='a b c': unquote the shell word, then one item per name)
                    names = " ".join(shlex.split(line.split("=", 1)[1])).split()
                    # (a bar saved before the BSD version had its own repo named them network-sys, cpu-sys ...)
                    got = [m[:-4] if m.endswith("-sys") else m for m in names]
                    return [m for m in got if m != "tray"] or DEFAULT_ITEMS
    except (OSError, ValueError):
        pass
    return DEFAULT_ITEMS


def clock_format():
    """24-hour or 12-hour, as chosen in Settings > Appearance (launch.sh keeps it in bar-env)."""
    try:
        with open(os.path.join(STATE, "bar-env"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("BAR_TIME="):
                    v = " ".join(shlex.split(line.split("=", 1)[1]))
                    if v in ("%H:%M", "%I:%M %p"):
                        return v
    except (OSError, ValueError):
        pass
    return "%H:%M"


def accent():
    """(colour, text colour on it) from Settings > Colors."""
    a = "ffffff"
    try:
        with open(os.path.join(CFG, "i3", "accent.conf"), encoding="utf-8") as f:
            m = re.search(r"^ACCENT=([0-9a-fA-F]{6})\s*$", f.read(), re.M)
            a = m.group(1) if m else a
    except OSError:
        pass
    r, g, b = (int(a[i:i + 2], 16) for i in (0, 2, 4))
    return "#" + a, "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def texts(wanted):
    out = {}
    plat = [PLATFORM[m] for m in wanted if m in PLATFORM]
    if plat:
        for line in run(["sh", os.path.join(SCRIPTS, "Platform.sh"), "plain"] + plat + ["_"]).splitlines():
            name, _tab, text = line.partition("\t")
            out[name] = text.strip()
    res = {}
    for m in wanted:
        if m in PLATFORM:
            res[m] = out.get(PLATFORM[m], "")
        elif m in SCRIPT:
            res[m] = TAGS.sub("", run([os.path.join(SCRIPTS, SCRIPT[m][0])] + SCRIPT[m][1:]).strip().split("\n")[0])
        elif m == "date":
            res[m] = time.strftime("%a %d %b  " + clock_format())
        elif m == "powermenu":
            res[m] = "󰐥"
    return res


def blocks(wanted, colours):
    acc, on_acc = colours
    t = texts(wanted)
    out = []
    for m in wanted:
        text = t.get(m, "")
        if not text:
            continue                                    # (nothing to show: no block, like polybar)
        strong = m in ("date", "powermenu")
        out.append({"name": m, "full_text": " %s " % text, "color": on_acc if strong else "#e6e6e6",
                    "background": acc if strong else "#303030", "border": acc if strong else "#303030",
                    "separator": False, "separator_block_width": 6, "markup": "none"})
    return out


def click(event):
    cmd = CLICKS.get((event.get("name"), event.get("button")))
    if not cmd:
        return
    cmd = [cmd[0][1:]] + cmd[1:] if cmd[0].startswith("@") else [os.path.join(SCRIPTS, cmd[0])] + cmd[1:]
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def main():
    out = sys.stdout
    first, buf = True, ""
    wanted, colours, last_conf = items(), accent(), time.monotonic()
    while True:
        if time.monotonic() - last_conf > 30:          # (a changed choice of items or colour shows within 30 s)
            wanted, colours, last_conf = items(), accent(), time.monotonic()
        line = json.dumps(blocks(wanted, colours)) + "\n"
        # (the header goes out together with the first items: i3bar's first frame already shows them)
        out.write(json.dumps({"version": 1, "click_events": True}) + "\n[\n" + line if first else "," + line)
        out.flush()
        first = False
        end = time.monotonic() + 2
        while True:
            left = end - time.monotonic()
            if left <= 0:
                break
            ready, _, _ = select.select([sys.stdin], [], [], left)
            if not ready:
                break
            chunk = os.read(sys.stdin.fileno(), 4096).decode("utf-8", "replace")
            if not chunk:                               # i3bar is gone
                return 0
            buf += chunk
            clicked = False
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip().lstrip("[,").strip()
                if line.startswith("{"):
                    try:
                        click(json.loads(line))
                        clicked = True
                    except ValueError:
                        pass
            if clicked:
                time.sleep(0.3)                         # let the change happen, then show it
                break


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BrokenPipeError, KeyboardInterrupt):
        sys.exit(0)
