"""
The document pane re-renders its content when its width changes.

The operator closes the workflow pane and the telemetry pane -- the two
panes of the sidebar -- and the document pane takes the whole of the body.
The content of the pane was **not** re-wrapped: it kept the width it had
while the sidebar was on the screen, and a third of the pane stood empty.

The cause was a guess.  The content was wrapped to 62% of the width of the
terminal, and the guess knew nothing about the sidebar -- the layout
divides the body 65/35, and the document pane takes the whole of it when
the sidebar leaves.  The pane is now told how wide it is, the way the
progress pane is told, and the content is wrapped to the width the pane
really has.

What the tests hold together:

* **the width that is computed is the width the layout uses** -- the
  region of the pane in the drawn layout, with the sidebar and without it;
* **the content is wrapped to the width of the pane** -- the widest line
  of the content reaches the width of the pane, and no line is wider than
  the area it is shown in;
* **the content is re-wrapped when the pane grows** -- the wider pane
  holds fewer lines, and the text reaches the wider area;
* **the scroll follows the content** -- the operator who was at the end
  of the document is at the end of it again, and not on its last line.

Run with:
    pytest tests/test_tui_document_pane_width.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.cells import cell_len
from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.tui.layout_manager import (  # noqa: E402
    apply_pane_visibility,
    build_torvalds_layout,
    document_pane_width,
    sidebar_is_visible,
)
from components.tui.markdown_view import PANEL_OVERHEAD, MarkdownView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The widths of the terminal that are measured.
WIDTHS = (80, 100, 120, 140, 160, 200)

#: The panes of the sidebar, and the state the operator puts them in when
#: the document pane is alone in the body.
NO_SIDEBAR = ("progress_pane", "telemetry_pane")

#: A paragraph long enough to fill a line at every width that is
#: measured, and to take several lines.
TEXT = (
    "The document pane carries the answer of the agent, and the answer is "
    "wrapped to the width of the pane that carries it: a line that reaches "
    "the end of the pane moves to the next line, and the text of the answer "
    "is read in as many lines as it needs."
)

#: The same paragraph, again and again: a document that is taller than the
#: pane, so that it can be scrolled.
LONG_TEXT = "\n\n".join([TEXT] * 40)


def a_console(width: int) -> Console:
    """A console of the size of a terminal.

    Args:
        width: The width of the terminal.

    Returns:
        The console.
    """
    return Console(width=width, height=40, color_system=None)


def an_app(console: Console):
    """A TUI application that is not running.

    Args:
        console: The console the panes are drawn on.

    Returns:
        The application.
    """
    from components.tui.tui_app import TuiApp

    app = TuiApp(
        agent=MagicMock(),
        prompt_handler_fn=MagicMock(),
        state=TuiState(),
        console=console,
    )
    app.state.set_markdown_content(TEXT)
    return app


def an_app_with_a_long_document(console: Console):
    """A TUI application whose document is taller than the pane.

    Args:
        console: The console the panes are drawn on.

    Returns:
        The application.
    """
    app = an_app(console)
    app.state.set_markdown_content(LONG_TEXT)
    return app


def the_document(console_width: int, hidden=()) -> tuple[int, int, int]:
    """The document pane as the operator sees it.

    The pane is measured in the **drawn** layout: the region of the pane
    in the map of the last frame.  The content is the panel the
    application put in that pane.

    Args:
        console_width: The width of the terminal.
        hidden: The panes the operator has hidden.

    Returns:
        The width of the pane, the width of the widest line of the
        content, and the number of lines the content has.
    """
    console = a_console(console_width)
    app = an_app(console)
    for pane in hidden:
        app.state.toggle_pane(pane)

    app._update_layout_panes()
    console.render_lines(
        app.layout, console.options.update_dimensions(console_width, 40)
    )

    region = app.layout.map[app.layout["markdown_pane"]].region
    panel = app.layout["markdown_pane"].renderable
    lines = panel.renderable.split("\n")
    widest = max(cell_len(line.plain) for line in lines)
    return region.width, widest, len(lines)


class TestTheWidthOfTheDocumentPane:
    """The pane knows how wide it is."""

    def test_the_width_is_the_one_the_layout_uses(self):
        """The number the pane wraps to is the number the layout gives it."""
        for console_width in WIDTHS:
            layout = build_torvalds_layout()
            console = a_console(console_width)
            console.render_lines(
                layout, console.options.update_dimensions(console_width, 40)
            )

            region = layout.map[layout["markdown_pane"]].region

            assert document_pane_width(console_width) == region.width, (
                f"the pane is {region.width} cells wide at {console_width} "
                f"columns, and the width that is computed is "
                f"{document_pane_width(console_width)}"
            )

    def test_the_width_is_the_one_the_layout_uses_without_the_sidebar(self):
        """The same number, when the sidebar has left the layout."""
        for console_width in WIDTHS:
            layout = build_torvalds_layout()
            console = a_console(console_width)
            apply_pane_visibility(layout, set(NO_SIDEBAR))
            console.render_lines(
                layout, console.options.update_dimensions(console_width, 40)
            )

            region = layout.map[layout["markdown_pane"]].region

            assert document_pane_width(console_width, False) == region.width, (
                f"the pane is {region.width} cells wide at {console_width} "
                f"columns without the sidebar, and the width that is "
                f"computed is {document_pane_width(console_width, False)}"
            )

    def test_the_document_pane_takes_the_whole_body_without_the_sidebar(self):
        """The space of the sidebar goes to the document pane."""
        assert document_pane_width(120, False) == 120

    def test_the_sidebar_is_on_the_screen_while_it_has_a_pane(self):
        """The rule of the sidebar lives in one place."""
        assert sidebar_is_visible(set())
        assert sidebar_is_visible({"progress_pane"})
        assert sidebar_is_visible({"telemetry_pane"})
        assert not sidebar_is_visible(set(NO_SIDEBAR))


class TestTheContentOfTheDocumentPane:
    """The content is wrapped to the width of the pane."""

    def test_the_content_reaches_the_width_of_the_pane(self):
        """The text fills the pane it is shown in."""
        for console_width in WIDTHS:
            pane, widest, _ = the_document(console_width)
            content = pane - PANEL_OVERHEAD

            assert widest == content, (
                f"the content is {widest} cells wide at {console_width} "
                f"columns, and the pane has {content} cells of content"
            )

    def test_no_line_of_the_content_is_wider_than_the_pane(self):
        """A line that is wider than the area is folded by Rich, and the
        pane loses a line of its content."""
        for console_width in WIDTHS:
            pane, widest, _ = the_document(console_width)
            content = pane - PANEL_OVERHEAD

            assert widest <= content, (
                f"a line of the content is {widest} cells wide at "
                f"{console_width} columns, and the pane has {content} cells"
            )

    def test_the_content_is_re_wrapped_when_the_pane_grows(self):
        """The pane takes the whole of the body, and the text follows it."""
        narrow_pane, narrow_widest, _ = the_document(120)
        wide_pane, wide_widest, _ = the_document(120, NO_SIDEBAR)

        assert wide_pane > narrow_pane, "the pane did not grow"
        assert wide_widest > narrow_widest, (
            "the content was not re-wrapped: it is "
            f"{wide_widest} cells wide in a pane of {wide_pane} cells"
        )

    def test_the_wider_pane_holds_fewer_lines(self):
        """The same text, in a wider pane, takes fewer lines."""
        _, _, narrow_lines = the_document(120)
        _, _, wide_lines = the_document(120, NO_SIDEBAR)

        assert wide_lines < narrow_lines, (
            f"the content takes {wide_lines} lines in the wide pane and "
            f"{narrow_lines} lines in the narrow one"
        )

    def test_the_view_wraps_to_the_width_it_is_given(self):
        """The pane is told how wide it is, and it takes the number."""
        state = TuiState()
        state.set_markdown_content(TEXT)
        view = MarkdownView(a_console(120))

        panel = view.render(state, max_height=20, width=60)
        widest = max(
            cell_len(line.plain) for line in panel.renderable.split("\n")
        )

        assert widest <= 60 - PANEL_OVERHEAD, (
            f"the content is {widest} cells wide, and the pane was given "
            f"60 cells"
        )


class TestTheScrollOfTheDocumentPane:
    """The scroll follows the content that was re-wrapped."""

    def test_the_scroll_is_at_the_end_of_the_document_again(self):
        """The operator was at the end of the document, and the document
        is shorter now: the operator is at its end, and not on its last
        line alone."""
        app = an_app_with_a_long_document(a_console(120))
        app._update_layout_panes()

        app.state.scroll_offset = app.state.max_scroll()
        before = app.state.total_rendered_lines
        assert app.state.scroll_offset > 0, "the document has one screen of text"

        for pane in NO_SIDEBAR:
            app.state.toggle_pane(pane)
        app._update_layout_panes()

        assert app.state.total_rendered_lines < before, (
            "the content was not re-wrapped: it still takes "
            f"{before} lines in the wider pane"
        )
        assert app.state.scroll_offset == app.state.max_scroll(), (
            f"the scroll is at {app.state.scroll_offset}, and the end of the "
            f"document is at {app.state.max_scroll()}"
        )

    def test_the_scroll_does_not_go_past_the_end(self):
        """The scroll of a document that is shorter than it was."""
        app = an_app_with_a_long_document(a_console(120))
        app._update_layout_panes()

        app.state.scroll_offset = app.state.max_scroll()
        for pane in NO_SIDEBAR:
            app.state.toggle_pane(pane)
        app._update_layout_panes()

        assert app.state.scroll_offset <= app.state.max_scroll()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
