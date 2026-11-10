#!/usr/bin/env python3
"""Probe the privilege escalation of the Linux toolkit.

It shows the three parts of the feature, without running ``pkexec`` and
without opening a window:

1. the **scan** - which ``sudo`` of a command line is a privilege
   escalation, and which is only an argument of another program;
2. the **rewrite** - what the ``sudo`` becomes, and what is left alone;
3. the **gate** - whether this machine can put the question in a window.

The terminal check is made against a pty of its own, so the probe never
touches the terminal of the operator.

Usage::

    python investigate/linux-privilege-escalation/probe_privilege_escalation.py

Exit code 0 means the probe ran; the answer it prints is the state of
the machine, not a verdict.
"""

from __future__ import annotations

import fcntl
import os
import pty
import subprocess
import sys
import termios
import tty
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from toolkits.linux_toolkit import privilege  # noqa: E402


COMMANDS = (
    "sudo systemctl restart nginx",
    "ls | sudo tee /tmp/out",
    "a && sudo b",
    "echo $(sudo id)",
    "sudo -u www-data whoami",
    "sudo -E make install",
    "sudo VAR=value /bin/echo hi",
    "sudo cd /tmp",
    "sudo -l",
    "sudo",
    "grep sudo /etc/sudoers",
    "echo sudo",
)


def show_the_scan() -> None:
    print("=" * 72)
    print("  1. THE SCAN - which sudo is a privilege escalation")
    print("=" * 72)
    print()
    for command in COMMANDS:
        invocations = privilege.find_sudo(command)
        if not invocations:
            print(f"  {command!r}")
            print("      no escalation - the word is only an argument")
            continue
        for invocation in invocations:
            program = invocation.program.value if invocation.program else "-"
            user = f", user={invocation.user}" if invocation.user else ""
            print(f"  {command!r}")
            print(f"      program={program!r}{user}")
            if invocation.dropped:
                print(f"      dropped: {invocation.dropped}")
            if invocation.blocked:
                print(f"      not rewritten: {invocation.blocked}")
    print()


def show_the_rewrite() -> None:
    print("=" * 72)
    print("  2. THE REWRITE - what the sudo becomes")
    print("=" * 72)
    print()
    for command in COMMANDS:
        plan = privilege.plan_privilege(command, "auto")
        if plan.backend == "none":
            continue
        print(f"  {command!r}")
        print(f"      -> {plan.command!r}")
        print(f"      backend={plan.backend}, timeout={plan.timeout}")
        for note in plan.notes:
            print(f"      note: {note}")
    print()


def show_the_gate() -> None:
    print("=" * 72)
    print("  3. THE GATE - can this machine ask in a window?")
    print("=" * 72)
    print()
    status = privilege.privilege_status()
    for key in (
        "backend",
        "usable",
        "pkexec_path",
        "gui_session",
        "polkit_agent",
        "terminal_managed",
        "reason",
    ):
        print(f"  {key:<18}: {status[key]}")
    print()
    if status["usable"]:
        print("  A command with a sudo in it will ask for the password in a window.")
    else:
        print("  A command with a sudo in it runs the sudo as it was written,")
        print("  and the password is asked for on the terminal.")
    print()


def show_the_terminal() -> None:
    print("=" * 72)
    print("  4. THE TERMINAL - is it a place a question belongs to?")
    print("=" * 72)
    print()
    code = (
        "import sys; sys.path.insert(0, %r);"
        "from toolkits.linux_toolkit import privilege;"
        "print(privilege.terminal_is_managed())" % str(REPO_ROOT)
    )

    def managed(cbreak: bool) -> str:
        master, slave = pty.openpty()
        old = termios.tcgetattr(slave)
        if cbreak:
            tty.setcbreak(slave)
        try:
            def preexec() -> None:
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

            result = subprocess.run(
                [sys.executable, "-c", code],
                stdin=slave,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=preexec,
                env={**os.environ, "TERM": "xterm"},
                timeout=120,
            )
            return result.stdout.decode().strip()
        finally:
            termios.tcsetattr(slave, termios.TCSADRAIN, old)
            os.close(master)
            os.close(slave)

    print("  the echo is off (the TUI draws the screen) : managed =", managed(True))
    print("  the echo is on  (an ordinary console)      : managed =", managed(False))
    print()
    print("  A managed terminal is never used for the question: pkexec is")
    print("  called with --disable-internal-agent, so it cannot fall back to")
    print("  its own textual prompt.")
    print()


def main() -> int:
    show_the_scan()
    show_the_rewrite()
    show_the_gate()
    show_the_terminal()
    return 0


if __name__ == "__main__":
    sys.exit(main())
