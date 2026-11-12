#!/usr/bin/env python3
"""The terminal of the operator, and the command that needs root.

The operator reported (2026-11-10):

  > *ok I see the same issue with hidden typing, afetr agnet runs pexdec
  > to ask root password I can notice this issue when the termo=inal does
  > not show typed characters*

The report of 2026-11-09 was about the same thing: the terminal was left
mute, so the operator typed into a terminal that showed nothing of it.

This probe measures the three things that decide it:

1. **the flag** - whether ``pkexec`` is allowed to fall back to its own
   textual agent.  That agent asks the password **on the terminal**, and
   the helper it spawns (``polkit-agent-helper-1``) turns the **echo off**
   on ``/dev/tty`` while it reads the answer.  ``libpolkit-agent-1``
   imports ``tcsetattr`` and ``tcgetattr`` - it changes the attributes of
   the terminal of the operator.

2. **the input** - what the child of an escalated command gets as its
   standard input.  The terminal of the operator, or nothing at all.

3. **the terminal** - whether the terminal is given back after a command
   that took it over.  The child is killed by the timeout of the command
   (``subprocess.run`` sends ``SIGKILL``), and a child that was killed
   while it held the echo off leaves the terminal mute.

Every measurement is made **inside a pty of its own**: the toolkit gives
the terminal back, and it reads the attributes of the controlling
terminal - so a probe that ran them in the terminal of the operator
would touch the very terminal it is measuring.  A probe that leaves a
mute terminal behind is not a probe.

Usage::

    python investigate/pkexec-hidden-typing/probe_escalation_terminal.py

Exit code 0 means the probe ran; the answer it prints is the state of
the code, not a verdict.
"""

from __future__ import annotations

import fcntl
import os
import pty
import shlex
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from toolkits.linux_toolkit import operations, privilege  # noqa: E402


#: A marker in the command line of the helper, so the probe can find it
#: again after the command was killed.
MARKER = "torvalds-probe-helper"

#: A child that behaves the way the polkit helper behaves: it takes the
#: terminal over - the echo off - and waits for the password.  It is
#: killed by the timeout of the command, and it never gets the password.
HELPER = """
# torvalds-probe-helper
import os, termios, time

fd = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY)
attributes = termios.tcgetattr(fd)
attributes[3] &= ~termios.ECHO
termios.tcsetattr(fd, termios.TCSANOW, attributes)
os.close(fd)

# The helper holds nothing of the caller: it keeps no pipe open.
os.close(0)
os.close(1)
os.close(2)
for other in range(3, 256):
    try:
        os.close(other)
    except OSError:
        pass

time.sleep(30)
"""


def echo_is_on(fd: int) -> bool:
    """Whether the terminal echoes what is typed.

    Args:
        fd: The file descriptor of the terminal.

    Returns:
        ``True`` when the echo is on.
    """
    try:
        attributes = termios.tcgetattr(fd)
    except Exception:
        return True
    return bool(attributes[3] & termios.ECHO)


def the_helper_is_alive() -> bool:
    """Whether the helper is still running.

    The timeout of a command kills the child that was started - the
    shell - and not necessarily the program the shell started.  A
    program that outlives the timeout keeps whatever it holds: the
    terminal, for one.

    Returns:
        ``True`` when a process with the marker in its command line is
        still there.
    """
    try:
        entries = os.listdir("/proc")
    except OSError:
        return False

    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % entry, "rb") as handle:
                command_line = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        if MARKER in command_line:
            return True
    return False


def show_the_flag() -> None:
    """Whether ``pkexec`` may ask the question on the terminal."""
    print("=" * 72)
    print("  1. THE FLAG - may pkexec ask the question on the terminal?")
    print("=" * 72)
    print()

    original = privilege.terminal_is_managed
    try:
        for managed in (True, False):
            privilege.terminal_is_managed = lambda: managed
            plan = privilege.plan_privilege("sudo systemctl restart nginx")
            state = "managed (an application draws the screen)" if managed else (
                "an ordinary console"
            )
            print("  the terminal is %-38s" % state)
            print("      the command : %s" % plan.command)
            print(
                "      the textual agent may ask: %s"
                % ("YES" if "--disable-internal-agent" not in plan.command else "no")
            )
    finally:
        privilege.terminal_is_managed = original

    print()
    print("  The textual agent of pkexec asks the password on the terminal,")
    print("  through a helper that turns the echo off on /dev/tty while it")
    print("  reads the answer.")
    print()


