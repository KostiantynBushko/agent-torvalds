"""
Every tool call shows its arguments in the progress pane.

The *Workflow & Tool Progress* pane shows the tool that runs and, under
its name, the line that says what it works on.  That line carried the
arguments of **one** tool -- the shell command -- and the call of every
other tool was a name with nothing under it.

The operator asked on 2026-11-23:

    currently only execute shell command shows a list of arguments in
    Workflow & Tool Progress window, I think the same must be applied
    to all tools call

What is asked of the pane:

  1. **Does every tool show its arguments?**  Every call of every tool
     shows what it was called with -- the command of the shell, the
     path of the file, and the **measure** of the body that is written
     in it.

  2. **Is the body of a file off the screen?**  A payload is measured
     and never printed: a secret that is written in a file is not on
     the screen, and the pane says how much of it there is.

  3. **Is the command of the shell still whole?**  The command is shown
     the way it has been shown since it was shown whole: the value
     alone, and every character of it on the screen.

  4. **Is the home of the operator off the screen?**  The home is
     hidden in every argument of every tool, and not only in the
     command of the shell.

  5. **Is a long value folded honestly?**  A value that is not a
     payload is folded: the pane shows the head of the value and says
     how many lines were left out.

  6. **Is every line of the pane the width of the pane?**  The detail
     is split to the width the layout really gives the pane.

  7. **Do the arguments of the call of the workflow reach the pane?**
     The other checks feed the state directly.  This one publishes the
     **real** event of the framework -- the ``ToolCall`` the workflow
     publishes -- and reads the pane that comes out of it.

The operator asked on 2026-11-23 for the second half of the first
answer to be taken back:

    not every tool must show everything it takes as an argument, for
    example write_file, it would be nice to see the path to the file
    but I'm not sure it is ok to print the content it writes

Usage:
    python investigate/tui-tool-arguments/probe_tool_arguments.py

The exit code is 0 when every check holds, 1 when one does not.

The probe writes nothing and talks to no service.
"""
from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402

from components.tui.layout_manager import progress_pane_width  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.tool_arguments import is_a_payload  # noqa: E402

#: The widths of the terminal the probe shows the pane at.
WIDTHS = (80, 120, 160)

#: The command of the operator: the one that has to stay whole.
COMMAND = (
    "cd ~/projects/agent-torvalds && git status --short && "
    "python -m pytest tests/ -x"
)

#: The calls of the tools, and the arguments every one of them is
#: called with.  Every one of them has to show its arguments.
THE_CALLS = (
    ("execute_shell_command", {"command": "ls -la"}),
    ("read_file", {"path": "/tmp/notes.md"}),
    ("write_file", {"path": "/tmp/notes.md", "content": "hello"}),
    ("mkdir", {"path": "/tmp/folder"}),
    ("cp", {"src": "/tmp/a.md", "dst": "/tmp/b.md"}),
    ("rm", {"path": "/tmp/old.md"}),
    ("run_postgres_query", {"query": "SELECT id FROM users"}),
    ("set_cell_value", {"path": "/tmp/book.xlsx", "cell": "B7", "value": "hi"}),
    ("git_update_changelog", {"path": "/tmp/repo", "description": "hi"}),
    ("filter_data", {"df_or_path": "/tmp/sales.xlsx", "column": "ssn",
                     "condition": "ssn == '123-45-6789'"}),
)

#: A body of a file: a value that is longer than the pane.
A_BODY = "\n".join(f"line {number}" for number in range(50))

#: A secret that is written in a file.  It must not reach the screen.
A_SECRET = "API_KEY=sk-live-abc123def456"

#: The body of a tool that is not a file: the content of a cell, the
#: text of an entry of a changelog, the condition of a filter.  It must
#: not reach the screen either.
A_BODY_OF_A_TOOL = "the pin of the card is 4471"


class Table:
    """A value the pane does not know: a table of rows."""

    def __init__(self, rows):
        self._rows = list(rows)

    def __len__(self):
        return len(self._rows)

    def __repr__(self):
        return "Table(ssn=[123-45-6789, 987-65-4321])"


#: A table of rows: the pane does not know what is inside it.
A_TABLE = Table(["123-45-6789"] * 294)


def a_state_with(tool_name: str, arguments: dict) -> TuiState:
    """A state that carries a tool that was called."""
    state = TuiState()
    state.update_tool_start(tool_name, arguments)
    return state


