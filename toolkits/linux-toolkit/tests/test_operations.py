"""
Unit tests for the Linux toolkit's library half.

Tests shell command execution and system operations including:
- execute_shell_command, execute_multiple_commands
- parse_command_output, get_system_info, check_file_permissions
- run_command_with_env

The suite moved here together with the toolkit: it used to live at
``tests/test_linux_toolkit.py`` and import the single module
``agent_linux_toolkit`` from the project root.  It now imports the library
half of the package through a **relative** import, so it belongs to the
package it tests.

The tests are offline and hermetic: every one of them runs harmless
commands (``echo``, ``pwd``, ``printf``) or works inside a temporary
directory, and none of them touches anything outside it.
"""

import os
import tempfile
import unittest
from pathlib import Path

from ..operations import (
    check_file_permissions,
    execute_multiple_commands,
    execute_shell_command,
    get_system_info,
    parse_command_output,
    run_command_with_env,
)

#: The repository root - three levels up from this file:
#: <root>/toolkits/linux-toolkit/tests/test_operations.py
REPO_ROOT = Path(__file__).resolve().parents[3]


class TestExecuteShellCommand(unittest.TestCase):
    def test_successful_command(self):
        result = execute_shell_command("echo hello")
        self.assertTrue(result["success"])
        self.assertIn("hello", result["stdout"])
        self.assertEqual(result["returncode"], 0)

    def test_failed_command(self):
        result = execute_shell_command("ls /nonexistent/path")
        self.assertFalse(result["success"])
        self.assertNotEqual(result["returncode"], 0)

    def test_returns_dict(self):
        result = execute_shell_command("pwd")
        self.assertIsInstance(result, dict)
        self.assertIn("stdout", result)
        self.assertIn("stderr", result)
        self.assertIn("returncode", result)
        self.assertIn("success", result)

    # -- the error contract ------------------------------------------------

    def test_a_failing_command_reports_the_error_and_never_raises(self):
        """A failure is *reported*, not raised.

        This is the contract the whole toolkit has: the agent gets a
        structured answer it can reason about, and the process never dies
        because a command exited non-zero.
        """
        result = execute_shell_command("ls /nonexistent/path")
        self.assertFalse(result["success"])
        self.assertEqual(result["stdout"], "")
        self.assertNotEqual(result["stderr"], "")
        self.assertIsInstance(result["returncode"], int)

    def test_a_timeout_is_reported_with_returncode_minus_one(self):
        """A timeout is a reported failure, not an exception."""
        result = execute_shell_command("sleep 5", timeout=1)
        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertEqual(result["stdout"], "")
        self.assertIn("timed out", result["stderr"])

    def test_the_timeout_message_names_the_command(self):
        result = execute_shell_command("sleep 5", timeout=1)
        self.assertIn("sleep 5", result["stderr"])

    def test_the_output_is_stripped(self):
        """The output is stripped, so the caller gets clean text."""
        result = execute_shell_command("printf 'hello\\n'")
        self.assertEqual(result["stdout"], "hello")

    def test_a_command_writing_to_stderr_is_captured(self):
        """The stderr is captured - but the command may still have succeeded.

        The exit code decides whether the command succeeded; stderr is
        only the text the command wrote.
        """
        result = execute_shell_command("echo oops >&2")
        self.assertIn("oops", result["stderr"])
        self.assertEqual(result["stdout"], "")

    def test_the_working_directory_is_honoured(self):
        """``cwd`` puts the command somewhere else."""
        with tempfile.TemporaryDirectory() as tmp:
            result = execute_shell_command("pwd", cwd=tmp)
            self.assertTrue(result["success"])
            # macOS puts /private in front of the temporary directory path.
            self.assertIn(os.path.basename(tmp), result["stdout"])

    def test_a_command_can_run_without_a_shell(self):
        """``shell=False`` runs the command directly, without a shell.

        Without a shell the string is the *program* to run, not a line
        for a shell to interpret - so it has to be a path.
        """
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "hello.sh")
            with open(script, "w") as handle:
                handle.write("#!/bin/sh\necho direct\n")
            os.chmod(script, 0o755)

            result = execute_shell_command(script, shell=False)
            self.assertTrue(result["success"])
            self.assertEqual(result["stdout"], "direct")

    def test_a_missing_binary_is_reported_and_never_raises(self):
        """Without a shell, a missing binary raises - and is caught."""
        result = execute_shell_command("definitely-not-a-real-binary", shell=False)
        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertNotEqual(result["stderr"], "")


class TestExecuteMultipleCommands(unittest.TestCase):
    def test_multiple_commands(self):
        commands = ["echo 1", "echo 2", "echo 3"]
        results = execute_multiple_commands(commands)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r["success"])

    def test_returns_list(self):
        results = execute_multiple_commands(["pwd"])
        self.assertIsInstance(results, list)

    # -- the error contract ------------------------------------------------

    def test_the_results_keep_the_order_of_the_commands(self):
        """The commands run one after another, in order."""
        results = execute_multiple_commands(["echo first", "echo second", "echo third"])
        self.assertEqual(
            [r["stdout"] for r in results],
            ["first", "second", "third"],
        )

    def test_one_failing_command_does_not_stop_the_others(self):
        """A failure is reported per command; the batch carries on."""
        results = execute_multiple_commands(["echo ok", "ls /nonexistent/path", "echo ok2"])
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0]["success"])
        self.assertFalse(results[1]["success"])
        self.assertTrue(results[2]["success"])

    def test_an_empty_list_gives_an_empty_result(self):
        self.assertEqual(execute_multiple_commands([]), [])


