#!/usr/bin/env python3
"""Spiral ("dwindle") tiling for i3, the way Hyprland tiles by default.

Whenever a window gets focus, i3 is told to split it along its longer side: a wide window is split side by
side, a tall one top and bottom. Opening windows one after another fills the screen like Hyprland:

    [ 1 ]  ->  [ 1 | 2 ]  ->  [ 1 | 2 ]  ->  [ 1 |  2  ]
                              [   | 3 ]      [   | 3|4 ]

Tabbed / stacked containers (SUPER+ALT+2/3), floating and fullscreen windows are left alone.
Turn it on or off with SUPER+ALT+T, or in Settings > Appearance > Window tiling.

When a screen is plugged in, unplugged or rearranged it redraws the wallpaper and the bars for the new layout.

It also keeps the focus ring (the border in your accent colour) on every window: apps that draw their own title
bar - Chrome, Electron apps like VS Code, Discord, Spotify - can tell i3 "no border" after they have opened, which
i3 obeys and the config's `for_window [all] border pixel 3` cannot catch (i3 does not even announce it, so every
window is looked at once a second). Such a border is put back. (To really hide
a window's border, give it `border pixel 0` in the i3 config: that is left alone.)
Needs nothing but python3: it talks to i3's IPC socket directly.

  AutoTiling.py            run (started by the i3 config; only one copy ever runs)
  AutoTiling.py --toggle   switch between spiral and classic (side by side) tiling
  AutoTiling.py --status   print the current mode
"""
import fcntl
import json
import os
import re
import select
import socket
import struct
import subprocess
import sys
import time

MAGIC = b"i3-ipc"
RUN_COMMAND, GET_WORKSPACES, SUBSCRIBE, GET_TREE, GET_CONFIG = 0, 1, 2, 4, 9
EVENT_BIT = 1 << 31
MODES = ("dwindle", "classic")          # dwindle = Hyprland-style spiral, classic = plain i3 (side by side)
DEFAULT_MODE = "dwindle"
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "i3")
SETTINGS = os.environ.get("I3DOTS_SETTINGS") or os.path.join(CONFIG_DIR, "settings.json")
RECONNECT_FOR = 30                       # seconds to wait for i3 to come back (in-place restart) before exiting
RING_WIDTH = 3                           # the border width the i3 config gives every window
RING_RECHECK = (0.4, 1.2, 3.0, 6.0)      # seconds after a window opens to look again (apps drop it a bit later)
RING_POLL = 1.0                          # seconds between looks at every window (an app can drop it at any time)
WORKSPACE_EVENT = 0                      # i3 IPC event: a workspace was made / focused / renamed ...
OUTPUT_EVENT = 1                         # i3 IPC event: a screen was plugged in, unplugged or rearranged
SCREENS_SETTLE = 1.5                     # seconds to wait after the last screen change before redrawing


# ------------------------------------------------------------------ mode (stored in settings.json)
def _load():
    try:
        with open(SETTINGS) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


_cache = {"mtime": None, "mode": DEFAULT_MODE}


def read_mode():
    """The saved mode; re-read only when settings.json changed (cheap to call on every event)."""
    try:
        mtime = os.stat(SETTINGS).st_mtime_ns
    except OSError:
        mtime = None
    if mtime != _cache["mtime"]:
        t = _load().get("tiling")
        mode = t.get("mode") if isinstance(t, dict) else None
        _cache.update(mtime=mtime, mode=mode if mode in MODES else DEFAULT_MODE)
    return _cache["mode"]


def save_mode(mode):
    data = _load()
    data["tiling"] = {"mode": mode}
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, SETTINGS)


