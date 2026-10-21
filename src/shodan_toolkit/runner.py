"""
Subprocess runner for the Shodan command-line interface.

This module is the single point of contact with the external ``shodan`` binary.
Everything else in the toolkit goes through :class:`ShodanRunner`, which keeps
the wrapping logic testable and makes it trivial to swap the transport (e.g.
for a mocked runner in tests) without touching the tool layer.

Design notes
------------
* The runner always executes the CLI with a *non-interactive*, *non-colored*,
  *non-paging* configuration so that stdout is machine-parseable.
* ``shodan search`` and ``shodan trends`` buffer their output and print it via
  ``click.echo_via_pager``.  We neutralise the pager (``PAGER=cat``) and force
  ``--no-color`` so the captured output is stable text.
* The Shodan CLI emits a ``pkg_resources`` deprecation warning on stderr with
  recent setuptools versions; that noise is filtered out of error messages.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "CommandResult",
    "ShodanRunner",
    "ShodanError",
    "ShodanNotInstalledError",
    "ShodanAuthError",
    "ShodanCLIError",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ShodanError(Exception):
    """Base class for every error raised by the toolkit."""


class ShodanNotInstalledError(ShodanError):
    """Raised when the ``shodan`` executable cannot be found on PATH."""


class ShodanAuthError(ShodanError):
    """Raised when the API key is missing, invalid, or rejected."""


class ShodanCLIError(ShodanError):
    """Raised when the Shodan CLI exits with a non-zero status code."""

    def __init__(self, message: str, result: Optional[CommandResult] = None):
        super().__init__(message)
        self.result = result


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class CommandResult:
    """Outcome of a single CLI invocation.

    Attributes:
        command: The argument vector that was executed.
        returncode: Process exit status.
        stdout: Raw standard output.
        stderr: Raw standard error.
        duration_ms: Wall-clock duration of the call in milliseconds.
    """

    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float = 0.0

    @property
    def ok(self) -> bool:
        """True when the process exited successfully."""
        return self.returncode == 0

    @property
    def output(self) -> str:
        """stdout with trailing whitespace removed."""
        return self.stdout.strip()

    @property
    def lines(self) -> List[str]:
        """stdout split into non-empty lines."""
        return [line for line in self.stdout.splitlines() if line.strip()]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of the result."""
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": round(self.duration_ms, 2),
            "ok": self.ok,
        }


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

# The Shodan CLI imports ``pkg_resources`` which modern setuptools warns about
# on every invocation.  The warning is noise for our purposes.
_NOISE_PATTERNS = (
    re.compile(r"^\s*import pkg_resources\s*$", re.MULTILINE),
    re.compile(r"pkg_resources is deprecated as an API.*$", re.MULTILINE),
    re.compile(r"^\s*from pkg_resources import.*$", re.MULTILINE),
)

_AUTH_HINTS = (
    "please run \"shodan init",
    "invalid api key",
    "no api key",
    "unauthorized",
)


def _strip_noise(text: str) -> str:
    """Remove known noisy lines from CLI stderr output."""
    cleaned = text
    for pattern in _NOISE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return cleaned.strip()


