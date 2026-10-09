"""
Action Executor - Execute configured project actions.

Provides safe execution of project actions (build, test, run, clean) with
timeout support, output capture, and error handling.

Category: Project Management
"""

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of executing a project action."""

    action_name: str
    project_name: str
    command: str
    success: bool
    return_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action_name": self.action_name,
            "project_name": self.project_name,
            "command": self.command,
            "success": self.success,
            "return_code": self.return_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": round(self.duration_ms, 2),
            "timed_out": self.timed_out,
        }


class ActionExecutor:
    """
    Executes configured project actions with safety features.

    Args:
        default_timeout: Default timeout in seconds for action execution (default: 120)
        capture_output: Whether to capture stdout/stderr (default: True)
    """

    def __init__(
        self,
        default_timeout: int = 120,
        capture_output: bool = True,
    ):
        self.default_timeout = default_timeout
        self.capture_output = capture_output

    def execute(
        self,
        project_name: str,
        action_name: str,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> ActionResult:
        """
        Execute a project action command.

        Args:
            project_name: Name of the project
            action_name: Name of the action (e.g., 'build', 'test')
            command: Shell command to execute
            cwd: Working directory for the command (default: project directory)
            timeout: Timeout in seconds (default: self.default_timeout)
            env: Additional environment variables

        Returns:
            ActionResult with execution details

        Raises:
            ValueError: If command is empty
            FileNotFoundError: If cwd doesn't exist
        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")

        if cwd and not Path(cwd).is_dir():
            raise FileNotFoundError(f"Working directory not found: {cwd}")

        effective_timeout = timeout or self.default_timeout

        logger.info(
            f"Executing action '{action_name}' for project '{project_name}': "
            f"{command} (timeout: {effective_timeout}s)"
        )

        start_time = time.monotonic()
        timed_out = False

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=self.capture_output,
                text=True,
                timeout=effective_timeout,
                env={**dict(__import__("os").environ), **(env or {})},
            )

            duration_ms = (time.monotonic() - start_time) * 1000

            return ActionResult(
                action_name=action_name,
                project_name=project_name,
                command=command,
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
                timed_out=False,
            )

        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - start_time) * 1000
            timed_out = True

            logger.warning(
                f"Action '{action_name}' timed out after {effective_timeout}s"
            )

            return ActionResult(
                action_name=action_name,
                project_name=project_name,
                command=command,
                success=False,
                return_code=-1,
                stdout="",
                stderr=f"Command timed out after {effective_timeout}s",
                duration_ms=duration_ms,
                timed_out=True,
            )

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(f"Action '{action_name}' failed: {e}")

            return ActionResult(
                action_name=action_name,
                project_name=project_name,
                command=command,
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                timed_out=False,
            )

    def dry_run(
        self,
        project_name: str,
        action_name: str,
        command: str,
        cwd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Preview an action without executing it.

        Args:
            project_name: Name of the project
            action_name: Name of the action
            command: Shell command to preview
            cwd: Working directory

        Returns:
            Dictionary with action preview information
        """
        return {
            "action_name": action_name,
            "project_name": project_name,
            "command": command,
            "cwd": cwd or "current directory",
            "status": "preview",
            "message": "This is a dry run. No command was executed.",
        }