def notify(text):
    try:
        subprocess.run(["notify-send", "-u", "low", "Window tiling", text], capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


# ------------------------------------------------------------------ i3 IPC
def socket_path():
    path = os.environ.get("I3SOCK")
    if path and os.path.exists(path):
        return path
    try:
        return subprocess.run(["i3", "--get-socketpath"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


class IPC:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("i3 closed the connection")
            buf += chunk
        return buf

    def send(self, mtype, payload=""):
        body = payload.encode()
        self.sock.sendall(MAGIC + struct.pack("=II", len(body), mtype) + body)

    def recv(self):
        head = self._read(14)
        if head[:6] != MAGIC:
            raise ConnectionError("not an i3 IPC reply")
        length, mtype = struct.unpack("=II", head[6:])
        return mtype, json.loads(self._read(length) or b"null")

    def request(self, mtype, payload=""):
        self.send(mtype, payload)
        while True:
            t, data = self.recv()
            if not t & EVENT_BIT:          # (this socket is not subscribed, but never mistake an event for the reply)
                return data


def find_focused(node, parent=None):
    if node.get("focused"):
        return node, parent
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        hit = find_focused(child, node)
        if hit:
            return hit
    return None


def keep_ring(cmd, con):
    """Put the border back on a window that asked i3 for none (see the top of this file)."""
    if not isinstance(con, dict) or not con.get("window") or con.get("border") != "none":
        return
    width = con.get("current_border_width")
    width = width if isinstance(width, int) and 1 <= width <= 20 else RING_WIDTH
    cmd.request(RUN_COMMAND, "[con_id=%d] border pixel %d" % (con["id"], width))


def workspace_names(cmd):
    """{2: "2:II", ...}: the names the i3 config gives workspaces 1-10 (set $ws2 "2:II")."""
    cfg = cmd.request(GET_CONFIG)
    text = cfg.get("config", "") if isinstance(cfg, dict) else ""
    names = {}
    for num, name in re.findall(r'^[ \t]*set[ \t]+\$ws(\d+)[ \t]+"?([^"\n]*?)"?[ \t]*$', text, re.M):
        n = int(num)
        if 1 <= n <= 10 and re.fullmatch(r'%d(:[^"\\]{1,40})?' % n, name):
            names[n] = name
    return names


def name_workspaces(cmd):
    """Give a workspace that is called just "1" (i3 makes one like that for each screen when it starts) its proper
    name, "1:I" - the bar shows "I" for it, the same as after SUPER+1. Without this the bar looked different right
    after logging in."""
    spaces = cmd.request(GET_WORKSPACES)
    if not isinstance(spaces, list):
        return
    taken = {w.get("name") for w in spaces if isinstance(w, dict)}
    names = None
    for w in spaces:
        name = w.get("name") if isinstance(w, dict) else None
        if not (isinstance(name, str) and name.isdigit()):
            continue
        if names is None:
            names = workspace_names(cmd)
        want = names.get(int(name))
        if want and want != name and want not in taken:
            cmd.request(RUN_COMMAND, 'rename workspace "%s" to "%s"' % (name, want))
            taken.add(want)


def screens_changed():
    """A screen was plugged in, unplugged or moved: draw the wallpaper for the new layout (feh draws it for the
    layout at the moment it runs - a later change leaves it misaligned) and give every screen its bar."""
    for cmd in ([os.path.join(CONFIG_DIR, "scripts", "Wallpaper.sh"), "--restore"],
                [os.path.join(os.path.dirname(CONFIG_DIR), "polybar", "launch.sh")]):
        if os.path.exists(cmd[0]):
            try:
                subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except OSError:
                pass


def all_windows(node):
    """Every window container below `node` (tiled and floating)."""
    if node.get("window"):
        yield node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        yield from all_windows(child)


def check_all_rings(cmd):
    """Look at every window once. An app can change its mind about its title bar at any time (Chrome and Electron
    when you switch the "system title bar" setting, GTK apps when they are maximised or tiled, a window that
    finishes loading late) and i3 does not tell anybody when the border goes: only looking finds out."""
    for con in all_windows(cmd.request(GET_TREE)):
        keep_ring(cmd, con)


def retile(cmd):
    """Set the split direction of the focused window to its longer side (what Hyprland's dwindle does)."""
    if read_mode() != "dwindle":
        return
    hit = find_focused(cmd.request(GET_TREE))
    if not hit:
        return
    con, parent = hit
    if con.get("type") != "con" or not con.get("window") or parent is None:
        return                                          # an empty workspace, or not a real window
    if parent.get("type") == "floating_con" or str(con.get("floating", "")).endswith("_on"):
        return                                          # floating windows are placed by hand
    if con.get("fullscreen_mode") or parent.get("layout") in ("tabbed", "stacked"):
        return                                          # keep tabs / stacks the user asked for
    rect = con.get("rect") or {}
    width, height = rect.get("width", 0), rect.get("height", 0)
    if not width or not height:
        return
    want = "splitv" if height > width else "splith"
    if parent.get("layout") != want:
        cmd.request(RUN_COMMAND, "split vertical" if want == "splitv" else "split horizontal")


def run():
    lock_dir = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    lock = open(os.path.join(lock_dir, "i3dots-autotiling-%d.lock" % os.getuid()), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0                                        # already running (i3 reload starts it again)
    last_ok = time.monotonic()
    while True:
        events = cmd = None
        try:
            path = socket_path()
            if not path:
                raise ConnectionError("i3 is not running")
            events, cmd = IPC(path), IPC(path)
            events.send(SUBSCRIBE, json.dumps(["window", "output", "workspace"]))
            events.recv()                               # {"success": true}
            last_ok = time.monotonic()
            name_workspaces(cmd)
            retile(cmd)
            later = []                                  # times to look at the windows again (just after one opened)
            checked = 0.0                               # when every window was last looked at
            screens_due = None                          # when to redraw after a screen change
            while True:
                now = time.monotonic()
                if screens_due is not None and now >= screens_due:
                    screens_due = None
                    screens_changed()
                if later and min(later) <= now or now - checked >= RING_POLL:
                    later = [t for t in later if t > now]
                    check_all_rings(cmd)
                    checked = last_ok = now
                wait = min([max(0.0, checked + RING_POLL - now)] + [max(0.0, t - now) for t in later]
                           + ([max(0.0, screens_due - now)] if screens_due is not None else []))
                ready, _, _ = select.select([events.sock], [], [], wait)
                if not ready:
                    continue
                mtype, ev = events.recv()
                if not (mtype & EVENT_BIT and isinstance(ev, dict)):
                    continue
                if mtype & ~EVENT_BIT == WORKSPACE_EVENT:
                    if ev.get("change") == "init":
                        name_workspaces(cmd)
                    continue
                if mtype & ~EVENT_BIT == OUTPUT_EVENT:
                    screens_due = time.monotonic() + SCREENS_SETTLE     # (a burst of changes counts as one)
                    continue
                change, con = ev.get("change"), ev.get("container")
                if change in ("new", "focus", "title", "floating", "move", "fullscreen_mode"):
                    keep_ring(cmd, con)
                if change == "new" and isinstance(con, dict) and isinstance(con.get("id"), int):
                    later += [time.monotonic() + d for d in RING_RECHECK]
                if change in ("focus", "new", "move", "floating"):
                    retile(cmd)
                    last_ok = time.monotonic()
        except (OSError, ConnectionError, ValueError):
            pass                                        # i3 restarted in place, or quit: try again for a while
        finally:
            for s in (events, cmd):
                if s:
                    s.close()
        if time.monotonic() - last_ok > RECONNECT_FOR:
            return 0                                    # i3 is gone (logged out)
        time.sleep(0.5)


def ensure_running():
    """Start the tiler in the background if it is not running (e.g. after it was killed)."""
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "i3dots-autotiling-%d.lock" % os.getuid())
    try:
        with open(path, "w") as probe:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(probe, fcntl.LOCK_UN)
    except OSError:
        return                                          # it is running (it holds the lock)
    subprocess.Popen([sys.executable, os.path.abspath(__file__)], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv):
    if "--status" in argv:
        print(read_mode())
        return 0
    if "--toggle" in argv:
        new = "classic" if read_mode() == "dwindle" else "dwindle"
        save_mode(new)
        notify("Spiral (like Hyprland): new windows split the focused one" if new == "dwindle"
               else "Classic: new windows open side by side")
        ensure_running()
        print(new)
        return 0
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
