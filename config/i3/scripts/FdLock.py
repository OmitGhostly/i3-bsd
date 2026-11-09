#!/usr/bin/env python3
"""flock(1) for the systems that do not have it (FreeBSD and OpenBSD): lock a file descriptor the calling shell
script has open, the same way util-linux flock does.

    exec 9>some.lock; FdLock.py [-n | -w SECONDS] [-x | -s] 9

The lock belongs to the open file (shared with the script, which keeps file descriptor 9 open), so it is held until
the script closes it or ends - after this program has already exited. compat.sh makes `flock` call this when the
system has no flock command. Exit status like flock: 0 locked, 1 not locked (busy with -n, or -w ran out)."""
import fcntl
import sys
import time


def main(argv):
    wait, shared, fd = None, False, None
    args = list(argv)
    while args:
        a = args.pop(0)
        if a in ("-n", "--nb", "--nonblock"):
            wait = 0.0
        elif a in ("-w", "--wait", "--timeout"):
            try:
                wait = float(args.pop(0))
            except (IndexError, ValueError):
                return 64
        elif a.startswith("-w") and len(a) > 2:
            try:
                wait = float(a[2:])
            except ValueError:
                return 64
        elif a in ("-x", "-e", "--exclusive"):
            shared = False
        elif a in ("-s", "--shared"):
            shared = True
        elif a.isdigit():
            fd = int(a)
        else:
            return 64                       # (a command to run, a file name: not used by these scripts)
    if fd is None:
        return 64
    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    end = None if wait is None else time.monotonic() + wait
    while True:
        try:
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
            return 0
        except BlockingIOError:
            if end is not None and time.monotonic() >= end:
                return 1
            time.sleep(0.05)
        except OSError:
            return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
