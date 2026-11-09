#!/usr/bin/env python3
"""The workspaces on the bar for the joined-up bar styles (Pill, Dark pill, Powerline): one strip, shaped like the
items on the right, whose ends are the first and last workspace's own ends - flush with the numbers - and the
workspace you are on a block inside it. With a one-sided block shape (Flag, Tag, Slanted, ...) the left side is the
mirror of the right side, and Powerline draws the workspaces as a chain pointing to the middle like the items on
the right: each one's end cuts into the next (a thin line where two in the same colour meet).

Polybar's own i3 module cannot draw that: a workspace there does not know whether it is the first or the last one,
and that decides whether its end sits on the strip or on the bar. So this follows i3 itself and prints the whole
strip each time something changes (polybar custom/script, tail = true). The separate-block styles keep polybar's
module. Colours and block ends come from polybar/style.ini, which the settings window writes when the bar starts.
Needs nothing but python3: it talks to i3's IPC socket directly.

Like polybar's module: only the workspaces on this bar's monitor ($MONITOR) plus urgent ones, sorted by number,
"1:I" shown as "I"; click one to go there, scroll for the next / previous one; i3's mode (when not "default")
at the end.

  PolybarWorkspaces.py            run (polybar starts it)
  PolybarWorkspaces.py --once     print the strip once and stop
"""
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time

MAGIC = b"i3-ipc"
EVENT_BIT = 1 << 31
GET_WORKSPACES, SUBSCRIBE, GET_BINDING_STATE = 1, 2, 12
STATES = ("focused", "unfocused", "visible", "urgent", "mode")
# used when style.ini cannot be read: the Powerline look with white as the colour
DEFAULT_STYLE = {"strip": "#303030", "l": "", "r": "", "end-gap": 12, "chain": False, "thin": "#1c1c1c",
                 "focused": ("#ffffff", "#000000"), "unfocused": ("#303030", "#e6e6e6"),
                 "visible": ("#303030", "#ffffff"), "urgent": ("#bfbfbf", "#000000"), "mode": ("#ffffff", "#000000")}
HEX = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
# each solid block end -> its thin outline (Nerd Font: the next code point), for two blocks of one colour in a chain
THIN = {chr(c): chr(c + 1) for c in range(0xe0b0, 0xe0c0, 2)}


# ------------------------------------------------------------------ the look
def style_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "polybar", "style.ini")


