"""Tests for the client layer and its command construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from shodan_toolkit.client import ShodanClient
from shodan_toolkit.runner import ShodanCLIError, ShodanError

from .conftest import FakeRunner, make_result


class TestSearch:
    def test_search_builds_expected_command(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["search"] = make_result("1.2.3.4\t80\thost\t\n")
        client.search("apache port:80", limit=5)

        args = fake_runner.calls[-1]
        assert args[0] == "search"
        assert "--no-color" in args
        assert "--fields" in args
        assert "--limit" in args
        assert args[args.index("--limit") + 1] == "5"
        assert args[-1] == "apache port:80"

    def test_search_caps_limit_at_1000(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["search"] = make_result("")
        client.search("nginx", limit=5000)

        args = fake_runner.calls[-1]
        assert args[args.index("--limit") + 1] == "1000"

    def test_search_uses_configured_max_results(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["search"] = make_result("")
        client.search("nginx")

        args = fake_runner.calls[-1]
        assert args[args.index("--limit") + 1] == "50"

    def test_search_requires_query(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        with pytest.raises(ShodanError, match="query is required"):
            client.search("   ")

    def test_search_returns_parsed_records(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["search"] = make_result(
            "1.2.3.4\t80\texample\tbanner\n"
        )
        results = client.search("test", limit=1)

        assert len(results) == 1
        assert results[0]["ip_str"] == "1.2.3.4"
        assert results[0]["port"] == 80


class TestCount:
    def test_count_parses_integer(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["count"] = make_result("1234\n")
        assert client.count("apache") == 1234

    def test_count_handles_commas(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["count"] = make_result("1,234\n")
        assert client.count("apache") == 1234

    def test_count_raises_on_unparsable_output(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["count"] = make_result("not-a-number\n")
        with pytest.raises(ShodanCLIError):
            client.count("apache")


class TestHost:
    def test_host_returns_parsed_data(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["host"] = make_result(
            "8.8.8.8\nHostnames:            dns.google\nCountry:              United States\n"
        )
        host = client.host("8.8.8.8")

        assert host["ip"] == "8.8.8.8"
        assert host["country"] == "United States"
        assert host["hostnames"] == ["dns.google"]

    def test_host_history_flag(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["host"] = make_result("")
        client.host("8.8.8.8", history=True)
        assert "--history" in fake_runner.calls[-1]


class TestStatsAndTrends:
    def test_stats_passes_facets(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["stats"] = make_result("")
        client.stats("apache", facets=["country", "port"], limit=3)

        args = fake_runner.calls[-1]
        assert args[args.index("--facets") + 1] == "country,port"
        assert args[args.index("--limit") + 1] == "3"

    def test_trends_omits_facets_when_absent(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["trends"] = make_result("")
        client.trends("apache")

        assert "--facets" not in fake_runner.calls[-1]


class TestApiKey:
    def test_init_writes_key_file(
        self, client: ShodanClient, tmp_path: Path
    ) -> None:
        result = client.init("my-secret-key")

        key_file = Path(result["key_file"])
        assert key_file.exists()
        assert key_file.read_text() == "my-secret-key"
        assert oct(key_file.stat().st_mode)[-3:] == "600"

    def test_init_rejects_empty_key(self, client: ShodanClient) -> None:
        with pytest.raises(ShodanError):
            client.init("  ")

    def test_has_api_key(
        self, client: ShodanClient, tmp_path: Path
    ) -> None:
        assert client.has_api_key() is False
        client.init("key")
        assert client.has_api_key() is True


class TestErrorPropagation:
    def test_cli_errors_surface(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["search"] = make_result(
            "", stderr="Invalid API key", returncode=1
        )
        with pytest.raises(ShodanCLIError):
            client.search("test")

    def test_empty_query_raises_before_call(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        with pytest.raises(ShodanError):
            client.host("")
        assert not fake_runner.calls


class TestRaw:
    def test_run_raw_returns_result(
        self, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["version"] = make_result("1.31.0\n")
        result = client.run_raw(["version"])

        assert result.ok
        assert result.output == "1.31.0"


class TestRunner:
    """Tests for the subprocess runner itself."""

    def test_duration_is_recorded(self, fake_runner) -> None:
        from shodan_toolkit.runner import CommandResult

        fake_runner.responses["version"] = make_result("1.31.0\n")
        result = fake_runner.run(["version"])
        assert isinstance(result, CommandResult)
        assert result.duration_ms >= 0.0

    def test_real_runner_executes_shodan(self) -> None:
        """The real runner must be able to execute the installed CLI."""
        from shodan_toolkit.runner import ShodanRunner

        runner = ShodanRunner(timeout=30)
        if not runner.is_available():
            pytest.skip("shodan CLI is not installed")

        result = runner.run(["--help"], check=True)
        assert result.ok
        assert "search" in result.stdout

    def test_real_runner_reports_missing_executable(self) -> None:
        from shodan_toolkit.runner import ShodanNotInstalledError, ShodanRunner

        runner = ShodanRunner(executable="definitely-not-a-real-binary-xyz")
        assert runner.is_available() is False
        with pytest.raises(ShodanNotInstalledError):
            runner.run(["--help"])

    def test_command_result_helpers(self) -> None:
        from shodan_toolkit.runner import CommandResult

        result = CommandResult(
            command=["shodan", "info"],
            returncode=0,
            stdout="  hello  \n\n",
            stderr="",
        )
        assert result.ok is True
        assert result.output == "hello"
        assert result.lines == ["  hello  "]
        assert result.to_dict()["ok"] is True
