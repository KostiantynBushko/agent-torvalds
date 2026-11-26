"""
The *Markdown Document Viewer* and the end of the answer it is showing.

**The operator asked for the auto scroll of the document pane:**

> auto scroll in "Markdown Document Viewer"

The pane carries the answer of the agent, and the answer is **written
while the operator watches it**: the workflow streams the answer token
by token, and every token lands in the document of the pane.

The operator asked on 2026-11-26 for a window that **does not move by
itself**: the text he reads must not slide away under him while the
answer is written.  The pane answers that with two rules:

* the window **holds its place** while the answer is written -- the
  operator may move it himself, and the answer that grows does not move
  it back;
* the window **goes to the end of the answer** when the answer is
  complete -- the operator reads the last lines of it without scrolling
  for them, and the answer that is complete does not take him away from
  a paragraph he is reading.

The probe answers five questions:

  1. **Does the window stay where it is while the answer is written?**

  2. **Does the window go to the end when the answer is complete?**

  3. **Does the operator who scrolls up keep his place?**

  4. **Does the operator move the window himself while the answer is
     written?**

  5. **Does a new document open at its beginning?**

Usage:
    python investigate/tui-document-auto-scroll/probe_document_auto_scroll.py

The exit code is 0 when every check holds, 1 when one does not.

The probe writes nothing and talks to no service.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402

from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    document_pane_width,
    pane_content_height,
)
from components.tui.markdown_view import MarkdownView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The width of the terminal of the operator.
WIDTH = 120

#: The height of the terminal of the operator.
HEIGHT = 40

#: The marker of the last line of the answer that was written before
#: the growth.
END_MARKER = "THE-END-OF-THE-ANSWER"

#: The marker of the **newest** line of the answer -- the line the
#: agent has just written.  It is unique in the document, and the
#: probe looks for it on the screen.
NEWEST_MARKER = "THE-NEWEST-LINE-OF-THE-ANSWER"

#: The marker of a line near the end of the answer -- the line the
#: operator scrolls up to read.
MIDDLE_MARKER = "THE-PARAGRAPH-THE-OPERATOR-READS"

#: The marker of the **last** line of the answer.  It is the line that
#: must be on the screen when the answer is complete.
LAST_MARKER = "THE-LAST-LINE-OF-THE-ANSWER"

#: The heading of a document that is new to the operator.
NEW_DOCUMENT_HEADING = "THE-TOOLS-OF-THE-AGENT"


def a_state() -> TuiState:
    """A state whose document pane has the height of the real layout.

    Returns:
        The state.
    """
    state = TuiState()
    layout = build_torvalds_layout()
    console = Console(width=WIDTH, height=HEIGHT, color_system=None)
    console.render_lines(layout, console.options.update_dimensions(WIDTH, HEIGHT))
    state.document_height = pane_content_height(layout, "markdown_pane")
    return state


def the_window_of(state: TuiState) -> List[str]:
    """The lines the document pane shows on the screen of the operator.

    The pane is drawn by the **real** view, at the width the layout
    gives it, and the lines that come out of it are the lines the
    operator sees.

    Args:
        state: The state of the TUI.

    Returns:
        The lines of the window.
    """
    view = MarkdownView(Console(width=WIDTH, height=HEIGHT, color_system=None))
    panel = view.render(
        state,
        max_height=state.document_height,
        width=document_pane_width(WIDTH),
    )
    return panel.renderable.plain.split("\n")


def an_answer(paragraphs: int) -> str:
    """An answer that is longer than the pane.

    The paragraph the operator reads is near the end of the answer: it
    is the paragraph he scrolls up to, after the answer was written.

    Args:
        paragraphs: The number of paragraphs of the answer.

    Returns:
        The answer.
    """
    parts = []
    for index in range(paragraphs * 2):
        if index == paragraphs * 2 - 3:
            parts.append(MIDDLE_MARKER)
            continue
        parts.append(
            f"Paragraph {index}. The answer of the agent is written while "
            f"the operator watches it, and the pane carries it."
        )
    parts.append(END_MARKER)
    parts.append(LAST_MARKER)
    return "\n\n".join(parts)


def a_long_paragraph() -> str:
    """A paragraph that is longer than the pane.

    It is what the agent writes while the operator reads: a paragraph
    that is longer than the pane pushes the end of the answer off the
    screen.

    Returns:
        The paragraph.
    """
    return "\n\n".join(
        f"Line {index} of the paragraph the agent is writing." for index in range(40)
    )


def a_run_that_is_written(state: TuiState, answer: str = "") -> None:
    """The operator asks a question, and the answer is written.

    The answer is written in pieces, the way the workflow streams it.

    Args:
        state: The state of the TUI.
        answer: The answer of the run.
    """
    state.set_busy(True, "a question")
    state.markdown_content = ""
    the_window_of(state)
    for piece in (answer or an_answer(20)).split("\n\n"):
        state.append_stream_token(piece + "\n\n")
    # The pane is drawn: the number of lines the document has is the
    # one of the frame that was drawn, and the window of the pane is
    # clamped to it.
    the_window_of(state)


def the_answer_is_complete(state: TuiState, answer: str) -> None:
    """The run is over: the answer of the run is the document of the pane.

    The call is the one the application makes.  The name of the
    argument is read from the signature of the method, because the
    probe measures the behaviour of the tree it runs in -- and it must
    run on the tree **before** the change as well, to say what the
    change adds.

    Args:
        state: The state of the TUI.
        answer: The answer of the run.
    """
    parameters = inspect.signature(state.set_markdown_content).parameters
    if "answer_is_complete" in parameters:
        state.set_markdown_content(answer, answer_is_complete=True)
        return
    state.set_markdown_content(answer)


def the_line_of(window: List[str], needle: str) -> int:
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


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


def check_the_window_stays_where_it_is() -> Tuple[bool, str]:
    """The window does not move while the answer is written.

    The answer grows, and the window does not follow it: the text the
    operator reads does not slide away under him.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state()
    a_run_that_is_written(state)

    # The agent writes more of the answer while the operator watches.
    state.append_stream_token(f"{NEWEST_MARKER}\n\n")
    window = the_window_of(state)

    holds = the_line_of(window, NEWEST_MARKER) < 0 and state.scroll_offset == 0
    report = (
        f"the offset of the window: {state.scroll_offset} of "
        f"{state.max_scroll()} lines\n"
        f"the newest line of the answer is on the screen: "
        f"{the_line_of(window, NEWEST_MARKER) >= 0}"
    )
    return holds, report


