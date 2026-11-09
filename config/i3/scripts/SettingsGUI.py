#!/usr/bin/env python3
"""i3wm-dots settings window: network (Wi-Fi, Ethernet, IP and DNS, VPN, proxy), Bluetooth, sound, displays
(resolution, refresh rate, orientation, scale, layout), appearance (window/terminal opacity, gaps, tiling, bar),
accent colour, terminal themes, mouse (touchpad gestures, cursor) and keybindings.

  SettingsGUI.py            open the settings window
  SettingsGUI.py --bar-env  print the saved bar settings as shell variables and write polybar/style.ini
                            (used by polybar/launch.sh)
  SettingsGUI.py --apply    apply the saved settings (run at every i3 start, no GTK needed)
  SettingsGUI.py --refresh-files  write the saved settings into the config files only (used by install.sh)
  SettingsGUI.py --cursor-files   write the cursor (the default one if none is saved) into the files only (install.sh)
  SettingsGUI.py --apply-mouse    apply only the mouse / touchpad settings (used by InputWatch.py)
  SettingsGUI.py --gestures print "on" or "off": are the touchpad swipe gestures switched on (used by Gestures.sh)
  SettingsGUI.py --wifi-icon  print "on" or "off": show the Wi-Fi applet's tray icon (used by NetApplet.sh)
  SettingsGUI.py --dry-run  with --apply: print the commands instead of running them
  SettingsGUI.py --i3bar-conf  print i3's own bar for the chosen bar (used where polybar is not installed)
  SettingsGUI.py --tab NAME open on a page: network (or wifi ethernet vpn proxy) bluetooth sound displays
                            appearance colors themes mouse keybindings

Changes are saved to ~/.config/i3/settings.json and applied immediately.
No root needed.  Requires: python3, python3-gobject (GTK 3), xinput, xrandr (pactl / bluetoothctl / nmcli for those tabs).
"""
import json
import os
import glob
import ipaddress
import math
import re
import shlex
import shutil
import subprocess
import sys

