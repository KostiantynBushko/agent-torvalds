"""
Regression tests for the startup tool selection menu.

The menu built by :mod:`agent_tool_selection` is supposed to show **every**
toolkit the agent can load. A toolkit that is wired into the retriever but
forgotten in :func:`agent_tool_selection._discover_tools` silently disappears
from the ``--select`` menu - the user is never told the capability exists.

The MikroTik RouterOS toolkit hit exactly that defect, so the tests below
lock the menu against it:

* the MikroTik tools must be discoverable and must form the ``Network``
  category;
* the menu must offer the same tool inventory as the retriever;
* the MikroTik tools must be reachable through every load path (menu,
  retriever, classic orchestrator, multi-window orchestrator).

The Shodan toolkit is locked down the same way, under the ``Security``
category: the twelve read-only tools must be discoverable, selectable and
rendered, and the four write-capable tools must stay out of the menu
unless the operator opts in.

Run with:
    pytest tests/test_tool_selection_menu.py -v
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# The eight MikroTik tools, by name
# ---------------------------------------------------------------------------

MIKROTIK_TOOL_NAMES = {
    "list_mikrotik_targets",
    "test_mikrotik_connection",
    "run_mikrotik_command",
    "get_routeros_config",
    "backup_routeros_config",
    "get_routeros_identity",
    "get_routeros_interfaces",
    "get_routeros_health",
}

# ---------------------------------------------------------------------------
# The Shodan tools, by name
# ---------------------------------------------------------------------------

#: The twelve read-only Shodan tools. The four write-capable tools only
#: join them when the operator opts in with
#: ``TORVALDS_SHODAN_ALLOW_MUTATING=1``.
SHODAN_READONLY_TOOL_NAMES = {
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

#: The four Shodan tools that change account state or consume credits.
SHODAN_MUTATING_TOOL_NAMES = {
    "shodan_create_alert",
    "shodan_delete_alert",
    "shodan_submit_scan",
    "shodan_download",
}

#: The environment variable that opts the agent into the write-capable
#: Shodan tools. The adapter reads it itself, so every load path - the
#: menu, the retriever and both orchestrators - behaves identically.
SHODAN_MUTATING_ENV_VAR = "TORVALDS_SHODAN_ALLOW_MUTATING"


@contextlib.contextmanager
def _shodan_opt_in(value: str | None = None):
    """Control the mutating-tools opt-in for the duration of the block.

    The menu is read-only by default and the opt-in is an environment
    variable, so a developer who has it exported in their shell would
    otherwise see the tests below fail. ``value=None`` removes the
    variable, which is the state of a clean environment.
    """
    with patch.dict(os.environ):
        os.environ.pop(SHODAN_MUTATING_ENV_VAR, None)
        if value is not None:
            os.environ[SHODAN_MUTATING_ENV_VAR] = value
        yield


#: Tool names the discovery menu and the retriever are allowed to share
#: with the orchestrators' ``--full`` inventory. The Excel and data
#: analysis toolkits are wired into the retriever and into the selection
#: menu, but *not* into the orchestrators' ``_collect_all_tools()``; that
#: gap predates the MikroTik work and is tracked separately. Pinning the
#: exact set keeps this test honest: a *new* difference still fails.
KNOWN_FULL_ONLY_GAP = {
    # Data / Excel
    "read_xlsx_file",
    "write_xlsx_file",
    "get_sheet_names",
    "get_cell_value",
    "set_cell_value",
    "get_dimensions",
    "copy_sheet",
    "apply_style",
    "create_empty_workbook",
    # Data / Analysis
    "read_excel_to_df",
    "read_csv_to_df",
    "compute_statistics",
    "filter_data",
    "aggregate_data",
    "pivot_table",
    "detect_missing_data",
    "correlation_matrix",
    "export_dataframe",
    "get_unique_values",
    "sort_data",
    "describe_data",
    "get_dataframe_info",
}

#: ``get_system_info`` is defined by both the OS toolkit and the Linux
#: toolkit, so it appears twice in the discovery menu. This is a
#: pre-existing name clash; it is tolerated by LlamaIndex but it is worth
#: pinning so that a *new* duplicate is caught.
KNOWN_DUPLICATE_TOOL_NAMES = {"get_system_info"}


def _load_mw_agent():
    """Load agent-torvalds-mw.py as an importable module."""
    path = ROOT / "agent-torvalds-mw.py"
    spec = importlib.util.spec_from_file_location("agent_torvalds_mw", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_torvalds_mw"] = module
    spec.loader.exec_module(module)
    return module


def _load_classic_agent():
    """Load agent-torvalds.py as an importable module."""
    path = ROOT / "agent-torvalds.py"
    spec = importlib.util.spec_from_file_location("agent_torvalds_classic", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_torvalds_classic"] = module
    spec.loader.exec_module(module)
    return module


def _retriever_tool_names() -> set:
    """Return the tool names the retriever would index.

    The retriever builds a real ``ObjectIndex`` over a ``VectorStoreIndex``,
    which needs a live embedding model. The index is stubbed out so the
    test stays offline: only the *inventory* is under test here.
    """
    import agent_tool_retriever as retriever

    with patch.object(retriever.ObjectIndex, "from_objects") as from_objects:
        from_objects.return_value.as_retriever.return_value = MagicMock()
        _, all_tools = retriever.build_tool_retriever(llm=None)

    return {t.metadata.name for t in all_tools}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDiscoverTools(unittest.TestCase):
    """_discover_tools() must find every toolkit, MikroTik included."""

    @classmethod
    def setUpClass(cls):
        from agent_tool_selection import _discover_tools

        cls.tools = _discover_tools()
        cls.names = {t.metadata.name for t in cls.tools}

    def test_mikrotik_tools_are_discovered(self):
        missing = MIKROTIK_TOOL_NAMES - self.names
        self.assertEqual(
            missing,
            set(),
            f"MikroTik tools missing from the selection menu: {sorted(missing)}",
        )

    def test_discovery_is_not_empty(self):
        self.assertGreater(len(self.tools), 50)

    def test_no_new_duplicate_tool_names(self):
        names = [t.metadata.name for t in self.tools]
        duplicates = {n for n in names if names.count(n) > 1}
        self.assertEqual(
            duplicates,
            KNOWN_DUPLICATE_TOOL_NAMES,
            f"unexpected duplicate tool names: {sorted(duplicates)}",
        )


# ---------------------------------------------------------------------------
# Grouping / the menu
# ---------------------------------------------------------------------------

class TestNetworkCategory(unittest.TestCase):
    """The MikroTik tools must form the 'Network' category in the menu."""

    @classmethod
    def setUpClass(cls):
        from agent_tool_selection import _discover_tools, group_tools_by_category

        cls.tools = _discover_tools()
        cls.groups = group_tools_by_category(cls.tools)

    def test_network_category_exists(self):
        self.assertIn(
            "Network",
            self.groups,
            "The 'Network' category is missing from the selection menu",
        )

    def test_network_category_holds_all_mikrotik_tools(self):
        network_names = {t.metadata.name for t in self.groups.get("Network", [])}
        self.assertEqual(
            MIKROTIK_TOOL_NAMES - network_names,
            set(),
            "Some MikroTik tools are not grouped under 'Network'",
        )

    def test_network_category_has_no_foreign_tools(self):
        """Only the MikroTik tools may live in the 'Network' category."""
        network_names = {t.metadata.name for t in self.groups.get("Network", [])}
        self.assertEqual(network_names, MIKROTIK_TOOL_NAMES)

    def test_every_tool_is_in_exactly_one_category(self):
        total = sum(len(v) for v in self.groups.values())
        self.assertEqual(total, len(self.tools))

    def test_no_uncategorized_tools(self):
        self.assertNotIn(
            "Uncategorized",
            self.groups,
            "A tool has no 'Category:' tag and would show up uncategorised",
        )


class TestCategoryDescription(unittest.TestCase):
    """The Network summary must describe real capabilities."""

    def test_network_summary_is_meaningful(self):
        from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import (
            get_all_tools,
        )
        from agent_tool_selection import _build_category_description

        summary = _build_category_description(get_all_tools())

        self.assertTrue(summary.startswith("Actions: "), summary)
        self.assertIn("discover", summary)
        self.assertIn("diagnose", summary)
        self.assertIn("execute", summary)
        self.assertIn("backup", summary)

    def test_network_summary_ignores_routeros_paths(self):
        """'/ip/firewall/filter' must not be read as a data-analysis verb."""
        from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import (
            get_all_tools,
        )
        from agent_tool_selection import _build_category_description

        summary = _build_category_description(get_all_tools())
        self.assertNotIn("filter", summary)
        self.assertNotIn("aggregate", summary)


# ---------------------------------------------------------------------------
# Parity with the other load paths
# ---------------------------------------------------------------------------

class TestMenuParity(unittest.TestCase):
    """
    The menu must expose the same tools as the other load paths.

    A toolkit wired into the retriever but missing from the menu is
    invisible to the operator, so the inventory paths are compared.
    """

    def test_menu_matches_retriever(self):
        """The retriever's inventory must match the menu's inventory."""
        from agent_tool_selection import _discover_tools

        menu_names = {t.metadata.name for t in _discover_tools()}
        retriever_names = _retriever_tool_names()

        self.assertEqual(
            menu_names - retriever_names,
            set(),
            "The menu exposes tools the retriever does not",
        )
        self.assertEqual(
            retriever_names - menu_names,
            set(),
            "The menu is missing tools the retriever exposes",
        )

    def test_mikrotik_is_in_every_load_path(self):
        """The MikroTik tools must be selectable and loadable everywhere."""
        from agent_tool_selection import _discover_tools

        menu_names = {t.metadata.name for t in _discover_tools()}
        classic_names = {t.metadata.name for t in _load_classic_agent()._collect_all_tools()}
        mw_names = {t.metadata.name for t in _load_mw_agent()._collect_all_tools()}
        retriever_names = _retriever_tool_names()

        for label, names in (
            ("selection menu", menu_names),
            ("classic orchestrator", classic_names),
            ("multi-window orchestrator", mw_names),
            ("retriever", retriever_names),
        ):
            missing = MIKROTIK_TOOL_NAMES - names
            self.assertEqual(
                missing,
                set(),
                f"MikroTik tools missing from the {label}: {sorted(missing)}",
            )

    def test_shodan_is_in_every_load_path(self):
        """The Shodan tools must be selectable and loadable everywhere."""
        from agent_tool_selection import _discover_tools

        with _shodan_opt_in():
            menu_names = {t.metadata.name for t in _discover_tools()}
            classic_names = {
                t.metadata.name for t in _load_classic_agent()._collect_all_tools()
            }
            mw_names = {t.metadata.name for t in _load_mw_agent()._collect_all_tools()}
            retriever_names = _retriever_tool_names()

        for label, names in (
            ("selection menu", menu_names),
            ("classic orchestrator", classic_names),
            ("multi-window orchestrator", mw_names),
            ("retriever", retriever_names),
        ):
            missing = SHODAN_READONLY_TOOL_NAMES - names
            self.assertEqual(
                missing,
                set(),
                f"Shodan tools missing from the {label}: {sorted(missing)}",
            )

    def test_menu_orchestrator_difference_is_known(self):
        """
        The menu may not hide a toolkit the orchestrators expose.

        The only tolerated difference is the known Excel / data analysis
        gap in the ``--full`` inventory, which predates this work.
        """
        from agent_tool_selection import _discover_tools

        menu_names = {t.metadata.name for t in _discover_tools()}
        classic_names = {t.metadata.name for t in _load_classic_agent()._collect_all_tools()}

        self.assertEqual(
            menu_names - classic_names,
            KNOWN_FULL_ONLY_GAP,
            "The menu exposes tools the classic agent does not",
        )
        self.assertEqual(
            classic_names - menu_names,
            set(),
            "The menu is missing tools the classic agent exposes",
        )


# ---------------------------------------------------------------------------
# Selecting the Network category end to end
# ---------------------------------------------------------------------------

class TestSelectingNetwork(unittest.TestCase):
    """Selecting the 'Network' category must return the MikroTik tools."""

    def test_select_tools_by_category_returns_mikrotik_tools(self):
        from agent_tool_selection import select_tools_by_category

        tools = select_tools_by_category(categories=["Network"])
        self.assertEqual({t.metadata.name for t in tools}, MIKROTIK_TOOL_NAMES)

    def test_select_tools_by_category_is_case_insensitive(self):
        from agent_tool_selection import select_tools_by_category

        tools = select_tools_by_category(categories=["network"])
        self.assertEqual({t.metadata.name for t in tools}, MIKROTIK_TOOL_NAMES)

    def test_interactive_selection_picks_the_network_category(self):
        """Drive the interactive flow and pick the 'Network' index."""
        from agent_tool_selection import _discover_tools, group_tools_by_category

        tools = _discover_tools()
        groups = group_tools_by_category(tools)
        categories = list(groups.keys())

        self.assertIn("Network", categories)
        index = categories.index("Network") + 1

        import builtins

        prompts: list[str] = []
        original_input = builtins.input

        def fake_input(prompt=""):
            prompts.append(prompt)
            return str(index)

        builtins.input = fake_input
        try:
            from agent_tool_selection import select_tools_interactively

            selected = select_tools_interactively(all_tools=tools)
        finally:
            builtins.input = original_input

        self.assertEqual(len(prompts), 1)
        self.assertEqual({t.metadata.name for t in selected}, MIKROTIK_TOOL_NAMES)

    def test_menu_displays_the_network_category(self):
        """The rendered menu must mention the Network category."""
        from agent_tool_selection import (
            _discover_tools,
            display_categories_for_selection,
            group_tools_by_category,
        )

        groups = group_tools_by_category(_discover_tools())

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            display_categories_for_selection(groups)

        output = buffer.getvalue()
        self.assertIn("Network", output)
        self.assertIn("8 tools", output)


# ---------------------------------------------------------------------------
# The Shodan tools in the selection menu
# ---------------------------------------------------------------------------

class TestSecurityCategory(unittest.TestCase):
    """The Shodan tools must form the 'Security' category in the menu."""

    @classmethod
    def setUpClass(cls):
        from agent_tool_selection import _discover_tools, group_tools_by_category

        with _shodan_opt_in():
            cls.tools = _discover_tools()
            cls.groups = group_tools_by_category(cls.tools)

    def test_security_category_exists(self):
        self.assertIn(
            "Security",
            self.groups,
            "The 'Security' category is missing from the selection menu",
        )

    def test_security_category_holds_the_shodan_tools(self):
        security_names = {t.metadata.name for t in self.groups.get("Security", [])}
        self.assertEqual(
            security_names,
            SHODAN_READONLY_TOOL_NAMES,
            "The 'Security' category does not hold exactly the read-only Shodan tools",
        )

    def test_the_write_tools_are_not_in_the_menu(self):
        """The menu must not offer the credit-consuming tools by default."""
        security_names = {t.metadata.name for t in self.groups.get("Security", [])}
        self.assertEqual(
            security_names & SHODAN_MUTATING_TOOL_NAMES,
            set(),
            "The write-capable Shodan tools are exposed without the opt-in",
        )

    def test_every_shodan_tool_reaches_the_menu(self):
        names = {t.metadata.name for t in self.tools}
        self.assertEqual(
            SHODAN_READONLY_TOOL_NAMES - names,
            set(),
            "Some Shodan tools are missing from the selection menu",
        )

    def test_the_shodan_tools_are_not_spread_over_other_categories(self):
        """A Shodan tool must not be filed under a foreign category."""
        for category, tools in self.groups.items():
            if category == "Security":
                continue
            foreign = {t.metadata.name for t in tools} & SHODAN_READONLY_TOOL_NAMES
            self.assertEqual(
                foreign,
                set(),
                f"Shodan tools are grouped under '{category}': {sorted(foreign)}",
            )


class TestSecurityCategoryDescription(unittest.TestCase):
    """The Security summary must describe real capabilities."""

    def test_security_summary_is_meaningful(self):
        from toolkits.shodan_toolkit.agent_shodan_toolkit import (
            get_all_tools,
        )
        from agent_tool_selection import _build_category_description

        with _shodan_opt_in():
            summary = _build_category_description(get_all_tools())

        self.assertTrue(summary.startswith("Actions: "), summary)
        self.assertIn("discover", summary)
        self.assertIn("inspect", summary)
        self.assertIn("diagnose", summary)
        self.assertIn("execute", summary)

    def test_no_verb_fallback_leaks_into_the_summary(self):
        """Every tool must map to a canonical action, not a raw verb."""
        from toolkits.shodan_toolkit.agent_shodan_toolkit import (
            get_all_tools,
        )
        from agent_tool_selection import _build_category_description

        with _shodan_opt_in():
            summary = _build_category_description(get_all_tools())

        self.assertNotRegex(
            summary,
            r"(^|,\s*)get($|,)",
            f"the summary contains a raw verb fallback: {summary}",
        )


# ---------------------------------------------------------------------------
# Selecting the Security category end to end
# ---------------------------------------------------------------------------

class TestSelectingSecurity(unittest.TestCase):
    """Selecting the 'Security' category must return the Shodan tools."""

    def test_select_tools_by_category_returns_shodan_tools(self):
        from agent_tool_selection import select_tools_by_category

        with _shodan_opt_in():
            tools = select_tools_by_category(categories=["Security"])

        self.assertEqual(
            {t.metadata.name for t in tools},
            SHODAN_READONLY_TOOL_NAMES,
        )

    def test_select_tools_by_category_is_case_insensitive(self):
        from agent_tool_selection import select_tools_by_category

        with _shodan_opt_in():
            tools = select_tools_by_category(categories=["security"])

        self.assertEqual(
            {t.metadata.name for t in tools},
            SHODAN_READONLY_TOOL_NAMES,
        )

    def test_interactive_selection_picks_the_security_category(self):
        """Drive the interactive flow and pick the 'Security' index."""
        from agent_tool_selection import _discover_tools, group_tools_by_category

        with _shodan_opt_in():
            tools = _discover_tools()
            groups = group_tools_by_category(tools)
            categories = list(groups.keys())

            self.assertIn("Security", categories)
            index = categories.index("Security") + 1

            import builtins

            prompts: list[str] = []
            original_input = builtins.input

            def fake_input(prompt=""):
                prompts.append(prompt)
                return str(index)

            builtins.input = fake_input
            try:
                from agent_tool_selection import select_tools_interactively

                selected = select_tools_interactively(all_tools=tools)
            finally:
                builtins.input = original_input

        self.assertEqual(len(prompts), 1)
        self.assertEqual(
            {t.metadata.name for t in selected},
            SHODAN_READONLY_TOOL_NAMES,
        )

    def test_menu_displays_the_security_category(self):
        """The rendered menu must mention the Security category."""
        from agent_tool_selection import (
            _discover_tools,
            display_categories_for_selection,
            group_tools_by_category,
        )

        with _shodan_opt_in():
            groups = group_tools_by_category(_discover_tools())

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                display_categories_for_selection(groups)

        output = buffer.getvalue()
        self.assertIn("Security", output)
        self.assertIn("12 tools", output)

    def test_the_write_tools_join_the_menu_after_the_opt_in(self):
        """With the opt-in, the write-capable tools join the category."""
        from agent_tool_selection import (
            _discover_tools,
            display_categories_for_selection,
            group_tools_by_category,
        )

        with _shodan_opt_in("1"):
            groups = group_tools_by_category(_discover_tools())
            security_names = {t.metadata.name for t in groups.get("Security", [])}

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                display_categories_for_selection(groups)

        self.assertEqual(
            security_names,
            SHODAN_READONLY_TOOL_NAMES | SHODAN_MUTATING_TOOL_NAMES,
        )
        self.assertIn("16 tools", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
