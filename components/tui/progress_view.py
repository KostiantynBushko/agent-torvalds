"""
Progress View for Torvalds Multi-Window Console.

Visualizes background workflow execution progress:
- Multi-step workflow iterations (current / max) with visual progress bar
- Real-time tool execution tracking with elapsed timers and status icons

The line under the name of a tool says what the tool works on -- the
command it runs, the path it reads.  The line carries the **whole**
of it: a command that is cut is a command the operator cannot read,
and the part that is cut away is the part that says what the command
does.  A detail that does not fit on one line is **split** and takes
the lines it needs: every line is the width of the pane, and nothing
of the command is lost.

**The task that runs now is on top of the pane.**  It is drawn
above the window of the pane -- *pinned* -- so the operator sees the
command that runs before anything else, and he keeps seeing it while
he scrolls the log.  The operator asked for it on 2026-11-22: the
command that runs now was in the middle of the commands, with the
finished ones above it -- and he asked for it again on the same day,
in the words of the request: *please make sure the tool task grow
down so that current executed is always on top of the window*.

**The list of the tasks that are done is a log, and it grows down.**
The oldest completion first, the newest at the bottom, and the window
stuck to the bottom: "down" walks forward in time, the way it does in
every scrollable thing the operator knows.  A task that is done is
**appended** at the bottom of the list, and the tasks that were done
before it do not move: the list grows down, and it never grows up.
The **anchor** of the window keeps the operator where he is: a new
task does not move the window of the operator who is reading an old
one.

**The pane that has the focus is marked.**  The border is brighter,
the title carries the marker ``▶``, and the subtitle says where the
operator is.
"""
import re
import time
from typing import List, NamedTuple, Optional, Tuple

from rich.cells import cell_len
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from components.tui.hotkeys import FOCUS_GAP, FOCUS_MARKER
from components.tui.path_display import hide_home
from components.tui.pane_scroll import PaneScroll
from components.tui.state_bridge import TuiState, ToolExecutionRecord

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

#: The icon of the progress pane: the high voltage sign U+26A1.
#:
#: The sign is a wide character, and it is two cells wide for Rich and
#: for every terminal - the width of the icon has to be the same for
#: both, or the frame of the panel breaks.  See the icon of the
#: telemetry panel for the whole story.
PROGRESS_ICON = "\u26a1"

#: The gap between the icon of a pane and the name of the pane: one
#: blank cell - the same gap the title of the telemetry panel uses.
#:
#: The icon is a wide character: it is two cells wide for Rich and for
#: every terminal, and it fills the two cells it takes.  The blank
#: cell after it is a blank cell that is read as a gap - the icon
#: sits in its own cells and the name of the pane starts after them.
#:
#: The gap was two blank cells wide while the icon of the telemetry
#: pane carried the variation selector U+FE0F: the terminal drew that
#: icon one cell narrower than Rich measured it, and the blank cell of
#: the gap fell into the cell the icon did not fill - no gap was read
#: at all.  The icon is one cell wide now, and one blank cell is the
#: gap.  The operator asked for the space on 2026-11-19.
TITLE_GAP = " "

#: The cells the panel spends on its border and on its padding: a
#: border on each side and a cell of padding on each side.
PANEL_OVERHEAD = 4

#: The cells the line of the detail spends before the text of the
#: detail starts: three spaces, the branch that opens the line, and
#: the space behind it.
#:
#: The lines after the first one are indented by the same number of
#: cells, so that the text of a command that takes several lines stands
#: under itself and reads as one command.
DETAIL_PREFIX = 5

#: The width of the pane when the caller does not say how wide the
#: pane is.  It is the width of the pane of a terminal of about 140
#: columns, and the text of the detail has 41 cells on one line.
DEFAULT_PANE_WIDTH = 50

#: How many tasks the pane shows.  They are the tasks that are **done**:
#: the log keeps the newest ones, the oldest of them is the first one
#: on the screen, and the newest is the last one.  The task that runs
#: now is not one of them -- it is pinned above them.
TASKS_SHOWN = 6

#: The words of a detail, and the spaces between them.
_WORDS = re.compile(r"\s+|\S+")


def detail_width(pane_width: int) -> int:
    """
    The number of cells the text of the detail has on one line.

    The pane spends a few of its cells on its frame, and the line of the
    detail spends a few more on the branch that opens it: what is
    left is the width of the text of the command.

    Args:
        pane_width: The number of cells the pane has on the screen.

    Returns:
        The number of cells of the text of the detail on one line.
    """
    return max(1, int(pane_width) - PANEL_OVERHEAD - DETAIL_PREFIX)


