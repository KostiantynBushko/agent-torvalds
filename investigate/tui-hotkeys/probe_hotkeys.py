#!/usr/bin/env python3
"""
The probe of the hot-keys of the Torvalds TUI.

It drives the **real** application -- the real state, the real layout,
the real panels -- with the keys the operator presses, and it draws
what the operator would see.

What it shows:

  * the keys of the reader, and the names they carry;
  * the pane that has the focus, and the marks that show it;
  * the scroll of the progress pane, and the position of the window;
  * the pane that is hidden, and the space its sibling takes;
  * the ``\\keys`` screen, and the lines to copy into the file of the
    configuration;
  * a chord that the operating system takes, and the refusal.

Run with:
    python investigate/tui-hotkeys/probe_hotkeys.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

from components.config import Config  # noqa: E402
from components.tui import hotkeys  # noqa: E402
from components.tui.input_reader import NonBlockingInputReader  # noqa: E402
from components.tui.layout_manager import build_torvalds_layout  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.tui_app import TuiApp  # noqa: E402

WIDTH = 120
HEIGHT = 34


def a_console() -> Console:
    """A console of the size of a terminal."""
    return Console(width=WIDTH, height=HEIGHT, color_system=None, force_terminal=False)


def a_state_with_tasks(count: int = 8) -> TuiState:
    """A state that carries the tasks of a run."""
    state = TuiState()
    state.model_name = "qwen3.6-27b"
    state.memory_msg_count = 12
    state.workflow_iteration = 3
    state.max_iterations = 8
    state.context_measured = True
    state.context_tokens = 8240
    state.context_messages = 12
    state.context_bytes = 40000
    state.context_window = 54000
    for index in range(count):
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


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------

def probe_the_reader() -> None:
    section("The reader names the keys")

    reader = NonBlockingInputReader()

    cases = [
        ("Ctrl+T", "\x14", "CTRL_T"),
        ("Ctrl+P", "\x10", "CTRL_P"),
        ("Ctrl+H", "\x08", "BACKSPACE"),
        ("Ctrl+I", "\x09", "TAB"),
        ("Ctrl+J", "\x0a", "ENTER"),
        ("Ctrl+M", "\x0d", "ENTER"),
        ("Ctrl+S", "\x13", "CTRL_S"),
        ("Ctrl+Z", "\x1a", "CTRL_Z"),
        ("Ctrl+Up", "\x1b[1;5A", "CTRL_UP"),
        ("Shift+Tab", "\x1b[Z", "SHIFT_TAB"),
        ("F5", "\x1b[15~", "F5"),
        ("Alt+a", "\x1ba", "ALT_a"),
    ]

    print(f"  {'the key':<12} {'the bytes':<18} {'the reader says':<16}")
    print("  " + "-" * 46)
    for label, sequence, expected in cases:
        name = _the_name_of(reader, sequence)
        mark = "ok" if name == expected else "DIFFERENT"
        print(f"  {label:<12} {sequence!r:<18} {str(name):<16} {mark}")


def _the_name_of(reader, sequence: str):
    """The name the reader gives a sequence of bytes.

    The name is asked of the reader the way the reader reads it: the
    single characters through ``_key_of``, and the control sequences
    through the buffer of the reader.
    """
    if len(sequence) == 1:
        return reader._key_of(sequence)

    reader._pending = sequence
    name = reader._poll_buffered()
    reader._pending = ""
    return name


# ---------------------------------------------------------------------------
# The keys of the TUI
# ---------------------------------------------------------------------------

def probe_the_keys() -> None:
    section("The keys of the TUI")

    resolved = hotkeys.resolve(Config(environ={}))

    print(f"  {'the key':<14} {'the action':<22} {'the scope':<10} {'the setting'}")
    print("  " + "-" * 72)
    for binding in resolved.hot_keys:
        print(
            f"  {binding.label:<14} {binding.action:<22} "
            f"{binding.scope:<10} {binding.setting}"
        )

    print()
    print("  The chords the operating system takes, and the reason of each:")
    for name, reason in hotkeys.SYSTEM_KEYS.items():
        print(f"    {name:<20} {reason}")
    print("    ALT_...              the Alt chords belong to the desktop")


# ---------------------------------------------------------------------------
# The focus and the scroll
# ---------------------------------------------------------------------------

def probe_the_focus_and_the_scroll() -> None:
    section("The focus, the scroll and the hidden pane")

    state = a_state_with_tasks()
    app = an_app(state)
    console = a_console()

    draw(app, console, "the panes, with the focus on the command bar")

    app._handle_key("TAB")
    print(f"  the focus is now: {state.focus}")
    draw(app, console, "the focus is on the document pane")

    app._handle_key("TAB")
    print(f"  the focus is now: {state.focus}")
    draw(app, console, "the focus is on the progress pane -- the border is brighter")

    app._handle_key("PGUP")
    app._handle_key("PGUP")
    scroll = state.scroll_of(hotkeys.FOCUS_PROGRESS)
    print(
        f"  the window of the log: offset {scroll.offset} of {scroll.total_lines} "
        f"-- {scroll.subtitle()}"
    )
    draw(app, console, "the progress pane scrolled back into the history")

    app._handle_key("ESCAPE")
    app._handle_key("CTRL_T")
    print(f"  the hidden panes: {sorted(state.hidden_panes)}")
    draw(app, console, "the telemetry pane is hidden -- the progress pane took the space")


# ---------------------------------------------------------------------------
# The file of the configuration
# ---------------------------------------------------------------------------

def probe_the_configuration() -> None:
    section("The file of the configuration")

    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "config.toml"
        path.write_text(
            '[hotkeys]\n'
            'toggle_telemetry = "Ctrl+Y"\n'
            'toggle_progress = "Ctrl+S"\n'
            'focus_previous = ""\n'
            'focus_next = "Ctrl+"\n',
            encoding="utf-8",
        )
        config = Config(path=path, environ={})
        resolved = hotkeys.resolve(config)

        print("  The file says:")
        for line in path.read_text(encoding="utf-8").splitlines():
            print(f"    {line}")

        print()
        print("  The bindings that stand:")
        for binding in resolved.hot_keys:
            print(f"    {binding.label:<14} {binding.action}")

        print()
        print("  What was refused, and why:")
        for problem in resolved.problems:
            print(f"    {problem}")


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------

def probe_the_screen() -> None:
    section("The \\keys screen")

    state = a_state_with_tasks()
    app = an_app(state)

    app.state.input_buffer = "\\keys"
    app._handle_enter_pressed()

    print(app.state.markdown_content)


def main() -> None:
    probe_the_reader()
    probe_the_keys()
    probe_the_focus_and_the_scroll()
    probe_the_configuration()
    probe_the_screen()


if __name__ == "__main__":
    main()
