"""
Every tool call shows its arguments in the *Workflow & Tool Progress* pane.

The pane shows the tool that runs and, under its name, the line that
says what it works on.  That line carried the arguments of **one**
tool -- the shell command -- and the call of every other tool was a
name with nothing under it:

    ✔ write_file (3ms)

The operator asked on 2026-11-23 for the same for every tool:

    currently only execute shell command shows a list of arguments in
    Workflow & Tool Progress window, I think the same must be applied
    to all tools call

The check is in three parts:

  * the **rule** -- how the arguments of a call become the text of the
    line: one argument is shown alone, several arguments are named, a
    value that is longer than the pane is folded with a marker that says
    how much of it was left out, and an argument that carries a
    **payload** is measured and never printed;
  * the **pane** -- the real panel, with the real state, rendered the
    way the terminal renders it;
  * the **state** -- the arguments are kept as they were given, and the
    home of the operator is hidden on the screen and not in the state.

Run with:
    pytest tests/test_tui_tool_arguments.py -v
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from rich.cells import cell_len  # noqa: E402
from rich.console import Console  # noqa: E402

from components.tui.layout_manager import progress_pane_width  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.tool_arguments import (  # noqa: E402
    MAX_VALUE_LINES,
    format_arguments,
    is_a_payload,
    the_folded_marker,
    the_measure_of_a_value,
    the_size_in_bytes,
)

#: The width the panel is rendered at.
WIDTH = 60

#: The command of the operator: the one that has to stay whole.
COMMAND = (
    "cd ~/projects/agent-torvalds && git status --short && "
    "python -m pytest tests/ -x"
)

#: The tools of the agent, and the arguments every one of them is
#: called with.  Every one of them has to show its arguments.
THE_CALLS = (
    ("execute_shell_command", {"command": "ls -la"}),
    ("read_file", {"path": "/tmp/notes.md"}),
    ("write_file", {"path": "/tmp/notes.md", "content": "hello"}),
    ("mkdir", {"path": "/tmp/folder"}),
    ("cp", {"src": "/tmp/a.md", "dst": "/tmp/b.md"}),
    ("rm", {"path": "/tmp/old.md"}),
)


def a_state_with(tool_name: str, arguments: dict) -> TuiState:
    """A state that carries a tool that was called."""
    state = TuiState()
    state.update_tool_start(tool_name, arguments)
    return state


def render(state: TuiState, width: int = WIDTH) -> str:
    """Render the progress panel and return it as plain text."""
    console = Console(width=width, color_system=None)
    panel = ProgressView().render(state, width=width)
    lines = console.render_lines(panel, console.options.update(width=width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


class TestTheRule:
    """The arguments of a call become the text of the line."""

    def test_a_call_without_arguments_has_no_detail(self):
        assert format_arguments({}) == ""

    def test_one_argument_is_shown_alone(self):
        """The name of the only argument would only add noise."""
        assert format_arguments({"command": "git status"}) == "git status"

    def test_several_arguments_are_named(self):
        """Two arguments are told apart by their names."""
        detail = format_arguments({"path": "/tmp/a.md", "content": "hello"})

        assert detail == "path=/tmp/a.md\ncontent=1 line, 5 B"

    def test_every_argument_is_shown(self):
        detail = format_arguments(
            {"src": "/tmp/a.md", "dst": "/tmp/b.md", "overwrite": True}
        )

        assert "src=/tmp/a.md" in detail
        assert "dst=/tmp/b.md" in detail
        assert "overwrite=True" in detail

    def test_an_argument_that_was_not_given_is_not_shown(self):
        """A tool that is called with ``path=None`` was called without a path."""
        detail = format_arguments({"path": None, "content": "hello"})

        assert "path" not in detail
        assert detail == "content=1 line, 5 B"

    def test_the_order_of_the_arguments_is_the_order_they_were_given_in(self):
        detail = format_arguments({"dst": "/tmp/b.md", "src": "/tmp/a.md"})

        assert detail.split("\n") == ["dst=/tmp/b.md", "src=/tmp/a.md"]

    def test_a_value_that_is_not_a_string_is_shown_as_it_is(self):
        detail = format_arguments({"timeout": 30, "shell": "/bin/bash"})

        assert detail == "timeout=30\nshell=/bin/bash"

    def test_one_argument_that_is_not_a_string_is_shown_alone(self):
        assert format_arguments({"timeout": 30}) == "30"

    def test_the_line_breaks_of_a_value_are_kept(self):
        """A value may be a script of more than one line."""
        detail = format_arguments({"command": "first\nsecond"})

        assert detail == "first\nsecond"

    def test_a_value_that_is_longer_than_the_pane_is_folded(self):
        """A script that is long is not a line of the pane."""
        value = "\n".join(f"line {number}" for number in range(20))

        lines = format_arguments(
            {"path": "/tmp/a.md", "command": value}
        ).split("\n")

        assert len(lines) == MAX_VALUE_LINES + 2, "the value was not folded"
        assert lines[0] == "path=/tmp/a.md"
        assert lines[1] == "command=line 0"
        assert lines[-1] == the_folded_marker(20 - MAX_VALUE_LINES)

    def test_the_marker_says_how_many_lines_were_left_out(self):
        value = "\n".join(f"line {number}" for number in range(20))

        detail = format_arguments({"command": value})

        assert f"{20 - MAX_VALUE_LINES} more lines" in detail

    def test_one_line_that_was_left_out_is_said_in_the_singular(self):
        value = "\n".join(f"line {number}" for number in range(7))

        detail = format_arguments({"command": value})

        assert "1 more line …" in detail

    def test_a_value_that_fits_is_not_folded(self):
        value = "\n".join(f"line {number}" for number in range(3))

        detail = format_arguments({"command": value})

        assert "more lines" not in detail

    def test_the_name_of_a_folded_value_is_on_its_first_line(self):
        """The operator knows which argument was folded."""
        value = "\n".join(f"line {number}" for number in range(20))

        detail = format_arguments({"path": "/tmp/a.md", "command": value})

        assert detail.split("\n")[1].startswith("command=")

    def test_the_arguments_that_are_not_a_mapping_are_not_arguments(self):
        assert format_arguments("path=/tmp") == ""
        assert format_arguments(None) == ""


class TestThePayload:
    """An argument that carries a body is measured, and never printed."""

    def test_a_payload_is_not_printed(self):
        """The text of a payload is not on the screen of the pane."""
        detail = format_arguments(
            {"path": "/tmp/.env", "content": "API_KEY=sk-live-abc123"}
        )

        assert "sk-live-abc123" not in detail
        assert "API_KEY" not in detail

    def test_a_payload_is_measured(self):
        """The measure says how much of the payload there is."""
        detail = format_arguments({"path": "/tmp/notes.md", "content": "hello"})

        assert detail == "path=/tmp/notes.md\ncontent=1 line, 5 B"

    def test_a_payload_keeps_its_name_when_it_is_the_only_argument(self):
        """A measure without a name says nothing."""
        detail = format_arguments({"content": "hello"})

        assert detail == "content=1 line, 5 B"

    def test_the_command_of_the_shell_is_not_measured(self):
        """The command is the act, and it is shown whole."""
        detail = format_arguments({"command": "git status"})

        assert detail == "git status"

    def test_the_measure_of_a_text_says_the_lines_and_the_size(self):
        value = "\n".join(f"line {number}" for number in range(20))

        measure = the_measure_of_a_value(value)

        assert measure.startswith("20 lines, ")
        assert measure.endswith(" B")

    def test_the_measure_of_an_empty_text_says_nothing(self):
        assert the_measure_of_a_value("") == "0 lines, 0 B"

    def test_the_measure_of_a_list_says_the_items(self):
        assert the_measure_of_a_value([1, 2, 3]) == "3 items"

    def test_the_measure_of_a_mapping_says_the_keys(self):
        assert the_measure_of_a_value({"a": "1", "b": "2"}) == "2 keys"

    def test_the_measure_of_a_number_is_the_number(self):
        """There is nothing in a number that has to be hidden."""
        assert the_measure_of_a_value(30) == "30"

    def test_a_size_is_said_in_the_unit_that_fits(self):
        assert the_size_in_bytes(512) == "512 B"
        assert the_size_in_bytes(1024) == "1.0 KB"
        assert the_size_in_bytes(1024 * 1024) == "1.0 MB"

    def test_the_environment_of_a_command_is_not_printed(self):
        """The keys of an environment are not the values of it."""
        detail = format_arguments(
            {"command": "pytest", "env_vars": {"API_KEY": "sk-live-abc123"}}
        )

        assert "sk-live-abc123" not in detail
        assert "env_vars=1 keys" in detail


# ---------------------------------------------------------------------------
# The pane
# ---------------------------------------------------------------------------


class TestThePane:
    """The pane shows the arguments of every tool call."""

    def test_every_tool_shows_its_arguments(self):
        """Every call of every tool shows what it was called with."""
        for tool_name, arguments in THE_CALLS:
            text = render(a_state_with(tool_name, arguments))

            for name, value in arguments.items():
                if is_a_payload(name):
                    # A payload is measured, and never printed.
                    assert f"{name}=" in text, (
                        f"the pane does not show the measure of the "
                        f"payload of {tool_name}: {text!r}"
                    )
                    continue
                assert str(value) in text, (
                    f"the pane does not show the arguments of "
                    f"{tool_name}: {text!r}"
                )

    def test_a_tool_that_is_not_the_shell_shows_its_arguments(self):
        """The complaint of the operator, as it is seen."""
        text = render(a_state_with("read_file", {"path": "/tmp/notes.md"}))

        assert "/tmp/notes.md" in text, f"the pane shows nothing: {text!r}"

    def test_the_arguments_of_a_call_with_several_of_them_are_named(self):
        text = render(
            a_state_with("write_file", {"path": "/tmp/a.md", "content": "hi"})
        )

        assert "path=/tmp/a.md" in text, f"the pane shows no name: {text!r}"
        assert "content=1 line, 2 B" in text, f"the pane shows no name: {text!r}"

    def test_the_command_of_the_shell_is_still_shown_alone(self):
        """The look of the command does not change."""
        text = render(a_state_with("execute_shell_command", {"command": "git status"}))

        assert "└ git status" in text, f"the command is not shown alone: {text!r}"

    def test_the_whole_command_is_still_on_the_screen(self):
        text = render(a_state_with("execute_shell_command", {"command": COMMAND}))

        for word in ("cd", "git", "status", "--short", "python", "pytest", "-x"):
            assert word in text, f"the pane does not show {word!r}: {text!r}"

    def test_the_home_of_the_operator_is_hidden_in_the_arguments(self):
        """The home is hidden in every argument, and not only in the command."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            return

        text = render(a_state_with("read_file", {"path": f"{home}/notes.md"}))

        assert home not in text, f"the pane shows the home: {text!r}"
        assert "~/notes.md" in text, f"the pane does not show ~/...: {text!r}"

    def test_a_long_value_is_folded_on_the_screen(self):
        """The pane says how much of the value was left out."""
        value = "\n".join(f"line {number}" for number in range(50))

        text = render(
            a_state_with("execute_shell_command", {"command": value})
        )

        assert "more lines" in text, f"the value was not folded: {text!r}"
        assert "line 0" in text, f"the head of the value is gone: {text!r}"

    def test_a_payload_is_not_printed_on_the_screen(self):
        """A secret that is written in a file is not on the screen."""
        text = render(
            a_state_with(
                "write_file",
                {"path": "/tmp/.env", "content": "API_KEY=sk-live-abc123"},
            )
        )

        assert "sk-live-abc123" not in text, (
            f"the pane shows the secret of the payload: {text!r}"
        )
        assert "path=/tmp/.env" in text, f"the pane shows no path: {text!r}"
        assert "content=" in text, f"the pane shows no measure: {text!r}"

    def test_no_line_of_the_pane_is_wider_than_the_pane(self):
        """The detail of every tool is split to the width of the pane."""
        for console_width in (80, 120, 160):
            pane_width = progress_pane_width(console_width)
            for tool_name, arguments in THE_CALLS:
                text = render(a_state_with(tool_name, arguments), pane_width)
                for line in text.split("\n"):
                    assert cell_len(line) <= pane_width, (
                        f"the line is {cell_len(line)} cells wide and the "
                        f"pane is {pane_width} cells wide: {line!r}"
                    )


