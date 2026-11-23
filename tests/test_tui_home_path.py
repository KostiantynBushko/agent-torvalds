"""
The home of the operator is not on the screen of the progress pane.

The *Workflow & Tool Progress* pane shows the tool that runs and, under
its name, the line that says what it works on.  That line carried the
home directory of the operator in full — on every path the agent touched
below the home.

The agent works with the real paths, and it keeps them: the state of the
TUI carries the path of the machine, and the tools read the files it
names.  The **screen** is where the home is hidden.

The check is in two parts:

  * the pane — the real panel, with the real state, rendered the way the
    terminal renders it;
  * the helper — the rule that hides the home, asked about the homes of
    every system, so that the check does not need a Windows machine to
    run to prove that a Windows home is hidden as well.

The investigation is in ``investigate/tui-home-path-in-progress/``.

Run with:
    pytest tests/test_tui_home_path.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from components.tui.path_display import hide_home, the_home  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The home the check hides.  It is a home of the generic kind — the
#: home of nobody — and the check is told which home to hide, so that
#: it does not depend on the machine it runs on.
HOME = "/home/user"

#: The home of a Windows machine, for the same reason.
WINDOWS_HOME = "C:\\Users\\user"

#: The width the panel is rendered at.
WIDTH = 60


def render(state: TuiState) -> str:
    """Render the progress panel and return it as plain text."""
    from rich.console import Console

    console = Console(width=WIDTH, color_system=None)
    panel = ProgressView().render(state)
    lines = console.render_lines(panel, console.options.update(width=WIDTH))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


def a_state_with_a_file(path: str) -> TuiState:
    """A state that carries a tool reading a file."""
    state = TuiState()
    state.update_tool_start("read_file", {"file_path": path})
    return state


def a_state_with_a_command(command: str) -> TuiState:
    """A state that carries a tool running a command."""
    state = TuiState()
    state.update_tool_start("execute_shell_command", {"command": command})
    return state


# ---------------------------------------------------------------------------
# The pane
# ---------------------------------------------------------------------------


class TestThePane:
    """The pane shows the path without the home of the operator."""

    def test_the_home_of_the_machine_is_not_on_the_screen(self):
        """The home of the machine the pane runs on stays off the screen."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            return  # the home of this machine cannot be found

        text = render(a_state_with_a_file(f"{home}/notes/todo.md"))

        assert home not in text, f"the pane shows the home of the operator: {text!r}"
        assert "~/notes/todo.md" in text, f"the pane does not show ~/...: {text!r}"

    def test_the_command_under_the_home_is_shown_as_a_tilde(self):
        """A command that works under the home does not carry the home."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            return

        text = render(a_state_with_a_command(f"cat {home}/notes/todo.md"))

        assert home not in text, f"the pane shows the home of the operator: {text!r}"
        assert "~/notes/todo.md" in text, f"the pane does not show ~/...: {text!r}"

    def test_the_cut_of_the_line_leaves_no_half_a_home(self):
        """The home is hidden before the line is cut, not after it."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            return

        state = a_state_with_a_command(
            "python -m pytest --rootdir=" + home + "/project"
        )
        text = render(state)

        assert home not in text, f"the pane shows the home of the operator: {text!r}"
        assert home[:6] not in text, (
            f"the cut of the line left half a home on the screen: {text!r}"
        )

    def test_a_folder_that_only_starts_like_the_home_is_left_alone(self):
        """The home is a whole path component, and nothing else is."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            return

        text = render(a_state_with_a_file(home + "data/report.md"))

        assert "~" not in text, (
            f"a folder that only starts like the home was hidden: {text!r}"
        )

    def test_the_state_keeps_the_real_path(self):
        """The agent works with the path of the machine, and keeps it."""
        state = a_state_with_a_file(f"{HOME}/notes/todo.md")

        assert state.task_stack.tasks[0].details == f"{HOME}/notes/todo.md"


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


class TestTheHomeIsHidden:
    """The rule that hides the home, asked about every system."""

    def test_a_path_under_the_home_becomes_a_tilde(self):
        assert hide_home(f"{HOME}/notes/todo.md", home=HOME) == "~/notes/todo.md"

    def test_the_home_itself_becomes_a_tilde(self):
        assert hide_home(HOME, home=HOME) == "~"

    def test_every_occurrence_of_the_home_is_hidden(self):
        text = f"cp {HOME}/a.md {HOME}/b.md"

        assert hide_home(text, home=HOME) == "cp ~/a.md ~/b.md"

    def test_the_home_inside_a_command_is_hidden(self):
        text = f"cat {HOME}/notes/todo.md | wc -l"

        assert hide_home(text, home=HOME) == "cat ~/notes/todo.md | wc -l"

    def test_a_quoted_path_is_hidden(self):
        """A quote ends the name of the home, and the home is hidden."""
        text = f'cat "{HOME}/notes/todo.md"'

        assert hide_home(text, home=HOME) == 'cat "~/notes/todo.md"'

    def test_a_path_with_a_space_behind_it_is_hidden(self):
        """A space ends the name of the home, and the home is hidden."""
        text = f"ls {HOME} "

        assert hide_home(text, home=HOME) == "ls ~ "

    def test_a_home_with_a_trailing_separator_is_hidden(self):
        """The separator at the end of the home belongs to the path."""
        text = f"{HOME}/notes/todo.md"

        assert hide_home(text, home=HOME + "/") == "~/notes/todo.md"

    def test_the_root_of_a_windows_drive_is_not_hidden(self):
        """Every path is below the root of the drive."""
        text = "C:\\Users\\user\\notes\\todo.md"

        assert hide_home(text, home="C:") == text

    def test_a_path_outside_the_home_is_left_alone(self):
        text = "/var/log/torvalds/agent.log"

        assert hide_home(text, home=HOME) == text

    def test_a_folder_that_only_starts_like_the_home_is_left_alone(self):
        text = HOME + "data/report.md"

        assert hide_home(text, home=HOME) == text

    def test_the_root_of_the_filesystem_is_not_hidden(self):
        """Every path is below the root: a "~" in its place would be a lie."""
        text = "/var/log/torvalds/agent.log"

        assert hide_home(text, home="/") == text

    def test_an_empty_text_stays_empty(self):
        assert hide_home("", home=HOME) == ""

    def test_a_text_without_a_home_stays_itself(self):
        text = "git status"

        assert hide_home(text, home=HOME) == text

    def test_a_windows_home_is_hidden(self):
        text = f"{WINDOWS_HOME}\\Documents\\todo.md"

        assert hide_home(text, home=WINDOWS_HOME) == "~\\Documents\\todo.md"

    def test_a_windows_path_is_not_case_sensitive(self):
        """A Windows path is the same path, however it is written."""
        text = f"{WINDOWS_HOME.lower()}\\documents\\todo.md"

        assert hide_home(text, home=WINDOWS_HOME) == "~\\documents\\todo.md"

    def test_a_windows_path_with_slashes_is_hidden(self):
        text = "C:/Users/user/Documents/todo.md"

        assert hide_home(text, home=WINDOWS_HOME) == "~/Documents/todo.md"

    def test_a_macos_home_is_hidden(self):
        text = "/Users/user/notes/todo.md"

        assert hide_home(text, home="/Users/user") == "~/notes/todo.md"

    def test_the_home_of_the_machine_is_used_when_none_is_given(self):
        """The home is computed, never written down."""
        assert the_home() == str(Path.home())
        assert the_home(HOME) == HOME