def _looks_like_auth_error(text: str) -> bool:
    """Heuristically detect authentication / initialisation problems."""
    lowered = text.lower()
    return any(hint in lowered for hint in _AUTH_HINTS)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class ShodanRunner:
    """Executes ``shodan`` CLI commands and returns structured results.

    Args:
        executable: Name or path of the Shodan CLI.  Defaults to ``shodan`` and
            is resolved from ``PATH`` at call time.
        timeout: Maximum number of seconds a single command may run.
        env: Extra environment variables merged into the child process
            environment.  ``SHODAN_TOOLKIT_*`` keys are also honoured.
        cwd: Working directory for the child process.
    """

    def __init__(
        self,
        executable: str = "shodan",
        timeout: float = 120.0,
        env: Optional[Mapping[str, str]] = None,
        cwd: Optional[str] = None,
    ):
        self.executable = executable
        self.timeout = timeout
        self.env = dict(env or {})
        self.cwd = cwd

    # -- environment ------------------------------------------------------

    def _build_env(self) -> Dict[str, str]:
        """Compose the environment for the child process."""
        child_env = os.environ.copy()
        child_env.update(self.env)

        # Neutralise the pager so buffered output is written straight to stdout.
        child_env.setdefault("PAGER", "cat")
        child_env.setdefault("GIT_PAGER", "cat")
        # `less` must not paginate or clear the screen.
        child_env.setdefault("LESS", "")
        # Deterministic, plain output.
        child_env.setdefault("TERM", "dumb")
        child_env.setdefault("NO_COLOR", "1")
        child_env.setdefault("PYTHONWARNINGS", "ignore::UserWarning")
        # Make sure the CLI never tries to open an interactive prompt.
        child_env.setdefault("SHODAN_CLI_NON_INTERACTIVE", "1")
        return child_env

    # -- availability -----------------------------------------------------

    def resolve_executable(self) -> Optional[str]:
        """Resolve the path of the Shodan CLI executable.

        Resolution order:

        1. An explicit path (the executable contains a path separator) is
           used as-is.
        2. A console script sitting next to the *running* interpreter is
           preferred.  This guarantees the CLI matches the dependency set of
           the environment the toolkit is running in, rather than an
           unrelated ``shodan`` that happens to appear earlier on ``PATH``.
        3. Otherwise the first match on ``PATH`` is used.

        Returns:
            The absolute path to the executable, or ``None`` if not found.
        """
        if os.sep in self.executable or (os.altsep and os.altsep in self.executable):
            candidate = Path(self.executable).expanduser()
            return str(candidate) if candidate.exists() else None

        # Prefer the console script of the current interpreter.
        sibling = Path(sys.executable).parent / self.executable
        if sibling.exists() and os.access(sibling, os.X_OK):
            return str(sibling)

        return shutil.which(self.executable)

    def is_available(self) -> bool:
        """Return True when the Shodan CLI can be located."""
        return self.resolve_executable() is not None

    def version(self) -> str:
        """Return the version string reported by the Shodan CLI."""
        result = self.run(["version"], check=False)
        if not result.ok:
            raise ShodanCLIError(
                f"Unable to determine Shodan CLI version: {result.stderr or result.stdout}",
                result=result,
            )
        return result.output

    # -- execution --------------------------------------------------------

    def run(
        self,
        args: Sequence[str],
        check: bool = True,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        """Run a Shodan CLI command.

        Args:
            args: Argument vector *without* the executable name.
            check: When True (default) a non-zero exit status raises
                :class:`ShodanCLIError` / :class:`ShodanAuthError`.
            timeout: Overrides the runner default timeout.

        Returns:
            The :class:`CommandResult` describing the invocation.

        Raises:
            ShodanNotInstalledError: The executable is missing.
            ShodanAuthError: The API key is missing or rejected.
            ShodanCLIError: The command failed for another reason.
            subprocess.TimeoutExpired: The command exceeded its timeout.
        """
        resolved = self.resolve_executable()
        if resolved is None:
            raise ShodanNotInstalledError(
                f"The '{self.executable}' executable was not found on PATH. "
                "Install it with: pip install shodan"
            )

        command = [resolved, *args]
        effective_timeout = self.timeout if timeout is None else timeout

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=self._build_env(),
                cwd=self.cwd,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ShodanCLIError(
                f"Shodan command timed out after {effective_timeout}s: "
                f"{' '.join(command)}"
            ) from exc
        except OSError as exc:
            raise ShodanNotInstalledError(
                f"Unable to execute '{self.executable}': {exc}"
            ) from exc

        result = CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=_strip_noise(completed.stderr or ""),
            duration_ms=(time.monotonic() - started) * 1000.0,
        )

        if check and not result.ok:
            message = result.stderr or result.stdout or "unknown error"
            if _looks_like_auth_error(message):
                raise ShodanAuthError(
                    "Shodan API authentication failed. Run 'shodan init <api-key>' "
                    f"to configure your key. Details: {message}"
                )
            raise ShodanCLIError(
                f"Shodan command failed (exit {result.returncode}): "
                f"{' '.join(command)} -> {message}",
                result=result,
            )

        return result

    # -- convenience ------------------------------------------------------

    def run_json(
        self,
        args: Sequence[str],
        check: bool = True,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run a command and parse stdout as JSON."""
        import json

        result = self.run(args, check=check, timeout=timeout)
        if not result.output:
            return {}
        try:
            return json.loads(result.output)
        except json.JSONDecodeError as exc:
            raise ShodanCLIError(
                f"Expected JSON output from shodan {' '.join(args)}, got: "
                f"{result.output[:400]}",
                result=result,
            ) from exc
