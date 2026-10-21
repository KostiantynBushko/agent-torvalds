#!/usr/bin/env python3
"""Diagnostic: concurrent tool calls to the SAME tool.

The workflow runs one ``call_tool`` step per tool call, concurrently. When a
model requests the same tool twice in one turn, both calls are in flight at
the same time — which is exactly the case that mis-pairs timings if the
pending starts are keyed by tool name alone.
"""
import asyncio
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.callbacks import CallbackManager
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama import Ollama
from rich.console import Console

from components.stats_handler import RequestStatsHandler, bind_callback_manager
from components.event_consumer import EventConsumer
from components.state_handler import StateHandler

MODEL = os.environ.get("TORVALDS_TEST_MODEL", "qwen3-coder:latest")
QUERY = os.environ.get(
    "TORVALDS_TEST_QUERY",
    "Call the slow_add tool TWICE in the same turn: first with a=1,b=2 "
    "and then with a=10,b=20. Then report both results.",
)


def slow_add(a: int, b: int) -> int:
    """Add two integers (deliberately slow so the calls overlap)."""
    import time
    time.sleep(0.4)
    return a + b


class _NullSpinner:
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    @property
    def is_paused(self): return False


async def main() -> None:
    llm = Ollama(model=MODEL, request_timeout=240, temperature=0.0)
    tool = FunctionTool.from_defaults(fn=slow_add)
    agent = FunctionAgent(tools=[tool], llm=llm, max_iterations=3)

    stats = RequestStatsHandler(request_id="conc", user_query=QUERY)
    cm = CallbackManager([stats])
    bind_callback_manager(agent, cm)

    consumer = EventConsumer(
        spinner_controller=_NullSpinner(),
        state_handler=StateHandler(),
        console=Console(),
        stats_handler=stats,
    )

    handler = agent.run(QUERY)
    await consumer.consume_events(handler, QUERY)

    d = stats.finalize().to_dict()
    print()
    print("=== concurrent same-tool stats ===")
    for k in ("llm_call_count", "total_tokens", "tool_call_count", "tools_used"):
        print(f"  {k:20s} = {d[k]!r}")
    print()
    print("  per-call durations (ms):",
          [round(t.duration_ms) for t in stats.stats.tool_calls])
    print("  pending starts left     :", stats._pending_tool_starts)
    if len(stats.stats.tool_calls) != d["tool_call_count"]:
        print("  >>> MISMATCH <<<")
    else:
        print("  >>> counts consistent <<<")


if __name__ == "__main__":
    asyncio.run(main())