def show_the_input() -> None:
    """What the child of an escalated command gets as its standard input."""
    print("=" * 72)
    print("  2. THE INPUT - what the child gets as its standard input")
    print("=" * 72)
    print()

    recorded = {}
    original_run = operations.subprocess.run

    def recording_run(*args, **kwargs):
        recorded["stdin"] = kwargs.get("stdin", "inherited")
        return original_run(*args, **kwargs)

    original_plan = operations.plan_privilege

    def escalated_plan(*args, **kwargs):
        # The plan of an escalated command - without a pkexec: the
        # probe does not open a window and does not run a program as
        # another user.
        return privilege.PrivilegePlan(
            command="echo hello",
            backend="pkexec",
            escalated=True,
        )

    operations.subprocess.run = recording_run
    try:
        operations.execute_shell_command("echo hello")
        ordinary = recorded.get("stdin", "inherited")

        recorded.clear()
        operations.plan_privilege = escalated_plan
        operations.execute_shell_command("sudo echo hello")
        escalated = recorded.get("stdin", "inherited")
    finally:
        operations.subprocess.run = original_run
        operations.plan_privilege = original_plan

    print("  an ordinary command gets  : %s" % ordinary)
    print("  an escalated command gets : %s" % escalated)
    print()
    if escalated == "inherited":
        print("  The escalated child inherits the terminal of the operator:")
        print("  it can read the keystrokes, and it can ask a question that")
        print("  the operator cannot answer.")
    else:
        print("  The escalated child gets nothing to read: the terminal of")
        print("  the operator is its own.")
    print()


def show_the_terminal() -> None:
    """Whether the terminal is given back after a command took it over."""
    print("=" * 72)
    print("  3. THE TERMINAL - is it given back?")
    print("=" * 72)
    print()

    before = echo_is_on(sys.stdin.fileno()) if sys.stdin.isatty() else True
    print("  echo before the command : %s" % ("on" if before else "off"))

    with tempfile.TemporaryDirectory() as directory:
        # The helper is a program of its own: a program that takes the
        # terminal over is a program, and quoting it into a command
        # line hides what it does.
        helper_path = Path(directory) / "helper.py"
        helper_path.write_text(HELPER, encoding="utf-8")
        # The marker travels in the **command line**: that is where
        # the_helper_is_alive() looks for it, and a marker that lives
        # in the body of the script is in no command line at all.
        helper_command = "%s %s %s" % (
            shlex.quote(sys.executable),
            shlex.quote(str(helper_path)),
            shlex.quote(MARKER),
        )

        result = operations.execute_shell_command(helper_command, timeout=3)
        time.sleep(0.2)

        after = echo_is_on(sys.stdin.fileno()) if sys.stdin.isatty() else True
        alive = the_helper_is_alive()

    print("  echo after the command  : %s" % ("on" if after else "off"))
    print("  the helper still runs   : %s" % ("yes" if alive else "no"))
    print("  the command said        : %s" % result["stderr"][:100].replace("\n", " "))

    print()
    if after:
        print("  The terminal was given back: the operator sees what they type.")
    else:
        print("  The terminal was left mute: the operator types into a")
        print("  terminal that shows nothing of it - and that state belongs")
        print("  to the terminal, so it outlives the agent.")
    if alive:
        print("  The command outlived its own timeout, and it still holds")
        print("  what it took.")
    print()


def measure() -> None:
    """Run the three measurements - inside the pty of the probe."""
    show_the_flag()
    show_the_input()
    show_the_terminal()


def main() -> int:
    """Measure the terminal in a pty of its own, and print the answer.

    Returns:
        The exit code: 0 when the probe ran.
    """
    if "--child" in sys.argv:
        measure()
        return 0

    master, slave = pty.openpty()
    old = termios.tcgetattr(slave)

    def preexec() -> None:
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    try:
        process = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--child"],
            stdin=slave,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=preexec,
            env={**os.environ, "TERM": "xterm"},
        )
        try:
            output = process.communicate(timeout=180)[0]
        except subprocess.TimeoutExpired:
            process.kill()
            output = process.communicate()[0]
    finally:
        termios.tcsetattr(slave, termios.TCSANOW, old)
        os.close(master)
        os.close(slave)

    print(output.decode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
