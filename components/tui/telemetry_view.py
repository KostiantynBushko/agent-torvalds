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

#: The icon of the telemetry pane: the high voltage sign U+26A1 - the
#: icon of the progress pane.
#:
#: The operator asked for it on 2026-11-19, after the icons of the
#: panes were put back: the telemetry pane is to carry the high
#: voltage sign, the way the progress pane carries it.
#:
#: The information sign U+2139 that this pane carried before was the
#: one icon that could break the frame of the panel.  The sign is a
#: narrow character - one cell wide - and the variation selector
#: U+FE0F that asks for the emoji presentation makes it two cells
#: wide for Rich, while a terminal without an emoji font draws it one
#: cell wide: the top border of the panel is then one cell shorter
#: than the rest of the frame, the corner of the panel sits inside
#: the edge of the panel, and the live screen leaves the corner of
#: the previous frame next to it - two corners at the right edge of
#: the panel.  That is what the operator reported on 2026-11-19.
#:
#: The high voltage sign is a wide character: it is two cells wide
#: for Rich and for every terminal, with or without the selector.
#: The width of the icon is the same on both sides of the frame, the
#: corner of the top border sits on the edge of the panel, and the
#: gap after the icon is read as a gap.
#:
#: The two panes of the sidebar carry the same icon now.  That is
#: what the operator asked for; the name of the pane - the name is
#: what tells the two panes apart - stands right next to the icon.
TELEMETRY_ICON = "\u26a1"

