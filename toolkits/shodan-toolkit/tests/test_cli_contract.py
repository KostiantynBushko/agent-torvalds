"""
Regression tests for the argument vectors the client builds.

Every subcommand of the Shodan CLI has its *own* set of options, and
``click`` rejects any option a subcommand does not declare.  Passing
``--no-color`` to ``shodan host`` therefore aborts the whole command with
``No such option '--no-color'`` — the request never reaches the API.

These tests pin the exact argument vector for every client method so a
future change cannot silently reintroduce an option the real CLI does not
accept.  ``examples/verify_argv.py`` performs the same check against the
installed binary.
"""

from __future__ import annotations

import pytest

from ..client import ShodanClient

from .conftest import FakeRunner, make_result

# Options that only ``shodan search`` (and ``parse``/``stream``) declare.
# Passing them to any other subcommand is a hard error in click.
NO_COLOR_SUBCOMMANDS = {"search"}


class TestArgumentVectorCompatibility:
    """The client must only pass options the real CLI accepts."""

    @pytest.mark.parametrize(
        "subcommand",
        ["stats", "trends", "host", "domain"],
    )
    def test_no_color_not_passed_to_unsupported_subcommands(
        self, client: ShodanClient, fake_runner: FakeRunner, subcommand: str
    ) -> None:
        """``--no-color`` is only valid for ``shodan search``."""
        fake_runner.responses[subcommand] = make_result("")

        call = {
            "stats": lambda: client.stats("nginx"),
            "trends": lambda: client.trends("nginx"),
            "host": lambda: client.host("8.8.8.8"),
            "domain": lambda: client.domain_info("example.com"),
        }[subcommand]
        call()

        args = fake_runner.calls[-1]
        assert args[0] == subcommand
        assert "--no-color" not in args, (
            f"'shodan {subcommand}' does not accept --no-color; "
            f"the CLI rejects the whole command"
        )

    def test_search_still_uses_no_color(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        """``shodan search`` does accept ``--no-color``, so keep using it."""
        fake_runner.responses["search"] = make_result("")
        client.search("nginx", limit=1)

        args = fake_runner.calls[-1]
        assert args[0] == "search"
        assert "--no-color" in args

    def test_myip_ipv6_flag_follows_subcommand(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        """``--ipv6`` belongs to the ``myip`` subcommand, not the root group."""
        fake_runner.responses["myip"] = make_result("1.1.1.1")

        client.myip(ipv6=True)

        args = fake_runner.calls[-1]
        assert args[0] == "myip"
        assert args[-1] == "--ipv6"
        assert "--ipv6" not in args[:1]

    def test_myip_without_ipv6_has_no_flag(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["myip"] = make_result("1.1.1.1")

        client.myip()

        args = fake_runner.calls[-1]
        assert args == ["myip"]


class TestKnownShodanOptionSet:
    """Guards the option sets of the real Shodan CLI 1.31.0.

    If Shodan changes a subcommand's options, this table flags the drift so
    the client can be updated deliberately rather than at runtime.
    """

    # Options declared by each subcommand, as of shodan 1.31.0.
    SUPPORTED_OPTIONS = {
        "search": {"--color", "--no-color", "--fields", "--limit", "--separator"},
        "count": set(),
        "stats": {"--limit", "--facets", "--filename", "-O"},
        "trends": {"--facets", "--filename", "-O", "--save", "-S"},
        "host": {"--format", "--history", "--filename", "-O", "--save", "-S"},
        "domain": {"--details", "-D", "--save", "-S", "--history", "-H", "--type", "-T"},
        "honeyscore": set(),
        "myip": {"--ipv6", "-6"},
        "info": set(),
        "download": {"--fields", "--limit"},
        "alert list": {"--expired"},
        "alert create": set(),
        "alert remove": set(),
        "scan list": set(),
        "scan status": set(),
        "scan submit": {"--wait", "--filename", "--force", "--verbose"},
    }

    @pytest.mark.parametrize(
        "subcommand,build",
        [
            ("stats", lambda c: c.stats("nginx")),
            ("trends", lambda c: c.trends("nginx")),
            ("host", lambda c: c.host("8.8.8.8")),
            ("domain", lambda c: c.domain_info("example.com")),
            ("search", lambda c: c.search("nginx", limit=1)),
            ("myip", lambda c: c.myip()),
            ("honeyscore", lambda c: c.honeyscore("1.1.1.1")),
            ("info", lambda c: c.account_info()),
        ],
    )
    def test_only_supported_options_are_used(
        self, client: ShodanClient, fake_runner: FakeRunner, subcommand, build
    ) -> None:
        fake_runner.responses[subcommand] = make_result("")
        build(client)

        args = fake_runner.calls[-1]
        allowed = self.SUPPORTED_OPTIONS[subcommand]
        used = {arg for arg in args if arg.startswith("-")}

        unsupported = used - allowed
        assert not unsupported, (
            f"'shodan {subcommand}' does not support {sorted(unsupported)}"
        )