def read_style(path=None):
    """The strip's colours and ends from the [barstyle] section of style.ini (anything missing or damaged: the
    default)."""
    st = dict(DEFAULT_STYLE)
    values, section = {}, None
    try:
        with open(path or style_path(), encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("["):
                    section = s.strip("[]").strip()
                elif section == "barstyle" and "=" in s and not s.startswith((";", "#")):
                    k, v = s.split("=", 1)
                    values[k.strip()] = v.strip()
    except (OSError, UnicodeDecodeError):
        return st
    if HEX.match(values.get("ws-strip", "")):
        st["strip"] = values["ws-strip"]
    for side in ("l", "r"):
        if "ws-cap-" + side in values:
            g = values["ws-cap-" + side]
            st[side] = g if len(g) <= 1 else st[side]
    gap = re.match(r"^(\d+)", values.get("ws-end-gap", ""))
    if gap:
        st["end-gap"] = int(gap.group(1))
    st["chain"] = values.get("ws-chain", "") == "true"
    if HEX.match(values.get("ws-thin", "")):
        st["thin"] = values["ws-thin"]
    for state in STATES:
        pair = values.get("ws-colors-" + state, "").split()
        if len(pair) == 2 and all(HEX.match(c) for c in pair):
            st[state] = tuple(pair)
    return st


def clean(text):
    """Text that cannot be taken for a polybar format tag."""
    return text.replace("%{", "% {")


def action(cmd):
    return cmd.replace("\\", "\\\\").replace(":", "\\:")


def plan(items, st):
    """What to draw for [(text, state)], item by item: a list of pieces for each one -
        ("cap", glyph, colour, colour behind it or None = the bar)   a block end
        ("room", colour)                                              a gap as wide as a block end
        ("text", text, colour, block colour)
    Nothing moves when you switch workspaces: every item takes the same room whatever its state.
      strip (pill, dark pill, symmetric shapes): room for an end on either side of each item - inside the strip
        that is the strip, or the ends of a block that sits in it; at the two outer ends it is the first / last
        item's own end, on the bar
      chain (powerline with a one-sided shape): the first item's start, then each item's end cutting into the
        next one (a thin line between two in one colour), the last one's end on the bar"""
    strip, left, right = st["strip"], st["l"], st["r"]
    colours = [st[state] for _, state in items]
    out = []
    for i, (text, state) in enumerate(items):
        bg, fg = colours[i]
        pieces = []
        if st.get("chain"):
            if i == 0 and left:
                pieces.append(("cap", left, bg, None))
            pieces.append(("text", text, fg, bg))
            if i < len(items) - 1:
                after = colours[i + 1][0]
                if not right:
                    pieces.append(("room", bg))               # flat ends: the blocks just meet
                elif after != bg:
                    pieces.append(("cap", right, bg, after))
                else:
                    pieces.append(("cap", THIN.get(right, right), st["thin"], bg))
            elif right:
                pieces.append(("cap", right, bg, None))
        else:
            inner = bg != strip
            for side, glyph in (("l", left), ("r", right)):
                if side == "r":
                    pieces.append(("text", text, fg, bg))
                if not glyph:
                    continue
                if (i == 0) if side == "l" else (i == len(items) - 1):
                    pieces.append(("cap", glyph, bg, None))  # the end of the whole strip, on the bar
                elif inner:
                    pieces.append(("cap", glyph, bg, strip))  # a block's end cutting into the strip
                else:
                    pieces.append(("room", strip))           # just the strip
        out.append(pieces)
    return out


def render(items, st, scroll=(None, None)):
    """The strip for [(text, state, click command or None)] as polybar format tags (see plan())."""
    if not items:
        return ""
    out = []
    for (text, state, click), pieces in zip(items, plan([(t, s) for t, s, _ in items], st)):
        seg = ""
        for p in pieces:
            if p[0] == "cap":
                seg += "%s%%{T3}%%{F%s}%s%%{T-}%%{B-}" % ("%%{B%s}" % p[3] if p[3] else "%{B-}", p[2], p[1])
            elif p[0] == "room":
                seg += "%%{B%s}%%{T3} %%{T-}%%{B-}" % p[1]
            else:
                seg += "%%{B%s}%%{F%s} %s %%{B-}" % (p[3], p[2], clean(p[1]))
        if click:
            seg = "%%{A1:%s:}%s%%{A}" % (action(click), seg)
        out.append(seg)
    line = "".join(out) + "%{F-}"
    up, down = scroll                                   # (scroll up: the next one, like polybar's module)
    if down:
        line = "%%{A5:%s:}%s%%{A}" % (action(down), line)
    if up:
        line = "%%{A4:%s:}%s%%{A}" % (action(up), line)
    if st["end-gap"]:
        line += "%%{O%d}" % st["end-gap"]
    return line


# ------------------------------------------------------------------ i3
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
            if not t & EVENT_BIT:
                return data


def shown_name(name):
    """"1:I" -> "I" (everything up to the first ":" goes, like polybar's strip-wsnumbers)."""
    return name.split(":", 1)[-1].strip(" ")


def goto(ws):
    if isinstance(ws.get("num"), int) and ws["num"] >= 0 and re.match(r"^%d(:|$)" % ws["num"], ws.get("name", "")):
        return "i3-msg -q workspace number %d" % ws["num"]
    return "i3-msg -q 'workspace \"%s\"'" % ws.get("name", "").replace("'", "").replace('"', '\\"')


def strip_for(workspaces, mode, monitor):
    """(items, (scroll up, scroll down)) for the workspaces i3 reported."""
    mine = [w for w in workspaces if not monitor or w.get("output") == monitor or w.get("urgent")]
    if monitor and not any(w.get("output") == monitor for w in workspaces):
        mine = list(workspaces)                     # (a monitor name that matches nothing: show them all)
    mine.sort(key=lambda w: (w.get("num", -1) < 0, w.get("num", -1), w.get("name", "")))
    items = []
    for w in mine:
        if w.get("focused"):
            state = "focused"
        elif w.get("urgent"):
            state = "urgent"
        elif w.get("visible"):
            state = "visible"
        else:
            state = "unfocused"
        items.append((shown_name(w.get("name", "")), state, goto(w)))
    if mode and mode != "default":
        items.append((mode, "mode", None))
    # scrolling goes through this monitor's workspaces only, and stops at the ends
    own = [w for w in mine if not monitor or w.get("output") == monitor] or mine
    current = next((k for k, w in enumerate(own) if w.get("visible")), None)
    up = down = None
    if current is not None:
        if current + 1 < len(own):
            up = goto(own[current + 1])
        if current > 0:
            down = goto(own[current - 1])
    return items, (up, down)


def current_mode(ipc):
    try:
        return (ipc.request(GET_BINDING_STATE) or {}).get("name", "default")
    except (ConnectionError, OSError, ValueError, AttributeError):
        return "default"


def main():
    st = read_style()
    monitor = os.environ.get("MONITOR", "")
    once = "--once" in sys.argv[1:]
    last = None
    while True:
        query = events = None
        try:
            path = socket_path()
            query, events = IPC(path), IPC(path)
            mode = current_mode(query)
            events.send(SUBSCRIBE, json.dumps(["workspace", "mode", "output", "shutdown"]))
            while True:
                items, scroll = strip_for(query.request(GET_WORKSPACES) or [], mode, monitor)
                line = render(items, st, scroll)
                if line != last:
                    print(line, flush=True)
                    last = line
                if once:
                    return 0
                t, data = events.recv()                 # wait for the next change
                while not t & EVENT_BIT:                # (the reply to the subscription)
                    t, data = events.recv()
                if t == EVENT_BIT | 2 and isinstance(data, dict):        # mode
                    mode = data.get("change", "default")
                elif t == EVENT_BIT | 6:                                 # shutdown (i3 restarts or exits)
                    raise ConnectionError("i3 is restarting")
        except (OSError, ConnectionError, ValueError):
            if once:
                return 1
            time.sleep(1)                                # i3 restarting: connect again
        finally:
            for c in (query, events):
                if c:
                    c.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, BrokenPipeError):
        sys.exit(0)