#: The gap between the icon of a pane and the name of the pane: one
#: blank cell.
#:
#: The gap was two blank cells wide while the icon of this pane
#: carried the variation selector U+FE0F.  Rich measured that icon
#: two cells wide and the terminal drew it one cell wide, so the
#: blank cell of the gap fell into the second cell of the icon and
#: no gap was read at all - the operator asked for the space on
#: 2026-11-19, and the space was not there.
#:
#: The icon of this pane is a wide character now - two cells wide for
#: Rich and for every terminal - and it fills the two cells it
#: takes.  The blank cell of the gap is a blank cell that is read as
#: a gap: the icon sits in its own cells, the name of the pane
#: starts in the cell after the gap, and the two are apart.  A
#: second blank cell would be a hole between them.
#:
#: The gap of the progress pane is the gap of this pane: the two
#: panes are drawn one above the other in the same sidebar, and a gap
#: in one of them and not in the other is read as a difference that
#: is not there.
TITLE_GAP = " "


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

    #: How many names the row shows before it counts the rest.
    TOOL_NAMES_SHOWN = 2

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

        The wording names every number.  The row is called *Prompt*,
        because the panel shows the prompt that goes to the model — and
        "context" is what the window of the model is called, so a row
        called "Context" left the operator guessing which of the two
        numbers was the size of the prompt.  The share names what it is
        a share of, for the same reason: "77.0% of 54K" does not say
        what the 54K are, and "of 54K window" does.

        There is no article in front of the number: "a 8K window" is
        wrong, and the panel is read at a glance.

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
                f"([{style}]{share:.1f}%[/{style}] of {window} window)"
            )
        else:
            head = f"{tokens} tok"

        tail = (
            f"{state.context_messages:,} msgs · "
            f"{_format_size(state.context_bytes)}"
        )
        return f"{head}\n{tail}"

    def _render_tools(self, state: TuiState) -> str:
        """Render the tools the agent really has.

        The count says how the agent got them, so that the number is
        never read as something it is not: "8 selected" is what the
        operator chose, "134 loaded" is every tool of every toolkit, and
        "156 indexed" is every tool the retriever reaches for.

        The names are shown when the operator picked the tools by hand -
        the categories that were selected with ``--select``.  The
        operator picks a category, and the panel names the category:
        "Operating System, System" says what the agent can do, and the
        name of one tool out of the eleven of a category says nothing
        about the other ten.  In the other modes the operator picked no
        tool at all, and a handful of names out of a hundred and fifty
        would say nothing that the count does not say better.

        The names that do not fit are counted and not shown: the panel
        has room for a few, and a list that is cut in the middle
        without saying so is a lie.

        When nothing is known, the row says so - a dash, like the row of
        the size of the prompt.

        Args:
            state: Current TuiState snapshot

        Returns:
            The readout, as one or two lines of markup.
        """
        if not state.active_tools:
            return "[dim]—[/dim]"

        count = len(state.active_tools)
        scope = state.active_tool_scope or "available"
        head = f"{count} {scope}"

        if scope != "selected":
            return head

        # The groups the operator picked.  The tools are the detail
        # behind them, and the panel names the groups: the picker asks
        # for a category, and the answer of the operator was a
        # category.  When the groups are not known, the tools are shown
        # - a row that knows less says what it does know.
        groups = list(state.active_tool_groups) or list(state.active_tools)
        names = groups[: self.TOOL_NAMES_SHOWN]
        lines = [", ".join(names)]
        rest = len(groups) - len(names)
        if rest > 0:
            # The count of the names that are not shown is on a line of
            # its own: a phrase that is broken in the middle is a
            # phrase nobody reads.
            lines.append(f"+{rest} more")

        return "\n".join([head] + lines)

    def render(self, state: TuiState) -> Panel:
        """
        Render the telemetry panel.
        
        Args:
            state: Current TuiState snapshot
            
        Returns:
            Rich Panel to place inside layout['telemetry_pane']
        """
        table = Table(box=None, show_header=False, expand=True, padding=(0, 0))
        # The value column is the wider one: the names of the tools are
        # long, and a name that is cut in half is not a name.  "fold"
        # breaks a name that does not fit instead of hiding the end of
        # it behind an ellipsis.
        table.add_column("Metric", style="dim cyan", ratio=35)
        table.add_column("Value", style="bold white", ratio=65, overflow="fold")

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

        # 4. The size of the prompt that goes to the model
        table.add_row("Prompt", self._render_context(state))

        # 5. LLM Invocations
        table.add_row("LLM Calls", f"{state.llm_call_count}")

        # 6. Tool Calls
        table.add_row("Tool Calls", f"{state.total_tool_calls}")

        # 7. The tools the agent really has
        #
        # The row used to name four toolkits that were written into the
        # source - "Git, OS, DB, Math" - whatever the operator had
        # selected, and whatever was installed on the machine.  A panel
        # that says something the agent does not do is worse than a
        # panel that says nothing: the operator reads it and believes
        # it.
        #
        # The row is a measurement now: the orchestrator hands over the
        # names of the tools the agent really has - the ones the
        # operator picked with --select, every tool in --full, and every
        # tool the retriever indexes.  When nothing is known, the row
        # says so.
        table.add_row("Tools", self._render_tools(state))

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

        # The title of the panel carries the icon of the pane.
        #
        # The icon is the high voltage sign, a wide character: it is
        # two cells wide for Rich and for every terminal, so the
        # frame of the panel is the same width on both sides of the
        # icon, and the corner of the top border sits on the edge of
        # the panel - the corner that used to be drawn twice, once
        # inside the panel and once at the edge of the screen.
        #
        # The icon and the name of the pane are separated by one blank
        # cell.  The icon fills the two cells it takes, the blank cell
        # after it is read as a gap, and the name of the pane starts
        # in the cell after the gap.  The operator asked for the space
        # on 2026-11-19.
        #
        # Below the width of the terminal the title does not fit, the
        # title is cut at the right, and the icon - the first thing in
        # the title - is never the part that is cut.
        return Panel(
            table,
            title=(
                "[bold magenta]"
                f"{TELEMETRY_ICON}{TITLE_GAP}Agent Telemetry & State"
                "[/bold magenta]"
            ),
            border_style="magenta",
            padding=(0, 1),
        )