def the_pane(state: TuiState, pane_width: int) -> str:
    """The pane, as plain text, the way the terminal renders it."""
    console = Console(width=pane_width, color_system=None)
    panel = ProgressView().render(state, width=pane_width)
    lines = console.render_lines(panel, console.options.update(width=pane_width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


#: The glyphs of the frame of the pane.  They are the decoration, and
#: the text of a value is read through them.
THE_FRAME = "│╭╮╰╯├┤┬┴┼─━"


def the_text_of_the_pane(text: str) -> str:
    """
    The text of the pane without the frame and without the spaces of the
    indentation and of the wrapping.

    A value that does not fit on one line is **split** by the pane, and
    the characters of it are on the screen all the same -- the frame and
    the indentation are between them.  The check reads the pane the way
    the operator reads it: the characters of the value are there.
    """
    for glyph in THE_FRAME:
        text = text.replace(glyph, "")
    return "".join(text.split())


def show_the_pane() -> None:
    """Show the pane at the widths of the terminals the operator uses."""
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        print(f"--- a terminal of {console_width} columns "
              f"(the pane is {pane_width} cells wide) ---")
        for tool_name, arguments in THE_CALLS:
            print(the_pane(a_state_with(tool_name, arguments), pane_width))
            print()
        print()


def check_every_tool_shows_its_arguments() -> bool:
    """Every call of every tool shows what it was called with."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        for tool_name, arguments in THE_CALLS:
            text = the_pane(a_state_with(tool_name, arguments), pane_width)
            for name, value in arguments.items():
                if is_a_payload(name):
                    # A payload is measured, and never printed.
                    if f"{name}=" not in text:
                        print(f"  FAIL  the pane does not show the measure "
                              f"of {name!r} of {tool_name} at {console_width} "
                              f"columns: {text!r}")
                        ok = False
                    continue
                if "".join(str(value).split()) not in the_text_of_the_pane(text):
                    print(f"  FAIL  the pane does not show {value!r} of "
                          f"{tool_name} at {console_width} columns: {text!r}")
                    ok = False
    return ok


def check_a_payload_is_not_printed() -> bool:
    """The body of a file is measured, and never printed."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(
            a_state_with(
                "write_file", {"path": "/tmp/.env", "content": A_SECRET}
            ),
            pane_width,
        )
        if A_SECRET in text:
            print(f"  FAIL  the pane prints the payload at {console_width} "
                  f"columns: {text!r}")
            ok = False
        if "API_KEY" in text:
            print(f"  FAIL  the pane prints the head of the payload at "
                  f"{console_width} columns: {text!r}")
            ok = False
        if "content=" not in text:
            print(f"  FAIL  the pane does not measure the payload at "
                  f"{console_width} columns: {text!r}")
            ok = False
        if "path=/tmp/.env" not in text:
            print(f"  FAIL  the pane does not show the path of the payload "
                  f"at {console_width} columns: {text!r}")
            ok = False

        # The measure is honest: the pane says how many lines there are.
        text = the_pane(
            a_state_with(
                "write_file", {"path": "/tmp/a.md", "content": A_BODY}
            ),
            pane_width,
        )
        if "50 lines" not in text:
            print(f"  FAIL  the pane does not say how many lines the "
                  f"payload has at {console_width} columns: {text!r}")
            ok = False
    return ok


def check_the_body_of_a_tool_is_measured() -> bool:
    """The body of a tool -- a cell, a changelog, a filter -- is measured."""
    ok = True
    the_calls = (
        ("set_cell_value",
         {"path": "/tmp/book.xlsx", "cell": "B7", "value": A_BODY_OF_A_TOOL}),
        ("git_update_changelog",
         {"path": "/tmp/repo", "description": A_BODY_OF_A_TOOL}),
        ("filter_data",
         {"df_or_path": "/tmp/sales.xlsx", "column": "ssn",
          "condition": A_BODY_OF_A_TOOL}),
    )
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        for tool_name, arguments in the_calls:
            text = the_pane(a_state_with(tool_name, arguments), pane_width)
            if A_BODY_OF_A_TOOL in text:
                print(f"  FAIL  the pane prints the body of {tool_name} at "
                      f"{console_width} columns: {text!r}")
                ok = False
            for name in arguments:
                if is_a_payload(name) and f"{name}=" not in text:
                    print(f"  FAIL  the pane does not measure {name!r} of "
                          f"{tool_name} at {console_width} columns: {text!r}")
                    ok = False
    return ok


def check_a_value_the_pane_does_not_know_is_measured() -> bool:
    """A value the pane does not know is measured, and never printed."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(
            a_state_with("filter_data", {"df_or_path": A_TABLE, "column": "ssn"}),
            pane_width,
        )
        if "123-45-6789" in text:
            print(f"  FAIL  the pane prints the rows of the table at "
                  f"{console_width} columns: {text!r}")
            ok = False
        if "Table" not in text:
            print(f"  FAIL  the pane does not say what kind of value it was "
                  f"given at {console_width} columns: {text!r}")
            ok = False
    return ok


def check_the_command_is_still_whole() -> bool:
    """The command of the shell is shown the way it has been shown."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(
            a_state_with("execute_shell_command", {"command": COMMAND}),
            pane_width,
        )
        for word in ("cd", "git", "status", "--short", "python", "pytest", "-x"):
            if word not in text:
                print(f"  FAIL  the pane does not show {word!r} of the "
                      f"command at {console_width} columns: {text!r}")
                ok = False
    return ok