def _the_head_that_fits(text: str, width: int) -> str:
    """
    The beginning of the text that fits on one line.

    A path is cut at the separator that fits: the name of the folder
    behind the separator stays whole, and a path that is cut in the
    middle of a name is harder to read than a path that is cut at a
    separator.  A text without a separator - a long flag, a long name
    - is cut at the edge of the line.

    Args:
        text: The text to cut.
        width: The number of cells of the line.

    Returns:
        The beginning of the text that fits.
    """
    cells = 0
    cut = 0
    for index, character in enumerate(text):
        size = cell_len(character)
        if cells + size > width:
            break
        cells += size
        cut = index + 1

    head = text[:cut]
    separator = max(head.rfind("/"), head.rfind("\\"))
    if separator > 0:
        head = head[: separator + 1]
    return head


def _split_word(word: str, width: int) -> List[str]:
    """
    The lines of a word that is longer than the line.

    The word is cut at the separator that fits, or at the edge of the
    line when it has no separator.

    Args:
        word: The word that does not fit on one line.
        width: The number of cells of the line.

    Returns:
        The lines of the word.
    """
    pieces: List[str] = []
    remaining = word
    while cell_len(remaining) > width:
        head = _the_head_that_fits(remaining, width)
        if not head:
            # Not even one character fits on the line: the character
            # goes on the line on its own, and the line is overfull.
            head = remaining[0]
        pieces.append(head)
        remaining = remaining[len(head):]
    if remaining:
        pieces.append(remaining)
    return pieces


def _split_block(block: str, width: int) -> List[str]:
    """
    The lines of one block of the detail.

    A block is a piece of the detail that carries no line break of its
    own.  The words are put on the lines as they come: a word that
    does not fit beside what is on the line goes on the next one, and
    a word that does not fit on a line of its own is cut.

    The spaces between the words are kept: a command carries spaces
    that mean something - inside a quoted text every one of them
    counts.  The spaces at the end of a line are the break of the
    line, and they are not shown.

    Args:
        block: The block of the detail.
        width: The number of cells of the line.

    Returns:
        The lines of the block.
    """
    if not block:
        return [""]

    lines: List[str] = []
    current = ""
    current_width = 0
    space = ""

    for token in _WORDS.findall(block):
        if token.isspace():
            # The spaces between the words: they are kept, and they
            # are the break of the line when the word behind them does
            # not fit.
            space = token
            continue

        word_width = cell_len(token)
        if word_width > width:
            # The word does not fit on a line of its own: it is cut.
            if current:
                lines.append(current)
                current = ""
                current_width = 0
            lines.extend(_split_word(token, width))
            space = ""
            continue

        space_width = cell_len(space)
        if current and current_width + space_width + word_width > width:
            # The word does not fit beside what is on the line: the
            # line ends here, and the word goes on the next one.
            lines.append(current)
            current = token
            current_width = word_width
            space = ""
            continue

        if current:
            current += space + token
            current_width += space_width + word_width
        else:
            # The line starts with the word: the spaces that stood
            # before it were the break of the line before it.
            current = token
            current_width = word_width
        space = ""

    if current:
        lines.append(current)
    return lines


def split_detail(details: str, width: int) -> List[str]:
    """
    The lines the detail is shown in.

    The detail is split at the width of the pane: a line that is full
    ends, and the text after it goes on the next line.  A line break
    that is in the detail itself is kept - the detail may be a script
    of more than one line.

    Nothing of the detail is lost: the lines together carry the whole
    of it.

    Args:
        details: The detail of the tool.
        width: The number of cells of the line.

    Returns:
        The lines the detail is shown in.
    """
    width = max(1, int(width))
    lines: List[str] = []
    for block in details.split("\n"):
        lines.extend(_split_block(block, width))
    return lines or [""]


def display_detail(details: str, width: int) -> str:
    """
    The line under the name of the tool, the way the screen shows it.

    The whole detail is shown: a command that is cut is a command the
    operator cannot read.  A detail that does not fit on one line is
    **split**, and the lines after the first one are indented under the
    text of the first one.

    The home of the operator is hidden **before** the text is split: a
    home that is cut in half is worse than a home that is shown.

    The text is escaped: a command carries square brackets of its own,
    and Rich reads them as markup - the text between them disappears
    from the screen, and the operator sees a command that is not the
    one that ran.

    Args:
        details: The detail of the tool.
        width: The number of cells of the text of the detail.

    Returns:
        The text of the detail, with the lines it takes.
    """
    lines = split_detail(hide_home(details), width)
    return ("\n" + " " * DETAIL_PREFIX).join(escape(line) for line in lines)


def _make_bar(current: int, total: int, width: int = 14) -> str:
    """Generate a clean ASCII progress bar."""
    if total <= 0:
        return "[" + "░" * width + "]"
    ratio = max(0.0, min(1.0, current / total))
    filled = int(ratio * width)
    unfilled = width - filled
    return "[" + ("█" * filled) + ("░" * unfilled) + "]"


