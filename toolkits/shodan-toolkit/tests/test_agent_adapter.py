"""
Integration tests for the Shodan agent adapter (``agent_shodan_toolkit.py``).

The adapter is the LlamaIndex half of the Shodan feature; the reusable
library half lives in ``toolkits/shodan-toolkit/src/shodan_toolkit/`` and is
tested by the suite that sits next to this file. What is covered here is the
*integration*:

* the tool registration: the read-only set, the opt-in for the write-capable
  tools, and the ``Category: Security`` tag the startup menu needs;
* the degradation contract: a missing ``shodan`` CLI, a missing API key or a
  broken install must never raise at import time and must never crash the
  agent boot;
* the error-payload convention: a failing tool returns ``success: false``
  instead of a traceback;
* the raw-command guard, which is what keeps ``shodan_raw`` read-only;
* the load-path parity: the retriever, the ``--select`` menu and both
  orchestrators must expose exactly the same Shodan tools.

This file lives in the toolkit's test directory so that *every* Shodan test
sits in one place. It is the only file there that reaches outside the
toolkit: it needs the agent-side modules, which live in the repository root.
When the toolkit is installed as a standalone library - with no agent
repository around - the whole module is skipped.

Run with:
    pytest toolkits/shodan-toolkit/tests/test_agent_adapter.py -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

#: The repository root: ``<root>/toolkits/shodan-toolkit/tests/<this file>``.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The agent-side adapter this module exercises.
_ADAPTER_PATH = REPO_ROOT / "agent_shodan_toolkit.py"

if not _ADAPTER_PATH.is_file():
    # The toolkit is used as a standalone library: there is no agent
    # repository to integrate with, so there is nothing to test here.
    pytest.skip(
        "the agent adapter is not available outside the agent repository",
        allow_module_level=True,
    )

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import agent_shodan_toolkit as shodan
except Exception as exc:  # pragma: no cover - depends on the environment
    pytest.skip(
        f"the agent adapter could not be imported: {exc}",
        allow_module_level=True,
    )


#: The twelve read-only tools the adapter exposes by default.
READONLY_TOOL_NAMES = {
    "shodan_search",
    "shodan_count",
    "shodan_host",
    "shodan_stats",
    "shodan_trends",
    "shodan_domain_info",
    "shodan_honeyscore",
    "shodan_myip",
    "shodan_account_info",
    "shodan_list_alerts",
    "shodan_list_scans",
    "shodan_raw",
}

#: The four tools that change account state or consume credits.
MUTATING_TOOL_NAMES = {
    "shodan_create_alert",
    "shodan_delete_alert",
    "shodan_submit_scan",
    "shodan_download",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_config(clean_env, tmp_path, monkeypatch):
    """Keep the tests away from the developer's real Shodan configuration.

    ``clean_env`` (from ``conftest.py``) removes the ``SHODAN_TOOLKIT_*``
    variables; this fixture then points them at a temporary directory, so
    the suite never reads - or writes - the real ``~/.config/shodan-toolkit``
    configuration.

    The working directory is moved to the repository root as well: the
    agent-side modules read their own configuration relative to it, and the
    suite must not depend on where pytest was started from.
    """
    monkeypatch.setenv("SHODAN_TOOLKIT_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("SHODAN_TOOLKIT_SHODAN_CONFIG_DIR", str(tmp_path / "shodan"))
    monkeypatch.chdir(REPO_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_module(name: str, filename: str):
    """Load a hyphenated orchestrator module by path."""
    path = REPO_ROOT / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _retriever_tool_names() -> set:
    """Return the tool names the retriever would index.

    The retriever builds a real ``ObjectIndex`` over a ``VectorStoreIndex``,
    which needs a live embedding model.  The index is stubbed out so the
    test stays offline: only the *inventory* is under test here.
    """
    import agent_tool_retriever as retriever

    with patch.object(retriever.ObjectIndex, "from_objects") as from_objects:
        from_objects.return_value.as_retriever.return_value = MagicMock()
        _, all_tools = retriever.build_tool_retriever(llm=None)

    return {t.metadata.name for t in all_tools}


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    """The adapter must expose the toolkit's tools under the Security tag."""

    def test_the_core_package_is_available(self):
        """The toolkit must be importable from the repository."""
        assert shodan.SHODAN_AVAILABLE is True

    def test_exactly_twelve_read_only_tools(self):
        """Only the read-only tools are exposed by default."""
        names = {t.metadata.name for t in shodan.get_all_tools()}
        assert len(names) == 12
        assert names == READONLY_TOOL_NAMES

    def test_the_mutating_tools_are_not_exposed_by_default(self):
        """An autonomous agent must not be able to change account state."""
        names = {t.metadata.name for t in shodan.get_all_tools()}
        assert names & MUTATING_TOOL_NAMES == set()

    def test_every_description_ends_with_the_security_category(self):
        """The selection menu groups tools by the Category suffix."""
        for tool in shodan.get_all_tools():
            assert tool.metadata.description.endswith("Category: Security"), (
                tool.metadata.name
            )

    def test_the_tools_expose_a_json_schema(self):
        """LlamaIndex needs a schema to build the tool call."""
        for tool in shodan.get_all_tools():
            assert tool.metadata.fn_schema is not None
            assert "properties" in tool.metadata.fn_schema.model_json_schema()

    def test_the_tool_functions_are_the_upstream_ones(self):
        """The adapter must not re-implement the tools."""
        from toolkits.shodan_toolkit import TOOL_REGISTRY

        for tool in shodan.get_all_tools():
            assert tool.fn is TOOL_REGISTRY[tool.metadata.name].fn

    def test_the_mutating_tools_can_be_opted_into(self, monkeypatch):
        """The environment variable enables the write-capable tools."""
        monkeypatch.setenv(shodan.MUTATING_ENV_VAR, "1")
        names = {t.metadata.name for t in shodan.get_all_tools()}
        assert names == READONLY_TOOL_NAMES | MUTATING_TOOL_NAMES

    def test_a_falsey_opt_in_keeps_the_tools_read_only(self, monkeypatch):
        """Only a truthy value enables the mutating tools."""
        for value in ("", "0", "false", "no", "off"):
            monkeypatch.setenv(shodan.MUTATING_ENV_VAR, value)
            names = {t.metadata.name for t in shodan.get_all_tools()}
            assert names == READONLY_TOOL_NAMES, value

    def test_the_explicit_flag_overrides_the_environment(self, monkeypatch):
        """An explicit argument wins over the environment variable."""
        monkeypatch.setenv(shodan.MUTATING_ENV_VAR, "1")
        names = {t.metadata.name for t in shodan.get_all_tools(include_mutating=False)}
        assert names == READONLY_TOOL_NAMES


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------