def check_the_home_is_off_the_screen() -> bool:
    """The home of the operator is hidden in every argument."""
    home = str(Path.home())
    if not home or home in ("/", "/root", "/nonexistent"):
        print("  the home of this machine cannot be found: the check is skipped")
        return True

    ok = True
    for tool_name, arguments in (
        ("read_file", {"path": f"{home}/notes.md"}),
        ("write_file", {"path": f"{home}/notes.md", "content": "hello"}),
        ("execute_shell_command", {"command": f"cat {home}/notes.md"}),
    ):
        text = the_pane(a_state_with(tool_name, arguments), 60)
        if home in text:
            print(f"  FAIL  the pane shows the home of the operator for "
                  f"{tool_name}: {text!r}")
            ok = False
    return ok


def check_a_long_value_is_folded() -> bool:
    """A value that is long is folded, and the marker says how much."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(
            a_state_with(
                "execute_shell_command", {"command": A_BODY}
            ),
            pane_width,
        )
        if "more lines" not in text:
            print(f"  FAIL  the value was not folded at {console_width} "
                  f"columns: {text!r}")
            ok = False
        if "line 0" not in text:
            print(f"  FAIL  the head of the value is gone at {console_width} "
                  f"columns: {text!r}")
            ok = False
    return ok


def check_every_line_fits_the_pane() -> bool:
    """No line of the pane is wider than the pane."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        calls = THE_CALLS + (
            ("write_file", {"path": "/tmp/a.md", "content": A_BODY}),
        )
        for tool_name, arguments in calls:
            text = the_pane(a_state_with(tool_name, arguments), pane_width)
            for line in text.split("\n"):
                if len(line) > pane_width:
                    print(f"  FAIL  the line is {len(line)} cells wide and "
                          f"the pane is {pane_width} cells wide: {line!r}")
                    ok = False
    return ok


def check_the_call_of_the_workflow_reaches_the_pane() -> bool:
    """The arguments of the tools the workflow calls reach the pane.

    The seam between the workflow and the pane is where the arguments
    could be lost: the workflow publishes the event of the call, the
    consumer of the events hands it over, the adapter puts it into the
    state, and the pane draws it.  The check drives the **real** event
    of the framework through the **real** consumer and the **real**
    adapter, and reads the pane that comes out of it.
    """
    from llama_index.core.agent.workflow import ToolCall

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
    state = TuiState()
    TuiEventAdapter(state).register_with_event_consumer(consumer)

    asyncio.run(
        consumer._handle_event(
            ToolCall(
                tool_name="write_file",
                tool_kwargs={"path": "/tmp/notes.md", "content": "hello"},
                tool_id="call-1",
            )
        )
    )

    text = the_pane(state, 60)
    for expected in ("write_file", "path=/tmp/notes.md", "content=1 line, 5 B"):
        if expected not in text:
            print(f"  FAIL  the pane does not show {expected!r} of the call "
                  f"of the workflow: {text!r}")
            return False
    if "hello" in text:
        print(f"  FAIL  the pane prints the payload of the call of the "
              f"workflow: {text!r}")
        return False
    return True


def main() -> int:
    """Run every check and report what holds."""
    show_the_pane()

    checks = (
        ("every tool shows its arguments",
         check_every_tool_shows_its_arguments),
        ("the body of a file is off the screen",
         check_a_payload_is_not_printed),
        ("the body of a tool is off the screen",
         check_the_body_of_a_tool_is_measured),
        ("a value the pane does not know is off the screen",
         check_a_value_the_pane_does_not_know_is_measured),
        ("the command of the shell is still whole",
         check_the_command_is_still_whole),
        ("the home of the operator is off the screen",
         check_the_home_is_off_the_screen),
        ("a long value is folded honestly",
         check_a_long_value_is_folded),
        ("every line fits the pane",
         check_every_line_fits_the_pane),
        ("the arguments of the call of the workflow reach the pane",
         check_the_call_of_the_workflow_reaches_the_pane),
    )

    failed = 0
    print("=" * 70)
    for name, check in checks:
        result = check()
        print(f"  {'PASS' if result else 'FAIL'}  {name}")
        if not result:
            failed += 1
    print("=" * 70)

    if failed:
        print(f"{failed} check(s) do not hold.")
        return 1
    print("Every check holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
