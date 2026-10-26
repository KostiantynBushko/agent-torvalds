"""
Unit tests for the Windows PowerShell toolkit's library half.

Tests the PowerShell command execution and the system operations:
- execute_shell_command, execute_multiple_commands
- parse_command_output, get_system_info, check_file_permissions
- run_command_with_env
- the private _get_powershell_command helper

The toolkit used to be a single module at the project root,
``agent_windows_toolkit.py``, and it carried **no** test suite at all.
This one came with the move.

The suite is **platform-independent**: it drives the operations through a
stubbed ``subprocess.run``, so it needs neither Windows nor a PowerShell
installation.  That matters, because the build that has to stay green
runs on Linux - and a suite that could only run on Windows would never
guard anything.
"""

import contextlib
import json
import subprocess
import unittest
import unittest.mock as mock

from .. import operations
from ..operations import (
    check_file_permissions,
    execute_multiple_commands,
    execute_shell_command,
    get_system_info,
    parse_command_output,
    run_command_with_env,
)


#: A finished process, as ``subprocess.run`` would return one.
def _process(stdout="", stderr="", returncode=0):
    """A stand-in for the result of ``subprocess.run``."""
    return mock.Mock(stdout=stdout, stderr=stderr, returncode=returncode)


@contextlib.contextmanager
def _stubbed_powershell(stdout="", stderr="", returncode=0):
    """Stub the PowerShell execution.

    Two things are stubbed: the helper that picks the PowerShell
    executable, and the ``subprocess.run`` that carries the command out.
    The helper is stubbed as well, because it runs ``where pwsh`` - a
    command that only exists on Windows.
    """
    with mock.patch.object(
        operations, "_get_powershell_command", return_value="pwsh"
    ), mock.patch.object(operations.subprocess, "run") as run:
        run.return_value = _process(stdout, stderr, returncode)
        yield run


class TestGetPowershellCommand(unittest.TestCase):
    """The private helper that picks the PowerShell executable."""

    def test_it_prefers_powershell_core(self):
        """``pwsh`` is tried first."""
        with mock.patch.object(operations.subprocess, "run") as run:
            run.return_value = _process(stdout="C:\\Program Files\\PowerShell\\pwsh.exe\n")
            self.assertEqual(operations._get_powershell_command(), "pwsh")

    def test_it_falls_back_to_windows_powershell(self):
        """``powershell.exe`` is the fallback."""
        with mock.patch.object(operations.subprocess, "run") as run:
            run.return_value = _process(returncode=1)
            self.assertEqual(operations._get_powershell_command(), "powershell.exe")

    def test_an_empty_answer_also_falls_back(self):
        """A found-but-empty answer is not an answer."""
        with mock.patch.object(operations.subprocess, "run") as run:
            run.return_value = _process(stdout="   \n", returncode=0)
            self.assertEqual(operations._get_powershell_command(), "powershell.exe")

    def test_an_exception_falls_back_too(self):
        """``where`` is missing on some systems - that must not raise."""
        with mock.patch.object(
            operations.subprocess, "run", side_effect=OSError("no where here")
        ):
            self.assertEqual(operations._get_powershell_command(), "powershell.exe")


