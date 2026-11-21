"""
The command of a tool is cut on the screen of the progress pane.

The *Workflow & Tool Progress* pane shows the tool that runs and, under
its name, the line that says what it works on.  That line carried the
**whole** command in the state, and the view cut it to forty
characters: the operator saw the head of a command and not the
command, and the head of a command says nothing about what the command
does.

Two things are asked of the pane:

  1. **Is the whole command on the screen?**  Every character of the
     command has to be there -- what is cut away is the part that says
     what the command does.

  2. **Is the command split when it does not fit?**  A command that is
     longer than the pane takes the lines it needs, and no line is
     wider than the pane.

Two more things are asked of the text that reaches the screen:

  3. **Is the command the command that ran?**  A command carries
     square brackets of its own.  Rich reads them as markup and drops
     the text between them, and the operator sees a command that is
     not the one that ran.

  4. **Is the width the width of the pane?**  The pane is a share of
     the width of the terminal, and the detail is split to the width
     the pane really has -- the width the layout gives it.

Usage:
    python investigate/tui-progress-full-command/probe_progress_detail.py

The exit code is 0 when every check holds, 1 when one does not.

The probe writes nothing and talks to no service.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402

from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    progress_pane_width,
)
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The command of the operator: the one that was cut, and that the pane
#: has to show whole.
COMMAND = (
    "cd ~/projects/agent-torvalds && git status --short && "
    "python -m pytest tests/ -x"
)

#: The command that carries square brackets of its own.
BRACKETS = "ls [abc] && echo done"

#: The widths of the terminal the probe shows the pane at.
WIDTHS = (80, 120, 160)


def a_state_with_a_command(command: str) -> TuiState:
    """A state that carries a tool running a command."""
    state = TuiState()
    state.update_tool_start("execute_shell_command", {"command": command})
    return state


def the_pane(state: TuiState, pane_width: int) -> str:
    """The pane, as plain text, the way the terminal renders it."""
    console = Console(width=pane_width, color_system=None)
    panel = ProgressView().render(state, width=pane_width)
    lines = console.render_lines(panel, console.options.update(width=pane_width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


def show_the_pane() -> None:
    """Show the pane at the widths of the terminals the operator uses."""
    state = a_state_with_a_command(COMMAND)
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        print(f"--- a terminal of {console_width} columns "
              f"(the pane is {pane_width} cells wide) ---")
        print(the_pane(state, pane_width))
        print()


def check_the_whole_command_is_on_the_screen() -> bool:
    """Every character of the command has to be on the screen."""
    state = a_state_with_a_command(COMMAND)
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(state, pane_width)
        for word in ("cd", "git", "status", "--short", "python", "pytest", "-x"):
            if word not in text:
                print(f"  FAIL  the pane does not show {word!r} "
                      f"at {console_width} columns")
                ok = False
    return ok


def check_the_command_is_split_to_the_width_of_the_pane() -> bool:
    """No line of the detail is wider than the pane."""
    state = a_state_with_a_command(COMMAND)
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        for line in the_pane(state, pane_width).split("\n"):
            if len(line) > pane_width:
                print(f"  FAIL  the line is {len(line)} cells wide and the "
                      f"pane is {pane_width} cells wide: {line!r}")
                ok = False
    return ok


def check_the_brackets_of_the_command_survive() -> bool:
    """The command on the screen is the command that ran."""
    state = a_state_with_a_command(BRACKETS)
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(state, pane_width)
        if "[abc]" not in text:
            print(f"  FAIL  the pane lost the brackets of the command "
                  f"at {console_width} columns: {text!r}")
            ok = False
    return ok


def check_the_width_is_the_width_of_the_layout() -> bool:
    """The number the pane splits to is the number the layout gives it."""
    ok = True
    for console_width in WIDTHS:
        layout = build_torvalds_layout()
        console = Console(width=console_width, color_system=None)
        console.render_lines(
            layout, console.options.update_dimensions(console_width, 40)
        )
        pane = layout["progress_pane"]
        region = layout.map[pane].region
        computed = progress_pane_width(console_width)
        if computed != region.width:
            print(f"  FAIL  the pane is {region.width} cells wide at "
                  f"{console_width} columns, and the width that is computed "
                  f"is {computed}")
            ok = False
    return ok


def main() -> int:
    """Run every check and report what holds."""
    show_the_pane()

    checks = (
        ("the whole command is on the screen",
         check_the_whole_command_is_on_the_screen),
        ("the command is split to the width of the pane",
         check_the_command_is_split_to_the_width_of_the_pane),
        ("the brackets of the command survive",
         check_the_brackets_of_the_command_survive),
        ("the width is the width of the layout",
         check_the_width_is_the_width_of_the_layout),
    )

    failed = 0
    print("=" * 70)
    for name, check in checks:
        result = check()
        print(f"  {'PASS' if result else 'FAIL'}  {name}")
        if not result:
            failed += 1
    print("=" * 70)

    if failed:
        print(f"{failed} check(s) do not hold.")
        return 1
    print("Every check holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
