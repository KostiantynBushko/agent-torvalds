"""
The command bar of the TUI — the invitation to press Enter.

The operator asked (2026-11-20) for two things in the command bar:

  * the invitation to press Enter, the way the agent-question mode has
    it — the operator has to see what Enter does with what he wrote;
  * the message of the operator must not occupy an entire input window
    — the invitation needs a place of its own.

The question is checked the way the running TUI does it — the real
layout, the real panels, the real width the terminal gives the bar:

  1. **Is the invitation on the screen while there is text?**  The bar
     is rendered at the width of a real terminal and the invitation is
     looked for on the lines of the screen.

  2. **Is the invitation on the line the operator writes on?**  The
     cursor is a cell with a style of its own: the row of the screen it
     is drawn on is found by the style, and the invitation has to stand
     on that row.

  3. **Does the message leave the window alone?**  The text of the
     operator must stop before the column of the invitation: the bar
     is split, and the text is wrapped at the width of its own column.

  4. **Are the hot commands as visible as they were?**  The empty bar
     carries the hot commands, and the change must not take any of
     them away.

  5. **Is the agent-question mode the same?**  The question of the
     agent keeps its own invitation, and its own column.

Usage:
    python investigate/tui-command-bar-invitation/probe_command_bar.py

The exit code is 0 when every check holds, 1 when one does not.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402
from rich.live import Live  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

from components.tui.input_text import (  # noqa: E402
    visible_line_count,
    visible_window,
)
from components.tui.layout_manager import (  # noqa: E402
    CONFIRM_INVITATION,
    HINTS_COLUMN_RATIO,
    PANEL_OVERHEAD,
    SEND_INVITATION,
    TEXT_COLUMN_RATIO,
    build_torvalds_layout,
    fit_footer,
    input_text_width,
    render_footer,
)

#: The width of the terminal the checks are made at.
TERMINAL_WIDTH = 100

#: The hot commands of the bar, as they are written in the source.
HOT_COMMANDS = (
    "[\\stats | \\tools | \\projects | \\chat-sessions | \\help | "
    "\\exit | PgUp/PgDn: Scroll]"
)


def old_empty_bar(width=TERMINAL_WIDTH) -> str:
    """The empty bar as it was before the change.

    The bar without text was a grid of two columns: the prompt on the
    left, the hot commands on the right — 65% and 35% of the bar.  The
    change kept that grid, and the probe compares the two renderings
    of it: the hot commands must not be shorter on the screen than
    they were.

    Args:
        width: The width of the terminal.

    Returns:
        The text of the screen of the old empty bar.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    layout = build_torvalds_layout()

    table = Table.grid(expand=True)
    table.add_column(justify="left", ratio=65)
    table.add_column(justify="right", ratio=35)
    table.add_row(
        Text.from_markup("[green]>>> [/green]"),
        Text.from_markup(f"[dim]{HOT_COMMANDS}[/dim]"),
    )
    panel = Panel(table, border_style="green", padding=(0, 1))
    layout["footer"].update(panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


def render(input_buffer: str, cursor_pos=None, width=TERMINAL_WIDTH,
           hitl_active: bool = False, hitl_prompt: str = "") -> str:
    """The screen of the TUI with the given text in the command bar.

    Args:
        input_buffer: The text of the operator.
        cursor_pos: The position of the cursor; the end of the text by
            default.
        width: The width of the terminal.
        hitl_active: Whether a question of the agent is waiting.
        hitl_prompt: The question of the agent.

    Returns:
        The text of the screen.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    layout = build_torvalds_layout()
    pos = len(input_buffer) if cursor_pos is None else cursor_pos
    text_width = input_text_width(width, hitl_active=hitl_active)

    panel = render_footer(
        input_buffer=input_buffer,
        cursor_pos=pos,
        hitl_active=hitl_active,
        hitl_prompt=hitl_prompt,
        width=text_width,
    )
    fit_footer(
        layout,
        console,
        panel,
        hitl_active,
        input_lines=visible_line_count(input_buffer, text_width),
    )
    layout["footer"].update(panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


def footer_rows(input_buffer: str, cursor_pos=None, width=TERMINAL_WIDTH):
    """The rows of the bar, and the row of the cursor on the screen.

    Args:
        input_buffer: The text of the operator.
        cursor_pos: The position of the cursor; the end of the text by
            default.
        width: The width of the terminal.

    Returns:
        The rows of the bar, and the number of the row the cursor is
        drawn on — -1 when the cursor is not on the screen.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    pos = len(input_buffer) if cursor_pos is None else cursor_pos
    text_width = input_text_width(width)

    panel = render_footer(
        input_buffer=input_buffer,
        cursor_pos=pos,
        width=text_width,
    )
    lines = console.render_lines(panel, console.options.update(height=None))
    rows = ["".join(segment.text for segment in row) for row in lines]

    cursor_row = -1
    for index, row in enumerate(lines):
        for segment in row:
            if segment.style and "on green" in str(segment.style):
                cursor_row = index
                break

    return rows, cursor_row


def main() -> int:
    """Run every check and report what was seen."""
    width = TERMINAL_WIDTH
    content = width - PANEL_OVERHEAD
    text_width = input_text_width(width)
    long_text = (
        "the operator asked for the invitation to press enter in the command "
        "bar, the way the agent question mode has it, and the message of the "
        "operator must not occupy the whole window of the input"
    )
    failures = []

    print(f"the terminal is {width} columns wide")
    print(f"the bar gives the text of the operator {text_width} cells")
    print()

    # 1. the invitation is on the screen while there is text
    screen = render("hello")
    if SEND_INVITATION not in screen:
        failures.append(
            "the invitation to press Enter is not on the screen -- the "
            "operator cannot see what Enter does with what he wrote"
        )
    print("the bar with text in it")
    for line in screen.splitlines()[-4:]:
        if line.strip():
            print(f"   {line.rstrip()}")
    print()

    # 2. the invitation stands on the line the cursor is on
    rows, cursor_row = footer_rows(long_text)
    invitation_row = None
    for index, row in enumerate(rows):
        if SEND_INVITATION in row:
            invitation_row = index
            break
    if invitation_row is None:
        failures.append("the invitation is not on the bar of a long text")
    elif cursor_row >= 0 and invitation_row != cursor_row:
        failures.append(
            f"the invitation stands on row {invitation_row} and the cursor "
            f"on row {cursor_row} -- the invitation is not on the line the "
            "operator writes on"
        )
    print("a text of three lines")
    for index, row in enumerate(rows):
        print(f"   row {index}: {row.rstrip()}")
    print(f"   the cursor is on row {cursor_row}")
    print(f"   the invitation is on row {invitation_row}")
    print()

    # 3. the message does not take the whole window
    column = content * TEXT_COLUMN_RATIO // 100
    lines, _, _ = visible_window(long_text, len(long_text), text_width)
    too_wide = [line for line in lines if len(line) > text_width]
    if too_wide:
        failures.append(
            "the text of the operator is wider than the column it has -- "
            "it reaches into the column of the invitation"
        )
    print("the message and the window")
    print(f"   the bar is {content} cells wide")
    print(f"   the text of the operator has {column} cells of it")
    print(f"   the invitation has {content - column} cells of it")
    print(f"   the text is wrapped at {text_width} cells")
    print()

    # 4. the hot commands are as visible as they were
    screen = render("")
    before = old_empty_bar()
    new_row = ""
    old_row = ""
    for line in screen.splitlines():
        if "\\stats" in line:
            new_row = line
            break
    for line in before.splitlines():
        if "\\stats" in line:
            old_row = line
            break
    if new_row != old_row:
        failures.append(
            "the hot commands are not what they were on the screen:\n"
            f"       before: {old_row.rstrip()!r}\n"
            f"       now:    {new_row.rstrip()!r}"
        )
    if SEND_INVITATION in screen:
        failures.append(
            "the invitation is on an empty bar -- there is nothing to send"
        )
    print(f"   the column of the hot commands is {content * HINTS_COLUMN_RATIO // 100} cells")
    print("the empty bar")
    for line in screen.splitlines()[-4:]:
        if line.strip():
            print(f"   {line.rstrip()}")
    print()

    # 5. the agent-question mode is the same
    screen = render("hello", hitl_active=True, hitl_prompt="Which one?")
    if CONFIRM_INVITATION not in screen:
        failures.append(
            "the invitation of the agent-question mode is not on the "
            "screen -- the change took it away"
        )
    print("the agent-question mode")
    for line in screen.splitlines()[-6:]:
        if line.strip():
            print(f"   {line.rstrip()}")
    print()

    if failures:
        print("something does not hold:")
        for failure in failures:
            print(f"   - {failure}")
        return 1

    print(
        "everything holds: the invitation is on the screen, it stands on "
        "the line the operator writes on, the message leaves the window "
        "alone, and the hot commands are where they were"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
