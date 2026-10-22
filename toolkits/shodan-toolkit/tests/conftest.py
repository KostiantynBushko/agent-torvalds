"""Shared pytest fixtures for the shodan-toolkit test suite."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from shodan_toolkit.client import ShodanClient
from shodan_toolkit.config import ShodanConfig
from shodan_toolkit.runner import CommandResult, ShodanRunner


class FakeRunner(ShodanRunner):
    """A runner that records invocations and replays canned results.

    Args:
        responses: Mapping of a command prefix (e.g. ``"search"``) to either a
            :class:`CommandResult` or a callable taking the full argument
            vector and returning one.
        default: Result used when no response matches.
    """

    def __init__(self, responses: Dict[str, Any], default: Any = None):
        super().__init__(executable="shodan")
        self.responses = responses
        self.default = default
        self.calls: List[List[str]] = []

    def resolve_executable(self):  # type: ignore[override]
        return "/usr/bin/shodan"

    def is_available(self) -> bool:  # type: ignore[override]
        return True

    def run(self, args, check: bool = True, timeout=None) -> CommandResult:
        args = list(args)
        self.calls.append(args)

        key = args[0] if args else ""
        response = self.responses.get(key, self.default)

        if response is None:
            result = CommandResult(
                command=["shodan", *args],
                returncode=0,
                stdout="",
                stderr="",
            )
        elif callable(response):
            result = response(args)
        else:
            result = response

        if check and result.returncode != 0:
            from shodan_toolkit.runner import ShodanCLIError

            raise ShodanCLIError(
                f"Shodan command failed: {result.stderr or result.stdout}",
                result=result,
            )
        return result


def make_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> CommandResult:
    """Build a :class:`CommandResult` for use in tests."""
    return CommandResult(
        command=["shodan"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


@pytest.fixture
def fake_runner() -> FakeRunner:
    """A :class:`FakeRunner` with no canned responses."""
    return FakeRunner(responses={})


@pytest.fixture
def config(tmp_path: Path) -> ShodanConfig:
    """A configuration pointing at a temporary credential directory."""
    return ShodanConfig(
        shodan_config_dir=str(tmp_path / "shodan"),
        api_key="test-key",
        max_results=50,
    )


@pytest.fixture
def client(config: ShodanConfig, fake_runner: FakeRunner) -> ShodanClient:
    """A client wired to the :class:`FakeRunner`."""
    return ShodanClient(config=config, runner=fake_runner)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove Shodan-related environment variables for test isolation."""
    for key in list(os.environ):
        if key.startswith("SHODAN_TOOLKIT_") or key == "SHODAN_API_KEY":
            monkeypatch.delenv(key, raising=False)
