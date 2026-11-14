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


#: The share of the context window below which the context is healthy.
CONTEXT_SHARE_OK = 50.0

#: The share of the context window from which the context is tight.
CONTEXT_SHARE_TIGHT = 80.0


def _compact_tokens(tokens: int) -> str:
    """Render a number of tokens the way it is read at a glance.

    The panel has room for a few characters, and ``1,000,000`` is not
    one of them.  The number is rounded — the exact count is in the
    log, where the size of the prompt is written out in full.

    Args:
        tokens: The number of tokens.

    Returns:
        The number, shortened: ``1M``, ``131K`` or the plain number.
    """
    if tokens >= 1_000_000:
        text = f"{tokens / 1_000_000:.1f}M"
        return text.replace(".0M", "M")
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}K"
    return str(tokens)


def _share_style(share: float) -> str:
    """The colour of the share of the context window that is in use.

    Green while the context has room, yellow when it is half full,
    red when three quarters of it are gone: at that point the next tool
    result does not fit any more.

    Args:
        share: The share of the window, in percent.

    Returns:
        The name of the Rich style.
    """
    if share >= CONTEXT_SHARE_TIGHT:
        return "bold red"
    if share >= CONTEXT_SHARE_OK:
        return "yellow"
    return "green"


def _format_size(total_bytes: int) -> str:
    """Render a number of bytes the way the operator reads a size.

    The helper of the chat history is used, so that the size of the
    prompt and the size of a session are written the same way.  A helper
    that cannot be imported is not a reason to lose the line: the plain
    number of bytes is used instead.

    Args:
        total_bytes: The size in bytes.

    Returns:
        The size in bytes, kilobytes or megabytes.
    """
    try:
        from chat_manager.stats import format_size
    except Exception:  # noqa: BLE001 - the line is still worth showing
        return f"{total_bytes} B"
    return format_size(total_bytes)


class TelemetryView:
    """
    Renders the Agent Telemetry and State pane in the bottom-right sidebar.
    """

    def _render_context(self, state: TuiState) -> str:
        """Render the size of the prompt that goes to the model.

        Two lines: the tokens of the prompt and the share of the context
        window they take, and the number of messages and the size of
        the prompt.

        The numbers are the ones the log carries — the same
        measurement, rendered in two lines instead of one.  A readout
        that disagrees with the log is worse than no readout at all.

        Before the first request there is no measurement, and the panel
        says so: a context of "0 tokens" would be a lie, because the
        size of the prompt is not known yet.

        Args:
            state: Current TuiState snapshot

        Returns:
            The readout, as one or two lines of markup.
        """
        if not state.context_measured:
            return "[dim]—[/dim]"

        tokens = f"{state.context_tokens:,}"
        if state.context_estimated:
            # The tokenizer was not available: the number is an
            # estimate, and the operator is told so.
            tokens = f"≈{tokens}"

        if state.context_window > 0:
            share = 100.0 * state.context_tokens / state.context_window
            style = _share_style(share)
            window = _compact_tokens(state.context_window)
            head = (
                f"{tokens} tok "
                f"([{style}]{share:.1f}% of {window}[/{style}])"
            )
        else:
            head = f"{tokens} tok"

        tail = (
            f"{state.context_messages:,} msgs · "
            f"{_format_size(state.context_bytes)}"
        )
        return f"{head}\n{tail}"

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

        # 4. The size of the context — the prompt that goes to the model
        table.add_row("Context", self._render_context(state))

        # 5. LLM Invocations
        table.add_row("LLM Calls", f"{state.llm_call_count}")

        # 6. Tool Calls
        table.add_row("Tool Calls", f"{state.total_tool_calls}")

        # 7. Active Toolkits
        if state.active_toolkits:
            toolkits_str = ", ".join(state.active_toolkits[:4])
            if len(state.active_toolkits) > 4:
                toolkits_str += f" +{len(state.active_toolkits) - 4}"
            table.add_row("Toolkits", toolkits_str)
        else:
            table.add_row("Toolkits", "Git, OS, DB, Math")

        # 8. Active Project
        if state.active_project:
            project_str = state.active_project
            if state.project_type:
                project_str = f"{project_str} ({state.project_type})"
            table.add_row("Project", project_str)
        elif state.registered_projects:
            table.add_row("Projects", f"{len(state.registered_projects)} registered")

        # 9. Active Chat Session
        if state.chat_session_name:
            session_str = state.chat_session_name
            if state.chat_session_type:
                session_str = f"{session_str} [{state.chat_session_type}]"
            table.add_row("Chat Session", session_str)

        # 10. Session Time
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