class TestExecuteShellCommand(unittest.TestCase):
    def test_successful_command(self):
        with _stubbed_powershell(stdout="hello"):
            result = execute_shell_command("Get-Date")
        self.assertTrue(result["success"])
        self.assertEqual(result["stdout"], "hello")
        self.assertEqual(result["returncode"], 0)

    def test_failed_command(self):
        with _stubbed_powershell(stderr="boom", returncode=1):
            result = execute_shell_command("Get-Item /nonexistent")
        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], 1)
        self.assertEqual(result["stderr"], "boom")

    def test_returns_dict(self):
        with _stubbed_powershell():
            result = execute_shell_command("Get-Date")
        self.assertIsInstance(result, dict)
        for key in ("stdout", "stderr", "returncode", "success"):
            self.assertIn(key, result)

    # -- the shape of the command ------------------------------------------

    def test_the_command_is_wrapped_for_powershell(self):
        """The command is handed to the PowerShell executable, not to a shell."""
        with _stubbed_powershell() as run:
            execute_shell_command("Get-Process")

        command = run.call_args.args[0]
        self.assertIn("pwsh", command)
        self.assertIn("-NoProfile", command)
        self.assertIn("-NonInteractive", command)
        self.assertIn("Get-Process", command)

    def test_the_working_directory_is_honoured(self):
        with _stubbed_powershell() as run:
            execute_shell_command("Get-Location", cwd="C:\\Windows")
        self.assertEqual(run.call_args.kwargs["cwd"], "C:\\Windows")

    def test_a_command_can_run_without_a_shell(self):
        with _stubbed_powershell() as run:
            execute_shell_command("Get-Date", shell=False)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_the_timeout_is_honoured(self):
        with _stubbed_powershell() as run:
            execute_shell_command("Get-Date", timeout=90)
        self.assertEqual(run.call_args.kwargs["timeout"], 90)

    # -- the error contract ------------------------------------------------

    def test_a_failing_command_reports_the_error_and_never_raises(self):
        """A failure is *reported*, not raised.

        This is the contract the whole toolkit has: the agent gets a
        structured answer it can reason about, and the process never dies
        because a command exited non-zero.
        """
        with _stubbed_powershell(stderr="boom", returncode=1):
            result = execute_shell_command("Get-Item /nonexistent")
        self.assertFalse(result["success"])
        self.assertEqual(result["stdout"], "")
        self.assertNotEqual(result["stderr"], "")
        self.assertIsInstance(result["returncode"], int)

    def test_a_timeout_is_reported_with_returncode_minus_one(self):
        """A timeout is a reported failure, not an exception."""
        with mock.patch.object(
            operations, "_get_powershell_command", return_value="pwsh"
        ), mock.patch.object(
            operations.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="sleep", timeout=1),
        ):
            result = execute_shell_command("Start-Sleep 60", timeout=1)

        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertEqual(result["stdout"], "")
        self.assertIn("timed out", result["stderr"])

    def test_the_timeout_message_names_the_command(self):
        with mock.patch.object(
            operations, "_get_powershell_command", return_value="pwsh"
        ), mock.patch.object(
            operations.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="sleep", timeout=1),
        ):
            result = execute_shell_command("Start-Sleep 60", timeout=1)
        self.assertIn("Start-Sleep 60", result["stderr"])

    def test_a_missing_binary_is_reported_and_never_raises(self):
        """Without a shell, a missing binary raises - and is caught."""
        with mock.patch.object(
            operations, "_get_powershell_command", return_value="pwsh"
        ), mock.patch.object(
            operations.subprocess, "run", side_effect=OSError("no such file")
        ):
            result = execute_shell_command("nope")

        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertNotEqual(result["stderr"], "")

    # -- the shape of the answer -------------------------------------------

    def test_the_output_is_stripped(self):
        """The output is stripped, so the caller gets clean text."""
        with _stubbed_powershell(stdout="  hello  \n"):
            result = execute_shell_command("Get-Date")
        self.assertEqual(result["stdout"], "hello")

    def test_a_command_writing_to_stderr_is_captured(self):
        """The stderr is captured - but the command may still have succeeded.

        The exit code decides whether the command succeeded; stderr is
        only the text the command wrote.
        """
        with _stubbed_powershell(stdout="", stderr="oops", returncode=0):
            result = execute_shell_command("Write-Error oops")
        self.assertIn("oops", result["stderr"])
        self.assertEqual(result["stdout"], "")


class TestExecuteMultipleCommands(unittest.TestCase):
    def test_multiple_commands(self):
        with _stubbed_powershell(stdout="ok"):
            results = execute_multiple_commands(["whoami", "Get-Location", "Get-Date"])
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertTrue(result["success"])

    def test_returns_list(self):
        with _stubbed_powershell():
            results = execute_multiple_commands(["Get-Date"])
        self.assertIsInstance(results, list)

    # -- the error contract ------------------------------------------------

    def test_the_results_keep_the_order_of_the_commands(self):
        """The commands run one after another, in order."""
        with _stubbed_powershell(stdout="same"):
            results = execute_multiple_commands(["a", "b", "c"])
        self.assertEqual([r["stdout"] for r in results], ["same"] * 3)

    def test_one_failing_command_does_not_stop_the_others(self):
        """A failure is reported per command; the batch carries on."""
        with mock.patch.object(
            operations, "_get_powershell_command", return_value="pwsh"
        ), mock.patch.object(
            operations.subprocess, "run", side_effect=[_process("ok"), OSError("boom"), _process("ok2")]
        ):
            results = execute_multiple_commands(["a", "b", "c"])

        self.assertEqual(len(results), 3)
        self.assertTrue(results[0]["success"])
        self.assertFalse(results[1]["success"])
        self.assertTrue(results[2]["success"])

    def test_an_empty_list_gives_an_empty_result(self):
        self.assertEqual(execute_multiple_commands([]), [])


