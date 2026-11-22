"""
The home of the operator on the screen of the progress pane.

The agent works with the real paths — the tools read the files the paths
name.  The **screen** is another thing: the *Workflow & Tool Progress*
pane shows the tool that runs and, under its name, the line that says
what it works on.  That line carried the home directory of the operator
in full, on every path the agent touched below the home.

The probe asks the real panel, with the real state, and reports what the
screen carries:

  1. **Is the home on the screen?**  A file under the home must be shown
     as ``~/...`` — the home itself must not appear.

  2. **Is the home on the screen inside a command?**  A shell command
     that works on a file under the home must not carry the home either.

  3. **Does the cut of the text leave half a home behind?**  The line is
     cut to the width of the pane.  A cut that lands inside the home
     leaves the first letters of the home on the screen — the home is
     hidden *before* the text is cut.

  4. **Is a folder that only starts like the home left alone?**  The home
     is a whole path component: a folder named ``userdata`` next to the
     home ``/home/user`` is another folder, and it is not the home of the
     operator.

  5. **Is the state still the truth?**  The agent must keep the real
     path: the pane hides it, the work does not.

  6. **Does it work on a Windows home?**  The pane is the same on every
     machine: a Windows home is hidden the same way, and the spelling of
     a Windows path is not case sensitive.

Usage:
    python investigate/tui-home-path-in-progress/probe_home_path.py

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

from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The home of the machine the probe runs on.  It is computed, never
#: written down — the probe names no home of its own.
HOME = str(Path.home())

#: The home of a Windows machine, for the check that does not need a
#: Windows machine to run.
WINDOWS_HOME = "C:\\Users\\user"

#: The width of the panel the probe renders at.
WIDTH = 60


def render(state: TuiState) -> str:
    """Render the progress panel and return it as plain text."""
    console = Console(width=WIDTH, color_system=None)
    panel = ProgressView().render(state)
    lines = console.render_lines(panel, console.options.update(width=WIDTH))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


def a_state_with_a_file_under_the_home() -> TuiState:
    """A state that carries a tool reading a file under the home."""
    state = TuiState()
    state.update_tool_start("read_file", {"file_path": f"{HOME}/notes/todo.md"})
    return state


def a_state_with_a_command_under_the_home(command: str = "") -> TuiState:
    """A state that carries a tool running a command under the home."""
    state = TuiState()
    state.update_tool_start(
        "execute_shell_command",
        {"command": command or f"cat {HOME}/notes/todo.md"},
    )
    return state


def a_state_with_a_long_command() -> TuiState:
    """A state that carries a command whose home is cut by the width."""
    state = TuiState()
    state.update_tool_start(
        "execute_shell_command",
        {"command": "python -m pytest --rootdir=" + HOME + "/project"},
    )
    return state


def main() -> int:
    """Ask the panel what it shows.  Return 1 when a check fails."""
    failures = []

    print("the panel, with a file under the home")
    text = render(a_state_with_a_file_under_the_home())
    for line in text.splitlines():
        if line.strip():
            print(f"   {line}")
    if HOME in text:
        failures.append(
            "the home of the operator is on the screen -- the pane shows the "
            "path of the file in full"
        )
    if "~/" not in text:
        failures.append("the file under the home is not shown as ~/...")
    print()

    print("the panel, with a command that works under the home")
    text = render(a_state_with_a_command_under_the_home())
    for line in text.splitlines():
        if line.strip():
            print(f"   {line}")
    if HOME in text:
        failures.append(
            "the home of the operator is on the screen inside the command"
        )
    if "~/" not in text:
        failures.append("the command does not carry ~/...")
    print()

    print("the panel, with a quoted path")
    text = render(a_state_with_a_command_under_the_home(f'cat "{HOME}/notes/todo.md"'))
    for line in text.splitlines():
        if line.strip():
            print(f"   {line}")
    if HOME in text:
        failures.append(
            "the home of the operator is on the screen inside a quoted path"
        )
    print()

    print("the panel, with a command the width cuts")
    text = render(a_state_with_a_long_command())
    for line in text.splitlines():
        if line.strip():
            print(f"   {line}")
    if HOME in text:
        failures.append(
            "the cut of the line left the home on the screen -- the home is "
            "hidden after the text is cut, not before it"
        )
    if HOME[:6] in text and HOME not in text:
        failures.append(
            "the cut of the line left half a home on the screen: "
            f"{HOME[:6]!r}"
        )
    print()

    print("a folder that only starts like the home")
    state = TuiState()
    state.update_tool_start(
        "read_file",
        {"file_path": HOME + "data/report.md"},
    )
    text = render(state)
    for line in text.splitlines():
        if line.strip():
            print(f"   {line}")
    if "~" in text:
        failures.append(
            "a folder that only starts like the home was hidden -- the home "
            "is a whole path component, and nothing else is"
        )
    print()

    print("the state keeps the truth")
    state = a_state_with_a_file_under_the_home()
    details = state.task_stack.tasks[0].details
    print(f"   the state carries: {details}")
    if HOME not in details:
        failures.append(
            "the state does not carry the real path -- the agent has to work "
            "with the path of the machine"
        )
    print()

    print("a Windows home")
    from components.tui.path_display import hide_home

    shown = hide_home(f"{WINDOWS_HOME}\\Documents\\todo.md", home=WINDOWS_HOME)
    print(f"   {WINDOWS_HOME}\\Documents\\todo.md  ->  {shown}")
    if shown != "~\\Documents\\todo.md":
        failures.append(f"a Windows home is not hidden the same way: {shown!r}")

    shown = hide_home(
        f"{WINDOWS_HOME.lower()}\\documents\\todo.md", home=WINDOWS_HOME
    )
    print(f"   a Windows path in another case      ->  {shown}")
    if shown != "~\\documents\\todo.md":
        failures.append(
            "a Windows path is not hidden when it is not written in the same "
            f"case: {shown!r}"
        )

    shown = hide_home(f"C:/Users/user/Documents/todo.md", home=WINDOWS_HOME)
    print(f"   a Windows path with slashes         ->  {shown}")
    if shown != "~/Documents/todo.md":
        failures.append(f"a Windows path with slashes is not hidden: {shown!r}")
    print()

    if failures:
        print("something does not hold:")
        for failure in failures:
            print(f"   - {failure}")
        return 1

    print(
        "everything holds: the home of the operator is not on the screen, "
        "the path under it is shown as ~/..., the state keeps the real path, "
        "and a Windows home is hidden the same way"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
