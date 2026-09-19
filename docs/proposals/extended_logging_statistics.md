# Proposal: Extended Request Logging & Statistics for Torvalds Agent

## 1. Problem Statement

Currently, the Torvalds agent has **minimal observability** into request processing. After each user query, there is no feedback on:

*   **Processing time** — How long did the request take?
*   **Token usage** — How many prompt/completion tokens were consumed per LLM call?
*   **Tool usage** — Which tools were invoked and how many times?
*   **Error tracking** — Errors are logged to cache but not surfaced to the user.
*   **Per-request cost estimation** — No visibility into token consumption trends.

**Drawbacks of current approach:**
*   Users cannot gauge performance or efficiency of their queries.
*   Debugging slow requests or token-heavy conversations is difficult.
*   No historical data for optimizing prompts or tool descriptions.
*   The `TokenCountingHandler` from Llama Index exists but is not wired into the agent.

## 2. Goal

Implement a **comprehensive request statistics system** that displays key metrics after each request, including:

| Metric | Description |
|---|---|
| ⏱️ Processing Time | Wall-clock time from input to response |
| 🔢 Total Tokens | Sum of prompt + completion tokens across all LLM calls |
| 📥 Prompt Tokens | Input tokens consumed |
| 📤 Completion Tokens | Output tokens generated |
| 🔧 Tools Used | List of tools invoked during the request |
| 🔁 LLM Calls | Number of LLM invocations (iterations) |
| ⚠️ Errors | Any errors encountered during processing |

## 3. Proposed Architecture

### 3.1. Core Components

```
┌─────────────────────────────────────────────────┐
│              Torvalds Agent                      │
│                                                  │
│  ┌──────────────┐   ┌──────────────────────┐    │
│  │  Request     │──▶│  CallbackManager     │    │
│  │  Handler     │   │  (Llama Index)       │    │
│  └──────────────┘   └──────────┬───────────┘    │
│                                │                 │
│              ┌─────────────────┼───────────┐     │
│              ▼                 ▼           ▼     │
│    ┌─────────────┐ ┌─────────────┐ ┌────────┐  │
│    │ TokenCount  │ │ ToolUsage   │ │ Timing │  │
│    │ Handler     │ │ Tracker     │ │ Hook   │  │
│    └─────────────┘ └─────────────┘ └────────┘  │
│              │               │           │      │
│              └───────┬───────┘───────────┘      │
│                      ▼                           │
│            ┌──────────────────┐                   │
│            │  StatsCollector  │                   │
│            │  (aggregates all)│                   │
│            └────────┬─────────┘                   │
│                     ▼                             │
│            ┌──────────────────┐                   │
│            │  StatsRenderer   │──▶ Console Output │
│            │  (Rich table)    │──▶ Cache Storage  │
│            └──────────────────┘                   │
└─────────────────────────────────────────────────┘
```

### 3.2. How Llama Index Callbacks Work

Llama Index provides a built-in callback system (`CallbackManager`) that fires events during agent execution:

*   `CBEventType.LLM` — Fires on every LLM call (start/end)
*   `CBEventType.FUNCTION_CALL` — Fires when tools are invoked
*   `CBEventType.AGENT_STEP` — Fires on each agent iteration

The existing `TokenCountingHandler` already captures token counts per LLM call. We extend this with a **custom handler** for tool tracking and timing.

### 3.3. Implementation Strategy

#### Step 1: Create a Custom Stats Callback Handler

Create a new module `agent_stats_handler.py` with a callback handler that extends `TokenCountingHandler` and adds tool/timing tracking:

```python
# agent_stats_handler.py (proposed)
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from llama_index.core.callbacks import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload


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


class RequestStatsHandler(BaseCallbackHandler):
    """
    Custom callback handler that collects per-request statistics.

    Tracks:
    - Token usage (prompt + completion) per LLM call
    - Tool invocations with timing
    - Overall request duration
    - Errors encountered
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
        self._tool_start_times: Dict[str, float] = {}

    # --- LLM Events ---

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
            tool_name = payload.get(EventPayload.TOOL_NAME, "unknown") if payload else "unknown"
            self._tool_start_times[event_id] = (tool_name, time.monotonic())

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

    def _on_llm_end(self, payload: Optional[Dict[str, Any]], event_id: str) -> None:
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

    def finalize(self) -> "RequestStats":
        """Finalize and return the collected stats."""
        self.stats.end_time = time.monotonic()
        self.stats.total_duration_ms = (
            self.stats.end_time - self.stats.start_time
        ) * 1000
        return self.stats
```

#### Step 2: Wire the Handler into the Agent

Modify `agent-torvalds.py` to attach the callback handler per request:

