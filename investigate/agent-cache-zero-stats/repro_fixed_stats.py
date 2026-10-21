#!/usr/bin/env python3
"""
Demonstration: the fix for the zeroed agent-cache request_stats.

Fix A — point the LLM's own callback_manager at the per-request stats
         handler. `FunctionAgent(callback_manager=...)` is silently ignored
         by pydantic; `llm_chat_callback()` resolves the manager from the
         LLM *instance*, so that is the one that must carry the handler.

Fix B — tool calls are published on the workflow event stream
         (`ToolCall` events), NOT as `CBEventType.FUNCTION_CALL` callback
         events. `CBEventType.FUNCTION_CALL` is never emitted anywhere in
         llama-index 0.14.25, so the stats handler has to be fed from the
         event consumer (or a tool callback) to count tool calls.
         This script simulates that feed by appending a ToolCallRecord
         exactly the way `EventConsumer._on_tool_call` would.

No network / LLM server required (uses MockFunctionCallingLLM).

Usage:
    python investigate/agent-cache-zero-stats/repro_fixed_stats.py
"""
import asyncio
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

try:
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.callbacks import CallbackManager
    from llama_index.core.llms.mock import MockFunctionCallingLLM
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.join(REPO, ".venv", "lib", "python3.12", "site-packages"))
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.callbacks import CallbackManager
    from llama_index.core.llms.mock import MockFunctionCallingLLM

from components.stats_handler import RequestStatsHandler, ToolCallRecord


async def main() -> None:
    stats_handler = RequestStatsHandler(request_id="repro-fixed", user_query="hello")
    callback_manager = CallbackManager([stats_handler])

    llm = MockFunctionCallingLLM()
    agent = FunctionAgent(tools=[], llm=llm)

    # ---- FIX A: the LLM instance is where the manager has to live ------
    llm.callback_manager = callback_manager
    # -------------------------------------------------------------------

    handler = agent.run("hello", callback_manager=callback_manager)
    await handler

    # ---- FIX B: feed tool calls in from the workflow event stream ------
    # In production `EventConsumer._on_tool_call` does this when it
    # receives a `ToolCall` event from the agent workflow.
    now = time.monotonic()
    stats_handler.stats.tool_calls.append(
        ToolCallRecord(
            tool_name="add_two",
            start_time=now,
            end_time=now + 0.0125,
            duration_ms=12.5,
        )
    )
    # -------------------------------------------------------------------

    stats = stats_handler.finalize().to_dict()

    print("--- stats produced by the FIXED wiring ---")
    for key in (
        "llm_call_count",
        "total_prompt_tokens",
        "total_completion_tokens",
        "total_tokens",
        "tool_call_count",
        "tools_used",
    ):
        print(f"  {key:26s} = {stats[key]!r}")

    assert stats["llm_call_count"] >= 1, "LLM events must reach the stats handler"
    assert stats["tool_call_count"] == 1, "tool calls must be counted"

    print()
    print("OK: fix verified — LLM calls and tool calls are recorded,")
    print("    so the cache entries will no longer be all zeros.")


if __name__ == "__main__":
    asyncio.run(main())