class Section(NamedTuple):
    """One part of the content of the pane.

    Attributes:
        lines: The lines of the part.
        anchors: The anchor of every line -- the id of the task the
            line belongs to.
    """

    lines: List[str]
    anchors: List[str]


class ProgressView:
    """
    Renders the Workflow and Tool Progress pane in the top-right sidebar.
    """

    def sections(
        self,
        state: TuiState,
        text_width: int,
    ) -> Tuple[Section, Section, Section]:
        """
        The three parts of the content of the pane.

        The **head** is the bar of the iteration and the name of the
        list.  The **running** part is the task that runs now -- it is
        drawn above the window of the pane, so it is on top of the
        window and it stays there while the operator scrolls the log.
        The **log** is the tasks that are done: the oldest completion
        first, and the newest at the bottom.  The log **grows down**:
        a task that is done is appended at the bottom of it, and the
        tasks that were done before it do not move.

        The anchor of a line is the id of the task the line belongs to,
        and the anchor is what keeps the operator on the task he is
        reading when a new task arrives.

        Args:
            state: Current TuiState snapshot
            text_width: The number of cells the detail of a tool has on
                one line.

        Returns:
            The head, the running task, and the log.
        """
        head_lines: List[str] = []
        head_anchors: List[str] = []

        # 1. Workflow Iteration Bar
        iter_num = state.workflow_iteration
        budget = max(0, state.max_iterations)

        if budget:
            # The budget of the run is known: the bar is the share of it
            # that is spent, and the share is the share of the budget.
            pct = int((iter_num / budget) * 100)
            bar = f"[green]{_make_bar(iter_num, budget, width=12)}[/green] "
            counter = f"[white]{iter_num}/{budget}[/white] [dim]({pct}%)[/dim]"
        else:
            # The budget of the run is not known.  The number of the
            # iteration is shown alone: a budget of one is a budget
            # nobody gave, and a bar that is full because of it would
            # say more than the run knows.
            bar = ""
            counter = f"[white]{iter_num}[/white]"

        head_lines.append(
            f"[bold cyan]Workflow Iteration:[/bold cyan] {bar}{counter}"
        )
        head_anchors.append("")

        # The blank line behind the bar.
        head_lines.append("")
        head_anchors.append("")

        # 2. Tool Tasks Header
        head_lines.append("[bold dim white]Recent Tool Tasks:[/bold dim white]")
        head_anchors.append("")

        now = time.time()
        spinner_char = SPINNER_FRAMES[state.spinner_frame % len(SPINNER_FRAMES)]

        # The task that runs now, and the tasks that are done.
        running = [task for task in state.tool_tasks if task.status == "running"]
        done = [task for task in state.tool_tasks if task.status != "running"]
        # The log is the order of what happened: the task that is done
        # first is the oldest one.  The list **grows down**: a task
        # that is done is appended at the bottom of the log, and the
        # tasks that were done before it do not move.
        done.sort(key=lambda task: task.end_time or task.start_time)

        running_lines, running_anchors = self._task_lines(
            running, now, spinner_char, text_width
        )
        log_lines, log_anchors = self._task_lines(
            done[-TASKS_SHOWN:], now, spinner_char, text_width
        )

        if not running and not done:
            log_lines = ["[dim]  No active background tasks[/dim]"]
            log_anchors = [""]

        return (
            Section(head_lines, head_anchors),
            Section(running_lines, running_anchors),
            Section(log_lines, log_anchors),
        )

    def content_lines(
        self,
        state: TuiState,
        text_width: int,
    ) -> Tuple[List[str], List[str]]:
        """
        The lines of the content of the pane, and the anchor of every line.

        The content is the head of the pane, the task that runs now, and
        the log of the tasks that are done.  The task that runs now is
        the **first** line of the list of the tasks: the operator sees
        the command that runs before anything else.

        Args:
            state: Current TuiState snapshot
            text_width: The number of cells the detail of a tool has on
                one line.

        Returns:
            The lines of the content, and the anchor of every line.
        """
        head, running, log = self.sections(state, text_width)

        lines = head.lines + running.lines + log.lines
        anchors = head.anchors + running.anchors + log.anchors
        return lines, anchors

    def _task_lines(
        self,
        tasks: List[ToolExecutionRecord],
        now: float,
        spinner_char: str,
        text_width: int,
    ) -> Tuple[List[str], List[str]]:
        """The lines of the tasks, and the anchor of every line.

        Args:
            tasks: The tasks to draw.
            now: The time the pane is drawn at.
            spinner_char: The frame of the spinner of the running task.
            text_width: The number of cells the detail of a tool has on
                one line.

        Returns:
            The lines of the tasks, and the anchor of every line.
        """
        lines: List[str] = []
        anchors: List[str] = []

        for task in tasks:
            lines.append(self._task_line(task, now, spinner_char))
            anchors.append(task.id)

            if not task.details:
                continue

            detail = display_detail(task.details, text_width)
            for index, detail_line in enumerate(detail.split("\n")):
                if index == 0:
                    # The branch opens the detail: it stands under the
                    # name of the tool.
                    lines.append(f"   [dim]└ {detail_line}[/dim]")
                else:
                    # The lines after the first one are indented under
                    # the text of the first one: the command stands
                    # under itself and reads as one command.
                    lines.append(f"[dim]{detail_line}[/dim]")
                anchors.append(task.id)

        return lines, anchors

    def _task_line(
        self,
        task: ToolExecutionRecord,
        now: float,
        spinner_char: str,
    ) -> str:
        """The line of a task: its name, its state, and how long it took."""
        if task.status == "running":
            elapsed = now - task.start_time
            return (
                f" [bold yellow]{spinner_char}[/bold yellow] "
                f"[yellow]{task.name}[/yellow] "
                f"[dim]({elapsed:.1f}s)[/dim]"
            )
        if task.status == "completed":
            dur_str = (
                f"{task.duration_ms:.0f}ms"
                if task.duration_ms < 1000
                else f"{task.duration_ms / 1000:.1f}s"
            )
            return (
                f" [bold green]✔[/bold green] "
                f"[white]{task.name}[/white] "
                f"[dim]({dur_str})[/dim]"
            )
        return (
            f" [bold red]✖[/bold red] "
            f"[red]{task.name}[/red] "
            f"[dim](failed)[/dim]"
        )

    def render(
        self,
        state: TuiState,
        width: Optional[int] = None,
        scroll: Optional[PaneScroll] = None,
        focused: bool = False,
    ) -> Panel:
        """
        Render the progress panel.

        Args:
            state: Current TuiState snapshot
            width: The number of cells the pane has on the screen.  The
                detail of a tool is split to fit it: the whole command
                is shown, and it takes the lines it needs.  None means
                the width of the pane is not known, and the default of
                the module is used.
            scroll: The scroll of the pane.  When it is given, the
                content is sliced to the window of the scroll, and the
                scroll learns the content it scrolls.  None means the
                whole content is shown.
            focused: Whether the pane has the focus.  The pane that has
                the focus carries a brighter border and the marker in
                its title.

        Returns:
            Rich Panel to place inside layout['progress_pane']
        """
        if width is None:
            width = DEFAULT_PANE_WIDTH
        text_width = detail_width(width)

        head, running, log = self.sections(state, text_width)

        if scroll is not None:
            # The task that runs now is **pinned**: it is drawn above
            # the window of the pane, and the window is the log of the
            # tasks that are done.  The window gets the lines that are
            # left of the pane, and the lines that do not fit are
            # reached with the keys of the pane.
            available = scroll.height or (
                len(head.lines) + len(running.lines) + len(log.lines)
            )
            height = max(
                1,
                available - len(head.lines) - len(running.lines),
            )
            scroll.set_frame(log.lines, log.anchors, height=height)
            lines = head.lines + running.lines + scroll.window()
        else:
            lines = head.lines + running.lines + log.lines

        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        for line in lines:
            table.add_row(Text.from_markup(line) if line else Text(""))

        # The title of the panel carries the icon of the pane, and it
        # is measured the way the title of the telemetry panel is: the
        # icon is two cells wide for Rich and for every terminal, so
        # that the frame of the panel is the same width on both sides
        # of the icon and the corner of the top border sits on the
        # edge of the panel.
        #
        # The icon and the name of the pane are separated by one blank
        # cell - the same gap the title of the telemetry panel uses.
        # The icon is a wide character: it fills the two cells it
        # takes, and the blank cell after it is read as a gap.  The
        # operator asked for the space on 2026-11-19.
        #
        # Below the width of the terminal the title does not fit, the
        # title is cut at the right, and the icon - the first thing in
        # the title - is never the part that is cut.
        #
        # The pane that has the focus carries the marker in front of
        # the icon: the operator must see which pane the keys go to.
        marker = f"{FOCUS_MARKER}{FOCUS_GAP}" if focused else ""

        # The subtitle says where the operator is.
        subtitle = ""
        if scroll is not None:
            position = scroll.subtitle()
            if position:
                subtitle = f"[dim]{position}[/dim]"

        return Panel(
            table,
            title=(
                "[bold cyan]"
                f"{marker}{PROGRESS_ICON}{TITLE_GAP}Workflow & Tool Progress"
                "[/bold cyan]"
            ),
            subtitle=subtitle,
            border_style="bright_cyan" if focused else "cyan",
            padding=(0, 1),
        )
