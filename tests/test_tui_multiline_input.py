"""
The input bar of the TUI — one line, or three.

The command bar carries what the operator types, and it carries it
well enough to write a long question into it:

- the hot commands on the right go away while there is text in the bar,
  and they come back when the last character is deleted;
- the view of the input grows with the lines of the input — up to
  three lines;
- the text that reaches the end of the view moves to the next line, the
  way the question of the agent moves to the next line in the
  agent-question mode, and the cursor goes with it;
- a paste arrives in one piece, and a paste that is longer than the
  window ends with its last lines on the screen; the operator can walk
  the cursor back into the text and edit it.

Run with:
    pytest tests/test_tui_multiline_input.py -v
"""
import io
import os
import pty
import select
import signal
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

from components.tui.input_reader import (  # noqa: E402
    BRACKETED_PASTE_OFF,
    BRACKETED_PASTE_ON,
    NonBlockingInputReader,
    PastedText,
)
from components.tui.input_text import (  # noqa: E402
    MAX_INPUT_LINES,
    cursor_column,
    cursor_line,
    line_count,
    move_cursor_down,
    move_cursor_up,
    normalize_paste,
    visible_line_count,
    visible_window,
    wrap_lines,
)
from components.tui.layout_manager import (  # noqa: E402
    FOOTER_HEIGHT,
    HINTS_COLUMN_RATIO,
    INPUT_PROMPT,
    PANEL_OVERHEAD,
    build_torvalds_layout,
    fit_footer,
    input_text_width,
    render_footer,
)
from components.tui.tui_app import TuiApp  # noqa: E402