def check_the_window_goes_to_the_end_of_the_complete_answer() -> Tuple[bool, str]:
    """The window goes to the end of the answer when it is complete.

    The operator reads the last lines of the answer without scrolling
    for them.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state()
    a_run_that_is_written(state)

    # The run is over: the answer is complete.
    the_answer_is_complete(state, an_answer(20))
    window = the_window_of(state)

    holds = the_line_of(window, LAST_MARKER) >= 0
    report = (
        f"the offset of the window: {state.scroll_offset} of "
        f"{state.max_scroll()} lines\n"
        f"the last line of the answer is on the screen: "
        f"{the_line_of(window, LAST_MARKER) >= 0}"
    )
    return holds, report


def check_the_operator_keeps_his_place() -> Tuple[bool, str]:
    """The operator who scrolled up keeps his place.

    The answer grows while he reads, and the window does not move.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state()
    a_run_that_is_written(state)

    # The operator reads the end of the answer and scrolls up from there.
    state.scroll_end()
    state.scroll_up(lines=8)
    before = the_line_of(the_window_of(state), MIDDLE_MARKER)

    # The agent writes a paragraph while he reads.
    state.append_stream_token(f"\n\n{a_long_paragraph()}")
    window = the_window_of(state)
    after = the_line_of(window, MIDDLE_MARKER)

    holds = before >= 0 and before == after
    report = (
        f"the line of the paragraph before: {before}\n"
        f"the line of the paragraph after:  {after}\n"
        f"the offset of the window: {state.scroll_offset}"
    )
    return holds, report


def check_the_operator_moves_the_window() -> Tuple[bool, str]:
    """The operator moves the window himself while the answer is written.

    The window goes where he puts it, and the answer that grows does
    not move it back.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state()
    a_run_that_is_written(state)
    the_window_of(state)

    # The operator scrolls down to the paragraph he reads.
    state.scroll_down(lines=5)
    before = state.scroll_offset

    # The agent writes a paragraph while he reads.
    state.append_stream_token(f"\n\n{a_long_paragraph()}")
    the_window_of(state)

    holds = state.scroll_offset == before
    report = (
        f"the offset of the window before: {before}\n"
        f"the offset of the window after:  {state.scroll_offset}"
    )
    return holds, report


def check_a_new_document_opens_at_its_beginning() -> Tuple[bool, str]:
    """A new document opens at its beginning.

    The output of a command is a document the operator has never seen.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state()
    state.set_markdown_content(an_answer(20))
    the_window_of(state)

    # The operator asks for the list of the tools: a new document.
    state.set_markdown_content(
        f"# {NEW_DOCUMENT_HEADING}\n\n"
        + "\n\n".join(f"- the tool number {index}" for index in range(40))
    )
    window = the_window_of(state)

    holds = NEW_DOCUMENT_HEADING in window[0]
    report = (
        f"the first line of the window: {window[0].strip()!r}\n"
        f"the offset of the window: {state.scroll_offset}"
    )
    return holds, report


def show_the_screen_of_the_operator() -> None:
    """Show the pane as the operator sees it, before and after the answer."""
    print("=" * 78)
    print("The document pane while the answer is written:")
    print("=" * 78)
    state = a_state()
    a_run_that_is_written(state)
    for line in the_window_of(state):
        print(f"  {line}")
    print()

    print("=" * 78)
    print("The document pane when the answer is complete:")
    print("=" * 78)
    the_answer_is_complete(state, an_answer(20))
    for line in the_window_of(state):
        print(f"  {line}")
    print()


def main() -> int:
    """Run every check and report what holds."""
    show_the_screen_of_the_operator()

    checks = (
        ("the window stays where it is while the answer is written",
         check_the_window_stays_where_it_is),
        ("the window goes to the end when the answer is complete",
         check_the_window_goes_to_the_end_of_the_complete_answer),
        ("the operator keeps his place while the answer grows",
         check_the_operator_keeps_his_place),
        ("the operator moves the window himself while the answer is written",
         check_the_operator_moves_the_window),
        ("a new document opens at its beginning",
         check_a_new_document_opens_at_its_beginning),
    )

    failed = 0
    print("=" * 78)
    for name, check in checks:
        ok, report = check()
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        for line in str(report).split("\n"):
            print(f"        {line}")
        if not ok:
            failed += 1
    print("=" * 78)

    if failed:
        print(f"{failed} check(s) do not hold.")
        return 1
    print("Every check holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
