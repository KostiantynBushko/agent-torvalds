"""
Tests for the terminal of the operator, and the command that needs root.

The operator reported (2026-11-10):

  > *ok I see the same issue with hidden typing, afetr agnet runs pexdec
  > to ask root password I can notice this issue when the termo=inal does
  > not show typed characters*

Three things decide it, and each of them has a test here:

* the **question** is asked in a window, never on the terminal;
* the **child** of an escalated command does not get the terminal of the
  operator;
* the **terminal** is given back after the command, whatever the command
  did to it and whether the timeout killed it.

The suite is offline and hermetic: no test runs ``pkexec``, no test
opens a window, and no test touches the terminal of the operator - the
checks that need a terminal run against a pty of their own.

The modules are patched with :func:`mock.patch.object` and not with a
name: the toolkit lives in a directory with a hyphen in its name, and
the package is registered twice under two names - a patch that goes by
name can land on the other copy.
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
import unittest
from pathlib import Path
from unittest import mock

from .. import operations, privilege
from ..operations import execute_shell_command
from ..privilege import PrivilegePlan, restore_terminal


#: The repository root - three levels up from this file:
#: <root>/toolkits/linux-toolkit/tests/test_privilege_terminal.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: A child that behaves the way the helper of the textual agent of
#: pkexec behaves: it takes the terminal over - the echo off - and waits
#: for the password that never comes.
HELPER = """
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

