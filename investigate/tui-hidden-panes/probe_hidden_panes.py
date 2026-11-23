#!/usr/bin/env python3
"""
The probe of the panes that hide.

It drives the **real** application -- the real state, the real layout,
the real panels -- with the keys the operator presses, and it draws
what the operator would see.

What it shows:

  * the sidebar with its two panes;
  * the sidebar with one pane: the space of the hidden pane goes to
    the pane that is left;
  * the sidebar with **no** pane: the sidebar leaves the layout, and
    the document pane takes the whole of the body;
  * the defect that was there before: a sidebar whose panes are all
    hidden and that is not hidden itself is drawn as *itself*, and the
    drawing never ends.

Run with:
    python investigate/tui-hidden-panes/probe_hidden_panes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

from components.tui.layout_manager import (  # noqa: E402
    apply_pane_visibility,
    build_torvalds_layout,
)
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.tui_app import TuiApp  # noqa: E402

WIDTH = 120
HEIGHT = 34


def a_console() -> Console:
    """A console of the size of a terminal."""
    return Console(width=WIDTH, height=HEIGHT, color_system=None, force_terminal=False)


def a_state() -> TuiState:
    """A state that carries the tasks of a run."""
    state = TuiState()
    state.model_name = "qwen3.6-27b"
    state.memory_msg_count = 12
    state.workflow_iteration = 3
    state.max_iterations = 8
    for index in range(4):
        state.update_tool_start(
            "execute_shell_command",
            {"command": f"python -m pytest tests/ -x --tb=short  # task {index}"},
        )
        state.update_tool_end("execute_shell_command", "ok")
    return state


def an_app(state: TuiState) -> TuiApp:
    """The real application, with the real panels."""
    return TuiApp(
        agent=None,
        prompt_handler_fn=None,
        state=state,
        console=a_console(),
    )


def draw(app: TuiApp, console: Console, title: str) -> None:
    """Draw the layout of the application, the way the terminal draws it."""
    app._update_layout_panes()
    console.rule(f"[bold]{title}[/bold]")
    console.print(app.layout)


def section(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def regions(app: TuiApp) -> None:
    """Print the region every pane has on the screen."""
    print()
    print(f"  {'the pane':<18} {'the region':<18} the state")
    print("  " + "-" * 52)
    for name in (
        "markdown_pane",
        "sidebar",
        "progress_pane",
        "telemetry_pane",
    ):
        pane = app.layout[name]
        drawn = app.layout.map.get(pane)
        if drawn is None:
            if pane._children:
                # A partition has no region of its own: it is the
                # region of its panes.
                size = "-- a partition --"
            else:
                size = "-- not on the screen --"
        else:
            size = f"{drawn.region.width} x {drawn.region.height}"
        state = "shown" if pane.visible else "hidden"
        print(f"  {name:<18} {size:<18} {state}")


def probe_the_panes() -> None:
    """The panes of the sidebar, and the space they take."""
    section("The panes of the sidebar")

    state = a_state()
    app = an_app(state)
    console = a_console()

    draw(app, console, "the sidebar with its two panes")
    regions(app)

    app._handle_key("CTRL_T")
    print()
    print(f"  the hidden panes: {sorted(state.hidden_panes)}")
    draw(app, console, "the telemetry pane is hidden -- the progress pane took the space")
    regions(app)

    app._handle_key("CTRL_P")
    print()
    print(f"  the hidden panes: {sorted(state.hidden_panes)}")
    draw(
        app,
        console,
        "both panes are hidden -- the sidebar left, the document pane took the body",
    )
    regions(app)

    app._handle_key("CTRL_T")
    app._handle_key("CTRL_P")
    print()
    print(f"  the hidden panes: {sorted(state.hidden_panes)}")
    draw(app, console, "the panes are back, in the place they were")
    regions(app)


def probe_the_defect() -> None:
    """The defect that was there before the fix.

    A Rich partition whose children are **all** invisible is a
    partition without a content of its own, and Rich draws such a
    partition as *itself*.  The layout draws the sidebar, the sidebar
    draws the layout, and the drawing never ends.
    """
    section("The defect: a sidebar whose panes are all hidden")

    console = a_console()
    layout = build_torvalds_layout()
    for name in (
        "header",
        "markdown_pane",
        "progress_pane",
        "telemetry_pane",
        "footer",
    ):
        layout[name].update(f"[{name}]")

    # The way the panes were hidden before the fix: the flag of the
    # two panes, and nothing else.
    layout["progress_pane"].visible = False
    layout["telemetry_pane"].visible = False

    print("  the sidebar has two children, and none of them is visible:")
    print(f"    the visible children of the sidebar: {len(layout['sidebar'].children)}")
    print("    the renderable of the sidebar: itself -- Rich draws it as itself")

    try:
        console.print(layout)
    except RecursionError:
        print()
        print("  RecursionError: maximum recursion depth exceeded")
        print()
        print("  The sidebar was drawn as itself, and the drawing never ended.")
        print("  The fix: the sidebar leaves the layout with its last pane.")
        return

    print()
    print("  The layout was drawn -- the Rich of this machine does not recurse.")


def probe_the_fix() -> None:
    """The rule that keeps the layout from drawing a partition as
    itself."""
    section("The rule: a drawn partition keeps a visible child")

    layout = build_torvalds_layout()
    console = a_console()
    for name in (
        "header",
        "markdown_pane",
        "progress_pane",
        "telemetry_pane",
        "footer",
    ):
        layout[name].update(f"[{name}]")

    for hidden in (
        set(),
        {"telemetry_pane"},
        {"progress_pane"},
        {"progress_pane", "telemetry_pane"},
    ):
        apply_pane_visibility(layout, hidden)
        console.print(layout)

        drawn = []
        for partition in _partitions(layout):
            if not partition.visible or not partition._children:
                continue
            if not partition.children:
                drawn.append(partition.name)

        names = ", ".join(sorted(hidden)) or "-- nothing --"
        print(f"  the hidden panes: {names}")
        print(f"    the partitions drawn as themselves: {drawn or 'none'}")


def _partitions(layout):
    """Every partition of the layout, the root included."""
    stack = [layout]
    while stack:
        partition = stack.pop()
        yield partition
        stack.extend(partition._children)


def main() -> None:
    probe_the_panes()
    probe_the_defect()
    probe_the_fix()


if __name__ == "__main__":
    main()
