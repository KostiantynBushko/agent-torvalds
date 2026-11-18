"""
The tools the operator selected, on the screen of the multi-window console.

The telemetry panel showed a row called "Toolkits", and the row showed
"Git, OS, DB, Math" - four toolkits that were written into the source.
They were the same four toolkits whatever the operator had selected, on
every machine, in every mode: the row was a decoration, and it looked
like a measurement.

The operator reported it on 2026-11-18: *"the Toolkits in telemetry view
looks like it does not represent real selected tools"*.

The row is a measurement now.  The orchestrator hands over the names of
the tools the agent really has - the ones the operator picked with
``--select`` - and the panel shows what it is told.  When nothing is
known, the panel says so instead of guessing.

The operator looked at the row on 2026-11-18 and said what was missing:
*"In the telemetry window I would like to see just common name for
selected group, like Operating System, System, Security and so on."*
The operator picked a **category**, so the panel names the category.

The tests below hold the row to that contract:

* the panel names the groups the operator selected;
* the panel says how many tools there are, and how the agent got them;
* the names of the tools are not the names of the groups;
* the four toolkits that were written into the source are gone.

Run with:
    pytest tests/test_tui_selected_tools_row.py -v
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.telemetry_view import TelemetryView  # noqa: E402


#: The toolkits that were written into the source of the panel.
HARD_CODED_LIST = ["Git", "OS", "DB", "Math"]

#: The same list, as the panel rendered it.
HARD_CODED_TOOLKITS = ", ".join(HARD_CODED_LIST)


def _load_mw_agent():
    """Load agent-torvalds-mw.py as an importable module."""
    path = ROOT / "agent-torvalds-mw.py"
    spec = importlib.util.spec_from_file_location("agent_torvalds_mw", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_torvalds_mw"] = module
    spec.loader.exec_module(module)
    return module


def _mentions(text: str, name: str) -> bool:
    """Whether the panel names the tool.

    The name is matched as a word: the tool "ls" is inside the word
    "Tools", and a row that names the word "Tools" does not name the
    tool "ls".
    """
    return bool(re.search(rf"\b{re.escape(name)}\b", text))


def _render_text(state, width: int = 80) -> str:
    """Render the telemetry panel and return it as plain text."""
    from rich.console import Console

    console = Console(width=width, color_system=None)
    panel = TelemetryView().render(state)
    lines = console.render_lines(panel, console.options.update(width=width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


# ---------------------------------------------------------------------------
# The state
# ---------------------------------------------------------------------------


class TestTheState(unittest.TestCase):
    """The state carries the measurement to the panel."""

    def test_it_holds_the_tools(self):
        """The names of the tools arrive in the state."""
        state = TuiState()
        state.update_tools(["get_resources", "get_identity"], scope="selected")

        self.assertEqual(state.active_tools, ["get_resources", "get_identity"])
        self.assertEqual(state.active_tool_scope, "selected")

    def test_it_holds_the_groups(self):
        """The groups the operator picked arrive in the state."""
        state = TuiState()
        state.update_tools(
            ["get_resources", "get_identity"],
            scope="selected",
            groups=["Operating System"],
        )

        self.assertEqual(state.active_tool_groups, ["Operating System"])

    def test_a_fresh_state_knows_nothing(self):
        """Nothing is known until it is measured."""
        state = TuiState()

        self.assertEqual(state.active_tools, [])
        self.assertEqual(state.active_tool_scope, "")
        self.assertEqual(state.active_tool_groups, [])

    def test_the_scope_is_a_word(self):
        """The scope is never a number that has to be read."""
        state = TuiState()
        state.update_tools(["get_resources"], scope=42)

        self.assertEqual(state.active_tool_scope, "42")


# ---------------------------------------------------------------------------
# The panel
# ---------------------------------------------------------------------------


class TestTheRow(unittest.TestCase):
    """What the panel shows."""

    def test_it_names_the_groups_the_operator_selected(self):
        """The row names the groups the operator picked.

        The operator picked a category, so the panel names the category.
        """
        state = TuiState()
        state.update_tools(
            ["mikrotik_get_resources", "mikrotik_get_identity"],
            scope="selected",
            groups=["Network"],
        )

        text = _render_text(state)

        self.assertIn("Network", text)

    def test_the_names_of_the_tools_are_not_the_names_of_the_groups(self):
        """The tools are the detail behind the group - not the headline."""
        state = TuiState()
        state.update_tools(
            ["mikrotik_get_resources", "mikrotik_get_identity"],
            scope="selected",
            groups=["Network"],
        )

        text = _render_text(state)

        self.assertFalse(_mentions(text, "mikrotik_get_resources"))
        self.assertFalse(_mentions(text, "mikrotik_get_identity"))

    def test_without_the_groups_it_names_the_tools(self):
        """A row that knows less says what it does know."""
        state = TuiState()
        state.update_tools(
            ["mikrotik_get_resources", "mikrotik_get_identity"], scope="selected"
        )

        text = _render_text(state)

        self.assertIn("mikrotik_get_resources", text)
        self.assertIn("mikrotik_get_identity", text)

    def test_it_says_how_many_tools_there_are(self):
        """The number of tools is on the screen."""
        state = TuiState()
        state.update_tools(["a_tool", "another_tool"], scope="selected")

        text = _render_text(state)

        self.assertIn("2 selected", text)

    def test_it_says_how_the_agent_got_them(self):
        """The count names its own source - it is never read as something else."""
        state = TuiState()
        state.update_tools(["a_tool"] * 134, scope="loaded")

        text = _render_text(state)

        self.assertIn("134 loaded", text)

    def test_the_tools_that_are_not_shown_are_counted(self):
        """The panel has room for a few names - and says how many are left."""
        shown = TelemetryView.TOOL_NAMES_SHOWN
        tools = [f"tool_number_{index}" for index in range(shown + 2)]

        state = TuiState()
        state.update_tools(tools, scope="selected")

        text = _render_text(state)

        self.assertIn(tools[0], text)
        self.assertIn("+2 more", text)

    def test_the_groups_that_are_not_shown_are_counted(self):
        """The groups that do not fit are counted - and not cut."""
        shown = TelemetryView.TOOL_NAMES_SHOWN
        groups = [f"Group number {index}" for index in range(shown + 2)]

        state = TuiState()
        state.update_tools(
            [f"tool_number_{index}" for index in range(shown + 2)],
            scope="selected",
            groups=groups,
        )

        text = _render_text(state)

        self.assertIn(groups[0], text)
        self.assertIn("+2 more", text)

    def test_the_tools_are_not_named_in_the_other_modes(self):
        """In the other modes the operator picked no tool at all."""
        state = TuiState()
        state.update_tools(["tool_one", "tool_two"], scope="indexed")

        text = _render_text(state)

        self.assertIn("2 indexed", text)
        self.assertNotIn("tool_one", text)

    def test_without_tools_it_shows_a_dash(self):
        """A row that guesses is worse than a row that says nothing."""
        text = _render_text(TuiState())

        self.assertIn("—", text)

    def test_it_does_not_show_the_toolkits_that_were_written_down(self):
        """The four toolkits of the source are gone."""
        state = TuiState()
        state.update_tools(["mikrotik_get_resources"], scope="selected")

        text = _render_text(state)

        self.assertNotIn(HARD_CODED_TOOLKITS, text)
        self.assertNotIn("DB", text)

    def test_the_row_is_named_tools(self):
        """The operator knows what the row is about."""
        text = _render_text(TuiState())

        self.assertIn("Tools", text)


# ---------------------------------------------------------------------------
# The source
# ---------------------------------------------------------------------------


class TestTheSource(unittest.TestCase):
    """The list that was written into the source is not there any more."""

    def _written_toolkits(self, path: Path) -> list:
        """The toolkits that are written into the source as a literal.

        The check reads the **code**, not the text: a comment that tells
        the story of the defect may name the four toolkits, but a literal
        that hands them to the panel may not.
        """
        tree = ast.parse(path.read_text())
        found = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == HARD_CODED_TOOLKITS:
                found.append([node.value])

            if isinstance(node, ast.List):
                names = [
                    element.value
                    for element in node.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                ]
                if names and len(names) == len(node.elts):
                    found.append(names)

        return found

    def test_the_panel_does_not_write_the_toolkits_down(self):
        """The panel renders what it is told."""
        path = ROOT / "components" / "tui" / "telemetry_view.py"

        self.assertNotIn(HARD_CODED_LIST, self._written_toolkits(path))

    def test_the_orchestrator_does_not_write_the_toolkits_down(self):
        """The orchestrator measures the tools."""
        path = ROOT / "agent-torvalds-mw.py"

        self.assertNotIn(HARD_CODED_LIST, self._written_toolkits(path))


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------


class TestTheOrchestrator(unittest.TestCase):
    """The orchestrator measures the tools the agent will really have."""

    @classmethod
    def setUpClass(cls):
        cls.mw = _load_mw_agent()

    def test_the_retriever_reaches_every_tool(self):
        """The retriever mode reaches the tools of every toolkit."""
        inventory = self.mw._agent_tool_inventory(True)

        self.assertTrue(inventory, "the retriever has no tools")

    def test_the_selected_tools_are_the_tools_of_the_agent(self):
        """``--select`` gives the agent the tools the operator picked."""
        from agent_tool_selection import _discover_tools, group_tools_by_category

        groups = group_tools_by_category(_discover_tools())
        selected = groups.get("Database", [])

        if not selected:
            self.skipTest("the database toolkit is not installed")

        inventory = self.mw._agent_tool_inventory(False, selected)

        self.assertEqual(
            [tool.metadata.name for tool in inventory],
            [tool.metadata.name for tool in selected],
        )

    def test_the_panel_names_the_tools_of_the_inventory(self):
        """What the panel shows is what the agent has."""
        from agent_tool_selection import _discover_tools, group_tools_by_category

        groups = group_tools_by_category(_discover_tools())
        selected = groups.get("Database", [])

        if not selected:
            self.skipTest("the database toolkit is not installed")

        inventory = self.mw._agent_tool_inventory(False, selected)

        state = TuiState()
        state.update_tools(
            [tool.metadata.name for tool in inventory], scope="selected"
        )

        text = _render_text(state)

        self.assertIn(selected[0].metadata.name, text)
        self.assertIn(f"{len(selected)} selected", text)

    def test_the_groups_are_the_categories_of_the_selected_tools(self):
        """The groups are the categories the operator picked."""
        from agent_tool_selection import _discover_tools, group_tools_by_category

        groups = group_tools_by_category(_discover_tools())
        selected = groups.get("Database", [])

        if not selected:
            self.skipTest("the database toolkit is not installed")

        inventory = self.mw._agent_tool_inventory(False, selected)

        self.assertEqual(
            self.mw._selected_tool_groups(inventory), ["Database"]
        )

    def test_the_panel_names_the_groups_of_the_inventory(self):
        """The row names the group the operator picked."""
        from agent_tool_selection import _discover_tools, group_tools_by_category

        groups = group_tools_by_category(_discover_tools())
        selected = groups.get("Database", [])

        if not selected:
            self.skipTest("the database toolkit is not installed")

        inventory = self.mw._agent_tool_inventory(False, selected)

        state = TuiState()
        state.update_tools(
            [tool.metadata.name for tool in inventory],
            scope="selected",
            groups=self.mw._selected_tool_groups(inventory),
        )

        text = _render_text(state)

        self.assertIn("Database", text)
        self.assertFalse(_mentions(text, selected[0].metadata.name))
        self.assertIn(f"{len(selected)} selected", text)


if __name__ == "__main__":
    unittest.main()
