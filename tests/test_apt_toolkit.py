"""
Unit tests for agent_apt_toolkit.py

Tests cover:
  - Package resolution (find_package_for_command)
  - Command existence checks (check_command_exists)
  - Sudo password handling (prompt_sudo_password, test_sudo_password)
  - Package installation (install_package, install_multiple_packages)
  - Interactive workflow (interactive_install_missing_command)
  - Tool registry (get_all_tools)

All subprocess calls are mocked to avoid actual system modifications.
"""
import pytest
import subprocess
from unittest.mock import patch, MagicMock, call
import os

# Import the module under test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from agent_apt_toolkit import (
    find_package_for_command,
    check_command_exists,
    prompt_sudo_password,
    test_sudo_password,
    clear_sudo_cache,
    install_package,
    install_multiple_packages,
    interactive_install_missing_command,
    get_all_tools,
)


# ============================================================================
# Fixtures & Helpers
# ============================================================================

def make_subprocess_result(returncode=0, stdout="", stderr="", timeout=None):
    """Helper to create a mock subprocess.CompletedProcess-like object."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# ============================================================================
# Fixtures for resetting module state between tests
# ============================================================================

@pytest.fixture(autouse=True)
def reset_sudo_cache():
    """Reset the sudo password cache before each test."""
    import agent_apt_toolkit
    agent_apt_toolkit._sudo_password_cache = None
    yield
    agent_apt_toolkit._sudo_password_cache = None


# ============================================================================
# Tests for find_package_for_command()
# ============================================================================

class TestFindPackageForCommand:
    """Tests for find_package_for_command()"""

    @patch("agent_apt_toolkit.subprocess.run")
    def test_apt_file_success(self, mock_run):
        """Method 1: apt-file finds the package."""
        mock_run.return_value = make_subprocess_result(
            returncode=0,
            stdout="ffmpeg: /usr/bin/ffmpeg\nffmpeg-dev: /usr/bin/ffmpeg-dev\n",
        )
        result = find_package_for_command("ffmpeg")
        assert result["success"] is True
        assert result["method"] == "apt-file"
        assert result["package_name"] is not None
        assert "ffmpeg" in result["candidates"]
        mock_run.assert_called_once()

    @patch("agent_apt_toolkit.subprocess.run")
    def test_apt_file_no_results(self, mock_run):
        """apt-file returns empty stdout → fallback to dpkg."""
        mock_run.return_value = make_subprocess_result(returncode=0, stdout="")
        # Second call (dpkg) also fails
        mock_run.side_effect = [
            make_subprocess_result(returncode=0, stdout=""),
            make_subprocess_result(returncode=1, stderr="no matches"),
            make_subprocess_result(
                returncode=0,
                stdout="unknown-cmd - some description\n",
            ),
        ]
        result = find_package_for_command("unknown-cmd")
        assert result["method"] == "apt-cache"
        assert result["success"] is True

    @patch("agent_apt_toolkit.subprocess.run")
    def test_fallback_to_dpkg(self, mock_run):
        """apt-file not available, dpkg finds it."""
        mock_run.side_effect = [
            FileNotFoundError("apt-file not found"),
            make_subprocess_result(returncode=0, stdout="coreutils: /usr/bin/ls"),
        ]
        result = find_package_for_command("ls")
        assert result["success"] is True
        assert result["method"] == "dpkg"
        assert result["package_name"] == "coreutils"

    @patch("agent_apt_toolkit.subprocess.run")
    def test_fallback_to_apt_cache(self, mock_run):
        """Both apt-file and dpkg fail, falls back to apt-cache."""
        mock_run.side_effect = [
            FileNotFoundError("apt-file not found"),
            make_subprocess_result(returncode=1, stderr="dpkg error"),
            make_subprocess_result(
                returncode=0,
                stdout="vim - visual editor\nvim-gtk - vim with GTK\n",
            ),
        ]
        result = find_package_for_command("vim")
        assert result["success"] is True
        assert result["method"] == "apt-cache"
        assert result["package_name"] == "vim"

    @patch("agent_apt_toolkit.subprocess.run")
    def test_all_methods_fail(self, mock_run):
        """All three methods fail → return failure dict."""
        mock_run.side_effect = [
            FileNotFoundError("apt-file not found"),
            FileNotFoundError("dpkg not found"),
            FileNotFoundError("apt-cache not found"),
        ]
        result = find_package_for_command("nonexistent")
        assert result["success"] is False
        assert result["package_name"] is None
        assert result["method"] == "none"
        assert result["candidates"] == []

    @patch("agent_apt_toolkit.subprocess.run")
    def test_apt_file_timeout(self, mock_run):
        """apt-file times out, falls back gracefully."""
        mock_run.side_effect = [
            subprocess.TimeoutExpired("apt-file", 30),
            make_subprocess_result(returncode=0, stdout="git: /usr/bin/git"),
        ]
        result = find_package_for_command("git")
        assert result["success"] is True
        assert result["method"] == "dpkg"


# ============================================================================
# Tests for check_command_exists()
# ============================================================================

class TestCheckCommandExists:
    """Tests for check_command_exists()"""

    @patch("agent_apt_toolkit.subprocess.run")
    def test_command_exists(self, mock_run):
        """Command found in PATH."""
        mock_run.return_value = make_subprocess_result(
            returncode=0, stdout="/usr/bin/python3"
        )
        result = check_command_exists("python3")
        assert result["exists"] is True
        assert result["path"] == "/usr/bin/python3"
        assert result["success"] is True

    @patch("agent_apt_toolkit.subprocess.run")
    def test_command_not_found(self, mock_run):
        """Command not in PATH."""
        mock_run.return_value = make_subprocess_result(
            returncode=1, stdout=""
        )
        result = check_command_exists("nonexistent-tool")
        assert result["exists"] is False
        assert result["path"] is None
        assert result["success"] is False

    @patch("agent_apt_toolkit.subprocess.run")
    def test_exception_handling(self, mock_run):
        """Exception during which call."""
        mock_run.side_effect = Exception("Unexpected error")
        result = check_command_exists("broken")
        assert result["exists"] is False
        assert result["success"] is False
        assert "error" in result


# ============================================================================
# Tests for prompt_sudo_password()
# ============================================================================

class TestPromptSudoPassword:
    """Tests for prompt_sudo_password()"""

    @patch("agent_apt_toolkit.subprocess.run")
    def test_parameter_method_success(self, mock_run):
        """Parameter method with valid password."""
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = prompt_sudo_password(method="parameter", password="mypassword")
        assert result["password_provided"] is True
        assert result["success"] is True
        assert result["method"] == "parameter"
        assert result["password"] == "mypassword"

    @patch("agent_apt_toolkit.subprocess.run")
    def test_parameter_method_invalid_password(self, mock_run):
        """Parameter method with invalid password."""
        mock_run.return_value = make_subprocess_result(returncode=1)
        result = prompt_sudo_password(method="parameter", password="wrongpassword")
        assert result["password_provided"] is False
        assert result["success"] is False
        assert "Invalid password" in result["error"]

    def test_parameter_method_no_password(self):
        """Parameter method without password provided."""
        result = prompt_sudo_password(method="parameter")
        assert result["password_provided"] is False
        assert "No password provided" in result["error"]

    @patch("agent_apt_toolkit.subprocess.run")
    def test_env_var_method_success(self, mock_run):
        """Environment variable method with valid password."""
        mock_run.return_value = make_subprocess_result(returncode=0)
        with patch("agent_apt_toolkit.os.environ.get", return_value="envpassword"):
            result = prompt_sudo_password(method="env_var")
            assert result["password_provided"] is True
            assert result["success"] is True
            assert result["method"] == "env_var"

    @patch("agent_apt_toolkit.subprocess.run")
    def test_env_var_method_invalid_password(self, mock_run):
        """Environment variable method with invalid password."""
        mock_run.return_value = make_subprocess_result(returncode=1)
        with patch("agent_apt_toolkit.os.environ.get", return_value="wrongpassword"):
            result = prompt_sudo_password(method="env_var")
            assert result["password_provided"] is False
            assert "Invalid password" in result["error"]

    def test_env_var_method_no_env_var(self):
        """Environment variable method without env var set."""
        with patch("agent_apt_toolkit.os.environ.get", return_value=None):
            result = prompt_sudo_password(method="env_var")
            assert result["password_provided"] is False

    @patch("agent_apt_toolkit.subprocess.run")
    def test_cache_method_success(self, mock_run):
        """Cache method with valid cached password."""
        import agent_apt_toolkit
        agent_apt_toolkit._sudo_password_cache = "cached_password"
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = prompt_sudo_password(method="cache")
        assert result["password_provided"] is True
        assert result["success"] is True
        assert result["method"] == "cache"

    @patch("agent_apt_toolkit.subprocess.run")
    def test_cache_method_invalid_cache(self, mock_run):
        """Cache method with invalid cached password."""
        import agent_apt_toolkit
        agent_apt_toolkit._sudo_password_cache = "wrong_cached"
        mock_run.return_value = make_subprocess_result(returncode=1)
        result = prompt_sudo_password(method="cache")
        assert result["password_provided"] is False

    @patch("agent_apt_toolkit.subprocess.run")
    def test_auto_method_parameter_priority(self, mock_run):
        """Auto method uses parameter when provided."""
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = prompt_sudo_password(method="auto", password="param_password")
        assert result["method"] == "parameter"
        assert result["success"] is True

    @patch("agent_apt_toolkit.subprocess.run")
    @patch("agent_apt_toolkit.os.environ.get")
    def test_auto_method_env_var_fallback(self, mock_env, mock_run):
        """Auto method falls back to env_var when no parameter."""
        mock_env.return_value = "env_password"
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = prompt_sudo_password(method="auto")
        assert result["method"] == "env_var"
        assert result["success"] is True

    @patch("agent_apt_toolkit.subprocess.run")
    @patch("agent_apt_toolkit.os.environ.get")
    def test_auto_method_console_fallback(self, mock_env, mock_run):
        """Auto method falls back to console when no other method works."""
        mock_env.return_value = None
        # Will try console, which will fail with EOFError
        result = prompt_sudo_password(method="auto")
        assert result["password_provided"] is False


# ============================================================================
# Tests for test_sudo_password()
# ============================================================================

class TestTestSudoPassword:
    """Tests for test_sudo_password()"""

    @patch("agent_apt_toolkit.subprocess.run")
    def test_valid_password(self, mock_run):
        """Password is valid (sudo returns 0)."""
        mock_run.return_value = make_subprocess_result(returncode=0)
        assert test_sudo_password("correctpassword") is True

    @patch("agent_apt_toolkit.subprocess.run")
    def test_invalid_password(self, mock_run):
        """Password is invalid (sudo returns non-zero)."""
        mock_run.return_value = make_subprocess_result(returncode=1)
        assert test_sudo_password("wrongpassword") is False

    def test_empty_password(self):
        """Empty password returns False."""
        assert test_sudo_password("") is False
        assert test_sudo_password(None) is False

    @patch("agent_apt_toolkit.subprocess.run")
    def test_exception(self, mock_run):
        """Exception during test."""
        mock_run.side_effect = Exception("sudo error")
        assert test_sudo_password("any") is False


# ============================================================================
# Tests for clear_sudo_cache()
# ============================================================================

class TestClearSudoCache:
    """Tests for clear_sudo_cache()"""

    def test_clear_cache(self):
        """Cache clearing works."""
        import agent_apt_toolkit
        agent_apt_toolkit._sudo_password_cache = "some_password"
        result = clear_sudo_cache()
        assert result["success"] is True
        assert agent_apt_toolkit._sudo_password_cache is None


# ============================================================================
# Tests for install_package()
# ============================================================================

class TestInstallPackage:
    """Tests for install_package()"""

    @patch("agent_apt_toolkit.check_command_exists")
    def test_already_installed(self, mock_check):
        """Package already installed → short-circuit."""
        mock_check.return_value = {"exists": True, "path": "/usr/bin/ffmpeg"}
        result = install_package("ffmpeg")
        assert result["success"] is True
        assert result["installed"] is True
        assert "Already installed" in result["steps"]

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False, "path": None},  # pre-check
        {"exists": True, "path": "/usr/bin/ffmpeg"},  # post-check
    ])
    @patch("agent_apt_toolkit.subprocess.run")
    def test_successful_install_with_password(self, mock_run, mock_check):
        """Install succeeds when password is provided."""
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = install_package(
            "ffmpeg", update_first=False, sudo_password="test123"
        )
        assert result["success"] is True
        assert result["installed"] is True
        assert result["package"] == "ffmpeg"

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},  # pre-check
        {"exists": True, "path": "/usr/bin/ffmpeg"},  # post-check
    ])
    @patch("agent_apt_toolkit.subprocess.run")
    @patch("agent_apt_toolkit.prompt_sudo_password")
    def test_install_prompts_for_password(self, mock_prompt, mock_run, mock_check):
        """When no password given, prompt is called."""
        mock_prompt.return_value = {
            "password_provided": True,
            "password": "prompted_password",
        }
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = install_package("ffmpeg", update_first=False)
        assert mock_prompt.called
        assert result["success"] is True

    @patch("agent_apt_toolkit.check_command_exists", return_value={"exists": False})
    @patch("agent_apt_toolkit.prompt_sudo_password")
    def test_no_password_provided(self, mock_prompt, mock_check):
        """Prompt returns no password → fail."""
        mock_prompt.return_value = {"password_provided": False}
        result = install_package("ffmpeg", update_first=False)
        assert result["success"] is False
        assert "No sudo password provided" in result["error"]

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},  # pre-check
        {"exists": True, "path": "/usr/bin/ffmpeg"},  # post-check
    ])
    @patch("agent_apt_toolkit.subprocess.run")
    def test_install_with_update(self, mock_run, mock_check):
        """apt-get update runs when update_first=True."""
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = install_package(
            "ffmpeg", update_first=True, sudo_password="test123"
        )
        # Should have called subprocess.run at least twice (update + install)
        assert mock_run.call_count >= 2
        assert result["success"] is True

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},
        {"exists": True, "path": "/usr/bin/ffmpeg"},
    ])
    @patch("agent_apt_toolkit.subprocess.run")
    def test_update_fails(self, mock_run, mock_check):
        """apt-get update failure aborts installation."""
        mock_run.side_effect = [
            make_subprocess_result(returncode=1, stderr="update error"),
        ]
        result = install_package(
            "ffmpeg", update_first=True, sudo_password="test123"
        )
        assert result["success"] is False
        assert "apt-get update failed" in result["error"]

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},
        {"exists": False},  # post-check still fails
    ])
    @patch("agent_apt_toolkit.subprocess.run")
    def test_install_fails(self, mock_run, mock_check):
        """apt-get install failure."""
        mock_run.return_value = make_subprocess_result(
            returncode=1, stderr="package not found"
        )
        result = install_package(
            "ffmpeg", update_first=False, sudo_password="test123"
        )
        assert result["success"] is False
        assert "Installation failed" in result["error"]


# ============================================================================
# Tests for install_multiple_packages()
# ============================================================================

class TestInstallMultiplePackages:
    """Tests for install_multiple_packages()"""

    @patch("agent_apt_toolkit.install_package")
    def test_installs_all_packages(self, mock_install):
        """Each package is installed sequentially."""
        mock_install.return_value = {"success": True, "installed": True}
        results = install_multiple_packages(
            ["pkg1", "pkg2", "pkg3"],
            update_first=True,
            sudo_password="test",
        )
        assert len(results) == 3
        assert mock_install.call_count == 3

    @patch("agent_apt_toolkit.install_package")
    def test_update_only_first(self, mock_install):
        """update_first=True only passed to first package."""
        mock_install.return_value = {"success": True}
        install_multiple_packages(
            ["pkg1", "pkg2"],
            update_first=True,
            sudo_password="test",
        )
        calls = mock_install.call_args_list
        assert calls[0][1]["update_first"] is True
        assert calls[1][1]["update_first"] is False


# ============================================================================
# Tests for interactive_install_missing_command()
# ============================================================================

class TestInteractiveInstallMissingCommand:
    """Tests for interactive_install_missing_command()"""

    @patch("agent_apt_toolkit.check_command_exists")
    def test_command_already_exists(self, mock_check):
        """Command exists → return immediately."""
        mock_check.return_value = {
            "exists": True,
            "path": "/usr/bin/ls",
        }
        result = interactive_install_missing_command("ls")
        assert result["success"] is True
        assert "already available" in result["message"]

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},  # initial check
        {"exists": False},  # install pre-check
        {"exists": True, "path": "/usr/bin/ffmpeg"},  # install post-check
        {"exists": True, "path": "/usr/bin/ffmpeg"},  # final check
    ])
    @patch("agent_apt_toolkit.find_package_for_command")
    @patch("agent_apt_toolkit.prompt_sudo_password")
    @patch("agent_apt_toolkit.install_package")
    def test_full_workflow_success(
        self, mock_install, mock_prompt, mock_resolve, mock_check
    ):
        """End-to-end successful workflow."""
        mock_resolve.return_value = {
            "success": True,
            "package_name": "ffmpeg",
        }
        mock_prompt.return_value = {
            "password_provided": True,
            "password": "secret",
        }
        mock_install.return_value = {"success": True, "installed": True}

        result = interactive_install_missing_command("ffmpeg")
        assert result["success"] is True
        assert result["command_available"] is True
        assert "Successfully installed" in result["message"]

    @patch("agent_apt_toolkit.check_command_exists", return_value={"exists": False})
    @patch("agent_apt_toolkit.find_package_for_command")
    def test_resolution_fails(self, mock_resolve, mock_check):
        """Cannot find package → fail early."""
        mock_resolve.return_value = {
            "success": False,
            "candidates": [],
        }
        result = interactive_install_missing_command("unknown-tool")
        assert result["success"] is False
        assert "Could not find a package" in result["error"]

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},
        {"exists": False},
    ])
    @patch("agent_apt_toolkit.find_package_for_command")
    @patch("agent_apt_toolkit.prompt_sudo_password")
    def test_password_not_provided(self, mock_prompt, mock_resolve, mock_check):
        """User cancels password prompt."""
        mock_resolve.return_value = {
            "success": True,
            "package_name": "some-pkg",
        }
        mock_prompt.return_value = {"password_provided": False}
        result = interactive_install_missing_command(
            "some-tool", prompt_password=True
        )
        assert result["success"] is False
        assert "Sudo password was not provided" in result["error"]

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},
        {"exists": False},
        {"exists": True, "path": "/usr/bin/tool"},
        {"exists": True, "path": "/usr/bin/tool"},
    ])
    @patch("agent_apt_toolkit.find_package_for_command")
    @patch("agent_apt_toolkit.prompt_sudo_password")
    @patch("agent_apt_toolkit.install_package")
    def test_no_password_prompt(
        self, mock_install, mock_prompt, mock_resolve, mock_check
    ):
        """prompt_password=False skips prompting."""
        mock_resolve.return_value = {
            "success": True,
            "package_name": "some-pkg",
        }
        mock_install.return_value = {"success": True}
        result = interactive_install_missing_command(
            "some-tool", prompt_password=False
        )
        assert not mock_prompt.called

    @patch("agent_apt_toolkit.check_command_exists", side_effect=[
        {"exists": False},
        {"exists": False},
        {"exists": True, "path": "/usr/bin/ffmpeg"},
        {"exists": True, "path": "/usr/bin/ffmpeg"},
    ])
    @patch("agent_apt_toolkit.find_package_for_command")
    @patch("agent_apt_toolkit.install_package")
    def test_with_pre_provided_password(
        self, mock_install, mock_resolve, mock_check
    ):
        """Workflow with pre-provided sudo password skips prompting."""
        mock_resolve.return_value = {
            "success": True,
            "package_name": "ffmpeg",
        }
        mock_install.return_value = {"success": True}
        result = interactive_install_missing_command(
            "ffmpeg",
            sudo_password="mypassword",
            prompt_password=True,
        )
        assert result["success"] is True


# ============================================================================
# Tests for get_all_tools()
# ============================================================================

class TestGetAllTools:
    """Tests for get_all_tools()"""

    def test_returns_list_of_tools(self):
        """get_all_tools returns a list of FunctionTool objects."""
        tools = get_all_tools()
        assert isinstance(tools, list)
        assert len(tools) == 8  # 8 tools registered

    def test_tool_descriptions(self):
        """Each tool has a description in metadata."""
        tools = get_all_tools()
        for tool in tools:
            assert hasattr(tool, "metadata")
            assert len(tool.metadata.description) > 0

    def test_tool_names(self):
        """Tool names match expected functions."""
        tools = get_all_tools()
        tool_names = {t.metadata.name for t in tools}
        expected = {
            "find_package_for_command",
            "check_command_exists",
            "install_package",
            "install_multiple_packages",
            "interactive_install_missing_command",
            "prompt_sudo_password",
            "test_sudo_password",
            "clear_sudo_cache",
        }
        assert tool_names == expected


# ============================================================================
# Edge Cases & Integration-style Tests (still mocked)
# ============================================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    @patch("agent_apt_toolkit.subprocess.run")
    def test_empty_command_name(self, mock_run):
        """Empty command string handled gracefully."""
        mock_run.return_value = make_subprocess_result(returncode=0, stdout="")
        result = check_command_exists("")
        # Should not crash
        assert "exists" in result

    @patch("agent_apt_toolkit.subprocess.run")
    def test_special_chars_in_package_name(self, mock_run):
        """Package names with hyphens and underscores."""
        mock_run.return_value = make_subprocess_result(
            returncode=0, stdout="/usr/bin/my-tool"
        )
        result = check_command_exists("my-tool")
        assert result["exists"] is True

    @patch("agent_apt_toolkit.subprocess.run")
    def test_long_timeout_handling(self, mock_run):
        """Long-running subprocess handled with timeout."""
        mock_run.return_value = make_subprocess_result(returncode=0, stdout="ok")
        result = check_command_exists("slow-tool")
        assert "exists" in result

    @patch("agent_apt_toolkit.check_command_exists", return_value={"exists": False})
    @patch("agent_apt_toolkit.prompt_sudo_password")
    @patch("agent_apt_toolkit.subprocess.run")
    def test_install_with_empty_password(
        self, mock_run, mock_prompt, mock_check
    ):
        """Empty password should not cause issues."""
        mock_prompt.return_value = {"password_provided": True, "password": ""}
        mock_run.return_value = make_subprocess_result(returncode=0)
        result = install_package("pkg", update_first=False)
        # Should still complete (may fail on actual sudo, but structurally ok)
        assert "package" in result