# ---------------------------------------------------------------------------
# The state
# ---------------------------------------------------------------------------


class TestTheState:
    """The state keeps the arguments as they were given."""

    def test_the_arguments_are_kept_whole(self):
        arguments = {"path": "/tmp/a.md", "content": "hello\nworld"}

        state = a_state_with("write_file", arguments)

        assert state.task_stack.tasks[0].arguments == arguments

    def test_the_state_keeps_the_real_path(self):
        """The agent works with the path of the machine, and keeps it."""
        state = a_state_with("read_file", {"file_path": "/tmp/notes.md"})

        arguments = state.task_stack.tasks[0].arguments
        assert arguments["file_path"] == "/tmp/notes.md"

    def test_the_arguments_of_the_call_are_not_changed(self):
        """The state keeps a copy: the caller may change its own dict."""
        arguments = {"path": "/tmp/a.md"}

        state = a_state_with("read_file", arguments)
        arguments["path"] = "/tmp/other.md"

        assert state.task_stack.tasks[0].arguments["path"] == "/tmp/a.md"


# ---------------------------------------------------------------------------
# The call of the workflow
# ---------------------------------------------------------------------------


def a_consumer_with(state: TuiState):
    """A consumer of the events of the workflow, wired to the state.

    It is the wiring the TUI uses: the consumer of the events, and the
    adapter that hands the tool calls over to the state.
    """
    from components.event_consumer import EventConsumer
    from components.spinner_controller import SpinnerController
    from components.state_handler import StateHandler
    from components.tui.state_bridge import TuiEventAdapter

    console = Console(file=io.StringIO())
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console),
        state_handler=StateHandler(),
        console=console,
    )
    TuiEventAdapter(state).register_with_event_consumer(consumer)
    return consumer


