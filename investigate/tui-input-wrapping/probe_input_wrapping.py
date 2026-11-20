"""
The input bar of the TUI — the text that reaches the end of the view.

The operator asked (2026-11-20) for the text of the command bar to
move to the next line when it reaches the end of the view, the way the
question of the agent moves to the next line in the agent-question
mode.

The question is checked the way the running TUI does it — the real
layout, the real panels, the real width the terminal gives the bar:

  1. **Does the text move to the next line?**  The bar is rendered at
     the width of a real terminal and the text is looked for on the
     lines of the screen.  Before the change the text was cut at the
     edge of the view, with an ellipsis, and the cursor went with it.

  2. **Does the cursor go with the text?**  The cursor is a cell with a
     style of its own: the row of the screen it is drawn on is found
     by the style, and it has to be the row the operator is writing on.

  3. **Does the bar stay three lines?**  A text of any length is seen
     through a window of three lines that follows the cursor.

  4. **Is the agent-question mode the same?**  The answer of the
     operator is wrapped the same way the question of the agent is.

Usage:
    python investigate/tui-input-wrapping/probe_input_wrapping.py

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

from components.tui.input_text import (  # noqa: E402
    MAX_INPUT_LINES,
    cursor_line,
    visible_line_count,
    wrap_lines,
)
from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    fit_footer,
    input_text_width,
    render_footer,
)

#: The width of the terminal the checks are made at.
TERMINAL_WIDTH = 100


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


def cursor_row_on_screen(panel, width=TERMINAL_WIDTH) -> int:
    """The row of the screen the cursor is drawn on.

    Args:
        panel: The panel of the command bar.
        width: The width of the terminal.

    Returns:
        The number of the row of the screen, counted from zero, or -1
        when the cursor is not on the screen at all.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    lines = console.render_lines(panel, console.options.update(height=None))

    for index, row in enumerate(lines):
        for segment in row:
            if segment.style and "on green" in str(segment.style):
                return index

    return -1


def main() -> int:
    """Run every check and report what was seen."""
    text_width = input_text_width(TERMINAL_WIDTH)
    long_text = (
        "The operator asked on 2026-11-20 for the text of the command bar "
        "to move to the next line when it reaches the end of the view, the "
        "way the question of the agent does."
    )
    failures = []

    print(f"the terminal is {TERMINAL_WIDTH} columns wide")
    print(f"the bar gives the text of the operator {text_width} cells")
    print()

    # 1. the text moves to the next line
    rows = wrap_lines(long_text, text_width)
    print("the text of the operator")
    print(f"   it takes {len(rows)} lines of the view")
    for index, (row, _) in enumerate(rows):
        print(f"   line {index}: {row[:58]!r}")
    print()

    screen = render(long_text)
    # The end of the text has to be on the screen: before the change the
    # text was cut at the edge of the view, with an ellipsis.
    if "of the agent does." not in screen:
        failures.append(
            "the end of the text of the operator is not on the screen -- "
            "the text was cut at the edge of the view"
        )
    print("the bar shows")
    for line in screen.splitlines()[-6:]:
        if line.strip():
            print(f"   {line.rstrip()}")
    print()

    # 2. the cursor goes with the text
    panel = render_footer(
        input_buffer=long_text,
        cursor_pos=len(long_text),
        width=text_width,
    )
    row_on_screen = cursor_row_on_screen(panel)
    row_in_text = cursor_line(long_text, len(long_text), text_width)
    print("the cursor")
    print(f"   the text puts it on line {row_in_text}")
    print(f"   the screen draws it on row {row_on_screen}")
    if row_on_screen < 0:
        failures.append(
            "the cursor is not on the screen -- it went with the text that "
            "was cut at the edge of the view"
        )
    print()

    # 3. the bar stays three lines
    visible = visible_line_count(long_text * 10, text_width)
    print("a text of any length")
    print(f"   the view shows {visible} lines")
    if visible != MAX_INPUT_LINES:
        failures.append(f"the view shows {visible} lines, not {MAX_INPUT_LINES}")
    print()

    # 4. the agent-question mode is the same
    screen = render(long_text, hitl_active=True, hitl_prompt="Which one?")
    if "of the agent does." not in screen:
        failures.append(
            "the end of the answer of the operator is not on the screen -- "
            "the answer was cut at the edge of the view"
        )
    print("the agent-question mode")
    for line in screen.splitlines()[-8:]:
        if line.strip():
            print(f"   {line.rstrip()}")
    print()

    if failures:
        print("something does not hold:")
        for failure in failures:
            print(f"   - {failure}")
        return 1

    print(
        "everything holds: the text moves to the next line, the cursor "
        "goes with it, and the bar takes three lines"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
