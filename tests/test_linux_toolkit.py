"""
Unit tests for agent_linux_toolkit.

Tests shell command execution and system operations including:
- execute_shell_command, execute_multiple_commands
- parse_command_output, get_system_info, check_file_permissions
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_linux_toolkit import (
    execute_shell_command,
    execute_multiple_commands,
    parse_command_output,
    get_system_info,
    check_file_permissions,
)


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


class TestGetSystemInfo(unittest.TestCase):
    def test_returns_dict(self):
        result = get_system_info()
        self.assertIsInstance(result, dict)

    def test_has_os_info(self):
        result = get_system_info()
        self.assertIn("os_info", result)


class TestCheckFilePermissions(unittest.TestCase):
    def test_existing_file(self):
        result = check_file_permissions("/etc/passwd")
        self.assertTrue(result["success"])
        self.assertIn("permissions", result)

    def test_nonexistent_file(self):
        result = check_file_permissions("/nonexistent/file")
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
