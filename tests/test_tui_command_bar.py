"""
The command bar of the TUI — the invitation to press Enter.

The operator asked on 2026-11-20 for two things in the command bar:

- the invitation to press Enter, the way the agent-question mode has
  it — the operator has to see what Enter does with what he wrote;
- the message of the operator must not occupy an entire input window —
  the invitation needs a place of its own.

The bar is now a grid of two columns, the way the agent-question mode
is: the text of the operator on the left, the invitation on the right,
on the line the cursor is on.  The hot commands keep the right column
while the bar is empty, and they are exactly as visible as they were.

Run with:
    pytest tests/test_tui_command_bar.py -v
"""
import io
import unittest

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from components.tui.input_text import visible_line_count
from components.tui.layout_manager import (
    CONFIRM_INVITATION,
    FOOTER_HEIGHT,
    HINTS_COLUMN_RATIO,
    INPUT_PROMPT,
    PANEL_OVERHEAD,
    SEND_INVITATION,
    TEXT_COLUMN_RATIO,
    build_torvalds_layout,
    fit_footer,
    input_text_width,
    render_footer,
)

#: The hot commands of the bar, as they are written in the source.
HOT_COMMANDS = (
    "[\\stats | \\tools | \\projects | \\chat-sessions | \\help | "
    "\\exit | PgUp/PgDn: Scroll]"
)


