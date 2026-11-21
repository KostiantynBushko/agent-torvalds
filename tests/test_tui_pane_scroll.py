"""
Unit tests for the scroll of the panes of the Torvalds TUI.

The operator asked on 2026-11-21 for the *Workflow & Tool Progress*
pane to scroll, and for the *Agent Telemetry & State* pane to be
hidden and shown.  The scroll of a pane is the window that shows part
of a content that is longer than the pane.

What the tests hold together:

* **the window is clamped to the content** -- the scroll never walks
  past the end of the log;
* **the anchor keeps the operator where he is** -- a new task that
  arrives while the operator is reading an old one does not move his
  window;
* **the window follows the end of the log** -- the operator who has
  not scrolled keeps the newest task, and the running task is the last
  line on the screen;
* **the list is a log** -- the oldest task first, and the newest at the
  bottom;
* **the hidden pane leaves the layout**, and its sibling takes the
  space;
* **the pane that has the focus is marked** -- a brighter border and
  the marker in its title -- and the panes that are not selected are
  not.

Run with:
    pytest tests/test_tui_pane_scroll.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

from components.tui.hotkeys import FOCUS_MARKER  # noqa: E402
from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    pane_content_height,
)
from components.tui.markdown_view import MarkdownView  # noqa: E402
from components.tui.pane_scroll import PaneScroll  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.telemetry_view import TelemetryView  # noqa: E402


def a_log(count: int, height: int = 5) -> PaneScroll:
    """A scroll of a log of `count` lines, each with its own anchor."""
    scroll = PaneScroll()
    scroll.set_frame(
        [f"line {index}" for index in range(count)],
        [f"task-{index}" for index in range(count)],
        height=height,
    )
    return scroll


class TestTheWindow(unittest.TestCase):
    """The window of the scroll."""

    def test_the_window_is_the_content_that_fits(self):
        scroll = a_log(20, height=5)

        self.assertEqual(scroll.window(), [f"line {i}" for i in range(15, 20)])

    def test_the_window_is_stuck_to_the_end_of_the_log(self):
        """The running task is the last line on the screen."""
        scroll = a_log(20, height=5)

        self.assertTrue(scroll.at_bottom)
        self.assertEqual(scroll.offset, 15)

    def test_the_offset_is_clamped_to_the_content(self):
        scroll = a_log(20, height=5)

        scroll.scroll_up(100)

        self.assertEqual(scroll.offset, 0)
        self.assertEqual(scroll.window()[0], "line 0")

    def test_the_offset_is_clamped_at_the_end(self):
        scroll = a_log(20, height=5)

        scroll.scroll_down(100)

        self.assertEqual(scroll.offset, 15)

    def test_a_content_shorter_than_the_window_shows_all_of_it(self):
        scroll = a_log(3, height=10)

        self.assertEqual(scroll.window(), ["line 0", "line 1", "line 2"])

    def test_the_scroll_up_and_down_move_the_window(self):
        scroll = a_log(20, height=5)

        scroll.scroll_up(3)
        self.assertEqual(scroll.offset, 12)

        scroll.scroll_down(2)
        self.assertEqual(scroll.offset, 14)

    def test_the_home_and_the_end_of_the_log(self):
        scroll = a_log(20, height=5)

        scroll.scroll_home()
        self.assertEqual(scroll.offset, 0)

        scroll.scroll_end()
        self.assertEqual(scroll.offset, 15)

    def test_the_subtitle_says_where_the_operator_is(self):
        scroll = a_log(20, height=5)

        scroll.scroll_up(4)
        position = scroll.subtitle()

        self.assertIn("12/20", position)
        self.assertIn("more", position)

    def test_the_subtitle_of_a_window_at_the_end_says_where_it_is(self):
        """At the end of the log there is nothing below -- and the
        operator still has to know where he is."""
        scroll = a_log(20, height=5)

        self.assertEqual(scroll.subtitle(), "▲ 16/20")

    def test_the_subtitle_of_a_window_at_the_top_says_what_is_below(self):
        scroll = a_log(20, height=5)
        scroll.scroll_home()

        self.assertEqual(scroll.subtitle(), "▼ 15 more")


class TestTheAnchor(unittest.TestCase):
    """The anchor keeps the operator where he is."""

    def test_the_anchor_is_the_item_at_the_top_of_the_window(self):
        scroll = a_log(20, height=5)

        scroll.scroll_up(3)

        self.assertEqual(scroll.anchor, "task-12")

    def test_a_new_task_does_not_move_the_window_of_the_operator(self):
        """The operator is reading a task, and the task stays."""
        scroll = a_log(20, height=5)
        scroll.scroll_up(5)
        offset = scroll.offset

        # A new task arrives at the end of the log.
        scroll.set_frame(
            [f"line {index}" for index in range(21)],
            [f"task-{index}" for index in range(21)],
            height=5,
        )

        self.assertEqual(
            scroll.offset,
            offset,
            "the window moved while the operator was reading an old task",
        )
        self.assertEqual(scroll.anchor, "task-10")

    def test_the_window_follows_the_end_when_the_operator_did_not_scroll(self):
        """The operator who has not scrolled keeps the newest task."""
        scroll = a_log(20, height=5)

        scroll.set_frame(
            [f"line {index}" for index in range(21)],
            [f"task-{index}" for index in range(21)],
            height=5,
        )

        self.assertEqual(scroll.offset, 16)
        self.assertEqual(scroll.window()[-1], "line 20")

    def test_the_window_follows_the_end_again_when_the_operator_scrolls_back(self):
        scroll = a_log(20, height=5)
        scroll.scroll_up(5)

        scroll.scroll_end()

        self.assertTrue(scroll.at_bottom)
        self.assertTrue(scroll.stuck)


class TestTheProgressPane(unittest.TestCase):
    """The pane of the progress of the workflow."""

    def _state_with_tasks(self, count: int) -> TuiState:
        state = TuiState()
        for index in range(count):
            state.update_tool_start(
                "execute_shell_command", {"command": f"command-{index}"}
            )
            state.update_tool_end("execute_shell_command", "ok")
        return state

    def test_the_list_of_the_tasks_is_a_log(self):
        """The oldest task first, and the newest at the bottom."""
        state = self._state_with_tasks(3)
        view = ProgressView()

        lines, anchors = view.content_lines(state, 40)

        self.assertIn("command-0", "\n".join(lines))
        self.assertIn("command-2", "\n".join(lines))
        self.assertLess(
            lines.index(next(line for line in lines if "command-0" in line)),
            lines.index(next(line for line in lines if "command-2" in line)),
            "the newest task is above the oldest one -- the list is not a log",
        )

    def test_every_line_of_a_task_carries_the_anchor_of_the_task(self):
        state = self._state_with_tasks(2)
        view = ProgressView()

        lines, anchors = view.content_lines(state, 40)

        self.assertEqual(len(lines), len(anchors))
        task = state.tool_tasks[-1].id
        self.assertIn(task, anchors, "the task has no anchor")

    def test_the_pane_shows_the_content_that_fits(self):
        state = self._state_with_tasks(8)
        scroll = PaneScroll()
        scroll.height = 6

        panel = ProgressView().render(state, width=60, scroll=scroll)

        self.assertIsNotNone(panel)
        self.assertEqual(scroll.total_lines, len(scroll.lines))

    def test_the_subtitle_says_where_the_operator_is(self):
        state = self._state_with_tasks(8)
        scroll = PaneScroll()
        scroll.height = 4

        panel = ProgressView().render(state, width=60, scroll=scroll)
        scroll.scroll_up(2)
        panel = ProgressView().render(state, width=60, scroll=scroll)

        self.assertIn("▲", panel.subtitle)
        self.assertIn("/", panel.subtitle)


class TestTheFocus(unittest.TestCase):
    """The pane that has the focus is marked."""

    def _render(self, view, state, focused):
        console = Console(width=60, color_system=None)
        panel = view.render(state, width=60, focused=focused)
        lines = console.render_lines(panel, console.options.update(width=60))
        return "\n".join("".join(s.text for s in line) for line in lines)

    def test_the_focused_progress_pane_carries_the_marker(self):
        state = TuiState()

        self.assertIn(
            FOCUS_MARKER, self._render(ProgressView(), state, focused=True)
        )

    def test_the_progress_pane_that_is_not_focused_carries_no_marker(self):
        state = TuiState()

        self.assertNotIn(
            FOCUS_MARKER, self._render(ProgressView(), state, focused=False)
        )

    def test_the_focused_telemetry_pane_carries_the_marker(self):
        state = TuiState()

        self.assertIn(
            FOCUS_MARKER, self._render(TelemetryView(), state, focused=True)
        )

    def test_the_telemetry_pane_that_is_not_focused_carries_no_marker(self):
        state = TuiState()

        self.assertNotIn(
            FOCUS_MARKER, self._render(TelemetryView(), state, focused=False)
        )

    def test_the_border_of_the_focused_pane_is_brighter(self):
        from rich.panel import Panel

        state = TuiState()

        focused = ProgressView().render(state, width=60, focused=True)
        plain = ProgressView().render(state, width=60, focused=False)

        self.assertIsInstance(focused, Panel)
        self.assertNotEqual(focused.border_style, plain.border_style)
        self.assertIn("bright", str(focused.border_style))

    def _render_document(self, state, focused):
        """The document pane, drawn the way the operator sees it."""
        console = Console(width=60, color_system=None)
        view = MarkdownView(console)
        panel = view.render(state, max_height=20, focused=focused)
        lines = console.render_lines(panel, console.options.update(width=60))
        return "\n".join("".join(s.text for s in line) for line in lines)

    def test_the_focused_document_pane_carries_the_marker(self):
        state = TuiState()

        self.assertIn(
            FOCUS_MARKER, self._render_document(state, focused=True)
        )

    def test_the_document_pane_that_is_not_focused_carries_no_marker(self):
        state = TuiState()

        self.assertNotIn(
            FOCUS_MARKER, self._render_document(state, focused=False)
        )

    def test_the_border_of_the_focused_document_pane_is_brighter(self):
        state = TuiState()
        view = MarkdownView(Console(width=60))

        focused = view.render(state, max_height=20, focused=True)
        plain = view.render(state, max_height=20, focused=False)

        self.assertNotEqual(focused.border_style, plain.border_style)
        self.assertIn("bright", str(focused.border_style))

    def test_the_marker_of_the_document_pane_stays_in_front_of_the_icon(self):
        """The marker stands in front of the icon of the pane -- and the
        icon is the first thing that is seen."""
        state = TuiState()

        drawn = self._render_document(state, focused=True)
        title = next(line for line in drawn.splitlines() if FOCUS_MARKER in line)

        self.assertLess(
            title.index(FOCUS_MARKER),
            title.index("\U0001f4c4"),
            "the marker is behind the icon of the pane",
        )


class TestTheHiddenPane(unittest.TestCase):
    """A hidden pane leaves the layout, and its sibling takes the space."""

    def _regions(self, console_width: int = 120, height: int = 40):
        layout = build_torvalds_layout()
        console = Console(width=console_width, height=height, color_system=None)
        console.render_lines(
            layout, console.options.update_dimensions(console_width, height)
        )
        return layout, console

    def test_the_hidden_pane_leaves_the_map(self):
        layout, console = self._regions()

        layout["telemetry_pane"].visible = False
        console.render_lines(
            layout, console.options.update_dimensions(120, 40)
        )

        with self.assertRaises(KeyError):
            layout.map[layout["telemetry_pane"]]

    def test_the_sibling_takes_the_space(self):
        layout, console = self._regions()

        before = layout.map[layout["progress_pane"]].region
        layout["telemetry_pane"].visible = False
        console.render_lines(
            layout, console.options.update_dimensions(120, 40)
        )
        after = layout.map[layout["progress_pane"]].region

        self.assertEqual(before.width, after.width)
        self.assertEqual(after.height, before.height * 2)

    def test_the_content_height_is_the_one_the_layout_uses(self):
        layout, console = self._regions()

        height = pane_content_height(layout, "progress_pane")
        region = layout.map[layout["progress_pane"]].region

        self.assertEqual(height, region.height - 2)

    def test_the_content_height_of_a_pane_that_is_not_there(self):
        layout, _ = self._regions()

        self.assertEqual(pane_content_height(layout, "no_such_pane"), 0)
        self.assertEqual(pane_content_height(layout, "no_such_pane", 12), 12)


if __name__ == "__main__":
    unittest.main()
