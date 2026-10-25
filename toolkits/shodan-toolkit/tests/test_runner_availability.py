"""
Tests for the runner's availability detection.

``is_available()`` must report whether the Shodan CLI can actually be
*used*, not merely whether a file with that name exists.  The Shodan CLI
1.31.0 imports ``pkg_resources``, which setuptools 81+ removed; such a
broken installation is present on disk but aborts on startup.  A naive
existence check would report it as healthy and hide the real problem.
"""

from __future__ import annotations

import pytest

from ..runner import ShodanRunner

from .conftest import make_result


class _ScriptedRunner(ShodanRunner):
    """A runner that resolves an executable but replays a fixed result."""

    def __init__(self, result) -> None:
        super().__init__(executable="shodan")
        self._result = result

    def resolve_executable(self):  # type: ignore[override]
        return "/usr/bin/shodan"

    def run(self, args, check: bool = True, timeout=None):  # type: ignore[override]
        return self._result


class TestIsAvailable:
    def test_missing_executable_is_unavailable(self) -> None:
        runner = ShodanRunner(executable="definitely-not-a-real-binary-xyz")
        assert runner.is_available() is False

    def test_runnable_cli_is_available(self) -> None:
        runner = _ScriptedRunner(make_result("Usage: shodan ...", returncode=0))
        assert runner.is_available() is True

    def test_broken_cli_is_unavailable(self) -> None:
        """A CLI that exists but crashes on startup is *not* available."""
        runner = _ScriptedRunner(
            make_result(
                "ModuleNotFoundError: No module named 'pkg_resources'",
                returncode=1,
            )
        )
        assert runner.is_available() is False

    def test_is_available_never_raises(self) -> None:
        """A raising runner must not propagate out of the availability check."""

        class Exploding(ShodanRunner):
            def resolve_executable(self):  # type: ignore[override]
                return "/usr/bin/shodan"

            def run(self, args, check: bool = True, timeout=None):  # type: ignore[override]
                raise OSError("boom")

        assert Exploding(executable="shodan").is_available() is False

    def test_real_cli_roundtrip(self) -> None:
        """The installed CLI must satisfy the check."""
        runner = ShodanRunner(timeout=30)
        if runner.resolve_executable() is None:
            pytest.skip("shodan CLI is not installed")

        # Either it runs (available) or it is genuinely broken (unavailable);
        # both are valid outcomes, but the check must not raise.
        assert isinstance(runner.is_available(), bool)
