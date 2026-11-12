"""
Tests for the command that outlives its timeout.

The timeout of a command used to kill the **shell** it started and
nothing else:

    result = subprocess.run(command, shell=True, timeout=timeout)

On a timeout, CPython calls ``process.kill()`` - SIGKILL, which cannot
be caught - and it kills the shell.  The program behind the shell - the
``sudo`` that asks for the password on the terminal - is its
grandchild, and it outlived the timeout: it kept the terminal with the
echo off, and the operator was left typing into a terminal that showed
nothing of it.

The timeout now ends the **whole tree**, and it ends it the way a
program is meant to be ended: a SIGTERM first, so a child that can
catch it gives the terminal back itself, and a SIGKILL after the grace
period, for a child that does not care.

The suite is offline and hermetic: no test runs ``pkexec``, no test
opens a window, and no test touches the terminal of the operator.

The verdict of the tests is reached through the **public** operation
and through a check of the processes that is written here, and not
through a helper of the implementation: a test that calls the very
helper it is proving would pass with a helper that does nothing.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from .. import operations, privilege
from ..operations import execute_shell_command


#: A command that starts a child of its own and writes the pid of that
#: child into a file.  The child is what outlives the timeout when the
#: tree is not ended as a whole.
STARTS_A_CHILD = """
import subprocess, sys, time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
with open(sys.argv[1], "w") as handle:
    handle.write(str(child.pid))
time.sleep(30)
"""

#: A command that catches the SIGTERM it is given.  It writes the fact
#: into a file, so the test can tell a SIGTERM from a SIGKILL: a
#: process that catches a signal is a process that was given the chance
#: to end by itself.
#:
#: The second file says that the handler is installed.  A signal that
#: arrives before the handler is there is a signal the process cannot
#: catch, and the test would prove nothing.
CATCHES_SIGTERM = """
import signal, sys, time

def handler(signum, frame):
    with open(sys.argv[1], "w") as handle:
        handle.write("terminated")
    sys.exit(0)

signal.signal(signal.SIGTERM, handler)
with open(sys.argv[2], "w") as handle:
    handle.write("ready")
time.sleep(30)
"""


def _alive(pid: int) -> bool:
    """Whether a process is still running.

    A process that has ended and only waits to be reaped holds
    nothing: it cannot answer a signal and it cannot keep a command
    alive.

    Args:
        pid: The pid of the process.

    Returns:
        ``True`` when the process is running.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as handle:
            stat = handle.read()
    except OSError:
        return True

    fields = stat[stat.rfind(")") + 2:].split()
    return not (fields and fields[0] == "Z")


def _usable(value: bool = True, reason: str = "pkexec is not installed"):
    """A stub for ``pkexec_usable`` that answers *value*."""
    return mock.patch.object(
        privilege,
        "pkexec_usable",
        return_value=(value, "" if value else reason),
    )


class TestTheTree(unittest.TestCase):
    """A command that outlives its timeout takes its tree with it."""

    def _wait_for(self, path: Path, timeout: float = 10.0) -> str:
        """Wait for the file to appear and return what it holds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    return content
            time.sleep(0.05)
        self.fail(f"the file {path} was not written within {timeout} seconds")

    def test_a_command_that_outlives_its_timeout_leaves_nothing_behind(self):
        """The program behind the shell does not outlive the timeout.

        This is the defect: the timeout killed the shell, and the
        program behind it - the ``sudo`` that asks for the password on
        the terminal - kept running with the echo off.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pid"
            command = "%s -c %s %s" % (
                shlex.quote(sys.executable),
                shlex.quote(STARTS_A_CHILD),
                shlex.quote(str(path)),
            )

            result = execute_shell_command(command, timeout=2)

            self.assertFalse(result["success"])
            self.assertEqual(result["returncode"], -1)
            self.assertIn("timed out", result["stderr"])

            grandchild = int(self._wait_for(path))
            try:
                self.assertFalse(
                    _alive(grandchild),
                    "the grandchild outlived the timeout of the command",
                )
            finally:
                # A process that outlived the timeout is left behind by
                # the defect; the test does not leave one behind itself.
                try:
                    os.kill(grandchild, signal.SIGKILL)
                except OSError:
                    pass

    def test_the_child_is_given_the_chance_to_end_by_itself(self):
        """A SIGTERM comes first, so a child can give the terminal back.

        A child that catches the SIGTERM is a child that was given the
        chance to give the terminal back by itself.  A child that is
        killed outright is a child that never gets the chance.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terminated"
            ready = Path(directory) / "ready"
            command = "%s -c %s %s %s" % (
                shlex.quote(sys.executable),
                shlex.quote(CATCHES_SIGTERM),
                shlex.quote(str(path)),
                shlex.quote(str(ready)),
            )

            execute_shell_command(command, timeout=2)

            # The handler has to be there before the signal comes, and
            # the file is written by the handler of the SIGTERM.
            self._wait_for(ready)
            self._wait_for(path)

    def test_the_grandchild_is_ended_with_the_shell(self):
        """The tree is ended as a whole, and not only the shell."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pid"
            process = subprocess.Popen(
                [sys.executable, "-c", STARTS_A_CHILD, str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                grandchild = int(self._wait_for(path))
                self.assertTrue(_alive(grandchild))

                operations._kill_tree(process.pid)

                self.assertFalse(
                    _alive(grandchild),
                    "the grandchild outlived the tree that was ended",
                )
            finally:
                operations._kill_tree(process.pid)
                process.wait(timeout=10)

    def test_the_timeout_is_reported_and_not_raised(self):
        """A timeout is a reported failure, never an exception."""
        result = execute_shell_command("sleep 30", timeout=1)
        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertIn("timed out", result["stderr"])


class TestTheRefusal(unittest.TestCase):
    """A command that needs root is refused when no window can be shown."""

    def test_nothing_is_run_and_the_reason_is_given(self):
        with mock.patch.object(operations, "_run_command") as run, _usable(
            False, "no polkit authentication agent is running"
        ):
            result = execute_shell_command("sudo make install")

        run.assert_not_called()
        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertIn("no polkit authentication agent is running", result["stderr"])

    def test_the_backend_is_reported_as_none(self):
        """The status says that there is no backend for the command."""
        with _usable(False):
            status = privilege.privilege_status()
        self.assertEqual(status["backend"], "none")
        self.assertFalse(status["usable"])

    def test_the_mode_sudo_still_runs_the_command_as_it_was_written(self):
        """The operator's own choice is not taken away."""
        with mock.patch.object(operations, "_run_command") as run, _usable(False):
            run.return_value = mock.Mock(stdout="ok\n", stderr="", returncode=0)
            result = execute_shell_command("sudo make install", privilege="sudo")

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], "sudo make install")
        self.assertTrue(result["success"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
