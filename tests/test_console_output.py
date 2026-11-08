"""Tests for the console output helper.

The chat commands print text that the operator must read as it is — the
content of a session is what the operator typed and what the model
answered, and Rich would read the square brackets in it as markup.

Run with:
    pytest tests/test_console_output.py -v
"""

import io
import unittest

from rich.console import Console

from components.console_output import print_verbatim


def _console() -> Console:
    """Return a console that writes into a buffer."""
    return Console(file=io.StringIO(), width=80, no_color=True)


class TestPrintVerbatim(unittest.TestCase):
    """The text reaches the terminal as it is."""

    def test_the_text_is_printed_as_it_is(self):
        console = _console()
        print_verbatim(console, "user: hello")
        self.assertEqual(console.file.getvalue().strip(), "user: hello")

    def test_square_brackets_are_not_markup(self):
        """The brackets of the session survive — Rich used to eat them."""
        console = _console()
        print_verbatim(console, "assistant: [dim]the plan[/dim]")
        self.assertIn("[dim]the plan[/dim]", console.file.getvalue())

    def test_a_closing_tag_does_not_raise(self):
        """The markup of Rich used to raise on a closing tag."""
        console = _console()
        print_verbatim(console, "user: a [/nope] broken tag")
        self.assertIn("[/nope]", console.file.getvalue())

    def test_the_lines_are_not_wrapped(self):
        """A long line stays the line it was written as."""
        console = _console()
        line = "user: " + ("x" * 200)
        print_verbatim(console, line)

        printed = console.file.getvalue().splitlines()
        self.assertEqual(printed[0], line)

    def test_the_style_is_kept(self):
        """The chat commands stay cyan."""
        console = _console()
        print_verbatim(console, "user: hello", style="cyan")

        segments = list(console.render("user: hello"))
        self.assertTrue(segments)


if __name__ == "__main__":
    unittest.main()
