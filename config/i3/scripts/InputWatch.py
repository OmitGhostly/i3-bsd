#!/usr/bin/env python3
"""Re-apply the saved mouse and touchpad settings (Settings > Mouse) and the keyboard settings (Input.sh: layout,
key repeat, touchpad tapping) when a mouse, touchpad, trackball or keyboard is plugged in or reconnects - a
Bluetooth mouse after sleep, a USB mouse, a dock. A new device otherwise starts with the system defaults (speed 0,
acceleration on, US layout) until the next login.

Started by the i3 config (only one copy runs); it stops by itself when i3 exits. Needs udevadm (systemd).
"""
import fcntl
import os
import select
import shutil
import socket
import subprocess
import sys
import time

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SETTLE = 1.5            # seconds: let X pick the new device up first (and treat a burst of events as one)
CHECK_I3 = 30           # seconds between "is i3 still running?" checks


def i3_socket():
    path = os.environ.get("I3SOCK")
    if path and os.path.exists(path):
        return path
    try:
        return subprocess.run(["i3", "--get-socketpath"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def i3_alive(path):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(path)
        return True
    except OSError:
        return False
    finally:
        s.close()


def apply_mouse():
    for cmd in (["bash", os.path.join(SCRIPTS, "Input.sh"), "--devices"],
                [sys.executable, os.path.join(SCRIPTS, "SettingsGUI.py"), "--apply-mouse"]):
        try:
            subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pass


def main():
    if not shutil.which("udevadm"):
        return 0
    lock = open(os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "i3dots-inputwatch-%d.lock" % os.getuid()), "w")
    # only one copy: a second one (i3 reload starts this again) gives up - unless the first is a leftover from a
    # session that just ended, which notices that within CHECK_I3 seconds and quits, so wait a little longer
    give_up = time.monotonic() + CHECK_I3 + 5
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() > give_up:
                return 0
            time.sleep(1)
    sock = i3_socket()
    if not sock:
        return 0
    try:
        mon = subprocess.Popen(["udevadm", "monitor", "--udev", "--subsystem-match=input"], stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return 0
    due, checked, pending = None, time.monotonic(), b""
    fd = mon.stdout.fileno()
    try:
        while True:
            now = time.monotonic()
            wait = CHECK_I3 if due is None else max(0.0, due - now)
            ready, _, _ = select.select([fd], [], [], min(wait, CHECK_I3))
            if ready:
                chunk = os.read(fd, 65536)              # (raw reads: select and a buffered reader do not mix)
                if not chunk:
                    break                               # udevadm stopped
                lines = (pending + chunk).split(b"\n")
                pending = lines.pop()[-4096:]           # an unfinished line waits for the rest
                if any(b" add " in line for line in lines):
                    due = time.monotonic() + SETTLE     # (more events in the burst push it back a little)
            now = time.monotonic()
            if due is not None and now >= due:
                due = None
                apply_mouse()
            if now - checked >= CHECK_I3:
                checked = now
                if not i3_alive(sock):
                    break                               # logged out
    finally:
        mon.terminate()
        try:
            mon.wait(timeout=3)
        except subprocess.TimeoutExpired:
            mon.kill()
    return 0


if __name__ == "__main__":
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__.strip())
        sys.exit(0)
    sys.exit(main())
