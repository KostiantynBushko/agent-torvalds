"""
The progress pane shows the whole command, and splits it when it is too long.

The *Workflow & Tool Progress* pane shows the tool that runs and, under its
name, the line that says what it works on.  That line was **cut** at forty
characters: a command that is longer than that lost its tail, and the tail
is the part that says what the command does.  The operator saw

    ✔ execute_shell_command (33ms)
      └ cd ~/projects/agent-torvalds &&

and could not tell what the command was.

The detail is now shown whole.  A detail that does not fit on one line is
**split** and takes the lines it needs, and every line is the width of the
pane.

Two things had to be right for that to work:

  * the pane has to know how wide it is -- the width of the sidebar is a
    share of the width of the terminal, and the detail is split to the width
    the pane really has;
  * the text of the command has to reach the screen **as it is** -- a command
    carries square brackets of its own, and Rich reads them as markup and
    drops them, so the operator would see a command that is not the one that
    ran.

The check is in two parts:

  * the rule -- how a detail is split, asked about the details that break it;
  * the pane -- the real panel, with the real state, rendered the way the
    terminal renders it.

Run with:
    pytest tests/test_tui_progress_detail.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from rich.cells import cell_len  # noqa: E402
from rich.console import Console  # noqa: E402

from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    progress_pane_width,
)
from components.tui.progress_view import (  # noqa: E402
    DETAIL_PREFIX,
    ProgressView,
    display_detail,
    split_detail,
)
from components.tui.state_bridge import TuiState  # noqa: E402

#: The width the panel is rendered at.
WIDTH = 60

#: The command of the operator: the one that was cut, and that the pane
#: has to show whole.
COMMAND = (
    "cd ~/projects/agent-torvalds && git status --short && "
    "python -m pytest tests/ -x"
)


def a_state_with_a_command(command: str) -> TuiState:
    """A state that carries a tool running a command."""
    state = TuiState()
    state.update_tool_start("execute_shell_command", {"command": command})
    return state


def render(state: TuiState, width: int = WIDTH) -> str:
    """Render the progress panel and return it as plain text."""
    console = Console(width=width, color_system=None)
    panel = ProgressView().render(state, width=width)
    lines = console.render_lines(panel, console.options.update(width=width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


def without_spaces(text: str) -> str:
    """The text without its spaces: every character that is not a space."""
    return "".join(text.split())


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


class TestTheDetailIsSplit:
    """The detail is split to the width of the pane."""

    def test_a_short_detail_is_one_line(self):
        assert split_detail("git status", 40) == ["git status"]

    def test_a_long_detail_is_split(self):
        lines = split_detail(COMMAND, 20)

        assert len(lines) > 1, "the command was not split"

    def test_every_line_fits_the_width(self):
        lines = split_detail(COMMAND, 20)

        for line in lines:
            assert cell_len(line) <= 20, f"the line is too wide: {line!r}"

    def test_nothing_of_the_detail_is_lost(self):
        """Only the spaces at the break of a line are gone."""
        lines = split_detail(COMMAND, 20)

        assert without_spaces(" ".join(lines)) == without_spaces(COMMAND)

    def test_a_path_is_split_at_its_separator(self):
        """A path is not cut in the middle of the name of a folder."""
        lines = split_detail("cd ~/projects/agent-torvalds", 19)

        assert lines[0] == "cd", f"the path was not split: {lines!r}"
        assert lines[1].endswith("/"), f"the path was cut in a name: {lines!r}"
        assert without_spaces(" ".join(lines)) == without_spaces(
            "cd ~/projects/agent-torvalds"
        )

    def test_a_word_that_does_not_fit_is_cut(self):
        """A word without a separator is cut at the edge of the line."""
        lines = split_detail("x" * 30, 10)

        assert len(lines) == 3
        for line in lines:
            assert cell_len(line) <= 10

    def test_a_line_break_in_the_detail_is_kept(self):
        """The detail may be a script of more than one line."""
        lines = split_detail("first\nsecond", 40)

        assert lines == ["first", "second"]

    def test_the_spaces_of_a_quoted_text_are_kept(self):
        """A command carries spaces that mean something."""
        lines = split_detail('echo "a  b" && ls', 40)

        assert '"a  b"' in lines[0]

    def test_a_width_of_no_cells_keeps_the_detail(self):
        """A width that nothing reaches does not lose the detail."""
        lines = split_detail(COMMAND, 0)

        assert without_spaces(" ".join(lines)) == without_spaces(COMMAND)

    def test_an_empty_detail_is_one_empty_line(self):
        assert split_detail("", 20) == [""]


class TestTheDetailIsShown:
    """The detail on the screen is the detail of the tool."""

    def test_the_home_of_the_operator_is_hidden(self):
        """The home is hidden before the text is split."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            return

        shown = display_detail(f"cat {home}/notes/todo.md", 40)

        assert home not in shown
        assert "~/notes/todo.md" in shown

    def test_the_home_is_hidden_before_the_text_is_split(self):
        """A home that is cut in half is worse than a home that is shown."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            return

        shown = display_detail(f"python -m pytest --rootdir={home}/project", 20)

        assert home not in shown
        assert home[:6] not in shown

    def test_the_lines_after_the_first_one_are_indented(self):
        """The text of a command that takes several lines stands under itself."""
        lines = display_detail(COMMAND, 20).split("\n")

        assert len(lines) > 1
        for line in lines[1:]:
            assert line.startswith(" " * DETAIL_PREFIX), (
                f"the line is not indented under the command: {line!r}"
            )


# ---------------------------------------------------------------------------
# The pane
# ---------------------------------------------------------------------------


class TestThePane:
    """The pane shows the whole command."""

    def test_the_whole_command_is_on_the_screen(self):
        """The command of the operator is not cut any more."""
        text = render(a_state_with_a_command(COMMAND), WIDTH)

        for word in ("cd", "git", "status", "--short", "python", "pytest", "-x"):
            assert word in text, f"the pane does not show {word!r}: {text!r}"

    def test_the_tail_of_the_command_is_on_the_screen(self):
        """The part that was cut away is the part that says what it does."""
        text = render(a_state_with_a_command(COMMAND), WIDTH)

        assert "-x" in text, f"the tail is missing: {text!r}"

    def test_the_command_is_split_over_several_lines(self):
        """A command that does not fit takes the lines it needs."""
        text = render(a_state_with_a_command(COMMAND), WIDTH)

        assert text.count("└") == 1, "the detail was not opened by a branch"
        assert text.count("\n") > 4, "the command was not split"

    def test_a_short_command_is_on_one_line(self):
        text = render(a_state_with_a_command("git status"), WIDTH)

        assert "└ git status" in text

    def test_the_command_with_brackets_is_the_command_that_ran(self):
        """The operator sees the command that ran, and not another one."""
        text = render(a_state_with_a_command("ls [abc] && echo done"), WIDTH)

        assert "[abc]" in text, f"the pane does not show the brackets: {text!r}"

    def test_a_markup_tag_of_the_command_is_not_a_tag(self):
        """A command that carries what looks like a tag shows it as it is."""
        text = render(a_state_with_a_command("grep [dim]x[/dim] ."), WIDTH)

        assert "[dim]x[/dim]" in text, f"the pane lost the tag: {text!r}"

    def test_the_pane_keeps_the_real_path(self):
        """The agent works with the path of the machine, and keeps it."""
        state = TuiState()
        state.update_tool_start("read_file", {"file_path": "/tmp/notes.md"})

        arguments = state.task_stack.tasks[0].arguments
        assert arguments["file_path"] == "/tmp/notes.md"


# ---------------------------------------------------------------------------
# The width of the pane
# ---------------------------------------------------------------------------


class TestTheWidthOfThePane:
    """The pane knows how wide it is."""

    def test_the_width_is_the_one_the_layout_uses(self):
        """The number the pane splits to is the number the layout gives it."""
        for console_width in (80, 100, 120, 140, 160, 200):
            layout = build_torvalds_layout()
            console = Console(width=console_width, color_system=None)
            console.render_lines(
                layout, console.options.update_dimensions(console_width, 40)
            )

            pane = layout["progress_pane"]
            region = layout.map[pane].region

            assert progress_pane_width(console_width) == region.width, (
                f"the pane is {region.width} cells wide at {console_width} "
                f"columns, and the width that is computed is "
                f"{progress_pane_width(console_width)}"
            )

    def test_a_wider_terminal_gives_a_wider_pane(self):
        assert progress_pane_width(160) > progress_pane_width(80)

    def test_the_detail_follows_the_width_of_the_pane(self):
        """A wider pane shows the command in fewer lines."""
        state = a_state_with_a_command(COMMAND)

        narrow = render(state, 80).count("\n")
        wide = render(state, 160).count("\n")

        assert narrow > wide, "the wider pane did not take fewer lines"

    def test_the_text_fits_the_pane_it_is_shown_in(self):
        """No line of the detail is wider than the pane."""
        for console_width in (80, 120, 160):
            pane = progress_pane_width(console_width)
            lines = split_detail(COMMAND, pane - 9)

            for line in lines:
                assert cell_len(line) <= pane - 9