```python
# In agent-torvalds.py (proposed changes)
import uuid
import time
from llama_index.core.callbacks import CallbackManager

# New import
from agent_stats_handler import RequestStatsHandler, StatsRenderer


async def prompt_handler(cmd: str, agent: FunctionAgent) -> tuple[str, RequestStats]:
    """Process a single command through the agent, returning both result and stats."""
    request_id = str(uuid.uuid4())[:8]

    # Create per-request handler
    handler = RequestStatsHandler(request_id=request_id, user_query=cmd)

    # Attach to agent's callback manager
    callback_manager = CallbackManager([handler])

    try:
        chat_memory = agent_chat_memory.get_chat_memory()
        increment_session_commands()

        # Pass callback_manager to the agent run
        result = await agent.run(
            cmd,
            memory=chat_memory,
            max_iterations=MAX_ITERATIONS,
            callback_manager=callback_manager,  # <-- inject handler
        )

        response_text = (
            result.get("output")
            if isinstance(result, dict)
            else str(result)
        )

        # Finalize stats
        stats = handler.finalize()
        return response_text, stats

    except Exception as e:
        import traceback
        from agent_cache_system import log_error
        log_error(str(e))
        stats = handler.finalize()
        stats.errors.append(str(e))
        return f"Error: {e}\n{traceback.format_exc()}", stats
```

#### Step 3: Render Statistics After Each Request

Create a `StatsRenderer` class that formats the statistics using Rich:

```python
# StatsRenderer (proposed)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from agent_stats_handler import RequestStats


class StatsRenderer:
    """Renders request statistics to the console."""

    def __init__(self, console: Console):
        self.console = console

    def render(self, stats: RequestStats, show_tools: bool = True) -> None:
        """Render a compact statistics panel after a response."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Label", style="dim cyan")
        table.add_column("Value", style="bold white")

        # Timing
        table.add_row(
            "⏱️ Duration",
            f"{stats.total_duration_ms/1000:.2f}s ({stats.total_duration_ms:.0f}ms)",
        )

        # LLM calls
        table.add_row("🔁 LLM Calls", str(stats.llm_call_count))

        # Tokens
        table.add_row(
            "🔢 Tokens",
            f"total={stats.total_tokens} "
            f"(📥{stats.total_prompt_tokens} 📤{stats.total_completion_tokens})",
        )

        # Tools
        if show_tools and stats.tool_calls:
            tools = stats.tools_used
            table.add_row("🔧 Tools", ", ".join(tools) if tools else "None")
            table.add_row(
                "🛠️ Tool Calls",
                f"{len(stats.tool_calls)} invocations",
            )

        # Errors
        if stats.errors:
            table.add_row("⚠️ Errors", f"{len(stats.errors)}")

        panel = Panel(
            table,
            title=f"[dim]Request {stats.request_id}[/dim]",
            border_style="dim blue",
            padding=(1, 1),
        )
        self.console.print(panel)
```

#### Step 4: Persist Statistics to Cache

Extend the cache system to store per-request statistics:

```python
# In agent_cache_system.py (proposed extension)
def save_request_stats(stats_dict: dict) -> str:
    """Save request statistics to the cache for historical analysis."""
    cache = _get_cache()
    if "request_stats" not in cache:
        cache["request_stats"] = []

    cache["request_stats"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": stats_dict.get("request_id"),
        "duration_ms": stats_dict.get("total_duration_ms"),
        "llm_calls": stats_dict.get("llm_call_count"),
        "total_tokens": stats_dict.get("total_tokens"),
        "prompt_tokens": stats_dict.get("total_prompt_tokens"),
        "completion_tokens": stats_dict.get("total_completion_tokens"),
        "tools_used": stats_dict.get("tools_used", []),
        "error_count": stats_dict.get("error_count", 0),
    })

    # Keep last 500 requests
    cache["request_stats"] = cache["request_stats"][-500:]
    _save_cache(cache)
    return f"Stats saved for request {stats_dict.get('request_id')}"


def get_stats_summary() -> dict:
    """Get summary statistics across all stored requests."""
    cache = _get_cache()
    stats_list = cache.get("request_stats", [])

    if not stats_list:
        return {"message": "No request statistics available yet."}

    total_tokens = sum(s.get("total_tokens", 0) for s in stats_list)
    total_duration = sum(s.get("duration_ms", 0) for s in stats_list)
    total_llm_calls = sum(s.get("llm_calls", 0) for s in stats_list)
    total_errors = sum(s.get("error_count", 0) for s in stats_list)

    return {
        "total_requests": len(stats_list),
        "total_tokens": total_tokens,
        "total_llm_calls": total_llm_calls,
        "avg_tokens_per_request": round(total_tokens / len(stats_list), 1),
        "avg_duration_ms": round(total_duration / len(stats_list), 1),
        "total_errors": total_errors,
    }
```

## 4. Configuration Options