def render_screen(width=120, height=24, footer_panel=None, layout=None,
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
    from rich.live import Live

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


def footer_screen(input_buffer, cursor_pos=None, width=120, **kwargs):
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


def cursor_row_on_screen(panel, width=120):
    """The row of the screen the cursor is drawn on.

    The cursor is a cell with a style of its own: it is found by the
    style, not by its text.

    Args:
        panel: The panel of the command bar.
        width: The width of the terminal.

    Returns:
        The number of the row of the screen, counted from zero.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    lines = console.render_lines(panel, console.options.update(height=None))

    for index, row in enumerate(lines):
        for segment in row:
            if segment.style and "on green" in str(segment.style):
                return index

    return -1


#: The environment variable that makes the reader in the child of the
#: pseudo-terminal start late.  A test sets it to imitate a machine
#: that is slower than the one the test runs on.
START_DELAY_VARIABLE = "TORVALDS_TEST_PTY_START_DELAY"

#: How long the parent waits for the child to say that it is ready.
#: The child imports the whole TUI package before it puts the terminal
#: into cbreak mode, and that takes longer than a guess would allow
#: for on a loaded machine.
READY_TIMEOUT = 60.0


def _read_until(fd, out, marker, timeout):
    """Read from the terminal until the marker shows up.

    Args:
        fd: The master side of the pseudo-terminal.
        out: The bytes that were read already.
        marker: The bytes that end the wait.
        timeout: How long the wait lasts at the most.

    Returns:
        The bytes that were read, the old ones included.
    """
    deadline = time.time() + timeout

    while marker not in out and time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.3)
        if not r:
            continue
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        out += chunk

    return out


def keys_from_pty(data: bytes, seconds=4.0, collect=2.0):
    """Type bytes into a pseudo-terminal and collect the keys of the reader.

    The bytes are typed only when the reader says that it is ready: a
    terminal that is still in its old mode takes a typed byte for a
    line of text, and it throws the line away when the mode changes.
    A key that was typed too early is lost, and the reader reports
    nothing at all.

    Args:
        data: The bytes to write into the terminal.
        seconds: How long the parent waits for the output.
        collect: How long the reader in the child collects the keys.

    Returns:
        A tuple of the keys the reader reported and the raw output of
        the terminal.  Every key is a pair of the name of its kind and
        its value: a paste is a string like any other, and only the
        kind tells it apart from a key that was typed.
    """
    script = (
        "import os, sys, time\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from components.tui.input_reader import NonBlockingInputReader\n"
        # A reader that starts late imitates a slow machine.
        f"time.sleep(float(os.environ.get({START_DELAY_VARIABLE!r}, '0')))\n"
        "r = NonBlockingInputReader()\n"
        "r.start()\n"
        # The child says that the terminal is ready for the keys.
        "print('READY', flush=True)\n"
        "got = []\n"
        "end = time.time() + %r\n" % collect
        +         "while time.time() < end:\n"
        "    if r.is_available():\n"
        "        k = r.poll_key()\n"
        "        if k is not None: got.append((type(k).__name__, k))\n"
        "    time.sleep(0.02)\n"
        "r.stop()\n"
        "print('KEYS:' + repr(got), flush=True)\n"
    )

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - child process
        os.environ["TERM"] = "xterm"
        os.chdir(str(ROOT))
        os.execv(sys.executable, [sys.executable, "-c", script])

    out = b""
    try:
        out = _read_until(fd, out, b"READY", READY_TIMEOUT)
        try:
            os.write(fd, data)
        except OSError:
            # The child is gone -- the keys it would report are lost.
            pass

        deadline = time.time() + seconds
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.3)
            if not r:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if b"KEYS:" in out:
                break
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, os.WNOHANG)

    text = out.decode("utf-8", "replace")
    if "KEYS:" not in text:
        return [], text
    keys_line = text.split("KEYS:")[1].split("\n")[0]
    return eval(keys_line), text  # noqa: S307 - controlled literal from our own child


def key_values(keys):
    """The values of the keys the reader reported."""
    return [value for _, value in keys]


def pasted_values(keys):
    """The values of the keys that were pastes."""
    return [value for kind, value in keys if kind == "PastedText"]


class TestTheHotCommands(unittest.TestCase):
    """The hot commands on the right of the bar."""

    def test_the_hot_commands_are_shown_when_the_bar_is_empty(self):
        """The operator has to see what he can type."""
        screen = footer_screen("")

        self.assertIn(
            "\\stats",
            screen,
            "the hot commands are not on the screen -- the operator "
            "cannot see what the bar takes",
        )
        self.assertIn("\\tools", screen)
        self.assertIn("\\projects", screen)

    def test_the_whole_list_of_hot_commands_is_shown_on_a_wide_terminal(self):
        """The bar is narrow on a narrow terminal, and the hints are cut."""
        screen = footer_screen("", width=240)

        self.assertIn("\\chat-sessions", screen)
        self.assertIn("\\help", screen)
        self.assertIn("\\exit", screen)

    def test_the_hints_point_at_the_keys_command(self):
        """The place where the keys are listed is a command of its own.

        The ``PgUp/PgDn: Scroll`` tail gave way to ``\\keys``: the keys
        of the TUI are listed by the command that renders them, and not
        by a tail of the hints.
        """
        screen = footer_screen("", width=240)

        self.assertIn("\\keys", screen)
        self.assertNotIn("PgUp/PgDn", screen)

    def test_the_hot_commands_are_hidden_while_there_is_text(self):
        """The width of the bar belongs to what the operator writes."""
        screen = footer_screen("hello", width=240)

        self.assertNotIn(
            "\\stats",
            screen,
            "the hot commands are still on the screen while the operator "
            "is writing",
        )

    def test_the_text_has_more_room_than_the_hot_commands_had(self):
        """The bar is wider once the commands are gone.

        The text of the operator has a column of its own -- three
        quarters of the bar -- and the hot commands had a third of it.
        So the text has more room than they had, and the invitation to
        press Enter has the rest.
        """
        width = 120
        content = width - PANEL_OVERHEAD
        hints_column = content * HINTS_COLUMN_RATIO // 100

        self.assertGreater(
            input_text_width(width) + len(INPUT_PROMPT),
            hints_column,
            "the text of the operator has less room than the hot commands "
            "had -- the bar did not get wider once the commands were gone",
        )

    def test_the_hot_commands_come_back_when_the_text_is_deleted(self):
        """Deleting the last character brings them back."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key("x")
        self.assertNotIn("\\stats", footer_screen(app.state.input_buffer))

        app._handle_key("BACKSPACE")

        self.assertEqual(app.state.input_buffer, "")
        self.assertIn(
            "\\stats",
            footer_screen(app.state.input_buffer),
            "the hot commands did not come back when the last character "
            "was deleted",
        )


class TestTheReader(unittest.TestCase):
    """The reader reports the keys of the terminal."""

    def test_the_enter_key_is_still_the_enter_key(self):
        """The rewrite of the escape sequences kept the old keys."""
        keys, _ = keys_from_pty(b"\r")

        self.assertIn("ENTER", key_values(keys))

    def test_the_shift_enter_is_not_a_key(self):
        """There is no Shift+Enter: the bar has no line break key.

        The operator decided on 2026-11-20 that the bar carries no
        Shift+Enter at all.  The reader **names** the modified keys --
        it has to, or there is nothing to bind -- but the name of the
        Shift+Enter is not the name of the Enter: the application
        drops it, and the text of the operator never changes by a key
        nobody can see.
        """
        for sequence in (b"\x1b[13;2~", b"\x1b[27;2;13~", b"\x1b[13;2u"):
            keys, _ = keys_from_pty(sequence)

            self.assertNotIn(
                "ENTER",
                key_values(keys),
                f"the reader reported an Enter: {keys!r}",
            )

    def test_the_keys_survive_a_reader_that_starts_late(self):
        """A reader that starts late still gets the keys.

        The terminal throws away the bytes that were typed before the
        reader put it into cbreak mode -- they are a line of text for
        the terminal, and it keeps no line when it stops waiting for
        one.  So the keys are typed only when the reader is ready,
        and a slow reader still gets them.
        """
        previous = os.environ.get(START_DELAY_VARIABLE)
        os.environ[START_DELAY_VARIABLE] = "2.0"
        try:
            keys, _ = keys_from_pty(b"\r")
        finally:
            if previous is None:
                os.environ.pop(START_DELAY_VARIABLE, None)
            else:
                os.environ[START_DELAY_VARIABLE] = previous

        self.assertIn(
            "ENTER",
            key_values(keys),
            f"the reader missed the key: {keys!r}",
        )

    def test_the_shift_enter_does_not_change_the_bar(self):
        """The sequence of the Shift+Enter leaves the bar as it was."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key("a")
        # Every name the reader gives the sequence of the Shift+Enter.
        # None of them is a key of the command bar, and the application
        # drops them all.
        for name in ("SHIFT_ENTER", "SHIFT_F3", "CTRL_INSERT", "ESCAPE"):
            app._handle_key(name)
        app._handle_key("b")

        self.assertEqual(
            app.state.input_buffer,
            "ab",
            "the bar changed by a key that is not a key",
        )


class TestTheViewOfTheInput(unittest.TestCase):
    """The view of the input grows with the input, up to three lines."""

    def test_the_view_grows_with_the_lines(self):
        """Every line of the input needs a line of the screen."""
        layout = build_torvalds_layout()
        console = Console(width=120, height=24, file=io.StringIO())

        one = fit_footer(
            layout,
            console,
            render_footer(input_buffer="a", cursor_pos=1),
            input_lines=1,
        )
        two = fit_footer(
            layout,
            console,
            render_footer(input_buffer="a\nb", cursor_pos=3),
            input_lines=2,
        )
        three = fit_footer(
            layout,
            console,
            render_footer(input_buffer="a\nb\nc", cursor_pos=5),
            input_lines=3,
        )

        self.assertEqual(one, FOOTER_HEIGHT)
        self.assertEqual(two, FOOTER_HEIGHT + 1)
        self.assertEqual(three, FOOTER_HEIGHT + 2)

    def test_the_three_lines_are_on_the_screen(self):
        """What the operator wrote is what the operator sees."""
        screen = footer_screen("first\nsecond\nthird")

        self.assertIn("first", screen)
        self.assertIn("second", screen)
        self.assertIn("third", screen)

    def test_the_view_shows_at_most_three_lines(self):
        """The view never grows past three lines."""
        text = "a\nb\nc\nd\ne"

        self.assertEqual(visible_line_count(text), MAX_INPUT_LINES)

        lines, row, _ = visible_window(text, len(text))
        self.assertEqual(len(lines), MAX_INPUT_LINES)

    def test_the_text_above_the_window_is_not_thrown_away(self):
        """The window is a window: the text is still there."""
        text = "a\nb\nc\nd\ne"

        lines, row, _ = visible_window(text, len(text))

        self.assertEqual(lines, ["c", "d", "e"])
        self.assertEqual(row, 2)
        self.assertEqual(line_count(text), 5)


class TestTheTextMovesToTheNextLine(unittest.TestCase):
    """The text that reaches the end of the view moves to the next line."""

    def test_the_text_is_wrapped_at_the_width_of_the_view(self):
        """The text is not cut at the edge: it moves to the next line."""
        width = 40
        text = "a" * 100

        lines, _, _ = visible_window(text, len(text), width)

        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "a" * 40)
        self.assertEqual(lines[1], "a" * 40)
        self.assertEqual(lines[2], "a" * 20)

    def test_no_word_of_the_text_is_thrown_away(self):
        """Every word of the operator is on some line."""
        width = 40
        text = "the operator asked for four things in the command bar"

        lines = wrap_lines(text, width)

        # The space at the break is eaten by the break -- it is the
        # space between two words, and no word is lost.
        self.assertEqual(
            "".join(line for line, _ in lines).replace(" ", ""),
            text.replace(" ", ""),
            "the wrapping lost a word of the text of the operator",
        )

    def test_the_cursor_goes_with_the_text_to_the_next_line(self):
        """The cursor is on the line the text moved to."""
        width = 40
        text = "a" * 100

        self.assertEqual(cursor_line(text, 45, width), 1)
        self.assertEqual(cursor_column(text, 45, width), 5)
        self.assertEqual(cursor_line(text, len(text), width), 2)

    def test_the_view_shows_at_most_three_lines_of_a_long_text(self):
        """The bar takes three lines, whatever the length of the text."""
        width = 40
        text = "a" * 500

        lines, row, _ = visible_window(text, len(text), width)

        self.assertEqual(len(lines), MAX_INPUT_LINES)
        self.assertEqual(row, MAX_INPUT_LINES - 1)
        self.assertEqual(visible_line_count(text, width), MAX_INPUT_LINES)

    def test_the_text_is_on_the_screen_on_the_next_line(self):
        """The operator sees the text that did not fit on one line."""
        screen = footer_screen("Q" * 200, width=100)
        rows = [line for line in screen.splitlines() if "Q" in line]

        self.assertGreater(
            len(rows),
            1,
            "the text of the operator is on one line -- it was cut at the "
            "edge of the view instead of moving to the next line",
        )

    def test_the_cursor_is_drawn_on_the_line_the_text_moved_to(self):
        """The cursor is on the screen, and it is on the right line."""
        width = 100
        text = "Q" * 200
        text_width = input_text_width(width)

        panel = render_footer(
            input_buffer=text,
            cursor_pos=len(text),
            width=text_width,
        )

        self.assertGreaterEqual(
            cursor_row_on_screen(panel, width),
            0,
            "the cursor is not on the screen -- the text was cut at the "
            "edge of the view and the cursor went with it",
        )

    def test_the_bar_grows_with_the_wrapped_text(self):
        """Every line the text takes needs a line of the screen."""
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

        self.assertEqual(given, FOOTER_HEIGHT + 2)

    def test_the_answer_of_the_agent_is_wrapped_too(self):
        """The agent-question mode wraps the answer the same way."""
        console = Console(width=100, height=24, file=io.StringIO())
        text = "Q" * 200
        text_width = input_text_width(100, hitl_active=True)

        panel = render_footer(
            input_buffer=text,
            cursor_pos=len(text),
            hitl_active=True,
            hitl_prompt="Which one?",
            width=text_width,
        )
        lines = console.render_lines(panel, console.options.update(height=None))
        rows = [
            "".join(segment.text for segment in row)
            for row in lines
        ]
        rows_with_text = [row for row in rows if "Q" in row]

        self.assertGreater(
            len(rows_with_text),
            1,
            "the answer of the operator was cut at the edge of the view",
        )


class TestTheTextThatIsSent(unittest.TestCase):
    """The text the agent gets is the text the operator wrote."""

    def _sent_to_the_agent(self, app):
        """The text the last query carried.

        Args:
            app: The application the query was sent from.

        Returns:
            The text of the query.
        """
        import asyncio

        sent = []

        async def handler(cmd, **kwargs):
            sent.append(cmd)
            return "ok", None

        app.prompt_handler_fn = handler

        async def run():
            app._handle_key("ENTER")
            if app._active_query_task is not None:
                await app._active_query_task

        asyncio.run(run())

        return sent[0] if sent else None

    def test_the_indentation_of_a_pasted_block_reaches_the_agent(self):
        """The text is not stripped on its way to the agent."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("    def f():\n        return 1"))

        sent = self._sent_to_the_agent(app)

        self.assertEqual(
            sent,
            "    def f():\n        return 1",
            "the indentation of the block did not reach the agent -- the "
            "text was stripped on its way",
        )

    def test_the_line_break_at_the_end_is_not_part_of_the_message(self):
        """The end of the text is not a part of it."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("a\n"))

        sent = self._sent_to_the_agent(app)

        self.assertEqual(
            sent,
            "a",
            "the line break at the end of the text went to the agent "
            "with the text",
        )

    def test_the_line_breaks_inside_the_text_are_kept(self):
        """Only the last line break is the empty last line of the bar."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("first\nsecond"))

        sent = self._sent_to_the_agent(app)

        self.assertEqual(
            sent,
            "first\nsecond",
            "the line break inside the text did not reach the agent",
        )

    def test_a_command_with_spaces_around_it_is_still_matched(self):
        """The spaces around a command are not a part of it."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        for character in "\\exit ":
            app._handle_key(character)
        app._handle_key("ENTER")

        self.assertTrue(
            app.state.exit_requested,
            "the command with a space around it was not matched",
        )


class TestThePaste(unittest.TestCase):
    """A paste arrives in one piece."""

    def test_the_reader_hands_over_the_paste_in_one_piece(self):
        """The text of the clipboard is not a keystroke."""
        keys, _ = keys_from_pty(b"\x1b[200~first\nsecond\x1b[201~")

        pastes = pasted_values(keys)

        self.assertEqual(
            len(pastes),
            1,
            f"the paste did not arrive in one piece: {keys!r}",
        )
        self.assertEqual(pastes[0], "first\nsecond")

    def test_the_terminal_is_asked_to_mark_the_pastes(self):
        """Without the mark, every newline of a paste is an ENTER."""
        _, raw = keys_from_pty(b"")

        self.assertIn(
            BRACKETED_PASTE_ON,
            raw,
            "the terminal was not asked to mark the pastes -- a paste "
            "would arrive as plain text and every newline in it would "
            "submit the command bar",
        )
        self.assertIn(
            BRACKETED_PASTE_OFF,
            raw,
            "the terminal was not given back -- it is left in the paste "
            "mode for the next program that runs in it",
        )

    def test_the_paste_is_put_into_the_input(self):
        """The text of the clipboard lands in the bar."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key("a")
        app._handle_key(PastedText("one\ntwo"))

        self.assertEqual(app.state.input_buffer, "aone\ntwo")
        self.assertEqual(app.state.cursor_pos, 8)

    def test_the_line_endings_of_the_clipboard_are_one_line_break(self):
        """A paste from Windows arrives with CRLF."""
        self.assertEqual(normalize_paste("one\r\ntwo"), "one\ntwo")
        self.assertEqual(normalize_paste("one\rtwo"), "one\ntwo")

    def test_the_control_characters_of_a_paste_are_dropped(self):
        """A pasted text may not act on the terminal."""
        pasted = "before\x1b[31mafter\x07"

        cleaned = normalize_paste(pasted)

        self.assertNotIn(
            "\x1b",
            cleaned,
            "the escape sequence of the paste is in the input -- the "
            "terminal would act on it",
        )
        self.assertNotIn("\x07", cleaned)
        self.assertIn("before", cleaned)
        self.assertIn("after", cleaned)

    def test_a_long_paste_shows_its_last_lines(self):
        """The operator sees the end of what he pasted."""
        pasted = "\n".join(f"line {number}" for number in range(1, 11))
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText(pasted))
        screen = footer_screen(app.state.input_buffer, app.state.cursor_pos)

        self.assertIn("line 10", screen)
        self.assertIn("line 9", screen)
        self.assertIn("line 8", screen)
        self.assertNotIn(
            "line 7",
            screen,
            "the beginning of the paste is on the screen -- the view did "
            "not scroll to the end of it",
        )

    def test_a_paste_that_never_closes_is_given_up_on(self):
        """A paste that swallows the keys of the operator is given up on."""
        keys, _ = keys_from_pty(b"\x1b[200~hello", seconds=9.0, collect=5.0)

        pastes = pasted_values(keys)

        self.assertEqual(
            pastes,
            ["hello"],
            f"the paste that never closed was not given up on: {keys!r}",
        )

    def test_the_pasted_text_can_be_edited(self):
        """The cursor walks back into the pasted text."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("first\nsecond\nthird"))

        # Walk the cursor up to the first line.
        app._handle_key("UP")
        app._handle_key("UP")
        self.assertEqual(app.state.cursor_pos, len("first"))

        # And edit it there.
        app._handle_key("X")
        self.assertEqual(app.state.input_buffer, "firstX\nsecond\nthird")

    def test_the_paste_does_not_submit(self):
        """A paste is text, not a command."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("what is this\nand this"))

        self.assertIsNone(
            app._active_query_task,
            "the paste submitted the command bar",
        )