class TestParseCommandOutput(unittest.TestCase):
    def test_parse_output(self):
        result = parse_command_output("line1\nline2\nline3")
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
        with _stubbed_powershell(stdout="info"):
            result = get_system_info()
        self.assertIsInstance(result, dict)

    def test_has_os_info(self):
        with _stubbed_powershell(stdout="info"):
            result = get_system_info()
        self.assertIn("os_info", result)

    # -- the shape of the answer -------------------------------------------

    def test_it_reports_the_four_families(self):
        """The four families the toolkit promises are all present."""
        with _stubbed_powershell(stdout="info"):
            result = get_system_info()
        for key in ("os_info", "cpu_info", "memory_info", "disk_usage"):
            self.assertIn(key, result)

    def test_the_values_are_the_output_of_the_commands(self):
        """The values are the raw output of the PowerShell cmdlets."""
        with _stubbed_powershell(stdout="Microsoft Windows 11"):
            result = get_system_info()
        self.assertIn("Microsoft Windows 11", result["os_info"])

    def test_a_failing_command_leaves_its_key_out(self):
        """A family whose command failed is simply absent.

        The operation reports what it could gather; it does not invent a
        key and it does not raise.
        """
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
    def test_it_parses_the_json_output(self):
        """``Get-Acl`` reports JSON - the operation parses it."""
        payload = json.dumps(
            {"Owner": "NT AUTHORITY\\SYSTEM", "Access": [{"AccessControlType": "Allow"}]}
        )
        with _stubbed_powershell(stdout=payload):
            result = check_file_permissions("C:\\Windows\\System32\\config")

        self.assertTrue(result["success"])
        self.assertEqual(result["owner"], "NT AUTHORITY\\SYSTEM")
        self.assertEqual(result["access"], [{"AccessControlType": "Allow"}])

    def test_a_missing_file_carries_the_error(self):
        """A failed command is reported with the error text."""
        with _stubbed_powershell(stderr="Get-Acl: cannot find path", returncode=1):
            result = check_file_permissions("C:\\nonexistent")

        self.assertFalse(result["success"])
        self.assertEqual(result["owner"], "")
        self.assertEqual(result["access"], [])
        self.assertIn("Get-Acl", result["error"])

    # -- the error contract ------------------------------------------------

    def test_malformed_json_is_reported_and_never_raises(self):
        """The command succeeded but its output is not JSON.

        That is a failure of the *operation*, and it is reported like one:
        the raw output is kept so the agent can look at it.
        """
        with _stubbed_powershell(stdout="not json at all"):
            result = check_file_permissions("C:\\Windows")

        self.assertFalse(result["success"])
        self.assertEqual(result["owner"], "")
        self.assertEqual(result["access"], [])
        self.assertEqual(result["error"], "Failed to parse JSON output")
        self.assertEqual(result["raw_output"], "not json at all")

    def test_the_empty_answer_carries_the_same_keys(self):
        """The failure answer has the same shape as the successful one."""
        with _stubbed_powershell(stderr="boom", returncode=1):
            result = check_file_permissions("C:\\nonexistent")
        for key in ("owner", "access", "success"):
            self.assertIn(key, result)


class TestRunCommandWithEnv(unittest.TestCase):
    def test_the_environment_variable_reaches_the_command(self):
        """The variable is set as a PowerShell assignment, in the command."""
        with _stubbed_powershell() as run:
            run_command_with_env("echo $env:MY_VAR", {"MY_VAR": "hello"})

        command = run.call_args.args[0]
        self.assertIn('$env:MY_VAR="hello"', command)
        self.assertIn("echo $env:MY_VAR", command)

    def test_the_assignments_come_before_the_command(self):
        with _stubbed_powershell() as run:
            run_command_with_env("Get-Date", {"MY_VAR": "hello"})

        command = run.call_args.args[0]
        self.assertLess(command.index("$env:MY_VAR"), command.index("Get-Date"))

    def test_a_quote_in_a_value_is_escaped(self):
        """A double quote in a value is escaped for PowerShell."""
        with _stubbed_powershell() as run:
            run_command_with_env("echo x", {"MY_VAR": 'a"b'})

        command = run.call_args.args[0]
        self.assertIn('$env:MY_VAR="a`"b"', command)

    def test_several_variables_are_all_set(self):
        with _stubbed_powershell() as run:
            run_command_with_env("Get-Date", {"A": "1", "B": "2"})

        command = run.call_args.args[0]
        self.assertIn('$env:A="1"', command)
        self.assertIn('$env:B="2"', command)

    # -- the error contract ------------------------------------------------

    def test_a_failing_command_is_reported_and_never_raises(self):
        with _stubbed_powershell(stderr="boom", returncode=1):
            result = run_command_with_env("Get-Item /nonexistent", {})
        self.assertFalse(result["success"])
        self.assertNotEqual(result["returncode"], 0)
        self.assertNotEqual(result["stderr"], "")

    def test_the_answer_has_the_same_shape_as_the_other_operations(self):
        """The same four keys as ``execute_shell_command``."""
        with _stubbed_powershell():
            result = run_command_with_env("Get-Date", {})
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
        with mock.patch.object(
            operations, "_get_powershell_command", return_value="pwsh"
        ), mock.patch.object(
            operations.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="sleep", timeout=30),
        ):
            result = run_command_with_env("Start-Sleep 60", {})

        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], -1)
        self.assertNotEqual(result["stderr"], "")

    def test_the_timeout_is_hardcoded_to_thirty_seconds(self):
        """The operation always allows 30 seconds - it has no knob.

        That is the behaviour the toolkit has always had, so it is pinned
        here rather than left to be discovered.
        """
        with _stubbed_powershell() as run:
            run_command_with_env("Get-Date", {})
        self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_it_always_runs_through_a_shell(self):
        """Unlike ``execute_shell_command``, this one always uses a shell."""
        with _stubbed_powershell() as run:
            run_command_with_env("Get-Date", {})
        self.assertTrue(run.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
