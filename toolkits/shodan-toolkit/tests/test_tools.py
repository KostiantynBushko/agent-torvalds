"""Tests for the LlamaIndex tool layer."""

from __future__ import annotations

import json
from typing import Any

import pytest

from .. import tools as tools_module
from ..client import ShodanClient
from ..tools import (
    TOOL_REGISTRY,
    get_all_tools,
    get_mutating_tools,
    get_readonly_tools,
    get_tools_by_name,
    set_client,
)

from .conftest import FakeRunner, make_result


@pytest.fixture(autouse=True)
def reset_client() -> Any:
    """Ensure the shared client is reset between tests."""
    set_client(None)
    yield
    set_client(None)


def _install(monkeypatch: pytest.MonkeyPatch, client: ShodanClient) -> None:
    set_client(client)
    monkeypatch.setattr(tools_module, "get_client", lambda: client)


class TestToolRegistry:
    def test_registry_is_populated(self) -> None:
        assert len(TOOL_REGISTRY) > 0
        for name, definition in TOOL_REGISTRY.items():
            assert definition.name == name
            assert definition.category in {"read", "write"}
            assert callable(definition.fn)

    def test_readonly_excludes_mutating_tools(self) -> None:
        readonly = {t.metadata.name for t in get_readonly_tools()}
        mutating = {t.metadata.name for t in get_mutating_tools()}

        assert readonly.isdisjoint(mutating)
        assert "shodan_search" in readonly
        assert "shodan_create_alert" in mutating

    def test_mutating_tools_not_included_by_default(self) -> None:
        names = {t.metadata.name for t in get_all_tools()}
        assert "shodan_create_alert" not in names
        assert "shodan_submit_scan" not in names

    def test_mutating_tools_included_on_request(self) -> None:
        names = {t.metadata.name for t in get_all_tools(include_mutating=True)}
        assert "shodan_create_alert" in names

    def test_explicit_names_filter(self) -> None:
        names = {t.metadata.name for t in get_tools_by_name(["shodan_search", "nope"])}
        assert names == {"shodan_search"}

    def test_tools_are_function_tools(self) -> None:
        from llama_index.core.tools import FunctionTool

        for tool in get_all_tools(include_mutating=True):
            assert isinstance(tool, FunctionTool)
            assert tool.metadata.description


class TestToolSchemas:
    def test_search_tool_schema(self) -> None:
        tool = get_tools_by_name(["shodan_search"])[0]
        params = tool.metadata.get_parameters_dict()

        assert "query" in params["properties"]
        assert "limit" in params["properties"]
        assert params["required"] == ["query"]

    def test_all_tools_have_required_params_documented(self) -> None:
        for tool in get_all_tools(include_mutating=True):
            params = tool.metadata.get_parameters_dict()
            for required in params.get("required", []):
                assert required in params["properties"], (
                    f"{tool.metadata.name}: required param '{required}' not declared"
                )


class TestToolExecution:
    def test_search_tool_returns_json(
        self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["search"] = make_result("1.2.3.4\t80\thost\t\n")
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_search("apache", limit=5))

        assert payload["success"] is True
        assert payload["data"]["count"] == 1
        assert payload["data"]["results"][0]["ip_str"] == "1.2.3.4"

    def test_count_tool(self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner) -> None:
        fake_runner.responses["count"] = make_result("42\n")
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_count("apache"))
        assert payload["success"] is True
        assert payload["data"]["total"] == 42

    def test_host_tool(self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner) -> None:
        fake_runner.responses["host"] = make_result("8.8.8.8\nCountry:  US\n")
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_host("8.8.8.8"))
        assert payload["success"] is True
        assert payload["data"]["country"] == "US"

    def test_stats_tool(self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner) -> None:
        fake_runner.responses["stats"] = make_result(
            "Top 1 Results for Facet: country\nUnited States   10\n"
        )
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_stats("apache"))
        assert payload["success"] is True
        assert payload["data"]["facets"]["country"][0]["count"] == 10

    def test_trends_tool(self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner) -> None:
        fake_runner.responses["trends"] = make_result("2017-06   100\n")
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_trends("apache"))
        assert payload["success"] is True
        assert payload["data"]["months"][0]["month"] == "2017-06"

    def test_domain_tool(self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner) -> None:
        fake_runner.responses["domain"] = make_result(
            "EXAMPLE.COM\n\nwww   A   1.2.3.4\n\n"
        )
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_domain_info("example.com"))
        assert payload["success"] is True
        assert payload["data"]["records"][0]["value"] == "1.2.3.4"

    def test_honeyscore_tool(self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner) -> None:
        fake_runner.responses["honeyscore"] = make_result(
            "Not a honeypot\nScore: 0.0\n"
        )
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_honeyscore("1.2.3.4"))
        assert payload["success"] is True
        assert payload["data"]["score"] == 0.0

    def test_raw_tool(self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner) -> None:
        fake_runner.responses["version"] = make_result("1.31.0\n")
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_raw(["version"]))
        assert payload["success"] is True
        assert payload["data"]["output"] == "1.31.0"

    def test_create_alert_tool(
        self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["alert"] = make_result(
            "Successfully created network alert!\nAlert ID: abc123\n"
        )
        _install(monkeypatch, client)

        payload = json.loads(
            tools_module.shodan_create_alert("my-alert", ["8.8.8.0/24"])
        )
        assert payload["success"] is True
        assert payload["data"]["name"] == "my-alert"


class TestToolErrorHandling:
    def test_errors_are_returned_not_raised(
        self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient, fake_runner: FakeRunner
    ) -> None:
        fake_runner.responses["search"] = make_result(
            "", stderr="Invalid API key", returncode=1
        )
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_search("apache"))

        assert payload["success"] is False
        assert "error" in payload

    def test_empty_query_returns_error_payload(
        self, monkeypatch: pytest.MonkeyPatch, client: ShodanClient
    ) -> None:
        _install(monkeypatch, client)

        payload = json.loads(tools_module.shodan_search(""))

        assert payload["success"] is False
        assert "query" in payload["error"].lower()
