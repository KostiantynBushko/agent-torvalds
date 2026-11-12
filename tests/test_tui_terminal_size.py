"""
The console of the TUI must ask the terminal for its size.

Rich reads ``COLUMNS`` and ``LINES`` from the environment before it
asks the terminal, and the shell exports them as a snapshot of the
size the terminal had when the shell started.  A console that believes
them lays the multi-window layout out for a terminal that is not there:
the frame is wider than the screen, the terminal folds it, the panes
leave their columns, and the screen scrolls on every frame.

The investigation is in ``investigate/tui-selection-and-flicker/``.

Run with:
    pytest tests/test_tui_terminal_size.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.tui.terminal_size import (  # noqa: E402
    SIZE_VARIABLES,
    build_console,
    console_environ,
)


class TestConsoleEnviron:
    """The environment of the console."""

    def test_the_size_variables_are_gone(self):
        """COLUMNS and LINES do not reach the console."""
        environ = console_environ(
            {"COLUMNS": "229", "LINES": "33", "TERM": "xterm"}
        )
        for name in SIZE_VARIABLES:
            assert name not in environ

    def test_the_rest_of_the_environment_stays(self):
        """TERM, NO_COLOR and the rest keep working."""
        source = {"TERM": "xterm-256color", "NO_COLOR": "", "LANG": "C.UTF-8"}
        assert console_environ(source) == source

    def test_the_environment_of_the_process_is_not_changed(self):
        """The environment of the agent is not touched."""
        before = dict(os.environ)
        console_environ()
        assert dict(os.environ) == before


class TestBuildConsole:
    """The console itself."""

    def test_it_ignores_the_stale_size(self, monkeypatch):
        """A console built here does not believe COLUMNS and LINES."""
        monkeypatch.setenv("COLUMNS", "229")
        monkeypatch.setenv("LINES", "33")
        console = build_console()
        assert "COLUMNS" not in console._environ
        assert "LINES" not in console._environ

    def test_it_asks_the_terminal(self, monkeypatch):
        """The size of the terminal is the size Rich uses."""
        monkeypatch.setattr(
            os, "get_terminal_size", lambda *args: os.terminal_size((120, 40))
        )
        console = build_console()
        assert (console.width, console.height) == (120, 40)

    def test_a_forced_size_still_wins(self, monkeypatch):
        """An operator who asks for a size gets it."""
        monkeypatch.setattr(
            os, "get_terminal_size", lambda *args: os.terminal_size((120, 40))
        )
        console = build_console(width=90, height=30)
        assert (console.width, console.height) == (90, 30)

    def test_it_follows_a_resize(self, monkeypatch):
        """The size is asked on every access, so a resize is followed."""
        size = [os.terminal_size((120, 40))]

        monkeypatch.setattr(
            os, "get_terminal_size", lambda *args: size[0]
        )
        console = build_console()
        assert (console.width, console.height) == (120, 40)

        size[0] = os.terminal_size((100, 30))
        assert (console.width, console.height) == (100, 30)


def _render_layout(width: int, height: int):
    """The layout of the TUI, at the given size."""
    from rich.console import Console

    from components.tui.layout_manager import (
        build_torvalds_layout,
        render_footer,
        render_header,
    )
    from components.tui.markdown_view import MarkdownView
    from components.tui.progress_view import ProgressView
    from components.tui.state_bridge import TuiState
    from components.tui.telemetry_view import TelemetryView

    console = Console(width=width, height=height, color_system=None)
    state = TuiState()
    layout = build_torvalds_layout()
    layout["header"].update(render_header("", 0, True, state.session_start_time))
    layout["markdown_pane"].update(MarkdownView(console).render(state))
    layout["progress_pane"].update(ProgressView().render(state))
    layout["telemetry_pane"].update(TelemetryView().render(state))
    layout["footer"].update(render_footer("", 0))

    lines = console.render_lines(
        layout, console.options.update(height=height, width=width)
    )
    return ["".join(segment.text for segment in line) for line in lines]


class TestTheLayoutFits:
    """The layout of the TUI, at the size of the terminal."""

    @pytest.mark.parametrize("width,height", [(80, 24), (120, 40), (200, 50)])
    def test_the_layout_fills_the_terminal(self, width, height):
        """Every row of the layout fits the terminal, and there are as
        many rows as the terminal has."""
        rows = _render_layout(width, height)
        assert len(rows) == height
        for number, row in enumerate(rows):
            assert len(row) <= width, f"row {number} is too wide"

    def test_the_panes_keep_their_columns(self):
        """The separator between the panes is where the layout puts it.

        A selection is made by column: when the panes are not aligned,
        the selection of the document pane carries the content of the
        progress pane with it.
        """
        rows = _render_layout(120, 40)
        columns = {
            row.index("││") for row in rows if "││" in row
        }
        assert len(columns) == 1, f"the panes are not aligned: {columns}"
