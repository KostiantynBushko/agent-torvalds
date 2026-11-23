"""
The panes of the TUI hide, and the layout survives it.

The operator hides the panes of the sidebar with ``Ctrl+T`` and
``Ctrl+P`` -- one of them, or the other one, or **both of them**.

**Both of them were a crash.**  A Rich partition whose children are
*all* invisible is a partition without a content of its own, and Rich
draws such a partition as *itself*: the layout draws the sidebar, the
sidebar draws the layout, and the operator gets a stack of a thousand
frames instead of a screen::

    File "rich/console.py", line 1339, in render
        for render_output in iter_render:
    File "rich/layout.py", line 401, in __rich_console__
        render_map = self.render(console, options.update_dimensions(width, height))
    File "rich/console.py", line 240, in update_dimensions
        options = self.copy()
    RecursionError: maximum recursion depth exceeded

The sidebar therefore leaves the layout together with its last pane, and
the document pane takes the whole of the body.

What the tests hold together:

* **the layout is drawn with every pane of the sidebar hidden** -- the
  crash is the regression these tests were written for;
* **the sidebar leaves the layout with its last pane**, and the document
  pane takes the whole of the body;
* **the pane that is left takes the whole of the sidebar** -- the space
  of a hidden pane goes to its sibling;
* **no partition of the layout has children that are all hidden** -- the
  invariant that keeps Rich from drawing a partition as itself;
* **the panes come back** -- the same keys, and the layout is the one
  it was.

Run with:
    pytest tests/test_tui_hidden_panes.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.layout import Layout

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.tui.layout_manager import (  # noqa: E402
    apply_pane_visibility,
    build_torvalds_layout,
)
from components.tui.state_bridge import TuiState  # noqa: E402

#: The size of the terminal the layout is drawn on.
WIDTH = 120
HEIGHT = 40


def a_console() -> Console:
    """A console of the size of a terminal."""
    return Console(width=WIDTH, height=HEIGHT, color_system=None)


def a_layout() -> Layout:
    """The layout of the TUI, with a panel in every pane."""
    layout = build_torvalds_layout()
    for name in (
        "header",
        "markdown_pane",
        "progress_pane",
        "telemetry_pane",
        "footer",
    ):
        layout[name].update(f"[{name}]")
    return layout


def an_app(console: Console | None = None):
    """A TUI application that is not running."""
    from components.tui.tui_app import TuiApp

    return TuiApp(
        agent=MagicMock(),
        prompt_handler_fn=MagicMock(),
        state=TuiState(),
        console=console or a_console(),
    )


def partitions(layout: Layout):
    """Every partition of the layout, the root included.

    Args:
        layout: The layout to walk.

    Yields:
        Every partition of the layout, the root first.
    """
    stack = [layout]
    while stack:
        partition = stack.pop()
        yield partition
        stack.extend(partition._children)


def region_of(layout: Layout, name: str):
    """The region a pane has on the screen, or None when it has none.

    Args:
        layout: The layout that was drawn.
        name: The name of the pane.

    Returns:
        The region of the pane, and None when the pane is not on the
        screen.
    """
    drawn = layout.map.get(layout[name])
    return drawn.region if drawn is not None else None


class TestTheHiddenPanes:
    """The panes of the sidebar hide, and the layout is still drawn."""

    def test_the_layout_is_drawn_with_every_pane_of_the_sidebar_hidden(self):
        """The crash: the sidebar was drawn as itself, and it never
        ended."""
        console = a_console()
        layout = a_layout()

        apply_pane_visibility(layout, {"progress_pane", "telemetry_pane"})

        console.print(layout)

    def test_the_sidebar_leaves_the_layout_with_its_last_pane(self):
        """A partition without a visible child is drawn as itself, and
        that is an endless recursion."""
        console = a_console()
        layout = a_layout()

        apply_pane_visibility(layout, {"progress_pane", "telemetry_pane"})
        console.print(layout)

        assert not layout["sidebar"].visible, (
            "the sidebar stayed on the screen without a pane"
        )
        assert region_of(layout, "sidebar") is None, (
            "the sidebar was drawn without a pane"
        )

    def test_the_document_pane_takes_the_whole_body(self):
        """The space of the sidebar goes to the document pane."""
        console = a_console()
        layout = a_layout()

        apply_pane_visibility(layout, {"progress_pane", "telemetry_pane"})
        console.print(layout)

        region = region_of(layout, "markdown_pane")
        assert region is not None
        assert region.width == WIDTH, (
            f"the document pane is {region.width} cells wide, "
            f"and the body is {WIDTH} cells wide"
        )

    def test_the_pane_that_is_left_takes_the_whole_sidebar(self):
        """The space of a hidden pane goes to its sibling."""
        console = a_console()
        layout = a_layout()

        apply_pane_visibility(layout, {"telemetry_pane"})
        console.print(layout)

        progress = region_of(layout, "progress_pane")
        telemetry = region_of(layout, "telemetry_pane")
        assert telemetry is None, "the hidden pane was drawn"
        assert progress is not None
        assert progress.height > 0

    def test_no_drawn_partition_has_children_that_are_all_hidden(self):
        """The invariant that keeps Rich from drawing a partition as
        itself.

        A partition that is **hidden** is never drawn -- Rich walks the
        visible children only -- so it is of no matter what its own
        children do.  A partition that is **drawn** and has no visible
        child is drawn as *itself*, and that is the endless recursion.
        """
        console = a_console()
        layout = a_layout()

        for hidden in (
            set(),
            {"progress_pane"},
            {"telemetry_pane"},
            {"progress_pane", "telemetry_pane"},
        ):
            apply_pane_visibility(layout, hidden)
            console.print(layout)

            for partition in partitions(layout):
                if not partition.visible or not partition._children:
                    continue
                assert partition.children, (
                    f"the partition {partition.name!r} is drawn and has "
                    f"children and none of them is visible -- Rich draws "
                    f"such a partition as itself, and that is an endless "
                    f"recursion"
                )

    def test_the_panes_come_back(self):
        """The same keys bring the panes back, in the place they were."""
        console = a_console()
        layout = a_layout()

        apply_pane_visibility(layout, {"progress_pane", "telemetry_pane"})
        console.print(layout)
        apply_pane_visibility(layout, set())
        console.print(layout)

        assert layout["sidebar"].visible
        for name in ("progress_pane", "telemetry_pane"):
            assert region_of(layout, name) is not None, (
                f"the {name} did not come back"
            )


class TestTheApplication:
    """The application hides the panes, and it keeps drawing."""

    def test_the_application_survives_the_hiding_of_both_panes(self):
        """The path the operator walks: the two keys, and the frame."""
        console = a_console()
        app = an_app(console)

        app._hotkey_toggle_telemetry()
        app._hotkey_toggle_progress()
        app._update_layout_panes()

        console.print(app.layout)

    def test_the_application_survives_the_hiding_of_the_panes_in_any_order(self):
        """The order of the keys does not matter."""
        for first, second in (
            ("_hotkey_toggle_telemetry", "_hotkey_toggle_progress"),
            ("_hotkey_toggle_progress", "_hotkey_toggle_telemetry"),
        ):
            console = a_console()
            app = an_app(console)

            getattr(app, first)()
            getattr(app, second)()
            app._update_layout_panes()

            console.print(app.layout)

    def test_the_application_brings_the_panes_back(self):
        """The keys are a switch, and the switch works both ways."""
        console = a_console()
        app = an_app(console)

        app._hotkey_toggle_telemetry()
        app._hotkey_toggle_progress()
        app._update_layout_panes()
        console.print(app.layout)

        app._hotkey_toggle_telemetry()
        app._hotkey_toggle_progress()
        app._update_layout_panes()
        console.print(app.layout)

        assert app.layout["sidebar"].visible
        assert app.layout["progress_pane"].visible
        assert app.layout["telemetry_pane"].visible


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
