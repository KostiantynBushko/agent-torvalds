#!/usr/bin/env python3
"""
Reproduction: agent cache request_stats are always zero.

Reproduces the exact symptom observed in ~/.cache/torvalds/agent_cache.json:
    llm_calls=0, total_tokens=0, prompt_tokens=0,
    completion_tokens=0, tool_call_count=0, tools_used=[]

No network / LLM server required (uses MockFunctionCallingLLM).

Usage:
    python investigate/agent-cache-zero-stats/repro_zero_stats.py
"""
import asyncio
import os
import sys

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

from components.stats_handler import RequestStatsHandler


async def main() -> None:
    # ---- Exactly what agent-torvalds.py:719-747 does -------------------
    stats_handler = RequestStatsHandler(request_id="repro", user_query="hello")
    callback_manager = CallbackManager([stats_handler])

    llm = MockFunctionCallingLLM()
    agent = FunctionAgent(tools=[], llm=llm, callback_manager=callback_manager)

    # agent.run(callback_manager=...) is the value that gets thrown away
    handler = agent.run("hello", callback_manager=callback_manager)
    await handler
    # --------------------------------------------------------------------

    stats = stats_handler.finalize().to_dict()

    print("--- stats produced by the CURRENT wiring ---")
    for key in (
        "llm_call_count",
        "total_prompt_tokens",
        "total_completion_tokens",
        "total_tokens",
        "tool_call_count",
        "tools_used",
    ):
        print(f"  {key:26s} = {stats[key]!r}")

    print()
    print(f"  agent has 'callback_manager' attr? {hasattr(agent, 'callback_manager')}")
    print(f"  llm.callback_manager handlers      = {llm.callback_manager.handlers}")

    assert stats["llm_call_count"] == 0, "expected the bug to reproduce (llm_call_count != 0)"
    assert stats["total_tokens"] == 0, "expected the bug to reproduce (total_tokens != 0)"

    print()
    print("OK: bug reproduced — all event-derived metrics are 0,")
    print("    exactly as persisted in ~/.cache/torvalds/agent_cache.json")


if __name__ == "__main__":
    asyncio.run(main())
