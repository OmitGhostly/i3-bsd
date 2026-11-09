#!/usr/bin/env python3
"""Go to the next or previous workspace by number: 1 -> 2 -> 3 ... and back, also to an empty one (it is created,
like pressing SUPER+2). Stops at 1 and at 10. The touchpad's three-finger swipe runs this (Gestures.sh).
Also moves the focused window to another workspace (SUPER+SHIFT+1..0, SUPER+CTRL+1..0, SUPER+SHIFT/CTRL+[ ]).

  Workspace.py next                  the workspace with the next number
  Workspace.py prev                  the workspace with the previous number
  Workspace.py move WS [follow]      move the focused window (or group) to workspace WS ("2:II", next, prev);
                                     with follow, go there too

Why moving goes through here: when the focused thing is a workspace itself that holds nothing but floating windows
(SUPER+CTRL+H on a floating window, or a sticky window that followed you to an empty workspace), i3's own "move
container to workspace" locks i3 up for good and eats memory until the computer runs out (i3 4.23 to 4.25.1).
Here those floating windows are moved one by one instead, which i3 handles fine; everything else is moved by i3's
own command, unchanged.
"""
import json
import re
import subprocess
import sys

FIRST, LAST = 1, 10


def i3(*args):
    try:
        return subprocess.run(["i3-msg"] + list(args), capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def name_for(num):
    """The name the i3 config gives workspace `num` (set $ws2 "2:II"), so a new one looks like SUPER+2 made it."""
    out = i3("-t", "get_config")
    try:
        config = json.loads(out).get("config", "")      # (the raw reply, from an i3-msg that does not unwrap it)
    except (ValueError, AttributeError):
        config = out                                    # i3-msg prints the config text itself
    m = re.search(r'^[ \t]*set[ \t]+\$ws%d[ \t]+"?([^"\n]*?)"?[ \t]*$' % num, config, re.M)
    name = m.group(1) if m else ""
    # only a plain "2" or "2:something" without quotes or backslashes goes into the i3 command
    return name if re.fullmatch(r'%d(:[^"\\]{1,40})?' % num, name) else str(num)


MOVE_TARGET_RE = re.compile(r'(next|prev|(10|[1-9])(:[^"\\]{1,40})?)\Z')


def find_focused(node):
    if not isinstance(node, dict):
        return None
    if node.get("focused"):
        return node
    for child in (node.get("nodes") or []) + (node.get("floating_nodes") or []):
        hit = find_focused(child)
        if hit:
            return hit
    return None


def floating_only_windows(tree):
    """The window ids to move one by one when the focused thing is a workspace with nothing but floating windows on
    it (see the top of this file); None in every other case."""
    node = find_focused(tree)
    if not node or node.get("type") != "workspace" or node.get("nodes") or not node.get("floating_nodes"):
        return None
    ids = []
    for fcon in node["floating_nodes"]:
        for win in (fcon.get("nodes") or []) if isinstance(fcon, dict) else []:
            if isinstance(win, dict) and isinstance(win.get("id"), int):
                ids.append(win["id"])
    return ids


def move(target, follow):
    where = "workspace " + target if target in ("next", "prev") else 'workspace number "%s"' % target
    try:
        tree = json.loads(i3("-t", "get_tree") or "null")
    except ValueError:
        tree = None
    ids = floating_only_windows(tree)
    if ids is None:
        cmds = ["move container to " + where]
    else:
        cmds = ["[con_id=%d] move container to %s" % (i, where) for i in ids]
    if follow:
        cmds.append(where)
    i3("; ".join(cmds))
    return 0


def main(argv):
    if argv[:1] == ["move"] and len(argv) in (2, 3) and MOVE_TARGET_RE.match(argv[1]) \
            and (len(argv) == 2 or argv[2] == "follow"):
        return move(argv[1], len(argv) == 3)
    if len(argv) != 1 or argv[0] not in ("next", "prev"):
        print(__doc__.strip())
        return 2
    try:
        spaces = json.loads(i3("-t", "get_workspaces") or "[]")
    except ValueError:
        return 1
    if not isinstance(spaces, list):
        return 1
    cur = next((w for w in spaces if isinstance(w, dict) and w.get("focused")), None)
    if cur is None:
        return 1
    num = cur.get("num") if isinstance(cur.get("num"), int) else -1
    if num < FIRST:                                     # a workspace without a number: start from the first
        want = FIRST
    else:
        want = num + 1 if argv[0] == "next" else num - 1
    if not FIRST <= want <= LAST or want == num:
        return 0
    if any(isinstance(w, dict) and w.get("num") == want for w in spaces):
        i3("workspace number %d" % want)                # it exists (whatever its name)
    else:
        i3('workspace number "%s"' % name_for(want))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
