"""
Agent Stats Handler — Per-request statistics collection and rendering.

This module provides a Llama Index callback handler that tracks:
  - Token usage (prompt + completion) per LLM call
  - Tool invocations with timing
  - Overall request duration
  - Errors encountered

It also includes a StatsRenderer that formats the statistics using Rich
panels/tables for display after each agent response.

Category: Infrastructure
Retriever Keywords: stats, statistics, logging, metrics, tokens, timing, performance
"""
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from llama_index.core.callbacks.base import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STATS_ENABLED = os.environ.get("TORVALDS_STATS_ENABLED", "true").lower() in ("true", "1", "yes")
STATS_VERBOSE = os.environ.get("TORVALDS_STATS_VERBOSE", "false").lower() in ("true", "1", "yes")
STATS_PERSIST = os.environ.get("TORVALDS_STATS_PERSIST", "true").lower() in ("true", "1", "yes")
STATS_MAX_HISTORY = int(os.environ.get("TORVALDS_STATS_MAX_HISTORY", "500"))
STATS_FORMAT = os.environ.get("TORVALDS_STATS_FORMAT", "compact").lower()  # compact | detailed | json


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""

    tool_name: str
    start_time: float
    end_time: float = 0.0
    duration_ms: float = 0.0
    succeeded: bool = True
    error_message: str = ""


@dataclass
class RequestStats:
    """Aggregated statistics for a single user request."""

    request_id: str
    user_query: str
    start_time: float
    end_time: float = 0.0
    total_duration_ms: float = 0.0
    llm_call_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def avg_llm_call_ms(self) -> float:
        if self.llm_call_count == 0:
            return 0.0
        return self.total_duration_ms / self.llm_call_count

    @property
    def tools_used(self) -> List[str]:
        return list(set(tc.tool_name for tc in self.tool_calls))

    def to_dict(self) -> dict:
        """Serialize to a dictionary suitable for caching."""
        return {
            "request_id": self.request_id,
            "user_query": self.user_query,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime()),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "llm_call_count": self.llm_call_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "tools_used": self.tools_used,
            "tool_call_count": len(self.tool_calls),
            "error_count": len(self.errors),
        }


# ---------------------------------------------------------------------------
# Callback handler
# ---------------------------------------------------------------------------


class RequestStatsHandler(BaseCallbackHandler):
    """
    Custom callback handler that collects per-request statistics.

    Tracks:
    - Token usage (prompt + completion) per LLM call
    - Tool invocations with timing
    - Overall request duration
    - Errors encountered

    Usage:
        handler = RequestStatsHandler(request_id="abc", user_query="hello")
        # Attach to agent via callback_manager
        stats = handler.finalize()
    """

    def __init__(self, request_id: str, user_query: str):
        self.request_id = request_id
        self.user_query = user_query
        self.stats = RequestStats(
            request_id=request_id,
            user_query=user_query,
            start_time=time.monotonic(),
        )
        self._llm_start_times: Dict[str, float] = {}
        self._tool_start_times: Dict[str, tuple] = {}

    def events_of_interest(self) -> List[CBEventType]:
        """Return the event types this handler is interested in."""
        return [
            CBEventType.LLM,
            CBEventType.FUNCTION_CALL,
            CBEventType.EXCEPTION,
        ]

    # --- Event start ---


    def start_trace(self, trace_id: str = "") -> None:
        """Start a trace (no-op for this handler)."""
        pass

    def end_trace(self, trace_id: str = "", **kwargs: Any) -> None:
        """End a trace (no-op for this handler)."""
        pass
    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        if event_type == CBEventType.LLM:
            self._llm_start_times[event_id] = time.monotonic()
        elif event_type == CBEventType.FUNCTION_CALL:
            tool_name = (
                payload.get(EventPayload.TOOL_NAME, "unknown")
                if payload
                else "unknown"
            )
            self._tool_start_times[event_id] = (tool_name, time.monotonic())

    # --- Event end ---

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        if event_type == CBEventType.LLM:
            self._on_llm_end(payload, event_id)
        elif event_type == CBEventType.FUNCTION_CALL:
            self._on_tool_end(payload, event_id)
        elif event_type == CBEventType.EXCEPTION:
            if payload:
                error = payload.get(EventPayload.EXCEPTION)
                if error:
                    self.stats.errors.append(str(error))

    def _on_llm_end(
        self, payload: Optional[Dict[str, Any]], event_id: str
    ) -> None:
        """Process LLM event end — extract token counts."""
        self.stats.llm_call_count += 1

        prompt_tokens = 0
        completion_tokens = 0

        if payload:
            # Try to get tokens from response payload
            response = payload.get(EventPayload.RESPONSE)
            if response:
                raw = getattr(response, "raw", None)
                if isinstance(raw, dict):
                    usage = raw.get("usage", raw.get("usage_metadata", {}))
                    if usage and isinstance(usage, dict):
                        prompt_tokens = (
                            usage.get("prompt_tokens", 0)
                            or usage.get("input_tokens", 0)
                            or 0
                        )
                        completion_tokens = (
                            usage.get("completion_tokens", 0)
                            or usage.get("output_tokens", 0)
                            or 0
                        )

        self.stats.total_prompt_tokens += prompt_tokens
        self.stats.total_completion_tokens += completion_tokens
        self.stats.total_tokens += prompt_tokens + completion_tokens

    def _on_tool_end(
        self, payload: Optional[Dict[str, Any]], event_id: str
    ) -> None:
        """Process tool call end — record timing and result."""
        if event_id not in self._tool_start_times:
            return

        tool_name, start = self._tool_start_times.pop(event_id)
        end = time.monotonic()
        duration_ms = (end - start) * 1000

        record = ToolCallRecord(
            tool_name=tool_name,
            start_time=start,
            end_time=end,
            duration_ms=duration_ms,
        )
        self.stats.tool_calls.append(record)

    def finalize(self) -> RequestStats:
        """Finalize and return the collected stats."""
        self.stats.end_time = time.monotonic()
        self.stats.total_duration_ms = (
            self.stats.end_time - self.stats.start_time
        ) * 1000
        return self.stats


