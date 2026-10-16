"""Small process-group supervisor; closes workers if their daemon disappears.

Invoked only by ProcessTree, already in a fresh session. No shell/auth handling.
"""
import os
import signal
import subprocess
import sys
import time


def stop():
    os.killpg(os.getpgrp(), signal.SIGKILL)


def main():
    parent = int(sys.argv[1])
    if os.getppid() != parent:
        stop()
    child = subprocess.Popen(sys.argv[2:], stdin=subprocess.DEVNULL)
    while True:
        if os.getppid() != parent:
            stop()
        code = child.poll()
        if code is not None:
            raise SystemExit(code if code >= 0 else 128-code)
        time.sleep(.05)


if __name__ == '__main__':
    main()
