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
import logging
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

from components.config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
#
# The values are resolved through components/config.py: the environment
# variable wins, the configuration file is the layer underneath it, and
# the built-in default is the last resort.
# ---------------------------------------------------------------------------

STATS_ENABLED = config.get("stats.enabled")
STATS_VERBOSE = config.get("stats.verbose")
STATS_PERSIST = config.get("stats.persist")
STATS_MAX_HISTORY = config.get("stats.max_history")
STATS_FORMAT = config.get("stats.format").lower()  # compact | detailed | json


logger.debug(
    "Stats config — enabled=%s, verbose=%s, persist=%s, max_history=%d, format=%s",
    STATS_ENABLED, STATS_VERBOSE, STATS_PERSIST, STATS_MAX_HISTORY, STATS_FORMAT,
)


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
from typing import cast

ALL_EVENTS: list[CBEventType] = cast(list[CBEventType], list(CBEventType))

EVENTS_OF_INTEREST: list[CBEventType] = [
    CBEventType.LLM,
    CBEventType.FUNCTION_CALL,
    CBEventType.EXCEPTION,
]

EVENTS_TO_IGNORE: list[CBEventType] = [e for e in ALL_EVENTS if e not in EVENTS_OF_INTEREST]

logger.debug("Events of interest: %s", [e.value for e in EVENTS_OF_INTEREST])


