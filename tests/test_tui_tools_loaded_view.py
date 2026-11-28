"""
The tools that are loaded, on the screen of the multi-window console.

The operator picked the tools at startup with ``--select`` and the only
place that showed the choice was the telemetry panel - and that row
names the **categories**: "Operating System, Project Management +1
more".  The names of the tools were nowhere.

The operator reported it on 2026-11-27:

    the tools are selected on start-up as it is and we can see what
    tools was selected by viewing tools using command \\tools, since for
    now I can see tools in the "Agent Telemetry & State" like this
    "Operating System, Project Management +1 more" which is not very
    informative

So the screen of the tools answers **two** questions at once: what the
agent can reach, and what it holds right now.  The tests below hold it
to that contract:

* the flat list of the tools marks the ones that are loaded;
* the loaded tools are named one by one, with their category;
* the menu of the categories says how many of the tools of a category
  are held;
* the screen never claims that a tool is loaded when it is not - the
  mode of the retriever holds nothing but the tools it pulled in;
* the truth comes from the state, and the state is filled in by the
  orchestrator.

Run with:
    pytest tests/test_tui_tools_loaded_view.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.tool_selection_view import (  # noqa: E402
    LOADED_MARK,
    NOT_LOADED_MARK,
    render_categories_markdown,
    render_loaded_tools_markdown,
    render_tool_list_markdown,
    scope_phrase,
)
from llama_index.core.tools import FunctionTool  # noqa: E402


# ---------------------------------------------------------------------------
# The tools of the tests
# ---------------------------------------------------------------------------


def _tool(name: str, category: str) -> FunctionTool:
    """Build a tool of a category, the way the toolkits build them."""

    def _fn() -> str:
        """Do a thing.  The tool is never called."""
        return "done"

    return FunctionTool.from_defaults(
        fn=_fn,
        name=name,
        description=f"Do a thing with the {category}. Category: {category}",
    )


OS_TOOLS = [
    _tool("read_file", "Operating System"),
    _tool("list_directory", "Operating System"),
]
GIT_TOOLS = [_tool("git_status", "Git")]
PROJECT_TOOLS = [_tool("create_project", "Project Management")]

ALL_TOOLS = OS_TOOLS + GIT_TOOLS + PROJECT_TOOLS

#: The tools the operator picked at startup.
SELECTED = ["read_file", "list_directory", "git_status"]

#: A skill tool: it is held by the agent and it is not in the menu.
SKILL_TOOL = "activate_skill"


def _groups():
    """The tools of the tests, grouped by category."""
    from agent_tool_selection import group_tools_by_category

    return group_tools_by_category(ALL_TOOLS)


# ---------------------------------------------------------------------------
# The state
# ---------------------------------------------------------------------------


class TestTheState(unittest.TestCase):
    """The state carries the tools that are loaded."""

    def test_it_holds_the_loaded_tools(self):
        state = TuiState()
        state.update_loaded_tools(["read_file", "git_status"])

        self.assertEqual(state.loaded_tools, ["read_file", "git_status"])

    def test_a_fresh_state_knows_nothing(self):
        """Nothing is known until it is measured."""
        self.assertEqual(TuiState().loaded_tools, [])

    def test_the_inventory_and_the_loaded_tools_are_two_things(self):
        """The inventory is what the agent can reach; the loaded tools
        are what it holds.  They are not the same field."""
        state = TuiState()
        state.update_tools(["a", "b", "c"], scope="indexed")
        state.update_loaded_tools(["a"])

        self.assertEqual(state.active_tools, ["a", "b", "c"])
        self.assertEqual(state.loaded_tools, ["a"])


# ---------------------------------------------------------------------------
# The flat list of the tools
# ---------------------------------------------------------------------------


class TestTheToolList(unittest.TestCase):
    """The list of the tools marks the ones that are loaded."""

    def test_it_marks_the_loaded_tools(self):
        text = render_tool_list_markdown(ALL_TOOLS, loaded=SELECTED)

        self.assertIn("`read_file`", text)
        self.assertIn(LOADED_MARK, text)

    def test_it_marks_the_tools_that_are_not_loaded(self):
        """A tool the agent does not hold is not marked."""
        text = render_tool_list_markdown(ALL_TOOLS, loaded=SELECTED)

        row = [line for line in text.splitlines() if "`create_project`" in line]
        self.assertTrue(row, "the tool is not on the screen")
        self.assertIn(NOT_LOADED_MARK, row[0])

    def test_it_says_how_many_tools_are_loaded(self):
        text = render_tool_list_markdown(ALL_TOOLS, loaded=SELECTED)

        self.assertIn("3 of 4", text)

    def test_it_lists_every_tool(self):
        """The list is the list of what is available - that is what it
        was before, and it stays."""
        text = render_tool_list_markdown(ALL_TOOLS, loaded=SELECTED)

        for tool in ALL_TOOLS:
            self.assertIn(f"`{tool.metadata.name}`", text)

    def test_without_the_loaded_tools_it_marks_none(self):
        """A screen that knows nothing marks nothing."""
        text = render_tool_list_markdown(ALL_TOOLS)

        self.assertIn("0 of 4", text)
        self.assertNotIn(LOADED_MARK, text)

    def test_it_says_how_the_agent_got_its_tools(self):
        """The scope is said in words, not as a code."""
        text = render_tool_list_markdown(ALL_TOOLS, loaded=SELECTED, scope="selected")

        self.assertIn("`--select`", text)


# ---------------------------------------------------------------------------
# The loaded tools, one by one
# ---------------------------------------------------------------------------


class TestTheLoadedTools(unittest.TestCase):
    """The loaded tools are named one by one."""

    def test_it_names_the_loaded_tools(self):
        text = render_loaded_tools_markdown(SELECTED, ALL_TOOLS, scope="selected")

        for name in SELECTED:
            self.assertIn(f"`{name}`", text)

    def test_it_names_the_category_of_a_loaded_tool(self):
        """The category is what the operator picked; the name of the
        tool is the detail behind it."""
        text = render_loaded_tools_markdown(SELECTED, ALL_TOOLS, scope="selected")

        self.assertIn("Operating System", text)
        self.assertIn("Git", text)

    def test_it_does_not_name_the_tools_that_are_not_loaded(self):
        text = render_loaded_tools_markdown(SELECTED, ALL_TOOLS, scope="selected")

        self.assertNotIn("`create_project`", text)

    def test_it_names_a_tool_that_is_not_in_the_menu(self):
        """A skill tool is held and it is not in the menu.  It is
        named, and it is named without a category - there is none."""
        text = render_loaded_tools_markdown(
            SELECTED + [SKILL_TOOL], ALL_TOOLS, scope="selected"
        )

        self.assertIn(f"`{SKILL_TOOL}`", text)

    def test_it_counts_the_loaded_tools(self):
        text = render_loaded_tools_markdown(SELECTED, ALL_TOOLS, scope="selected")

        self.assertIn("(3)", text)

    def test_without_a_loaded_tool_it_says_so(self):
        """A screen that says nothing is better than a screen that
        guesses."""
        text = render_loaded_tools_markdown([], ALL_TOOLS, scope="indexed")

        self.assertIn("No tool is loaded right now", text)

    def test_it_says_how_the_agent_got_them(self):
        """In the mode of the retriever the agent reaches for the tools
        it needs - the screen says that, and not that they are all
        there."""
        text = render_loaded_tools_markdown([], ALL_TOOLS, scope="indexed")

        self.assertIn("on demand", text)


# ---------------------------------------------------------------------------
# The menu of the categories
# ---------------------------------------------------------------------------


class TestTheCategoryMenu(unittest.TestCase):
    """The menu says how many of the tools of a category are held."""

    def test_it_counts_the_loaded_tools_of_a_category(self):
        text = render_categories_markdown(
            _groups(), len(ALL_TOOLS), loaded=SELECTED, scope="selected"
        )

        self.assertIn("2/2", text)

    def test_it_counts_the_category_that_is_not_held(self):
        text = render_categories_markdown(
            _groups(), len(ALL_TOOLS), loaded=SELECTED, scope="selected"
        )

        self.assertIn("0/1", text)

    def test_it_says_how_many_tools_are_loaded(self):
        text = render_categories_markdown(
            _groups(), len(ALL_TOOLS), loaded=SELECTED, scope="selected"
        )

        self.assertIn("3 of 4 tools", text)

    def test_a_tool_that_is_not_in_the_menu_is_not_counted(self):
        """The skill tools are not in the menu, and they are not
        counted against the tools of the menu."""
        text = render_categories_markdown(
            _groups(), len(ALL_TOOLS), loaded=SELECTED + [SKILL_TOOL], scope="selected"
        )

        self.assertIn("3 of 4 tools", text)

    def test_the_menu_is_still_a_menu(self):
        """The picker of the categories is still there."""
        text = render_categories_markdown(_groups(), len(ALL_TOOLS))

        self.assertIn("Startup Tool Selection", text)
        self.assertIn("Type your selection in the command bar", text)

    def test_without_the_loaded_tools_it_marks_no_category(self):
        """A menu that knows nothing counts nothing: no category of it
        carries a count of the tools that are held."""
        text = render_categories_markdown(_groups(), len(ALL_TOOLS))

        self.assertNotIn("0/2", text)
        self.assertNotIn("2/2", text)
        self.assertNotIn("Loaded now", text)


# ---------------------------------------------------------------------------
# The scope
# ---------------------------------------------------------------------------


class TestTheScope(unittest.TestCase):
    """The scope is said in the words of the operator."""

    def test_the_selected_scope_names_the_flag(self):
        self.assertIn("--select", scope_phrase("selected"))

    def test_the_loaded_scope_says_it(self):
        self.assertIn("upfront", scope_phrase("loaded"))

    def test_the_indexed_scope_says_it_is_on_demand(self):
        self.assertIn("on demand", scope_phrase("indexed"))

    def test_an_unknown_scope_says_something(self):
        """A scope that is not known still says what the screen shows."""
        self.assertTrue(scope_phrase("something-else"))


# ---------------------------------------------------------------------------
# The orchestrator
# ---------------------------------------------------------------------------


def _load_mw_agent():
    """Load agent-torvalds-mw.py as an importable module."""
    import importlib.util

    path = ROOT / "agent-torvalds-mw.py"
    spec = importlib.util.spec_from_file_location("agent_torvalds_mw", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_torvalds_mw"] = module
    spec.loader.exec_module(module)
    return module


class TestTheOrchestrator(unittest.TestCase):
    """The orchestrator measures the tools the agent holds."""

    @classmethod
    def setUpClass(cls):
        cls.mw = _load_mw_agent()

    def _create_agent(self, **kwargs):
        """Build an agent without a model and without a session.

        The agent is built for the tools it holds, and that is all this
        test needs: the model is not called, and the session of the
        chat manager is not needed for it.

        Args:
            **kwargs: The arguments of the agent.

        Returns:
            The names of the tools the agent holds, as they were handed
            over to the caller.
        """
        from unittest.mock import MagicMock, patch

        class _FakeAgent:
            """The agent of the tests: it holds the tools and it is
            never called."""

            def __init__(self, **kwargs):
                self.tools = list(kwargs.get("tools") or [])

        held: list = []

        with patch.object(self.mw, "apply_context_window", lambda llm: None), \
             patch.object(self.mw, "get_memory_buffer", lambda *a, **k: None), \
             patch.object(self.mw, "build_system_prompt", lambda *a, **k: "prompt"), \
             patch.object(self.mw, "build_skills", lambda *a, **k: ([], "", [])), \
             patch.object(self.mw, "RetryingOllama", lambda *a, **k: MagicMock()), \
             patch.object(self.mw, "HITLFunctionAgent", _FakeAgent):
            self.mw.create_agent(
                is_tui=False,
                on_loaded_tools=held.extend,
                **kwargs,
            )

        return held

    def test_the_selected_tools_are_the_tools_the_agent_holds(self):
        """``--select`` gives the agent the tools the operator picked,
        and those are the tools it holds."""
        selected = [tool for tool in ALL_TOOLS if tool.metadata.name in SELECTED]

        held = self._create_agent(use_retriever=False, tools=selected)

        names = [name for name in held if name in SELECTED]
        self.assertEqual(sorted(names), sorted(SELECTED))

    def test_every_tool_is_held_when_they_are_loaded_upfront(self):
        """``--full`` gives the agent every tool, and the agent holds
        every tool."""
        held = self._create_agent(use_retriever=False, tools=list(ALL_TOOLS))

        for tool in ALL_TOOLS:
            self.assertIn(tool.metadata.name, held)

    def test_the_retriever_hands_out_the_tools_it_writes_down(self):
        """The tools the retriever hands out are the tools the agent
        holds for that question - and the recorder writes them down."""
        import asyncio

        from agent_tool_retriever import RecordingObjectRetriever

        recorded: list = []

        class _Node:
            def __init__(self, tool):
                self.node = tool

        class _InnerRetriever:
            async def aretrieve(self, query_bundle):
                return [_Node(OS_TOOLS[0])]

        class _Mapping:
            def from_node(self, node):
                return node

        retriever = RecordingObjectRetriever(
            retriever=_InnerRetriever(),
            object_node_mapping=_Mapping(),
            on_retrieve=recorded.extend,
        )

        tools = asyncio.run(retriever.aretrieve("what is in the working copy?"))

        self.assertEqual([tool.metadata.name for tool in tools], ["read_file"])
        self.assertEqual([tool.metadata.name for tool in recorded], ["read_file"])

    def test_a_broken_recorder_does_not_break_the_retriever(self):
        """A note that cannot be written is a note that is lost - the
        run goes on."""
        from agent_tool_retriever import RecordingObjectRetriever

        def _broken(_tools):
            raise RuntimeError("the note cannot be written")

        retriever = RecordingObjectRetriever(
            retriever=None,
            object_node_mapping=None,
            on_retrieve=_broken,
        )
        retriever._record([_tool("read_file", "Operating System")])


if __name__ == "__main__":
    unittest.main()
