"""
Unit tests for the privilege escalation of the Linux toolkit.

The tests cover the three parts of the feature:

* the **scan** - which ``sudo`` of a command line is a privilege
  escalation, and which is only an argument of another program;
* the **rewrite** - what the ``sudo`` becomes, and what is left alone;
* the **gate** - when pkexec may ask the operator, and what happens
  when it may not.

The suite is offline and hermetic: no test runs ``pkexec``, no test
opens a window, and no test touches anything outside the process.  The
gate is stubbed where it matters, so the tests say the same thing on a
machine with a desktop and on a machine without one.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

from .. import operations, privilege
from ..operations import check_privilege_backend, execute_shell_command
from ..privilege import (
    DEFAULT_TIMEOUT,
    PRIVILEGE_MODES,
    PRIVILEGE_TIMEOUT,
    find_sudo,
    plan_privilege,
    scan,
)


#: The repository root - three levels up from this file:
#: <root>/toolkits/linux-toolkit/tests/test_privilege.py
REPO_ROOT = Path(__file__).resolve().parents[3]


def _usable(value: bool = True, reason: str = "pkexec is not installed"):
    """A stub for ``pkexec_usable`` that answers *value*.

    The module is patched by **object** and not by name: the toolkit
    lives in a directory with a hyphen in its name, and the package is
    registered twice under two names - a patch that goes by name can
    land on the other copy.
    """
    return mock.patch.object(
        privilege,
        "pkexec_usable",
        return_value=(value, "" if value else reason),
    )


class TestTheScan(unittest.TestCase):
    """Which ``sudo`` is a privilege escalation."""

    def test_a_sudo_that_starts_a_command_is_an_escalation(self):
        invocations = find_sudo("sudo systemctl restart nginx")
        self.assertEqual(len(invocations), 1)
        self.assertEqual(invocations[0].program.value, "systemctl")
        self.assertEqual([a.value for a in invocations[0].args], ["restart", "nginx"])

    def test_a_sudo_after_a_pipe_is_an_escalation(self):
        invocations = find_sudo("ls | sudo tee out")
        self.assertEqual(len(invocations), 1)
        self.assertEqual(invocations[0].program.value, "tee")

    def test_a_sudo_after_a_logical_and_is_an_escalation(self):
        invocations = find_sudo("a && sudo b")
        self.assertEqual(len(invocations), 1)

    def test_a_sudo_inside_a_command_substitution_is_an_escalation(self):
        invocations = find_sudo("echo $(sudo id)")
        self.assertEqual(len(invocations), 1)
        self.assertEqual(invocations[0].program.value, "id")

    def test_a_sudo_as_an_argument_is_not_an_escalation(self):
        """``grep sudo /etc/sudoers`` searches for a word."""
        self.assertEqual(find_sudo("grep sudo /etc/sudoers"), [])

    def test_a_sudo_inside_a_quoted_word_is_not_an_escalation(self):
        self.assertEqual(find_sudo("echo sudo"), [])
        self.assertEqual(find_sudo("echo 'sudo ls'"), [])

    def test_a_program_that_only_looks_like_sudo_is_not_an_escalation(self):
        self.assertEqual(find_sudo("cat sudoers"), [])
        self.assertEqual(find_sudo("echo mysudo"), [])

    def test_two_sudos_are_two_escalations(self):
        invocations = find_sudo("sudo a && sudo b")
        self.assertEqual(len(invocations), 2)

    def test_the_user_is_read(self):
        for command, user in (
            ("sudo -u www-data whoami", "www-data"),
            ("sudo -uwww-data whoami", "www-data"),
            ("sudo --user www-data whoami", "www-data"),
            ("sudo --user=www-data whoami", "www-data"),
        ):
            with self.subTest(command=command):
                invocations = find_sudo(command)
                self.assertEqual(invocations[0].user, user)

    def test_a_sudo_that_runs_no_program_is_marked(self):
        invocations = find_sudo("sudo")
        self.assertIsNotNone(invocations[0].blocked)

    def test_a_sudo_that_lists_the_rights_is_marked(self):
        """``sudo -l`` does not run a program, and pkexec cannot list."""
        for command in ("sudo -l", "sudo --list", "sudo -v", "sudo -e"):
            with self.subTest(command=command):
                invocations = find_sudo(command)
                self.assertIsNotNone(invocations[0].blocked)

    def test_the_scan_knows_where_a_command_starts(self):
        tokens = scan("a && b")
        commands = [token.value for token in tokens if token.is_command]
        self.assertEqual(commands, ["a", "b"])


class TestTheRewrite(unittest.TestCase):
    """What the ``sudo`` becomes."""

    def _plan(self, command, mode="auto", usable=True):
        with _usable(usable), mock.patch.object(
            privilege,
            "terminal_is_managed",
            return_value=True,
        ):
            return plan_privilege(command, mode)

    def test_a_sudo_becomes_a_pkexec(self):
        plan = self._plan("sudo systemctl restart nginx")
        self.assertEqual(
            plan.command,
            "pkexec --keep-cwd --disable-internal-agent systemctl restart nginx",
        )
        self.assertEqual(plan.backend, "pkexec")
        self.assertTrue(plan.escalated)

    def test_the_working_directory_is_kept(self):
        """pkexec runs a program in the home of the target user."""
        plan = self._plan("sudo make install")
        self.assertIn("--keep-cwd", plan.command)

    def test_the_textual_agent_is_switched_off(self):
        """The question must not be asked on the terminal the agent draws on."""
        plan = self._plan("sudo make install")
        self.assertIn("--disable-internal-agent", plan.command)

    def test_the_user_is_kept(self):
        plan = self._plan("sudo -u www-data whoami")
        self.assertIn("--user www-data", plan.command)

    def test_a_flag_without_an_equivalent_is_dropped_and_reported(self):
        plan = self._plan("sudo -E make install")
        self.assertNotIn("-E", plan.command)
        self.assertTrue(any("-E" in note for note in plan.notes))

    def test_a_sudo_that_runs_no_program_is_left_alone(self):
        plan = self._plan("sudo -l")
        self.assertEqual(plan.command, "sudo -l")
        self.assertEqual(plan.backend, "sudo")

    def test_a_command_without_a_sudo_is_not_escalated(self):
        plan = self._plan("ls -la")
        self.assertEqual(plan.command, "ls -la")
        self.assertEqual(plan.backend, "none")
        self.assertFalse(plan.escalated)

    def test_the_rest_of_the_command_is_left_as_it_was_written(self):
        """The rewrite touches the sudo and nothing else."""
        plan = self._plan('sudo sh -c "echo hi" > /tmp/out')
        self.assertEqual(plan.command, 'pkexec --keep-cwd --disable-internal-agent sh -c "echo hi" > /tmp/out')

    def test_an_assignment_is_set_for_the_program_itself(self):
        """``sudo VAR=value cmd`` sets the variable for the program."""
        plan = self._plan("sudo VAR=value /bin/echo hi")
        self.assertIn("/usr/bin/env VAR=value /bin/echo hi", plan.command)

    def test_a_builtin_is_run_through_a_shell(self):
        plan = self._plan("sudo cd /tmp")
        self.assertIn("/bin/sh -c", plan.command)
        self.assertIn("cd /tmp", plan.command)

    def test_two_sudos_are_two_pkexecs(self):
        plan = self._plan("sudo a && sudo b")
        self.assertEqual(plan.command.count("pkexec"), 2)

    def test_the_rewrite_is_reported(self):
        plan = self._plan("sudo -u www-data whoami")
        self.assertEqual(len(plan.rewrites), 1)
        self.assertEqual(plan.rewrites[0]["user"], "www-data")


class TestTheGate(unittest.TestCase):
    """When pkexec may ask the operator."""

    def test_auto_uses_pkexec_when_it_can(self):
        with _usable(True):
            plan = plan_privilege("sudo make install")
        self.assertEqual(plan.backend, "pkexec")

    def test_auto_refuses_the_command_when_pkexec_cannot_ask(self):
        """The question belongs in a window, and there is no window.

        The command is refused with the reason.  It is **not** run as a
        ``sudo``: a ``sudo`` asks for the password on the terminal of
        the agent, and the terminal of the agent cannot give it back -
        the operator is left with a terminal that shows nothing of what
        they type.
        """
        with _usable(False):
            plan = plan_privilege("sudo make install")
        self.assertIsNotNone(plan.error)
        self.assertFalse(plan.success)
        self.assertIn("pkexec", plan.error)

    def test_the_reason_is_in_the_error(self):
        """The refusal says what is missing."""
        with _usable(False, "no polkit authentication agent is running"):
            plan = plan_privilege("sudo make install")
        self.assertIn("no polkit authentication agent is running", plan.error)

    def test_pkexec_refuses_the_command_when_it_cannot_ask(self):
        """The mode that insists on pkexec does not fall back silently."""
        with _usable(False):
            plan = plan_privilege("sudo make install", "pkexec")
        self.assertIsNotNone(plan.error)
        self.assertFalse(plan.success)

    def test_the_sudo_mode_still_asks_on_the_terminal(self):
        """The mode is the operator's own choice, and it is documented.

        It is the only way to ask for the password on the terminal -
        and the terminal is given back afterwards, whatever the command
        did to it.
        """
        with _usable(False):
            plan = plan_privilege("sudo make install", "sudo")
        self.assertIsNone(plan.error)
        self.assertTrue(plan.success)
        self.assertEqual(plan.command, "sudo make install")
        self.assertEqual(plan.backend, "sudo")

    def test_sudo_never_rewrites(self):
        with _usable(True):
            plan = plan_privilege("sudo make install", "sudo")
        self.assertEqual(plan.command, "sudo make install")
        self.assertEqual(plan.backend, "sudo")

    def test_an_unknown_mode_is_reported_and_not_raised(self):
        """A failure is reported, never raised - that is the contract."""
        plan = plan_privilege("ls", "banana")
        self.assertIsNotNone(plan.error)
        self.assertIn("banana", plan.error)

    def test_the_modes_are_the_ones_that_are_documented(self):
        self.assertEqual(PRIVILEGE_MODES, ("auto", "pkexec", "sudo"))


class TestTheTimeout(unittest.TestCase):
    """A window needs more time than a command."""

    def test_an_escalated_command_gets_the_longer_timeout(self):
        with _usable(True):
            plan = plan_privilege("sudo make install")
        self.assertEqual(plan.timeout, PRIVILEGE_TIMEOUT)

    def test_a_timeout_of_the_caller_is_respected(self):
        with _usable(True):
            plan = plan_privilege("sudo make install", timeout=5)
        self.assertEqual(plan.timeout, 5)

    def test_a_command_that_is_not_escalated_keeps_the_timeout(self):
        with _usable(True):
            plan = plan_privilege("ls -la")
        self.assertIsNone(plan.timeout)

    def test_the_default_timeout_is_the_one_the_operations_use(self):
        self.assertEqual(DEFAULT_TIMEOUT, 30)


class TestTheTerminal(unittest.TestCase):
    """The terminal the agent is drawing on must not be asked anything.

    The check is made against a pty of its own, so it never touches the
    terminal of the operator.
    """

    def _managed_in_a_pty(self, cbreak: bool) -> str:
        """What the toolkit sees of a terminal in the given mode."""
        import fcntl
        import os
        import pty
        import subprocess
        import termios
        import tty

        code = (
            "import sys; sys.path.insert(0, %r);"
            "from toolkits.linux_toolkit import privilege;"
            "print(privilege.terminal_is_managed())"
            % str(REPO_ROOT)
        )

        master, slave = pty.openpty()
        old = termios.tcgetattr(slave)
        if cbreak:
            # What the TUI does: the application draws the screen
            # itself, so the echo is off.
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

    def test_a_terminal_the_tui_draws_on_is_managed(self):
        """The echo is off in the TUI - the terminal must not be used."""
        self.assertEqual(self._managed_in_a_pty(cbreak=True), "True")

    def test_an_ordinary_console_is_not_managed(self):
        """A console with the echo on is a place a question belongs to."""
        self.assertEqual(self._managed_in_a_pty(cbreak=False), "False")


class TestTheOperations(unittest.TestCase):
    """The operations that use the plan."""

    def _run(self, command, **kwargs):
        """Run a command with the running of it stubbed out.

        The stub records what would have been run, so the test never
        starts pkexec and never opens a window.  The helper that runs
        the command is the one that is stubbed - it is the one that
        starts a process, and it is tested on its own.
        """
        recorded = {}

        def fake_run(cmd, **run_kwargs):
            recorded["command"] = cmd
            recorded["timeout"] = run_kwargs.get("timeout")
            recorded["env"] = run_kwargs.get("env")
            recorded["stdin"] = run_kwargs.get("stdin")
            return mock.Mock(
                stdout="ok\n",
                stderr="",
                returncode=0,
            )

        with mock.patch.object(
            operations, "_run_command", side_effect=fake_run
        ), _usable(True), mock.patch.object(
            privilege,
            "terminal_is_managed",
            return_value=True,
        ):
            result = execute_shell_command(command, **kwargs)

        return result, recorded

    def test_the_response_says_what_ran_the_command(self):
        result, _ = self._run("ls -la")
        self.assertEqual(result["privilege"], "none")
        self.assertTrue(result["success"])

    def test_a_sudo_is_escalated_through_pkexec(self):
        result, recorded = self._run("sudo make install")
        self.assertEqual(result["privilege"], "pkexec")
        self.assertIn("pkexec", recorded["command"])

    def test_the_command_that_is_run_is_the_rewritten_one(self):
        _, recorded = self._run("sudo make install")
        self.assertEqual(recorded["command"], "pkexec --keep-cwd --disable-internal-agent make install")

    def test_an_escalated_command_waits_longer_for_the_operator(self):
        _, recorded = self._run("sudo make install")
        self.assertEqual(recorded["timeout"], PRIVILEGE_TIMEOUT)

    def test_a_command_that_is_not_escalated_keeps_the_default_timeout(self):
        _, recorded = self._run("ls -la")
        self.assertEqual(recorded["timeout"], DEFAULT_TIMEOUT)

    def test_the_notes_of_the_escalation_are_reported(self):
        result, _ = self._run("sudo -E make install")
        self.assertIn("privilege_notes", result)
        self.assertTrue(any("-E" in note for note in result["privilege_notes"]))

    def test_a_command_that_cannot_be_asked_for_is_reported_and_not_raised(self):
        """Nothing is run when the question cannot be asked."""
        with mock.patch.object(
            operations, "_run_command"
        ) as run, _usable(False):
            result = execute_shell_command("sudo make install", privilege="pkexec")
        run.assert_not_called()
        self.assertFalse(result["success"])
        self.assertNotEqual(result["stderr"], "")

    def test_a_command_that_needs_root_is_refused_when_there_is_no_window(self):
        """The fallback of the mode ``auto`` is gone.

        The command is refused with the reason, and nothing is run: a
        pkexec --keep-cwd /bin/sh -c 'that is run as it was written asks for the password on'
        the terminal of the agent, and the terminal of the agent cannot
        give it back.
        """
        with mock.patch.object(
            operations, "_run_command"
        ) as run, _usable(False):
            result = execute_shell_command("sudo make install")
        run.assert_not_called()
        self.assertFalse(result["success"])
        self.assertIn("pkexec", result["stderr"])

    def test_the_privilege_backend_can_be_reported(self):
        status = check_privilege_backend()
        for key in ("backend", "usable", "pkexec_path", "gui_session", "polkit_agent"):
            self.assertIn(key, status)
        self.assertIn(status["backend"], ("pkexec", "none"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