def _extract_usage(response: Any) -> Dict[str, Any]:
    """
    Extract the token-usage mapping from a LlamaIndex LLM response.

    Different LLM integrations expose usage differently, so several
    shapes are probed:

    * ``response.raw["usage"]`` — Ollama (``prompt_tokens`` /
      ``completion_tokens``) and most OpenAI-compatible providers.
    * ``response.raw["usage_metadata"]`` — some providers.
    * ``response.raw["prompt_eval_count"]`` / ``["eval_count"]`` — the raw
      Ollama wire format, used when ``usage`` was not populated.
    * ``response.additional_kwargs["usage"]`` — fallback location.
    * ``response.usage`` / ``response.usage_metadata`` — attribute access.

    Args:
        response: The LLM response object carried by the callback payload.

    Returns:
        dict: The usage mapping, or an empty dict when none could be found.
    """
    if response is None:
        return {}

    def _from_mapping(mapping: Any) -> Dict[str, Any]:
        if not isinstance(mapping, dict):
            return {}
        usage = mapping.get("usage")
        if isinstance(usage, dict) and usage:
            return usage
        usage = mapping.get("usage_metadata")
        if isinstance(usage, dict) and usage:
            return usage
        # Raw Ollama wire format.
        if "prompt_eval_count" in mapping or "eval_count" in mapping:
            prompt = mapping.get("prompt_eval_count") or 0
            completion = mapping.get("eval_count") or 0
            return {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            }
        # Token counts sitting directly on the payload. Both the
        # prompt/completion and the input/output spellings are accepted.
        prompt = mapping.get("prompt_tokens") or mapping.get("input_tokens")
        completion = mapping.get("completion_tokens") or mapping.get("output_tokens")
        if prompt is not None or completion is not None:
            prompt = prompt or 0
            completion = completion or 0
            return {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": mapping.get("total_tokens") or (prompt + completion),
            }
        return {}

    # Attribute access first (covers response.usage / response.usage_metadata).
    for attr in ("usage", "usage_metadata"):
        value = getattr(response, attr, None)
        if isinstance(value, dict) and value:
            return value

    raw = getattr(response, "raw", None)
    usage = _from_mapping(raw)
    if usage:
        return usage

    additional = getattr(response, "additional_kwargs", None)
    if isinstance(additional, dict):
        usage = _from_mapping(additional)
        if usage:
            return usage

    return {}


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
        # Call parent __init__ with ignore lists - this is REQUIRED for newer Llama Index versions
        super().__init__(
            event_starts_to_ignore=EVENTS_TO_IGNORE,
            event_ends_to_ignore=EVENTS_TO_IGNORE,
        )
        self.request_id = request_id
        self.user_query = user_query
        self.stats = RequestStats(
            request_id=request_id,
            user_query=user_query,
            start_time=time.monotonic(),
        )
        self._llm_start_times: Dict[str, float] = {}
        self._tool_start_times: Dict[str, tuple] = {}
        # Tool calls sourced from the workflow event stream (LlamaIndex never
        # emits CBEventType.FUNCTION_CALL, so they arrive via EventConsumer).
        #
        # Keyed by tool_id when available. The workflow executes tool calls
        # CONCURRENTLY (one ``call_tool`` step per call), so several calls to
        # the same tool can be in flight at the same time. Keying by tool
        # name alone would collapse them into a single entry and mis-pair the
        # start times with the wrong results. A FIFO list per key keeps the
        # pairing correct even when the same tool is called twice at once.
        self._pending_tool_starts: Dict[str, List[float]] = {}

        logger.debug(
            "RequestStatsHandler created — request_id=%s, query='%s'",
            request_id, user_query[:80],
        )

    # --- Event start ---

    def start_trace(self, trace_id: str = "") -> None:
        """Start a trace (no-op for this handler)."""
        logger.debug("start_trace called — trace_id=%s", trace_id)

    def end_trace(self, trace_id: str = "", **kwargs: Any) -> None:
        """End a trace (no-op for this handler)."""
        logger.debug("end_trace called — trace_id=%s", trace_id)

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "on_event_start — type=%s, event_id=%s",
            event_type.value if hasattr(event_type, "value") else event_type,
            event_id,
        )
        if event_type == CBEventType.LLM:
            self._llm_start_times[event_id] = time.monotonic()
            logger.debug("  → LLM start recorded for event %s", event_id)
        elif event_type == CBEventType.FUNCTION_CALL:
            tool_name = (
                payload.get(EventPayload.TOOL, "unknown")
                if payload
                else "unknown"
            )
            self._tool_start_times[event_id] = (tool_name, time.monotonic())
            logger.debug("  → Tool call start: tool='%s', event_id=%s", tool_name, event_id)

    # --- Event end ---

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        logger.debug(
            "on_event_end — type=%s, event_id=%s",
            event_type.value if hasattr(event_type, "value") else event_type,
            event_id,
        )
        if event_type == CBEventType.LLM:
            self._on_llm_end(payload, event_id)
        elif event_type == CBEventType.FUNCTION_CALL:
            self._on_tool_end(payload, event_id)
        elif event_type == CBEventType.EXCEPTION:
            if payload:
                error = payload.get(EventPayload.EXCEPTION)
                if error:
                    logger.warning("  → Exception caught: %s", error)
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
                usage = _extract_usage(response)
                if usage:
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

        logger.debug(
            "  → LLM call #%d finished — prompt=%d, completion=%d, total=%d tokens",
            self.stats.llm_call_count,
            prompt_tokens,
            completion_tokens,
            prompt_tokens + completion_tokens,
        )

    def _on_tool_end(
        self, payload: Optional[Dict[str, Any]], event_id: str
    ) -> None:
        """Process tool call end — record timing and result."""
        if event_id not in self._tool_start_times:
            logger.debug("  → Tool call event_id %s not found in start times (skipping)", event_id)
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

        logger.debug(
            "  → Tool call finished: tool='%s', duration=%.1fms, total_tool_calls=%d",
            tool_name, duration_ms, len(self.stats.tool_calls),
        )

    # ------------------------------------------------------------------
    # Public API — tool calls sourced from the workflow event stream
    # ------------------------------------------------------------------
    #
    # LlamaIndex 0.14.x never emits CBEventType.FUNCTION_CALL: the enum
    # value exists but nothing raises it, and FunctionAgent publishes tool
    # activity on the *workflow event stream* (ToolCall / ToolCallResult
    # events) instead. EventConsumer receives those events and feeds them
    # back into this handler through the methods below.

    def begin_tool_call(self, tool_name: str, tool_id: str = "") -> None:
        """
        Record the start of a tool invocation.

        Args:
            tool_name: Name of the tool being invoked.
            tool_id: Optional identifier of the specific invocation. The
                workflow runs tool calls concurrently, so the id is used to
                keep concurrent calls to the *same* tool apart.
        """
        key = tool_id or tool_name
        self._pending_tool_starts.setdefault(key, []).append(time.monotonic())
        logger.debug(
            "  → Tool call started: tool='%s', key='%s', pending=%d",
            tool_name, key, len(self._pending_tool_starts),
        )

    def end_tool_call(
        self,
        tool_name: str,
        succeeded: bool = True,
        error_message: str = "",
        tool_id: str = "",
    ) -> None:
        """
        Record the completion of a tool invocation.

        Args:
            tool_name: Name of the tool that finished.
            succeeded: Whether the tool call completed successfully.
            error_message: Optional error detail when the call failed.
            tool_id: Optional identifier of the specific invocation, matching
                the one passed to :meth:`begin_tool_call`.
        """
        # Prefer the id-keyed bucket; fall back to the name-keyed one for
        # callers that do not provide ids.
        key = tool_id or tool_name
        queue = self._pending_tool_starts.get(key)
        start = queue.pop(0) if queue else None
        if not queue:
            self._pending_tool_starts.pop(key, None)

        if start is None:
            # No matching start was recorded (e.g. only the result was
            # observed) — still count the call so the count stays truthful.
            start = time.monotonic()
            logger.debug("  → Tool call end without start: tool='%s'", tool_name)

        end = time.monotonic()
        record = ToolCallRecord(
            tool_name=tool_name,
            start_time=start,
            end_time=end,
            duration_ms=(end - start) * 1000,
            succeeded=succeeded,
            error_message=error_message,
        )
        self.stats.tool_calls.append(record)

        if not succeeded and error_message:
            self.stats.errors.append(f"Tool '{tool_name}' failed: {error_message}")

        logger.debug(
            "  → Tool call recorded: tool='%s', duration=%.1fms, succeeded=%s, "
            "total_tool_calls=%d",
            tool_name, record.duration_ms, succeeded, len(self.stats.tool_calls),
        )

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: float = 0.0,
        succeeded: bool = True,
        error_message: str = "",
    ) -> None:
        """
        Record a completed tool call in one shot.

        Convenience wrapper for callers that already know the duration.

        Args:
            tool_name: Name of the tool that was invoked.
            duration_ms: How long the call took, in milliseconds.
            succeeded: Whether the tool call completed successfully.
            error_message: Optional error detail when the call failed.
        """
        end = time.monotonic()
        start = end - (duration_ms / 1000.0)

        record = ToolCallRecord(
            tool_name=tool_name,
            start_time=start,
            end_time=end,
            duration_ms=duration_ms,
            succeeded=succeeded,
            error_message=error_message,
        )
        self.stats.tool_calls.append(record)

        if not succeeded and error_message:
            self.stats.errors.append(f"Tool '{tool_name}' failed: {error_message}")

        logger.debug(
            "  → Tool call recorded: tool='%s', duration=%.1fms, total_tool_calls=%d",
            tool_name, duration_ms, len(self.stats.tool_calls),
        )

    def finalize(self) -> RequestStats:
        """Finalize and return the collected stats."""
        self.stats.end_time = time.monotonic()
        self.stats.total_duration_ms = (
            self.stats.end_time - self.stats.start_time
        ) * 1000

        logger.debug(
            "Stats finalized — request_id=%s, duration=%.1fms, llm_calls=%d, "
            "tokens=%d (📥%d 📤%d), tools=%d, errors=%d",
            self.stats.request_id,
            self.stats.total_duration_ms,
            self.stats.llm_call_count,
            self.stats.total_tokens,
            self.stats.total_prompt_tokens,
            self.stats.total_completion_tokens,
            len(self.stats.tool_calls),
            len(self.stats.errors),
        )
        return self.stats