Add environment variables for tuning:

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_STATS_ENABLED` | `true` | Enable/disable stats collection |
| `TORVALDS_STATS_VERBOSE` | `false` | Show detailed per-tool timing |
| `TORVALDS_STATS_PERSIST` | `true` | Save stats to cache for history |
| `TORVALDS_STATS_MAX_HISTORY` | `500` | Max number of requests to retain |
| `TORVALDS_STATS_FORMAT` | `compact` | Output format: `compact`, `detailed`, `json` |

## 5. Example Output

### Compact Mode (Default)

```
>>> what is the latest commit in /home/kbush/ai-agent-investiagte/agent-torvalds?
Processing...

─────────────────────────────────────
  Agent Response
─────────────────────────────────────

The latest commit is: abc1234 - "Update README" (2 hours ago)

─────────────────────────────────────
┌─ Request a3f7b2c1 ─────────────────┐
│ ⏱️ Duration    2.34s (2340ms)       │
│ 🔁 LLM Calls  2                    │
│ 🔢 Tokens     total=1247 (📥982 📤265) │
│ 🔧 Tools      git_get_latest_commit │
│ 🛠️ Tool Calls 1 invocations        │
└────────────────────────────────────┘
─────────────────────────────────────
```

### Detailed Mode (`TORVALDS_STATS_VERBOSE=true`)

```
┌─ Request a3f7b2c1 ───────────────────────────────┐
│ ⏱️ Duration         2.34s (2340ms)                │
│ 🔁 LLM Calls        2                             │
│   └─ Avg per call   1170ms                        │
│ 🔢 Tokens           total=1247                     │
│   ├─ 📥 Prompt      982                           │
│   └─ 📤 Completion  265                           │
│ 🔧 Tools            git_get_latest_commit          │
│   └─ Duration       45ms                          │
│ 🛠️ Tool Calls      1 invocations                  │
│ ⚠️ Errors           0                             │
└───────────────────────────────────────────────────┘
```

## 6. Implementation Plan

### Phase 1: Core Stats Handler (Week 1)
- [ ] Create `agent_stats_handler.py` with `RequestStatsHandler`
- [ ] Wire handler into `prompt_handler()` in `agent-torvalds.py`
- [ ] Display basic stats (duration, tokens, LLM calls) after each request

### Phase 2: Tool Tracking & Rendering (Week 1-2)
- [ ] Implement tool call tracking with timing
- [ ] Create `StatsRenderer` with Rich panels/tables
- [ ] Add compact and detailed output modes

### Phase 3: Persistence & History (Week 2)
- [ ] Extend cache system to store per-request stats
- [ ] Implement `get_stats_summary()` for aggregate analytics
- [ ] Add `\stats` command to view session history

### Phase 4: Configuration & Polish (Week 2-3)
- [ ] Add environment variable support
- [ ] Add CLI flag `--no-stats` to disable
- [ ] Token budget enforcement (optional)
- [ ] Documentation updates

## 7. Risks & Mitigation

| Risk | Mitigation |
|---|---|
| **Callback overhead** | Callbacks are lightweight; timing adds <1ms per event |
| **Token counting accuracy with Ollama** | Ollama may not return usage metadata; fallback to tokenizer estimation |
| **Cache bloat** | Limit stored history to 500 requests; configurable |
| **Breaking existing behavior** | Stats are additive — no changes to core agent logic |
| **Sensitive data in logs** | Only store metrics (tokens, timing), not query/response content |

## 8. Dependencies

*   **Llama Index** `CallbackManager` and `TokenCountingHandler` — already available
*   **Rich** — already used for console output
*   **No new external dependencies required**

## 9. Future Enhancements

*   **Cost estimation** — If running with paid APIs, calculate per-request cost
*   **Export to CSV/JSON** — Allow exporting stats for external analysis
*   **Real-time dashboard** — Web-based stats dashboard (future)
*   **Per-tool analytics** — Track which tools are most/least used
*   **Performance alerts** — Warn when requests exceed threshold (time/tokens)
*   **Session comparison** — Compare stats across different models/configs

## 10. Conclusion

Extending the logging system with request statistics is a **high-value, low-risk** improvement. It leverages Llama Index's existing callback infrastructure and provides immediate visibility into agent performance. The implementation is modular, configurable, and can be toggled on/off without affecting core functionality.

**Key Benefits:**
1.  **Transparency** — Users see exactly what happened behind the scenes
2.  **Debugging** — Easy to identify slow requests or token-heavy operations
3.  **Optimization** — Data-driven decisions for prompt tuning and tool selection
4.  **Cost awareness** — Track token consumption over time
5.  **Zero breaking changes** — Fully additive feature

---

*Document prepared by Torvalds AI Agent*
*Date: 2025-01*
*Repository: git@github.com:KostiantynBushko/agent-torvalds.git*
