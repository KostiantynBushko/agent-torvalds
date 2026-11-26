"""
The document pane and the end of the answer it is showing.

The *Markdown Document Viewer* carries the answer of the agent, and the
answer is **written while the operator watches it**: the workflow
streams the answer token by token, and every token lands in the
document of the pane.

The window of the pane **follows the end of the answer** while it is
written: every line that is written appears at the bottom of the frame,
and the operator watches the answer as it is written.

The operator may move the window himself -- `Up`, `Down`, `Home`,
`End` -- and the answer that grows does not move it back: the window
holds the place he put it in, and the text he reads does not slide
away under him.  `End` puts the window at the end of the answer again,
and the window follows the end from then on.

What the tests hold together:

* **the window follows the end** -- every line that is written is on
  the screen, at the bottom of the frame;
* **the operator moves the window himself** -- the answer that grows
  does not drag the window back to the end;
* **the operator may follow the answer again** -- `End` arms the
  follow, and the window follows the tail while the answer is written;
* **the answer that is complete goes to the end** -- the last lines of
  the answer are on the screen;
* **the operator who is reading is not taken away** -- the answer that
  is complete does not take him away from the paragraph he reads;
* **a new document opens at its beginning** -- the output of a command
  is a document the operator has never seen.

Run with:
    pytest tests/test_tui_document_auto_scroll.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

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

#: The marker of the **last** line of the answer.  It is the line that
#: must be on the screen when the answer is complete.
LAST_MARKER = "THE-LAST-LINE-OF-THE-ANSWER"


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


def the_subtitle(state: TuiState) -> str:
    """The subtitle of the document pane.

    Args:
        state: The state of the TUI.

    Returns:
        The subtitle, as the operator reads it.
    """
    view = MarkdownView(a_console())
    panel = view.render(state, max_height=state.document_height, width=WIDTH)
    return str(panel.subtitle)


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
    parts.append(LAST_MARKER)
    return "\n\n".join(parts)


def a_long_paragraph() -> str:
    """A paragraph that is longer than the pane.

    It is what the agent writes while the operator reads: it pushes the
    end of the answer off the screen.

    Returns:
        The paragraph.
    """
    return "\n\n".join(
        f"Line {index} of the paragraph the agent is writing." for index in range(40)
    )


def the_pieces_of(answer: str) -> list:
    """The answer in the pieces the workflow streams it in.

    Args:
        answer: The answer.

    Returns:
        The pieces of the answer.
    """
    return [piece + "\n\n" for piece in answer.split("\n\n")]


def a_run_that_is_written(state: TuiState, answer: str = "") -> None:
    """The operator asks a question, and the answer is written.

    The answer is written in pieces, the way the workflow streams it:
    token by token, and every token lands in the document of the pane.
    The pane is drawn after every piece -- the TUI draws the pane on
    every frame, and the follow of the end happens in the draw.

    Args:
        state: The state of the TUI.
        answer: The answer of the run.
    """
    state.set_busy(True, "a question")
    state.markdown_content = ""
    the_window(state)
    for piece in the_pieces_of(answer or an_answer()):
        state.append_stream_token(piece)
        the_window(state)


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


class TestTheWindowWhileTheAnswerIsWritten:
    """The window of the pane follows the end of the answer."""

    def test_the_window_follows_the_end_of_the_answer(self):
        """The newest line of the answer is on the screen."""
        state = a_state()
        a_run_that_is_written(state)

        state.append_stream_token(NEWEST_MARKER)
        window = the_window(state)

        assert the_line_of(window, NEWEST_MARKER) >= 0, (
            "the window did not follow the end of the answer while it was "
            f"being written: the window is at {state.scroll_offset} of "
            f"{state.max_scroll()}"
        )
        assert state.scroll_offset == state.max_scroll(), (
            f"the window is at {state.scroll_offset} and not at the end of "
            f"the answer, which is at {state.max_scroll()}"
        )

    def test_the_window_follows_every_update(self):
        """Every line that is written appears at the bottom of the frame."""
        state = a_state()
        state.set_busy(True, "a question")
        state.markdown_content = ""
        the_window(state)

        for number, piece in enumerate(the_pieces_of(an_answer()), start=1):
            state.append_stream_token(piece)
            window = the_window(state)

            assert state.scroll_offset == state.max_scroll(), (
                f"the window did not follow the end of the answer after the "
                f"piece {number} was written: it is at "
                f"{state.scroll_offset} and not at {state.max_scroll()}"
            )

    def test_the_newest_line_is_the_last_line_of_the_frame(self):
        """The newest line of the answer is at the bottom of the frame."""
        state = a_state()
        a_run_that_is_written(state)

        state.append_stream_token(NEWEST_MARKER)
        window = the_window(state)

        line = the_line_of(window, NEWEST_MARKER)
        assert line >= 0, "the newest line of the answer is not on the screen"
        assert line == len(window) - 1, (
            f"the newest line of the answer is on line {line} of "
            f"{len(window)}, and not at the bottom of the frame"
        )


class TestTheOperatorWhoMovesTheWindow:
    """The operator may move the window while the answer is written."""

    def test_the_operator_may_move_the_window_while_the_answer_is_written(self):
        """The window goes where the operator puts it."""
        state = a_state()
        a_run_that_is_written(state)

        state.scroll_up(lines=3)
        before = state.scroll_offset
        assert before == state.max_scroll() - 3

        # The answer that grows does not take the window back.
        state.append_stream_token(f"\n\n{a_long_paragraph()}")
        the_window(state)

        assert state.scroll_offset == before, (
            f"the window was moved back to {state.scroll_offset} by the "
            f"answer that grew: it was at {before}"
        )

    def test_the_line_the_operator_reads_does_not_move(self):
        """The paragraph the operator reads stays where he put it."""
        state = a_state()
        a_run_that_is_written(state)

        # The operator reads the end of the answer and scrolls up -- the
        # line he reads is the one just above the end of the answer.
        state.scroll_up(lines=3)
        before = the_line_of(the_window(state), READ_MARKER)
        assert before >= 0, "the paragraph the operator reads is not on the screen"

        # The agent writes a paragraph that is longer than the pane.
        state.append_stream_token(f"\n\n{a_long_paragraph()}")
        window = the_window(state)

        assert the_line_of(window, READ_MARKER) == before, (
            "the paragraph the operator reads moved while the answer grew: "
            f"it was on line {before}, and it is on line "
            f"{the_line_of(window, READ_MARKER)}"
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

    def test_the_end_key_arms_the_follow_again(self):
        """The operator asks for the end, and the window follows it."""
        state = a_state()
        a_run_that_is_written(state)

        # The operator reads a paragraph and scrolls away from the end.
        state.scroll_up(lines=3)
        assert state.scroll_offset < state.max_scroll()

        # The operator asks for the end of the answer.
        state.scroll_end()
        assert state.scroll_offset == state.max_scroll()

        # The answer grows, and the window follows it.
        state.append_stream_token(f"\n\n{a_long_paragraph()}")
        window = the_window(state)

        assert state.scroll_offset == state.max_scroll(), (
            f"the window did not follow the end of the answer again: it is "
            f"at {state.scroll_offset} and not at {state.max_scroll()}"
        )
        assert the_line_of(window, NEWEST_MARKER) < 0, (
            "the window followed the end, and the marker that was written "
            "before the follow was armed is on the screen"
        )


class TestTheAnswerThatIsComplete:
    """The window goes to the end of the answer when the answer is complete."""

    def test_the_window_goes_to_the_end_of_the_answer(self):
        """The last lines of the answer are on the screen."""
        state = a_state()
        a_run_that_is_written(state)

        # The run is over: the answer is the document of the pane.
        state.set_markdown_content(an_answer(), answer_is_complete=True)
        window = the_window(state)

        assert the_line_of(window, LAST_MARKER) >= 0, (
            "the last line of the answer is not on the screen: the window "
            f"is at {state.scroll_offset} of {state.max_scroll()}"
        )
        assert state.scroll_offset == state.max_scroll(), (
            f"the window is at {state.scroll_offset} and not at the end of "
            f"the answer, which is at {state.max_scroll()}"
        )

    def test_the_answer_that_is_complete_does_not_take_the_operator_away(self):
        """The operator who is reading a paragraph keeps his place."""
        state = a_state()
        a_run_that_is_written(state)
        the_window(state)

        # The operator reads the end of the answer and scrolls up -- the
        # line he reads is the one just above the end of the answer.
        state.scroll_end()
        state.scroll_up(lines=3)
        before = state.scroll_offset

        # The run is over: the answer is complete.
        state.set_markdown_content(an_answer(), answer_is_complete=True)
        window = the_window(state)

        assert state.scroll_offset == before, (
            f"the window was taken away from the paragraph the operator "
            f"reads: it was at {before}, and it is at {state.scroll_offset}"
        )
        assert the_line_of(window, LAST_MARKER) < 0, (
            "the window went to the end of the answer while the operator "
            "was reading a paragraph of it"
        )

    def test_the_window_goes_to_the_end_when_the_operator_follows_the_answer(self):
        """The operator who is at the end of the answer is at its end."""
        state = a_state()
        a_run_that_is_written(state)
        the_window(state)

        # The operator scrolls to the end of the answer: he follows it.
        state.scroll_end()

        # The run is over: the answer is complete.
        state.set_markdown_content(an_answer(), answer_is_complete=True)
        window = the_window(state)

        assert the_line_of(window, LAST_MARKER) >= 0, (
            "the last line of the answer is not on the screen: the window "
            f"is at {state.scroll_offset} of {state.max_scroll()}"
        )


class TestThePane:
    """The pane says what it does."""

    def test_the_pane_says_that_the_answer_is_being_written(self):
        """The operator is told that the answer is still coming."""
        state = a_state()
        a_run_that_is_written(state)

        subtitle = the_subtitle(state)

        assert "the answer is being written" in subtitle, (
            f"the pane does not say that the answer is being written: its "
            f"subtitle is {subtitle!r}"
        )

    def test_the_pane_says_that_it_follows_the_end(self):
        """The pane says that it follows the end of the answer."""
        state = a_state()
        a_run_that_is_written(state)

        subtitle = the_subtitle(state)

        assert "the window follows the end" in subtitle, (
            f"the pane does not say that it follows the end of the answer: "
            f"its subtitle is {subtitle!r}"
        )

    def test_the_pane_says_that_it_holds_its_place(self):
        """The pane says that it stands still on purpose."""
        state = a_state()
        a_run_that_is_written(state)

        # The operator reads a paragraph and scrolls away from the end.
        state.scroll_up(lines=3)
        subtitle = the_subtitle(state)

        assert "the window holds its place" in subtitle, (
            f"the pane does not say that it holds its place: its subtitle "
            f"is {subtitle!r}"
        )
        assert "the window follows the end" not in subtitle, (
            f"the pane says that it follows the end, and its window holds "
            f"its place: its subtitle is {subtitle!r}"
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
