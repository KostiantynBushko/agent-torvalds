"""
Every tool call shows its arguments in the progress pane.

The *Workflow & Tool Progress* pane shows the tool that runs and, under
its name, the line that says what it works on.  That line carried the
arguments of **one** tool -- the shell command -- and the call of every
other tool was a name with nothing under it.

The operator asked on 2026-11-23:

    currently only execute shell command shows a list of arguments in
    Workflow & Tool Progress window, I think the same must be applied
    to all tools call

What is asked of the pane:

  1. **Does every tool show its arguments?**  Every call of every tool
     shows what it was called with -- the command of the shell, the
     path of the file, the text that is written in it.

  2. **Is the command of the shell still whole?**  The command is shown
     the way it has been shown since it was shown whole: the value
     alone, and every character of it on the screen.

  3. **Is the home of the operator off the screen?**  The home is
     hidden in every argument of every tool, and not only in the
     command of the shell.

  4. **Is a long value folded honestly?**  A body of a file is not a
     line of the pane.  The pane shows the head of the value and says
     how many lines were left out.

  5. **Is every line of the pane the width of the pane?**  The detail
     is split to the width the layout really gives the pane.

Usage:
    python investigate/tui-tool-arguments/probe_tool_arguments.py

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

from components.tui.layout_manager import progress_pane_width  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The widths of the terminal the probe shows the pane at.
WIDTHS = (80, 120, 160)

#: The command of the operator: the one that has to stay whole.
COMMAND = (
    "cd ~/projects/agent-torvalds && git status --short && "
    "python -m pytest tests/ -x"
)

#: The calls of the tools, and the arguments every one of them is
#: called with.  Every one of them has to show its arguments.
THE_CALLS = (
    ("execute_shell_command", {"command": "ls -la"}),
    ("read_file", {"path": "/tmp/notes.md"}),
    ("write_file", {"path": "/tmp/notes.md", "content": "hello"}),
    ("mkdir", {"path": "/tmp/folder"}),
    ("cp", {"src": "/tmp/a.md", "dst": "/tmp/b.md"}),
    ("rm", {"path": "/tmp/old.md"}),
)

#: A body of a file: a value that is longer than the pane.
A_BODY = "\n".join(f"line {number}" for number in range(50))


def a_state_with(tool_name: str, arguments: dict) -> TuiState:
    """A state that carries a tool that was called."""
    state = TuiState()
    state.update_tool_start(tool_name, arguments)
    return state


def the_pane(state: TuiState, pane_width: int) -> str:
    """The pane, as plain text, the way the terminal renders it."""
    console = Console(width=pane_width, color_system=None)
    panel = ProgressView().render(state, width=pane_width)
    lines = console.render_lines(panel, console.options.update(width=pane_width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


def show_the_pane() -> None:
    """Show the pane at the widths of the terminals the operator uses."""
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        print(f"--- a terminal of {console_width} columns "
              f"(the pane is {pane_width} cells wide) ---")
        for tool_name, arguments in THE_CALLS:
            print(the_pane(a_state_with(tool_name, arguments), pane_width))
            print()
        print()


def check_every_tool_shows_its_arguments() -> bool:
    """Every call of every tool shows what it was called with."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        for tool_name, arguments in THE_CALLS:
            text = the_pane(a_state_with(tool_name, arguments), pane_width)
            for value in arguments.values():
                if str(value) not in text:
                    print(f"  FAIL  the pane does not show {value!r} of "
                          f"{tool_name} at {console_width} columns: {text!r}")
                    ok = False
    return ok


def check_the_command_is_still_whole() -> bool:
    """The command of the shell is shown the way it has been shown."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(
            a_state_with("execute_shell_command", {"command": COMMAND}),
            pane_width,
        )
        for word in ("cd", "git", "status", "--short", "python", "pytest", "-x"):
            if word not in text:
                print(f"  FAIL  the pane does not show {word!r} of the "
                      f"command at {console_width} columns: {text!r}")
                ok = False
    return ok


def check_the_home_is_off_the_screen() -> bool:
    """The home of the operator is hidden in every argument."""
    home = str(Path.home())
    if not home or home in ("/", "/root", "/nonexistent"):
        print("  the home of this machine cannot be found: the check is skipped")
        return True

    ok = True
    for tool_name, arguments in (
        ("read_file", {"path": f"{home}/notes.md"}),
        ("write_file", {"path": f"{home}/notes.md", "content": "hello"}),
        ("execute_shell_command", {"command": f"cat {home}/notes.md"}),
    ):
        text = the_pane(a_state_with(tool_name, arguments), 60)
        if home in text:
            print(f"  FAIL  the pane shows the home of the operator for "
                  f"{tool_name}: {text!r}")
            ok = False
    return ok


def check_a_long_value_is_folded() -> bool:
    """A body of a file is folded, and the marker says how much."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        text = the_pane(
            a_state_with(
                "write_file", {"path": "/tmp/a.md", "content": A_BODY}
            ),
            pane_width,
        )
        if "more lines" not in text:
            print(f"  FAIL  the value was not folded at {console_width} "
                  f"columns: {text!r}")
            ok = False
        if "line 0" not in text:
            print(f"  FAIL  the head of the value is gone at {console_width} "
                  f"columns: {text!r}")
            ok = False
    return ok


def check_every_line_fits_the_pane() -> bool:
    """No line of the pane is wider than the pane."""
    ok = True
    for console_width in WIDTHS:
        pane_width = progress_pane_width(console_width)
        calls = THE_CALLS + (
            ("write_file", {"path": "/tmp/a.md", "content": A_BODY}),
        )
        for tool_name, arguments in calls:
            text = the_pane(a_state_with(tool_name, arguments), pane_width)
            for line in text.split("\n"):
                if len(line) > pane_width:
                    print(f"  FAIL  the line is {len(line)} cells wide and "
                          f"the pane is {pane_width} cells wide: {line!r}")
                    ok = False
    return ok


def main() -> int:
    """Run every check and report what holds."""
    show_the_pane()

    checks = (
        ("every tool shows its arguments",
         check_every_tool_shows_its_arguments),
        ("the command of the shell is still whole",
         check_the_command_is_still_whole),
        ("the home of the operator is off the screen",
         check_the_home_is_off_the_screen),
        ("a long value is folded honestly",
         check_a_long_value_is_folded),
        ("every line fits the pane",
         check_every_line_fits_the_pane),
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