def render_screen(width=100, height=24, footer_panel=None, layout=None,
                  hitl_active=False, input_lines=1):
    """Render the TUI the way the app does, and return what is on screen.

    Args:
        width: The width of the terminal.
        height: The height of the terminal.
        footer_panel: The panel to put into the footer partition.
        layout: The layout to render; a fresh one by default.
        hitl_active: Whether a question of the agent is waiting.
        input_lines: The number of lines the input bar shows.

    Returns:
        The text of the screen.
    """
    console = Console(width=width, height=height, file=io.StringIO())
    layout = layout if layout is not None else build_torvalds_layout()

    if footer_panel is not None:
        fit_footer(
            layout,
            console,
            footer_panel,
            hitl_active,
            input_lines=input_lines,
        )
        layout["footer"].update(footer_panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


def bar_screen(input_buffer, cursor_pos=None, width=100, **kwargs):
    """The screen of the TUI with the given text in the command bar.

    Args:
        input_buffer: The text of the operator.
        cursor_pos: The position of the cursor; the end of the text by
            default.
        width: The width of the terminal.
        kwargs: The rest of the arguments of :func:`render_screen`.

    Returns:
        The text of the screen.
    """
    pos = len(input_buffer) if cursor_pos is None else cursor_pos
    text_width = input_text_width(width)
    panel = render_footer(
        input_buffer=input_buffer,
        cursor_pos=pos,
        width=text_width,
    )
    kwargs.setdefault("width", width)
    return render_screen(
        footer_panel=panel,
        input_lines=visible_line_count(input_buffer, text_width),
        **kwargs,
    )


def bar_rows(input_buffer, cursor_pos=None, width=100):
    """The rows of the bar, and the row the cursor is drawn on.

    Args:
        input_buffer: The text of the operator.
        cursor_pos: The position of the cursor; the end of the text by
            default.
        width: The width of the terminal.

    Returns:
        The rows of the bar, and the number of the row the cursor is
        drawn on — -1 when the cursor is not on the screen at all.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    pos = len(input_buffer) if cursor_pos is None else cursor_pos
    panel = render_footer(
        input_buffer=input_buffer,
        cursor_pos=pos,
        width=input_text_width(width),
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


def row_with(rows, needle):
    """The number of the row that holds the given text, or -1.

    Args:
        rows: The rows of the bar.
        needle: The text to look for.

    Returns:
        The number of the row, counted from zero, or -1 when the text
        is on no row.
    """
    for index, row in enumerate(rows):
        if needle in row:
            return index
    return -1


class TestTheInvitation(unittest.TestCase):
    """The invitation to press Enter."""

    def test_the_invitation_is_shown_while_there_is_text(self):
        """The operator has to see what Enter does with what he wrote."""
        screen = bar_screen("hello")

        self.assertIn(
            SEND_INVITATION,
            screen,
            "the invitation to press Enter is not on the screen -- the "
            "operator cannot see what Enter does with what he wrote",
        )

    def test_the_invitation_is_not_shown_on_an_empty_bar(self):
        """There is nothing to send while the bar is empty."""
        screen = bar_screen("")

        self.assertNotIn(
            SEND_INVITATION,
            screen,
            "the invitation is on an empty bar -- there is nothing to send",
        )

    def test_the_invitation_stands_on_the_line_the_cursor_is_on(self):
        """The invitation is next to the line the operator writes on."""
        text = "the operator asked for the invitation to press enter"

        rows, cursor_row = bar_rows(text)

        self.assertGreaterEqual(
            cursor_row,
            0,
            "the cursor is not on the screen -- there is no line to stand "
            "the invitation on",
        )
        self.assertEqual(
            row_with(rows, SEND_INVITATION),
            cursor_row,
            "the invitation does not stand on the line the cursor is on",
        )

    def test_the_invitation_follows_the_cursor_up(self):
        """The cursor walks the lines, and the invitation walks with it."""
        text = "the operator asked for the invitation to press enter"

        rows, _ = bar_rows(text, cursor_pos=0)

        self.assertEqual(
            row_with(rows, SEND_INVITATION),
            1,
            "the invitation did not move to the first line of the text "
            "when the cursor walked up to it",
        )

    def test_the_agent_question_mode_keeps_its_own_invitation(self):
        """The question of the agent is confirmed, not sent."""
        console = Console(width=100, height=24, file=io.StringIO())
        panel = render_footer(
            input_buffer="hello",
            cursor_pos=5,
            hitl_active=True,
            hitl_prompt="Which one?",
            width=input_text_width(100, hitl_active=True),
        )
        lines = console.render_lines(panel, console.options.update(height=None))
        rows = ["".join(segment.text for segment in row) for row in lines]

        self.assertIn(
            CONFIRM_INVITATION,
            "\n".join(rows),
            "the invitation of the agent-question mode is gone",
        )

    def test_the_invitation_survives_the_busy_prompt(self):
        """The bar of a busy agent invites Enter as well."""
        console = Console(width=100, height=24, file=io.StringIO())
        panel = render_footer(
            input_buffer="hello",
            cursor_pos=5,
            is_busy=True,
            width=input_text_width(100, is_busy=True),
        )
        lines = console.render_lines(panel, console.options.update(height=None))
        rows = ["".join(segment.text for segment in row) for row in lines]

        self.assertIn(
            SEND_INVITATION,
            "\n".join(rows),
            "the invitation is gone while the agent is busy",
        )


class TestTheMessageAndTheWindow(unittest.TestCase):
    """The message of the operator does not take the whole window."""

    def test_the_text_has_a_column_of_its_own(self):
        """Three quarters of the bar are the text, a quarter the invitation."""
        width = 100
        content = width - PANEL_OVERHEAD
        column = content * TEXT_COLUMN_RATIO // 100

        self.assertEqual(
            input_text_width(width),
            column - len(INPUT_PROMPT),
            "the width of the text is not the width of its column",
        )

    def test_the_text_is_wrapped_before_the_column_of_the_invitation(self):
        """The message stops where the invitation begins."""
        width = 100
        content = width - PANEL_OVERHEAD
        column = content * TEXT_COLUMN_RATIO // 100
        text = "Q" * 200

        screen = bar_screen(text, width=width)
        rows = [line for line in screen.splitlines() if "Q" in line]

        self.assertGreater(
            len(rows),
            1,
            "the message of the operator took the whole window -- the "
            "invitation has no column of its own",
        )
        # The message never reaches past its own column: the border,
        # the padding, and the column of the text are the whole of it.
        column_end = 2 + column
        for row in rows:
            self.assertLessEqual(
                row.rindex("Q") + 1,
                column_end,
                "the message of the operator reaches into the column of "
                "the invitation",
            )

        # The line the operator writes on: the message ends before the
        # invitation starts -- the two of them do not share a cell.
        written = [row for row in rows if SEND_INVITATION in row]
        self.assertTrue(
            written,
            "the invitation is not on the line the operator writes on",
        )
        row = written[0]
        self.assertLessEqual(
            row.rindex("Q") + 1,
            row.index(SEND_INVITATION),
            "the message of the operator reaches into the column of the "
            "invitation",
        )

    def test_the_bar_is_not_cropped_by_the_invitation(self):
        """The invitation stands on a line of the bar, not beside it."""
        layout = build_torvalds_layout()
        console = Console(width=100, height=24, file=io.StringIO())
        text = "Q" * 200
        text_width = input_text_width(100)

        given = fit_footer(
            layout,
            console,
            render_footer(
                input_buffer=text,
                cursor_pos=len(text),
                width=text_width,
            ),
            input_lines=visible_line_count(text, text_width),
        )

        self.assertEqual(
            given,
            FOOTER_HEIGHT + 2,
            "the bar did not get the room of the three lines of the text",
        )

    def test_the_hot_commands_keep_their_room(self):
        """The change did not take any of the hot commands away."""
        width = 100
        console = Console(width=width, height=24, file=io.StringIO())

        # The empty bar as it was before the change: the prompt on the
        # left, the hot commands on the right, a third of the bar.
        table = Table.grid(expand=True)
        table.add_column(justify="left", ratio=100 - HINTS_COLUMN_RATIO)
        table.add_column(justify="right", ratio=HINTS_COLUMN_RATIO)
        table.add_row(
            Text.from_markup("[green]>>> [/green]"),
            Text.from_markup(f"[dim]{HOT_COMMANDS}[/dim]"),
        )
        before = console.render_lines(
            Panel(table, border_style="green", padding=(0, 1)),
            console.options.update(height=None),
        )
        before_row = [
            "".join(segment.text for segment in row) for row in before
        ]

        panel = render_footer(input_buffer="", cursor_pos=0)
        after = console.render_lines(panel, console.options.update(height=None))
        after_row = ["".join(segment.text for segment in row) for row in after]

        self.assertEqual(
            [row for row in after_row if "\\stats" in row],
            [row for row in before_row if "\\stats" in row],
            "the hot commands are not what they were on the screen",
        )


if __name__ == "__main__":
    unittest.main()
