"""
Progress View for Torvalds Multi-Window Console.

Visualizes background workflow execution progress:
- Multi-step workflow iterations (current / max) with visual progress bar
- Real-time tool execution tracking with elapsed timers and status icons
"""
import time
from typing import Optional
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from components.tui.path_display import hide_home
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

#: The width of the line under the name of the tool: the pane is
#: narrow, and the line is cut to the width it has.
DETAIL_WIDTH = 40


def display_detail(details: str) -> str:
    """
    The line under the name of the tool, the way the screen shows it.

    The home of the operator is hidden **before** the line is cut: a
    cut that lands inside the home leaves half of it on the screen.

    The line is the way the *screen* shows the path.  The state keeps
    the real path — the agent works with the path of the machine, and
    the pane only hides the home of the operator.
    """
    return hide_home(details)[:DETAIL_WIDTH]


def _make_bar(current: int, total: int, width: int = 14) -> str:
    """Generate a clean ASCII progress bar."""
    if total <= 0:
        return "[" + "░" * width + "]"
    ratio = max(0.0, min(1.0, current / total))
    filled = int(ratio * width)
    unfilled = width - filled
    return "[" + ("█" * filled) + ("░" * unfilled) + "]"


class ProgressView:
    """
    Renders the Workflow and Tool Progress pane in the top-right sidebar.
    """

    def render(self, state: TuiState) -> Panel:
        """
        Render the progress panel.
        
        Args:
            state: Current TuiState snapshot
            
        Returns:
            Rich Panel to place inside layout['progress_pane']
        """
        table = Table.grid(expand=True)
        table.add_column(ratio=1)

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

        iter_text = Text.from_markup(
            f"[bold cyan]Workflow Iteration:[/bold cyan] {bar}{counter}\n"
        )
        table.add_row(iter_text)

        # 2. Tool Tasks Header
        table.add_row(Text.from_markup("[bold dim white]Recent Tool Tasks:[/bold dim white]"))

        # 3. Tool Tasks List
        tasks = state.tool_tasks[-6:]  # Show up to 6 most recent tasks
        if not tasks:
            table.add_row(Text.from_markup("[dim]  No active background tasks[/dim]"))
        else:
            now = time.time()
            spinner_char = SPINNER_FRAMES[state.spinner_frame % len(SPINNER_FRAMES)]

            for task in reversed(tasks):
                if task.status == "running":
                    elapsed = now - task.start_time
                    row_markup = (
                        f" [bold yellow]{spinner_char}[/bold yellow] "
                        f"[yellow]{task.name}[/yellow] "
                        f"[dim]({elapsed:.1f}s)[/dim]"
                    )
                elif task.status == "completed":
                    dur_str = f"{task.duration_ms:.0f}ms" if task.duration_ms < 1000 else f"{task.duration_ms / 1000:.1f}s"
                    row_markup = (
                        f" [bold green]✔[/bold green] "
                        f"[white]{task.name}[/white] "
                        f"[dim]({dur_str})[/dim]"
                    )
                else:  # Error
                    row_markup = (
                        f" [bold red]✖[/bold red] "
                        f"[red]{task.name}[/red] "
                        f"[dim](failed)[/dim]"
                    )

                if task.details:
                    row_markup += f"\n   [dim]└ {display_detail(task.details)}[/dim]"

                table.add_row(Text.from_markup(row_markup))

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
        return Panel(
            table,
            title=(
                "[bold cyan]"
                f"{PROGRESS_ICON}{TITLE_GAP}Workflow & Tool Progress"
                "[/bold cyan]"
            ),
            border_style="cyan",
            padding=(0, 1),
        )