class TestDegradation:
    """A broken installation must never break the agent boot."""

    def test_the_status_report_never_raises(self):
        """The status helper reports the state instead of raising."""
        status = shodan.get_toolkit_status()
        assert status["available"] is True
        assert "cli_available" in status
        assert "has_api_key" in status

    def test_a_missing_cli_produces_an_error_payload(self, monkeypatch):
        """A failing tool returns success=false, not a traceback."""
        tools = {t.metadata.name: t for t in shodan.get_all_tools()}

        from toolkits.shodan_toolkit import runner as core_runner

        def _boom(self, args, check=True, timeout=None):
            raise core_runner.ShodanCLIError("shodan command failed (exit 127)")

        with patch.object(core_runner.ShodanRunner, "run", _boom):
            payload = json.loads(tools["shodan_search"].fn(query="nginx", limit=1))

        assert payload["success"] is False
        assert "error" in payload

    def test_the_raw_guard_refuses_mutating_subcommands(self):
        """shodan_raw must not be an escape hatch around the read-only split."""
        tools = {t.metadata.name: t for t in shodan.get_all_tools()}

        payload = json.loads(
            tools["shodan_raw"].fn(args=["alert", "create", "x", "1.2.3.4/32"])
        )

        assert payload["success"] is False
        assert "read-only" in payload["error"].lower()

    def test_the_readonly_helper_never_returns_write_tools(self):
        """The explicit read-only helper ignores the environment variable."""
        assert {t.metadata.name for t in shodan.get_readonly_tools()} == READONLY_TOOL_NAMES

    def test_the_mutating_helper_returns_only_write_tools(self):
        """The explicit mutating helper returns exactly the write tools."""
        assert {t.metadata.name for t in shodan.get_mutating_tools()} == MUTATING_TOOL_NAMES


# ---------------------------------------------------------------------------
# Load-path parity
# ---------------------------------------------------------------------------


class TestLoadPaths:
    """The tools must be reachable through every load path."""

    def test_the_tools_are_in_the_selection_menu(self):
        """The --select menu must show the Shodan capability."""
        from agent_tool_selection import _discover_tools

        names = {t.metadata.name for t in _discover_tools()}
        assert names >= READONLY_TOOL_NAMES

    def test_they_form_the_security_category(self):
        """The menu groups them under Security."""
        from agent_tool_selection import _discover_tools, group_tools_by_category

        groups = group_tools_by_category(_discover_tools())
        assert "Security" in groups
        security_names = {t.metadata.name for t in groups["Security"]}
        assert security_names == READONLY_TOOL_NAMES

    def test_the_retriever_exposes_them(self):
        """The retriever indexes them for on-demand loading."""
        assert _retriever_tool_names() >= READONLY_TOOL_NAMES

    @pytest.mark.parametrize(
        "module_name,filename",
        [
            ("agent_torvalds_classic", "agent-torvalds.py"),
            ("agent_torvalds_mw", "agent-torvalds-mw.py"),
        ],
    )
    def test_both_orchestrators_expose_them(self, module_name, filename):
        """Both orchestrators load them in the full-inventory mode."""
        module = _load_module(module_name, filename)
        names = {t.metadata.name for t in module._collect_all_tools()}
        assert names >= READONLY_TOOL_NAMES


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
