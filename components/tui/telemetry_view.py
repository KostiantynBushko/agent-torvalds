"""
Telemetry View for Torvalds Multi-Window Console.

Renders real-time agent telemetry, session metrics, and toolkit state:
- Operational mode and active retrieved toolkits
- LLM inference statistics and token usage
- System cache hit rates
- Running session duration
"""
import time
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from components.tui.state_bridge import TuiState


class TelemetryView:
    """
    Renders the Agent Telemetry and State pane in the bottom-right sidebar.
    """

    def render(self, state: TuiState) -> Panel:
        """
        Render the telemetry panel.
        
        Args:
            state: Current TuiState snapshot
            
        Returns:
            Rich Panel to place inside layout['telemetry_pane']
        """
        table = Table(box=None, show_header=False, expand=True, padding=(0, 0))
        table.add_column("Metric", style="dim cyan", ratio=45)
        table.add_column("Value", style="bold white", ratio=55)

        # 1. Mode
        table.add_row("Mode", state.mode)

        # 2. Cache Hit Rate
        cache_total = state.cache_total
        cache_hits = state.cache_hits
        if cache_total > 0:
            cache_pct = (cache_hits / cache_total) * 100
            table.add_row("Cache Hits", f"{cache_hits}/{cache_total} ({cache_pct:.0f}%)")
        else:
            table.add_row("Cache Hits", f"{cache_hits} (idle)")

        # 3. Total Tokens & Prompt/Completion breakdown
        if state.total_tokens > 0:
            tokens_str = f"{state.total_tokens:,} [dim]({state.prompt_tokens:,}p/{state.completion_tokens:,}c)[/dim]"
        else:
            tokens_str = "0"
        table.add_row("Total Tokens", tokens_str)

        # 4. LLM Invocations
        table.add_row("LLM Calls", f"{state.llm_call_count}")

        # 5. Tool Calls
        table.add_row("Tool Calls", f"{state.total_tool_calls}")

        # 6. Active Toolkits
        if state.active_toolkits:
            toolkits_str = ", ".join(state.active_toolkits[:4])
            if len(state.active_toolkits) > 4:
                toolkits_str += f" +{len(state.active_toolkits) - 4}"
            table.add_row("Toolkits", toolkits_str)
        else:
            table.add_row("Toolkits", "Git, OS, DB, Math")

        # 7. Session Time
        elapsed_sec = int(time.time() - state.session_start_time)
        m, s = divmod(elapsed_sec, 60)
        h, m = divmod(m, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"
        table.add_row("Session Time", time_str)

        # Check for temporary notification banner
        notification = state.get_notification()
        if notification:
            table.add_row(
                Text.from_markup(f"[bold yellow]Notice:[/bold yellow] [yellow]{notification}[/yellow]")
            )

        return Panel(
            table,
            title="[bold magenta]ℹ️ Agent Telemetry & State[/bold magenta]",
            border_style="magenta",
            padding=(0, 1),
        )