class TestTheCallOfTheWorkflow:
    """The arguments of the tools the workflow calls reach the pane.

    The other checks of this file feed the state directly.  This one
    drives the **real** event of the framework -- the ``ToolCall`` the
    workflow publishes -- through the **real** consumer and the **real**
    adapter, and reads the pane that comes out of it.

    The seam between the workflow and the pane is where the arguments
    could be lost, and it is the place the operator looks at: the
    arguments of every call of the workflow must be on the screen.
    """

    def test_the_arguments_of_the_event_of_the_workflow_are_on_the_screen(self):
        from llama_index.core.agent.workflow import ToolCall

        state = TuiState()
        consumer = a_consumer_with(state)

        asyncio.run(
            consumer._handle_event(
                ToolCall(
                    tool_name="write_file",
                    tool_kwargs={
                        "path": "/tmp/notes.md",
                        "content": "hello",
                    },
                    tool_id="call-1",
                )
            )
        )

        text = render(state)
        assert "write_file" in text, f"the pane shows no tool: {text!r}"
        assert "path=/tmp/notes.md" in text, f"the pane shows no path: {text!r}"
        assert "content=1 line, 5 B" in text, f"the pane shows no measure: {text!r}"
        assert "hello" not in text, f"the pane shows the payload: {text!r}"

    def test_the_command_of_the_shell_is_whole_through_the_workflow(self):
        """The look of the command does not change on the way."""
        from llama_index.core.agent.workflow import ToolCall

        state = TuiState()
        consumer = a_consumer_with(state)

        asyncio.run(
            consumer._handle_event(
                ToolCall(
                    tool_name="execute_shell_command",
                    tool_kwargs={"command": COMMAND},
                    tool_id="call-1",
                )
            )
        )

        text = render(state)
        assert "└ cd ~/projects" in text, f"the command is not whole: {text!r}"

    def test_the_arguments_stay_on_the_screen_when_the_call_is_done(self):
        """The answer of the tool does not take the arguments away."""
        from llama_index.core.agent.workflow import ToolCall, ToolCallResult
        from llama_index.core.tools import ToolOutput

        state = TuiState()
        consumer = a_consumer_with(state)

        asyncio.run(
            consumer._handle_event(
                ToolCall(
                    tool_name="read_file",
                    tool_kwargs={"path": "/tmp/notes.md"},
                    tool_id="call-1",
                )
            )
        )
        asyncio.run(
            consumer._handle_event(
                ToolCallResult(
                    tool_name="read_file",
                    tool_kwargs={"path": "/tmp/notes.md"},
                    tool_output=ToolOutput(
                        tool_name="read_file",
                        raw_input={"path": "/tmp/notes.md"},
                        raw_output="the notes",
                    ),
                    return_direct=False,
                    tool_id="call-1",
                )
            )
        )

        text = render(state)
        assert "read_file" in text, f"the pane shows no tool: {text!r}"
        assert "/tmp/notes.md" in text, f"the pane shows no path: {text!r}"
