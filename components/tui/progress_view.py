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

from components.tui.state_bridge import TuiState, ToolExecutionRecord

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


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
        max_iter = max(1, state.max_iterations)
        pct = int((iter_num / max_iter) * 100) if max_iter > 0 else 0
        bar_str = _make_bar(iter_num, max_iter, width=12)

        iter_text = Text.from_markup(
            f"[bold cyan]Workflow Iteration:[/bold cyan] "
            f"[green]{bar_str}[/green] [white]{iter_num}/{max_iter}[/white] [dim]({pct}%)[/dim]\n"
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
                    row_markup += f"\n   [dim]└ {task.details}[/dim]"

                table.add_row(Text.from_markup(row_markup))

        return Panel(
            table,
            title="[bold cyan]⚡ Workflow & Tool Progress[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
