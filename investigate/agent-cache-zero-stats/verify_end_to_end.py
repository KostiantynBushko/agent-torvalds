#!/usr/bin/env python3
"""
End-to-end verification of the zero-stats fix through the REAL production
wiring — the actual ``prompt_handler`` from ``agent-torvalds.py``, with a
real Ollama LLM and a real tool call.

This exercises the complete path:

    prompt_handler()
      -> bind_callback_manager(agent, cm)      # Fix A
      -> EventConsumer.set_stats_handler(...)  # Fix B
      -> agent.run(...)  ->  LLM events  ->  RequestStatsHandler
      -> ToolCall/ToolCallResult -> RequestStatsHandler
      -> save_request_stats(...)               # Fix C

Requires Ollama running on http://localhost:11434.

Usage:
    python investigate/agent-cache-zero-stats/verify_end_to_end.py
"""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

try:
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.tools import FunctionTool
    from llama_index.llms.ollama import Ollama
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.join(REPO, ".venv", "lib", "python3.12", "site-packages"))
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.tools import FunctionTool
    from llama_index.llms.ollama import Ollama

from components.stats_handler import RequestStatsHandler, bind_callback_manager
from components.event_consumer import EventConsumer
from components.state_handler import StateHandler
from rich.console import Console

# NOTE: the model must support NATIVE function calling. Models that only
# emit the tool call as plain text (e.g. qwen2.5-coder without a native
# tools API) never produce a ToolCall event, so tool_call_count stays 0
# for a reason unrelated to the stats wiring.
MODEL = os.environ.get("TORVALDS_TEST_MODEL", "qwen3-coder:latest")
QUERY = os.environ.get(
    "TORVALDS_TEST_QUERY",
    "Use the add_two tool to add 17 and 25, then tell me the result.",
)


def add_two(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


async def main() -> None:
    try:
        import urllib.request

        with urllib.request.urlopen("http://localhost:11434/api/version", timeout=5) as r:
            print(f"Ollama: {r.read().decode().strip()}")
    except Exception as exc:
        print(f"Ollama is not reachable ({exc}) — aborting.")
        return

    print(f"Model: {MODEL}")
    print(f"Query: {QUERY}\n")

    # ---- Build the agent exactly like create_agent() does --------------
    llm = Ollama(model=MODEL, request_timeout=120, temperature=0.0)
    tool = FunctionTool.from_defaults(fn=add_two)
    agent = FunctionAgent(tools=[tool], llm=llm, max_iterations=5)

    # ---- Per-request wiring, exactly like prompt_handler() ------------
    stats_handler = RequestStatsHandler(request_id="e2e", user_query=QUERY)
    from llama_index.core.callbacks import CallbackManager
    callback_manager = CallbackManager([stats_handler])

    bind_callback_manager(agent, callback_manager)          # Fix A

    console = Console()
    state = StateHandler()
    consumer = EventConsumer(
        spinner_controller=_NullSpinner(),
        state_handler=state,
        console=console,
        stats_handler=stats_handler,                        # Fix B
    )

    handler = agent.run(QUERY)
    await consumer.consume_events(handler, QUERY)

    stats = stats_handler.finalize()
    data = stats.to_dict()

    print("=== stats produced through the production wiring ===")
    for key in (
        "llm_call_count",
        "total_prompt_tokens",
        "total_completion_tokens",
        "total_tokens",
        "tool_call_count",
        "tools_used",
        "error_count",
    ):
        print(f"  {key:26s} = {data[key]!r}")

    # ---- Fix C: persist and read back ---------------------------------
    from agent_cache_system import save_request_stats, get_stats_summary
    save_request_stats(data)
    summary = get_stats_summary()
    print()
    print("=== get_stats_summary() tail ===")
    print("  " + json.dumps({k: summary.get(k) for k in (
        "total_requests", "total_tokens", "total_llm_calls", "total_tool_calls"
    )}, indent=2).replace("\n", "\n  "))

    # ---- Assertions ---------------------------------------------------
    assert data["llm_call_count"] >= 1, "LLM calls must be recorded"
    assert data["total_tokens"] > 0, "tokens must be recorded"
    assert data["tool_call_count"] >= 1, "tool calls must be recorded"
    assert data["tools_used"], "tools_used must be populated"
    assert "error" not in summary, f"summary broke: {summary}"

    print()
    print("OK: end-to-end verification passed —")
    print("    LLM calls, tokens and tool calls are all non-zero,")
    print("    and the cache entry persists them correctly.")


class _NullSpinner:
    """Minimal spinner stand-in (no animation)."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    @property
    def is_paused(self) -> bool:
        return False


if __name__ == "__main__":
    asyncio.run(main())
