"""
The document pane follows the end of the answer it is showing.

The *Markdown Document Viewer* carries the answer of the agent, and the
answer is **written while the operator watches it**: the workflow
streams the answer token by token, and every token lands in the
document of the pane.

The pane had **no auto scroll**.  The window of the pane stayed where
it was while the answer grew, and the operator was shown the beginning
of an answer that was still being written -- the part he had already
read, and never the part that was new.

What the tests hold together:

* **the window follows the end** -- the newest line of the answer is on
  the screen, and it stays on the screen while the answer is written;
* **the operator keeps his place** -- the operator who scrolls up to
  read a paragraph is not dragged back to the end by the next token;
* **the follow comes back** -- the operator who scrolls to the end
  again is at the end of the answer from then on;
* **a new document opens at its beginning** -- the output of a command
  is a document the operator has never seen;
* **a new run follows its answer** -- the answer of a run is written
  while the operator watches it.

Run with:
    pytest tests/test_tui_document_auto_scroll.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.tui.markdown_view import MarkdownView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The width of the terminal that is measured.
WIDTH = 120

#: The height of the terminal that is measured.
HEIGHT = 40

#: The number of lines the document pane shows.
PANE_HEIGHT = 12

#: The marker of the newest line of the answer.  It is unique in the
#: document, and the tests look for it on the screen.
NEWEST_MARKER = "THE-NEWEST-LINE-OF-THE-ANSWER"

#: The marker of the line the operator scrolls up to read.
READ_MARKER = "THE-PARAGRAPH-THE-OPERATOR-READS"


def a_console() -> Console:
    """A console of the size of a terminal.

    Returns:
        The console.
    """
    return Console(width=WIDTH, height=HEIGHT, color_system=None)


def a_state() -> TuiState:
    """A state whose document pane has the height that is measured.

    Returns:
        The state.
    """
    state = TuiState()
    state.document_height = PANE_HEIGHT
    return state


def the_window(state: TuiState) -> list:
    """The lines the document pane shows.

    The pane is drawn by the **real** view, and the lines that come out
    of it are the lines the operator sees.

    Args:
        state: The state of the TUI.

    Returns:
        The lines of the window.
    """
    view = MarkdownView(a_console())
    panel = view.render(state, max_height=state.document_height, width=WIDTH)
    return panel.renderable.plain.split("\n")


def an_answer(paragraphs: int = 20) -> str:
    """An answer that is longer than the pane.

    The line the operator reads is near the end of the answer: it is the
    line he scrolls up to, after the answer was written.

    Args:
        paragraphs: The number of paragraphs of the answer.

    Returns:
        The answer.
    """
    parts = []
    for index in range(paragraphs * 2):
        if index == paragraphs * 2 - 3:
            parts.append(READ_MARKER)
            continue
        parts.append(
            f"Paragraph {index}. The answer of the agent is written while "
            f"the operator watches it, and the pane carries it."
        )
    return "\n\n".join(parts)


def a_long_paragraph() -> str:
    """A paragraph that is longer than the pane.

    It is what the agent writes while the operator reads: it pushes the
    end of the answer off the screen, and the window that follows the
    end is the only way to keep the newest line on the screen.

    Returns:
        The paragraph.
    """
    return "\n\n".join(
        f"Line {index} of the paragraph the agent is writing." for index in range(40)
    )


def the_line_of(window, needle: str) -> int:
    """The number of the line of the window that carries the text.

    Args:
        window: The lines of the window.
        needle: The text to look for.

    Returns:
        The number of the line, and -1 when there is none.
    """
    for index, line in enumerate(window):
        if needle in line:
            return index
    return -1


class TestTheFollowOfTheDocumentPane:
    """The window follows the end of the answer."""

    def test_the_window_follows_the_end_of_the_answer(self):
        """The newest line of the answer is on the screen."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        # The operator read the whole answer: he is at its end.
        state.scroll_end()
        the_window(state)

        # The agent writes a paragraph that is longer than the pane.
        state.append_stream_token(f"\n\n{a_long_paragraph()}\n\n{NEWEST_MARKER}")
        window = the_window(state)

        assert the_line_of(window, NEWEST_MARKER) >= 0, (
            "the newest line of the answer is not on the screen: the "
            f"window is at {state.scroll_offset} of {state.max_scroll()}"
        )

    def test_the_window_follows_the_end_of_the_answer_of_a_run(self):
        """The answer of a run is written while the operator watches it."""
        state = a_state()

        # The operator asks a question: the run starts.
        state.set_busy(True, "a question")
        state.markdown_content = ""
        the_window(state)

        # The answer is written, token by token.
        for index in range(40):
            state.append_stream_token(f"Paragraph {index} of the answer.\n\n")
        state.append_stream_token(NEWEST_MARKER)
        window = the_window(state)

        assert the_line_of(window, NEWEST_MARKER) >= 0, (
            "the newest line of the answer is not on the screen: the "
            f"window is at {state.scroll_offset} of {state.max_scroll()}"
        )

    def test_the_operator_keeps_his_place(self):
        """The operator who scrolled up is not dragged back to the end."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        # The operator reads the end of the answer and scrolls up -- the
        # line he reads is the one just above the end of the answer.
        state.scroll_end()
        state.scroll_up(lines=3)
        before = the_line_of(the_window(state), READ_MARKER)
        assert before >= 0, "the line the operator reads is not on the screen"

        # The agent writes a paragraph while he reads.
        state.append_stream_token(f"\n\n{a_long_paragraph()}")
        window = the_window(state)

        assert the_line_of(window, READ_MARKER) == before, (
            "the line the operator reads moved while the answer grew"
        )

    def test_the_follow_comes_back_when_the_operator_scrolls_to_the_end(self):
        """The operator who comes back to the end follows the answer again."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        state.scroll_up(lines=8)
        the_window(state)

        # The operator scrolls back to the end of the answer.
        state.scroll_end()

        state.append_stream_token(f"\n\n{a_long_paragraph()}\n\n{NEWEST_MARKER}")
        window = the_window(state)

        assert the_line_of(window, NEWEST_MARKER) >= 0, (
            "the newest line of the answer is not on the screen: the "
            f"window is at {state.scroll_offset} of {state.max_scroll()}"
        )

    def test_the_follow_comes_back_when_the_operator_scrolls_down_to_the_end(self):
        """The last line down is the end: the window follows from there."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        state.scroll_up(lines=8)
        the_window(state)

        # The operator scrolls down, line by line, to the end.
        for _ in range(200):
            state.scroll_down(lines=1)

        state.append_stream_token(f"\n\n{a_long_paragraph()}\n\n{NEWEST_MARKER}")
        window = the_window(state)

        assert the_line_of(window, NEWEST_MARKER) >= 0, (
            "the newest line of the answer is not on the screen: the "
            f"window is at {state.scroll_offset} of {state.max_scroll()}"
        )

    def test_the_pane_opens_at_the_beginning_of_the_first_document(self):
        """The welcome of the console opens at its first line."""
        state = a_state()
        window = the_window(state)

        assert "Torvalds" in window[0], (
            f"the pane does not open at the beginning of the document: "
            f"its first line is {window[0].strip()!r}"
        )
        assert state.scroll_offset == 0

    def test_the_pane_says_that_it_follows_the_end(self):
        """The operator is told that the window moves by itself."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        # The operator is at the end of the answer.
        state.scroll_end()
        panel = MarkdownView(a_console()).render(
            state, max_height=state.document_height, width=WIDTH
        )

        assert "follows the end" in panel.subtitle, (
            f"the pane does not say that it follows the end: its subtitle "
            f"is {panel.subtitle!r}"
        )

    def test_the_pane_does_not_say_that_it_follows_the_end(self):
        """The pane does not lie: the window that holds its place does
        not follow the end."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        state.scroll_up(lines=8)
        panel = MarkdownView(a_console()).render(
            state, max_height=state.document_height, width=WIDTH
        )

        assert "follows the end" not in panel.subtitle, (
            f"the pane says that it follows the end, and its window holds "
            f"its place: its subtitle is {panel.subtitle!r}"
        )

    def test_a_new_document_opens_at_its_beginning(self):
        """The output of a command opens at its first line."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        state.set_markdown_content(
            "# The tools\n\n"
            + "\n\n".join(f"- the tool number {index}" for index in range(40))
        )
        window = the_window(state)

        assert "The tools" in window[0], (
            f"the window does not open at the beginning of the document: "
            f"its first line is {window[0].strip()!r}"
        )
        assert state.scroll_offset == 0

    def test_a_new_document_does_not_follow_the_end(self):
        """The output of a command does not follow the content."""
        state = a_state()
        state.set_markdown_content(
            "# The tools\n\n"
            + "\n\n".join(f"- the tool number {index}" for index in range(40))
        )
        the_window(state)

        state.append_stream_token(f"\n\n{NEWEST_MARKER}")
        window = the_window(state)

        assert the_line_of(window, NEWEST_MARKER) < 0, (
            "the window followed the end of a document that was not the "
            "answer of a run"
        )

    def test_the_answer_of_the_run_keeps_the_window_where_it_is(self):
        """The answer of a run is the document that was already there."""
        state = a_state()
        state.set_busy(True, "a question")
        state.markdown_content = ""
        the_window(state)

        for index in range(40):
            state.append_stream_token(f"Paragraph {index} of the answer.\n\n")
        the_window(state)

        # The operator scrolls up while the answer is written.
        state.scroll_up(lines=5)
        before = state.scroll_offset

        # The run is over: the answer is the document of the pane.
        state.set_markdown_content(an_answer(), follows_end=True)
        window = the_window(state)

        assert state.scroll_offset == before, (
            f"the window moved to {state.scroll_offset} when the answer of "
            f"the run arrived, and it was at {before}"
        )
        assert the_line_of(window, NEWEST_MARKER) < 0


class TestTheScrollOfTheDocumentPane:
    """The scroll of the pane is the scroll of the state."""

    def test_the_offset_is_the_offset_of_the_scroll(self):
        """The number of the state is the number of the scroll."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        state.scroll_down(lines=3)

        assert state.scroll_offset == state.document_scroll.offset

    def test_the_number_of_lines_is_the_number_of_the_scroll(self):
        """The size of the document is the size of the scroll."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        assert state.total_rendered_lines == state.document_scroll.total_lines
        assert state.total_rendered_lines > PANE_HEIGHT

    def test_the_window_is_clamped_to_the_content(self):
        """The window never walks past the end of the document."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        state.scroll_down(lines=1000)

        assert state.scroll_offset <= state.max_scroll()

    def test_the_window_does_not_go_past_the_end(self):
        """The window of a document that is shorter than it was."""
        state = a_state()
        state.set_markdown_content(an_answer())
        the_window(state)

        state.scroll_end()
        state.set_markdown_content("A short answer.\n")
        the_window(state)

        assert state.scroll_offset <= state.max_scroll()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