class TestParseCommandOutput(unittest.TestCase):
    def test_parse_output(self):
        output = "line1\nline2\nline3"
        result = parse_command_output(output)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["first_line"], "line1")
        self.assertEqual(result["last_line"], "line3")
        self.assertEqual(len(result["lines"]), 3)

    def test_empty_output(self):
        result = parse_command_output("")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["lines"], [])

    # -- the shape of the answer -------------------------------------------

    def test_the_empty_answer_carries_the_same_keys(self):
        """The empty answer has the same shape as a populated one."""
        result = parse_command_output("")
        self.assertEqual(
            sorted(result), ["count", "first_line", "last_line", "lines"]
        )

    def test_a_single_line_is_its_own_first_and_last_line(self):
        result = parse_command_output("only")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["first_line"], "only")
        self.assertEqual(result["last_line"], "only")

    def test_the_output_is_stripped_before_it_is_split(self):
        """A trailing newline does not produce an empty last line."""
        result = parse_command_output("line1\nline2\n")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["last_line"], "line2")


class TestGetSystemInfo(unittest.TestCase):
    def test_returns_dict(self):
        result = get_system_info()
        self.assertIsInstance(result, dict)

    def test_has_os_info(self):
        result = get_system_info()
        self.assertIn("os_info", result)

    # -- the shape of the answer -------------------------------------------

    def test_it_reports_the_four_families(self):
        """The four families the toolkit promises are all present."""
        result = get_system_info()
        for key in ("os_info", "cpu_info", "memory_info", "disk_usage"):
            self.assertIn(key, result)

    def test_the_values_are_the_output_of_the_commands(self):
        """The values are the raw output of the shell commands."""
        result = get_system_info()
        self.assertIn("Linux", result["os_info"])

    def test_a_failing_command_leaves_its_key_out(self):
        """A family whose command failed is simply absent.

        The operation reports what it could gather; it does not invent a
        key and it does not raise.
        """
        # ``uname`` is what fills "os_info".  If it cannot be run, the
        # key is missing rather than empty.
        import toolkits.linux_toolkit.operations as operations

        original = operations.execute_shell_command
        operations.execute_shell_command = lambda *a, **k: {
            "stdout": "",
            "stderr": "boom",
            "returncode": 1,
            "success": False,
        }
        try:
            result = operations.get_system_info()
        finally:
            operations.execute_shell_command = original

        self.assertEqual(result, {})
        self.assertNotIn("os_info", result)


class TestCheckFilePermissions(unittest.TestCase):
    def test_existing_file(self):
        result = check_file_permissions("/etc/passwd")
        self.assertTrue(result["success"])
        self.assertIn("permissions", result)

    def test_nonexistent_file(self):
        result = check_file_permissions("/nonexistent/file")
        self.assertFalse(result["success"])

    # -- the shape of the answer -------------------------------------------

    def test_it_reports_the_permissions_the_owner_and_the_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "file.txt")
            with open(path, "w") as handle:
                handle.write("x")

            result = check_file_permissions(path)
            self.assertTrue(result["success"])
            self.assertRegex(result["permissions"], r"^-rw")
            self.assertTrue(result["owner"])
            self.assertTrue(result["group"])

    def test_a_missing_file_carries_the_error(self):
        result = check_file_permissions("/nonexistent/file")
        self.assertFalse(result["success"])
        self.assertEqual(result["permissions"], "")
        self.assertEqual(result["owner"], "")
        self.assertEqual(result["group"], "")
        self.assertIn("error", result)


class TestRunCommandWithEnv(unittest.TestCase):
    def test_the_environment_variable_reaches_the_command(self):
        result = run_command_with_env("echo $MY_VAR", {"MY_VAR": "hello"})
        self.assertTrue(result["success"])
        self.assertEqual(result["stdout"], "hello")

    # -- the error contract ------------------------------------------------

    def test_the_parent_environment_is_inherited(self):
        """The custom variables are *added* to the environment."""
        result = run_command_with_env("echo $PATH", {"MY_VAR": "x"})
        self.assertTrue(result["success"])
        self.assertNotEqual(result["stdout"], "")

    def test_a_failing_command_is_reported_and_never_raises(self):
        result = run_command_with_env("ls /nonexistent/path", {})
        self.assertFalse(result["success"])
        self.assertNotEqual(result["returncode"], 0)
        self.assertNotEqual(result["stderr"], "")

    def test_the_answer_has_the_same_shape_as_the_other_operations(self):
        """The same four keys as ``execute_shell_command``."""
        result = run_command_with_env("echo hi", {})
        self.assertEqual(
            sorted(result), ["returncode", "stderr", "stdout", "success"]
        )

    def test_a_timeout_is_reported_with_returncode_minus_one(self):
        """A timeout is caught and reported, never raised.

        ``run_command_with_env`` has no timeout parameter - it always
        gives the command 30 seconds - so the timeout path is exercised
        by making the call itself time out.  The 30 seconds are not
        spent: the wait is what is replaced, not the whole operation.
        """
        import subprocess
        import unittest.mock as mock

        with mock.patch(
            "toolkits.linux_toolkit.operations.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="sleep 60", timeout=30),
        ):
            result = run_command_with_env("sleep 60", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertNotEqual(result["stderr"], "")

    def test_the_timeout_is_hardcoded_to_thirty_seconds(self):
        """The operation always allows 30 seconds - it has no knob.

        That is the behaviour the toolkit has always had, so it is pinned
        here rather than left to be discovered.
        """
        import unittest.mock as mock

        with mock.patch(
            "toolkits.linux_toolkit.operations.subprocess.run"
        ) as run:
            run.return_value = mock.Mock(
                stdout="", stderr="", returncode=0
            )
            run_command_with_env("echo hi", {})

        self.assertEqual(run.call_args.kwargs["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