# ---------------------------------------------------------------------------
# Callback manager wiring
# ---------------------------------------------------------------------------


def bind_callback_manager(agent: Any, callback_manager: Optional[Any]) -> bool:
    """
    Bind a callback manager to the LLM instance backing an agent.

    Why this is needed
    ------------------
    ``llama_index.core.llms.callbacks.llm_chat_callback`` resolves the
    callback manager from the **LLM instance**, not from the agent::

        callback_manager = getattr(_self, "callback_manager", None)
        if not isinstance(callback_manager, CallbackManager):
            _self.callback_manager = CallbackManager()
        yield _self.callback_manager

    Meanwhile ``FunctionAgent`` is a Pydantic model that has **no**
    ``callback_manager`` field, so ``FunctionAgent(callback_manager=...)`` and
    ``agent.run(callback_manager=...)`` are silently discarded (Pydantic's
    default ``extra`` behaviour is to ignore unknown kwargs).

    The practical consequence is that a handler attached to the manager
    passed to ``agent.run()`` never receives a single event, while the
    manager that *does* receive events — the one on the LLM — stays empty.
    The result is that every event-derived metric (LLM calls, tokens) is
    permanently zero.

    This helper points the LLM's manager at the given one so that LLM-level
    events actually reach the handlers.

    Args:
        agent: The agent whose ``llm`` should receive the manager.
        callback_manager: The callback manager to install on the LLM.

    Returns:
        bool: True if the manager was successfully bound to an LLM.
    """
    if callback_manager is None:
        return False

    llm = getattr(agent, "llm", None)
    if llm is None:
        logger.warning(
            "bind_callback_manager: agent has no 'llm' attribute — "
            "callback events will not be received"
        )
        return False

    try:
        llm.callback_manager = callback_manager
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("bind_callback_manager: failed to set llm.callback_manager: %s", exc)
        return False

    logger.debug(
        "bind_callback_manager: callback manager bound to LLM %s",
        type(llm).__name__,
    )
    return True


# ---------------------------------------------------------------------------
# Stats renderer
# ---------------------------------------------------------------------------


class StatsRenderer:
    """Renders request statistics to the console using Rich."""

    def __init__(self, console: Console):
        self.console = console
        logger.debug("StatsRenderer created")

    def render(
        self, stats: RequestStats, show_tools: bool = True
    ) -> None:
        """Render a statistics panel after a response."""
        logger.debug("Rendering stats — format=%s, request_id=%s", STATS_FORMAT, stats.request_id)

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

        logger.debug("Rendering stats as JSON")
        self.console.print(
            json.dumps(stats.to_dict(), indent=2, default=str),
            style="dim yellow",
        )
