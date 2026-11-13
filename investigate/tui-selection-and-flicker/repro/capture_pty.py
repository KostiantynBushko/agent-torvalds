"""
Capture the raw byte stream a terminal receives from the TUI.

Spawns ``tui_child.py`` on a pty of a fixed size, records everything the
child writes, and stores it in a file.  The file can then be replayed
through ``term_emulator.py`` to see the screen the operator sees.

The environment matters: Rich's ``Console.size`` prefers the ``LINES``
and ``COLUMNS`` environment variables over the real terminal size, so
the capture can be run with a *stale* ``LINES``/``COLUMNS`` pair to
reproduce the defect the operator sees.

Usage:
    python capture_pty.py --out capture.bin [--seconds 4] [--mode idle|request]
                           [--noisy] [--legacy-console] [--clear-env]
                           [--stale-lines N --stale-cols N] [--log-dir DIR]
"""
from __future__ import annotations

import argparse
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="capture.bin")
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--mode", choices=["idle", "request"], default="idle")
    parser.add_argument("--noisy", action="store_true")
    parser.add_argument("--legacy-console", action="store_true")
    parser.add_argument("--rows", type=int, default=40)
    parser.add_argument("--cols", type=int, default=120)
    parser.add_argument(
        "--clear-env",
        action="store_true",
        help="Remove LINES/COLUMNS from the environment of the child.",
    )
    parser.add_argument("--stale-lines", type=int, default=0)
    parser.add_argument("--stale-cols", type=int, default=0)
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Where the log of the child goes (TORVALDS_LOG_DIR).",
    )
    args = parser.parse_args()

    command = [
        sys.executable,
        os.path.join(HERE, "tui_child.py"),
        "--seconds",
        str(args.seconds),
        "--mode",
        args.mode,
    ]
    if args.noisy:
        command.append("--noisy")
    if args.legacy_console:
        command.append("--legacy-console")

    env = dict(os.environ)
    if args.clear_env:
        env.pop("LINES", None)
        env.pop("COLUMNS", None)
    if args.stale_lines:
        env["LINES"] = str(args.stale_lines)
    if args.stale_cols:
        env["COLUMNS"] = str(args.stale_cols)
    if args.log_dir:
        env["TORVALDS_LOG_DIR"] = os.path.abspath(args.log_dir)

    master, slave = pty.openpty()
    # Give the pty a fixed size, so the TUI lays out deterministically.
    fcntl.ioctl(
        slave, termios.TIOCSWINSZ, struct.pack("HHHH", args.rows, args.cols, 0, 0)
    )

    child = subprocess.Popen(
        command,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=REPO,
        env=env,
        close_fds=True,
    )
    os.close(slave)

    chunks = []
    deadline = time.time() + args.seconds + 2.0
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if not ready:
                if child.poll() is not None:
                    break
                continue
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
    finally:
        if child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
        os.close(master)

    payload = b"".join(chunks)
    out_path = os.path.abspath(args.out)
    with open(out_path, "wb") as handle:
        handle.write(payload)

    print(f"captured {len(payload)} bytes -> {out_path}")


if __name__ == "__main__":
    main()