time.sleep(10)
"""


def _usable(value: bool = True):
    """A stub for ``pkexec_usable`` that answers *value*."""
    return mock.patch.object(
        privilege,
        "pkexec_usable",
        return_value=(value, "" if value else "pkexec is not installed"),
    )


class TestTheQuestion(unittest.TestCase):
    """The question is asked in a window, never on the terminal."""

    def _plan(self, managed: bool) -> PrivilegePlan:
        """The plan of a command that asks for root."""
        with _usable(True), mock.patch.object(
            privilege,
            "terminal_is_managed",
            return_value=managed,
        ):
            return privilege.plan_privilege("sudo systemctl restart nginx")

    def test_the_textual_agent_is_switched_off_on_an_ordinary_console(self):
        """The terminal of the operator is not where the question belongs.

        Without the flag, pkexec falls back to its own textual agent
        when no graphical agent answers, and that agent asks the
        password on the terminal - through a helper that turns the echo
        off on /dev/tty while it reads the answer.
        """
        plan = self._plan(managed=False)
        self.assertIn("--disable-internal-agent", plan.command)

    def test_the_textual_agent_is_switched_off_on_a_managed_terminal(self):
        """The TUI draws the screen, and the question is still not asked there."""
        plan = self._plan(managed=True)
        self.assertIn("--disable-internal-agent", plan.command)

    def test_the_terminal_is_still_reported(self):
        """The state of the terminal is reported, whatever it is."""
        plan = self._plan(managed=True)
        self.assertEqual(plan.backend, "pkexec")


class TestTheInput(unittest.TestCase):
    """The child of an escalated command does not get the terminal."""

    def _run(self, command: str, plan: PrivilegePlan) -> dict:
        """Run a command with the running of it stubbed out.

        The helper that starts the process is the one that is stubbed:
        it is the one that knows what the child is given to read, and it
        is tested on its own.
        """
        recorded = {}

        def fake_run(cmd, **run_kwargs):
            recorded["command"] = cmd
            recorded["stdin"] = run_kwargs.get("stdin")
            return mock.Mock(stdout="ok\n", stderr="", returncode=0)

        with mock.patch.object(
            operations, "_run_command", side_effect=fake_run
        ), mock.patch.object(
            operations, "plan_privilege", return_value=plan
        ):
            execute_shell_command(command)

        return recorded

    def test_an_ordinary_command_keeps_the_terminal(self):
        """A command of the operator reads the terminal as it always did."""
        recorded = self._run("ls -la", PrivilegePlan(command="ls -la"))
        self.assertIsNone(recorded["stdin"])

    def test_an_escalated_command_gets_nothing_to_read(self):
        """The child of a privilege escalation runs as another user."""
        plan = PrivilegePlan(
            command="pkexec --keep-cwd id",
            backend="pkexec",
            escalated=True,
        )
        recorded = self._run("sudo id", plan)
        self.assertEqual(recorded["stdin"], subprocess.DEVNULL)


class TestTheTerminal(unittest.TestCase):
    """The terminal is given back after every command."""

    def _helper_command(self, directory: str) -> str:
        """The command of a helper that takes the terminal over.

        The helper is written to a file of its own: a program that
        takes the terminal over is a program, and quoting it into a
        command line hides what it does.
        """
        path = Path(directory) / "helper.py"
        path.write_text(HELPER, encoding="utf-8")
        return "%s %s" % (shlex.quote(sys.executable), shlex.quote(str(path)))

    def _in_a_pty(self, code: str, timeout: int = 120) -> str:
        """Run *code* against a pty of its own.

        The pty is the controlling terminal of the child, so the
        terminal of the operator is never touched.

        Args:
            code: The Python code to run in the child.
            timeout: The seconds the child may take.

        Returns:
            What the child printed.
        """
        master, slave = pty.openpty()
        old = termios.tcgetattr(slave)

        def preexec() -> None:
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                stdin=slave,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=preexec,
                env={**os.environ, "TERM": "xterm"},
                timeout=timeout,
            )
            return result.stdout.decode("utf-8", "replace")
        finally:
            termios.tcsetattr(slave, termios.TCSANOW, old)
            os.close(master)
            os.close(slave)

    def _run_the_helper_in_a_pty(self, before_too: bool) -> str:
        """Run a command that takes the terminal over, in a pty of its own.

        Args:
            before_too: Whether the state before the command is printed
                as well.

        Returns:
            What the child printed.
        """
        with tempfile.TemporaryDirectory() as directory:
            helper = self._helper_command(directory)
            code = (
                "import sys, termios;"
                "sys.path.insert(0, %r);"
                "from toolkits.linux_toolkit import operations;"
                "fd = sys.stdin.fileno();"
                "before = bool(termios.tcgetattr(fd)[3] & termios.ECHO);"
                "result = operations.execute_shell_command(%r, timeout=3);"
                "after = bool(termios.tcgetattr(fd)[3] & termios.ECHO);"
                "print(before, after)" % (str(REPO_ROOT), helper)
            )
            if not before_too:
                code = code.replace("print(before, after)", "print(after)")
            return self._in_a_pty(code).strip()

    def test_the_terminal_is_given_back_after_a_command_that_took_it(self):
        """A command that turned the echo off does not keep it off."""
        output = self._run_the_helper_in_a_pty(before_too=True)
        self.assertEqual(output.split()[-2:], ["True", "True"])

    def test_the_terminal_is_given_back_when_the_timeout_kills_the_command(self):
        """The timeout sends SIGKILL - the terminal is given back anyway."""
        output = self._run_the_helper_in_a_pty(before_too=False)
        self.assertEqual(output.split()[-1], "True")

    def test_a_terminal_that_is_not_there_is_reported(self):
        """There is nothing to give back when there was no terminal."""
        self.assertFalse(restore_terminal(None))

    def test_the_context_manager_gives_the_terminal_back(self):
        """The context manager puts the terminal back as it found it."""
        code = """
import sys, termios
sys.path.insert(0, %r)
from toolkits.linux_toolkit import privilege

fd = sys.stdin.fileno()
before = termios.tcgetattr(fd)
before[3] &= ~termios.ECHO
termios.tcsetattr(fd, termios.TCSANOW, before)
with privilege.preserved_terminal():
    pass
after = termios.tcgetattr(fd)
print(bool(after[3] & termios.ECHO))
""" % str(REPO_ROOT)
        output = self._in_a_pty(code).strip()
        self.assertEqual(output.split()[-1], "False")

    def test_the_context_manager_gives_the_terminal_back_when_the_body_fails(self):
        """An exception in the body does not keep the terminal."""
        code = """
import sys, termios
sys.path.insert(0, %r)
from toolkits.linux_toolkit import privilege

fd = sys.stdin.fileno()
before = termios.tcgetattr(fd)
before[3] &= ~termios.ECHO
termios.tcsetattr(fd, termios.TCSANOW, before)
try:
    with privilege.preserved_terminal():
        raise RuntimeError("the command failed")
except RuntimeError:
    pass
after = termios.tcgetattr(fd)
print(bool(after[3] & termios.ECHO))
""" % str(REPO_ROOT)
        output = self._in_a_pty(code).strip()
        self.assertEqual(output.split()[-1], "False")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
