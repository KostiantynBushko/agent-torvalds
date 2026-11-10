"""
The TUI footer — the line the operator types on.

The footer carries two things: the command bar, and the HITL panel that
holds the question of the agent *and* the line the answer is typed on.
The HITL panel is taller than the command bar, and a panel that is
taller than the partition it lives in is cropped from the bottom — the
bottom of that panel is the answer line.

The typed text is also operator input: it may hold square brackets, and
Rich reads square brackets as markup.  The text between them used to
disappear from the screen.

Run with:
    pytest tests/test_tui_footer.py -v
"""
import io
import unittest

from rich.console import Console

from components.tui.layout_manager import (
    FOOTER_HEIGHT,
    build_torvalds_layout,
    fit_footer,
    footer_height,
    render_footer,
)


def render_screen(width=120, height=24, footer_panel=None, layout=None,
                  hitl_active=False):
    """Render the TUI the way the app does, and return what is on screen.

    Args:
        width: The width of the terminal.
        height: The height of the terminal.
        footer_panel: The panel to put into the footer partition.
        layout: The layout to render; a fresh one by default.
        hitl_active: Whether a question of the agent is waiting.

    Returns:
        The text of the screen.
    """
    from rich.live import Live

    console = Console(width=width, height=height, file=io.StringIO())
    layout = layout if layout is not None else build_torvalds_layout()

    if footer_panel is not None:
        fit_footer(layout, console, footer_panel, hitl_active)
        layout["footer"].update(footer_panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


class TestTheFooterShowsWhatIsTyped(unittest.TestCase):
    """What the operator types has to be on the screen."""

    def test_the_typed_answer_is_visible_while_a_question_is_waiting(self):
        """The answer line is the last line of the HITL panel."""
        panel = render_footer(
            input_buffer="ZZQQ",
            cursor_pos=4,
            hitl_active=True,
            hitl_prompt="Which file should I read?",
        )
        screen = render_screen(footer_panel=panel, hitl_active=True)

        self.assertIn(
            "ZZQQ",
            screen,
            "the typed answer is not on the screen -- the footer is "
            "cropped and the operator types into the void",
        )
        self.assertIn(
            "Answer:",
            screen,
            "the answer line is missing from the footer",
        )

    def test_the_question_is_visible_while_a_question_is_waiting(self):
        """The question is what the operator is answering."""
        panel = render_footer(
            input_buffer="ZZQQ",
            cursor_pos=4,
            hitl_active=True,
            hitl_prompt="Which file should I read?",
        )
        screen = render_screen(footer_panel=panel, hitl_active=True)

        self.assertIn("AGENT QUESTION", screen)
        self.assertIn("Which file should I read?", screen)

    def test_the_typed_answer_is_visible_for_a_long_question(self):
        """A question that wraps takes more room, and the answer keeps it."""
        question = "Which of these files should I read? " * 8
        panel = render_footer(
            input_buffer="ZZQQ",
            cursor_pos=4,
            hitl_active=True,
            hitl_prompt=question,
        )
        screen = render_screen(footer_panel=panel, hitl_active=True)

        self.assertIn(
            "ZZQQ",
            screen,
            "a question that wraps pushes the answer line out of the "
            "footer",
        )

    def test_the_typed_answer_is_visible_at_a_narrow_terminal(self):
        """A narrow terminal wraps the question more, not less."""
        panel = render_footer(
            input_buffer="ZZQQ",
            cursor_pos=4,
            hitl_active=True,
            hitl_prompt="Which file should I read?",
        )
        screen = render_screen(width=80, footer_panel=panel, hitl_active=True)

        self.assertIn("ZZQQ", screen)

    def test_the_typed_command_is_visible_without_a_question(self):
        """The command bar has always shown what is typed."""
        panel = render_footer(input_buffer="ZZQQ", cursor_pos=4)
        screen = render_screen(footer_panel=panel, hitl_active=True)

        self.assertIn("ZZQQ", screen)


class TestTheTypedTextIsNotMarkup(unittest.TestCase):
    """The typed text is operator input, and Rich reads ``[]`` as markup."""

    def test_brackets_in_the_answer_are_shown(self):
        """The text between the brackets used to disappear."""
        panel = render_footer(
            input_buffer="rm -rf [a-z]",
            cursor_pos=11,
            hitl_active=True,
            hitl_prompt="Which file should I read?",
        )
        screen = render_screen(footer_panel=panel, hitl_active=True)

        self.assertIn(
            "[a-z]",
            screen,
            "the brackets in the typed answer were read as markup and "
            "the text between them was swallowed",
        )

    def test_a_closing_bracket_does_not_break_the_footer(self):
        """A tag that closes nothing must not take the panel down."""
        panel = render_footer(
            input_buffer="[/]",
            cursor_pos=3,
            hitl_active=True,
            hitl_prompt="Which file should I read?",
        )
        # The panel is built without an exception -- that is the check.
        screen = render_screen(footer_panel=panel, hitl_active=True)
        self.assertIn("AGENT QUESTION", screen)

    def test_brackets_in_the_command_are_shown(self):
        """The command bar escapes the text already; it stays that way."""
        panel = render_footer(input_buffer="ls [a-z]", cursor_pos=8)
        screen = render_screen(footer_panel=panel, hitl_active=True)

        self.assertIn("[a-z]", screen)


class TestTheFooterGetsTheRoomItNeeds(unittest.TestCase):
    """The footer partition is sized to the panel it holds."""

    def test_the_footer_is_three_lines_without_a_question(self):
        """The command bar is one line of content."""
        layout = build_torvalds_layout()
        console = Console(width=120, height=24, file=io.StringIO())

        given = fit_footer(layout, console, render_footer(input_buffer="", cursor_pos=0))

        self.assertEqual(given, FOOTER_HEIGHT)
        self.assertEqual(layout["footer"].size, FOOTER_HEIGHT)

    def test_the_footer_grows_while_a_question_is_waiting(self):
        """The HITL panel carries the question and the answer."""
        layout = build_torvalds_layout()
        console = Console(width=120, height=24, file=io.StringIO())
        panel = render_footer(
            input_buffer="",
            cursor_pos=0,
            hitl_active=True,
            hitl_prompt="Which file should I read?",
        )

        given = fit_footer(layout, console, panel, True)

        self.assertGreater(given, FOOTER_HEIGHT)
        self.assertEqual(layout["footer"].size, given)

    def test_the_footer_shrinks_back_after_the_answer(self):
        """The body gets its line back when the question is answered."""
        layout = build_torvalds_layout()
        console = Console(width=120, height=24, file=io.StringIO())

        fit_footer(
            layout,
            console,
            render_footer(input_buffer="", cursor_pos=0, hitl_active=True, hitl_prompt="Which?"),
            True,
        )
        given = fit_footer(layout, console, render_footer(input_buffer="", cursor_pos=0))

        self.assertEqual(given, FOOTER_HEIGHT)

    def test_the_height_of_the_panel_is_the_height_it_is_given(self):
        """The partition is never smaller than the panel it holds."""
        console = Console(width=120, height=24, file=io.StringIO())
        panel = render_footer(
            input_buffer="ZZQQ",
            cursor_pos=4,
            hitl_active=True,
            hitl_prompt="Which file should I read?",
        )

        self.assertEqual(
            footer_height(console, panel),
            len(console.render_lines(panel, console.options.update(height=None))),
        )


class TestTheTerminalIsNeverLeftMute(unittest.TestCase):
    """The reader puts the terminal into cbreak mode; it gives it back."""

    def test_the_reader_registers_itself_with_atexit(self):
        """An exit that does not go through ``stop()`` still restores it.

        The echo is off while the TUI runs, because the TUI draws the
        typed text itself.  The terminal keeps that state when the
        process dies, and the state belongs to the terminal -- so the
        operator is left with a terminal that shows nothing of what
        they type.
        """
        import atexit

        from components.tui.input_reader import NonBlockingInputReader

        before = atexit._ncallbacks()
        reader = NonBlockingInputReader()
        after = atexit._ncallbacks()

        self.assertEqual(
            after,
            before + 1,
            "the reader does not give the terminal back when the "
            "interpreter shuts down",
        )
        self.assertTrue(callable(reader.stop))

    def test_the_reader_restores_the_terminal_it_found(self):
        """The attributes it found are the attributes it puts back."""
        import sys
        import termios

        from components.tui.input_reader import NonBlockingInputReader

        reader = NonBlockingInputReader()
        if not reader._is_tty:
            self.skipTest("stdin is not a terminal")

        fd = sys.stdin.fileno()
        before = termios.tcgetattr(fd)
        reader.start()
        try:
            during = termios.tcgetattr(fd)
            self.assertFalse(
                during[3] & termios.ECHO,
                "the reader does not switch the echo off",
            )
        finally:
            reader.stop()
        after = termios.tcgetattr(fd)

        self.assertEqual(after[3], before[3], "the terminal was not given back")

    def test_stopping_a_reader_that_never_started_is_harmless(self):
        """The hook may fire when the reader never ran."""
        from components.tui.input_reader import NonBlockingInputReader

        reader = NonBlockingInputReader()
        reader.stop()

        self.assertFalse(reader._is_active)


if __name__ == "__main__":
    unittest.main()