class TestTheCursorWalksTheLines(unittest.TestCase):
    """Up and down walk the lines of a multi-line input."""

    def test_up_and_down_move_between_the_lines(self):
        """The cursor goes where the operator says."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("first\nsecond"))
        self.assertEqual(app.state.cursor_pos, len("first\nsecond"))

        # The cursor is at the end of the last line; one line up it is
        # at the end of the line above -- the column is kept, and it is
        # clamped to the end of that line.
        app._handle_key("UP")
        self.assertEqual(
            cursor_line(app.state.input_buffer, app.state.cursor_pos),
            0,
            "the cursor did not walk up to the line above",
        )
        self.assertEqual(app.state.cursor_pos, len("first"))

        app._handle_key("DOWN")
        self.assertEqual(
            cursor_line(app.state.input_buffer, app.state.cursor_pos),
            1,
            "the cursor did not walk back down to the last line",
        )

    def test_the_column_is_kept_when_the_line_is_long_enough(self):
        """The cursor keeps its place in the line."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("first line\nsecond line"))
        app._handle_key("LEFT")
        app._handle_key("LEFT")
        app._handle_key("UP")

        self.assertEqual(app.state.cursor_pos, len("first line") - 1)

    def test_the_history_is_still_there_for_a_single_line(self):
        """A one-line input walks the history, as it always did."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app.state.command_history = ["\\stats", "\\tools"]

        app._handle_key("UP")
        self.assertEqual(app.state.input_buffer, "\\tools")

        app._handle_key("UP")
        self.assertEqual(app.state.input_buffer, "\\stats")

    def test_the_cursor_stops_at_the_first_line(self):
        """The cursor does not walk out of the input."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("first\nsecond"))
        app._handle_key("UP")
        app._handle_key("UP")
        app._handle_key("UP")

        self.assertEqual(
            app.state.cursor_pos,
            len("first"),
            "the cursor walked out of the input",
        )

    def test_the_history_is_reached_at_the_first_line(self):
        """The history is one line up from the first line of the input."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app.state.command_history = ["\\stats"]
        app._handle_key(PastedText("first\nsecond"))

        # The cursor is on the last line: it walks the lines of the
        # input first.
        app._handle_key("UP")
        self.assertEqual(app.state.input_buffer, "first\nsecond")

        # And on the first line it reaches the history.
        app._handle_key("UP")
        self.assertEqual(app.state.input_buffer, "\\stats")


class TestTheTextOfTheInput(unittest.TestCase):
    """The text of the input is text, not markup."""

    def test_the_brackets_of_the_text_are_shown(self):
        """Rich reads square brackets as markup."""
        screen = footer_screen("rm -rf [a-z]")

        self.assertIn("[a-z]", screen)

    def test_the_brackets_of_a_paste_are_shown(self):
        """A paste is operator input too."""
        app = TuiApp(agent=None, prompt_handler_fn=None)

        app._handle_key(PastedText("rm -rf [a-z]"))
        screen = footer_screen(app.state.input_buffer, app.state.cursor_pos)

        self.assertIn("[a-z]", screen)

    def test_a_closing_bracket_does_not_break_the_footer(self):
        """A tag that closes nothing must not take the panel down."""
        panel = render_footer(input_buffer="[/]", cursor_pos=3)
        screen = render_screen(footer_panel=panel)

        self.assertIn("[/]", screen)


class TestTheHelpers(unittest.TestCase):
    """The helpers of the input text."""

    def test_an_empty_text_is_one_line(self):
        """The bar always has a line."""
        self.assertEqual(line_count(""), 1)
        self.assertEqual(visible_line_count(""), 1)

    def test_the_cursor_is_on_the_line_it_is_written_on(self):
        """The cursor of a text is on the line of its position."""
        text = "first\nsecond\nthird"

        self.assertEqual(cursor_line(text, len(text)), 2)
        self.assertEqual(cursor_line(text, move_cursor_up(text, len(text))), 1)
        self.assertEqual(cursor_line(text, move_cursor_down(text, 0)), 1)
        self.assertEqual(move_cursor_down(text, len(text)), len(text))

    def test_the_column_is_kept_and_clamped_to_the_line(self):
        """The cursor keeps its place, and stops at the end of the line."""
        text = "first\nsecond"

        # The cursor is at the end of "second" -- six cells in.
        self.assertEqual(move_cursor_up(text, len(text)), len("first"))


if __name__ == "__main__":
    unittest.main()
