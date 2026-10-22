"""
Tests for the ``shodan_raw`` safety guard.

``shodan_raw`` is registered in the *read-only* category and is handed to
autonomous agents, but it can execute any CLI subcommand.  Without a guard
an agent could run ``shodan_raw(["alert", "create", ...])`` and silently
create network alerts — exactly the class of side effect the read-only /
mutating split exists to prevent.

The guard therefore refuses subcommands that change account state, consume
credits, or write files.
"""

from __future__ import annotations

import json

import pytest

from shodan_toolkit.tools import (
    MUTATING_SHODAN_SUBCOMMANDS,
    _is_mutating_command,
    _normalise_subcommand,
    shodan_raw,
)


class TestNormaliseSubcommand:
    @pytest.mark.parametrize(
        "args,expected",
        [
            (["host", "8.8.8.8"], "host"),
            (["alert", "create", "name"], "alert create"),
            (["alert", "list"], "alert list"),
            (["init", "SECRET"], "init"),
            (["download", "out.json.gz", "nginx"], "download"),
            (["myip", "--ipv6"], "myip"),
            (["--color", "alert", "list"], "alert list"),
            (["host", "--format", "pretty", "1.1.1.1"], "host"),
            ([], ""),
        ],
    )
    def test_normalisation(self, args, expected) -> None:
        assert _normalise_subcommand(args) == expected


class TestMutatingDetection:
    @pytest.mark.parametrize(
        "args",
        [
            ["alert", "create", "name", "8.8.8.0/24"],
            ["alert", "remove", "123"],
            ["alert", "clear"],
            ["alert", "import", "file.json"],
            ["scan", "submit", "8.8.8.0/24"],
            ["scan", "internet"],
            ["download", "out.json.gz", "nginx"],
            ["data", "download", "dataset"],
            ["org", "add", "someone"],
            ["org", "remove", "someone"],
            ["init", "SECRET"],
        ],
    )
    def test_mutating_commands_are_detected(self, args) -> None:
        assert _is_mutating_command(args) is True

    @pytest.mark.parametrize(
        "args",
        [
            ["host", "8.8.8.8"],
            ["alert", "list"],
            ["alert", "stats", "5"],
            ["scan", "list"],
            ["scan", "status", "abc"],
            ["count", "nginx"],
            ["stats", "nginx"],
            ["trends", "nginx"],
            ["domain", "example.com"],
            ["honeyscore", "1.1.1.1"],
            ["myip"],
            ["info"],
        ],
    )
    def test_read_only_commands_are_allowed(self, args) -> None:
        assert _is_mutating_command(args) is False

    def test_registry_covers_known_mutating_groups(self) -> None:
        """The guard list must mention every group that has mutating verbs."""
        for group in ("alert", "scan", "org", "data"):
            assert any(
                entry.startswith(f"{group} ") for entry in MUTATING_SHODAN_SUBCOMMANDS
            ), f"no mutating entry for the '{group}' group"


class TestRawToolBehaviour:
    def test_mutating_command_is_refused(self, monkeypatch) -> None:
        """A mutating command must not reach the CLI."""
        calls = []

        class Recorder:
            def run_raw(self, args, check=True):
                calls.append(list(args))
                raise AssertionError("the CLI must not be invoked")

        from shodan_toolkit import tools

        monkeypatch.setattr(tools, "get_client", lambda: Recorder())

        payload = json.loads(shodan_raw(["alert", "create", "x", "8.8.8.0/24"]))

        assert payload["success"] is False
        assert "read-only" in payload["error"]
        assert not calls

    def test_read_only_command_runs(self, monkeypatch) -> None:
        class Recorder:
            def run_raw(self, args, check=True):
                from shodan_toolkit.runner import CommandResult

                return CommandResult(
                    command=["shodan", *args], returncode=0, stdout="ok", stderr=""
                )

        from shodan_toolkit import tools

        monkeypatch.setattr(tools, "get_client", lambda: Recorder())

        payload = json.loads(shodan_raw(["host", "8.8.8.8"]))

        assert payload["success"] is True
        assert payload["data"]["output"] == "ok"
        assert payload["data"]["command"] == "shodan host 8.8.8.8"