CONFIG_DIR = os.path.join((os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")), "i3")
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
# FreeBSD (GhostBSD too), OpenBSD or NetBSD: some things work differently on each (the tests set I3DOTS_OS)
SYSTEM = (os.environ.get("I3DOTS_OS") or os.uname().sysname).lower()
SYSTEM = SYSTEM if SYSTEM in ("openbsd", "netbsd") else "freebsd"
SETTINGS_FILE = os.environ.get("I3DOTS_SETTINGS", os.path.join(CONFIG_DIR, "settings.json"))
ALL = "__all__"          # key used for "all mice and touchpads"
ROTATIONS = [("normal", "Landscape"), ("left", "Portrait (left)"),
             ("right", "Portrait (right)"), ("inverted", "Landscape (flipped)")]
SCALES = [100, 125, 150, 175, 200, 250, 300]     # screen scale in percent
DRY = False
FILES_ONLY = False       # --refresh-files: write the config files, but run nothing (no reloads, no X changes)


# ------------------------------------------------------------------ helpers
def run(cmd, check=False):
    """Run a command list; in dry-run mode just print it."""
    if DRY:
        print("+", " ".join(shlex.quote(c) for c in cmd))
        return ""
    if FILES_ONLY:
        return ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        if check:
            raise
        return ""
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "command failed: " + " ".join(cmd))
    return r.stdout


def query(cmd):
    """Read-only command, always executed (also in dry-run mode)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
    except OSError:
        data = {}
    except ValueError:
        # not readable (a hand edit gone wrong...): the defaults are used, and a copy is kept, since the next save
        # writes over it
        data = {}
        damaged = SETTINGS_FILE + ".damaged"
        if not os.path.exists(damaged) and not DRY:
            try:
                shutil.copy2(SETTINGS_FILE, damaged)
            except OSError:
                pass
    if not isinstance(data, dict):
        data = {}
    # a hand-edited or damaged file must never crash the login-time apply: wrong types are dropped
    for key in ("mouse", "monitors", "opacity", "gaps", "bar", "cursor", "apps", "keybinds", "themes", "colors", "tiling", "sound",
                "terminal_font", "gestures", "network", "proxy"):
        if key in data and not isinstance(data[key], dict):
            del data[key]
    sanitize_settings(data)
    data.setdefault("mouse", {})
    data.setdefault("monitors", {})
    return data


def _num(v, lo, hi, kind=int):
    """v as a number clamped to [lo, hi], or None when it is not a usable number."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        return None
    return max(lo, min(hi, kind(v)))


def sanitize_settings(data):
    """Keep only well-formed values: a hand-edited or damaged settings.json can never crash the window,
    reach a config file or a command. Anything unexpected is dropped and the default is used instead."""
    def clean(key, fn):
        if key in data:
            data[key] = fn(data[key])

    def mouse(m):
        out = {}
        for name, c in m.items():
            if isinstance(name, str) and isinstance(c, dict):
                out[name] = mouse_config(c)
        return out

    def monitors(m):
        out = {}
        for name, c in m.items():
            if not (isinstance(name, str) and isinstance(c, dict)):
                continue
            o = {}
            if isinstance(c.get("enabled"), bool):
                o["enabled"] = c["enabled"]
            if isinstance(c.get("mode"), str) and re.fullmatch(r"\d{2,5}x\d{2,5}", c["mode"]):
                o["mode"] = c["mode"]
            if isinstance(c.get("rate"), str) and re.fullmatch(r"\d{1,3}(\.\d{1,3})?", c["rate"]):
                o["rate"] = c["rate"]
            if c.get("rotate") in [r for r, _ in ROTATIONS]:
                o["rotate"] = c["rotate"]
            if c.get("scale") in SCALES and not isinstance(c.get("scale"), bool):
                o["scale"] = int(c["scale"])
            if isinstance(c.get("primary"), bool):
                o["primary"] = c["primary"]
            x, y = _num(c.get("x"), -32768, 32767), _num(c.get("y"), -32768, 32767)
            if x is not None and y is not None:
                o["x"], o["y"] = x, y
            out[name] = o
        return out

    def opacity(c):
        out = {}
        for k in ("active", "inactive", "terminal"):
            v = _num(c.get(k), -1e9, 1e9)
            if v is not None and 20 <= v <= 100:      # out of range = damaged: use the default, not the extreme
                out[k] = v
        return out

    def gaps(c):
        out = {}
        for k in ("inner", "outer"):
            v = _num(c.get(k), 0, 100)
            if v is not None:
                out[k] = v
        if isinstance(c.get("smart"), bool):
            out["smart"] = c["smart"]
        return out

    def bar(c):
        out = {}
        if c.get("position") in ("top", "bottom"):
            out["position"] = c["position"]
        size, style, divider = (c.get(k) if isinstance(c.get(k), str) else None for k in ("size", "style", "divider"))
        style = BAR_STYLE_ALIASES.get(style, style)       # (only strings get here: a list would not hash)
        if size in BAR_SIZES:
            out["size"] = size
        if style in dict(BAR_STYLES):
            out["style"] = style
        if divider in dict(BAR_DIVIDERS):
            out["divider"] = divider
        for k in ("title", "media"):
            if isinstance(c.get(k), bool):
                out[k] = c[k]
        if _num(c.get("spacing"), 0, BAR_SPACING_MAX) is not None:
            out["spacing"] = clean_spacing(c["spacing"])
        if isinstance(c.get("bg_mode"), str) and c["bg_mode"] in dict(BAR_BG_MODES):
            out["bg_mode"] = c["bg_mode"]
        if _num(c.get("bg_opacity"), 0, 100) is not None:
            out["bg_opacity"] = _num(c["bg_opacity"], 0, 100)
        if norm_accent(c.get("bg_color")):
            out["bg_color"] = norm_accent(c["bg_color"])
        mons = c.get("monitors")
        if isinstance(mons, list) and mons and all(isinstance(n, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", n) for n in mons):
            out["monitors"] = mons
        else:
            out["monitors"] = None
        return out

    def cursor(c):
        out = {}
        if isinstance(c.get("theme"), str) and re.fullmatch(r"[A-Za-z0-9 ._+-]{1,80}", c["theme"]):
            out["theme"] = c["theme"]
        sz = _num(c.get("size"), 8, 256)
        if sz is not None:
            out["size"] = sz
        return out

    def apps(c):
        return {k: v for k, v in c.items() if k in APP_SLOTS and isinstance(v, str) and SAFE_CMD.match(v)}

    def keybinds(c):
        out = {}
        for bid, o in c.items():
            if isinstance(bid, str) and isinstance(o, dict) and isinstance(o.get("key"), str) and KEY_RE.match(o["key"]):
                d = o.get("default")
                new_id = BIND_ID_RENAMED.get(bid, bid)        # (a bind whose command changed keeps its key)
                if new_id != bid and new_id in c:
                    continue
                out[new_id] = {"key": o["key"], "default": d if isinstance(d, str) and KEY_RE.match(d) else o["key"]}
        return out

    def themes(c):
        return {k: v for k, v in c.items() if k in ("ghostty", "kitty") and isinstance(v, str)
                and re.fullmatch(r"[^\"\\\n\r]{1,80}", v)}

    def terminal_font(c):
        out = {}
        for k in ("ghostty", "kitty"):
            v = clean_font_size(c.get(k))
            if v:
                out[k] = v
        return out

    def sound(c):
        return {k: c[k] for k in ("volume_feedback", "screenshot_sound") if isinstance(c.get(k), bool)}

    def tiling(c):
        return {"mode": c["mode"]} if c.get("mode") in TILING_MODES else {}

    def gestures(c):
        return {k: c[k] for k in GESTURES_DEFAULT if isinstance(c.get(k), bool)}

    def network(c):
        return {"tray_icon": c["tray_icon"]} if isinstance(c.get("tray_icon"), bool) else {}

    def proxy(c):
        return proxy_choice({"proxy": c})

    def colors(c):
        a = norm_accent(c.get("accent"))
        return {"accent": a} if a and brightness(a) >= ACCENT_MIN_BRIGHT else {}

    for key, fn in (("mouse", mouse), ("monitors", monitors), ("opacity", opacity), ("gaps", gaps), ("bar", bar),
                    ("cursor", cursor), ("apps", apps), ("keybinds", keybinds), ("themes", themes), ("colors", colors), ("tiling", tiling), ("sound", sound), ("terminal_font", terminal_font),
                    ("gestures", gestures), ("network", network), ("proxy", proxy)):
        clean(key, fn)
    return data


def save_settings(data):
    """Write settings.json in one piece: a new file, on the disk (a power cut can never leave it half written or
    empty), then swapped in."""
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, SETTINGS_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------ mouse
XINPUT_DEVICE_RE = re.compile(r"^[\s\u23a1\u23a2\u23a3\u239c\u21b3~]*(.+?)\s+id=(\d+)\s+\[slave\s+pointer")


def xinput_props(dev):
    """{property: [values]} of one xinput device (an id)."""
    props = {}
    for line in query(["xinput", "list-props", dev]).splitlines():
        m = re.match(r"^\s+(.+?) \(\d+\):\s*(.*)$", line)
        if m:
            props[m.group(1)] = [v.strip() for v in m.group(2).split(",")]
    return props


def list_pointers():
    """[(id, name, properties)] of the mice, touchpads and trackballs that have libinput acceleration settings.
    By id, not name: a wireless receiver often shows up as a keyboard and a mouse with the same name, and xinput
    refuses a name that matches two devices."""
    out = []
    for line in query(["xinput", "list", "--short"]).splitlines():
        m = XINPUT_DEVICE_RE.match(line)
        if not m or m.group(1).startswith("Virtual core") or "XTEST" in m.group(1):
            continue
        props = xinput_props(m.group(2))
        if "libinput Accel Speed" in props:
            out.append((m.group(2), m.group(1), props))
    return out


def list_pointer_devices():
    """Names of the mice and touchpads (each name once), for the settings window."""
    names = []
    for _dev, name, _props in list_pointers():
        if name not in names:
            names.append(name)
    return names


def mouse_config(c):
    """One saved mouse setting, cleaned up: {"accel": bool, "speed_on": s, "speed_off": s, "speed": s of the current mode}.
    The same number means two different things: with acceleration ON, libinput's speed reshapes the acceleration
    curve (how soon and how far it speeds up); with it OFF it multiplies every movement by one fixed amount. So each
    mode keeps its own speed, and switching acceleration brings back the feel you set for that mode. (A file from an
    older version has one "speed": that becomes the speed of the mode it was saved with.)"""
    accel = bool(c.get("accel", True))

    def one(key):
        v = _num(c.get(key), -1.0, 1.0, float)
        return None if v is None else round(v, 2)
    old = one("speed")
    on, off = one("speed_on"), one("speed_off")
    if on is None:
        on = old if (old is not None and accel) else 0.0
    if off is None:
        off = old if (old is not None and not accel) else 0.0
    return {"accel": accel, "speed_on": on, "speed_off": off, "speed": on if accel else off}


def apply_mouse_device(dev, speed, accel, props):
    """Acceleration on/off, then speed, for one device (an xinput id). Profile first: a profile change must not undo
    the speed. Off = the "flat" profile (speed still works: it scales the pointer evenly). Reads the device back
    and tries once more when the driver did not take a value; returns what the device reports (mouse_report)."""
    speed = max(-1.0, min(1.0, speed)) if speed == speed else 0.0      # libinput range; NaN -> default
    cur = props.get("libinput Accel Profile Enabled")
    avail = props.get("libinput Accel Profiles Available") or ["1", "1"]
    can_flat = avail[1:2] == ["1"]
    if cur and len(cur) >= 2 and (accel or can_flat):
        # (adaptive, flat) - or (adaptive, flat, custom) on xf86-input-libinput 1.3 and newer, which refuses a list
        # of the wrong length: sending two values there silently left acceleration on
        want = ["1", "0"] if accel else ["0", "1"]
        want = want + ["0"] * (len(cur) - 2)
    else:
        want = None
    for _attempt in (1, 2):
        if want:
            run(["xinput", "set-prop", dev, "libinput Accel Profile Enabled"] + want)
        run(["xinput", "set-prop", dev, "libinput Accel Speed", "%.2f" % speed])
        if DRY or FILES_ONLY:
            return None
        now = xinput_props(dev)
        report = mouse_report(now)
        if report["speed"] is not None and abs(report["speed"] - round(speed, 2)) < 0.006 \
                and (want is None or report["accel"] == accel):
            return report
    return report


def mouse_report(props):
    """What a device says it is doing: {"accel": bool or None, "speed": float or None, "can_turn_off": bool}."""
    cur = props.get("libinput Accel Profile Enabled") or []
    avail = props.get("libinput Accel Profiles Available") or []
    try:
        speed = float((props.get("libinput Accel Speed") or [""])[0])
    except ValueError:
        speed = None
    return {"accel": (cur[0] == "1") if cur else None, "speed": speed,
            "can_turn_off": avail[1:2] == ["1"] if avail else bool(cur)}


def mouse_choice(settings, name):
    """The saved (speed, acceleration) for a device: its own setting, else the one for all devices, else None."""
    mouse = settings.get("mouse") if isinstance(settings.get("mouse"), dict) else {}
    cfg = mouse.get(name) or mouse.get(ALL)
    if not isinstance(cfg, dict):
        return None
    cfg = mouse_config(cfg)
    return cfg["speed"], cfg["accel"]


def apply_mouse(settings):
    for dev, name, props in list_pointers():
        choice = mouse_choice(settings, name)
        if choice:
            apply_mouse_device(dev, choice[0], choice[1], props)


def mouse_status():
    """One line per pointing device: what the driver is really doing right now (shown under the sliders)."""
    lines = []
    for _dev, name, props in list_pointers():
        r = mouse_report(props)
        if r["speed"] is None:
            continue
        mode = {True: "acceleration on", False: "acceleration off", None: "acceleration unknown"}[r["accel"]]
        extra = "" if r["can_turn_off"] or r["accel"] is False else "  (this device cannot turn acceleration off)"
        lines.append("%s: %s, speed %+.2f%s" % (name, mode, r["speed"], extra))
    return lines


# ------------------------------------------------------------------ monitors
class Output:
    def __init__(self, name):
        self.name = name
        self.primary = False
        self.modes = {}          # "1920x1080" -> [rates as strings, highest first]
        self.cur_mode = None
        self.cur_rate = None
        self.rotate = "normal"
        self.scale = 100
        self.x = 0
        self.y = 0
        self.w = 0
        self.h = 0
        self.enabled = False


def parse_xrandr(text):
    outs, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(\S+) (connected|disconnected)\b(.*)$", line)
        if m:
            cur = None
            if m.group(2) != "connected":
                continue
            cur = Output(m.group(1))
            outs.append(cur)
            rest = m.group(3)
            cur.primary = " primary" in " " + rest.split("(")[0]
            g = re.search(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", rest)
            if g:
                cur.enabled = True
                cur.x = int(g.group(3))
                cur.y = int(g.group(4))
                cur.w, cur.h = int(g.group(1)), int(g.group(2))
            before = rest.split("(")[0].split()
            for r in ("left", "right", "inverted"):
                if r in before:
                    cur.rotate = r
            continue
        m = re.match(r"^\s+(\d+x\d+)i?\s+(.*)$", line)
        if m and cur:
            mode, rest = m.group(1), m.group(2)
            rates = []
            for tok in rest.split():
                rm = re.match(r"^(\d+(?:\.\d+)?)([*+]*)$", tok)
                if not rm:
                    continue
                rates.append(rm.group(1))
                if "*" in rm.group(2):
                    cur.cur_mode, cur.cur_rate = mode, rm.group(1)
            if mode not in cur.modes:
                cur.modes[mode] = rates
    for o in outs:
        if o.enabled and o.cur_mode and o.w:
            pct = 100.0 * out_size(o.cur_mode, o.rotate)[0] / o.w
            o.scale = min(SCALES, key=lambda v: abs(v - pct))
    return outs


def mode_area(mode):
    w, h = mode.split("x")
    return int(w) * int(h)


def out_size(mode, rotate, scale=100):
    """Size of a screen on the desktop (width, height) after rotation and scaling.
    At 200% a 3840x2160 screen takes up 1920x1080 of desktop space."""
    w, h = (int(v) for v in mode.split("x"))
    w, h = (h, w) if rotate in ("left", "right") else (w, h)
    if scale in SCALES and scale != 100:
        w, h = round(w * 100 / scale), round(h * 100 / scale)
    return (w, h)


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def touching(a, b):
    """True when two rectangles share part of an edge (no gap, no overlap)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    side = (ax + aw == bx or bx + bw == ax) and ay < by + bh and by < ay + ah
    top = (ay + ah == by or by + bh == ay) and ax < bx + bw and bx < ax + aw
    return side or top


def snap_position(others, size, raw, tol=150):
    """Nearest valid spot for a screen of `size` near `raw`: glued to the edge of another screen,
    sliding freely along that edge, snapping to aligned edges / centre within `tol` pixels."""
    w, h = size
    rx, ry = raw
    if not others:
        return (rx, ry)
    cands = []
    for (ox, oy, ow, oh) in others:
        m = max(1, min(w, h, ow, oh) // 3)           # keep at least this much contact
        for x in (ox + ow, ox - w):                    # right of / left of
            y = min(max(ry, oy - h + m), oy + oh - m)
            for al in (oy, oy + oh - h, oy + (oh - h) // 2):
                if abs(y - al) <= tol:
                    y = al
                    break
            cands.append((x, y))
        for y in (oy + oh, oy - h):                    # below / above
            x = min(max(rx, ox - w + m), ox + ow - m)
            for al in (ox, ox + ow - w, ox + (ow - w) // 2):
                if abs(x - al) <= tol:
                    x = al
                    break
            cands.append((x, y))
    good = [c for c in cands if not any(overlaps((c[0], c[1], w, h), o) for o in others)]
    if not good:
        right = max(o[0] + o[2] for o in others)
        return (right, others[0][1])
    return min(good, key=lambda c: (c[0] - rx) ** 2 + (c[1] - ry) ** 2)


def build_xrandr(outputs, cfg):
    """One xrandr command that sets every output. Uses the saved x/y positions from the layout
    editor; without them the screens are laid out left to right."""
    cmd = ["xrandr"]
    enabled = [o for o in outputs if cfg.get(o.name, {}).get("enabled", True)]
    if outputs and not enabled:
        return cmd                         # never switch every screen off (a damaged file must not leave a black desktop)
    use_pos = bool(enabled) and all("x" in cfg.get(o.name, {}) and "y" in cfg.get(o.name, {}) for o in enabled)
    x = 0
    for o in sorted(outputs, key=lambda o: o.x):
        c = cfg.get(o.name, {})
        if not c.get("enabled", True):
            cmd += ["--output", o.name, "--off"]
            continue
        mode = c.get("mode")
        if mode not in o.modes:            # saved mode no longer exists on this monitor: keep what it runs now
            mode = o.cur_mode or (max(o.modes, key=mode_area) if o.modes else None)
        if not mode:
            continue
        rate = c.get("rate")
        if rate not in o.modes.get(mode, []):
            rate = o.cur_rate if mode == o.cur_mode else (o.modes[mode][0] if o.modes.get(mode) else None)
        rot = c.get("rotate", o.rotate)
        if rot not in [r for r, _ in ROTATIONS]:
            rot = o.rotate
        scale = c.get("scale", o.scale)
        if scale not in SCALES:
            scale = o.scale
        cmd += ["--output", o.name, "--mode", mode]
        if rate:
            cmd += ["--rate", str(rate)]
        try:
            px, py = (int(c["x"]), int(c["y"])) if use_pos else (x, 0)
            if not (-32768 <= px <= 32767 and -32768 <= py <= 32767):
                raise ValueError("position out of range")
            pos = "%dx%d" % (px, py)
        except (KeyError, TypeError, ValueError, OverflowError):
            pos = "%dx0" % x
        k = "%.5f" % (100.0 / scale)
        cmd += ["--rotate", rot, "--scale", "%sx%s" % (k, k), "--pos", pos]
        if c.get("primary"):
            cmd += ["--primary"]
        x += out_size(mode, rot, scale)[0]
    return cmd


def apply_monitors(settings):
    cfg = settings.get("monitors", {})
    if not cfg:
        return
    outs = parse_xrandr(query(["xrandr", "--query"]))
    outs = [o for o in outs if o.name in cfg or len(outs) == 1]
    if not outs:
        return
    cmd = build_xrandr(outs, cfg)
    if len(cmd) > 1:
        run(cmd)


def refresh_desktop(changed):
    """After a layout change: redraw the bar(s) and the wallpaper for the new screens."""
    if not changed or DRY:
        return
    for cmd in ([os.path.join(CONFIG_DIR, "scripts", "Wallpaper.sh"), "--restore"],
                [os.path.expanduser("~/.config/polybar/launch.sh")]):
        if os.path.exists(cmd[0]):
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def snapshot_monitors():
    """Current monitor state as a settings dict (used to revert a bad change)."""
    snap = {}
    for o in parse_xrandr(query(["xrandr", "--query"])):
        snap[o.name] = {"enabled": o.enabled, "mode": o.cur_mode, "rate": o.cur_rate,
                        "rotate": o.rotate, "scale": o.scale, "primary": o.primary, "x": o.x, "y": o.y}
    return snap


# ------------------------------------------------------------------ mouse cursor theme
CURSOR_DEFAULT_SIZE = 24
CURSOR_SIZES = [16, 24, 32, 48, 64, 96]
# the default cursor (the installer unpacks it into ~/.local/share/icons from assets/cursors): used whenever no
# theme was picked in Settings > Mouse > Mouse cursor and it is installed
CURSOR_DEFAULT_THEME = "capitaine-cursors"


def current_cursor():
    """(theme or None, size) of the cursor the desktop uses right now: ~/.icons/default and the X resources, else
    the size X picks by itself (libXcursor: Xft.dpi * 16 / 72, else the shorter screen side / 48), rounded to one
    of CURSOR_SIZES. The settings window starts from this, so it shows - and keeps - what you already have."""
    theme = None
    try:
        with open(os.path.expanduser("~/.icons/default/index.theme")) as f:
            m = re.search(r"^[ \t]*Inherits[ \t]*=[ \t]*([^,\n]+)", f.read(), re.M)
            theme = m.group(1).strip() if m else None
    except (OSError, UnicodeDecodeError):
        pass
    res = query(["xrdb", "-query"])
    m = re.search(r"^Xcursor\.theme:\s*(\S+)", res, re.M)
    theme = theme or (m.group(1) if m else None)
    size = None
    m = re.search(r"^Xcursor\.size:\s*(\d+)", res, re.M)
    if m:
        size = int(m.group(1))
    else:
        dpi = re.search(r"^Xft\.dpi:\s*(\d+)", res, re.M)
        if dpi:
            size = int(dpi.group(1)) * 16 // 72
        else:
            dim = re.search(r"dimensions:\s*(\d+)x(\d+) pixels", query(["xdpyinfo"]))
            if dim:
                size = min(int(dim.group(1)), int(dim.group(2))) // 48
    size = min(CURSOR_SIZES, key=lambda v: abs(v - size)) if size else CURSOR_DEFAULT_SIZE
    return theme, size


def list_cursor_themes():
    """Names of installed cursor themes (icon themes that ship a cursors/ folder)."""
    dirs = [os.path.expanduser("~/.icons"), os.path.expanduser("~/.local/share/icons"),
            "/usr/share/icons", "/usr/local/share/icons", "/usr/pkg/share/icons"]
    dirs += [os.path.join(d, "icons") for d in os.environ.get("XDG_DATA_DIRS", "").split(":") if d]
    found = set()
    for d in dirs:
        try:
            for name in os.listdir(d):
                if os.path.isdir(os.path.join(d, name, "cursors")):
                    found.add(name)
        except OSError:
            pass
    return sorted(found, key=str.lower)


def cursor_choice(settings, themes=None):
    """(theme or None, size): the theme picked in Settings, else the default one (Capitaine Cursors) when it is
    installed; None leaves the cursor as the system has it."""
    cfg = settings.get("cursor") if isinstance(settings.get("cursor"), dict) else {}
    theme = cfg.get("theme") if isinstance(cfg.get("theme"), str) else None
    if not theme:
        theme = CURSOR_DEFAULT_THEME if CURSOR_DEFAULT_THEME in (themes if themes is not None
                                                                  else list_cursor_themes()) else None
    try:
        size = max(8, min(256, int(cfg.get("size", CURSOR_DEFAULT_SIZE))))
    except (TypeError, ValueError):
        size = CURSOR_DEFAULT_SIZE
    return theme, size


def _set_ini_key(text, key, value):
    line = "%s=%s" % (key, value)
    if re.search(r"^[ \t]*%s[ \t]*=.*$" % re.escape(key), text, re.M):
        return re.sub(r"^[ \t]*%s[ \t]*=.*$" % re.escape(key), line, text, flags=re.M)
    if "[Settings]" not in text:
        text = "[Settings]\n" + text
    return text.replace("[Settings]", "[Settings]\n" + line, 1)


def _write_if_changed(path, text):
    try:
        with open(path) as f:
            if f.read() == text:
                return
    except OSError:
        pass
    if DRY:
        print("write", path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".i3tmp", "w") as f:
        f.write(text)
    os.replace(path + ".i3tmp", path)


XSETTINGSD_CONF = os.path.join((os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")), "xsettingsd",
                               "xsettingsd.conf")
XPROFILE_MARK = ("# >>> i3wm-dots cursor (Settings > Mouse > Mouse cursor) >>>",
                 "# <<< i3wm-dots cursor <<<")
XRESOURCES_MARK = ("! >>> i3wm-dots cursor (Settings > Mouse > Mouse cursor) >>>",
                   "! <<< i3wm-dots cursor <<<")


def _xcursor_resources():
    """(theme, size) as the X resources say right now (what newly started programs - and i3 - use)."""
    res = query(["xrdb", "-query"])
    t = re.search(r"^Xcursor\.theme:\s*(\S+)", res, re.M)
    z = re.search(r"^Xcursor\.size:\s*(\d+)", res, re.M)
    return (t.group(1) if t else None, int(z.group(1)) if z else None)


def _set_block(text, lines, marks=XPROFILE_MARK):
    """Put `lines` between the two `marks` lines of a file (replacing an older copy of the block)."""
    start, end = marks
    block = "\n".join([start] + lines + [end])
    pat = re.compile(r"^%s$.*?^%s$\n?" % (re.escape(start), re.escape(end)), re.M | re.S)
    if pat.search(text):
        return pat.sub(lambda _m: block + "\n", text, count=1)        # (a function: no backslash processing)
    return (text + ("\n" if text and not text.endswith("\n") else "") + block + "\n")


def _edit_ini(path, theme, size):
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        text = "[Settings]\n"
    text = _set_ini_key(text, "gtk-cursor-theme-name", theme)
    text = _set_ini_key(text, "gtk-cursor-theme-size", size)
    _write_if_changed(path, text)


def _link_cursor_theme(theme, data_home):
    """A theme that is only in ~/.local/share/icons (the default one, or one installed with KDE's 'Get New Cursors')
    is not found by libXcursor before 1.2.2, which only looks in ~/.icons - so plain X programs and i3 would keep
    their old cursor. Link it into ~/.icons (recorded, so uninstall.sh removes the link again)."""
    src = os.path.join(data_home, "icons", theme)
    dst = os.path.expanduser(os.path.join("~/.icons", theme))
    if not os.path.isdir(os.path.join(src, "cursors")) or os.path.lexists(dst) or DRY:
        return
    if any(os.path.isdir(os.path.join(d, theme, "cursors")) for d in ("/usr/share/icons", "/usr/local/share/icons",
                                                                     "/usr/pkg/share/icons", "/usr/X11R6/share/icons")):
        return                                         # (the system has it where every program looks)
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.symlink(src, dst)
    except OSError:
        return
    manifest = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "i3wm-dots",
                            "installed")
    try:
        os.makedirs(os.path.dirname(manifest), exist_ok=True)
        with open(manifest, "a") as f:
            f.write("path %s\n" % dst)
    except OSError:
        pass


def apply_cursor(settings):
    """Make the chosen cursor theme / size the one every program uses, so it does not change as the pointer moves
    from one window to another. Each kind of program looks in its own place:
      plain X programs, i3, the bar     X resources (Xcursor.theme / .size) + the "default" theme in ~/.icons and
                                        ~/.local/share/icons (+ the desktop background via xsetroot)
      GTK 3 / GTK 4 apps                gtk-3.0 / gtk-4.0 settings.ini, and live through xsettingsd (open GTK apps
                                        switch at once; Flatpak apps read it too)
      Qt, Electron, Java, Flatpak       XCURSOR_THEME / XCURSOR_SIZE: ~/.xprofile and environment.d (from the next
                                        login on) and the session bus (programs it starts)"""
    theme, size = cursor_choice(settings)
    if not theme:
        return
    if not isinstance(theme, str) or not re.match(r"^[A-Za-z0-9 ._+-]+\Z", theme):
        return                                         # never put anything but a plain theme name into config files
    index = "[Icon Theme]\nName=Default\nComment=Default cursor theme\nInherits=%s\n" % theme
    _write_if_changed(os.path.expanduser("~/.icons/default/index.theme"), index)
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    _link_cursor_theme(theme, data_home)
    _write_if_changed(os.path.join(data_home, "icons", "default", "index.theme"), index)
    _edit_ini(os.path.join(_CFG_HOME, "gtk-3.0", "settings.ini"), theme, size)
    _edit_ini(os.path.join(_CFG_HOME, "gtk-4.0", "settings.ini"), theme, size)       # (GTK 4 apps: Ghostty...)
    _write_if_changed(XSETTINGSD_CONF, "# written by the i3 settings window (Mouse > Mouse cursor)\n"
                                       "Gtk/CursorThemeName \"%s\"\nGtk/CursorThemeSize %d\n" % (theme, size))
    # XCURSOR_* for the next login (display managers read ~/.xprofile; systemd sessions environment.d)
    xprofile = os.path.expanduser("~/.xprofile")
    try:
        with open(xprofile) as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        text = ""
    _write_if_changed(xprofile, _set_block(text, [
        "export XCURSOR_THEME=%s" % shlex.quote(theme), "export XCURSOR_SIZE=%d" % size,
        "command -v xrdb >/dev/null 2>&1 && printf 'Xcursor.theme: %s\\nXcursor.size: %s\\n' \"$XCURSOR_THEME\" "
        "\"$XCURSOR_SIZE\" | xrdb -merge"]))
    _write_if_changed(os.path.join(_CFG_HOME, "environment.d", "90-i3dots-cursor.conf"),
                      "XCURSOR_THEME=%s\nXCURSOR_SIZE=%d\n" % (theme, size))
    # ...and the X resources at the start of the next session, before i3 starts: i3 loads its cursor only once,
    # when it starts, and every window that does not pick its own cursor (GTK windows like this settings window,
    # most pop-ups) shows i3's - so i3 must start with the right size, or the pointer changes size over them
    xres = os.path.expanduser("~/.Xresources")
    try:
        with open(xres) as f:
            rtext = f.read()
    except (OSError, UnicodeDecodeError):
        rtext = ""
    _write_if_changed(xres, _set_block(rtext, ["Xcursor.theme: %s" % theme, "Xcursor.size: %d" % size],
                                       XRESOURCES_MARK))
    changed = False
    if DRY:
        print("+ xrdb -merge  (Xcursor.theme: %s, Xcursor.size: %d)" % (theme, size))
    elif not FILES_ONLY:
        changed = _xcursor_resources() != (theme, size)
        try:
            subprocess.run(["xrdb", "-merge"], input="Xcursor.theme: %s\nXcursor.size: %d\n" % (theme, size),
                           text=True, capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
    run(["xsetroot", "-cursor_name", "left_ptr"])
    env_vars = ["XCURSOR_THEME=%s" % theme, "XCURSOR_SIZE=%d" % size]
    if shutil.which("dbus-update-activation-environment"):
        run(["dbus-update-activation-environment"] + env_vars)
    xs = os.path.join(CONFIG_DIR, "scripts", "XSettings.sh")             # open GTK apps follow at once
    if os.path.exists(xs):
        run(["bash", xs])
    if changed:
        # i3 picks the new cursor up only when it (re)starts: restart it in place (windows stay as they are, like
        # SUPER+SHIFT+R). Not needed at login when the session already started with these values (~/.Xresources).
        run(["i3-msg", "-q", "restart"])


# ------------------------------------------------------------------ window opacity (picom)
PICOM_CONF = os.path.join((os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")), "picom", "picom.conf")
OPACITY_DEFAULT = {"active": 100, "inactive": 95, "terminal": 95}
GHOSTTY_CONF = os.path.join((os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")), "ghostty", "config")
KITTY_CONF = os.path.join((os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")), "kitty", "kitty.conf")


def set_conf_line(path, pattern, line):
    """Replace the (first) line matching `pattern` in a config file, or append `line`. True if the file changed."""
    try:
        with open(path) as f:
            text = orig = f.read()
    except OSError:
        return False                                    # that terminal is not installed / configured
    if re.search(pattern, text, re.M):
        text = re.sub(pattern, line, text, count=1, flags=re.M)
    else:
        text += ("" if text.endswith("\n") or not text else "\n") + line + "\n"
    if text == orig:
        return False
    if DRY:
        print("write %s: %s" % (path, line))
        return True
    with open(path + ".i3tmp", "w") as f:
        f.write(text)
    os.replace(path + ".i3tmp", path)
    return True


def apply_terminal_opacity(settings):
    """Background opacity of Ghostty and kitty (their own setting, so only the terminal gets see-through)."""
    cfg = settings.get("opacity") or {}
    try:
        pct = int(cfg["terminal"])
    except (KeyError, TypeError, ValueError):
        return
    val = "%.2f" % (min(100, max(20, pct)) / 100.0)
    changed = set_conf_line(GHOSTTY_CONF, r"^[ \t]*background-opacity[ \t]*=.*$", "background-opacity = " + val)
    if changed and not DRY:
        subprocess.run(["pkill", "-USR2", "-x", "ghostty"], capture_output=True)       # Ghostty reloads its config
    changed = set_conf_line(KITTY_CONF, r"^[ \t]*background_opacity[ \t].*$", "background_opacity " + val)
    if changed and not DRY:
        subprocess.run(["pkill", "-USR1", "-x", "kitty"], capture_output=True)         # kitty reloads its config


def apply_opacity(settings, restart=False):
    """Window opacity: picom's focused / unfocused values, and the terminal's own background opacity."""
    apply_terminal_opacity(settings)
    apply_picom_opacity(settings, restart)


def apply_picom_opacity(settings, restart=False):
    """Write active-opacity / inactive-opacity into picom.conf; restart picom if the file changed."""
    cfg = settings.get("opacity")
    if not cfg or not os.path.exists(PICOM_CONF):
        return
    # 20% is the floor: lower would make windows practically invisible
    vals = {"active-opacity": min(100, max(20, int(cfg.get("active", 100)))) / 100.0,
            "inactive-opacity": min(100, max(20, int(cfg.get("inactive", 95)))) / 100.0}
    with open(PICOM_CONF) as f:
        text = orig = f.read()
    for key, val in vals.items():
        line = "%s = %.2f;" % (key, val)
        if re.search(r"^[ \t]*%s[ \t]*=.*$" % key, text, re.M):
            text = re.sub(r"^[ \t]*%s[ \t]*=.*$" % key, line, text, flags=re.M)
        else:
            text += "\n" + line + "\n"
    if text == orig:
        return
    if DRY:
        print("write %s: %s" % (PICOM_CONF, ", ".join("%s=%.2f" % kv for kv in vals.items())))
        return
    with open(PICOM_CONF + ".i3tmp", "w") as f:
        f.write(text)
    os.replace(PICOM_CONF + ".i3tmp", PICOM_CONF)
    if restart and subprocess.run(["pgrep", "-x", "picom"], capture_output=True).returncode == 0:
        subprocess.run(["pkill", "-u", str(os.getuid()), "-x", "picom"])
        subprocess.Popen([os.path.join(CONFIG_DIR, "scripts", "Picom.sh")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------ terminal themes (Ghostty, kitty)
THEME_DEFAULT = {"ghostty": "mono", "kitty": "01-Wallust"}       # the shipped monochrome themes
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})\Z")
_CFG_HOME = (os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))
KITTY_THEME_DIR = os.path.join(_CFG_HOME, "kitty", "kitty-themes")
GHOSTTY_THEME_DIRS = [os.path.join(_CFG_HOME, "ghostty", "themes"), "/usr/share/ghostty/themes",
                      "/usr/local/share/ghostty/themes", "/opt/ghostty/share/ghostty/themes"]


def _list_files(dirs, suffix=""):
    found = {}
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            path = os.path.join(d, n)
            if not os.path.isfile(path) or n.startswith("."):
                continue
            if suffix and not n.endswith(suffix):
                continue
            name = n[:-len(suffix)] if suffix else n
            if re.fullmatch(r"[^\"\\\n\r]{1,80}", name):          # names that are safe to write into a config
                found.setdefault(name, path)                      # the first folder wins (your own themes first)
    return found


def list_ghostty_themes():
    return _list_files(GHOSTTY_THEME_DIRS)


def list_kitty_themes():
    return _list_files([KITTY_THEME_DIR], ".conf")


def theme_label(kind, name):
    if name == THEME_DEFAULT.get(kind):
        return "Monochrome (default)"
    return name.replace("_", " ") if kind == "kitty" else name


def parse_theme_colors(kind, path):
    """{'bg','fg','palette'[16]} as '#rrggbb' strings (missing values fall back to a dark default)."""
    out = {"bg": "#000000", "fg": "#e6e6e6", "palette": ["#555555"] * 16}
    try:
        with open(path, errors="replace") as f:
            lines = f.read().splitlines()[:400]
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if kind == "ghostty":
            m = re.match(r"^(background|foreground)\s*=\s*(\S+)$", line)
            n = re.match(r"^palette\s*=\s*(\d+)\s*=\s*(\S+)$", line)
            key, val = (m.group(1), m.group(2)) if m else (None, None)
            idx, pal = (int(n.group(1)), n.group(2)) if n else (None, None)
        else:
            m = re.match(r"^(background|foreground)\s+(\S+)$", line)
            n = re.match(r"^color(\d+)\s+(\S+)$", line)
            key, val = (m.group(1), m.group(2)) if m else (None, None)
            idx, pal = (int(n.group(1)), n.group(2)) if n else (None, None)
        if key:
            h = HEX_RE.match(val)
            if h:
                out["bg" if key == "background" else "fg"] = "#" + h.group(1)
        elif idx is not None and 0 <= idx < 16:
            h = HEX_RE.match(pal)
            if h:
                out["palette"][idx] = "#" + h.group(1)
    return out


def current_theme(kind):
    """The theme named in the terminal's config right now (or None)."""
    try:
        if kind == "ghostty":
            with open(GHOSTTY_CONF) as f:
                m = re.search(r'^[ \t]*theme[ \t]*=[ \t]*"?([^"\n]+?)"?[ \t]*$', f.read(), re.M)
        else:
            with open(KITTY_CONF) as f:
                m = re.search(r"^[ \t]*include[ \t]+\S*kitty-themes/([^/\s]+)\.conf[ \t]*$", f.read(), re.M)
    except OSError:
        return None
    return m.group(1) if m else None


def apply_themes(settings):
    """Write the chosen Ghostty / kitty theme into their configs and make running terminals reload."""
    cfg = settings.get("themes") or {}
    gh, ki = cfg.get("ghostty"), cfg.get("kitty")
    if isinstance(gh, str) and gh in list_ghostty_themes():
        if set_conf_line(GHOSTTY_CONF, r"^[ \t]*theme[ \t]*=.*$", 'theme = "%s"' % gh) and not DRY:
            subprocess.run(["pkill", "-USR2", "-x", "ghostty"], capture_output=True)
    if isinstance(ki, str) and ki in list_kitty_themes():
        line = "include ~/.config/kitty/kitty-themes/%s.conf" % ki
        if set_conf_line(KITTY_CONF, r"^[ \t]*include[ \t]+\S*kitty-themes/[^/\s]+\.conf[ \t]*$", line) and not DRY:
            subprocess.run(["pkill", "-USR1", "-x", "kitty"], capture_output=True)


# ------------------------------------------------------------------ terminal text size (Ghostty, kitty)
FONT_SIZE_DEFAULT = {"ghostty": 12.0, "kitty": 14.0}       # what the shipped configs use
FONT_SIZE_RANGE = (6.0, 36.0)


def clean_font_size(v):
    """A text size in points, rounded to half points, or None if it is not a sensible number."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return None
    if not FONT_SIZE_RANGE[0] <= v <= FONT_SIZE_RANGE[1]:
        return None
    return round(v * 2) / 2.0


def current_font_size(kind):
    if kind == "ghostty":
        return clean_font_size(read_value(GHOSTTY_CONF, "font-size", FONT_SIZE_DEFAULT["ghostty"])) or FONT_SIZE_DEFAULT["ghostty"]
    return clean_font_size(read_value(KITTY_CONF, "font_size", FONT_SIZE_DEFAULT["kitty"])) or FONT_SIZE_DEFAULT["kitty"]


def apply_terminal_font(settings):
    """Write the text size into the Ghostty / kitty config and make open terminals reload it."""
    cfg = settings.get("terminal_font") or {}
    gh, ki = clean_font_size(cfg.get("ghostty")), clean_font_size(cfg.get("kitty"))
    if gh and set_conf_line(GHOSTTY_CONF, r"^[ \t]*font-size[ \t]*=.*$", "font-size = %g" % gh) and not DRY:
        subprocess.run(["pkill", "-USR2", "-x", "ghostty"], capture_output=True)
    if ki and set_conf_line(KITTY_CONF, r"^[ \t]*font_size[ \t].*$", "font_size %g" % ki) and not DRY:
        subprocess.run(["pkill", "-USR1", "-x", "kitty"], capture_output=True)


# ------------------------------------------------------------------ gaps between windows (i3)
I3_CONFIG = os.path.join(CONFIG_DIR, "config")
GAPS_DEFAULT = {"inner": 5, "outer": 0, "smart": True}


def read_value(path, key, default):
    """Current number for 'key' in a config file (first match), else the default."""
    try:
        with open(path) as f:
            m = re.search(r"^\s*%s\s*[= ]\s*([0-9.]+)" % re.escape(key), f.read(), re.M)
        return float(m.group(1)) if m else default
    except (OSError, ValueError):
        return default


def apply_gaps(settings, reload=False):
    """Write gaps inner/outer + smart_gaps into the i3 config; apply live (gaps commands, or a reload
    when smart_gaps changed, since that one is config-only)."""
    cfg = settings.get("gaps")
    if not cfg or not os.path.exists(I3_CONFIG):
        return
    inner = min(100, max(0, int(cfg.get("inner", 5))))       # same range as the sliders
    outer = min(100, max(0, int(cfg.get("outer", 0))))
    smart = "on" if cfg.get("smart", True) else "off"
    want = {"gaps inner": "gaps inner %d" % inner, "gaps outer": "gaps outer %d" % outer,
            "smart_gaps": "smart_gaps %s" % smart}
    with open(I3_CONFIG) as f:
        text = orig = f.read()
    for key, line in want.items():
        pat = r"^%s\s+.*$" % re.escape(key)
        if re.search(pat, text, re.M):
            text = re.sub(pat, line, text, count=1, flags=re.M)
        else:
            text += "\n" + line + "\n"
    if text == orig:
        return
    smart_changed = re.search(r"^smart_gaps\s+(\S+)", orig, re.M)
    smart_changed = (smart_changed.group(1) if smart_changed else None) != smart
    if DRY:
        print("write %s: %s" % (I3_CONFIG, "; ".join(want.values())))
        return
    with open(I3_CONFIG + ".i3tmp", "w") as f:
        f.write(text)
    os.replace(I3_CONFIG + ".i3tmp", I3_CONFIG)
    if reload and smart_changed:
        run(["i3-msg", "reload"])
    else:
        run(["i3-msg", "gaps inner all set %d; gaps outer all set %d" % (inner, outer)])


# ------------------------------------------------------------------ colour theme (accent colour for everything)
# The look is black + greys + ONE accent colour (white = the original monochrome look). Changing the accent
# rewrites every place that colour is used: window borders, bar, menus (rofi), notifications (dunst), lock
# screen, stay-awake button, audio visualizer, terminal greeting and this window.
ACCENT_DEFAULT = "#ffffff"
ACCENT_PRESETS = [("mono", "Mono", "#ffffff"), ("cyan", "Cyan", "#00e5ff"), ("blue", "Blue", "#4d9fff"),
                  ("green", "Green", "#3ddc84"), ("purple", "Purple", "#b388ff"), ("pink", "Pink", "#ff6ec7"),
                  ("red", "Red", "#ff5252"), ("orange", "Orange", "#ff9f43"), ("yellow", "Yellow", "#ffd84d")]
ACCENT_RE = re.compile(r"^#?([0-9a-fA-F]{6})\Z")
ACCENT_MIN_BRIGHT = 0.35     # darker colours would be unreadable on the black background
POLYBAR_COLORS = os.path.join(_CFG_HOME, "polybar", "colors.ini")
ROFI_COLORS = os.path.join(CONFIG_DIR, "rofi", "colors-mono.rasi")
DUNST_COLORS = os.path.join(_CFG_HOME, "dunst", "dunstrc.d", "50-mono.conf")
ACCENT_CONF = os.path.join(CONFIG_DIR, "accent.conf")
CAVA_CONF = os.path.join(_CFG_HOME, "cava", "config")
FASTFETCH_CONF = os.path.join(_CFG_HOME, "fastfetch", "config-pokemon.jsonc")
CAVA_STEPS = (0.10, 0.19, 0.29, 0.43, 0.55, 0.75, 0.90, 1.00)


def norm_accent(value):
    """'#RRGGBB' (lowercase) for a valid colour, else None. Anything that is not a plain 6-digit hex is rejected."""
    if not isinstance(value, str):
        return None
    m = ACCENT_RE.match(value.strip())
    return "#" + m.group(1).lower() if m else None


def brightness(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def shade(hex_color, t):
    """The colour darkened towards black (t=1 keeps it)."""
    return "#%02x%02x%02x" % tuple(round(int(hex_color[i:i + 2], 16) * t) for i in (1, 3, 5))


def accent_palette(accent):
    return {"A": accent, "S": shade(accent, 0.75), "D": shade(accent, 0.55)}


def _rofi_colors(c):
    return """/* Palette: black / greys + one accent colour. Written by the Settings window (Colors tab); safe to hand-edit. */
* {
active-background: #1c1c1c;
active-foreground: %(A)s;
normal-background: #000000;
normal-foreground: #e6e6e6;
urgent-background: %(A)s;
urgent-foreground: #000000;

alternate-active-background: #1c1c1c;
alternate-active-foreground: %(A)s;
alternate-normal-background: #0a0a0a;
alternate-normal-foreground: #e6e6e6;
alternate-urgent-background: %(A)s;
alternate-urgent-foreground: #000000;

selected-active-background: %(A)s;
selected-active-foreground: #000000;
selected-normal-background: %(A)s;
selected-normal-foreground: #000000;
selected-urgent-background: %(S)s;
selected-urgent-foreground: #000000;

background-color: #000000;
background: rgba(0,0,0,0.92);
foreground: #e6e6e6;
border-color: %(A)s;

color0: #000000;
color1: #1c1c1c;
color2: #303030;
color3: #4a4a4a;
color4: #6e6e6e;
color5: #8c8c8c;
color6: %(S)s;
color7: #e6e6e6;
color8: #8c8c8c;
color9: %(A)s;
color10: %(S)s;
color11: #e6e6e6;
color12: %(A)s;
color13: #d9d9d9;
color14: #f2f2f2;
color15: %(A)s;
}
""" % c


BAR_SEGMENTS = 13            # modules in the "blocks" bar style (polybar/blocks.ini)


def bar_segments(accent):
    """Block colours for the "blocks" bar style: dark on the left, the accent colour on the right, each with a
    readable text colour (black on light blocks, white on dark ones)."""
    out = []
    for i in range(BAR_SEGMENTS):
        bg = shade(accent, 0.18 + 0.82 * i / (BAR_SEGMENTS - 1))
        out.append((bg, readable_on(bg)))
    return out


def readable_on(bg):
    """Black or white text, whichever contrasts more with the background (WCAG contrast ratio)."""
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#000000" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "#f2f2f2"


def _polybar_colors(c):
    v = bar_colors(c["A"])
    keys = ["background", "background-alt", "foreground", "primary", "secondary", "alert", "disabled", "line"]
    out = ["; Palette: black / greys + one accent colour. Written by the Settings window (Colors tab); safe to hand-edit.",
           "[colors]"] + ["%s = %s" % (k, v[k]) for k in keys]
    out.append("; the bar styles (Settings > Appearance > Bar style): one colour, alternating, dark, then the 13 shades "
               "from dark to the colour (gradient / powerline), each block colour with its text colour")
    out += ["%s = %s" % (k, v[k]) for k in ("block", "blockfg", "block2", "block2fg", "dark", "darkfg")]
    out += ["%s = %s" % (k, v[k]) for i in range(1, BAR_SEGMENTS + 1) for k in ("seg%d" % i, "segfg%d" % i)]
    return "\n".join(out) + "\n"


def _dunst_colors(c):
    return """[global]
    frame_color = "%(A)s"
    separator_color = frame
[urgency_low]
    background = "#000000f2"
    foreground = "%(S)s"
    frame_color = "#303030"
    highlight = "%(A)s"
[urgency_normal]
    background = "#000000f2"
    foreground = "#ffffff"
    frame_color = "%(A)s"
    highlight = "%(A)s"
[urgency_critical]
    background = "%(A)s"
    foreground = "#000000"
    frame_color = "%(A)s"
    highlight = "#000000"
""" % c


def _accent_conf(c):
    return ("# Colours used by the shell scripts (lock screen, bar buttons). Written by the Settings window.\n"
            "ACCENT=%s\nACCENT_DIM=%s\nACCENT_MUTED=%s\n" % (c["A"][1:], c["S"][1:], c["D"][1:]))


YAZI_THEME = os.path.join(_CFG_HOME, "yazi", "theme.toml")
YAZI_MARK = "# i3wm-dots:"          # the theme's first line: while it is there, the colour follows Settings > Colors


def _yazi_theme(c):
    """yazi (the file manager) in black and greys with the accent colour. Only sections every yazi from 25.2 on knows
    or skips: yazi 26 refuses a theme with a section it does not know, older ones ignore the newer sections."""
    c = dict(c, T=readable_on(c["A"]))          # text on the accent colour
    return """# i3wm-dots: yazi in black and greys with your accent colour. The Settings window (Colors) rewrites this file
# when you change the colour - delete these first lines to make it your own, it is then left alone.

[mgr]
cwd             = { fg = "%(A)s", bold = true }
find_keyword    = { fg = "%(T)s", bg = "%(A)s", bold = true }
find_position   = { fg = "%(S)s", bold = true, italic = true }
symlink_target  = { fg = "#8c8c8c", italic = true }
marker_copied   = { fg = "#e6e6e6", bg = "#e6e6e6" }
marker_cut      = { fg = "#6e6e6e", bg = "#6e6e6e" }
marker_marked   = { fg = "%(S)s", bg = "%(S)s" }
marker_selected = { fg = "%(A)s", bg = "%(A)s" }
count_copied    = { fg = "#000000", bg = "#e6e6e6" }
count_cut       = { fg = "#000000", bg = "#8c8c8c" }
count_selected  = { fg = "%(T)s", bg = "%(A)s" }
border_symbol   = "│"
border_style    = { fg = "#303030" }
# (the highlighted row in yazi before 26 - newer ones use [indicator] below)
hovered         = { fg = "%(T)s", bg = "%(A)s" }
preview_hovered = { fg = "#000000", bg = "#8c8c8c" }

[indicator]
parent  = { fg = "#000000", bg = "#8c8c8c" }
current = { fg = "%(T)s", bg = "%(A)s" }
preview = { fg = "#000000", bg = "#8c8c8c" }

[tabs]
active   = { fg = "%(T)s", bg = "%(A)s", bold = true }
inactive = { fg = "#8c8c8c", bg = "#1c1c1c" }

[mode]
normal_main = { fg = "%(T)s", bg = "%(A)s", bold = true }
normal_alt  = { fg = "%(A)s", bg = "#1c1c1c" }
select_main = { fg = "#000000", bg = "#e6e6e6", bold = true }
select_alt  = { fg = "#e6e6e6", bg = "#1c1c1c" }
unset_main  = { fg = "#000000", bg = "#8c8c8c", bold = true }
unset_alt   = { fg = "#8c8c8c", bg = "#1c1c1c" }

[status]
perm_type       = { fg = "%(A)s" }
perm_read       = { fg = "#e6e6e6" }
perm_write      = { fg = "#b3b3b3" }
perm_exec       = { fg = "%(S)s" }
perm_sep        = { fg = "#4a4a4a" }
progress_label  = { fg = "#ffffff", bold = true }
progress_normal = { fg = "%(A)s", bg = "#303030" }
progress_error  = { fg = "#ffffff", bg = "#6e6e6e" }

[which]
mask            = { bg = "#0a0a0a" }
cand            = { fg = "%(A)s" }
rest            = { fg = "#6e6e6e" }
desc            = { fg = "#e6e6e6" }
separator_style = { fg = "#4a4a4a" }

[confirm]
border  = { fg = "%(A)s" }
title   = { fg = "%(A)s", bold = true }
btn_yes = { fg = "%(T)s", bg = "%(A)s", bold = true }
btn_no  = { fg = "#e6e6e6" }

[spot]
border   = { fg = "%(A)s" }
title    = { fg = "%(A)s", bold = true }
tbl_col  = { fg = "%(A)s" }
tbl_cell = { fg = "%(T)s", bg = "%(A)s" }

[notify]
title_info  = { fg = "#e6e6e6", bold = true }
title_warn  = { fg = "%(A)s", bold = true }
title_error = { fg = "#ffffff", bold = true, underline = true }

[pick]
border   = { fg = "%(A)s" }
active   = { fg = "%(T)s", bg = "%(A)s" }
inactive = { fg = "#e6e6e6" }

[input]
border   = { fg = "%(A)s" }
title    = { fg = "#e6e6e6" }
value    = { fg = "#ffffff" }
selected = { fg = "%(T)s", bg = "%(A)s" }

[cmp]
border   = { fg = "%(A)s" }
active   = { fg = "%(T)s", bg = "%(A)s" }
inactive = { fg = "#e6e6e6" }

[tasks]
border  = { fg = "%(A)s" }
title   = { fg = "#e6e6e6" }
hovered = { fg = "%(T)s", bg = "%(A)s" }

[help]
border  = { fg = "%(A)s" }
chord   = { fg = "%(A)s" }
action  = { fg = "#8c8c8c" }
hovered = { fg = "%(T)s", bg = "%(A)s" }

[filetype]
rules = [
  { url = "*/", fg = "%(A)s", bold = true },                       # folders
  { url = "*", is = "orphan", fg = "#6e6e6e", italic = true },    # links that point nowhere
  { url = "*", is = "link", fg = "#b3b3b3", italic = true },
  { url = "*", is = "exec", fg = "#ffffff", bold = true },
  { mime = "image/*", fg = "#d9d9d9" },
  { mime = "{audio,video}/*", fg = "#bfbfbf" },
  { mime = "application/{zip,rar,7z*,tar,gzip,xz,zstd,bzip*,lzma,compress,archive,cpio,arj,xar,ms-cab*}", fg = "#a6a6a6" },
  { url = "*", fg = "#e6e6e6" },
]
""" % c


def _yazi_theme_is_ours(path):
    """The theme the installer put there (its first line), or none yet in the folder the installer made."""
    try:
        with open(path) as f:
            return f.readline().startswith(YAZI_MARK)
    except OSError:
        return os.path.exists(os.path.join(os.path.dirname(path), ".i3wm-dots-installed"))


def _write_generated(path, text):
    """Write a generated file only when it differs; returns True when it changed."""
    path = os.path.realpath(path)          # keep a symlinked (stow-managed) config a symlink
    try:
        with open(path) as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    if DRY:
        print("write", path)
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".i3tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    return True


def _sub_in_file(path, pattern, repl, flags=re.M):
    """Regex-replace inside an existing file (no-op when the file is missing). Returns True when it changed."""
    path = os.path.realpath(path)
    try:
        with open(path) as f:
            old = f.read()
    except OSError:
        return False
    new = re.sub(pattern, repl, old, flags=flags)
    if new == old:
        return False
    if DRY:
        print("write", path)
        return True
    with open(path + ".i3tmp", "w") as f:
        f.write(new)
    os.replace(path + ".i3tmp", path)
    return True


def apply_colors(settings):
    """Write the accent colour into every config that uses it, then reload i3 / notifications.
    A lock makes two simultaneous applies (login + the Settings window) take turns instead of mixing colours."""
    import fcntl
    lock = None
    try:
        lock = open(os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "i3dots-colors-%d.lock" % os.getuid()), "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
    except OSError:
        lock = None                       # no lock available: still apply
    try:
        _apply_colors(settings)
    finally:
        if lock:
            lock.close()


def _apply_colors(settings):
    cfg = settings.get("colors")
    accent = norm_accent(cfg.get("accent")) if isinstance(cfg, dict) else None
    if not accent or brightness(accent) < ACCENT_MIN_BRIGHT:
        return
    c = accent_palette(accent)
    key = "white" if accent == ACCENT_DEFAULT else "38;2;%d;%d;%d" % tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))
    errors = []
    results = {}

    def step(name, fn, *args):
        """One file failing (say, read-only) must not leave the other files on the old colour."""
        try:
            results[name] = bool(fn(*args))
        except OSError as e:
            results[name] = False
            errors.append("%s: %s" % (os.path.basename(args[0]), e))

    def gen(name, path, text):
        if os.path.isdir(os.path.dirname(path)):
            step(name, _write_generated, path, text)
    gen("polybar", POLYBAR_COLORS, _polybar_colors(c))
    gen("rofi", ROFI_COLORS, _rofi_colors(c))
    gen("dunst", DUNST_COLORS, _dunst_colors(c))
    gen("accent", ACCENT_CONF, _accent_conf(c))
    if _yazi_theme_is_ours(YAZI_THEME):          # (a yazi theme of your own is never overwritten)
        gen("yazi", YAZI_THEME, _yazi_theme(c))
    step("i3", _sub_in_file, I3_CONFIG, r"^set \$accent[ \t]+#[0-9a-fA-F]{6}[ \t]*$", lambda m: "set $accent %s" % accent)
    step("cava", _sub_in_file, CAVA_CONF, r"^gradient_color_([1-8]) = .*$",
         lambda m: "gradient_color_%s = '%s'" % (m.group(1), shade(accent, CAVA_STEPS[int(m.group(1)) - 1])))
    step("fastfetch", _sub_in_file, FASTFETCH_CONF, r'("keyColor"\s*:\s*)"[^"]*"', lambda m: '%s"%s"' % (m.group(1), key))
    changed = any(results.values())
    dunst_changed = results.get("dunst", False)
    if (not changed and not errors) or DRY:
        return
    if changed and dunst_changed:
        run(["dunstctl", "reload"])
    if changed:
        run(["i3-msg", "reload"])     # re-reads the border colours and relaunches the bar with the new colours
    if errors:
        raise OSError("some colour files could not be written (%s)" % "; ".join(errors))


# ------------------------------------------------------------------ window tiling (AutoTiling.py)
TILING_MODES = ("dwindle", "classic")
TILING_LABELS = [("dwindle", "Spiral, like Hyprland (new windows split the focused one)"),
                 ("classic", "Classic i3 (new windows open side by side)")]
AUTOTILING = os.path.join(CONFIG_DIR, "scripts", "AutoTiling.py")


def apply_tiling(settings):
    """The tiler reads the mode from settings.json by itself; just make sure it is running."""
    if DRY or not os.path.exists(AUTOTILING):
        return
    subprocess.Popen([sys.executable, AUTOTILING], start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)      # exits at once if it already runs


# ------------------------------------------------------------------ touchpad gestures (Touchégg)
# Three fingers left / right go to the next / previous workspace. Touchégg reads the touchpad in a system service
# (touchegg.service); its client in your session runs the commands from ~/.config/touchegg/touchegg.conf.
GESTURES_DEFAULT = {"enabled": True, "natural": True}     # natural: swipe left = next workspace, like a Mac
TOUCHEGG_CONF = os.path.join(_CFG_HOME, "touchegg", "touchegg.conf")
GESTURES_SCRIPT = os.path.join(CONFIG_DIR, "scripts", "Gestures.sh")
WORKSPACE_SCRIPT = os.path.join(CONFIG_DIR, "scripts", "Workspace.py")
TOUCHEGG_HINT = "Swipe gestures use Touchégg, which only runs on Linux."


def gesture_choice(settings):
    g = settings.get("gestures") if isinstance(settings.get("gestures"), dict) else {}
    return {k: g[k] if isinstance(g.get(k), bool) else v for k, v in GESTURES_DEFAULT.items()}


def touchegg_conf(settings):
    """The Touchégg config for the saved choice (no gestures at all when they are switched off)."""
    from xml.sax.saxutils import escape
    g = gesture_choice(settings)
    # an absolute path: Touchégg does not promise a shell that would expand "~" (shlex.quote is a no-op for a plain path)
    script = escape(shlex.quote(WORKSPACE_SCRIPT))
    nxt, prv = ("LEFT", "RIGHT") if g["natural"] else ("RIGHT", "LEFT")

    def swipe(direction, what):
        return ('    <gesture type="SWIPE" fingers="3" direction="%s">\n'
                '      <action type="RUN_COMMAND">\n'
                '        <repeat>false</repeat>\n'
                '        <command>%s %s</command>\n'
                '        <on>begin</on>\n'
                '      </action>\n'
                '    </gesture>\n' % (direction, script, what))
    gestures = (swipe(nxt, "next") + swipe(prv, "prev")) if g["enabled"] else ""
    return ('<!-- Touchpad gestures for i3 (Settings > Mouse & touchpad > Touchpad gestures). Written by the settings\n'
            '     window: three fingers %s = next workspace, %s = previous. Edits here are replaced on Apply. -->\n'
            '<touchégg>\n'
            '  <settings>\n'
            '    <property name="animation_delay">150</property>\n'
            '    <property name="action_execute_threshold">20</property>\n'
            '    <property name="color">auto</property>\n'
            '    <property name="borderColor">auto</property>\n'
            '  </settings>\n'
            '  <application name="All">\n'
            '%s'
            '  </application>\n'
            '</touchégg>\n' % (nxt.lower(), prv.lower(), gestures))


def touchegg_state():
    """'missing' (not installed), 'stopped' (its service is not running) or 'ok'."""
    if not shutil.which("touchegg"):
        return "missing"
    return "ok"


def apply_gestures(settings):
    """Write the gesture config, then (re)start the Touchégg client so it takes effect."""
    path = os.path.realpath(TOUCHEGG_CONF)
    changed = _write_generated(path, touchegg_conf(settings))
    if DRY or FILES_ONLY or not os.path.exists(GESTURES_SCRIPT):
        return
    subprocess.Popen([GESTURES_SCRIPT] + (["restart"] if changed else []), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------ top bar (polybar)
BAR_DEFAULT = {"position": "top", "monitors": None, "size": "large", "style": "solid", "divider": "rounded",
               "title": False, "media": False, "spacing": 12,
               "bg_mode": "solid", "bg_opacity": 70, "bg_color": "#000000"}
# the bar's own background (the dark part around the blocks - the blocks themselves never change): solid, see-through
# (bg_opacity, 0-100 %) or blurred (see-through, and picom blurs what is behind it), in any colour (bg_color)
BAR_BG_MODES = [("solid", "Solid"), ("transparent", "See-through"), ("blur", "Blurred (see-through, frosted)")]
BAR_SPACING_MAX = 40          # px between two blocks (even numbers: half of it goes on each side of a block)
# monitors None = every monitor
BAR_STYLES = [("solid", "One colour - every item in its own block"),
              ("gradient", "Gradient - blocks from dark to your colour"),
              ("sunset", "Sunset - blocks from your colour to dark"),
              ("alternate", "Alternating - blocks in two shades"),
              ("duo", "Two-tone - your colour and charcoal, taking turns"),
              ("dark", "Dark - dark blocks, text in your colour"),
              ("charcoal", "Charcoal - grey blocks, white text"),
              ("spotlight", "Spotlight - grey blocks, the clock and power in your colour"),
              ("pill", "Pill - every item in one long block"),
              ("darkpill", "Dark pill - one long dark block, text in your colour"),
              ("powerline", "Powerline - blocks joined in a chain"),
              ("underline", "Underline - text over a line in your colour"),
              ("glow", "Glow - plain text in your colour"),
              ("flat", "Flat - plain text (the classic look)")]
# the styles "Block shape" applies to (the ones made of blocks)
BAR_SHAPED = ("solid", "gradient", "sunset", "alternate", "duo", "dark", "charcoal", "spotlight", "pill", "darkpill",
              "powerline")
BAR_JOINED = ("pill", "darkpill", "powerline")      # blocks joined into one: no space between them
BAR_STYLE_ALIASES = {"blocks": "solid"}          # older settings: the first block style
BAR_DIVIDERS = [("rounded", "Rounded"), ("arrows", "Arrows"), ("slanted", "Slanted"), ("square", "Square"),
                ("backslant", "Backslant"), ("tab", "Tab - wider at the bottom"), ("hanging", "Hanging - wider at the top"),
                ("tag", "Tag - flat start, pointed end"), ("flag", "Flag - pointed start, flat end"),
                ("bullet", "Bullet - flat start, round end"), ("leaf", "Leaf - round start, pointed end"),
                ("wing", "Wing - slanted start, round end")]
# the Nerd Font powerline glyphs drawn at the left / right end of a block ("" = a flat end). All of them are as tall
# as the bar (2168 font units) and 1060 wide, which is what BAR_SIZES below is measured for.
CAP_ROUND_L, CAP_ROUND_R = "\ue0b6", "\ue0b4"            # half circles
CAP_ARROW_L, CAP_ARROW_R = "\ue0b2", "\ue0b0"            # points
CAP_LOWR, CAP_UPL = "\ue0ba", "\ue0bc"                   # lower-right / upper-left triangles ("/" ends)
CAP_UPR, CAP_LOWL = "\ue0be", "\ue0b8"                   # upper-right / lower-left triangles ("\\" ends)
# each end seen in a mirror: the workspaces on the left of the bar are the mirror image of the items on the right,
# so a one-sided shape (Flag, Tag, Slanted, ...) points to the middle of the bar on both sides
CAP_MIRROR = {CAP_ROUND_L: CAP_ROUND_R, CAP_ROUND_R: CAP_ROUND_L, CAP_ARROW_L: CAP_ARROW_R, CAP_ARROW_R: CAP_ARROW_L,
              CAP_LOWR: CAP_LOWL, CAP_LOWL: CAP_LOWR, CAP_UPL: CAP_UPR, CAP_UPR: CAP_UPL, "": ""}
BAR_CAPS = {"rounded": (CAP_ROUND_L, CAP_ROUND_R), "arrows": (CAP_ARROW_L, CAP_ARROW_R),
            "slanted": (CAP_LOWR, CAP_UPL), "square": ("", ""),
            "backslant": (CAP_UPR, CAP_LOWL), "tab": (CAP_LOWR, CAP_LOWL), "hanging": (CAP_UPR, CAP_UPL),
            "tag": ("", CAP_ARROW_R), "flag": (CAP_ARROW_L, ""), "bullet": ("", CAP_ROUND_R),
            "leaf": (CAP_ROUND_L, CAP_ARROW_R), "wing": (CAP_LOWR, CAP_ROUND_R)}
# Each size, measured on polybar 3.7 so that everything lands on whole pixels:
#   height  the bar in px (plus its 1 px line)
#   text    (size in px, vertical offset that centres it); icon: the same for the bigger icons (mug, power)
#   cap     (height in px the block-end glyph is drawn at, its offset): half a pixel to a pixel taller than the bar,
#           so its flat side covers the block's edge completely (no seam) and the curve is barely trimmed
# Whole-pixel text matters with this font: at 16 px its capitals are exactly 10 px tall and the letters come out
# clearly sharper than at 17 px. (Polybar turns "pixelsize=13" into 16.6 px, which is why Normal looked soft.)
BAR_SIZES = {"small": {"height": 24, "text": (13, 2), "icon": (16, 3), "cap": (24.5, 4)},
             "normal": {"height": 30, "text": (16, 3), "icon": (20, 3), "cap": (31.5, 5)},
             "large": {"height": 38, "text": (18, 3), "icon": (22, 4), "cap": (38.5, 5)},
             "xlarge": {"height": 44, "text": (22, 4), "icon": (26, 4), "cap": (45, 7)}}
BAR_SIZE_LABELS = [("small", "Small - 24 px tall, 13 px text"), ("normal", "Normal - 30 px tall, 16 px text"),
                   ("large", "Large - 38 px tall, 18 px text (default)"), ("xlarge", "Extra large - 44 px tall, 22 px text")]
BAR_FONT_FAMILY = "FantasqueSansM Nerd Font Mono"
GLYPH_EM = 2048               # the font's units per em; a block-end glyph is 2168 units tall and 1060 wide (advance)
CAP_GLYPH_H, CAP_GLYPH_W = 2168, 1060
# the items on the right of the bar, left to right ("playerctl" - what is playing - goes first when switched on)
BAR_ITEMS = ("network", "bluetooth", "pulseaudio", "backlight", "caffeine", "nightlight", "battery", "cpu", "memory",
             "gpu", "date", "powermenu")
POLYBAR_STYLE = os.path.join(_CFG_HOME, "polybar", "style.ini")


def bar_choice(settings):
    """The saved bar settings, each one checked: anything unknown or damaged gives the default."""
    bar = settings.get("bar") if isinstance(settings.get("bar"), dict) else {}

    def pick(key, allowed):
        v = bar.get(key)
        v = BAR_STYLE_ALIASES.get(v, v) if isinstance(v, str) else None
        return v if v in allowed else BAR_DEFAULT[key]
    mons = bar.get("monitors")
    return {"bottom": bar.get("position") == "bottom", "size": pick("size", BAR_SIZES),
            "style": pick("style", dict(BAR_STYLES)), "divider": pick("divider", dict(BAR_DIVIDERS)),
            "title": bar.get("title") is True, "media": bar.get("media") is True,
            "spacing": clean_spacing(bar.get("spacing")),
            "bg_mode": pick("bg_mode", dict(BAR_BG_MODES)),
            "bg_opacity": _num(bar.get("bg_opacity"), 0, 100) if _num(bar.get("bg_opacity"), 0, 100) is not None
            else BAR_DEFAULT["bg_opacity"],
            "bg_color": norm_accent(bar.get("bg_color")) or BAR_DEFAULT["bg_color"],
            "monitors": [m for m in mons if isinstance(m, str)] if isinstance(mons, list) else []}


def bar_bg_value(mode, opacity, color):
    """The bar's background for polybar: '#AARRGGBB' (solid = fully opaque; see-through and blurred use the slider).
    Needs the compositor (picom) for the see-through part, like window opacity."""
    alpha = 255 if mode == "solid" else round(max(0, min(100, opacity)) * 2.55)
    return "#%02x%s" % (alpha, (norm_accent(color) or "#000000")[1:])


def clean_spacing(value):
    """The space between blocks: a whole, even number of px from 0 to BAR_SPACING_MAX, else the default."""
    v = _num(value, 0, BAR_SPACING_MAX)
    return BAR_DEFAULT["spacing"] if v is None else v - v % 2


def bar_font_spec(px, offset):
    """A polybar font line drawing the bar font at exactly `px` pixels. Polybar turns a point size into pixels at
    its dpi (fixed to 96 in config.ini), so px * 0.75 points is exact; "pixelsize=" would be rescaled and blur."""
    pt = ("%.3f" % (px * 0.75)).rstrip("0").rstrip(".")
    return "%s:size=%s;%d" % (BAR_FONT_FAMILY, pt, offset)


def bar_fonts(size):
    """(text, icon, block-end) polybar font lines for a bar size."""
    s = BAR_SIZES[size]
    cap_h, cap_off = s["cap"]
    return bar_font_spec(*s["text"]), bar_font_spec(*s["icon"]), bar_font_spec(cap_h * GLYPH_EM / CAP_GLYPH_H, cap_off)


_platform_cache = {}


def platform_has(what):
    """Platform.sh has WHAT (battery, backlight, wifi, volume): asked once per run of this program."""
    if what not in _platform_cache:
        try:
            r = subprocess.run(["sh", os.path.join(SCRIPTS_DIR, "Platform.sh"), "has", what],
                               capture_output=True, timeout=15)
            _platform_cache[what] = r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _platform_cache[what] = False
    return _platform_cache[what]


def bar_items(choice):
    """The items on the right of the bar, left to right. An item this computer has no hardware for (battery on a
    desktop, Wi-Fi, Bluetooth, screen brightness, a GPU sensor) is left out instead of leaving an empty block.
    (Bluetooth: its bar item uses BlueZ, which only runs on Linux.)"""
    have = {"network": platform_has("wifi"), "bluetooth": False, "pulseaudio": platform_has("volume"),
            "backlight": platform_has("backlight"), "battery": platform_has("battery"),
            "gpu": bool(shutil.which("nvidia-smi"))}
    return (["playerctl"] if choice["media"] else []) + [m for m in BAR_ITEMS if have.get(m, True)]


def mix(c1, c2, t):
    """c1 blended into c2: t=1 gives c1, t=0 gives c2."""
    return "#%02x%02x%02x" % tuple(round(int(c1[i:i + 2], 16) * t + int(c2[i:i + 2], 16) * (1 - t)) for i in (1, 3, 5))


def bar_colors(accent):
    """Every colour of the bar for one accent colour (polybar/colors.ini holds the same values)."""
    a = norm_accent(accent) or ACCENT_DEFAULT
    second, dark = shade(a, 0.6), mix(a, "#141414", 0.16)
    c = {"background": "#f2000000", "background-alt": "#1c1c1c", "foreground": "#e6e6e6", "primary": a,
         "secondary": shade(a, 0.75), "alert": a, "disabled": "#6e6e6e", "line": "#303030",
         "block": a, "blockfg": readable_on(a),                      # one colour
         "block2": second, "block2fg": readable_on(second),          # alternating: the second shade
         "dark": dark, "darkfg": a}                                  # dark blocks, text in the colour
    for i, (bg, fg) in enumerate(bar_segments(a), 1):                # gradient / powerline: dark -> the colour
        c["seg%d" % i], c["segfg%d" % i] = bg, fg
    return c


def bar_style_rows(style, divider, items, height, col, spacing=BAR_DEFAULT["spacing"], bar_bg=None):
    """How each item on the right of the bar looks in a style: block colour (bg), text colour (fg), underline (ul),
    the glyphs at its left / right end (l, r) with their colours, and the space on each side of it (gap, px).
    `spacing` is the room between two blocks (each block gets half of it on either side); joined-up styles have none.
    An end glyph " " is a gap the width of a block end, used between the items of a joined-up style.
    `col(name)` turns a colours.ini name into a value: a reference for polybar, #rrggbb for the preview.
    Returns ({item: {...}}, {bar-wide values: underline size, the flat bar's item spacing, focused workspace})."""
    left, right = BAR_CAPS[divider] if style in BAR_SHAPED else ("", "")
    bar_bg = bar_bg or col("background")        # the bar's own background (Settings: solid / see-through / blurred)
    rows = {}
    half = clean_spacing(spacing) // 2

    def block(m, bg, fg, lcap=left, lbg=bar_bg, rcap=right, gap=half, ul=None):
        rows[m] = {"bg": bg, "fg": fg, "ul": ul or bg, "l": lcap, "lfg": bg, "lbg": lbg,
                   "r": rcap, "rfg": bg, "rbg": bar_bg, "gap": gap, "lead": 0}

    def shade_of(i, n):                         # position i of n -> one of the 13 colours from dark to the colour
        k = 1 + (round(12 * i / (n - 1)) if n > 1 else 12)
        return col("seg%d" % k), col("segfg%d" % k)

    if style in BAR_JOINED:
        # what is playing comes and goes, so it keeps a block of its own instead of breaking the chain
        if "playerctl" in items:
            block("playerctl", col("block"), col("blockfg"))
        chain = [m for m in items if m != "playerctl"]
        prev = bar_bg
        for i, m in enumerate(chain):
            last = i == len(chain) - 1
            if style in ("pill", "darkpill"):   # one block: the ends on the outside, a little room between items
                bg, fg = (col("block"), col("blockfg")) if style == "pill" else (col("dark"), col("darkfg"))
                block(m, bg, fg, lcap=left if i == 0 else " ", lbg=bar_bg if i == 0 else bg,
                      rcap=right if last else "", gap=0)
            else:                               # each block's left end cuts into the block before it
                bg, fg = shade_of(i, len(chain))
                if left or i == 0:
                    block(m, bg, fg, lbg=prev, rcap=right if last else "", gap=0)
                else:                           # square: the blocks just meet, with a little room in each
                    block(m, bg, fg, lcap=" ", lbg=bg, rcap="", gap=0)
                prev = bg
    else:
        for i, m in enumerate(items):
            if style == "gradient":
                block(m, *shade_of(i, len(items)))
            elif style == "sunset":
                block(m, *shade_of(len(items) - 1 - i, len(items)))
            elif style == "duo":
                block(m, *((col("block"), col("blockfg")) if i % 2 == 0 else (col("line"), col("foreground"))))
            elif style == "charcoal":
                block(m, col("line"), col("foreground"))
            elif style == "spotlight":
                block(m, *((col("block"), col("blockfg")) if m in ("date", "powermenu")
                           else (col("line"), col("foreground"))))
            elif style == "glow":
                block(m, bar_bg, col("primary"))
            elif style == "alternate":
                block(m, *((col("block"), col("blockfg")) if i % 2 == 0 else (col("block2"), col("block2fg"))))
            elif style == "dark":
                block(m, col("dark"), col("darkfg"))
            elif style == "underline":
                block(m, bar_bg, col("foreground"), ul=col("primary"))
            else:
                block(m, col("block"), col("blockfg"))
    if style not in BAR_JOINED and items:
        # the last block (the power button) sits right at the screen edge: its space goes only on its left side
        last = rows[items[-1]]
        last["lead"], last["gap"] = last["gap"], 0
    for m in ("playerctl",) + BAR_ITEMS:        # items that are not shown still need values
        if m not in rows:
            block(m, col("block"), col("blockfg"))
    bar = {"line": 0, "gap": half, "ws-bg": col("primary"), "ws-fg": col("background"), "ws-ul": col("primary"),
           "bg": bar_bg}
    if style == "underline":
        bar.update({"line": 2 if height < 34 else 3, "ws-bg": col("background-alt"), "ws-fg": col("foreground")})
    elif style in ("dark", "darkpill"):
        bar.update({"ws-bg": col("dark"), "ws-fg": col("darkfg")})
    bar["ws"] = workspace_style(style, divider, spacing)
    return rows, bar


WS_STATES = ("focused", "unfocused", "visible", "urgent", "mode")


def workspace_style(style, divider, spacing=BAR_DEFAULT["spacing"]):
    """How the workspaces on the left of the block bar look, following the items on the right:
      - separate blocks (solid, gradient, ...): each workspace is a block with the same ends, the one you are on
        in the bright colour and the others dark, the first one at the screen edge like the power button
      - joined-up styles (pill, dark pill, powerline): all of them in one strip, the one you are on a block inside
        it (its ends cut into the strip). PolybarWorkspaces.py draws that strip so its ends are the first and last
        workspace's own, flush with the numbers; the labels below (with ws-start / ws-end as the strip's ends)
        are the fallback when it cannot run
    The block ends are the mirror image of the right side's, so a one-sided shape points to the middle on both sides;
    with one of those, Powerline makes the workspaces a chain like the items on the right (see PolybarWorkspaces).
    Colours are names in bar_colors(); bg None = just text. "mode" is i3's mode (resize) when one is on."""
    shaped = style in BAR_SHAPED
    left, right = BAR_CAPS[divider] if shaped else ("", "")
    one_sided = (CAP_MIRROR[right], CAP_MIRROR[left]) != (left, right)
    left, right = CAP_MIRROR[right], CAP_MIRROR[left]
    strip = None
    if style == "pill":                                     # one block in the colour: the one you are on is dark
        strip = "block"
        focused, other, fg, vis = ("line", "foreground"), "block", "blockfg", ("block2", "block2fg")
    elif style == "darkpill":                               # one dark block: the one you are on darker still
        strip = "dark"
        focused, other, fg, vis = ("background-alt", "darkfg"), "dark", "secondary", ("dark", "darkfg")
    elif style == "powerline":                              # one charcoal chain: the one you are on in the colour
        strip = "line"
        focused, other, fg, vis = ("primary", "blockfg"), "line", "foreground", ("line", "primary")
    elif style == "dark":
        focused, other, fg, vis = ("dark", "darkfg"), "background-alt", "disabled", ("background-alt", "secondary")
    elif shaped:
        focused, other, fg, vis = ("primary", "blockfg"), "line", "foreground", ("line", "primary")
    else:                                                   # text only, the one you are on marked
        focused = ("background-alt", "foreground") if style == "underline" else ("primary", "background")
        other, fg, vis = None, "disabled", (None, "secondary")
    joined = strip is not None
    space = clean_spacing(spacing)
    return {"shaped": shaped, "joined": joined, "strip": strip, "l": left, "r": right,
            "chain": style == "powerline" and one_sided, "thin": "background-alt",
            "gap": space if shaped and not joined else 0,          # between two workspaces
            "end-gap": space if joined else 0,                     # after the strip (separate blocks: "gap" does it)
            "focused": focused, "unfocused": (other, fg), "visible": vis,
            "urgent": ("secondary", "background"), "mode": focused}


def workspace_label(ws, state, colour, text="%name%"):
    """The polybar label for workspaces in one state (focused / unfocused / visible / urgent / mode): its colours
    and end glyphs are written into the text as format tags. Separate blocks: each workspace a block of its own.
    Joined: a piece of the strip - either just the strip with room where the ends would be (so nothing shifts
    when you switch), or a block inside it. `colour(name)` gives #rrggbb (a reference cannot go inside a tag)."""
    bg, fg = ws[state]
    if bg is None:                                             # text only (the underline / glow styles)
        return "%%{F%s}  %s  %%{F-}" % (colour(fg), text)
    pad = " " if ws["shaped"] else "  "
    if ws["joined"]:
        strip = colour(ws["strip"])
        inner = bg != ws["strip"]

        def end(glyph):
            if not glyph:
                return ""
            return "%%{T3}%%{F%s}%s%%{T-}" % (colour(bg), glyph) if inner else "%{T3} %{T-}"
        return "%%{B%s}%s%%{B%s}%%{F%s}%s%s%s%%{B%s}%s%%{B-}%%{F-}" % (
            strip, end(ws["l"]), colour(bg), colour(fg), pad, text, pad, strip, end(ws["r"]))
    out = ""
    if ws["l"]:
        out += "%%{T3}%%{F%s}%s%%{T-}" % (colour(bg), ws["l"])
    out += "%%{B%s}%%{F%s}%s%s%s%%{B-}" % (colour(bg), colour(fg), pad, text, pad)
    if ws["r"]:
        out += "%%{T3}%%{F%s}%s%%{T-}" % (colour(bg), ws["r"])
    return out + "%{F-}"


def workspace_ends(ws, colour):
    """(start, end) of the joined-up strip: its outer ends, drawn before the first and after the last workspace."""
    if not ws["joined"]:
        return "", ""
    c = colour(ws["strip"])
    return tuple("%%{T3}%%{F%s}%s%%{T-}%%{F-}" % (c, g) if g else "" for g in (ws["l"], ws["r"]))


def saved_accent(settings):
    cfg = settings.get("colors")
    a = norm_accent(cfg.get("accent")) if isinstance(cfg, dict) else None
    return a if a and brightness(a) >= ACCENT_MIN_BRIGHT else ACCENT_DEFAULT


def _colors_ini_names():
    """The colour names polybar/colors.ini defines (an older or hand-edited file may lack the newer ones)."""
    names, section = set(), None
    try:
        with open(POLYBAR_COLORS) as f:
            for line in f:
                s = line.strip()
                if s.startswith("["):
                    section = s.strip("[]").strip()
                elif section == "colors" and "=" in s and not s.startswith((";", "#")):
                    names.add(s.split("=", 1)[0].strip())
    except (OSError, UnicodeDecodeError):
        pass
    return names


def bar_style_ini(settings):
    """polybar/style.ini for the saved style: every item's colours and end glyphs. Colours are references into
    colors.ini (so a hand edit there still counts); a name colors.ini lacks is written as a plain value."""
    choice = bar_choice(settings)
    names, values = _colors_ini_names(), bar_colors(saved_accent(settings))

    def col(name):
        return "${colors.%s}" % name if name in names else values[name]
    rows, bar = bar_style_rows(choice["style"], choice["divider"], bar_items(choice),
                               BAR_SIZES[choice["size"]]["height"], col, choice["spacing"],
                               bar_bg_value(choice["bg_mode"], choice["bg_opacity"], choice["bg_color"]))

    def value(k, v):
        if k == "gap":
            return "%dpx" % v                       # spacing in pixels (a bare number would mean spaces)
        if k == "lead":
            return "%d" % v                         # polybar's format-offset: pixels, room on the left only
        return '" "' if v == " " else v              # (a value that is a space is quoted, or polybar would drop it)
    out = ["; How the bar's blocks look (Settings > Appearance > Bar style). Written by the settings window each time",
           "; the bar starts, so edits here are replaced: change colours in colors.ini, or blocks.ini for the layout.",
           "[barstyle]"]
    out += [("%s = %s" % (k, value(k, v))).rstrip() for k, v in bar.items() if k != "ws"]
    # the workspaces: whole labels (colours as #rrggbb: a ${colors.x} reference cannot go inside a format tag)
    ws = bar["ws"]
    out += ["ws-%s = %s" % (st, workspace_label(ws, st, lambda n: values[n], "%mode%" if st == "mode" else "%name%"))
            for st in WS_STATES]
    start, end = workspace_ends(ws, lambda n: values[n])
    out += [("ws-start = %s" % start).rstrip(), ("ws-end = %s" % end).rstrip(),
            "ws-gap = %dpx" % ws["gap"], "ws-end-gap = %dpx" % ws["end-gap"]]
    # the same for the joined-up styles' workspace strip (PolybarWorkspaces.py draws it: it knows which workspace
    # is first and last, so the strip's ends are theirs)
    out += [("ws-strip = %s" % (values[ws["strip"]] if ws["strip"] else "")).rstrip(),
            ("ws-cap-l = %s" % ws["l"]).rstrip(), ("ws-cap-r = %s" % ws["r"]).rstrip(),
            "ws-chain = %s" % ("true" if ws["chain"] else "false"), "ws-thin = %s" % values[ws["thin"]]]
    out += [("ws-colors-%s = %s" % (st, "%s %s" % (values[ws[st][0]], values[ws[st][1]])
                                     if ws[st][0] else "")).rstrip() for st in WS_STATES]
    for m in ("playerctl",) + BAR_ITEMS:
        out += [("%s-%s = %s" % (m, k, value(k, v))).rstrip() for k, v in rows[m].items()]
    return "\n".join(out) + "\n"


def write_bar_style(settings):
    if os.path.isdir(os.path.dirname(POLYBAR_STYLE)):
        _write_generated(POLYBAR_STYLE, bar_style_ini(settings))


def bar_modules(items):
    """The polybar module for each item."""
    return list(items)


def bar_env(settings):
    """Shell assignments for polybar/launch.sh."""
    choice = bar_choice(settings)
    text, icon, cap = bar_fonts(choice["size"])
    items = bar_items(choice)
    env = {"BAR_BOTTOM": "true" if choice["bottom"] else "false", "BAR_HEIGHT": BAR_SIZES[choice["size"]]["height"],
           "BAR_FONT_SPEC": text, "BAR_ICON_SPEC": icon, "BAR_CAP_SPEC": cap,
           "BAR_STYLE": choice["style"], "BAR_DIVIDER": choice["divider"],
           "BAR_NAME": "main" if choice["style"] == "flat" else "blocks",
           "BAR_LEFT": "i3 xwindow" if choice["title"] else "i3",
           # the workspaces: polybar's module, or (joined-up styles) the strip PolybarWorkspaces.py draws
           "BAR_LEFT_B": ("b-wsj" if choice["style"] in BAR_JOINED else "b-i3") + (" xwindow" if choice["title"] else ""),
           "BAR_RIGHT": " ".join(bar_modules(items)), "BAR_RIGHT_B": " ".join("b-" + m for m in bar_modules(items)),
           "BAR_MONITORS": " ".join(choice["monitors"])}
    return "\n".join("%s=%s" % (k, shlex.quote(str(v))) for k, v in env.items())


def i3bar_conf(settings):
    """i3's own bar (i3bar), used where polybar is not installed - NetBSD has no package of it: the position, text
    size, colours and monitors of the bar you chose; I3barStatus.py fills in the items. polybar/launch.sh writes this
    to i3/bar-fallback.conf (which the i3 config includes) only when there is no polybar."""
    choice = bar_choice(settings)
    c = bar_colors(saved_accent(settings))
    pt = ("%.2f" % (BAR_SIZES[choice["size"]]["text"][0] * 0.75)).rstrip("0").rstrip(".")
    bg = norm_accent(choice["bg_color"]) or "#000000"
    out = ["# i3's own bar, written by polybar/launch.sh because polybar is not installed (NetBSD has no package of",
           "# it): the bar you chose in Settings > Appearance, as far as i3bar can show it. Empty with polybar.",
           "bar {",
           "    id i3dots",
           '    status_command exec "$HOME/.config/i3/scripts/I3barStatus.py"',
           "    position %s" % ("bottom" if choice["bottom"] else "top"),
           "    font pango:%s %s" % (BAR_FONT_FAMILY, pt),
           "    strip_workspace_numbers yes",
           '    separator_symbol " "']
    out += ["    output %s" % m for m in choice["monitors"] if re.match(r"^[A-Za-z0-9_.:-]+$", m)]
    out += ["    colors {",
            "        background %s" % bg,
            "        statusline %s" % c["foreground"],
            "        separator %s" % c["line"],
            "        focused_workspace  %s %s %s" % (c["primary"], c["primary"], c["blockfg"]),
            "        active_workspace   %s %s %s" % (c["line"], c["line"], c["foreground"]),
            "        inactive_workspace %s %s %s" % (c["line"], c["line"], c["foreground"]),
            "        urgent_workspace   %s %s %s" % (c["secondary"], c["secondary"], "#000000"),
            "        binding_mode       %s %s %s" % (c["primary"], c["primary"], c["blockfg"]),
            "    }",
            "}"]
    return "\n".join(out)


# ------------------------------------------------------------------ bar pictures (settings window)
# sample text for each item: (with the bar's icon font, without it)
PREVIEW_TEXT = {"playerctl": ("󰎈 Song - Artist", "Song - Artist"), "network": ("󰤨 Home 82%", "Wi-Fi 82%"),
                "bluetooth": ("󰂯", "BT"), "pulseaudio": ("󰕾 60%", "Vol 60%"), "backlight": ("󰃟 75%", "Light 75%"),
                "caffeine": ("󰛊", "Awake"), "nightlight": ("󰖙", "Night"), "battery": ("󰁹 87%", "Bat 87%"),
                "cpu": ("󰻠 12%", "CPU 12%"), "memory": ("󰍛 34%", "RAM 34%"), "gpu": ("󰢮 GPU 5%", "GPU 5%"),
                "date": (None, None), "powermenu": ("󰐥", "Power")}
# the small pictures in the dropdowns: a few items with short text
THUMB_TEXT = {"network": ("󰤨", "Wi-Fi"), "pulseaudio": ("󰕾 60", "60%"), "date": ("12:30", "12:30")}
THUMB_SIZE = (232, 26)
THUMB_FONT = {"height": 26, "text": (13, 0), "icon": (13, 0), "cap": (27, 0)}     # (offsets unused in pictures)
THUMB_SPACING = 6
_font_ok = {}


def _rgba(value):
    """'#rrggbb' or polybar's '#aarrggbb' -> (r, g, b, a) from 0 to 1."""
    v = value.lstrip("#")
    a = int(v[:2], 16) / 255 if len(v) == 8 else 1.0
    v = v[2:] if len(v) == 8 else v
    return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


_ws_module = {}


def _workspace_module():
    """PolybarWorkspaces.py (next to this file), which lays out the joined-up workspace strip; None if it cannot be
    loaded (the picture then draws the strip the simpler way polybar's own module does)."""
    if "m" not in _ws_module:
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PolybarWorkspaces.py")
        try:
            spec = importlib.util.spec_from_file_location("PolybarWorkspaces", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _ws_module["m"] = mod if callable(getattr(mod, "plan", None)) else None
        except Exception:                                   # (a missing or broken file must not stop the window)
            _ws_module["m"] = None
    return _ws_module["m"]


CAP_THIN = {chr(c + 1): chr(c) for c in range(0xe0b0, 0xe0c0, 2)}     # thin outline -> its solid block end


def _thin_edge(cr, solid, x, top, cw, h, ry, rgba):
    """Draw the thin outline glyph of the block end `solid` (the line where two blocks of one colour meet in a
    chain): the slanted, pointed or round edge of that end, as a line about as thick as the font draws it."""
    ym, y1, y2 = top + h / 2, top + h / 2 - ry, top + h / 2 + ry
    cr.save()
    cr.rectangle(x, top, cw, h)
    cr.clip()
    cr.new_path()
    if solid in (CAP_ROUND_L, CAP_ROUND_R):
        cr.save()
        cr.translate(x + cw if solid == CAP_ROUND_L else x, ym)
        cr.scale(cw, ry)
        if solid == CAP_ROUND_L:
            cr.arc(0, 0, 1, 0.5 * math.pi, 1.5 * math.pi)
        else:
            cr.arc_negative(0, 0, 1, 0.5 * math.pi, -0.5 * math.pi)
        cr.restore()
    else:
        pts = {CAP_ARROW_L: ((x + cw, y1), (x, ym), (x + cw, y2)), CAP_ARROW_R: ((x, y1), (x + cw, ym), (x, y2)),
               CAP_LOWR: ((x + cw, y1), (x, y2)), CAP_UPL: ((x + cw, y1), (x, y2)),
               CAP_UPR: ((x, y1), (x + cw, y2)), CAP_LOWL: ((x, y1), (x + cw, y2))}[solid]
        cr.move_to(*pts[0])
        for pt in pts[1:]:
            cr.line_to(*pt)
    cr.set_source_rgba(*rgba)
    cr.set_line_width(max(1.0, cw * 0.09))
    cr.stroke()
    cr.restore()


def paint_bar(cr, width, style, divider, accent, size="large", items=None, title=False, bottom=False, thumb=False,
              spacing=BAR_DEFAULT["spacing"], bar_bg=None, blur=False):
    """Draw the bar as polybar will show it in a style (same colours, block ends and spacing: see bar_style_rows),
    on the cairo context `cr`, `width` pixels wide. thumb=True draws the small dropdown picture instead: a few
    items, no workspaces. Shrinks the drawing to fit when the bar would be wider than `width`."""
    from gi.repository import Pango, PangoCairo
    if "ok" not in _font_ok:
        names = {f.get_name() for f in PangoCairo.FontMap.get_default().list_families()}
        _font_ok["ok"] = BAR_FONT_FAMILY in names
    nerd = _font_ok["ok"]
    family = BAR_FONT_FAMILY if nerd else "monospace"
    pal = bar_colors(accent)
    if thumb:
        dims, spacing = THUMB_FONT, THUMB_SPACING
        items = list(THUMB_TEXT)
        texts = {m: THUMB_TEXT[m][0 if nerd else 1] for m in items}
    else:
        dims = BAR_SIZES[size if size in BAR_SIZES else "large"]
        items = list(items if items is not None else BAR_ITEMS)
        texts = {m: PREVIEW_TEXT[m][0 if nerd else 1] for m in items}
        if "date" in texts:
            import time
            texts["date"] = time.strftime("%a %d %b  %H:%M")
    h, font_px, icon_px = dims["height"], dims["text"][0], dims["icon"][0]
    rows, extra = bar_style_rows(style, divider, items, h, lambda n: pal[n], spacing, None if thumb else bar_bg)
    layout = PangoCairo.create_layout(cr)

    def measure(text, px):
        fd = Pango.FontDescription.from_string(family)
        fd.set_absolute_size(px * Pango.SCALE)
        layout.set_font_description(fd)
        layout.set_text(text, -1)
        return layout.get_pixel_size()
    space = measure(" ", font_px)[0]
    # the end glyphs as polybar draws them (BAR_SIZES "cap"): a little taller than the bar, as wide as the glyph's
    # advance at that size, rounded up like polybar does
    cap_h = dims["cap"][0]
    cap_w, cap_ry = math.ceil(cap_h * CAP_GLYPH_W / CAP_GLYPH_H), cap_h / 2

    # lay out the right-hand items: [(kind, x, w, ...)]
    parts, x = [], 0
    for m in items:
        txt = texts[m]
        px = icon_px if m in ("caffeine", "powermenu") and nerd and not thumb else font_px
        if style == "flat":
            if m in ("cpu", "memory") and nerd:                   # the flat bar spells these out
                txt = txt.replace(" ", " CPU " if m == "cpu" else " RAM ", 1)
            fg = pal["primary"] if m == "date" else pal["secondary"] if m in ("caffeine", "nightlight", "playerctl") \
                else pal["foreground"]
            x += extra["gap"]
            tw = measure(txt, px)[0]
            parts.append(("text", x, tw, txt, px, fg, None))
            x += tw + extra["gap"]
            continue
        r = rows[m]
        x += r["lead"] + r["gap"]
        start = x
        if r["l"]:
            parts.append(("cap", x, cap_w, r["l"], r["lfg"], r["lbg"]))
            x += cap_w
        inner = measure(txt, px)[0]                              # (the spaces around it are in the text font)
        tw = inner + 2 * space
        joined = r["gap"] == 0 and not r["lead"]                 # touches the items next to it
        parts.append(("box", x, tw, r["bg"], bool(r["l"]) or joined, bool(r["r"]) or joined))
        parts.append(("text", x + space, inner, txt, px, r["fg"], None))
        x += tw
        if r["r"]:
            parts.append(("cap", x, cap_w, r["r"], r["rfg"], r["rbg"]))
            x += cap_w
        if extra["line"]:
            parts.append(("line", start, x - start, r["ul"]))
        x += r["gap"]
    right_w = x + (space if style == "flat" and not thumb else 0)  # (the block bar has no right padding: the power
                                                                   # button reaches the screen edge)

    # the left-hand side: workspaces (and the window title)
    left, lx = [], 0
    ws = extra["ws"]                                               # (see workspace_style: as polybar draws them)
    names = ("I", "II", "III")
    wsmod = _workspace_module() if ws["joined"] and not thumb else None
    if wsmod:
        # the joined-up styles: laid out by PolybarWorkspaces.plan(), exactly as the bar draws them
        st = {"strip": pal[ws["strip"]], "l": ws["l"], "r": ws["r"], "chain": ws["chain"], "thin": pal[ws["thin"]]}
        st.update({s: (pal[ws[s][0]], pal[ws[s][1]]) for s in WS_STATES})
        states = ["focused" if i == 0 else "unfocused" for i in range(len(names))]
        flat = [p for pieces in wsmod.plan(list(zip(names, states)), st) for p in pieces]
        for k, p in enumerate(flat):
            beside = (k > 0, k < len(flat) - 1)                    # (a block reaches under what touches it)
            if p[0] == "cap":
                left.append(("cap", lx, cap_w, p[1], p[2], p[3] or extra["bg"]))
                lx += cap_w
            elif p[0] == "room":
                left.append(("box", lx, cap_w, p[1]) + beside)
                lx += cap_w
            else:
                txt = " %s " % p[1]
                tw = measure(txt, font_px)[0]
                left.append(("box", lx, tw, p[3]) + beside)
                left.append(("text", lx, tw, txt, font_px, p[2], None))
                lx += tw
        lx += ws["end-gap"]
    elif not thumb:
        strip = pal[ws["strip"]] if ws["joined"] else None
        for i, name in enumerate(names):
            bg, fg = ws["focused" if i == 0 else "unfocused"]
            pad = " " if ws["shaped"] else "  "
            txt = pad + name + pad
            tw = measure(txt, font_px)[0]
            if bg is None:                                         # just text
                left.append(("text", lx, tw, txt, font_px, pal[fg], None))
                lx += tw
                continue
            start = lx
            inner = not strip or bg != ws["strip"]                 # (a joined strip: a block inside it, or not)
            for side in ("l", "r"):
                if side == "r":
                    left.append(("box", lx, tw, pal[bg], bool(ws["l"]) or bool(strip), bool(ws["r"]) or bool(strip)))
                    left.append(("text", lx, tw, txt, font_px, pal[fg], None))
                    lx += tw
                if ws[side]:
                    # (joined: the strip's two outer ends are the first / last workspace's own, on the bar -
                    # as PolybarWorkspaces.py draws them)
                    outer = not strip or (i == 0 if side == "l" else i == len(names) - 1)
                    if outer or inner:
                        left.append(("cap", lx, cap_w, ws[side], pal[bg], extra["bg"] if outer else strip))
                    else:                                          # just the strip, as wide as an end
                        left.append(("box", lx, cap_w, strip, True, True))
                    lx += cap_w
            if i == 0 and extra["line"]:
                left.append(("line", start, lx - start, extra["ws-ul"]))
            lx += ws["gap"]
        lx += ws["end-gap"]
    if not thumb:
        if title:
            tw = measure("  Terminal - zsh  ", font_px)[0]
            left.append(("text", lx + space, tw, "  Terminal - zsh  ", font_px, pal["disabled"], None))
            lx += tw + space

    need = lx + right_w + (0 if thumb else 4 * space)
    scale = min(1.0, width / need) if need else 1.0
    full_h = h if thumb else h + 1                                 # + the bar's 1 px border line
    cr.save()
    cr.scale(scale, scale)
    w = width / scale
    y0 = (full_h / scale - full_h) / 2                             # keep a shrunk bar centred
    cr.translate(0, y0)
    if thumb:
        cr.set_source_rgba(0, 0, 0, 1)
        cr.rectangle(0, 0, w, h)
        cr.fill()
    else:
        bg = _rgba(extra["bg"])
        if bg[3] < 1:
            # a see-through bar: show it over a stand-in wallpaper (soft blobs, smoothed when blurred)
            import cairo
            g = cairo.LinearGradient(0, 0, w, 0)
            g.add_color_stop_rgb(0, 0.36, 0.47, 0.60)
            g.add_color_stop_rgb(0.5, 0.78, 0.82, 0.88)
            g.add_color_stop_rgb(1, 0.30, 0.38, 0.46)
            cr.set_source(g)
            cr.rectangle(0, 0, w, full_h)
            cr.fill()
            for i in range(int(w // 90) + 1):
                cx = i * 90 + 30
                rg = cairo.RadialGradient(cx, full_h / 2, 1, cx, full_h / 2, 28 if blur else 14)
                rg.add_color_stop_rgba(0, 0.95, 0.95, 0.95, 0.55 if blur else 0.9)
                rg.add_color_stop_rgba(1, 0.95, 0.95, 0.95, 0)
                cr.set_source(rg)
                cr.rectangle(cx - 30, 0, 60, full_h)
                cr.fill()
        cr.set_source_rgba(*bg)
        cr.rectangle(0, 0, w, full_h)
        cr.fill()
        cr.set_source_rgba(*_rgba(pal["line"]))
        cr.rectangle(0, 0 if bottom else h, w, 1)
        cr.fill()
    top = 1 if (bottom and not thumb) else 0
    off = 6 if thumb else w - right_w                              # thumbnails start at the left

    def draw(parts, dx):
        # what is behind the end glyphs first, then the blocks (reaching 2 px under whatever they touch, so
        # no hairline shows where they meet when the picture is shrunk), then the glyphs and text on top
        for p in parts:
            if p[0] == "cap":
                cr.set_source_rgba(*_rgba(p[5]))
                cr.rectangle(p[1] + dx, top, p[2], h)
                cr.fill()
        for p in parts:
            if p[0] == "box":
                cr.set_source_rgba(*_rgba(p[3]))
                cr.rectangle(p[1] + dx - (2 if p[4] else 0), top, p[2] + (2 if p[4] else 0) + (2 if p[5] else 0), h)
                cr.fill()
        for p in parts:
            kind, px0 = p[0], p[1] + dx
            if kind == "box":
                continue
            elif kind == "line":
                cr.set_source_rgba(*_rgba(p[3]))
                cr.rectangle(px0, top + h - extra["line"], p[2], extra["line"])
                cr.fill()
            elif kind == "text":
                tw, th = measure(p[3], p[4])
                cr.set_source_rgba(*_rgba(p[5]))
                cr.move_to(px0, top + (h - th) / 2)
                PangoCairo.show_layout(cr, layout)
            elif kind == "cap":
                cw, glyph = p[2], p[3]
                if glyph in CAP_THIN:                              # a thin line: the edge of that block end
                    _thin_edge(cr, CAP_THIN[glyph], px0, top, cw, h, cap_ry, _rgba(p[4]))
                    continue
                if glyph not in (CAP_ROUND_L, CAP_ROUND_R, CAP_ARROW_L, CAP_ARROW_R, CAP_LOWR, CAP_UPL, CAP_UPR,
                                 CAP_LOWL):
                    continue                                       # " ": just room, in the colour behind it
                cr.save()
                cr.rectangle(px0 - 1, top, cw + 2, h)              # the glyph is cut off at the bar's edges
                cr.clip()
                cr.set_source_rgba(*_rgba(p[4]))
                # (the glyph overlaps its block by a hair, so no seam shows between them)
                ym = top + h / 2
                y1, y2 = ym - cap_ry, ym + cap_ry
                x0, x1 = px0 - 0.5, px0 + cw + 0.5                 # the glyph's left and right edge (with the overlap)
                if glyph == CAP_ROUND_L:
                    cr.rectangle(px0 + cw - 0.5, top, 1, h)
                    cr.fill()
                    cr.translate(px0 + cw, ym)
                    cr.scale(cw, cap_ry)
                    cr.arc(0, 0, 1, 0.5 * math.pi, 1.5 * math.pi)
                elif glyph == CAP_ROUND_R:
                    cr.rectangle(px0 - 0.5, top, 1, h)
                    cr.fill()
                    cr.translate(px0, ym)
                    cr.scale(cw, cap_ry)
                    cr.arc(0, 0, 1, -0.5 * math.pi, 0.5 * math.pi)
                elif glyph == CAP_ARROW_L:                         # points left
                    cr.move_to(x1, y1)
                    cr.line_to(x1, y2)
                    cr.line_to(px0, ym)
                elif glyph == CAP_ARROW_R:                         # points right
                    cr.move_to(x0, y1)
                    cr.line_to(x0, y2)
                    cr.line_to(px0 + cw, ym)
                elif glyph == CAP_LOWR:                            # "/" left end
                    cr.move_to(x1, y1)
                    cr.line_to(x1, y2)
                    cr.line_to(px0, y2)
                elif glyph == CAP_UPL:                             # "/" right end
                    cr.move_to(x0, y1)
                    cr.line_to(px0 + cw, y1)
                    cr.line_to(x0, y2)
                elif glyph == CAP_UPR:                             # "\\" left end
                    cr.move_to(px0, y1)
                    cr.line_to(x1, y1)
                    cr.line_to(x1, y2)
                else:                                              # CAP_LOWL: "\\" right end
                    cr.move_to(x0, y1)
                    cr.line_to(x0, y2)
                    cr.line_to(px0 + cw, y2)
                cr.close_path()
                cr.fill()
                cr.restore()
    draw(left, 0)
    draw(parts, off)
    cr.restore()


BAR_BLUR_EXCLUDES = ("window_type = 'dock'", "class_g = 'Polybar'")     # in picom's blur-background-exclude


def apply_bar_blur(settings, restart=True):
    """Blurred bar background: take the bar out of picom's blur-background-exclude list (so picom blurs what is
    behind its see-through part); any other mode puts it back. Restarts picom when the file changed."""
    if not os.path.exists(PICOM_CONF):
        return
    blur = bar_choice(settings)["bg_mode"] == "blur"
    with open(PICOM_CONF) as f:
        text = orig = f.read()
    m = re.search(r"^([ \t]*blur-background-exclude[ \t]*=[ \t]*\[)(.*?)(\][ \t]*;)", text, re.M | re.S)
    if not m:
        return
    entries = [e.strip() for e in re.findall(r'"[^"]*"', m.group(2))]
    keep = [e for e in entries if e.strip('"') not in BAR_BLUR_EXCLUDES]
    if not blur:
        keep = ['"%s"' % e for e in BAR_BLUR_EXCLUDES] + keep
    text = text[:m.start()] + m.group(1) + " " + ", ".join(keep) + " " + m.group(3) + text[m.end():]
    if text == orig:
        return
    if DRY:
        print("write %s: bar blur %s" % (PICOM_CONF, "on" if blur else "off"))
        return
    with open(PICOM_CONF + ".i3tmp", "w") as f:
        f.write(text)
    os.replace(PICOM_CONF + ".i3tmp", PICOM_CONF)
    if restart and not FILES_ONLY and subprocess.run(["pgrep", "-x", "picom"], capture_output=True).returncode == 0:
        subprocess.run(["pkill", "-u", str(os.getuid()), "-x", "picom"])
        subprocess.Popen([os.path.join(CONFIG_DIR, "scripts", "Picom.sh")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def apply_bar(settings):
    """Restart the bar so it picks up the new position / monitor choice."""
    apply_bar_blur(settings)
    launch = os.path.expanduser("~/.config/polybar/launch.sh")
    if DRY:
        print("+", launch)
        print(bar_env(settings))
    elif os.path.exists(launch):
        subprocess.Popen([launch], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ------------------------------------------------------------------ sound (pactl: PipeWire or PulseAudio)
PA_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,199}\Z")     # device names as PipeWire/PulseAudio make them
PA_HINT = ("This tab needs PulseAudio (pactl), which %s does not use by default. The volume keys and the bar's "
           "volume item work without it, with the system's own mixer (FreeBSD: mixer, OpenBSD: sndioctl, "
           "NetBSD: mixerctl)." % {"freebsd": "FreeBSD", "openbsd": "OpenBSD", "netbsd": "NetBSD"}[SYSTEM])
VOLUME_MAX = 150                                                       # same limit as the volume keys
SOUNDS_CONF = os.path.join(CONFIG_DIR, "sounds.conf")
SOUND_DEFAULT = {"volume_feedback": True, "screenshot_sound": True}
TEST_SOUNDS = [os.path.join(share, "sounds", f)                        # (/usr/local, NetBSD's /usr/pkg)
               for share in ("/usr/local/share", "/usr/pkg/share", "/usr/share")
               for f in ("freedesktop/stereo/audio-volume-change.oga", "freedesktop/stereo/bell.oga",
                         "freedesktop/stereo/complete.oga", "alsa/Front_Center.wav")]


def english_messages_env():
    """The environment with only the messages in English (the character set stays yours): for a tool whose text
    output is read here, like an older pactl's "Default Sink:" and "Mute: yes"."""
    env = dict(os.environ)
    every = env.pop("LC_ALL", "")
    if every and not env.get("LC_CTYPE"):
        env["LC_CTYPE"] = every
    env.pop("LANGUAGE", None)
    env["LC_MESSAGES"] = "C"
    return env


def pa_ctl(args, timeout=6):
    """Run pactl. Returns (ok, output); never raises."""
    exe = shutil.which("pactl")
    if not exe:
        return False, "pactl is not installed"
    try:
        r = subprocess.run([exe] + list(args), capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           env=english_messages_env())
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as e:
        return False, str(e)
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def _pa_percent(volume):
    """Loudest channel of a pactl JSON volume map, in percent."""
    best = 0
    for ch in (volume or {}).values():
        m = re.match(r"\s*(\d+)%", str(ch.get("value_percent", "")) if isinstance(ch, dict) else "")
        if m:
            best = max(best, int(m.group(1)))
    return best


def _pa_text_percent(text):
    m = re.search(r"(\d+)%", text or "")
    return int(m.group(1)) if m else 0


def pa_default(kind):
    """Name of the default sink/source."""
    ok, out = pa_ctl(["get-default-" + kind])
    if ok and out.strip() and "\n" not in out.strip():
        return out.strip()
    ok, out = pa_ctl(["info"])                    # older pactl: no get-default-*
    m = re.search(r"^Default %s:\s*(\S+)" % ("Sink" if kind == "sink" else "Source"), out if ok else "", re.M)
    return m.group(1) if m else ""


def pa_devices(kind):
    """[{'name','label','volume','mute'}] for kind 'sink' (outputs) or 'source' (microphones, without monitors)."""
    ok, out = pa_ctl(["-f", "json", "list", kind + "s"])
    devs = []
    data = None
    if ok:
        try:
            data = json.loads(out)
        except ValueError:
            data = None
    if isinstance(data, list):
        for d in data:
            if not isinstance(d, dict):
                continue
            name = d.get("name") or ""
            if not PA_NAME_RE.match(name):
                continue
            if kind == "source" and (name.endswith(".monitor") or d.get("monitor_of_sink") not in (None, "", "n/a")):
                continue                          # a recording of an output, not a microphone
            devs.append({"name": name, "label": d.get("description") or name,
                         "volume": _pa_percent(d.get("volume")), "mute": bool(d.get("mute"))})
        return devs
    # older pactl without JSON output: names from the short list, volume/mute asked one by one
    ok, out = pa_ctl(["list", "short", kind + "s"])
    for line in (out if ok else "").splitlines():
        f = line.split("\t")
        if len(f) < 2 or not PA_NAME_RE.match(f[1]) or (kind == "source" and f[1].endswith(".monitor")):
            continue
        _o, vol = pa_ctl(["get-%s-volume" % kind, f[1]])
        _o, mute = pa_ctl(["get-%s-mute" % kind, f[1]])
        devs.append({"name": f[1], "label": f[1], "volume": _pa_text_percent(vol), "mute": "yes" in mute})
    return devs


def pa_streams():
    """Apps playing sound now: [{'id','app','volume','mute'}]."""
    ok, out = pa_ctl(["-f", "json", "list", "sink-inputs"])
    try:
        data = json.loads(out) if ok else None
    except ValueError:
        data = None
    streams = []
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict) or not isinstance(d.get("index"), int):
            continue
        props = d.get("properties") if isinstance(d.get("properties"), dict) else {}
        app = props.get("application.name") or props.get("media.name") or "Unknown app"
        streams.append({"id": d["index"], "app": str(app)[:60], "volume": _pa_percent(d.get("volume")),
                        "mute": bool(d.get("mute"))})
    return sorted(streams, key=lambda x: x["app"].lower())


def pa_snapshot():
    """Everything the Sound tab shows, read in one go (runs off the UI thread)."""
    if not shutil.which("pactl"):
        return {"available": False}
    ok, _out = pa_ctl(["info"])
    if not ok:
        return {"available": False, "error": "No sound server is running (PipeWire or PulseAudio)."}
    return {"available": True, "sinks": pa_devices("sink"), "sources": pa_devices("source"),
            "default_sink": pa_default("sink"), "default_source": pa_default("source"), "streams": pa_streams()}


def pa_set_default(kind, name):
    """Make a device the default and move what is playing/recording now over to it."""
    if kind not in ("sink", "source") or not PA_NAME_RE.match(name or ""):
        return False, "invalid device"
    ok, out = pa_ctl(["set-default-" + kind, name])
    if not ok:
        return False, out.strip()[-160:]
    streams = "sink-inputs" if kind == "sink" else "source-outputs"
    _ok, lst = pa_ctl(["list", "short", streams])
    for line in lst.splitlines():
        sid = line.split("\t")[0].strip()
        if sid.isdigit():
            pa_ctl(["move-%s" % streams[:-1], sid, name])
    return True, ""


def pa_set_volume(kind, target, pct):
    """kind: sink / source (target = name) or sink-input (target = number)."""
    pct = max(0, min(VOLUME_MAX, int(pct)))
    if kind in ("sink", "source") and PA_NAME_RE.match(str(target)):
        return pa_ctl(["set-%s-volume" % kind, str(target), "%d%%" % pct])
    if kind == "sink-input" and str(target).isdigit():
        return pa_ctl(["set-sink-input-volume", str(target), "%d%%" % pct])
    return False, "invalid target"


def pa_set_mute(kind, target, mute):
    flag = "1" if mute else "0"
    if kind in ("sink", "source") and PA_NAME_RE.match(str(target)):
        return pa_ctl(["set-%s-mute" % kind, str(target), flag])
    if kind == "sink-input" and str(target).isdigit():
        return pa_ctl(["set-sink-input-mute", str(target), flag])
    return False, "invalid target"


def pa_test_sound(sink):
    """Play a short sound on one output."""
    snd = next((f for f in TEST_SOUNDS if os.path.isfile(f)), None)
    if not snd:
        return False, "no test sound found (install sound-theme-freedesktop)"
    if shutil.which("paplay") and PA_NAME_RE.match(sink or ""):
        cmd = ["paplay", "--device=" + sink, snd]
    elif shutil.which("paplay"):
        cmd = ["paplay", snd]
    elif shutil.which("pw-play"):
        cmd = ["pw-play", snd]
    else:
        return False, "no player found (install pulseaudio-utils)"
    if DRY:
        print("+", " ".join(cmd))
        return True, ""
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True, ""


def apply_sound(settings):
    """Write the sound-effect switches for Sounds.sh (volume keys and screenshots read it)."""
    cfg = dict(SOUND_DEFAULT, **(settings.get("sound") or {}))
    text = ("# Written by the Settings window (Sound tab). Read by scripts/Sounds.sh.\n"
            "muteVolume=%s\nmuteScreenshots=%s\n" % ("false" if cfg["volume_feedback"] else "true",
                                                     "false" if cfg["screenshot_sound"] else "true"))
    if os.path.isdir(CONFIG_DIR):
        _write_if_changed(SOUNDS_CONF, text)


# ------------------------------------------------------------------ bluetooth (bluetoothctl / BlueZ)
BT_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z")
BT_HINT = ("This tab uses BlueZ, which only runs on Linux. FreeBSD and NetBSD pair Bluetooth devices with their "
           "own tools (FreeBSD Handbook: Bluetooth; NetBSD: btpair); OpenBSD has no Bluetooth support.")


def bt_ctl(args, timeout=20, agent=None):
    """Run bluetoothctl with a time limit. Returns (ok, output); never raises."""
    exe = shutil.which("bluetoothctl")
    if not exe:
        return False, "bluetoothctl is not installed"
    cmd = [exe] + (["--agent", agent] if agent else []) + list(args)
    if DRY and args and args[0] not in ("show", "devices", "info"):
        print("+", " ".join(shlex.quote(c) for c in cmd))
        return True, ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as e:
        return False, str(e)
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def bt_state():
    """{'available', 'powered', 'blocked'} for the default adapter."""
    ok, out = bt_ctl(["show"], timeout=8)
    if not ok or "Powered:" not in out:
        return {"available": False, "powered": False, "installed": bool(shutil.which("bluetoothctl"))}
    return {"available": True, "installed": True, "powered": "Powered: yes" in out}


def bt_devices():
    """Every device BlueZ knows: [{'mac','name','paired','connected'}], paired ones first."""
    ok, out = bt_ctl(["devices"], timeout=8)
    found = []
    for line in (out if ok else "").splitlines():
        m = re.match(r"^Device\s+(\S+)\s*(.*)$", line.strip())
        if not (m and BT_MAC_RE.match(m.group(1))):
            continue
        mac, name = m.group(1).upper(), m.group(2).strip()
        _ok, info = bt_ctl(["info", mac], timeout=6)
        found.append({"mac": mac, "name": name or mac,
                      "paired": "Paired: yes" in info, "connected": "Connected: yes" in info})
    return sorted(found, key=lambda d: (not d["paired"], not d["connected"], d["name"].lower()))


def bt_power(on):
    if on:
        run_quiet = shutil.which("rfkill")
        if run_quiet and not DRY:
            subprocess.run([run_quiet, "unblock", "bluetooth"], capture_output=True, timeout=10)
    ok, out = bt_ctl(["power", "on" if on else "off"], timeout=15)
    return ok and "Failed" not in out, out


def bt_scan(seconds=8):
    """Look for nearby devices for a few seconds (they then show up in bt_devices)."""
    return bt_ctl(["--timeout", str(int(seconds)), "scan", "on"], timeout=seconds + 8)


def bt_action(action, mac):
    """connect / disconnect / remove one device. Returns (ok, message)."""
    if action not in ("connect", "disconnect", "remove") or not BT_MAC_RE.match(mac or ""):
        return False, "invalid request"
    ok, out = bt_ctl([action, mac], timeout=30)
    good = {"connect": "Connection successful", "disconnect": "Successful disconnected",
            "remove": "has been removed"}[action]
    if DRY:
        return True, ""
    if good in out or (action == "remove" and "removed" in out.lower()):
        return True, ""
    last = [l for l in out.splitlines() if l.strip()][-1:]
    return False, (last[0] if last else "no answer from bluetoothctl").strip()


def bt_pair(mac):
    """Pair, trust and connect (Just Works pairing: headphones, speakers, mice, game pads...)."""
    if not BT_MAC_RE.match(mac or ""):
        return False, "invalid address"
    ok, out = bt_ctl(["pair", mac], timeout=45, agent="NoInputNoOutput")
    if not DRY and "Pairing successful" not in out and "AlreadyExists" not in out and "Already" not in out:
        last = [l for l in out.splitlines() if l.strip()][-1:]
        return False, (last[0] if last else "pairing failed").strip() + \
            " (keyboards that ask for a PIN: use the full Bluetooth manager)"
    bt_ctl(["trust", mac], timeout=10)
    return bt_action("connect", mac)


# ------------------------------------------------------------------ wi-fi (NetworkManager / nmcli)
NM_HINT = {"freebsd": "Wi-Fi on FreeBSD and GhostBSD: the network icon in the tray (NetworkMgr) joins networks.",
           "openbsd": "Wi-Fi on OpenBSD:  doas ifconfig iwx0 join NAME wpakey PASSWORD  (or /etc/hostname.iwx0; "
                      "your card may be iwm0, athn0, ...).",
           "netbsd": "Wi-Fi on NetBSD: add the network to /etc/wpa_supplicant.conf and start wpa_supplicant "
                     "(see the NetBSD guide, Networking)."}[SYSTEM]


NET_APPLET = os.path.join(CONFIG_DIR, "scripts", "NetApplet.sh")


def wifi_tray_icon(settings):
    """Show nm-applet's icon in the tray? Off by default: the Wi-Fi item in the bar opens the Wi-Fi tab instead."""
    n = settings.get("network") if isinstance(settings.get("network"), dict) else {}
    return n.get("tray_icon") is True


def apply_net_applet(settings, restart=False):
    """Hide or show nm-applet's tray icon (NetApplet.sh does it and keeps the applet running for password prompts)."""
    if DRY or FILES_ONLY or not os.path.exists(NET_APPLET):
        return
    subprocess.Popen([NET_APPLET] + (["restart"] if restart else []), start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def nm_ctl(args, timeout=30):
    """Run nmcli with a time limit. Returns (ok, output); never raises."""
    exe = shutil.which("nmcli")
    if not exe:
        return False, "nmcli is not installed"
    cmd = [exe] + list(args)
    is_read = bool(args) and (args[0] == "-t" or list(args) == ["radio", "wifi"])
    if DRY and not is_read:
        shown = ["***" if i and args[i - 1] == "password" else a for i, a in enumerate(args)]
        print("+", "nmcli", " ".join(shlex.quote(c) for c in shown))
        return True, ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as e:
        return False, str(e)
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def nm_fields(line):
    """Split one line of 'nmcli -t' output (':' separates fields, '\\:' and '\\\\' are escapes)."""
    return [re.sub(r"\\(.)", r"\1", p) for p in re.split(r"(?<!\\):", line)]


def nm_valid_ssid(ssid):
    return isinstance(ssid, str) and 0 < len(ssid.encode("utf-8", "ignore")) <= 32 and not re.search(r"[\x00-\x1f]", ssid)


def nm_valid_password(pw):
    return isinstance(pw, str) and (8 <= len(pw) <= 63 or re.fullmatch(r"[0-9A-Fa-f]{64}", pw) is not None) \
        and not re.search(r"[\x00-\x1f]", pw)


def nm_state():
    """{'available', 'enabled', 'iface'}: is there a Wi-Fi adapter, is the radio on, and its device name."""
    ok, out = nm_ctl(["-t", "-f", "DEVICE,TYPE", "device"], timeout=8)
    iface = ""
    for line in (out if ok else "").splitlines():
        f = nm_fields(line)
        if len(f) >= 2 and f[1] == "wifi":
            iface = f[0]
            break
    ok2, rad = nm_ctl(["radio", "wifi"], timeout=8)
    return {"installed": bool(shutil.which("nmcli")), "available": bool(iface), "iface": iface,
            "enabled": ok2 and rad.strip() == "enabled"}


def nm_saved():
    """Names of the Wi-Fi profiles NetworkManager remembers."""
    ok, out = nm_ctl(["-t", "-f", "NAME,TYPE", "connection", "show"], timeout=8)
    saved = set()
    for line in (out if ok else "").splitlines():
        f = nm_fields(line)
        if len(f) >= 2 and f[-1] in ("802-11-wireless", "wifi"):
            saved.add(":".join(f[:-1]))
    return saved


def nm_networks(rescan=False):
    """Visible networks, one row per name: [{'ssid','signal','security','active','saved'}], best first."""
    ok, out = nm_ctl(["-t", "-f", "IN-USE,SIGNAL,SECURITY,SSID", "device", "wifi", "list",
                      "--rescan", "yes" if rescan else "no"], timeout=25)
    saved = nm_saved()
    nets = {}
    for line in (out if ok else "").splitlines():
        f = nm_fields(line)
        if len(f) < 4:
            continue
        ssid = ":".join(f[3:])
        if not ssid:
            continue                                   # hidden networks have no name to show
        try:
            sig = int(f[1])
        except ValueError:
            sig = 0
        n = {"ssid": ssid, "signal": sig, "security": f[2] if f[2] not in ("", "--") else "Open",
             "active": f[0].strip() == "*", "saved": ssid in saved}
        old = nets.get(ssid)
        if not old or n["active"] or (not old["active"] and n["signal"] > old["signal"]):
            nets[ssid] = n
    return sorted(nets.values(), key=lambda n: (not n["active"], -n["signal"], n["ssid"].lower()))


def nm_power(on):
    if on and shutil.which("rfkill") and not DRY:
        subprocess.run(["rfkill", "unblock", "wifi"], capture_output=True, timeout=10)
    ok, out = nm_ctl(["radio", "wifi", "on" if on else "off"], timeout=15)
    return ok, out


def nm_last(out, default):
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines[-1] if lines else default


def nm_connect(ssid, password=None, hidden=False, saved=False):
    """Join a network. A remembered network just reconnects; a new one needs its password (open networks none)."""
    if not nm_valid_ssid(ssid):
        return False, "invalid network name"
    if password is not None and not nm_valid_password(password):
        return False, "the password must be 8 to 63 characters"
    if saved and not password and not hidden:
        ok, out = nm_ctl(["connection", "up", "id", ssid], timeout=45)
    else:
        args = ["device", "wifi", "connect", ssid]
        if password:
            args += ["password", password]
        if hidden:
            args += ["hidden", "yes"]
        ok, out = nm_ctl(args, timeout=60)
    if DRY or ok:                       # (nmcli's exit code: its messages are in the user's language)
        return True, ""
    return False, nm_last(out, "could not connect")


def nm_disconnect(iface):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", iface or ""):
        return False, "no Wi-Fi device"
    ok, out = nm_ctl(["device", "disconnect", iface], timeout=20)
    return (True, "") if DRY or ok else (False, nm_last(out, "could not disconnect"))


def nm_forget(ssid):
    if not nm_valid_ssid(ssid):
        return False, "invalid network name"
    ok, out = nm_ctl(["connection", "delete", "id", ssid], timeout=20)
    return (True, "") if DRY or ok else (False, nm_last(out, "could not forget the network"))


# ------------------------------------------------------------------ network: adapters, IP settings, VPN, proxy
UUID_RE = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\Z")
IFACE_RE = re.compile(r"[A-Za-z0-9_.@-]{1,32}\Z")
NET_STATE = {"connected": "Connected", "disconnected": "Not connected", "unavailable": "Not available",
             "unmanaged": "Not managed by NetworkManager", "deactivating": "Disconnecting...",
             "connected (externally)": "Connected (outside NetworkManager)"}


def _resolv_dns():
    """The DNS servers the system uses (resolv.conf), as far as it says."""
    try:
        with open("/etc/resolv.conf", errors="replace") as f:
            found = re.findall(r"^[ \t]*nameserver[ \t]+([0-9A-Fa-f.:]+)", f.read(), re.M)
    except OSError:
        return []
    return [d for d in found if _ip_ok(d)][:4]


def _ip_ok(text, v4=False):
    try:
        a = ipaddress.ip_address(text)
    except ValueError:
        return False
    return a.version == 4 or not v4


def nm_show(args):
    """'nmcli -t -e no -f FIELDS ... show' as {FIELD: [values]} (FIELD[1], FIELD[2]... collected in order)."""
    ok, out = nm_ctl(["-t", "-e", "no"] + list(args), timeout=10)
    res = {}
    for line in (out if ok else "").splitlines():
        key, sep, val = line.partition(":")
        if not sep:
            continue
        key, val = re.sub(r"\[\d+\]$", "", key.strip()), val.strip()
        if val and val != "--":
            res.setdefault(key, []).append(val)
    return res


def _nm_devices():
    """Wi-Fi and Ethernet adapters as NetworkManager sees them, or None when it is not running."""
    ok, out = nm_ctl(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION,CON-UUID", "device"], timeout=8)
    if not ok:
        return None
    devs = []
    for line in out.splitlines():
        f = nm_fields(line)
        if len(f) < 5 or f[1] not in ("wifi", "ethernet") or not IFACE_RE.match(f[0]):
            continue
        state = f[2].strip()
        info = nm_show(["-f", "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS,IP6.ADDRESS", "device", "show", f[0]])
        devs.append({"iface": f[0], "type": f[1], "state": state, "nm": True,
                     "status": "Connecting..." if state.startswith("connecting") else NET_STATE.get(state, state),
                     "connected": state.startswith("connected"),
                     "connection": "" if f[3] in ("", "--") else f[3],
                     "uuid": f[4] if UUID_RE.match(f[4]) else "",
                     "mac": (info.get("GENERAL.HWADDR") or [""])[0],
                     "ip4": info.get("IP4.ADDRESS", []), "gw4": (info.get("IP4.GATEWAY") or [""])[0],
                     "dns": info.get("IP4.DNS", []),
                     "ip6": [a for a in info.get("IP6.ADDRESS", []) if not a.lower().startswith("fe80")]})
    return devs


def _mask_prefix(mask):
    """'0xffffff00' or '255.255.255.0' -> 24 (None if it is not a netmask)."""
    try:
        n = int(mask, 16) if mask.lower().startswith("0x") else int(ipaddress.IPv4Address(mask))
        return ipaddress.IPv4Network("0.0.0.0/%s" % ipaddress.IPv4Address(n)).prefixlen
    except ValueError:
        return None


def _ifconfig_devices():
    """FreeBSD / OpenBSD / NetBSD: the adapters from ifconfig and the default route (read only)."""
    text = query(["ifconfig", "-a"])
    gw, gw_if = "", ""
    route = query(["route", "-n", "get", "default"])
    m = re.search(r"^\s*gateway:\s*(\S+)", route, re.M)
    if m and _ip_ok(m.group(1)):
        gw = m.group(1)
        m2 = re.search(r"^\s*interface:\s*(\S+)", route, re.M)
        gw_if = m2.group(1) if m2 else ""
    devs, dns = [], _resolv_dns()
    for blk in re.split(r"\n(?=\S)", text):
        m = re.match(r"^([A-Za-z0-9_.]+):\s+flags=", blk)
        if not m or re.match(r"(lo|pflog|pfsync|enc|gif|stf|faith|bridge|tun|tap|wg|vlan|carp|lagg|ipsec)\d",
                             m.group(1)):
            continue
        iface = m.group(1)
        mac = re.search(r"^\s+(?:ether|lladdr|address:)\s+([0-9A-Fa-f:]{17})", blk, re.M)
        if not mac:
            continue                                   # (not a network card)
        kind = "wifi" if re.search(r"\bssid\b|\bnwid\b|ieee80211:|IEEE ?802\.11", blk) else "ethernet"
        ip4 = []
        for a, rest in re.findall(r"^\s+inet\s+(\S+)(.*)$", blk, re.M):
            if "/" in a:
                ip4.append(a)
            else:
                mk = re.search(r"netmask\s+(\S+)", rest)
                pre = _mask_prefix(mk.group(1)) if mk else None
                ip4.append("%s/%d" % (a, pre) if pre is not None else a)
        ip6 = []
        for a, rest in re.findall(r"^\s+inet6\s+(\S+)(.*)$", blk, re.M):
            a = a.split("%")[0]
            if a.lower().startswith("fe80"):
                continue
            pl = re.search(r"prefixlen\s+(\d+)", rest)
            ip6.append(a if "/" in a or not pl else "%s/%s" % (a, pl.group(1)))
        st = re.search(r"^\s+status:\s*(.+)$", blk, re.M)
        active = bool(st and st.group(1).strip() in ("active", "associated")) or (not st and bool(ip4))
        ssid = re.search(r"\b(?:ssid|nwid|join)\s+(\"[^\"]*\"|\S+)", blk)
        devs.append({"iface": iface, "type": kind, "state": "connected" if active and ip4 else "disconnected",
                     "status": "Connected" if active and ip4 else ("Cable unplugged" if kind == "ethernet" and st
                                                                   and "no carrier" in st.group(1) else "Not connected"),
                     "connected": bool(active and ip4),
                     "connection": ssid.group(1).strip('"') if ssid and kind == "wifi" else "", "uuid": "",
                     "mac": mac.group(1), "ip4": ip4, "gw4": gw if iface == gw_if else "",
                     "dns": dns if ip4 else [], "ip6": ip6})
    return devs


def net_devices():
    """The computer's Wi-Fi and Ethernet adapters with their addresses: NetworkManager where it runs (then they can
    be changed), else ifconfig. [{'iface', 'type', 'status', 'connected', 'connection',
    'uuid', 'mac', 'ip4', 'gw4', 'dns', 'ip6'}]"""
    if shutil.which("nmcli"):
        devs = _nm_devices()
        if devs is not None:
            return devs
    return _ifconfig_devices()


def nm_ip_settings(uuid):
    """How a saved connection gets its address: {'id', 'method' (auto / manual / other), 'address', 'prefix',
    'gateway', 'dns' [list]} or None."""
    if not UUID_RE.match(uuid or ""):
        return None
    info = nm_show(["-f", "connection.id,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns", "connection", "show",
                    "uuid", uuid])
    if not info:
        return None
    addrs = [a.strip() for a in ",".join(info.get("ipv4.addresses", [])).split(",") if a.strip()]
    addr, _sl, pre = (addrs[0] if addrs else "").partition("/")
    method = (info.get("ipv4.method") or ["auto"])[0]
    return {"id": (info.get("connection.id") or [""])[0],
            "method": method if method in ("auto", "manual") else "other",
            "address": addr, "prefix": pre, "gateway": (info.get("ipv4.gateway") or [""])[0],
            "dns": [d.strip() for d in ",".join(info.get("ipv4.dns", [])).replace(" ", ",").split(",") if d.strip()]}


def parse_ip_form(method, address, prefix, gateway, dns):
    """Check what was typed in the IP settings. Returns (values, None) or (None, the problem in words)."""
    out = {"method": "manual" if method == "manual" else "auto", "address": "", "prefix": 0, "gateway": "",
           "dns": []}
    for d in [x for x in re.split(r"[\s,;]+", dns or "") if x]:
        if not _ip_ok(d):
            return None, "'%s' is not a DNS server address (like 1.1.1.1)" % d[:40]
        out["dns"].append(str(ipaddress.ip_address(d)))
    if len(out["dns"]) > 4:
        return None, "at most 4 DNS servers"
    if out["method"] == "auto":
        return out, None
    address, prefix, gateway = (address or "").strip(), (prefix or "").strip(), (gateway or "").strip()
    if not _ip_ok(address, v4=True):
        return None, "enter the address, like 192.168.1.50"
    if re.fullmatch(r"/?\d{1,2}", prefix) and 1 <= int(prefix.lstrip("/")) <= 32:
        out["prefix"] = int(prefix.lstrip("/"))
    elif re.fullmatch(r"[0-9.]{7,15}", prefix) and _mask_prefix(prefix):
        out["prefix"] = _mask_prefix(prefix)
    else:
        return None, "enter the subnet as 24 or 255.255.255.0"
    net = ipaddress.IPv4Network("%s/%d" % (address, out["prefix"]), strict=False)
    a = ipaddress.IPv4Address(address)
    if out["prefix"] <= 30 and a in (net.network_address, net.broadcast_address):
        return None, "%s is not a usable address in that subnet" % address
    out["address"] = str(a)
    if gateway:
        if not _ip_ok(gateway, v4=True):
            return None, "enter the router, like 192.168.1.1 (or leave it empty)"
        if ipaddress.IPv4Address(gateway) not in net:
            return None, "the router %s is not in the subnet of %s/%d" % (gateway, address, out["prefix"])
        out["gateway"] = str(ipaddress.IPv4Address(gateway))
    return out, None


def nm_set_ip(uuid, values, reconnect=True):
    """Save checked values (parse_ip_form) into a NetworkManager connection; reconnect it to use them now."""
    if not UUID_RE.match(uuid or ""):
        return False, "no saved connection to change"
    dns = ",".join(values["dns"])
    args = ["connection", "modify", "uuid", uuid, "ipv4.method", values["method"],
            "ipv4.addresses", "%s/%d" % (values["address"], values["prefix"]) if values["method"] == "manual" else "",
            "ipv4.gateway", values["gateway"] if values["method"] == "manual" else "",
            "ipv4.dns", dns, "ipv4.ignore-auto-dns", "yes" if dns else "no"]
    ok, out = nm_ctl(args, timeout=20)
    if not (ok or DRY):
        return False, nm_last(out, "could not save the IP settings")
    if reconnect:
        ok, out = nm_ctl(["connection", "up", "uuid", uuid], timeout=60)
        if not (ok or DRY):
            return False, "saved, but reconnecting failed: " + nm_last(out, "")
    return True, ""


def nm_device_up(iface, on):
    """Connect / disconnect an adapter (NetworkManager picks its saved connection)."""
    if not IFACE_RE.match(iface or ""):
        return False, "no such adapter"
    ok, out = nm_ctl(["device", "connect" if on else "disconnect", iface], timeout=60 if on else 20)
    return (True, "") if DRY or ok else (False, nm_last(out, "it did not work"))


VPN_KINDS = {"openvpn": "OpenVPN", "vpnc": "Cisco (vpnc)", "openconnect": "OpenConnect", "l2tp": "L2TP",
             "pptp": "PPTP", "strongswan": "IPsec", "libreswan": "IPsec", "fortisslvpn": "Fortinet SSL",
             "sstp": "SSTP"}


def nm_vpns():
    """Saved VPN connections: [{'name', 'uuid', 'kind', 'active'}]."""
    ok, out = nm_ctl(["-t", "-f", "NAME,UUID,TYPE,ACTIVE", "connection", "show"], timeout=8)
    vpns = []
    for line in (out if ok else "").splitlines():
        f = nm_fields(line)
        if len(f) < 4 or f[-2] not in ("vpn", "wireguard") or not UUID_RE.match(f[-3]):
            continue
        name, uuid, kind = ":".join(f[:-3]), f[-3], f[-2]
        if kind == "wireguard":
            label = "WireGuard"
        else:
            svc = (nm_show(["-f", "vpn.service-type", "connection", "show", "uuid", uuid]).get("vpn.service-type")
                   or [""])[0]
            label = VPN_KINDS.get(svc.rsplit(".", 1)[-1].lower(), "VPN")
        vpns.append({"name": name, "uuid": uuid, "kind": label, "active": f[-1].strip() == "yes"})
    return sorted(vpns, key=lambda v: v["name"].lower())


def nm_vpn(action, uuid):
    """up / down / delete one VPN connection."""
    if action not in ("up", "down", "delete") or not UUID_RE.match(uuid or ""):
        return False, "no such VPN"
    ok, out = nm_ctl(["connection", action, "uuid", uuid], timeout=90 if action == "up" else 25)
    return (True, "") if DRY or ok else (False, nm_last(out, "it did not work"))


def vpn_file_kind(path):
    """'wireguard' or 'openvpn' for a VPN file someone picked, or None (it must be a small text file)."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > 512 * 1024:
            return None
        with open(path, errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    if re.search(r"^\s*\[Interface\]", text, re.M) and re.search(r"^\s*PrivateKey\s*=", text, re.M):
        return "wireguard"
    if re.search(r"^\s*(remote|client|dev\s+tun|dev\s+tap|<ca>)\b", text, re.M):
        return "openvpn"
    return None


def nm_vpn_import(path):
    """Add a VPN from a WireGuard (.conf) or OpenVPN (.ovpn) file. WireGuard names the connection (and its network
    interface) after the file, which must then be a short plain name: otherwise a copy with such a name is used."""
    import tempfile
    kind = vpn_file_kind(path)
    if not kind:
        return False, "that is not a WireGuard or OpenVPN file"
    tmp = None
    use = path
    if kind == "wireguard":
        stem = os.path.splitext(os.path.basename(path))[0]
        name = re.sub(r"[^A-Za-z0-9_=+.-]", "", stem)[:15] or "wg0"
        if name != stem or not path.endswith(".conf"):
            tmp = tempfile.mkdtemp(prefix="i3dots-vpn-")
            use = os.path.join(tmp, name + ".conf")
            shutil.copyfile(path, use)
            os.chmod(use, 0o600)
    try:
        ok, out = nm_ctl(["connection", "import", "type", kind, "file", use], timeout=30)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    if ok or DRY:
        return True, kind
    msg = nm_last(out, "could not add it")
    if kind == "openvpn" and ("plugin" in msg.lower() or "vpn" in msg.lower()):
        msg += " - OpenVPN needs NetworkManager's OpenVPN plugin"
    return False, msg


PROXY_DEFAULT = {"mode": "none", "http": "", "https": "", "socks": "", "same": True, "pac": "",
                 "ignore": "localhost, 127.0.0.0/8, ::1"}
PROXY_MARK = ("# >>> i3wm-dots proxy (Settings > Network > Proxy) >>>", "# <<< i3wm-dots proxy <<<")
HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\Z")
PROXY_ENV_NAMES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "auto_proxy",
                   "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def parse_hostport(text):
    """'host:port' (also '[v6]:port' or with http:// in front) -> (host, port), or None."""
    t = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://", "", (text or "").strip()).rstrip("/")
    m = re.fullmatch(r"\[([0-9A-Fa-f:.]{2,45})\]:(\d{1,5})", t) or re.fullmatch(r"([^:\s/\[\]@]{1,253}):(\d{1,5})", t)
    if not m or not 1 <= int(m.group(2)) <= 65535:
        return None
    host = m.group(1)
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None
    elif not HOST_RE.match(host):
        return None
    return host, int(m.group(2))


def _hostport_text(hp):
    return ("[%s]:%d" if ":" in hp[0] else "%s:%d") % hp


def parse_ignore(text):
    """'localhost, 127.0.0.0/8, *.lan' -> the list, or None if an entry has odd characters."""
    items = [x for x in re.split(r"[\s,;]+", text or "") if x]
    if len(items) > 64 or any(not re.fullmatch(r"[A-Za-z0-9.*:/\[\]_-]{1,255}", x) for x in items):
        return None
    return items


def valid_pac(url):
    return isinstance(url, str) and re.fullmatch(r"(https?|file)://[^\s'\"\\`$;<>|&]{1,1024}", url) is not None


def proxy_choice(settings):
    """The saved proxy (Settings > Network > Proxy), cleaned; the default (no proxy) when nothing is saved."""
    c = settings.get("proxy") if isinstance(settings.get("proxy"), dict) else {}
    out = dict(PROXY_DEFAULT)
    if c.get("mode") in ("none", "manual", "auto"):
        out["mode"] = c["mode"]
    for k in ("http", "https", "socks"):
        hp = parse_hostport(c.get(k)) if isinstance(c.get(k), str) else None
        out[k] = _hostport_text(hp) if hp else ""
    if isinstance(c.get("same"), bool):
        out["same"] = c["same"]
    if valid_pac(c.get("pac")):
        out["pac"] = c["pac"]
    if isinstance(c.get("ignore"), str) and parse_ignore(c["ignore"]) is not None:
        out["ignore"] = ", ".join(parse_ignore(c["ignore"]))
    return out


def proxy_env(cfg):
    """The environment variables for a proxy choice ({} = none)."""
    env = {}
    if cfg["mode"] == "manual":
        http, https = parse_hostport(cfg["http"]), parse_hostport(cfg["http"] if cfg["same"] else cfg["https"])
        socks = parse_hostport(cfg["socks"])
        if http:
            env["http_proxy"] = "http://%s/" % _hostport_text(http)
        if https:
            env["https_proxy"] = "http://%s/" % _hostport_text(https)
        if socks:
            env["all_proxy"] = "socks5://%s/" % _hostport_text(socks)
    elif cfg["mode"] == "auto" and valid_pac(cfg["pac"]):
        env["auto_proxy"] = cfg["pac"]                 # (Chromium-based browsers read it)
    if env:
        env["no_proxy"] = ",".join(parse_ignore(cfg["ignore"]) or [])
        for k in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            if k in env:
                env[k.upper()] = env[k]
    return env


_GSET = {}


def _gsettings_proxy():
    """Is GNOME's proxy setting there (gsettings + its schema)? Firefox and GTK apps follow it."""
    if "ok" not in _GSET:
        _GSET["ok"] = bool(shutil.which("gsettings")) and \
            "org.gnome.system.proxy" in query(["gsettings", "list-schemas"]).split()
    return _GSET["ok"]


def proxy_current(settings):
    """What the Proxy section starts from: the saved choice, else GNOME's proxy setting, else none."""
    if isinstance(settings.get("proxy"), dict) or not _gsettings_proxy():
        return proxy_choice(settings)

    def get(schema, key):
        return query(["gsettings", "get", schema, key]).strip().strip("'")
    cfg = dict(PROXY_DEFAULT)
    mode = get("org.gnome.system.proxy", "mode")
    cfg["mode"] = mode if mode in ("none", "manual", "auto") else "none"
    for k, schema in (("http", "org.gnome.system.proxy.http"), ("https", "org.gnome.system.proxy.https"),
                      ("socks", "org.gnome.system.proxy.socks")):
        hp = parse_hostport("%s:%s" % (get(schema, "host"), get(schema, "port")))
        cfg[k] = _hostport_text(hp) if hp else ""
    cfg["same"] = get("org.gnome.system.proxy", "use-same-proxy") != "false"
    pac = get("org.gnome.system.proxy", "autoconfig-url")
    cfg["pac"] = pac if valid_pac(pac) else ""
    ign = re.findall(r"'([^']*)'", query(["gsettings", "get", "org.gnome.system.proxy", "ignore-hosts"]))
    if ign and parse_ignore(", ".join(ign)) is not None:
        cfg["ignore"] = ", ".join(ign)
    return proxy_choice({"proxy": cfg})


def _remove_block(text, marks):
    start, end = marks
    return re.sub(r"^%s$.*?^%s$\n?" % (re.escape(start), re.escape(end)), "", text, flags=re.M | re.S)


def apply_proxy(settings):
    """Use the proxy everywhere it is read:
      programs started from the next login      ~/.xprofile (~/.xinitrc and ~/.xsession read it) and environment.d
      Firefox, GTK / GNOME apps (at once)        GNOME's proxy setting (gsettings), where it exists
      programs D-Bus / systemd start from now    their activation environment"""
    cfg = proxy_choice(settings)
    env = proxy_env(cfg)
    xprofile = os.path.expanduser("~/.xprofile")
    try:
        with open(xprofile) as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        text = ""
    if env:
        new = _set_block(text, ["export %s=%s" % (k, shlex.quote(v)) for k, v in sorted(env.items())], PROXY_MARK)
    else:
        new = _remove_block(text, PROXY_MARK)
    if new != text and (new or os.path.exists(xprofile)):
        _write_if_changed(xprofile, new)
    envd = os.path.join(_CFG_HOME, "environment.d", "90-i3dots-proxy.conf")
    if env:
        _write_if_changed(envd, "".join("%s=%s\n" % (k, v) for k, v in sorted(env.items())))
    elif os.path.exists(envd) and not DRY:
        os.remove(envd)
    if FILES_ONLY:
        return
    if _gsettings_proxy():
        g = ["gsettings", "set", "org.gnome.system.proxy"]
        run(g + ["mode", cfg["mode"]])
        if cfg["mode"] == "manual":
            for k, schema in (("http", "org.gnome.system.proxy.http"), ("https", "org.gnome.system.proxy.https"),
                              ("socks", "org.gnome.system.proxy.socks")):
                hp = parse_hostport(cfg["http"] if k == "https" and cfg["same"] else cfg[k])
                run(["gsettings", "set", schema, "host", hp[0] if hp else ""])
                run(["gsettings", "set", schema, "port", str(hp[1] if hp else 0)])
            run(g + ["use-same-proxy", "true" if cfg["same"] else "false"])
        if cfg["mode"] == "auto":
            run(g + ["autoconfig-url", cfg["pac"]])
        run(g + ["ignore-hosts", "[%s]" % ", ".join("'%s'" % i for i in (parse_ignore(cfg["ignore"]) or []))])
    pairs = ["%s=%s" % (k, env.get(k, "")) for k in PROXY_ENV_NAMES]
    if shutil.which("dbus-update-activation-environment"):
        run(["dbus-update-activation-environment"] + pairs)


# ------------------------------------------------------------------ keybindings (i3 config)
BIND_RE = re.compile(r"^(\s*bindsym(?:\s+--\S+)*\s+)(\S+)(\s+)(.*?)\s*$")
MODE_START_RE = re.compile(r"^mode\s+.*\{\s*$")
KEYCAPTURE_MODE = "keycapture"
KEY_RE = re.compile(r"^[A-Za-z0-9_$]+(\+[A-Za-z0-9_$]+)*\Z")
# A changed key is saved under the bind's command (its id). These commands changed, so a key someone picked for
# the old one moves over: moving a window to a workspace goes through Workspace.py (see its top for why).
BIND_ID_RENAMED = {}
for _n in range(1, 11):
    BIND_ID_RENAMED["move container to workspace number %d; workspace number $ws%d" % (_n, _n)] = \
        "exec --no-startup-id $scripts/Workspace.py move $ws%d follow" % _n
    BIND_ID_RENAMED["move container to workspace number $ws%d" % _n] = \
        "exec --no-startup-id $scripts/Workspace.py move $ws%d" % _n
for _d in ("next", "prev"):
    BIND_ID_RENAMED["move container to workspace %s; workspace %s" % (_d, _d)] = \
        "exec --no-startup-id $scripts/Workspace.py move %s follow" % _d
    BIND_ID_RENAMED["move container to workspace %s" % _d] = "exec --no-startup-id $scripts/Workspace.py move %s" % _d
del _n, _d


def parse_binds(text):
    """Every top-level bindsym in the i3 config with its '## description'. id = the command (+ #n if repeated)."""
    binds, seen, desc, in_mode = [], {}, "", False
    for i, line in enumerate(text.split("\n")):
        s = line.strip()
        if MODE_START_RE.match(s):
            in_mode, desc = True, ""
            continue
        if in_mode:
            if s == "}":
                in_mode = False
            continue
        if s.startswith("## "):
            desc = s[3:]
            continue
        m = BIND_RE.match(line)
        if m:
            cmd = m.group(4)
            seen[cmd] = seen.get(cmd, 0) + 1
            bid = cmd if seen[cmd] == 1 else "%s #%d" % (cmd, seen[cmd])
            binds.append({"line": i, "key": m.group(2), "cmd": cmd, "desc": desc or cmd, "id": bid})
            desc = ""
        elif s:
            desc = ""
    return binds


def norm_key(key):
    """Canonical form for comparing key combos ($mod == Mod4, case-insensitive, any modifier order)."""
    parts = key.split("+")
    alias = {"mod4": "$mod", "mod1": "$alt", "control": "ctrl"}
    mods = sorted({alias.get(p.lower(), p.lower()) for p in parts[:-1]})
    return "+".join(mods + [parts[-1].lower()])


def pretty_key(key):
    out = []
    for p in key.split("+"):
        q = {"$mod": "Super", "mod4": "Super", "$alt": "Alt", "mod1": "Alt", "ctrl": "Ctrl", "control": "Ctrl"}.get(p.lower())
        out.append(q or (p.upper() if len(p) == 1 else p))
    return " + ".join(out)


def apply_keybinds(settings, reload=False):
    """Write the saved key overrides ({id: {"key":..., "default":...}}) into the i3 config.
    The new config is checked with `i3 -C` first; if i3 rejects it nothing is changed. Returns True if changed."""
    over = settings.get("keybinds") or {}
    if not over or not os.path.exists(I3_CONFIG):
        return False
    with open(I3_CONFIG) as f:
        text = f.read()
    lines = text.split("\n")
    binds = parse_binds(text)
    byid = {b["id"]: b for b in binds}
    used = {norm_key(b["key"]): b["id"] for b in binds}
    for bid, o in over.items():
        b = byid.get(bid)
        new = o.get("key") if isinstance(o, dict) else None
        if not b or not isinstance(new, str) or not KEY_RE.match(new) or norm_key(new) == norm_key(b["key"]):
            continue                       # (KEY_RE: nothing but a key combo can ever reach the i3 config)
        owner = used.get(norm_key(new))
        if owner and owner != bid and owner not in over:
            continue                       # another (unchanged) bind owns that combo now - leave this one alone
        lines[b["line"]] = BIND_RE.sub(lambda m: m.group(1) + new + m.group(3) + m.group(4), lines[b["line"]], count=1)
        used.pop(norm_key(b["key"]), None)
        used[norm_key(new)] = bid
        b["key"] = new
    new_text = "\n".join(lines)
    if new_text == text:
        return False
    if DRY:
        print("write %s (%d keybinding change(s))" % (I3_CONFIG, sum(1 for a, b in zip(text.split("\n"), lines) if a != b)))
        return True
    if not os.path.exists(I3_CONFIG + ".bak"):
        shutil.copy2(I3_CONFIG, I3_CONFIG + ".bak")      # one-time safety copy of the config before the first edit
    tmp = I3_CONFIG + ".new"
    with open(tmp, "w") as f:
        f.write(new_text)
    ok = True
    try:
        r = subprocess.run(["i3", "-C", "-c", tmp], capture_output=True, text=True, timeout=20)
        ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass                               # no i3 binary here: cannot check, write anyway
    if not ok:
        os.remove(tmp)
        raise RuntimeError("i3 rejected the new keybindings: " + (r.stderr or r.stdout).strip()[:200])
    os.replace(tmp, I3_CONFIG)
    if reload:
        run(["i3-msg", "reload"])
    return True


# ------------------------------------------------------------------ default applications (defaults.conf)
DEFAULTS_CONF = os.path.join(CONFIG_DIR, "defaults.conf")
ROFI_TERMINAL = os.path.join(CONFIG_DIR, "rofi", "00-terminal.rasi")
APP_NAMES = {
    "yazi": "Yazi", "ranger": "ranger", "lf": "lf", "nnn": "nnn", "mc": "Midnight Commander", "vifm": "Vifm",
    "thunar": "Thunar", "dolphin": "Dolphin", "nautilus": "Nautilus (Files)", "nemo": "Nemo", "pcmanfm": "PCManFM",
    "pcmanfm-qt": "PCManFM-Qt", "caja": "Caja", "spacefm": "SpaceFM", "krusader": "Krusader", "doublecmd": "Double Commander",
    "ghostty": "Ghostty", "kitty": "kitty", "alacritty": "Alacritty", "wezterm": "WezTerm", "konsole": "Konsole",
    "gnome-terminal": "GNOME Terminal", "xfce4-terminal": "Xfce Terminal", "tilix": "Tilix", "terminator": "Terminator",
    "xterm": "XTerm", "st": "st", "urxvt": "rxvt-unicode", "lxterminal": "LXTerminal", "qterminal": "QTerminal",
    "firefox": "Firefox", "chromium": "Chromium", "chromium-browser": "Chromium", "google-chrome": "Google Chrome",
    "google-chrome-stable": "Google Chrome", "brave": "Brave", "brave-browser": "Brave", "vivaldi": "Vivaldi",
    "librewolf": "LibreWolf", "epiphany": "GNOME Web", "falkon": "Falkon", "qutebrowser": "qutebrowser",
    "microsoft-edge": "Microsoft Edge", "microsoft-edge-stable": "Microsoft Edge", "zen-browser": "Zen Browser",
    "floorp": "Floorp", "waterfox": "Waterfox", "opera": "Opera", "": "System default"}
# slot -> (defaults.conf key, launcher script that reads it, fallback, installable choices)
APP_SLOTS = {
    "files": {"script": "LaunchFileManager.sh", "default": "yazi", "label": "file manager",
              "choices": ["yazi", "thunar", "dolphin", "nautilus", "nemo", "pcmanfm", "pcmanfm-qt", "caja", "spacefm", "krusader",
                          "doublecmd", "ranger", "lf", "nnn", "mc", "vifm"]},
    "term": {"script": "LaunchTerminal.sh", "default": "ghostty", "label": "terminal",
             "choices": ["ghostty", "kitty", "alacritty", "wezterm", "konsole", "gnome-terminal", "xfce4-terminal",
                         "tilix", "terminator", "lxterminal", "qterminal", "st", "urxvt", "xterm"]},
    "browser": {"script": "LaunchBrowser.sh", "default": "", "label": "browser",
                "choices": ["", "firefox", "chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave",
                            "brave-browser", "vivaldi", "librewolf", "epiphany", "falkon", "qutebrowser", "microsoft-edge",
                            "microsoft-edge-stable", "zen-browser", "floorp", "waterfox", "opera"]},
}
SAFE_CMD = re.compile(r"^[A-Za-z0-9_./+ -]*\Z")      # custom commands: no quotes, $, ; | & or backticks


def app_slot_for(cmd):
    for slot, info in APP_SLOTS.items():
        if info["script"] in cmd:
            return slot
    return None


def app_name(command):
    base = command.split()[0] if command.strip() else ""
    return APP_NAMES.get(base) or (base[:1].upper() + base[1:] if base else APP_NAMES[""])


def read_defaults():
    """{'term': 'ghostty', 'files': 'thunar', ...} from defaults.conf (simple KEY="value" lines)."""
    out = {}
    try:
        with open(DEFAULTS_CONF) as f:
            for line in f:
                m = re.match(r'^\s*(\w+)=(?:"([^"]*)"|(\S*))\s*$', line)
                if m:
                    out[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    except OSError:
        pass
    return out


def app_installed(cmd):
    """On PATH, or where the launcher scripts also look: ~/.local/bin (yazi or kitty from their own downloads) and
    /snap/bin (the Snap Store)."""
    extra = os.pathsep.join([os.environ.get("PATH", ""), os.path.expanduser("~/.local/bin"), "/snap/bin"])
    return bool(shutil.which(cmd.split()[0], path=extra)) if cmd.strip() else False


def installed_choices(slot, current):
    """[(command, label)] for the apps from the list that are installed, plus the current one."""
    cmds = [c for c in APP_SLOTS[slot]["choices"] if c == "" or app_installed(c)]
    if current not in cmds:
        cmds.append(current)
    seen, out = set(), []
    for c in cmds:
        label = app_name(c)
        if label in seen and c != "":        # chromium vs chromium-browser: list one
            continue
        seen.add(label)
        out.append((c, label))
    return out


def apply_apps(settings):
    """Write the chosen default apps into defaults.conf (and rofi's terminal). The launcher scripts read it."""
    apps = settings.get("apps") or {}
    if not apps or not os.path.exists(DEFAULTS_CONF):
        return False
    with open(DEFAULTS_CONF) as f:
        text = orig = f.read()
    for slot, value in apps.items():
        if slot not in APP_SLOTS or not isinstance(value, str) or not SAFE_CMD.match(value):
            continue
        line = '%s="%s"' % (slot, value)
        if re.search(r"^%s=.*$" % slot, text, re.M):
            text = re.sub(r"^%s=.*$" % slot, line, text, count=1, flags=re.M)
        else:
            text += "\n" + line + "\n"
    changed = text != orig
    if changed:
        if DRY:
            print("write %s: %s" % (DEFAULTS_CONF, ", ".join('%s="%s"' % kv for kv in apps.items())))
        else:
            with open(DEFAULTS_CONF + ".i3tmp", "w") as f:
                f.write(text)
            os.replace(DEFAULTS_CONF + ".i3tmp", DEFAULTS_CONF)
    term = apps.get("term")
    if term and SAFE_CMD.match(term) and os.path.exists(ROFI_TERMINAL):
        with open(ROFI_TERMINAL) as f:
            rt = f.read()
        new = re.sub(r'^(\s*terminal:\s*)".*?";', lambda m: '%s"%s";' % (m.group(1), term.split()[0]), rt, count=1, flags=re.M)
        if new != rt and not DRY:
            with open(ROFI_TERMINAL + ".i3tmp", "w") as f:
                f.write(new)
            os.replace(ROFI_TERMINAL + ".i3tmp", ROFI_TERMINAL)
    return changed


def refresh_files(settings):
    """After a reinstall: write the saved settings into the freshly copied config files, without touching the
    running session (the installer may run from another desktop). The rest is applied at the next login."""
    global FILES_ONLY
    FILES_ONLY = True
    failed = []
    for step in (apply_cursor, apply_opacity, apply_themes, apply_terminal_font, apply_colors, apply_gaps, apply_apps,
                 apply_gestures, apply_bar_blur):
        try:
            step(settings)
        except Exception as e:  # noqa: BLE001 - one bad setting must not stop the others
            failed.append(step.__name__)
            print("i3 settings: %s failed: %s" % (step.__name__, e), file=sys.stderr)
    try:
        apply_keybinds(settings, reload=False)
    except Exception as e:  # noqa: BLE001
        failed.append("apply_keybinds")
        print("i3 settings: apply_keybinds failed: %s" % e, file=sys.stderr)
    return 1 if failed else 0


def apply_all(settings):
    """Apply every saved setting. One failing step is reported but never stops the others."""
    for step in (apply_mouse, apply_cursor, apply_monitors, apply_opacity, apply_themes, apply_terminal_font, apply_colors,
                 apply_gaps, apply_apps, apply_sound, apply_gestures, apply_bar_blur):
        try:
            step(settings)
        except Exception as e:  # noqa: BLE001 - login must not break on a bad setting
            print("i3 settings: %s failed: %s" % (step.__name__, e), file=sys.stderr)
    try:
        apply_keybinds(settings, reload=True)
    except Exception as e:  # noqa: BLE001
        print("i3 settings: apply_keybinds failed: %s" % e, file=sys.stderr)


# ------------------------------------------------------------------ one settings window at a time
TAB_NAMES = ("mouse", "displays", "appearance", "colors", "themes", "keybindings", "sound", "bluetooth", "network",
             "wifi", "ethernet", "vpn", "proxy")
NET_PARTS = ("wifi", "ethernet", "vpn", "proxy")     # (parts of the Network page: --tab wifi opens it on Wi-Fi)
# the list on the left: (page, name, icon (Nerd Font), words the search finds it by, group)
SIDEBAR = (("network", "Network", "\U000F05A9", "network wifi wi-fi wireless internet ethernet lan wired cable ip "
                                                  "address dns router gateway proxy vpn wireguard openvpn", 0),
           ("bluetooth", "Bluetooth", "\U000F00AF", "bluetooth pair headphones earbuds speaker devices", 0),
           ("sound", "Sound", "\U000F057E", "sound volume audio speakers headphones microphone mic output input", 0),
           ("displays", "Displays", "\U000F0379", "displays monitors screens resolution refresh rate rotate rotation "
                                                    "scale arrange primary brightness backlight dim", 1),
           ("appearance", "Appearance", "\U000F056E", "appearance bar opacity transparency gaps tiling spiral blur "
                                                        "workspaces position size style", 1),
           ("colors", "Colors", "\U000F03D8", "colors colours accent", 1),
           ("themes", "Themes", "\U000F018D", "themes terminal ghostty kitty font text size colours", 1),
           ("mouse", "Mouse", "\U000F037D", "mouse touchpad trackpad pointer speed acceleration cursor gestures "
                                              "swipe", 2),
           ("keybindings", "Keybindings", "\U000F030C", "keybindings keyboard shortcuts keys hotkeys apps "
                                                          "applications terminal browser", 2))
GUI_SOCKET = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "i3dots-settings-%d.sock" % os.getuid())


def hand_over(tab=None):
    """If a settings window is already open, ask it to come to the front (and show `tab`). True if it answered."""
    import socket
    try:
        if os.stat(GUI_SOCKET).st_uid != os.getuid():
            return False                                # not ours: never talk to someone else's socket
    except OSError:
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(GUI_SOCKET)
        s.sendall(("show %s\n" % (tab if tab in TAB_NAMES else "")).encode())
        return s.recv(16).startswith(b"ok")
    except OSError:
        return False
    finally:
        s.close()


# ------------------------------------------------------------------ GUI
CSS_TEMPLATE = """
* { font-family: "FantasqueSansM Nerd Font Mono", "Fantasque Sans Mono", monospace; font-size: 11pt;
    color: #e6e6e6; background-image: none; box-shadow: none; outline-style: none; text-shadow: none;
    -gtk-outline-radius: 8px; }
*:disabled { opacity: 0.4; }
window, dialog, notebook, notebook > stack, scrolledwindow, viewport, stack { background-color: #000000; }
notebook, notebook > stack { border: none; }
/* dialogs and the file chooser (GTK gives them their own backgrounds) */
messagedialog, messagedialog box, messagedialog .dialog-action-area, dialog box, filechooser, filechooser box,
filechooser paned, filechooser stack, filechooser .dialog-action-area { background-color: #000000; }
messagedialog .dialog-action-area { padding: 6px 12px 12px 12px; }
messagedialog .dialog-action-area button { margin: 4px; }
messagedialog label.title { color: #e6e6e6; font-size: 12pt; }
list, list row, placessidebar, placessidebar list, placessidebar row { background-color: #0a0a0a; }
list row:hover, placessidebar row:hover { background-color: #161616; }
list row:selected, placessidebar row:selected { background-color: @A@; }
list row:selected label, placessidebar row:selected label, placessidebar row:selected image { color: #000000; }
filechooser .path-bar button { padding: 4px 12px; }
list row box, placessidebar row box, treeview header button box, filechooser .path-bar box,
messagedialog .dialog-action-area box { background-color: transparent; }
filechooser actionbar, actionbar { background-color: #0a0a0a; border-top: 1px solid #1f1f1f; }
headerbar, .titlebar { background-color: #0a0a0a; border-bottom: 1px solid #1f1f1f; }
separator { background-color: #1f1f1f; min-height: 1px; min-width: 1px; }

/* the list of pages on the left (like macOS System Settings) */
.sidebar, .sidebar scrolledwindow, .sidebar viewport, .sidebar list { background-color: #0a0a0a; }
.sidebar { border-right: 1px solid #1c1c1c; }
.sidebar row { padding: 5px 8px; margin: 1px 10px; border-radius: 9px; background-color: transparent; }
.sidebar row:hover { background-color: #161616; }
.sidebar row:selected, .sidebar row:selected:focus { background-color: @A@; }
.sidebar row:selected label { color: #000000; }
.sidebar row:selected .chip { background-color: #000000; color: @A@; }
.chip { background-color: #1f1f1f; color: #e6e6e6; border-radius: 7px; min-width: 28px; min-height: 28px;
        font-size: 13pt; }
.navlabel { font-size: 11pt; }
.brand { font-size: 10pt; color: #6e6e6e; }

/* text */
label.title { color: @A@; font-size: 12.5pt; font-weight: bold; }
label.title.pagetitle { font-size: 18pt; }
label.dim { color: #7a7a7a; font-size: 10pt; }
label.status { color: #8c8c8c; }
label.value { color: #bdbdbd; }

/* settings grouped in rounded cards */
.card { background-color: #0d0d0d; border: 1px solid #1f1f1f; border-radius: 12px; }
.card box, .card label { background-color: transparent; }
.card > .setrow { padding: 9px 14px; }
.card > .setrow.sep { border-top: 1px solid #1a1a1a; }
.listcard { background-color: #0d0d0d; border: 1px solid #1f1f1f; border-radius: 12px; padding: 6px; }
.listcard scrolledwindow, .listcard viewport { background-color: #0d0d0d; }

/* lists */
treeview, treeview.view { background-color: #0d0d0d; color: #e6e6e6; }
treeview.view:hover { background-color: #161616; }
treeview.view:selected, treeview.view:selected:focus { background-color: @A@; color: #000000; }
treeview header button { background-color: #0d0d0d; color: #7a7a7a; border: none; border-bottom: 1px solid #1f1f1f;
                         border-radius: 0; padding: 6px 10px; box-shadow: none; }
treeview header button:hover { background-color: #0d0d0d; color: #bdbdbd; }

/* text fields: rounded; the search field is a pill */
entry { background-color: #0f0f0f; color: #e6e6e6; border: 1px solid #2e2e2e; border-radius: 9px; padding: 6px 10px;
        caret-color: @A@; }
entry:focus { border-color: #8c8c8c; box-shadow: 0 0 0 3px @G@; }
entry selection { background-color: @A@; color: #000000; }
entry.search, searchentry { border-radius: 999px; padding: 6px 12px; background-color: #141414; }
entry image { color: #6e6e6e; }

/* buttons: outlined pills (Normal / hover / Focus / Active), the main one filled */
button { background-color: transparent; color: #e6e6e6; border: 1px solid #4a4a4a; border-radius: 999px;
         padding: 6px 18px; }
button:hover { background-color: #121212; border-color: #9a9a9a; }
button:active, button:checked { background-color: #262626; border-color: #bdbdbd; }
button:focus { border-color: @A@; box-shadow: 0 0 0 3px @G@; }
button.suggested-action { background-color: @A@; border-color: @A@; color: #000000; font-weight: bold; }
button.suggested-action label { color: #000000; }
button.suggested-action:hover { background-color: @S@; border-color: @S@; }
button.destructive-action { border-color: #6e6e6e; }
combobox button, combobox button * { background-color: #0f0f0f; color: #e6e6e6; }
combobox button { border: 1px solid #2e2e2e; border-radius: 9px; padding: 5px 12px; }
combobox button:hover { border-color: #6e6e6e; }
combobox arrow { color: #8c8c8c; }
spinbutton { border-radius: 9px; }
spinbutton button { border: none; border-radius: 0; padding: 4px 8px; }

/* the segmented switcher (Wi-Fi / Ethernet / VPN / Proxy) */
.segmented { background-color: #0d0d0d; border: 1px solid #262626; border-radius: 999px; padding: 3px; }
.segmented button { border: none; border-radius: 999px; background-color: transparent; color: #8c8c8c;
                    padding: 5px 20px; box-shadow: none; }
.segmented button:hover { color: #e6e6e6; background-color: #161616; }
.segmented button:checked { background-color: @A@; }
.segmented button:checked label { color: #000000; }

/* menus */
menu, .menu, menu menuitem, menu menuitem *, popover, popover * { background-color: #0f0f0f; color: #e6e6e6; }
menu, popover { border: 1px solid #262626; border-radius: 10px; padding: 4px; }
menu menuitem { border-radius: 7px; padding: 5px 10px; }
menu menuitem:hover, menu menuitem:hover * { background-color: @A@; color: #000000; }

/* sliders: a thin rounded track and a round knob */
scale trough { background-color: #262626; min-height: 4px; min-width: 4px; border: none; border-radius: 999px; }
scale trough highlight { background-color: @A@; border: none; border-radius: 999px; }
scale slider { background-color: @A@; min-width: 16px; min-height: 16px; border-radius: 999px; border: 3px solid #000000;
               margin: -9px; }
scale slider:hover { box-shadow: 0 0 0 4px @G@; }
scale value, scale marks, scale mark label { color: #8c8c8c; }

/* switches: a pill with a round knob */
switch { background-color: #262626; border: 1px solid #3a3a3a; border-radius: 999px; min-width: 44px;
         min-height: 22px; padding: 2px; }
switch:checked { background-color: @A@; border-color: @A@; }
switch slider { background-color: #9a9a9a; border-radius: 999px; border: none; min-width: 20px; min-height: 20px;
                margin: 0; }
switch:checked slider { background-color: #000000; }
switch image { color: transparent; }

/* check boxes (rounded squares) and radio buttons (circles) */
checkbutton check, treeview check { background-color: #0f0f0f; border: 1px solid #6e6e6e; border-radius: 5px;
                                    min-width: 16px; min-height: 16px; color: #000000; }
checkbutton check:checked, treeview check:checked { background-color: @A@; border-color: @A@; }
radiobutton radio { background-color: #0f0f0f; border: 1px solid #8c8c8c; border-radius: 999px; min-width: 16px;
                    min-height: 16px; color: #000000; }
radiobutton radio:checked { background-color: @A@; border-color: @A@; }

scrollbar, scrollbar trough { background-color: transparent; border: none; }
scrollbar slider { background-color: #2e2e2e; border-radius: 999px; min-width: 6px; min-height: 6px; border: none; }
scrollbar slider:hover { background-color: #6e6e6e; }
frame > border { border: 1px solid #1f1f1f; border-radius: 12px; }
frame > label { color: @A@; font-weight: bold; }

/* the Displays canvas */
.canvas { background-color: #0a0a0a; border: 1px solid #1f1f1f; border-radius: 12px; }
.mon { background-color: #262626; border: 1px solid #8c8c8c; border-radius: 8px; }
.mon box, .mon-ghost box { background-color: transparent; }
.mon label { color: #e6e6e6; }
.mon .mon-num { font-size: 22pt; font-weight: bold; }
.mon .mon-name { font-size: 9pt; color: #8c8c8c; }
.mon-sel { background-color: @A@; border-color: @A@; }
.mon-sel label, .mon-sel .mon-num, .mon-sel .mon-name { color: #000000; }
.mon-ghost { background-color: @G@; border: 2px solid @S@; border-radius: 8px; }
.mon-off { background-color: #141414; border: 1px dashed #6e6e6e; }
.mon-off label, .mon-off .mon-name { color: #6e6e6e; }
.mon-off .mon-num { font-size: 14pt; }
.mon-off.mon-sel { border: 2px solid @A@; }
.mon-off.mon-sel label { color: @A@; }
.ident { font-size: 72pt; font-weight: bold; color: #000000; background-color: @A@; padding: 10px 40px;
         border-radius: 16px; }
"""


def css_for(accent=ACCENT_DEFAULT):
    """The Settings window stylesheet in the chosen accent colour."""
    accent = norm_accent(accent) or ACCENT_DEFAULT
    c = accent_palette(accent)
    ghost = "rgba(%d,%d,%d,0.18)" % tuple(int(accent[i:i + 2], 16) for i in (1, 3, 5))
    return CSS_TEMPLATE.replace("@A@", c["A"]).replace("@S@", c["S"]).replace("@G@", ghost).encode()


def launch_gui(confirm=True, tab=None):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk
    # pictures of the bar need cairo for Python (python3-cairo / python-cairo / python3-gi-cairo); without it the
    # window works the same, just without the pictures
    try:
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import PangoCairo
        import cairo
        gi.require_foreign("cairo")
        have_cairo = PangoCairo is not None
    except (ImportError, ValueError, AttributeError):
        cairo, have_cairo = None, False

    GLib.set_prgname("i3dots-settings")
    Gdk.set_program_class("i3dots-settings")

    if Gdk.Screen.get_default() is None:
        print("i3 settings: no graphical display (start it from your i3 session, e.g. SUPER+ALT+M)", file=sys.stderr)
        return 1
    provider = Gtk.CssProvider()
    settings = load_settings()
    live_accent = {"v": saved_accent(settings)}       # the colour picked in the Colors tab, before Apply too
    accent_listeners = []                             # called when it changes (the bar pictures follow it)
    provider.load_from_data(css_for((settings.get('colors') or {}).get('accent')))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    win = Gtk.Window(title="Settings")
    # fit the screen the pointer is on: on a small or scaled screen (e.g. a 1440x900 laptop) the buttons must
    # stay visible
    try:
        disp = Gdk.Display.get_default()
        try:
            _scr, px_, py_ = disp.get_default_seat().get_pointer().get_position()
            mon_ = disp.get_monitor_at_point(px_, py_)
        except Exception:  # noqa: BLE001
            mon_ = disp.get_primary_monitor() or disp.get_monitor(0)
        wa = mon_.get_workarea()
        win.set_default_size(min(1280, wa.width - 40), min(940, wa.height - 60))
    except Exception:  # noqa: BLE001
        win.set_default_size(1200, 760)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.connect("destroy", Gtk.main_quit)

    # the pages listed on the left (like macOS System Settings); the page on the right, Close / Apply under it.
    # The pages live in a notebook without tabs: the list on the left switches them.
    root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    win.add(root)
    sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    sidebar.get_style_context().add_class("sidebar")
    sidebar.set_size_request(236, -1)
    root.pack_start(sidebar, False, False, 0)
    main_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    root.pack_start(main_col, True, True, 0)
    nb = Gtk.Notebook()
    nb.set_show_tabs(False)
    nb.set_show_border(False)
    main_col.pack_start(nb, True, True, 0)
    page_w = {}                             # page name -> its widget in the notebook
    page_boxes = []                         # every page's box: their setting rows are grouped into cards at the end
    part_boxes = []                         # (the same for the parts of a page)

    def add_page(name, widget):
        page_w[name] = widget
        nb.append_page(widget, Gtk.Label(label=name))

    def page():
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side_ in ("top", "bottom", "start", "end"):
            getattr(box, "set_margin_" + side_)(26 if side_ in ("start", "end") else 22)
        page_boxes.append(box)
        return box

    def cardify(box, part=False, name=None):
        """Group each run of setting rows (row()) in a page into one rounded card, with a thin line between rows.
        A page starts with its name in large letters (its own first heading when that already says it; not in a
        part of a page, like the Network parts)."""
        run_ = []

        def flush():
            if not run_:
                return
            at = box.get_children().index(run_[0])
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            card.get_style_context().add_class("card")
            for i, w in enumerate(run_):
                box.remove(w)
                if i:
                    w.get_style_context().add_class("sep")
                card.pack_start(w, False, False, 0)
            box.pack_start(card, False, False, 0)
            box.reorder_child(card, at)
            run_.clear()
        for w in box.get_children():
            if isinstance(w, Gtk.Box) and w.get_style_context().has_class("setrow") and w.get_parent() is box:
                run_.append(w)
            else:
                flush()
        flush()
        if part:
            return
        kids = box.get_children()
        first = kids[0] if kids and isinstance(kids[0], Gtk.Label) and \
            kids[0].get_style_context().has_class("title") else None
        if first is not None and (name is None or first.get_text().lower().startswith(name.lower())):
            first.get_style_context().add_class("pagetitle")       # the page's own heading: larger
        elif name:
            t_ = Gtk.Label(label=name, xalign=0)
            t_.get_style_context().add_class("title")
            t_.get_style_context().add_class("pagetitle")
            box.pack_start(t_, False, False, 0)
            box.reorder_child(t_, 0)

    def scrolled(box):
        """Every tab scrolls, so the window never has to be taller than the screen."""
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(box)
        return sw

    def guard_scroll(widget):
        """The mouse wheel scrolls the page; it never changes a dropdown, and only changes a slider or number box
        that you clicked into first (GTK would otherwise change whatever the pointer passes over while scrolling)."""
        def on_scroll(w, ev):
            if isinstance(w, (Gtk.Scale, Gtk.SpinButton)) and w.has_focus():
                return False
            sw = w.get_ancestor(Gtk.ScrolledWindow)
            if sw is not None:
                adj = sw.get_vadjustment()
                ok, _dx, dy = ev.get_scroll_deltas()
                if not ok:
                    dy = {Gdk.ScrollDirection.UP: -1, Gdk.ScrollDirection.DOWN: 1}.get(ev.direction, 0)
                top = adj.get_upper() - adj.get_page_size()
                adj.set_value(max(adj.get_lower(), min(top, adj.get_value() + dy * 60)))
            return True
        if getattr(widget, "_scroll_guarded", False):
            return widget
        widget._scroll_guarded = True
        widget.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        widget.connect("scroll-event", on_scroll)
        return widget

    def guard_all(w):
        if isinstance(w, (Gtk.ComboBox, Gtk.Scale, Gtk.SpinButton)):
            guard_scroll(w)
        if isinstance(w, Gtk.Container):
            for child in w.get_children():
                guard_all(child)

    def dim(text):
        lb = Gtk.Label(label=text, xalign=0)
        lb.get_style_context().add_class("dim")
        lb.set_line_wrap(True)
        return lb

    def row(label, widget, width=230):
        r = Gtk.Box(spacing=12)
        r.get_style_context().add_class("setrow")
        lb = Gtk.Label(label=label, xalign=0)
        lb.set_size_request(width, -1)
        r.pack_start(lb, False, False, 0)
        r.pack_start(widget, True, True, 0)
        return r

    # ---------------- mouse tab
    mp = page()
    t = Gtk.Label(label="Mouse & touchpad", xalign=0)
    t.get_style_context().add_class("title")
    mp.pack_start(t, False, False, 0)

    devices = list_pointer_devices()
    dev_combo = Gtk.ComboBoxText()
    dev_combo.append(ALL, "All mice and touchpads")
    for d in devices:
        dev_combo.append(d, d)
    dev_combo.set_active_id(ALL)
    mp.pack_start(row("Device", dev_combo), False, False, 0)

    speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.05)
    speed.set_digits(2)
    speed.set_value_pos(Gtk.PositionType.RIGHT)
    speed.add_mark(0.0, Gtk.PositionType.BOTTOM, "default")
    mp.pack_start(row("Pointer speed", speed), False, False, 0)

    accel = Gtk.Switch()
    accel.set_halign(Gtk.Align.START)
    mp.pack_start(row("Mouse acceleration", accel), False, False, 0)
    mp.pack_start(dim("Speed goes from -1 (slowest) to +1 (fastest). Acceleration ON: the pointer speeds up the "
                      "faster you move your hand, and the slider sets how soon and how far it speeds up. "
                      "Acceleration OFF: a flat response - the same hand movement always moves the pointer the same "
                      "distance, and the slider is a plain multiplier. The two settings each remember their own "
                      "speed, so switching acceleration brings back the speed you chose for it. Changes take effect "
                      "right away. 'All mice and touchpads' sets every device; pick one device to give it its own "
                      "settings. A mouse that is plugged in or reconnects later (Bluetooth) gets them too."),
                  False, False, 0)
    mouse_state = dim("")
    mp.pack_start(row("Right now", mouse_state), False, False, 0)
    if not devices:
        mp.pack_start(dim("No mouse or touchpad with libinput settings was found. "
                          "Settings will still be saved and applied the next time a device is detected."), False, False, 0)

    # touchpad gestures section (same tab)
    mp.pack_start(Gtk.Separator(), False, False, 6)
    gt = Gtk.Label(label="Touchpad gestures", xalign=0)
    gt.get_style_context().add_class("title")
    mp.pack_start(gt, False, False, 0)
    gest_saved = gesture_choice(settings)
    gest_on = Gtk.Switch()
    gest_on.set_halign(Gtk.Align.START)
    gest_on.set_active(gest_saved["enabled"])
    mp.pack_start(row("Three-finger swipe", gest_on), False, False, 0)
    gest_dir = Gtk.ComboBoxText()
    gest_dir.append("natural", "Swipe left goes to the next workspace (like a Mac)")
    gest_dir.append("reverse", "Swipe right goes to the next workspace")
    gest_dir.set_active_id("natural" if gest_saved["natural"] else "reverse")
    gest_dir_row = row("Direction", gest_dir)
    mp.pack_start(gest_dir_row, False, False, 0)
    gest_on.connect("notify::active", lambda *_: gest_dir_row.set_sensitive(gest_on.get_active()))
    gest_dir_row.set_sensitive(gest_on.get_active())
    gest_state = touchegg_state()
    mp.pack_start(dim("Put three fingers on the touchpad and swipe to change workspace: 1 -> 2 -> 3 and back, the "
                      "same as SUPER+1/2/3 (an empty workspace is opened too; it stops at 1 and 10). Changes when you "
                      "press Apply."), False, False, 0)
    if gest_state == "missing":
        mp.pack_start(dim(TOUCHEGG_HINT), False, False, 0)

    # cursor theme section (same tab)
    sep = Gtk.Separator()
    mp.pack_start(sep, False, False, 6)
    ct = Gtk.Label(label="Mouse cursor", xalign=0)
    ct.get_style_context().add_class("title")
    mp.pack_start(ct, False, False, 0)
    cur_saved = settings.get("cursor", {})
    cur_now_theme, cur_now_size = current_cursor()          # what the desktop uses now (nothing saved yet)
    themes = list_cursor_themes()
    if cur_saved.get("theme") and cur_saved["theme"] not in themes:
        themes.append(cur_saved["theme"])
    cur_effective, _cur_sz = cursor_choice(settings, themes)   # (the saved one, else the default Capitaine Cursors)
    cur_combo = Gtk.ComboBoxText()
    for th in themes:
        cur_combo.append(th, th + ("  (default)" if th == CURSOR_DEFAULT_THEME else ""))
    cur_combo.set_active_id(cur_effective or (cur_now_theme if cur_now_theme in themes else None)
                            or ("Adwaita" if "Adwaita" in themes else None))
    if cur_combo.get_active_id() is None and themes:
        cur_combo.set_active(0)
    mp.pack_start(row("Cursor theme", cur_combo), False, False, 0)
    cur_size = Gtk.ComboBoxText()
    for sz in CURSOR_SIZES:
        cur_size.append(str(sz), "%d px%s" % (sz, "  (default)" if sz == CURSOR_DEFAULT_SIZE else ""))
    # (the size the login applies: the saved one; with the default theme and nothing saved, the default size)
    cur_size.set_active_id(str(cur_saved.get("size", _cur_sz if cur_effective and not cur_saved.get("theme")
                                             else cur_now_size)))
    if cur_size.get_active_id() is None:
        cur_size.set_active_id(str(CURSOR_DEFAULT_SIZE))
    mp.pack_start(row("Cursor size", cur_size), False, False, 0)
    cur_prev = Gtk.Image()
    cur_prev.set_halign(Gtk.Align.START)
    mp.pack_start(row("Preview", cur_prev), False, False, 0)
    mp.pack_start(dim("Used by every program, so the pointer looks the same over every window. The default is "
                      "Capitaine Cursors (installed with this desktop). Open GTK apps switch at once; other programs "
                      "that are already open when you restart them (Qt and Electron apps from your next login). More "
                      "themes: install a cursor theme (for example 'bibata-cursor-theme' where your system has it) or "
                      "put one in ~/.local/share/icons."), False, False, 0)
    if not themes:
        mp.pack_start(dim("No cursor themes were found in /usr/share/icons or ~/.icons."), False, False, 0)

    def cursor_preview(*_):
        theme, size = cur_combo.get_active_id(), cur_size.get_active_id()
        if not theme or not size:
            return
        st = Gtk.Settings.get_default()
        old = (st.get_property("gtk-cursor-theme-name"), st.get_property("gtk-cursor-theme-size"))
        try:
            st.set_property("gtk-cursor-theme-name", theme)
            st.set_property("gtk-cursor-theme-size", int(size))
            cur = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "left_ptr")
            pb = cur.get_image() if cur else None
            if pb is not None:
                cur_prev.set_from_pixbuf(pb)
        except Exception:  # noqa: BLE001 - the preview is optional
            pass
        finally:
            # only the picture changes: the settings window's own cursor stays the one the rest of the desktop
            # uses (it used to switch to the previewed size, so the pointer grew while this window was open)
            try:
                st.set_property("gtk-cursor-theme-name", old[0])
                st.set_property("gtk-cursor-theme-size", old[1])
            except Exception:  # noqa: BLE001
                pass

    cur_combo.connect("changed", cursor_preview)
    cur_size.connect("changed", cursor_preview)
    add_page("mouse", scrolled(mp))

    loading = {"v": False}

    def device_cfg(dev):
        """The (cleaned) setting a device starts from: its own, else the one for all devices, else the defaults."""
        return mouse_config(settings["mouse"].get(dev) or settings["mouse"].get(ALL) or {})

    def load_device(*_):
        loading["v"] = True
        cfg = device_cfg(dev_combo.get_active_id())
        accel.set_active(cfg["accel"])
        speed.set_value(cfg["speed"])
        loading["v"] = False

    def show_state(*_):
        lines = []
        try:
            lines = mouse_status()
        except Exception:  # noqa: BLE001 - only a readout
            pass
        mouse_state.set_text("\n".join(lines) if lines else "(no mouse or touchpad with libinput settings found)")

    mouse_live = {"id": 0}
    mouse_saved = {"v": json.loads(json.dumps(settings["mouse"]))}   # what Apply last saved

    def mouse_revert(*_):
        """Closing without Apply puts the mouse back the way it was saved (the slider changed it live)."""
        if settings["mouse"] != mouse_saved["v"]:
            try:
                apply_mouse({"mouse": mouse_saved["v"]})
            except Exception:  # noqa: BLE001 - closing must always work
                pass
    win.connect("destroy", mouse_revert)

    def store_device(widget=None, *_):
        if loading["v"]:
            return
        dev = dev_combo.get_active_id()
        cfg = device_cfg(dev)
        if widget is accel:
            # acceleration flipped: the slider moves to the speed that mode remembers
            cfg["accel"] = accel.get_active()
            loading["v"] = True
            speed.set_value(cfg["speed_on"] if cfg["accel"] else cfg["speed_off"])
            loading["v"] = False
        else:
            cfg["speed_on" if cfg["accel"] else "speed_off"] = round(speed.get_value(), 2)
        cfg["speed"] = cfg["speed_on"] if cfg["accel"] else cfg["speed_off"]
        if dev == ALL:
            settings["mouse"] = {ALL: cfg}          # "all" means every device: drop the ones set one by one
        else:
            settings["mouse"][dev] = cfg
        # feel it right away (a short wait, so dragging the slider does not run xinput for every step)
        if mouse_live["id"]:
            GLib.source_remove(mouse_live["id"])

        def live():
            mouse_live["id"] = 0
            try:
                apply_mouse(settings)
            except Exception as e:  # noqa: BLE001 - a live preview must never break the window
                print("i3 settings: mouse: %s" % e, file=sys.stderr)
            show_state()
            return False
        mouse_live["id"] = GLib.timeout_add(200, live)

    dev_combo.connect("changed", load_device)
    speed.connect("value-changed", store_device)
    accel.connect("notify::active", lambda *_: store_device(accel))
    load_device()
    show_state()
    cursor_preview()

    # ---------------- monitors tab
    mon = page()
    t = Gtk.Label(label="Displays", xalign=0)
    t.get_style_context().add_class("title")
    mon.pack_start(t, False, False, 0)
    outputs = sorted(parse_xrandr(query(["xrandr", "--query"])), key=lambda o: (o.x, o.y))
    number = {o.name: i + 1 for i, o in enumerate(outputs)}
    saved_m = settings.get("monitors", {})
    widgets = {}
    boxes = {}
    pos = {}
    first_on = next((o for o in outputs if saved_m.get(o.name, {}).get("enabled", o.enabled)), None)
    ui = {"sel": (first_on or outputs[0]).name if outputs else None, "drag": None}
    CW, CH = 790, 290
    OFF_W, OFF_H, OFF_STRIP = 120, 54, 66      # screens that are switched off: small boxes in a row at the bottom

    mon.pack_start(dim("Drag the numbered screens to match your desk. Click one to change its settings. A screen "
                       "that is switched off stays in the list: it is shown greyed out along the bottom - click it "
                       "and turn Enabled on to use it again."), False, False, 0)
    canvas = Gtk.Fixed()
    canvas.set_size_request(CW, CH)
    canvas.get_style_context().add_class("canvas")
    cframe = Gtk.EventBox()
    cframe.get_style_context().add_class("canvas")
    cframe.add(canvas)
    mon.pack_start(cframe, False, False, 0)
    ghost = Gtk.Box()
    ghost.get_style_context().add_class("mon-ghost")
    canvas.put(ghost, 0, 0)

    tools = Gtk.Box(spacing=10)
    ident_btn = Gtk.Button(label="Identify")
    tools.pack_start(ident_btn, False, False, 0)
    mon.pack_start(tools, False, False, 0)

    stack = Gtk.Stack()
    mon.pack_start(stack, True, True, 0)
    primary_group = None
    scales = {}              # monitor name -> scale combo

    def enabled_names():
        return [o.name for o in outputs if widgets[o.name][0].get_active()]

    def size_of(name):
        en, res, hz, rot, pr = widgets[name]
        m = res.get_active_id()
        sc = scales[name].get_active_id()
        return out_size(m, rot.get_active_id() or "normal", int(sc) if sc else 100) if m else (1920, 1080)

    def rect_of(name, at=None):
        x, y = at if at else pos[name]
        w, h = size_of(name)
        return (x, y, w, h)

    def settle():
        """Make the layout valid: no overlaps, every screen touching another one."""
        placed = []
        for n in enabled_names():
            r = rect_of(n)
            if placed and (any(overlaps(r, p) for p in placed) or not any(touching(r, p) for p in placed)):
                x, y = snap_position(placed, (r[2], r[3]), (r[0], r[1]))
                r = (x, y, r[2], r[3])
                pos[n] = (x, y)
            placed.append(r)

    def view_for(rects, ch=CH):
        if not rects:
            return 1.0, 0.0, 0.0
        x0 = min(r[0] for r in rects)
        y0 = min(r[1] for r in rects)
        x1 = max(r[0] + r[2] for r in rects)
        y1 = max(r[1] + r[3] for r in rects)
        # leave room around the layout so a screen can be dragged to any side
        world_w = (x1 - x0) + 0.9 * max(r[2] for r in rects)
        world_h = (y1 - y0) + 0.9 * max(r[3] for r in rects)
        sc = min(CW / world_w, ch / world_h)
        return sc, CW / 2 - (x0 + x1) / 2 * sc, ch / 2 - (y0 + y1) / 2 * sc

    def place_all(view=None):
        names = enabled_names()
        off = [o.name for o in outputs if o.name not in names]
        sc, ox, oy = view or view_for([rect_of(n) for n in names], CH - (OFF_STRIP if off else 0))
        ui["view"] = (sc, ox, oy)
        for o in outputs:
            b = boxes[o.name]
            ctx = b.get_style_context()
            if o.name in names:
                x, y, w, h = rect_of(o.name)
                b.set_size_request(max(30, int(w * sc)), max(24, int(h * sc)))
                canvas.move(b, int(ox + x * sc), int(oy + y * sc))
                ctx.remove_class("mon-off")
                b.sub.set_text("%s%s" % (o.name, "  ★" if widgets[o.name][4].get_active() else ""))
            else:
                # switched off: not part of the layout, but still on show (and clickable) so it can be turned back on
                i = off.index(o.name)
                b.set_size_request(OFF_W, OFF_H)
                canvas.move(b, 8 + i * (OFF_W + 10), CH - OFF_H - 6)
                ctx.add_class("mon-off")
                b.sub.set_text("%s  (off)" % o.name)
            b.set_opacity(1)
            (ctx.add_class if o.name == ui["sel"] else ctx.remove_class)("mon-sel")
        canvas.move(ghost, -5000, -5000)
        ghost.set_opacity(0)

    def select(name):
        ui["sel"] = name
        stack.set_visible_child_name(name)
        place_all(ui["view"] if ui["drag"] else None)

    def on_press(box, ev, name):
        if ev.button != 1:
            return False
        select(name)
        if name not in enabled_names():
            return True                           # a screen that is off is only selected, not dragged
        ui["drag"] = {"name": name, "x": ev.x_root, "y": ev.y_root, "start": pos[name], "raw": pos[name]}
        return True

    def on_motion(box, ev, name):
        d = ui["drag"]
        if not d or d["name"] != name:
            return False
        sc, ox, oy = ui["view"]
        rx = d["start"][0] + (ev.x_root - d["x"]) / sc
        ry = d["start"][1] + (ev.y_root - d["y"]) / sc
        d["raw"] = (rx, ry)
        w, h = size_of(name)
        canvas.move(box, int(ox + rx * sc), int(oy + ry * sc))
        others = [rect_of(n) for n in enabled_names() if n != name]
        gx, gy = snap_position(others, (w, h), (rx, ry))
        ghost.set_size_request(max(30, int(w * sc)), max(24, int(h * sc)))
        canvas.move(ghost, int(ox + gx * sc), int(oy + gy * sc))
        ghost.set_opacity(1)
        d["snap"] = (gx, gy)
        return True

    def on_release(box, ev, name):
        d = ui["drag"]
        ui["drag"] = None
        if d and d["name"] == name:
            if "snap" in d:
                pos[name] = (int(round(d["snap"][0])), int(round(d["snap"][1])))
            place_all()
        return True

    for o in outputs:
        sv = saved_m.get(o.name, {})
        pos[o.name] = (sv["x"], sv["y"]) if "x" in sv and "y" in sv else (o.x, o.y)

        frame = Gtk.Frame(label=" %d  -  %s " % (number[o.name], o.name))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, "set_margin_" + side)(14)
        frame.add(box)

        en = Gtk.Switch()
        en.set_halign(Gtk.Align.START)
        en.set_active(sv.get("enabled", o.enabled))
        box.pack_start(row("Enabled", en, 150), False, False, 0)

        res = Gtk.ComboBoxText()
        for m in sorted(o.modes, key=mode_area, reverse=True):
            res.append(m, m.replace("x", " × "))
        want_mode = sv.get("mode") or o.cur_mode or (max(o.modes, key=mode_area) if o.modes else None)
        res.set_active_id(want_mode)
        box.pack_start(row("Resolution", res, 150), False, False, 0)

        hz = Gtk.ComboBoxText()
        box.pack_start(row("Refresh rate", hz, 150), False, False, 0)

        def make_fill(res, hz, o):
            def fill(want=None):
                hz.remove_all()
                for r in o.modes.get(res.get_active_id() or "", []):
                    hz.append(r, "%s Hz" % r)
                if not (want and hz.set_active_id(want)):
                    hz.set_active(0)
            return fill
        fill = make_fill(res, hz, o)
        fill(sv.get("rate") or o.cur_rate)
        res.connect("changed", lambda *_a, f=fill: f(None))

        rot = Gtk.ComboBoxText()
        for key, label in ROTATIONS:
            rot.append(key, label)
        rot.set_active_id(sv.get("rotate", o.rotate))
        box.pack_start(row("Orientation", rot, 150), False, False, 0)

        sc = Gtk.ComboBoxText()
        for v in SCALES:
            sc.append(str(v), "%d%%%s" % (v, "  (default)" if v == 100 else ""))
        want = sv.get("scale", o.scale)
        sc.set_active_id(str(want if want in SCALES else 100))
        scales[o.name] = sc
        box.pack_start(row("Scale", sc, 150), False, False, 0)
        note = Gtk.Label(label="Makes everything bigger on this screen (good for high-resolution screens). "
                               "Higher values look a little softer than a native resolution.")
        note.set_xalign(0)
        note.set_line_wrap(True)
        note.get_style_context().add_class("dim-label")
        box.pack_start(row("", note, 150), False, False, 0)

        pr = Gtk.RadioButton.new_with_label_from_widget(primary_group, "Make this the primary display")
        if primary_group is None:
            primary_group = pr
        pr.set_active(sv.get("primary", o.primary))
        box.pack_start(row("", pr, 150), False, False, 0)

        widgets[o.name] = (en, res, hz, rot, pr)
        stack.add_named(frame, o.name)

        eb = Gtk.EventBox()
        eb.get_style_context().add_class("mon")
        eb.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                      Gdk.EventMask.POINTER_MOTION_MASK)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vb.set_valign(Gtk.Align.CENTER)
        num = Gtk.Label(label=str(number[o.name]))
        num.get_style_context().add_class("mon-num")
        eb.sub = Gtk.Label(label=o.name)
        eb.sub.get_style_context().add_class("mon-name")
        vb.pack_start(num, False, False, 0)
        vb.pack_start(eb.sub, False, False, 0)
        eb.add(vb)
        eb.connect("button-press-event", on_press, o.name)
        eb.connect("motion-notify-event", on_motion, o.name)
        eb.connect("button-release-event", on_release, o.name)
        canvas.put(eb, 0, 0)
        boxes[o.name] = eb

        def changed(*_a):
            settle()
            place_all()
        en.connect("notify::active", changed)
        res.connect("changed", changed)
        rot.connect("changed", changed)
        sc.connect("changed", changed)
        pr.connect("toggled", changed)

    canvas.remove(ghost)          # re-add last so the drop preview is drawn above the screens
    canvas.put(ghost, 0, 0)
    if not outputs:
        mon.pack_start(dim("No displays were detected (xrandr found nothing)."), False, False, 0)
    else:
        settle()
        stack.set_visible_child_name(ui["sel"])
    mon.pack_start(dim("After applying, you get 10 seconds to confirm - if the screen goes dark, "
                       "just wait and it reverts."), False, False, 0)

    # brightness: changes right away (not part of Apply), through Brightness.sh like the brightness keys - the
    # backlight, or on screens without one the picture is dimmed instead
    import threading as _bthreads
    bright_sh = os.path.join(SCRIPTS_DIR, "Brightness.sh")
    bri = {"loading": True, "pending": None, "timer": None, "busy": False}
    bt = Gtk.Label(label="Brightness", xalign=0)
    bt.get_style_context().add_class("title")
    bri_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 1)
    bri_scale.set_digits(0)
    bri_scale.set_value_pos(Gtk.PositionType.RIGHT)
    bri_scale.connect("format-value", lambda _s, v: "%d%%" % v)
    bri_scale.set_sensitive(False)                 # (until the brightness now has been read)
    guard_scroll(bri_scale)
    bri_note = dim("")
    mon.pack_start(bt, False, False, 0)
    bri_row = row("Screens", bri_scale)
    mon.pack_start(bri_row, False, False, 0)
    mon.pack_start(bri_note, False, False, 0)

    def bri_worker(v):
        run([bright_sh, "--set", str(v)])
        GLib.idle_add(bri_done)

    def bri_done():
        bri["busy"] = False
        if bri["pending"] is not None and bri["timer"] is None:
            bri["timer"] = GLib.timeout_add(10, bri_flush)
        return False

    def bri_flush():
        """Send only the latest value (every 90 ms at most, one at a time) while the slider is dragged."""
        bri["timer"] = None
        if bri["busy"] or bri["pending"] is None:
            return False
        v, bri["pending"] = bri["pending"], None
        bri["busy"] = True
        _bthreads.Thread(target=bri_worker, args=(v,), daemon=True).start()
        return False

    def bri_changed(w):
        if bri["loading"]:
            return
        bri["pending"] = int(round(w.get_value()))
        if bri["timer"] is None:
            bri["timer"] = GLib.timeout_add(90, bri_flush)
    bri_scale.connect("value-changed", bri_changed)

    def bri_show(kind, val):
        bri["loading"] = True
        try:
            v = int(float(val))
        except ValueError:
            v = 100
        bri_scale.set_value(max(5, min(100, v)))
        bri_row.get_children()[0].set_text("Built-in screen" if kind == "backlight" else "All screens")
        if kind == "backlight":
            bri_note.set_text("The screen's backlight, the same as the brightness keys. It changes right away.")
        else:
            bri_note.set_text("Your screens have no backlight this computer can control (most desktop monitors "
                              "don't), so this dims the picture instead. It works together with the night light, "
                              "is kept, and comes back when you log in. The monitor's own buttons still set its "
                              "real brightness.")
        bri_scale.set_sensitive(True)
        bri["loading"] = False
        return False

    def bri_load(*_a):
        if bri["busy"] or bri["pending"] is not None:      # (it is being moved right now)
            return

        def work():
            k = query([bright_sh, "--kind"]).strip()
            v = query([bright_sh, "--get"]).strip()
            GLib.idle_add(bri_show, k, v)
        _bthreads.Thread(target=work, daemon=True).start()
    bri_load()
    mon.connect("map", bri_load)          # (back on this tab: the brightness keys may have changed it)
    add_page("displays", scrolled(mon))

    # ---------------- appearance tab
    ap = page()
    t = Gtk.Label(label="Window opacity", xalign=0)
    t.get_style_context().add_class("title")
    ap.pack_start(t, False, False, 0)
    op = settings.get("opacity") or {
        "active": round(read_value(PICOM_CONF, "active-opacity", 1.0) * 100),
        "inactive": round(read_value(PICOM_CONF, "inactive-opacity", 0.95) * 100)}
    if "terminal" not in op:
        op = dict(op, terminal=round(read_value(GHOSTTY_CONF, "background-opacity", 0.95) * 100))

    def pct_scale(value):
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 20, 100, 1)
        sc.set_digits(0)
        sc.set_value_pos(Gtk.PositionType.RIGHT)
        sc.set_value(value)
        sc.connect("format-value", lambda _s, v: "%d%%" % v)
        return sc

    op_active = pct_scale(op.get("active", OPACITY_DEFAULT["active"]))
    op_inactive = pct_scale(op.get("inactive", OPACITY_DEFAULT["inactive"]))
    ap.pack_start(row("Focused window", op_active), False, False, 0)
    ap.pack_start(row("Unfocused windows", op_inactive), False, False, 0)
    op_terminal = pct_scale(op.get("terminal", OPACITY_DEFAULT["terminal"]))
    ap.pack_start(row("Terminal background", op_terminal), False, False, 0)
    ap.pack_start(dim("100% is fully solid; lower is more see-through. Set the unfocused value lower than the "
                      "focused one to make the window you are using stand out. The terminal slider only changes the "
                      "background of Ghostty and kitty (the text stays sharp); it adds to the window values above. "
                      "Needs the compositor (picom) to be running. Video players and fullscreen windows stay solid."),
                  False, False, 0)

    # gaps section (same tab)
    mp_sep = Gtk.Separator()
    ap.pack_start(mp_sep, False, False, 6)
    gt = Gtk.Label(label="Gaps between windows", xalign=0)
    gt.get_style_context().add_class("title")
    ap.pack_start(gt, False, False, 0)
    gp = settings.get("gaps") or {
        "inner": int(read_value(I3_CONFIG, "gaps inner", GAPS_DEFAULT["inner"])),
        "outer": int(read_value(I3_CONFIG, "gaps outer", GAPS_DEFAULT["outer"])),
        "smart": not re.search(r"^\s*smart_gaps\s+off", open(I3_CONFIG).read(), re.M) if os.path.exists(I3_CONFIG) else True}

    def px_scale(value):
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 40, 1)
        sc.set_digits(0)
        sc.set_value_pos(Gtk.PositionType.RIGHT)
        sc.set_value(value)
        sc.connect("format-value", lambda _s, v: "%d px" % v)
        return sc

    gap_inner = px_scale(gp.get("inner", GAPS_DEFAULT["inner"]))
    gap_outer = px_scale(gp.get("outer", GAPS_DEFAULT["outer"]))
    gap_smart = Gtk.Switch()
    gap_smart.set_halign(Gtk.Align.START)
    gap_smart.set_active(bool(gp.get("smart", GAPS_DEFAULT["smart"])))
    ap.pack_start(row("Between windows", gap_inner), False, False, 0)
    ap.pack_start(row("Around the screen edge", gap_outer), False, False, 0)
    ap.pack_start(row("No gaps for a lone window", gap_smart), False, False, 0)
    ap.pack_start(dim("0 px = windows touch (no gap). Turning the last option on makes a single window "
                      "fill the screen. Changing it reloads i3 (your windows stay open)."), False, False, 0)

    # window tiling section (same tab)
    ap.pack_start(Gtk.Separator(), False, False, 6)
    tl = Gtk.Label(label="Window tiling", xalign=0)
    tl.get_style_context().add_class("title")
    ap.pack_start(tl, False, False, 0)
    tiling_mode = Gtk.ComboBoxText()
    for key, label in TILING_LABELS:
        tiling_mode.append(key, label)
    tiling_mode.set_active_id((settings.get("tiling") or {}).get("mode") or "dwindle")
    ap.pack_start(row("New windows", tiling_mode), False, False, 0)
    ap.pack_start(dim("Spiral: each new window takes half of the window you are using - side by side when that window "
                      "is wide, top and bottom when it is tall - just like Hyprland. Classic: new windows are added "
                      "next to each other. Switch any time with SUPER+ALT+T. Tabbed and stacked groups "
                      "(SUPER+ALT+2/3) and floating windows are never changed."), False, False, 0)

    # top bar section (same tab)
    ap.pack_start(Gtk.Separator(), False, False, 6)
    bt = Gtk.Label(label="Bar", xalign=0)
    bt.get_style_context().add_class("title")
    ap.pack_start(bt, False, False, 0)
    bar_saved = settings.get("bar", {})
    bar_pos = Gtk.ComboBoxText()
    bar_pos.append("top", "Top of the screen")
    bar_pos.append("bottom", "Bottom of the screen")
    bar_pos.set_active_id(bar_saved.get("position", "top") if bar_saved.get("position") in ("top", "bottom") else "top")
    ap.pack_start(row("Bar position", bar_pos), False, False, 0)
    bar_size = Gtk.ComboBoxText()
    for key, label in BAR_SIZE_LABELS:
        bar_size.append(key, label)
    bar_size.set_active_id(bar_saved.get("size") if bar_saved.get("size") in BAR_SIZES else BAR_DEFAULT["size"])
    ap.pack_start(row("Bar size", bar_size), False, False, 0)
    saved_choice = bar_choice(settings)

    def picture_combo(options):
        """A dropdown whose entries show a small picture of the bar next to their name."""
        store = Gtk.ListStore(str, str, object)
        for key, label in options:
            store.append([key, label, None])
        combo = Gtk.ComboBox.new_with_model(store)
        combo.set_id_column(0)
        if have_cairo:
            pic = Gtk.CellRendererPixbuf()
            pic.set_padding(4, 3)
            combo.pack_start(pic, False)
            combo.set_cell_data_func(pic, lambda _l, cell, model, it, *_: cell.set_property("surface", model[it][2]))
        text = Gtk.CellRendererText()
        combo.pack_start(text, True)
        combo.add_attribute(text, "text", 1)
        return combo, store
    bar_style, bar_style_store = picture_combo(BAR_STYLES)
    bar_style.set_active_id(saved_choice["style"])
    ap.pack_start(row("Bar style", bar_style), False, False, 0)
    bar_div, bar_div_store = picture_combo(BAR_DIVIDERS)
    bar_div.set_active_id(saved_choice["divider"])
    bar_div_row = row("Block shape", bar_div)
    ap.pack_start(bar_div_row, False, False, 0)
    bar_space = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, BAR_SPACING_MAX, 2)
    bar_space.set_digits(0)
    bar_space.set_value_pos(Gtk.PositionType.RIGHT)
    bar_space.set_value(saved_choice["spacing"])
    bar_space.connect("format-value", lambda _s, v: "%d px" % clean_spacing(int(round(v))))

    def snap_space(sc):
        v = clean_spacing(int(round(sc.get_value())))       # whole, even pixels: half goes on each side of a block
        if v != sc.get_value():
            sc.set_value(v)
    bar_space.connect("value-changed", snap_space)
    bar_space_row = row("Space between blocks", bar_space)
    ap.pack_start(bar_space_row, False, False, 0)
    # the bar's own background: only the dark part around the blocks - the blocks keep their colours
    bar_bg_mode = Gtk.ComboBoxText()
    for key, label in BAR_BG_MODES:
        bar_bg_mode.append(key, label)
    bar_bg_mode.set_active_id(saved_choice["bg_mode"])
    ap.pack_start(row("Bar background", bar_bg_mode), False, False, 0)
    bar_bg_op = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
    bar_bg_op.set_digits(0)
    bar_bg_op.set_value_pos(Gtk.PositionType.RIGHT)
    bar_bg_op.set_value(saved_choice["bg_opacity"])
    bar_bg_op.connect("format-value", lambda _s, v: "%d%%" % v)
    bar_bg_op_row = row("Background opacity", bar_bg_op)
    ap.pack_start(bar_bg_op_row, False, False, 0)
    bar_bg_col = Gtk.ColorButton()
    _c = Gdk.RGBA()
    _c.parse(saved_choice["bg_color"])
    bar_bg_col.set_rgba(_c)
    bar_bg_col.set_title("Bar background colour")
    bar_bg_black = Gtk.Button(label="Black")
    bar_bg_black.connect("clicked", lambda *_: (_c.parse("#000000"), bar_bg_col.set_rgba(_c),
                                                 bar_bg_col.emit("color-set")))
    bg_col_box = Gtk.Box(spacing=8)
    bg_col_box.pack_start(bar_bg_col, False, False, 0)
    bg_col_box.pack_start(bar_bg_black, False, False, 0)
    ap.pack_start(row("Background colour", bg_col_box), False, False, 0)
    ap.pack_start(dim("Only the bar's own background changes - the blocks keep their colours. See-through and Blurred "
                      "show your wallpaper behind the bar (the slider sets how much: 0% is clear glass, 100% solid); "
                      "Blurred frosts it. Both need the compositor (picom) running. The colour works with every mode."),
                  False, False, 0)

    def bar_bg_now():
        rgba = bar_bg_col.get_rgba()
        color = "#%02x%02x%02x" % tuple(round(max(0, min(1, v)) * 255) for v in (rgba.red, rgba.green, rgba.blue))
        mode = bar_bg_mode.get_active_id() or BAR_DEFAULT["bg_mode"]
        return mode, int(round(bar_bg_op.get_value())), color

    def bar_bg_preview():
        mode, op, color = bar_bg_now()
        return {"bar_bg": bar_bg_value(mode, op, color), "blur": mode == "blur"}
    bar_title = Gtk.Switch()
    bar_title.set_halign(Gtk.Align.START)
    bar_title.set_active(bar_saved.get("title") is True)
    ap.pack_start(row("Show the window title", bar_title), False, False, 0)
    bar_media = Gtk.Switch()
    bar_media.set_halign(Gtk.Align.START)
    bar_media.set_active(bar_saved.get("media") is True)
    ap.pack_start(row("Show what is playing", bar_media), False, False, 0)
    # a picture of the bar as it will look, kept up to date with every choice above (and the Colors tab)
    preview_items = bar_items({"media": False})          # the items this computer shows (no battery on a desktop...)
    if have_cairo:
        pvl = Gtk.Label(label="Preview", xalign=0)
        pvl.get_style_context().add_class("dim")
        ap.pack_start(pvl, False, False, 0)
        bar_preview = Gtk.DrawingArea()
        ap.pack_start(bar_preview, False, False, 0)

        def draw_preview(area, cr):
            size = bar_size.get_active_id() or BAR_DEFAULT["size"]
            items = (["playerctl"] if bar_media.get_active() else []) + preview_items
            paint_bar(cr, area.get_allocated_width(), bar_style.get_active_id() or BAR_DEFAULT["style"],
                      bar_div.get_active_id() or BAR_DEFAULT["divider"], live_accent["v"], size, items,
                      title=bar_title.get_active(), bottom=bar_pos.get_active_id() == "bottom",
                      spacing=clean_spacing(int(round(bar_space.get_value()))), **bar_bg_preview())
            return False
        bar_preview.connect("draw", draw_preview)

    def thumb(style, divider, scale):
        w, h = THUMB_SIZE
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * scale, h * scale)
        surf.set_device_scale(scale, scale)
        paint_bar(cairo.Context(surf), w, style, divider, live_accent["v"], thumb=True)
        return surf

    def refresh_bar_pictures(*_):
        style = bar_style.get_active_id() or BAR_DEFAULT["style"]
        bar_div_row.set_sensitive(style in BAR_SHAPED)
        bar_space_row.set_sensitive(style not in BAR_JOINED)      # those join their blocks up
        if not have_cairo:
            return
        try:
            scale = max(1, bar_style.get_scale_factor())
            divider = bar_div.get_active_id() or BAR_DEFAULT["divider"]
            for r in bar_style_store:
                r[2] = thumb(r[0], divider, scale)
            for r in bar_div_store:                          # the shapes, shown in the chosen style (or one colour)
                r[2] = thumb(style if style in BAR_SHAPED else "solid", r[0], scale)
        except Exception as e:  # noqa: BLE001 - a picture that fails must never stop the window
            print("i3 settings: bar pictures: %s" % e, file=sys.stderr)
        bar_preview.set_size_request(-1, BAR_SIZES[bar_size.get_active_id() or BAR_DEFAULT["size"]]["height"] + 1)
        bar_preview.queue_draw()
    for w, sig in ((bar_style, "changed"), (bar_div, "changed"), (bar_size, "changed"), (bar_pos, "changed"),
                   (bar_title, "notify::active"), (bar_media, "notify::active"), (bar_style, "notify::scale-factor")):
        w.connect(sig, refresh_bar_pictures)
    accent_listeners.append(refresh_bar_pictures)
    if have_cairo:
        bar_space.connect("value-changed", lambda *_: bar_preview.queue_draw())

    def bar_bg_changed(*_):
        bar_bg_op_row.set_sensitive((bar_bg_mode.get_active_id() or "solid") != "solid")
        if have_cairo:
            bar_preview.queue_draw()
    bar_bg_mode.connect("changed", bar_bg_changed)
    bar_bg_op.connect("value-changed", bar_bg_changed)
    bar_bg_col.connect("color-set", bar_bg_changed)
    bar_bg_changed()
    refresh_bar_pictures()
    ap.pack_start(dim("Every item on the right of the bar (Wi-Fi, Bluetooth, volume, brightness, stay-awake, night light, "
                      "battery, CPU, RAM, GPU, clock, power) can sit in its own block in your accent colour (Colors tab), "
                      "in a gradient, in two shades, in grey or dark blocks, in one long pill or a powerline chain - or show "
                      "as plain, glowing or underlined text. The shape sets how the ends of the blocks look, the space "
                      "how far apart they are (Pill, Dark pill and Powerline join them up, so it does not apply there). Items your computer has "
                      "no hardware for are left out. The window title and the song or video that is playing are hidden "
                      "unless you switch them on above."),
                  False, False, 0)
    bar_all = Gtk.Switch()
    bar_all.set_halign(Gtk.Align.START)
    bar_sel = bar_saved.get("monitors")
    bar_all.set_active(not bar_sel)
    ap.pack_start(row("Show on all monitors", bar_all), False, False, 0)
    bar_checks = {}
    bar_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    for o in sorted(parse_xrandr(query(["xrandr", "--query"])), key=lambda o: (o.x, o.y)):
        if not o.enabled:
            continue
        cb = Gtk.CheckButton(label="%d  -  %s%s" % (number.get(o.name, len(bar_checks) + 1), o.name,
                                                    "  (primary)" if o.primary else ""))
        cb.set_active(not bar_sel or o.name in bar_sel)
        bar_checks[o.name] = cb
        bar_list.pack_start(cb, False, False, 0)
    bar_list_row = row("Show only on", bar_list)
    ap.pack_start(bar_list_row, False, False, 0)
    ap.pack_start(dim("The numbers match the screens in the Displays tab. The system tray goes on the primary "
                      "monitor if it shows the bar, otherwise on the first one that does. Left and right "
                      "positions are not available: the bar program (polybar) can only sit on the top or bottom."),
                  False, False, 0)

    def bar_toggle(*_):
        bar_list_row.set_sensitive(not bar_all.get_active() and bool(bar_checks))
    bar_all.connect("notify::active", bar_toggle)
    bar_toggle()
    ap_scroll = Gtk.ScrolledWindow()
    ap_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    ap_scroll.add(ap)
    add_page("appearance", ap_scroll)

    # ---------------- keybindings tab
    kp = page()
    t = Gtk.Label(label="Keybindings", xalign=0)
    t.get_style_context().add_class("title")
    kp.pack_start(t, False, False, 0)
    kp.pack_start(dim("Pick a row, then Change key and press the new combination. Super is the key with the "
                      "Windows/logo symbol. Changes are written to your i3 config when you press Apply."),
                  False, False, 0)
    kb_search = Gtk.SearchEntry()
    kb_search.set_placeholder_text("Search by action or key...")
    kp.pack_start(kb_search, False, False, 0)

    try:
        with open(I3_CONFIG) as f:
            kb_binds = parse_binds(f.read())
    except OSError:
        kb_binds = []
    kb_over = dict(settings.get("keybinds") or {})
    kb_default = {b["id"]: kb_over.get(b["id"], {}).get("default", b["key"]) for b in kb_binds}
    kb_cur = {b["id"]: b["key"] for b in kb_binds}          # what the config says now
    kb_new = dict(kb_cur)                                    # what the list shows (edited, not yet applied)
    saved_apps = settings.get("apps") or {}
    defaults_now = read_defaults()
    app_new = {slot: saved_apps.get(slot, defaults_now.get(slot, info["default"])) for slot, info in APP_SLOTS.items()}
    kb_slot = {b["id"]: app_slot_for(b["cmd"]) for b in kb_binds}

    def kb_label(bid):
        desc = next((b["desc"] for b in kb_binds if b["id"] == bid), bid)
        slot = kb_slot.get(bid)
        return "%s (%s)" % (desc, app_name(app_new[slot])) if slot else desc

    kb_store = Gtk.ListStore(str, str, str, str)             # label, keys, id, weight marker
    for b in kb_binds:
        kb_store.append([kb_label(b["id"]), pretty_key(b["key"]), b["id"], ""])
    kb_filter = kb_store.filter_new()

    def kb_visible(model, it, _data=None):
        q = kb_search.get_text().strip().lower()
        return not q or q in model[it][0].lower() or q in model[it][1].lower()
    kb_filter.set_visible_func(kb_visible)
    kb_view = Gtk.TreeView(model=kb_filter)
    kb_view.set_headers_visible(True)
    for title, col, expand in (("Action", 0, True), ("Keys", 1, False)):
        cell = Gtk.CellRendererText()
        cell.set_property("ellipsize", 3)
        tc = Gtk.TreeViewColumn(title, cell, text=col)
        tc.set_expand(expand)
        tc.set_resizable(True)
        if col == 1:
            tc.set_min_width(300)
        def cell_data(_c, rend, model, it, _data=None, col=col):
            if it is None:
                return
            row = model[it]
            rend.set_property("weight", 700 if row[3] else 400)
            rend.set_property("text", row[col] + (" *" if col == 1 and row[3] else ""))
        tc.set_cell_data_func(cell, cell_data)
        kb_view.append_column(tc)
    kb_scroll = Gtk.ScrolledWindow()
    kb_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    kb_scroll.set_min_content_height(380)
    kb_scroll.add(kb_view)
    kp.pack_start(kb_scroll, True, True, 0)
    kb_btns = Gtk.Box(spacing=10)
    kb_change = Gtk.Button(label="Change key...")
    kb_reset = Gtk.Button(label="Reset this one")
    kb_reset_all = Gtk.Button(label="Reset all to default")
    kb_app = Gtk.Button(label="Change application...")
    kb_app.set_sensitive(False)
    for b_ in (kb_change, kb_app, kb_reset, kb_reset_all):
        kb_btns.pack_start(b_, False, False, 0)
    kp.pack_start(kb_btns, False, False, 0)
    kp.pack_start(dim("Rows with an application in brackets, like the file manager, terminal and browser, also have "
                      "Change application... to pick which program that key opens."), False, False, 0)
    add_page("keybindings", scrolled(kp))

    def kb_selected_id():
        model, it = kb_view.get_selection().get_selected()
        return model[it][2] if it else None

    def kb_refresh_row(bid):
        for row_ in kb_store:
            if row_[2] == bid:
                row_[0] = kb_label(bid)
                row_[1] = pretty_key(kb_new[bid])
                row_[3] = "*" if norm_key(kb_new[bid]) != norm_key(kb_default[bid]) else ""
        kb_filter.refilter()

    def kb_desc(bid):
        return next((b["desc"] for b in kb_binds if b["id"] == bid), bid)

    modifier_keys = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
                     "Meta_L", "Meta_R", "Hyper_L", "Hyper_R", "ISO_Level3_Shift", "Caps_Lock", "Num_Lock",
                     "Mode_switch"}

    def capture_key(bid):
        """Dialog that records one key combination. Returns the i3 key string, or None."""
        have_mode = ('mode "%s"' % KEYCAPTURE_MODE) in open(I3_CONFIG).read()
        if have_mode and not DRY:
            # i3 normally swallows bound combos (even Super+Return); switch to a mode with no bindings meanwhile
            run(["i3-msg", 'mode "%s"' % KEYCAPTURE_MODE])
            subprocess.Popen(["sh", "-c", "sleep 90; i3-msg -t get_binding_state | grep -q %s && i3-msg mode default"
                              % KEYCAPTURE_MODE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dlg = Gtk.Dialog(title="Change key", transient_for=win, modal=True)
        dlg.set_default_size(460, 190)
        area = dlg.get_content_area()
        area.set_spacing(14)
        for side in ("top", "bottom", "start", "end"):
            getattr(area, "set_margin_" + side)(18)
        area.pack_start(Gtk.Label(label=kb_desc(bid), xalign=0), False, False, 0)
        shown = Gtk.Label(label="Press the new key combination...")
        shown.get_style_context().add_class("title")
        area.pack_start(shown, True, True, 0)
        hint = dim("Hold the modifiers (Super, Alt, Ctrl, Shift), then press a key.")
        area.pack_start(hint, False, False, 0)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        ok_btn = dlg.add_button("Set", Gtk.ResponseType.OK)
        ok_btn.set_sensitive(False)
        got = {"key": None}

        def on_key(_w, ev):
            name = Gdk.keyval_name(ev.keyval) or ""
            if name in modifier_keys:
                return True
            keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
            found, base, _grp, _lvl, _cons = keymap.translate_keyboard_state(
                ev.hardware_keycode, Gdk.ModifierType(0), ev.group)
            key = Gdk.keyval_name(Gdk.keyval_to_lower(base if found else ev.keyval)) or name
            st = ev.state
            mods = []
            if st & (Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.MOD4_MASK):
                mods.append("$mod")
            if st & Gdk.ModifierType.MOD1_MASK:
                mods.append("$alt")
            if st & Gdk.ModifierType.CONTROL_MASK:
                mods.append("Ctrl")
            if st & Gdk.ModifierType.SHIFT_MASK:
                mods.append("Shift")
            special = key.startswith(("XF86", "F")) and (key.startswith("XF86") or key[1:].isdigit()) or key in ("Print", "Pause")
            if not mods and not special:
                shown.set_text("Add a modifier (Super, Alt or Ctrl)")
                ok_btn.set_sensitive(False)
                got["key"] = None
                return True
            got["key"] = "+".join(mods + [key])
            shown.set_text(pretty_key(got["key"]))
            ok_btn.set_sensitive(True)
            return True
        dlg.connect("key-press-event", on_key)
        dlg.show_all()
        try:
            resp = dlg.run()
        finally:
            dlg.destroy()
            if have_mode and not DRY:
                run(["i3-msg", "mode default"])
        return got["key"] if resp == Gtk.ResponseType.OK else None

    def kb_change_key(*_):
        bid = kb_selected_id()
        if not bid:
            status.set_text("Pick an action first.")
            return
        new = capture_key(bid)
        if not new:
            return
        clash = next((o for o in kb_new if o != bid and norm_key(kb_new[o]) == norm_key(new)), None)
        if clash:
            d = Gtk.MessageDialog(transient_for=win, modal=True, message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.NONE, text="%s is already used" % pretty_key(new))
            d.format_secondary_text('It belongs to "%s". Swap the two keys?' % kb_desc(clash))
            d.add_button("Cancel", Gtk.ResponseType.CANCEL)
            d.add_button("Swap", Gtk.ResponseType.YES)
            resp = d.run()
            d.destroy()
            if resp != Gtk.ResponseType.YES:
                return
            kb_new[clash] = kb_new[bid]
            kb_refresh_row(clash)
        kb_new[bid] = new
        kb_refresh_row(bid)
        status.set_text("Press Apply to save the new keybindings.")

    def kb_reset_one(*_):
        bid = kb_selected_id()
        if not bid:
            return
        want = kb_default[bid]
        clash = next((o for o in kb_new if o != bid and norm_key(kb_new[o]) == norm_key(want)), None)
        if clash:
            kb_new[clash] = kb_new[bid]
            kb_refresh_row(clash)
        kb_new[bid] = want
        kb_refresh_row(bid)

    def kb_reset_everything(*_):
        for bid in kb_new:
            kb_new[bid] = kb_default[bid]
            kb_refresh_row(bid)

    def kb_update_buttons(*_):
        bid = kb_selected_id()
        kb_app.set_sensitive(bool(bid and kb_slot.get(bid)))

    def kb_change_app(*_):
        bid = kb_selected_id()
        slot = kb_slot.get(bid) if bid else None
        if not slot:
            return
        info = APP_SLOTS[slot]
        dlg = Gtk.Dialog(title="Change %s" % info["label"], transient_for=win, modal=True)
        area = dlg.get_content_area()
        area.set_spacing(12)
        for side in ("top", "bottom", "start", "end"):
            getattr(area, "set_margin_" + side)(18)
        area.pack_start(Gtk.Label(label="Which program should %s open?" % pretty_key(kb_new[bid]), xalign=0), False, False, 0)
        combo = Gtk.ComboBoxText()
        for cmd, label in installed_choices(slot, app_new[slot]):
            combo.append(cmd or "__default__", "%s%s" % (label, "  (%s)" % cmd if cmd else ""))
        combo.append("__other__", "Other... (type a command)")
        cur = app_new[slot]
        combo.set_active_id(cur or "__default__")
        area.pack_start(combo, False, False, 0)
        entry = Gtk.Entry()
        entry.set_placeholder_text("command, e.g. mybrowser --private-window")
        entry.set_no_show_all(True)
        area.pack_start(entry, False, False, 0)
        note = dim("Only programs found on this computer are listed. Other opens any command you type."
                   + (" Yazi and the other terminal file managers open in your terminal." if slot == "files" else ""))
        area.pack_start(note, False, False, 0)
        err = dim("")
        area.pack_start(err, False, False, 0)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dlg.add_button("Set", Gtk.ResponseType.OK)

        def on_combo(*_a):
            entry.set_visible(combo.get_active_id() == "__other__")
        combo.connect("changed", on_combo)
        dlg.show_all()
        on_combo()
        chosen = None
        while True:
            if dlg.run() != Gtk.ResponseType.OK:
                break
            pick = combo.get_active_id()
            val = entry.get_text().strip() if pick == "__other__" else ("" if pick == "__default__" else pick)
            if pick == "__other__" and (not val or not SAFE_CMD.match(val)):
                err.set_text("Use only letters, numbers, spaces and . _ / + - in the command.")
                continue
            chosen = val
            break
        dlg.destroy()
        if chosen is None:
            return
        app_new[slot] = chosen
        for b_id, sl in kb_slot.items():
            if sl == slot:
                kb_refresh_row(b_id)
        status.set_text("Press Apply to save: %s -> %s" % (info["label"], app_name(chosen)))

    kb_view.get_selection().connect("changed", kb_update_buttons)
    kb_app.connect("clicked", kb_change_app)
    kb_change.connect("clicked", kb_change_key)
    kb_reset.connect("clicked", kb_reset_one)
    kb_reset_all.connect("clicked", kb_reset_everything)
    kb_view.connect("row-activated", kb_change_key)
    kb_search.connect("search-changed", lambda *_: kb_filter.refilter())

    def kb_commit():
        """Turn the edited list into saved overrides and write them to the i3 config."""
        over = {}
        for bid, key in kb_new.items():
            if norm_key(key) != norm_key(kb_default[bid]):
                over[bid] = {"key": key, "default": kb_default[bid]}
        settings["keybinds"] = over
        # a key that went back to its default must also be written back
        for bid, key in kb_new.items():
            if bid not in over and norm_key(kb_cur[bid]) != norm_key(key):
                over[bid] = {"key": key, "default": kb_default[bid]}
        changed = apply_keybinds(settings, reload=True)
        settings["keybinds"] = {b: o for b, o in over.items() if norm_key(o["key"]) != norm_key(kb_default[b])}
        for bid in kb_new:
            kb_cur[bid] = kb_new[bid]
        return changed

    def identify(*_):
        """Flash each screen's number on that screen for a moment."""
        for o in parse_xrandr(query(["xrandr", "--query"])):
            if not o.enabled:
                continue
            w = Gtk.Window(type=Gtk.WindowType.POPUP)
            w.set_default_size(150, 150)
            w.move(o.x + 40, o.y + 60)
            lb = Gtk.Label(label=str(number.get(o.name, "?")))
            lb.get_style_context().add_class("ident")
            w.add(lb)
            w.show_all()
            GLib.timeout_add_seconds(3, lambda w=w: (w.destroy(), False)[1])
    ident_btn.connect("clicked", identify)

    # ---------------- sound tab
    import threading
    import time as _time
    sp = page()
    snd_msg = dim("")

    def volume_row(title):
        """[label] [0-150% slider with a 100% mark] [Mute switch]"""
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, VOLUME_MAX, 1)
        sc.set_digits(0)
        sc.set_value_pos(Gtk.PositionType.RIGHT)
        sc.add_mark(100, Gtk.PositionType.BOTTOM, "100%")
        sc.connect("format-value", lambda _s, v: "%d%%" % v)
        guard_scroll(sc)
        mute = Gtk.Switch()
        mute.set_valign(Gtk.Align.CENTER)
        box = Gtk.Box(spacing=12)
        box.pack_start(sc, True, True, 0)
        box.pack_start(Gtk.Label(label="Mute"), False, False, 0)
        box.pack_start(mute, False, False, 0)
        return row(title, box), sc, mute

    out_title = Gtk.Label(label="Output", xalign=0)
    out_title.get_style_context().add_class("title")
    sp.pack_start(out_title, False, False, 0)
    out_combo = Gtk.ComboBoxText()
    sp.pack_start(row("Play sound on", out_combo), False, False, 0)
    out_row, out_vol, out_mute = volume_row("Volume")
    sp.pack_start(out_row, False, False, 0)
    out_btns = Gtk.Box(spacing=10)
    snd_test = Gtk.Button(label="Play test sound")
    out_btns.pack_start(snd_test, False, False, 0)
    sp.pack_start(row("", out_btns), False, False, 0)

    in_title = Gtk.Label(label="Microphone", xalign=0)
    in_title.get_style_context().add_class("title")
    sp.pack_start(in_title, False, False, 0)
    in_combo = Gtk.ComboBoxText()
    sp.pack_start(row("Record from", in_combo), False, False, 0)
    in_row, in_vol, in_mute = volume_row("Input level")
    sp.pack_start(in_row, False, False, 0)

    apps_title = Gtk.Label(label="Apps playing sound", xalign=0)
    apps_title.get_style_context().add_class("title")
    sp.pack_start(apps_title, False, False, 0)
    apps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    sp.pack_start(apps_box, False, False, 0)

    fx_title = Gtk.Label(label="Sound effects", xalign=0)
    fx_title.get_style_context().add_class("title")
    sp.pack_start(fx_title, False, False, 0)
    snd_saved = dict(SOUND_DEFAULT, **(settings.get("sound") or {}))
    fx_vol = Gtk.Switch()
    fx_vol.set_halign(Gtk.Align.START)
    fx_vol.set_active(snd_saved["volume_feedback"])
    sp.pack_start(row("Volume change sound", fx_vol), False, False, 0)
    fx_shot = Gtk.Switch()
    fx_shot.set_halign(Gtk.Align.START)
    fx_shot.set_active(snd_saved["screenshot_sound"])
    sp.pack_start(row("Screenshot sound", fx_shot), False, False, 0)

    snd_btns = Gtk.Box(spacing=10)
    snd_refresh = Gtk.Button(label="Refresh")
    snd_mixer = Gtk.Button(label="Open full mixer")
    mixer_exe = shutil.which("pavucontrol") or shutil.which("pwvucontrol")
    snd_mixer.set_sensitive(bool(mixer_exe))
    snd_btns.pack_start(snd_refresh, False, False, 0)
    snd_btns.pack_start(snd_mixer, False, False, 0)
    sp.pack_start(snd_btns, False, False, 0)
    sp.pack_start(snd_msg, False, False, 0)
    sp.pack_start(dim("Devices and volumes change right away (the volume keys use the same output). "
                      "The sound-effect switches are saved when you press Apply."), False, False, 0)
    sp_scroll = Gtk.ScrolledWindow()
    sp_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sp_scroll.add(sp)
    add_page("sound", sp_scroll)

    snd = {"loading": False, "pending": {}, "timer": None, "last_user": 0.0, "busy": False, "streams": None,
           "sinks": {}, "sources": {}}
    snd_live = (out_combo, out_vol, out_mute, snd_test, in_combo, in_vol, in_mute)

    def snd_worker(jobs):
        """Run pactl changes off the UI thread; report the first failure."""
        def go():
            err = None
            for fn in jobs:
                try:
                    ok, out = fn()
                except Exception as e:  # noqa: BLE001
                    ok, out = False, str(e)
                if not ok and err is None:
                    err = (out or "").strip()[-140:] or "failed"
            if err:
                GLib.idle_add(lambda: (snd_msg.set_text("Could not change the sound setting: " + err), False)[1])
        threading.Thread(target=go, daemon=True).start()

    def snd_flush():
        snd["timer"] = None
        jobs = list(snd["pending"].values())
        snd["pending"].clear()
        if jobs:
            snd_worker(jobs)
        return False

    def snd_send(key, fn):
        """Collect fast slider moves and send only the latest value (every 90 ms at most)."""
        if snd["loading"]:
            return
        snd["pending"][key] = fn
        snd["last_user"] = _time.monotonic()
        if snd["timer"] is None:
            snd["timer"] = GLib.timeout_add(90, snd_flush)

    def build_apps(streams):
        for child in apps_box.get_children():
            apps_box.remove(child)
        if not streams:
            apps_box.pack_start(dim("No app is playing sound right now."), False, False, 0)
        # (the apps' rows in one rounded card, like the rest of the window)
        ctx_ = apps_box.get_style_context()
        (ctx_.add_class if streams else ctx_.remove_class)("card")
        for i_, st in enumerate(streams):
            r_, sc_, mu_ = volume_row(st["app"])
            sc_.set_value(st["volume"])
            mu_.set_active(st["mute"])
            sid = st["id"]
            sc_.connect("value-changed", lambda w, sid=sid: snd_send(("app-vol", sid), lambda v=int(w.get_value()): pa_set_volume("sink-input", sid, v)))
            mu_.connect("notify::active", lambda w, _p, sid=sid: snd_send(("app-mute", sid), lambda m=w.get_active(): pa_set_mute("sink-input", sid, m)))
            r_.stream_widgets = (sc_, mu_)
            r_.get_style_context().add_class("setrow")
            if i_:
                r_.get_style_context().add_class("sep")
            apps_box.pack_start(r_, False, False, 0)
        apps_box.show_all()

    def snd_fill(res, note=None):
        snd["busy"] = False
        if _time.monotonic() - snd["last_user"] < 1.5 or snd["pending"]:
            return False                              # the user is moving a slider right now: do not jump it back
        snd["loading"] = True
        try:
            ok = bool(res.get("available"))
            for w in snd_live:
                w.set_sensitive(ok)
            if not ok:
                snd_msg.set_text(res.get("error") or PA_HINT)
                out_combo.remove_all()
                in_combo.remove_all()
                build_apps([])
                return False
            snd["sinks"] = {d["name"]: d for d in res["sinks"]}
            snd["sources"] = {d["name"]: d for d in res["sources"]}
            for combo, devs, cur in ((out_combo, res["sinks"], res["default_sink"]),
                                     (in_combo, res["sources"], res["default_source"])):
                if [r[0] for r in combo.get_model()] != [d["label"] for d in devs] or combo.get_active_id() != cur:
                    combo.remove_all()
                    for d in devs:
                        combo.append(d["name"], d["label"])
                    if not combo.set_active_id(cur) and devs:
                        combo.set_active(0)
            sink = snd["sinks"].get(out_combo.get_active_id() or "")
            src = snd["sources"].get(in_combo.get_active_id() or "")
            for dev, vol_w, mute_w in ((sink, out_vol, out_mute), (src, in_vol, in_mute)):
                vol_w.set_sensitive(bool(dev))
                mute_w.set_sensitive(bool(dev))
                if dev:
                    vol_w.set_value(dev["volume"])
                    mute_w.set_active(dev["mute"])
            ids = [x["id"] for x in res["streams"]]
            rows = [c for c in apps_box.get_children() if hasattr(c, "stream_widgets")]
            if snd["streams"] != ids:
                snd["streams"] = ids
                build_apps(res["streams"])
            else:
                for r_, st in zip(rows, res["streams"]):
                    r_.stream_widgets[0].set_value(st["volume"])
                    r_.stream_widgets[1].set_active(st["mute"])
            snd_msg.set_text(note or ("" if res["sinks"] else "No output device was found."))
        finally:
            snd["loading"] = False
        return False

    def snd_reload(note=None):
        if snd["busy"]:
            return
        snd["busy"] = True

        def go():
            try:
                res = pa_snapshot()
            except Exception as e:  # noqa: BLE001
                res = {"available": False, "error": str(e)}
            GLib.idle_add(snd_fill, res, note)
        threading.Thread(target=go, daemon=True).start()

    def on_device(combo, kind):
        if snd["loading"]:
            return
        name = combo.get_active_id()
        if not name:
            return

        def go():
            ok, out = pa_set_default(kind, name)
            GLib.idle_add(lambda: (snd_reload(None if ok else "Could not switch: " + out), False)[1])
        snd["last_user"] = 0.0
        threading.Thread(target=go, daemon=True).start()
    out_combo.connect("changed", on_device, "sink")
    in_combo.connect("changed", on_device, "source")
    out_vol.connect("value-changed", lambda w: snd_send(("vol", "sink"), lambda n=out_combo.get_active_id(), v=int(w.get_value()): pa_set_volume("sink", n, v)))
    in_vol.connect("value-changed", lambda w: snd_send(("vol", "source"), lambda n=in_combo.get_active_id(), v=int(w.get_value()): pa_set_volume("source", n, v)))
    out_mute.connect("notify::active", lambda w, _p: snd_send(("mute", "sink"), lambda n=out_combo.get_active_id(), m=w.get_active(): pa_set_mute("sink", n, m)))
    in_mute.connect("notify::active", lambda w, _p: snd_send(("mute", "source"), lambda n=in_combo.get_active_id(), m=w.get_active(): pa_set_mute("source", n, m)))

    def on_test(*_):
        ok, out = pa_test_sound(out_combo.get_active_id())
        snd_msg.set_text("" if ok else "Could not play a test sound: " + out)
    snd_test.connect("clicked", on_test)
    snd_refresh.connect("clicked", lambda *_: (snd.update(last_user=0.0), snd_reload()))
    snd_mixer.connect("clicked", lambda *_: mixer_exe and subprocess.Popen(
        [mixer_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True))

    def snd_tick():
        if nb.get_current_page() == nb.page_num(sp_scroll) and _time.monotonic() - snd["last_user"] > 2:
            snd_reload()                              # apps start and stop playing: keep the list current
        return True
    GLib.timeout_add_seconds(3, snd_tick)

    def on_snd_page(_nb, _page, num):
        if num == nb.page_num(sp_scroll):
            snd["last_user"] = 0.0
            snd_reload()
        return False
    nb.connect("switch-page", on_snd_page)

    # ---------------- bluetooth tab
    bp = page()
    bt_title = Gtk.Label(label="Bluetooth", xalign=0)
    bt_title.get_style_context().add_class("title")
    bp.pack_start(bt_title, False, False, 0)
    bt_msg = dim("")
    bt_power_sw = Gtk.Switch()
    bt_power_sw.set_halign(Gtk.Align.START)
    bp.pack_start(row("Bluetooth", bt_power_sw), False, False, 0)

    def bt_list(cols):
        store = Gtk.ListStore(*([str] * len(cols) + [str]))        # last column = MAC address (hidden)
        view = Gtk.TreeView(model=store)
        for i, c in enumerate(cols):
            r_ = Gtk.CellRendererText()
            r_.set_property("ellipsize", 3 if i == 0 else 0)
            col_ = Gtk.TreeViewColumn(c, r_, text=i)
            col_.set_expand(i == 0)
            if i > 0:
                col_.set_min_width(170)
            col_.set_resizable(True)
            view.append_column(col_)
        sc_ = Gtk.ScrolledWindow()
        sc_.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc_.set_min_content_height(150)
        sc_.add(view)
        card_ = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)          # (the list in a rounded card)
        card_.get_style_context().add_class("listcard")
        card_.pack_start(sc_, True, True, 0)
        return store, view, card_

    my_title = Gtk.Label(label="My devices", xalign=0)
    my_title.get_style_context().add_class("title")
    bp.pack_start(my_title, False, False, 0)
    my_store, my_view, my_scroll = bt_list(["Device", "Status"])
    bp.pack_start(my_scroll, True, True, 0)
    my_btns = Gtk.Box(spacing=10)
    bt_connect = Gtk.Button(label="Connect")
    bt_disconnect = Gtk.Button(label="Disconnect")
    bt_forget = Gtk.Button(label="Forget device")
    bt_refresh = Gtk.Button(label="Refresh")
    for b_ in (bt_connect, bt_disconnect, bt_forget, bt_refresh):
        my_btns.pack_start(b_, False, False, 0)
    bp.pack_start(my_btns, False, False, 0)

    add_title = Gtk.Label(label="Add a device", xalign=0)
    add_title.get_style_context().add_class("title")
    bp.pack_start(add_title, False, False, 0)
    bp.pack_start(dim("Put the device in pairing mode, then press Search. Pick it from the list and press Pair and connect."),
                  False, False, 0)
    near_store, near_view, near_scroll = bt_list(["Nearby device", "Address"])
    bp.pack_start(near_scroll, True, True, 0)
    add_btns = Gtk.Box(spacing=10)
    bt_search = Gtk.Button(label="Search for devices")
    bt_pair_btn = Gtk.Button(label="Pair and connect")
    bt_manager = Gtk.Button(label="Open full Bluetooth manager")
    for b_ in (bt_search, bt_pair_btn, bt_manager):
        add_btns.pack_start(b_, False, False, 0)
    bp.pack_start(add_btns, False, False, 0)
    bp.pack_start(bt_msg, False, False, 0)
    bt_manager.set_sensitive(bool(shutil.which("blueman-manager")))
    bp_page = scrolled(bp)
    add_page("bluetooth", bp_page)

    bt_busy = {"n": 0, "power_ui": False}
    bt_all = (bt_power_sw, bt_connect, bt_disconnect, bt_forget, bt_refresh, bt_search, bt_pair_btn)

    def bt_set_busy(on, text=None):
        bt_busy["n"] += 1 if on else -1
        for w in bt_all:
            w.set_sensitive(bt_busy["n"] <= 0)
        if text is not None:
            bt_msg.set_text(text)

    def bt_background(work, done, text):
        """Run work() off the UI thread, then done(result) on it."""
        bt_set_busy(True, text)

        def go():
            try:
                res = work()
            except Exception as e:                      # never let a worker thread die silently
                res = (False, str(e))
            GLib.idle_add(finish, res)

        def finish(res):
            bt_set_busy(False)
            done(res)
            return False
        threading.Thread(target=go, daemon=True).start()

    def bt_fill(state, devs):
        bt_busy["power_ui"] = True
        bt_power_sw.set_active(bool(state.get("powered")))
        bt_busy["power_ui"] = False
        bt_msg.set_text("")
        my_store.clear()
        near_store.clear()
        for d in devs:
            if d["paired"]:
                my_store.append([d["name"], "Connected" if d["connected"] else "Not connected", d["mac"]])
            else:
                near_store.append([d["name"], d["mac"], d["mac"]])
        if not state.get("available"):
            bt_msg.set_text(BT_HINT if not state.get("installed") or not shutil.which("bluetoothctl") else
                            "No Bluetooth adapter found.")
        elif not state.get("powered"):
            bt_msg.set_text("Bluetooth is off. Turn it on with the switch above.")

    def bt_reload(note=None):
        def work():
            st = bt_state()
            return (st, bt_devices() if st.get("available") else [])
        bt_background(work, lambda res: (bt_fill(*res), bt_msg.set_text(note) if note else None), "Reading Bluetooth devices...")

    def selected(view):
        model, it = view.get_selection().get_selected()
        return (model[it][0], model[it][2]) if it else (None, None)

    def on_power(sw, _p):
        if bt_busy["power_ui"] or bt_busy["n"] > 0:
            return
        want = sw.get_active()
        bt_background(lambda: bt_power(want), lambda res: bt_reload(None if res[0] else "Could not change Bluetooth power: " + res[1].strip()[-120:]),
                      "Turning Bluetooth %s..." % ("on" if want else "off"))
    bt_power_sw.connect("notify::active", on_power)

    def do_device(action, verb):
        name, mac = selected(my_view)
        if not mac:
            bt_msg.set_text("Pick a device in My devices first.")
            return
        bt_background(lambda: bt_action(action, mac),
                      lambda res: bt_reload("%s %s." % (name, verb) if res[0] else "Could not %s %s: %s" % (action, name, res[1])),
                      "%s..." % verb.capitalize())
    bt_connect.connect("clicked", lambda *_: do_device("connect", "connected"))
    bt_disconnect.connect("clicked", lambda *_: do_device("disconnect", "disconnected"))

    def forget(*_):
        name, mac = selected(my_view)
        if not mac:
            bt_msg.set_text("Pick a device in My devices first.")
            return
        d = Gtk.MessageDialog(transient_for=win, modal=True, message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.NONE, text="Forget %s?" % name)
        d.format_secondary_text("It will be unpaired. You can pair it again later.")
        d.add_button("Cancel", Gtk.ResponseType.NO)
        d.add_button("Forget", Gtk.ResponseType.YES)
        ans = d.run()
        d.destroy()
        if ans == Gtk.ResponseType.YES:
            bt_background(lambda: bt_action("remove", mac),
                          lambda res: bt_reload("Forgot %s." % name if res[0] else "Could not forget %s: %s" % (name, res[1])),
                          "Removing...")
    bt_forget.connect("clicked", forget)
    bt_refresh.connect("clicked", lambda *_: bt_reload())

    def search(*_):
        def work():
            if not bt_state().get("powered"):
                return (False, "Turn Bluetooth on first.")
            bt_scan(8)
            return (True, "")
        bt_background(work, lambda res: bt_reload("Search finished. Pick your device below." if res[0] else res[1]),
                      "Searching for devices (8 seconds)...")
    bt_search.connect("clicked", search)

    def pair(*_):
        name, mac = selected(near_view)
        if not mac:
            bt_msg.set_text("Press Search, then pick a device in the nearby list.")
            return
        bt_background(lambda: bt_pair(mac),
                      lambda res: bt_reload("Paired and connected to %s." % name if res[0] else "Could not pair %s: %s" % (name, res[1])),
                      "Pairing with %s (can take up to 30 seconds)..." % name)
    bt_pair_btn.connect("clicked", pair)

    def open_manager(*_):
        exe = shutil.which("blueman-manager")
        if exe:
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bt_manager.connect("clicked", open_manager)

    bt_loaded = {"done": False}

    def on_page(_nb, _page, num):
        if num == nb.page_num(bp_page) and not bt_loaded["done"]:
            bt_loaded["done"] = True
            bt_reload()
        return False
    nb.connect("switch-page", on_page)

    # ---------------- network tab: Wi-Fi, Ethernet, VPN and proxy, chosen with the segmented switcher at the top
    netp = page()
    nt_ = Gtk.Label(label="Network", xalign=0)
    nt_.get_style_context().add_class("title")
    netp.pack_start(nt_, False, False, 0)
    net_stack = Gtk.Stack()
    net_stack.set_vhomogeneous(False)                   # (each part as tall as it is: the page scrolls)
    net_stack.set_hhomogeneous(False)
    net_seg = Gtk.StackSwitcher()
    net_seg.set_stack(net_stack)
    net_seg.get_style_context().add_class("segmented")
    net_seg.set_halign(Gtk.Align.START)
    netp.pack_start(net_seg, False, False, 0)
    netp.pack_start(net_stack, True, True, 0)

    def net_part():
        b_ = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        part_boxes.append(b_)
        return b_

    def heading(text):
        lb = Gtk.Label(label=text, xalign=0)
        lb.get_style_context().add_class("title")
        return lb

    wp = net_part()
    net_stack.add_titled(wp, "wifi", "Wi-Fi")
    wf_power = Gtk.Switch()
    wf_power.set_halign(Gtk.Align.START)
    wp.pack_start(row("Wi-Fi", wf_power), False, False, 0)
    wf_now = dim("")
    wp.pack_start(wf_now, False, False, 0)
    wn_title = Gtk.Label(label="Networks", xalign=0)
    wn_title.get_style_context().add_class("title")
    wp.pack_start(wn_title, False, False, 0)
    wf_store, wf_view, wf_scroll = bt_list(["Network", "Signal", "Security", "Status"])
    wf_view.get_column(1).set_min_width(80)
    wf_view.get_column(2).set_min_width(110)
    wf_view.get_column(3).set_min_width(130)
    wp.pack_start(wf_scroll, True, True, 0)
    wf_btns = Gtk.Box(spacing=10)
    wf_connect = Gtk.Button(label="Connect")
    wf_disconnect = Gtk.Button(label="Disconnect")
    wf_forget = Gtk.Button(label="Forget network")
    wf_rescan = Gtk.Button(label="Scan again")
    for b_ in (wf_connect, wf_disconnect, wf_forget, wf_rescan):
        wf_btns.pack_start(b_, False, False, 0)
    wp.pack_start(wf_btns, False, False, 0)
    wf_btns2 = Gtk.Box(spacing=10)
    wf_hidden = Gtk.Button(label="Join a hidden network...")
    wf_editor = Gtk.Button(label="Open full network editor")
    wf_editor.set_sensitive(bool(shutil.which("nm-connection-editor")))
    wf_btns2.pack_start(wf_hidden, False, False, 0)
    wf_btns2.pack_start(wf_editor, False, False, 0)
    wp.pack_start(wf_btns2, False, False, 0)
    wf_msg = dim("")
    wp.pack_start(wf_msg, False, False, 0)
    wf_tray = Gtk.Switch()
    wf_tray.set_halign(Gtk.Align.START)
    wf_tray.set_active(wifi_tray_icon(settings))
    wp.pack_start(row("Wi-Fi icon in the tray", wf_tray), False, False, 0)
    wp.pack_start(dim("Off by default: the Wi-Fi item in the bar opens this tab. The network helper behind the icon "
                      "(nm-applet) keeps running either way, so a saved network that needs its password can still ask "
                      "for it. Changes when you press Apply."), False, False, 0)
    wp_page = scrolled(netp)
    add_page("network", wp_page)

    wf_busy = {"n": 0, "ui": False, "iface": "", "nets": {}}
    wf_all = (wf_power, wf_connect, wf_disconnect, wf_forget, wf_rescan, wf_hidden)

    def wf_background(work, done, text):
        wf_busy["n"] += 1
        for w in wf_all:
            w.set_sensitive(False)
        wf_msg.set_text(text)

        def go():
            try:
                res = work()
            except Exception as e:
                res = (False, str(e))
            GLib.idle_add(finish, res)

        def finish(res):
            wf_busy["n"] -= 1
            for w in wf_all:
                w.set_sensitive(wf_busy["n"] <= 0)
            done(res)
            return False
        threading.Thread(target=go, daemon=True).start()

    def wf_fill(state, nets):
        wf_busy["ui"] = True
        wf_power.set_active(bool(state.get("enabled")))
        wf_busy["ui"] = False
        wf_busy["iface"] = state.get("iface", "")
        wf_busy["nets"] = {n["ssid"]: n for n in nets}
        wf_msg.set_text("")
        wf_store.clear()
        cur = ""
        for n in nets:
            status = "Connected" if n["active"] else ("Saved" if n["saved"] else "")
            if n["active"]:
                cur = n["ssid"]
            wf_store.append([n["ssid"], "%d%%" % n["signal"], n["security"], status, n["ssid"]])
        wf_now.set_text(("Connected to %s." % cur) if cur else "Not connected.")
        if not state.get("installed"):
            wf_msg.set_text(NM_HINT)
        elif not state.get("available"):
            wf_msg.set_text("No Wi-Fi adapter found on this computer.")
            wf_now.set_text("")
        elif not state.get("enabled"):
            wf_msg.set_text("Wi-Fi is off. Turn it on with the switch above.")
            wf_now.set_text("")

    def wf_reload(note=None, rescan=False):
        def work():
            st = nm_state()
            return (st, nm_networks(rescan) if st.get("available") and st.get("enabled") else [])

        def done(res):
            wf_fill(*res)
            if note:
                wf_msg.set_text(note)
            if net_loaded["done"]:
                net_reload()                            # (the addresses change with the connection)
        wf_background(work, done, "Looking for networks..." if rescan else "Reading Wi-Fi status...")

    def wf_selected():
        model, it = wf_view.get_selection().get_selected()
        return model[it][4] if it else None

    def ask_text(title, with_name, ssid=""):
        """Small dialog for a Wi-Fi name and/or password. Returns (name, password) or None."""
        d = Gtk.Dialog(title=title, transient_for=win, modal=True)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        d.add_button("Connect", Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        d.set_default_response(Gtk.ResponseType.OK)
        box = d.get_content_area()
        box.set_spacing(10)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, "set_margin_" + side)(16)
        name = Gtk.Entry()
        name.set_activates_default(True)
        pw = Gtk.Entry()
        pw.set_visibility(False)
        pw.set_activates_default(True)
        if with_name:
            name.set_placeholder_text("Network name")
            box.pack_start(name, False, False, 0)
        else:
            box.pack_start(Gtk.Label(label="Password for %s" % ssid, xalign=0), False, False, 0)
        pw.set_placeholder_text("Password")
        box.pack_start(pw, False, False, 0)
        show = Gtk.CheckButton(label="Show password")
        show.connect("toggled", lambda b: pw.set_visibility(b.get_active()))
        box.pack_start(show, False, False, 0)
        d.show_all()
        ans = d.run()
        res = (name.get_text().strip(), pw.get_text()) if ans == Gtk.ResponseType.OK else None
        d.destroy()
        return res

    def on_wf_power(sw, _p):
        if wf_busy["ui"] or wf_busy["n"] > 0:
            return
        want = sw.get_active()
        wf_background(lambda: nm_power(want),
                      lambda res: wf_reload(None if res[0] else "Could not change Wi-Fi power: " + res[1].strip()[-120:]),
                      "Turning Wi-Fi %s..." % ("on" if want else "off"))
    wf_power.connect("notify::active", on_wf_power)

    def wf_join(ssid, password=None, hidden=False):
        n = wf_busy["nets"].get(ssid)
        saved = bool(n and n["saved"])
        wf_background(lambda: nm_connect(ssid, password, hidden, saved),
                      lambda res: wf_reload(("Connected to %s." % ssid) if res[0] else "Could not connect to %s: %s" % (ssid, res[1])),
                      "Connecting to %s..." % ssid)

    def on_wf_connect(*_):
        ssid = wf_selected()
        if not ssid:
            wf_msg.set_text("Pick a network first.")
            return
        n = wf_busy["nets"].get(ssid, {})
        if n.get("security", "").find("802.1X") >= 0 and not n.get("saved"):
            wf_msg.set_text("This network uses a username and password login (802.1X). Use the full network editor.")
            return
        if n.get("security") == "Open" or n.get("saved"):
            wf_join(ssid)
            return
        got = ask_text("Join %s" % ssid, False, ssid)
        if got:
            if not nm_valid_password(got[1]):
                wf_msg.set_text("The password must be 8 to 63 characters.")
                return
            wf_join(ssid, got[1])
    wf_connect.connect("clicked", on_wf_connect)

    def on_wf_disconnect(*_):
        iface = wf_busy["iface"]
        wf_background(lambda: nm_disconnect(iface),
                      lambda res: wf_reload("Disconnected." if res[0] else "Could not disconnect: " + res[1]),
                      "Disconnecting...")
    wf_disconnect.connect("clicked", on_wf_disconnect)

    def on_wf_forget(*_):
        ssid = wf_selected()
        n = wf_busy["nets"].get(ssid or "", {})
        if not ssid:
            wf_msg.set_text("Pick a network first.")
            return
        if not n.get("saved"):
            wf_msg.set_text("%s is not saved, so there is nothing to forget." % ssid)
            return
        d = Gtk.MessageDialog(transient_for=win, modal=True, message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.NONE, text="Forget %s?" % ssid)
        d.format_secondary_text("Its saved password is removed. You will need the password to join again.")
        d.add_button("Cancel", Gtk.ResponseType.NO)
        d.add_button("Forget", Gtk.ResponseType.YES)
        ans = d.run()
        d.destroy()
        if ans == Gtk.ResponseType.YES:
            wf_background(lambda: nm_forget(ssid),
                          lambda res: wf_reload("Forgot %s." % ssid if res[0] else "Could not forget %s: %s" % (ssid, res[1])),
                          "Removing...")
    wf_forget.connect("clicked", on_wf_forget)
    wf_rescan.connect("clicked", lambda *_: wf_reload(rescan=True))

    def on_wf_hidden(*_):
        got = ask_text("Join a hidden network", True)
        if not got:
            return
        name, pw = got
        if not nm_valid_ssid(name):
            wf_msg.set_text("Enter the network name (up to 32 characters).")
            return
        if pw and not nm_valid_password(pw):
            wf_msg.set_text("The password must be 8 to 63 characters.")
            return
        wf_join(name, pw or None, hidden=True)
    wf_hidden.connect("clicked", on_wf_hidden)

    def on_wf_editor(*_):
        exe = shutil.which("nm-connection-editor")
        if exe:
            subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wf_editor.connect("clicked", on_wf_editor)

    wf_loaded = {"done": False}

    def on_wf_page(_nb, _page, num):
        if num == nb.page_num(wp_page) and not wf_loaded["done"]:
            wf_loaded["done"] = True
            wf_reload()
        return False
    nb.connect("switch-page", on_wf_page)

    # -- the adapters' details (addresses, router, DNS) and their IP settings: Wi-Fi part and Ethernet part
    nm_ok = bool(shutil.which("nmcli"))
    wd_title = heading("Wi-Fi details")
    wd_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    tray_row = wf_tray.get_parent()
    for w_ in (wd_title, wd_box):
        wp.pack_start(w_, False, False, 0)
        wp.reorder_child(w_, wp.get_children().index(tray_row))
    if not nm_ok:
        # no NetworkManager: only what works here - the hint (wf_msg) and the
        # adapter's details; the switch, the list and its buttons, and the tray icon switch are NetworkManager's
        kids_ = wp.get_children()
        at_ = kids_.index(tray_row)
        tray_hint = kids_[at_ + 1] if at_ + 1 < len(kids_) else None
        for w_ in (wf_power.get_parent(), wf_now, wn_title, wf_scroll, wf_btns, wf_btns2, tray_row, tray_hint):
            if w_ is not None and w_.get_parent() is wp:
                wp.remove(w_)

    ep = net_part()
    net_stack.add_titled(ep, "ethernet", "Ethernet")
    ep.pack_start(heading("Wired connections"), False, False, 0)
    ep_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    ep.pack_start(ep_box, False, False, 0)
    ep_btns = Gtk.Box(spacing=10)
    ep_refresh = Gtk.Button(label="Refresh")
    ep_editor = Gtk.Button(label="Open full network editor")
    ep_editor.set_sensitive(bool(shutil.which("nm-connection-editor")))
    ep_btns.pack_start(ep_refresh, False, False, 0)
    ep_btns.pack_start(ep_editor, False, False, 0)
    ep.pack_start(ep_btns, False, False, 0)
    ep_msg = dim("")
    ep.pack_start(ep_msg, False, False, 0)
    if nm_ok:
        ep.pack_start(dim("A cable that is plugged in connects by itself. 'IP settings' sets a fixed address or your "
                          "own DNS servers for a connection (Wi-Fi networks have the same button on the Wi-Fi "
                          "part); changing them reconnects it."), False, False, 0)
    else:
        ep.pack_start(dim({"openbsd": "OpenBSD sets the addresses in /etc/hostname.<adapter> (for example "
                                      "'inet autoconf' or a fixed 'inet 192.168.1.50 255.255.255.0'); see "
                                      "hostname.if(5). Shown here as they are now.",
                           "netbsd": "NetBSD sets the addresses in /etc/ifconfig.<adapter> or with dhcpcd in "
                                     "/etc/rc.conf. Shown here as they are now."}.get(
            SYSTEM, "FreeBSD and GhostBSD set the addresses in /etc/rc.conf (for example ifconfig_em0=\"DHCP\" or a "
                    "fixed \"inet 192.168.1.50/24\"), or with NetworkMgr in the tray. Shown here as they are now.")),
            False, False, 0)

    def value_label(text):
        lb = Gtk.Label(label=text, xalign=0)
        lb.set_selectable(True)                         # (addresses can be copied)
        lb.set_line_wrap(True)
        lb.get_style_context().add_class("value")
        return lb

    def info_card(dev, buttons):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.get_style_context().add_class("card")
        rows = [("Adapter", "%s (%s)" % (dev["iface"], "Wi-Fi" if dev["type"] == "wifi" else "Ethernet")),
                ("Status", dev["status"] + (" - %s" % dev["connection"] if dev["connection"] else "")),
                ("IP address", ", ".join(dev["ip4"]) or "-"), ("Router", dev["gw4"] or "-"),
                ("DNS servers", ", ".join(dev["dns"]) or "-")]
        if dev["ip6"]:
            rows.append(("IPv6 address", ", ".join(dev["ip6"])))
        rows.append(("Hardware address", dev["mac"] or "-"))
        for i, (k, v) in enumerate(rows):
            r = Gtk.Box(spacing=12)
            r.get_style_context().add_class("setrow")
            if i:
                r.get_style_context().add_class("sep")
            lb = Gtk.Label(label=k, xalign=0)
            lb.set_size_request(230, -1)
            r.pack_start(lb, False, False, 0)
            r.pack_start(value_label(v), True, True, 0)
            card.pack_start(r, False, False, 0)
        if buttons:
            r = Gtk.Box(spacing=10)
            r.get_style_context().add_class("setrow")
            r.get_style_context().add_class("sep")
            for b_ in buttons:
                r.pack_start(b_, False, False, 0)
            card.pack_start(r, False, False, 0)
        return card

    net_busy = {"n": 0}

    def net_background(work, done, msg_label, text):
        net_busy["n"] += 1
        msg_label.set_text(text)

        def go():
            try:
                res = work()
            except Exception as e:  # noqa: BLE001
                res = (False, str(e))
            GLib.idle_add(finish, res)

        def finish(res):
            net_busy["n"] -= 1
            done(res)
            return False
        threading.Thread(target=go, daemon=True).start()

    def ip_dialog(dev, msg_label):
        """Automatic (DHCP) or a fixed address, and your own DNS servers, for the adapter's connection."""
        cfg = nm_ip_settings(dev["uuid"])
        if cfg is None:
            msg_label.set_text("This adapter has no saved connection to change.")
            return
        d = Gtk.Dialog(title="IP settings - %s" % (cfg["id"] or dev["iface"]), transient_for=win, modal=True)
        d.add_button("Cancel", Gtk.ResponseType.CANCEL)
        d.add_button("Save", Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        d.set_default_response(Gtk.ResponseType.OK)
        d.set_default_size(560, -1)
        box = d.get_content_area()
        box.set_spacing(12)
        for side_ in ("top", "bottom", "start", "end"):
            getattr(box, "set_margin_" + side_)(18)
        method = Gtk.ComboBoxText()
        method.append("auto", "Automatic (DHCP)")
        method.append("manual", "Manual (a fixed address)")
        if cfg["method"] == "other":
            method.append("other", "Something else (set in the full network editor)")
        method.set_active_id(cfg["method"])
        e_addr, e_mask, e_gw, e_dns = Gtk.Entry(), Gtk.Entry(), Gtk.Entry(), Gtk.Entry()
        for e_, t_, ph in ((e_addr, cfg["address"], "192.168.1.50"), (e_mask, cfg["prefix"], "24 or 255.255.255.0"),
                           (e_gw, cfg["gateway"], "192.168.1.1"), (e_dns, ", ".join(cfg["dns"]), "automatic")):
            e_.set_text(t_)
            e_.set_placeholder_text(ph)
            e_.set_activates_default(True)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.get_style_context().add_class("card")
        fixed_rows = []
        for i, (k, w_) in enumerate((("Configure IPv4", method), ("IP address", e_addr), ("Subnet", e_mask),
                                     ("Router", e_gw), ("DNS servers", e_dns))):
            r = row(k, w_, width=170)
            if i:
                r.get_style_context().add_class("sep")
            card.pack_start(r, False, False, 0)
            if w_ in (e_addr, e_mask, e_gw):
                fixed_rows.append(r)
        box.pack_start(card, False, False, 0)
        box.pack_start(dim("DNS servers: one or more addresses (like 1.1.1.1, 9.9.9.9) - leave it empty to use the "
                           "ones the network gives. Saving reconnects this connection."), False, False, 0)
        err = dim("")
        box.pack_start(err, False, False, 0)

        def sync(*_):
            for r in fixed_rows:
                r.set_sensitive(method.get_active_id() == "manual")
            d.set_response_sensitive(Gtk.ResponseType.OK, method.get_active_id() != "other")
        method.connect("changed", sync)
        guard_all(card)
        d.show_all()
        sync()
        while True:
            if d.run() != Gtk.ResponseType.OK:
                d.destroy()
                return
            vals, problem = parse_ip_form(method.get_active_id(), e_addr.get_text(), e_mask.get_text(),
                                          e_gw.get_text(), e_dns.get_text())
            if vals:
                break
            err.set_text("Not saved: " + problem + ".")
        d.destroy()
        net_background(lambda: nm_set_ip(dev["uuid"], vals, reconnect=dev["connected"]),
                       lambda res: net_reload(("Saved the IP settings of %s." % (cfg["id"] or dev["iface"]))
                                              if res[0] else "Could not change the IP settings: " + res[1],
                                              msg_label),
                       msg_label, "Saving the IP settings...")

    def fill_devices(devs, note=None, note_label=None):
        for box_ in (wd_box, ep_box):
            for c in box_.get_children():
                box_.remove(c)
        wifi = [d_ for d_ in devs if d_["type"] == "wifi"]
        wired = [d_ for d_ in devs if d_["type"] == "ethernet"]
        for d_ in wifi + wired:
            btns = []
            if d_.get("nm") and (d_["uuid"] or d_["type"] == "ethernet"):   # (NetworkManager's own adapters)
                msg_ = wf_msg if d_["type"] == "wifi" else ep_msg
                if d_["type"] == "ethernet" and d_["state"] not in ("unmanaged", "unavailable"):
                    b_ = Gtk.Button(label="Disconnect" if d_["connected"] else "Connect")
                    b_.connect("clicked", lambda _b, dv=d_, m=msg_: net_background(
                        lambda: nm_device_up(dv["iface"], not dv["connected"]),
                        lambda res, dv=dv, m=m: net_reload(None if res[0] else "Could not %s %s: %s" % (
                            "disconnect" if dv["connected"] else "connect", dv["iface"], res[1]), m),
                        m, "Disconnecting..." if dv["connected"] else "Connecting..."))
                    btns.append(b_)
                if d_["uuid"]:
                    b_ = Gtk.Button(label="IP settings...")
                    b_.connect("clicked", lambda _b, dv=d_, m=msg_: ip_dialog(dv, m))
                    btns.append(b_)
            (wd_box if d_["type"] == "wifi" else ep_box).pack_start(info_card(d_, btns), False, False, 0)
        if not wifi:
            wd_box.pack_start(dim("No Wi-Fi adapter found."), False, False, 0)
        if not wired:
            ep_box.pack_start(dim("No wired (Ethernet) adapter found on this computer."), False, False, 0)
        guard_all(wd_box)
        wd_box.show_all()
        ep_box.show_all()
        ep_msg.set_text("")
        if note and note_label is not None:
            note_label.set_text(note)

    def net_reload(note=None, note_label=None):
        net_background(net_devices, lambda devs: fill_devices(devs if isinstance(devs, list) else [], note,
                                                              note_label),
                       ep_msg, "Reading the network adapters...")
    ep_refresh.connect("clicked", lambda *_: (net_reload(), vpn_reload()))
    ep_editor.connect("clicked", on_wf_editor)

    # -- VPN
    vp = net_part()
    net_stack.add_titled(vp, "vpn", "VPN")
    vp.pack_start(heading("VPN connections"), False, False, 0)
    vpn_store, vpn_view, vpn_card = bt_list(["Name", "Type", "Status"])
    vpn_view.get_column(1).set_min_width(130)
    vpn_view.get_column(2).set_min_width(130)
    vp.pack_start(vpn_card, False, False, 0)
    vpn_btns = Gtk.Box(spacing=10)
    vpn_up = Gtk.Button(label="Connect")
    vpn_down = Gtk.Button(label="Disconnect")
    vpn_add = Gtk.Button(label="Add from a file...")
    vpn_del = Gtk.Button(label="Remove")
    for b_ in (vpn_up, vpn_down, vpn_add, vpn_del):
        vpn_btns.pack_start(b_, False, False, 0)
    vp.pack_start(vpn_btns, False, False, 0)
    vpn_btns2 = Gtk.Box(spacing=10)
    vpn_editor = Gtk.Button(label="Open full network editor")
    vpn_editor.set_sensitive(bool(shutil.which("nm-connection-editor")))
    vpn_editor.connect("clicked", on_wf_editor)
    vpn_btns2.pack_start(vpn_editor, False, False, 0)
    vp.pack_start(vpn_btns2, False, False, 0)
    vpn_msg = dim("")
    vp.pack_start(vpn_msg, False, False, 0)
    vp.pack_start(dim("Add a VPN from the file your VPN provider gives you: a WireGuard file (.conf) or an OpenVPN "
                      "file (.ovpn). Connecting may ask for a password. Other kinds (Cisco, IPsec...) are set up in the "
                      "full network editor." if nm_ok else
                      "VPN connections here use NetworkManager, which only runs on Linux. On this system use "
                      "WireGuard (wg-quick, or 'ifconfig wg' on OpenBSD) or OpenVPN from the packages."),
                  False, False, 0)
    if not nm_ok:
        for w_ in (vpn_card, vpn_btns, vpn_btns2):
            w_.set_no_show_all(True)
    vpn_all = (vpn_up, vpn_down, vpn_add, vpn_del)

    def vpn_fill(vpns):
        vpn_store.clear()
        for v_ in vpns if isinstance(vpns, list) else []:
            vpn_store.append([v_["name"], v_["kind"], "Connected" if v_["active"] else "", v_["uuid"]])
        if isinstance(vpns, list) and not vpns:
            vpn_msg.set_text("No VPN yet. Add one from a file.")
        for b_ in vpn_all:
            b_.set_sensitive(True)

    def vpn_reload(note=None):
        if not nm_ok:
            return

        def done(vpns):
            vpn_msg.set_text("")
            vpn_fill(vpns)
            if note:
                vpn_msg.set_text(note)
        for b_ in vpn_all:
            b_.set_sensitive(False)
        net_background(nm_vpns, done, vpn_msg, "Reading the VPN connections...")

    def vpn_selected():
        model, it = vpn_view.get_selection().get_selected()
        return (model[it][0], model[it][3]) if it else (None, None)

    def vpn_do(action, verb, done_text):
        name, uuid = vpn_selected()
        if not uuid:
            vpn_msg.set_text("Pick a VPN first.")
            return
        if action == "delete":
            q = Gtk.MessageDialog(transient_for=win, modal=True, message_type=Gtk.MessageType.QUESTION,
                                  buttons=Gtk.ButtonsType.NONE, text="Remove %s?" % name)
            q.format_secondary_text("Its settings are deleted. You can add it again from its file.")
            q.add_button("Cancel", Gtk.ResponseType.NO)
            q.add_button("Remove", Gtk.ResponseType.YES)
            ans = q.run()
            q.destroy()
            if ans != Gtk.ResponseType.YES:
                return
        net_background(lambda: nm_vpn(action, uuid),
                       lambda res: (vpn_reload((done_text % name) if res[0] else "Could not %s %s: %s" % (
                           verb, name, res[1])), net_reload()),
                       vpn_msg, "%s %s..." % (verb.capitalize() + "ing" if verb != "remove" else "Removing", name))
    vpn_up.connect("clicked", lambda *_: vpn_do("up", "connect", "Connected to %s."))
    vpn_down.connect("clicked", lambda *_: vpn_do("down", "disconnect", "Disconnected %s."))
    vpn_del.connect("clicked", lambda *_: vpn_do("delete", "remove", "Removed %s."))

    def on_vpn_add(*_):
        fc = Gtk.FileChooserDialog(title="Add a VPN from a file", transient_for=win, modal=True,
                                   action=Gtk.FileChooserAction.OPEN)
        fc.add_button("Cancel", Gtk.ResponseType.CANCEL)
        fc.add_button("Add", Gtk.ResponseType.OK).get_style_context().add_class("suggested-action")
        flt = Gtk.FileFilter()
        flt.set_name("VPN files (.conf, .ovpn)")
        for pat in ("*.conf", "*.ovpn", "*.CONF", "*.OVPN"):
            flt.add_pattern(pat)
        fc.add_filter(flt)
        every = Gtk.FileFilter()
        every.set_name("All files")
        every.add_pattern("*")
        fc.add_filter(every)
        path = fc.get_filename() if fc.run() == Gtk.ResponseType.OK else None
        fc.destroy()
        if not path:
            return
        net_background(lambda: nm_vpn_import(path),
                       lambda res: vpn_reload(("Added the %s VPN from %s." % (
                           "WireGuard" if res[1] == "wireguard" else "OpenVPN", os.path.basename(path)))
                           if res[0] else "Could not add it: " + res[1]),
                       vpn_msg, "Adding the VPN...")
    vpn_add.connect("clicked", on_vpn_add)

    # -- proxy (saved with Apply, like the rest of the window)
    pp = net_part()
    net_stack.add_titled(pp, "proxy", "Proxy")
    pp.pack_start(heading("Proxy"), False, False, 0)
    px_start = proxy_current(settings)
    px_mode = Gtk.ComboBoxText()
    px_mode.append("none", "No proxy")
    px_mode.append("manual", "Manual (a proxy server)")
    px_mode.append("auto", "Automatic (a configuration file URL)")
    px_mode.set_active_id(px_start["mode"])
    pp.pack_start(row("Proxy", px_mode), False, False, 0)
    px_http, px_https, px_socks, px_ignore, px_pac = (Gtk.Entry() for _i in range(5))
    for e_, k, ph in ((px_http, "http", "proxy.example.com:8080"), (px_https, "https", "proxy.example.com:8443"),
                      (px_socks, "socks", "proxy.example.com:1080"), (px_ignore, "ignore", "localhost, 127.0.0.0/8"),
                      (px_pac, "pac", "http://wpad.example.com/proxy.pac")):
        e_.set_text(px_start[k])
        e_.set_placeholder_text(ph)
    px_same = Gtk.Switch()
    px_same.set_halign(Gtk.Align.START)
    px_same.set_active(px_start["same"])
    px_rows = {"manual": [row("Web proxy (HTTP)", px_http), row("Same proxy for HTTPS", px_same),
                          row("Secure web proxy (HTTPS)", px_https), row("SOCKS proxy", px_socks)],
               "auto": [row("Configuration URL", px_pac)]}
    px_rows["both"] = [row("No proxy for", px_ignore)]
    for r_ in px_rows["manual"] + px_rows["auto"] + px_rows["both"]:
        r_.set_no_show_all(True)
        for c_ in r_.get_children():
            c_.show_all()
        pp.pack_start(r_, False, False, 0)
    pp.pack_start(dim("Programs you start after your next login use it (they read http_proxy and friends), and "
                      "Firefox and GTK apps that follow the system proxy%s. 'No proxy for': addresses that are "
                      "reached directly, separated by commas. Changes when you press Apply." % (
                          " use it at once" if _gsettings_proxy() else "")), False, False, 0)
    px_msg = dim("")
    pp.pack_start(px_msg, False, False, 0)

    def px_sync(*_):
        m = px_mode.get_active_id()
        for r_ in px_rows["manual"]:
            r_.set_visible(m == "manual")
        px_rows["manual"][2].set_visible(m == "manual" and not px_same.get_active())
        for r_ in px_rows["auto"]:
            r_.set_visible(m == "auto")
        for r_ in px_rows["both"]:
            r_.set_visible(m in ("manual", "auto"))
    px_mode.connect("changed", px_sync)
    px_same.connect("notify::active", px_sync)
    px_saved = {"v": px_start}

    def proxy_form():
        """The Proxy section as a saved setting, or (None, the problem). Fields the chosen mode does not use are
        kept as they are (so an unchanged section counts as unchanged)."""
        cfg = dict(PROXY_DEFAULT, mode=px_mode.get_active_id() or "none", same=px_same.get_active())
        used = {"http": cfg["mode"] == "manual", "https": cfg["mode"] == "manual" and not cfg["same"],
                "socks": cfg["mode"] == "manual"}
        for k, e_, what in (("http", px_http, "web proxy"), ("https", px_https, "HTTPS proxy"),
                            ("socks", px_socks, "SOCKS proxy")):
            t_ = e_.get_text().strip()
            hp = parse_hostport(t_) if t_ else None
            if t_ and not hp and used[k]:
                return None, "the %s must be server:port, like proxy.example.com:8080" % what
            cfg[k] = _hostport_text(hp) if hp else (px_saved["v"][k] if t_ else "")
        if cfg["mode"] == "manual" and not (cfg["http"] or (cfg["https"] and not cfg["same"]) or cfg["socks"]):
            return None, "enter a proxy server, like proxy.example.com:8080"
        pac = px_pac.get_text().strip()
        if cfg["mode"] == "auto" and not valid_pac(pac):
            return None, "the configuration URL must start with http://, https:// or file://"
        cfg["pac"] = pac if valid_pac(pac) else (px_saved["v"]["pac"] if pac else "")
        ign = parse_ignore(px_ignore.get_text())
        if ign is None and cfg["mode"] != "none":
            return None, "'No proxy for' may only hold host names and addresses, separated by commas"
        cfg["ignore"] = ", ".join(ign) if ign is not None else px_saved["v"]["ignore"]
        return proxy_choice({"proxy": cfg}), None

    net_loaded = {"done": False}

    def on_net_page(_nb, _page, num):
        if num == nb.page_num(wp_page) and not net_loaded["done"]:
            net_loaded["done"] = True
            px_sync()
            net_reload()
            vpn_reload()
        return False
    nb.connect("switch-page", on_net_page)

    def on_net_part(*_):
        """Coming back to Ethernet or VPN shows them as they are now (a cable or a VPN may have changed)."""
        if not net_loaded["done"] or net_busy["n"] > 0:
            return
        part = net_stack.get_visible_child_name()
        if part == "ethernet":
            net_reload()
        elif part == "vpn":
            vpn_reload()
    net_stack.connect("notify::visible-child", on_net_part)

    # ---------------- themes tab
    tp = page()
    tt = Gtk.Label(label="Terminal themes", xalign=0)
    tt.get_style_context().add_class("title")
    tp.pack_start(tt, False, False, 0)
    tp.pack_start(dim("Pick a colour theme and a text size for each terminal. The preview shows the background, the "
                      "text at the chosen size and the 16 terminal colours. Press Apply to use them; open terminals "
                      "reload by themselves (a Ghostty window you zoomed with Ctrl +/- keeps its own size)."),
                  False, False, 0)
    theme_pick = {}                                  # kind -> function returning the chosen theme name
    font_pick = {}                                   # kind -> function returning the chosen text size
    prev_font = ("FantasqueSansM Nerd Font Mono" if "FantasqueSansM Nerd Font Mono" in query(["fc-list", ":", "family"])
                 else "monospace")
    saved_font = settings.get("terminal_font") or {}

    def theme_section(kind, title, themes, current):
        lbl = Gtk.Label(label=title, xalign=0)
        lbl.get_style_context().add_class("title")
        tp.pack_start(lbl, False, False, 0)
        if not themes:
            tp.pack_start(dim("No %s themes were found (%s is not installed or has no theme folder)." % (title, title)),
                          False, False, 0)
            theme_pick[kind] = lambda: None
            return
        store = Gtk.ListStore(str, str)
        names = sorted(themes, key=lambda n: (n != THEME_DEFAULT.get(kind), theme_label(kind, n).lower()))
        for n in names:
            store.append([theme_label(kind, n), n])
        flt = store.filter_new()
        query = {"q": ""}
        flt.set_visible_func(lambda m, it, _d: query["q"] in m[it][0].lower())
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search themes...")
        view = Gtk.TreeView(model=flt)
        view.set_headers_visible(False)
        view.append_column(Gtk.TreeViewColumn("Theme", Gtk.CellRendererText(), text=0))
        sc_ = Gtk.ScrolledWindow()
        sc_.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc_.set_min_content_height(130)
        sc_.add(view)
        prev = Gtk.DrawingArea()
        prev.set_size_request(-1, 92)
        cur = {"name": current if current in themes else None, "colors": None}
        size_now = clean_font_size(saved_font.get(kind)) or current_font_size(kind)
        size = Gtk.SpinButton.new_with_range(FONT_SIZE_RANGE[0], FONT_SIZE_RANGE[1], 0.5)
        size.set_digits(1)
        size.set_value(size_now)
        size_reset = Gtk.Button(label="Default (%g)" % FONT_SIZE_DEFAULT[kind])
        size_box = Gtk.Box(spacing=10)
        size_box.pack_start(size, False, False, 0)
        size_box.pack_start(Gtk.Label(label="pt"), False, False, 0)
        size_box.pack_start(size_reset, False, False, 0)
        size_reset.connect("clicked", lambda *_: size.set_value(FONT_SIZE_DEFAULT[kind]))

        def preview_height():
            px = size.get_value() * 96 / 72.0                       # points -> pixels at 96 dpi
            prev.set_size_request(-1, int(px * 1.6 + 60))
            prev.queue_draw()
        size.connect("value-changed", lambda *_: preview_height())
        font_pick[kind] = lambda: clean_font_size(size.get_value())

        def show(name):
            cur["name"] = name
            cur["colors"] = parse_theme_colors(kind, themes[name])
            prev.queue_draw()

        def hexrgb(h):
            return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

        def draw(_w, cr):
            c = cur["colors"]
            if not c:
                return False
            w_, h_ = prev.get_allocated_width(), prev.get_allocated_height()
            cr.set_source_rgb(*hexrgb(c["bg"]))
            cr.rectangle(0, 0, w_, h_)
            cr.fill()
            cr.set_source_rgb(*hexrgb(c["fg"]))
            cr.select_font_face(prev_font)
            px = size.get_value() * 96 / 72.0                       # the real size the terminal will use
            cr.set_font_size(px)
            cr.move_to(12, 10 + px)
            cr.show_text("user@host:~$ ls --color  The quick brown fox")
            top = int(px * 1.6) + 14
            for i, col in enumerate(c["palette"]):
                x = 12 + (i % 8) * 34
                y = top + (i // 8) * 22
                cr.set_source_rgb(*hexrgb(col))
                cr.rectangle(x, y, 30, 18)
                cr.fill()
            return False
        prev.connect("draw", draw)

        def on_sel(sel):
            model, it = sel.get_selected()
            if it:
                show(model[it][1])
        view.get_selection().connect("changed", on_sel)

        def on_search(e):
            query["q"] = e.get_text().strip().lower()
            flt.refilter()
        search.connect("search-changed", on_search)
        tp.pack_start(search, False, False, 0)
        tp.pack_start(sc_, True, True, 0)
        tp.pack_start(row("Text size", size_box, 120), False, False, 0)
        tp.pack_start(prev, False, False, 0)
        preview_height()
        theme_pick[kind] = lambda: cur["name"]
        if cur["name"]:
            for i, r_ in enumerate(flt):
                if r_[1] == cur["name"]:
                    view.get_selection().select_path(Gtk.TreePath(i))
                    view.scroll_to_cell(Gtk.TreePath(i), None, True, 0.3, 0)
                    break
            show(cur["name"])

    saved_t = settings.get("themes") or {}
    gh_themes, ki_themes = list_ghostty_themes(), list_kitty_themes()
    theme_section("ghostty", "Ghostty", gh_themes, saved_t.get("ghostty") or current_theme("ghostty"))
    theme_section("kitty", "kitty", ki_themes, saved_t.get("kitty") or current_theme("kitty"))
    add_page("themes", scrolled(tp))

    # ---------------- colors tab
    cp = page()
    ctitle = Gtk.Label(label="Colors", xalign=0)
    ctitle.get_style_context().add_class("title")
    cp.pack_start(ctitle, False, False, 0)
    cp.pack_start(dim("Pick the accent colour used everywhere: window borders, the bar, menus, notifications, "
                      "the lock screen and this window. Black and the greys stay as they are. "
                      "Press Apply to use it (the bar and borders refresh by themselves)."), False, False, 0)
    acc = {"v": live_accent["v"]}
    sw_css = "".join("button.sw-%s, button.sw-%s:hover { background-color: %s; border: 2px solid #303030; "
                     "padding: 0; min-height: 44px; }\n" % (k, k, hx) for k, _n, hx in ACCENT_PRESETS)
    sw_css += "button.sw-on, button.sw-on:hover { border: 3px solid #ffffff; }\n"
    sw_prov = Gtk.CssProvider()
    sw_prov.load_from_data(sw_css.encode())
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), sw_prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    pv_prov = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), pv_prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    grid = Gtk.Grid(column_spacing=12, row_spacing=12)
    sw_buttons = {}

    def pick_preset(_b, hx):
        set_accent(hx)

    for idx, (key, name, hx) in enumerate(ACCENT_PRESETS):
        cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        b = Gtk.Button()
        b.set_size_request(120, 44)
        b.get_style_context().add_class("sw-" + key)
        b.set_tooltip_text("%s  %s" % (name, hx))
        b.connect("clicked", pick_preset, hx)
        sw_buttons[key] = (b, hx)
        cell.pack_start(b, False, False, 0)
        cap = Gtk.Label(label=name, xalign=0.5)
        cap.get_style_context().add_class("dim")
        cell.pack_start(cap, False, False, 0)
        grid.attach(cell, idx % 3, idx // 3, 1, 1)
    cp.pack_start(grid, False, False, 0)

    custom_entry = Gtk.Entry(max_length=7, width_chars=9)
    custom_entry.set_placeholder_text("#00e5ff")
    cp.pack_start(row("Custom colour (hex)", custom_entry, width=230), False, False, 0)
    custom_msg = dim("")
    cp.pack_start(custom_msg, False, False, 0)

    pvt = Gtk.Label(label="Preview", xalign=0)
    pvt.get_style_context().add_class("dim")
    cp.pack_start(pvt, False, False, 0)
    pv_bar = Gtk.Box(spacing=4)
    pv_bar.get_style_context().add_class("pv-bar")
    for txt, cls in (("I", "pv-chip"), ("II", "pv-dim"), ("III", "pv-dim")):
        lb = Gtk.Label(label=txt)
        lb.get_style_context().add_class(cls)
        pv_bar.pack_start(lb, False, False, 0)
    for txt, cls in (("12:30", "pv-acc"), ("awake", "pv-acc")):
        lb = Gtk.Label(label=txt)
        lb.get_style_context().add_class(cls)
        pv_bar.pack_end(lb, False, False, 8)
    if have_cairo:                  # the real bar, in the style chosen in the Appearance tab
        col_bar = Gtk.DrawingArea()
        col_bar.set_size_request(-1, 45)
        col_bar.connect("draw", lambda area, cr: paint_bar(
            cr, area.get_allocated_width(), bar_style.get_active_id() or BAR_DEFAULT["style"],
            bar_div.get_active_id() or BAR_DEFAULT["divider"], live_accent["v"], bar_size.get_active_id() or "large",
            (["playerctl"] if bar_media.get_active() else []) + preview_items, title=bar_title.get_active(),
            spacing=clean_spacing(int(round(bar_space.get_value()))), **bar_bg_preview()) and False)
        accent_listeners.append(col_bar.queue_draw)
        cp.pack_start(col_bar, False, False, 0)
    else:
        cp.pack_start(pv_bar, False, False, 0)
    pv_win = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    pv_win.get_style_context().add_class("pv-win")
    lb = Gtk.Label(label="A focused window has this border", xalign=0)
    lb.get_style_context().add_class("pv-text")
    pv_win.pack_start(lb, False, False, 0)
    sel = Gtk.Label(label=" Selected menu item ", xalign=0)
    sel.get_style_context().add_class("pv-sel")
    pv_win.pack_start(sel, False, False, 0)
    cp.pack_start(pv_win, False, False, 0)

    def paint_preview(hx):
        pv_prov.load_from_data((
            ".pv-bar { background-color: #000000; border-bottom: 1px solid #303030; padding: 6px 4px; }\n"
            ".pv-chip { background-color: %(hx)s; color: #000000; padding: 3px 12px; }\n"
            ".pv-dim { color: #6e6e6e; padding: 3px 12px; }\n"
            ".pv-acc { color: %(hx)s; }\n"
            ".pv-win { background-color: #000000; border: 3px solid %(hx)s; padding: 14px; }\n"
            ".pv-text { color: #e6e6e6; }\n"
            ".pv-sel { background-color: %(hx)s; color: #000000; padding: 3px 8px; }\n" % {"hx": hx}).encode())

    def set_accent(hx, from_entry=False):
        hx = norm_accent(hx)
        if not hx:
            return
        acc["v"] = live_accent["v"] = hx
        for fn in accent_listeners:
            fn()
        for _k, (btn, bhx) in sw_buttons.items():
            ctx = btn.get_style_context()
            (ctx.add_class if bhx == hx else ctx.remove_class)("sw-on")
        if not from_entry:
            custom_entry.handler_block_by_func(on_custom)
            custom_entry.set_text(hx)
            custom_entry.handler_unblock_by_func(on_custom)
            custom_msg.set_text("")
        paint_preview(hx)

    def on_custom(e):
        txt = e.get_text()
        hx = norm_accent(txt)
        if not hx:
            custom_msg.set_text("Type a colour like #00e5ff." if txt.strip() else "")
        elif brightness(hx) < ACCENT_MIN_BRIGHT:
            custom_msg.set_text("That colour is too dark to read on black - pick a brighter one.")
        else:
            custom_msg.set_text("")
            set_accent(hx, from_entry=True)
    custom_entry.connect("changed", on_custom)
    set_accent(acc["v"])
    add_page("colors", scrolled(cp))

    # ---------------- buttons
    bar = Gtk.Box(spacing=10)
    for side in ("top", "bottom", "start", "end"):
        getattr(bar, "set_margin_" + side)(14)
    status = Gtk.Label(label="", xalign=0)
    status.get_style_context().add_class("status")
    status.set_ellipsize(3)                 # a long error message must not stretch the window
    status.set_max_width_chars(70)
    status.connect("notify::label", lambda lb, _p: lb.set_tooltip_text(lb.get_text() or None))
    bar.pack_start(status, True, True, 0)
    close = Gtk.Button(label="Close")
    close.connect("clicked", lambda *_: win.destroy())
    apply_btn = Gtk.Button(label="Apply")
    apply_btn.get_style_context().add_class("suggested-action")
    bar.pack_end(apply_btn, False, False, 0)
    bar.pack_end(close, False, False, 0)
    main_col.pack_start(Gtk.Separator(), False, False, 0)
    main_col.pack_start(bar, False, False, 0)

    def collect_monitors():
        cfg = {}
        names = enabled_names()
        x0 = min([pos[n][0] for n in names] or [0])
        y0 = min([pos[n][1] for n in names] or [0])
        for name, (en, res, hz, rot, pr) in widgets.items():
            px, py = pos[name] if name in names else (x0, y0)
            cfg[name] = {"enabled": en.get_active(), "mode": res.get_active_id(),
                         "rate": hz.get_active_id(), "rotate": rot.get_active_id(),
                         "scale": int(scales[name].get_active_id() or 100),
                         "primary": pr.get_active(), "x": int(px - x0), "y": int(py - y0)}
        return cfg

    def ask_keep():
        d = Gtk.MessageDialog(transient_for=win, modal=True, message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.NONE, text="Keep these display settings?")
        d.add_button("Revert", Gtk.ResponseType.NO)
        d.add_button("Keep", Gtk.ResponseType.YES)
        left = {"n": 10}
        d.format_secondary_text("Reverting in %d seconds..." % left["n"])

        def tick():
            left["n"] -= 1
            if left["n"] <= 0:
                d.response(Gtk.ResponseType.NO)
                return False
            d.format_secondary_text("Reverting in %d seconds..." % left["n"])
            return True
        tid = GLib.timeout_add_seconds(1, tick)
        resp = d.run()
        GLib.source_remove(tid) if left["n"] > 0 else None
        d.destroy()
        return resp == Gtk.ResponseType.YES

    def on_apply(*_):
        try:
            apply_everything()
        except Exception as e:  # noqa: BLE001 - never let a failed apply crash the window
            status.set_text("Error: %s" % e)

    def apply_everything():
        errs = []

        def safe(what, fn, *args, **kw):
            """One failing part (say, a read-only file) must not stop the rest or lose the saved settings."""
            try:
                return fn(*args, **kw)
            except Exception as e:  # noqa: BLE001
                errs.append("%s: %s" % (what, e))
                return None

        store_device()
        if cur_combo.get_active_id():
            settings["cursor"] = {"theme": cur_combo.get_active_id(), "size": int(cur_size.get_active_id())}
            safe("cursor", apply_cursor, settings)
        settings["opacity"] = {"active": int(op_active.get_value()), "inactive": int(op_inactive.get_value()),
                               "terminal": int(op_terminal.get_value())}
        safe("opacity", apply_opacity, settings, restart=True)
        picked = {k: f() for k, f in theme_pick.items() if f()}
        if picked:
            settings["themes"] = picked
            safe("themes", apply_themes, settings)
        sizes = {k: f() for k, f in font_pick.items() if f()}
        if sizes:
            settings["terminal_font"] = sizes
            safe("text size", apply_terminal_font, settings)
        settings["colors"] = {"accent": acc["v"]}
        safe("colors", apply_colors, settings)
        provider.load_from_data(css_for(acc["v"]))
        settings["gaps"] = {"inner": int(gap_inner.get_value()), "outer": int(gap_outer.get_value()),
                            "smart": gap_smart.get_active()}
        safe("gaps", apply_gaps, settings, reload=True)
        settings["apps"] = dict(app_new)
        safe("apps", apply_apps, settings)
        settings["tiling"] = {"mode": tiling_mode.get_active_id() or "dwindle"}
        safe("tiling", apply_tiling, settings)
        settings["gestures"] = {"enabled": gest_on.get_active(), "natural": gest_dir.get_active_id() != "reverse"}
        settings["sound"] = {"volume_feedback": fx_vol.get_active(), "screenshot_sound": fx_shot.get_active()}
        safe("sound", apply_sound, settings)
        safe("keybindings", kb_commit)
        chosen = [n for n, cb in bar_checks.items() if cb.get_active()]
        if bar_all.get_active() or not chosen:
            chosen = None
            if not bar_all.get_active():
                bar_all.set_active(True)      # nothing ticked = show everywhere, never a bar-less desktop
        old_choice = bar_choice(settings)
        settings["bar"] = {"position": bar_pos.get_active_id() or "top", "monitors": chosen,
                           "size": bar_size.get_active_id() or BAR_DEFAULT["size"],
                           "style": bar_style.get_active_id() or BAR_DEFAULT["style"],
                           "divider": bar_div.get_active_id() or BAR_DEFAULT["divider"],
                           "title": bar_title.get_active(), "media": bar_media.get_active(),
                           "spacing": clean_spacing(int(bar_space.get_value()))}
        settings["bar"]["bg_mode"], settings["bar"]["bg_opacity"], settings["bar"]["bg_color"] = bar_bg_now()
        old_icon = wifi_tray_icon(settings)
        settings["network"] = {"tray_icon": wf_tray.get_active()}
        pcfg, perr = proxy_form()
        if perr:
            errs.append("proxy not saved: " + perr)
            px_msg.set_text("Not saved: %s." % perr)
        else:
            px_msg.set_text("")
            if pcfg != px_saved["v"]:                  # (only a changed proxy is written anywhere)
                settings["proxy"] = pcfg
                safe("proxy", apply_proxy, settings)
                px_saved["v"] = pcfg
        # the bar (launch.sh) and the gesture / Wi-Fi helpers read settings.json themselves: save it before them
        safe("saving the settings", save_settings, settings)
        mouse_saved["v"] = json.loads(json.dumps(settings["mouse"]))
        safe("gestures", apply_gestures, settings)
        if wifi_tray_icon(settings) != old_icon:
            safe("Wi-Fi icon", apply_net_applet, settings, restart=True)
        if bar_choice(settings) != old_choice:
            safe("bar", apply_bar, settings)       # only restart the bar when its settings actually changed
        before = snapshot_monitors()
        new_mon = collect_monitors() if widgets else {}
        settings["monitors"] = new_mon or settings.get("monitors", {})
        try:
            apply_mouse(settings)
            # only a real layout change (resolution, rate, rotation, scale, position, on/off) needs the 10-second
            # "Keep?" question; making a screen primary cannot leave you with a dark screen
            def risky(d):
                return {k: {f: v for f, v in c.items() if f != "primary"} for k, c in d.items() if isinstance(c, dict)}
            changed = bool(new_mon) and risky(new_mon) != risky({k: v for k, v in before.items() if k in new_mon})
            any_change = bool(new_mon) and new_mon != {k: v for k, v in before.items() if k in new_mon}
            if new_mon:
                apply_monitors(settings)
                refresh_desktop(any_change)          # (a new primary screen moves the tray: redraw the bar)
            if changed and confirm and not DRY and not ask_keep():
                settings["monitors"] = before
                apply_monitors(settings)
                for name, (en, res, hz, rot, pr) in widgets.items():
                    b = before.get(name, {})
                    if b.get("mode"):
                        res.set_active_id(b["mode"])
                        hz.set_active_id(b.get("rate"))
                    rot.set_active_id(b.get("rotate", "normal"))
                    scales[name].set_active_id(str(b.get("scale", 100)))
                    en.set_active(b.get("enabled", True))
                    pr.set_active(b.get("primary", False))
                    if "x" in b:
                        pos[name] = (b["x"], b["y"])
                settle()
                place_all()
                status.set_text("Reverted the display change.")
                save_settings(settings)
                return
            save_settings(settings)
            if errs:
                status.set_text("Saved, but some parts failed - " + "; ".join(errs)[:220])
            else:
                status.set_text("Saved to %s" % SETTINGS_FILE.replace(os.path.expanduser("~"), "~"))
        except Exception as e:  # noqa: BLE001 - show any failure to the user
            status.set_text("Error: %s" % e)

    apply_btn.connect("clicked", on_apply)
    guard_all(nb)

    def show_tab(name):
        if name in NET_PARTS:
            net_stack.set_visible_child_name(name)
            name = "network"
        if name in page_w:
            nb.set_current_page(nb.page_num(page_w[name]))

    # ---------------- the list of pages on the left, with a search field on top
    search = Gtk.SearchEntry()
    search.set_placeholder_text("Search")
    search.get_style_context().add_class("search")
    for side_, px_ in (("top", 16), ("start", 12), ("end", 12)):
        getattr(search, "set_margin_" + side_)(px_)
    sidebar.pack_start(search, False, False, 0)
    nav = Gtk.ListBox()
    nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
    nav_rows = []                                       # (row, page, words, group)
    for key, label, glyph, words, grp in SIDEBAR:
        if key not in page_w:
            continue
        r_ = Gtk.ListBoxRow()
        hb = Gtk.Box(spacing=10)
        chip = Gtk.Label(label=glyph)
        chip.get_style_context().add_class("chip")
        chip.set_size_request(28, 28)
        lb_ = Gtk.Label(label=label, xalign=0)
        lb_.get_style_context().add_class("navlabel")
        hb.pack_start(chip, False, False, 0)
        hb.pack_start(lb_, True, True, 0)
        r_.add(hb)
        nav.add(r_)
        nav_rows.append((r_, key, (label + " " + words).lower(), grp))

    def nav_info(r_):
        return next((x for x in nav_rows if x[0] is r_), None)

    def nav_header(r_, before, *_):
        a, b = nav_info(r_), nav_info(before) if before is not None else None
        if b is not None and a is not None and a[3] != b[3]:
            gap = Gtk.Box()
            gap.set_size_request(-1, 14)               # (a little space between the groups, like macOS)
            r_.set_header(gap)
        else:
            r_.set_header(None)
    nav.set_header_func(nav_header)

    def nav_match(r_):
        q = search.get_text().strip().lower().split()
        info = nav_info(r_)
        return not q or info is None or all(w in info[2] for w in q)
    nav.set_filter_func(lambda r_, *_: nav_match(r_))
    nav_sw = Gtk.ScrolledWindow()
    nav_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    nav_sw.add(nav)
    sidebar.pack_start(nav_sw, True, True, 0)
    nav_sync = {"busy": False}

    def on_nav(_lb, r_):
        info = nav_info(r_) if r_ is not None else None
        if info is None or nav_sync["busy"]:
            return
        nb.set_current_page(nb.page_num(page_w[info[1]]))
    nav.connect("row-selected", on_nav)

    def on_nb_switch(_nb, widget, _num):
        key = next((k for k, w in page_w.items() if w is widget), None)
        r_ = next((x[0] for x in nav_rows if x[1] == key), None)
        if r_ is not None and nav.get_selected_row() is not r_:
            nav_sync["busy"] = True
            nav.select_row(r_)
            nav_sync["busy"] = False
        return False
    nb.connect("switch-page", on_nb_switch)

    def on_search(*_):
        nav.invalidate_filter()
    search.connect("search-changed", on_search)

    part_words = {"proxy": "proxy", "vpn": "vpn", "wireguard": "vpn", "openvpn": "vpn", "ethernet": "ethernet",
                  "lan": "ethernet", "wired": "ethernet", "cable": "ethernet", "wifi": "wifi", "wi-fi": "wifi",
                  "wireless": "wifi"}

    def on_search_enter(*_):
        for r_, key, _w, _g in nav_rows:
            if nav_match(r_):
                nav.select_row(r_)                     # Enter: the first page that matches
                q = search.get_text().strip().lower().split()
                if key == "network" and q and q[0] in part_words:
                    net_stack.set_visible_child_name(part_words[q[0]])   # ...on the part it names
                break
    search.connect("activate", on_search_enter)

    def on_key(_w, ev):
        if ev.state & Gdk.ModifierType.CONTROL_MASK and ev.keyval in (Gdk.KEY_f, Gdk.KEY_F):
            search.grab_focus()                        # Ctrl+F: search the pages
            return True
        return False
    win.connect("key-press-event", on_key)
    def page_box_of(widget, depth=4):
        """The page() box inside a page widget (scrolled window, viewport...)."""
        if widget in page_boxes:
            return widget
        if depth and isinstance(widget, Gtk.Container):
            for c in widget.get_children():
                found = page_box_of(c, depth - 1)
                if found is not None:
                    return found
        return None
    page_names = {}
    for key, label, _g, _w, _grp in SIDEBAR:
        pb = page_box_of(page_w[key]) if key in page_w else None
        if pb is not None:
            page_names[id(pb)] = label
    for b_ in page_boxes:
        cardify(b_, name=page_names.get(id(b_)))
    for b_ in part_boxes:
        cardify(b_, part=True)

    # one window at a time: a second SUPER+ALT+M (or a click on the bar) brings this one to the front instead
    import socket
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    for _attempt in range(2):
        try:
            server.bind(GUI_SOCKET)
            break
        except OSError:
            if hand_over(tab):
                sys.exit(0)                             # another window answered: it shows itself
            try:
                os.unlink(GUI_SOCKET)                   # left over from a window that crashed
            except OSError:
                pass
    else:
        server = None
    if server is not None:
        server.listen(4)
        try:
            my_inode = os.stat(GUI_SOCKET).st_ino           # to remove only our own socket file when closing
        except OSError:
            my_inode = None

        def on_client(_src, _cond):
            try:
                conn, _addr = server.accept()
                conn.settimeout(1)
                msg = conn.recv(64).decode("utf-8", "replace").split()
                conn.sendall(b"ok\n")
                conn.close()
            except OSError:
                return True
            if msg[:1] == ["show"]:
                if len(msg) > 1 and msg[1] in TAB_NAMES:
                    show_tab(msg[1])
                win.present()
                run(["i3-msg", '[instance="^i3dots-settings$"] focus'])
            return True
        GLib.io_add_watch(server.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, on_client)

        def cleanup(*_):
            try:
                if my_inode is not None and os.stat(GUI_SOCKET).st_ino == my_inode:
                    os.unlink(GUI_SOCKET)
            except OSError:
                pass
        win.connect("destroy", cleanup)
    win.show_all()
    show_tab(tab if tab in TAB_NAMES else nav_rows[0][1])
    sel_ = nav.get_selected_row()
    if sel_ is not None:
        sel_.grab_focus()                               # (the keyboard starts on the list of pages, not the search)
    if outputs:
        place_all()
    Gtk.main()


def main(argv):
    global DRY, FILES_ONLY
    DRY = "--dry-run" in argv
    if "--bar-env" in argv:
        settings = load_settings()
        try:
            write_bar_style(settings)
        except OSError as e:                            # the bar still starts (with the last style written)
            print("i3 settings: could not write %s: %s" % (POLYBAR_STYLE, e), file=sys.stderr)
        print(bar_env(settings))
        return 0
    if "--i3bar-conf" in argv:                         # for polybar/launch.sh where there is no polybar
        print(i3bar_conf(load_settings()))
        return 0
    if "--apply" in argv:
        apply_all(load_settings())
        return 0
    if "--refresh-files" in argv:
        return refresh_files(load_settings())
    if "--cursor-files" in argv:                       # for install.sh: the default cursor into the files of a new
        FILES_ONLY = True                              # install (no saved settings yet), before the first login
        try:
            apply_cursor(load_settings())
        except Exception as e:  # noqa: BLE001
            print("i3 settings: apply_cursor failed: %s" % e, file=sys.stderr)
            return 1
        return 0
    if "--apply-mouse" in argv:                         # for InputWatch.py: a mouse or touchpad was plugged in
        apply_mouse(load_settings())
        return 0
    if "--gestures" in argv:                            # for Gestures.sh: are the swipe gestures switched on?
        print("on" if gesture_choice(load_settings())["enabled"] else "off")
        return 0
    if "--wifi-icon" in argv:                           # for NetApplet.sh: show nm-applet's tray icon?
        print("on" if wifi_tray_icon(load_settings()) else "off")
        return 0
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    tab = None
    if "--tab" in argv and argv.index("--tab") + 1 < len(argv):
        tab = argv[argv.index("--tab") + 1].lower().replace("-", "")
        tab = tab if tab in TAB_NAMES else None
    if not DRY and hand_over(tab):
        return 0                                        # the open settings window came to the front
    try:
        if launch_gui(confirm="--no-confirm" not in argv, tab=tab):
            return 1                                    # (no display to show it on)
    except ImportError:
        # `python3` may be a pyenv/conda/venv one without GTK: retry with the system Python that has it
        if not os.environ.get("I3DOTS_REEXEC"):
            check = "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk"
            cands = ["/usr/local/bin/python3", "/usr/pkg/bin/python3", "/usr/bin/python3"]
            for d in ("/usr/local/bin", "/usr/pkg/bin", "/usr/bin"):
                cands += sorted(glob.glob(d + "/python3.*[0-9]"), reverse=True)
            for cand in cands:
                if os.path.exists(cand) and os.path.realpath(cand) != os.path.realpath(sys.executable):
                    if subprocess.run([cand, "-c", check], capture_output=True).returncode == 0:
                        os.environ["I3DOTS_REEXEC"] = "1"
                        os.execv(cand, [cand] + sys.argv)
        print("The settings window needs GTK for Python. Install it:\n"
              "  FreeBSD / GhostBSD:  sudo pkg install py311-pygobject gtk3   (py3XX: your python3's version)\n"
              "  OpenBSD: doas pkg_add py3-gobject3 gtk+3\n"
              "  NetBSD:  pkgin install py314-gobject3 gtk3+   (py3XX: your python3's version)", file=sys.stderr)
        os.system("notify-send 'Settings' 'Install python3-gobject (GTK) to use the settings window' 2>/dev/null")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