# ---------------------------------------------------------------------------
# Stats renderer
# ---------------------------------------------------------------------------


class StatsRenderer:
    """Renders request statistics to the console using Rich."""

    def __init__(self, console: Console):
        self.console = console

    def render(
        self, stats: RequestStats, show_tools: bool = True
    ) -> None:
        """Render a statistics panel after a response."""
        fmt = STATS_FORMAT

        if fmt == "json":
            self._render_json(stats)
            return

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="dim cyan")
        table.add_column("Value", style="bold white")

        # Timing
        table.add_row(
            "⏱️ Duration",
            f"{stats.total_duration_ms / 1000:.2f}s ({stats.total_duration_ms:.0f}ms)",
        )

        # LLM calls
        table.add_row("🔁 LLM Calls", str(stats.llm_call_count))

        if STATS_VERBOSE and stats.llm_call_count > 0:
            table.add_row(
                "   └─ Avg per call",
                f"{stats.avg_llm_call_ms:.0f}ms",
            )

        # Tokens
        table.add_row(
            "🔢 Tokens",
            f"total={stats.total_tokens} "
            f"(📥{stats.total_prompt_tokens} 📤{stats.total_completion_tokens})",
        )

        if STATS_VERBOSE:
            table.add_row("")
            table.add_row("   ├─ 📥 Prompt", str(stats.total_prompt_tokens))
            table.add_row("   └─ 📤 Completion", str(stats.total_completion_tokens))

        # Tools
        if show_tools and stats.tool_calls:
            tools = stats.tools_used
            table.add_row("🔧 Tools", ", ".join(tools) if tools else "None")
            table.add_row(
                "🛠️ Tool Calls",
                f"{len(stats.tool_calls)} invocations",
            )

            if STATS_VERBOSE:
                # Show per-tool timing
                for tc in stats.tool_calls:
                    table.add_row(
                        f"   └─ {tc.tool_name}",
                        f"{tc.duration_ms:.0f}ms",
                    )

        # Errors
        if stats.errors:
            table.add_row("⚠️ Errors", f"{len(stats.errors)}")
            if STATS_VERBOSE:
                for err in stats.errors[:5]:
                    table.add_row("   └─", err[:60] + "..." if len(err) > 60 else err)
        else:
            if STATS_VERBOSE:
                table.add_row("⚠️ Errors", "0")

        panel = Panel(
            table,
            title=f"[dim]Request {stats.request_id}[/dim]",
            border_style="dim blue",
            padding=(1, 1),
        )
        self.console.print(panel)

    def _render_json(self, stats: RequestStats) -> None:
        """Render stats as JSON."""
        import json

        self.console.print(
            json.dumps(stats.to_dict(), indent=2, default=str),
            style="dim yellow",
        )
