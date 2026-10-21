#!/usr/bin/env python3
"""
Live proof against a running Ollama instance.

Runs the SAME query twice — once with the broken wiring, once with the fixed
wiring — and prints the resulting metrics side by side.

Requires:
  * Ollama running on http://localhost:11434
  * a model pulled locally (override with TORVALDS_TEST_MODEL)

Usage:
    python investigate/agent-cache-zero-stats/repro_live_ollama.py
"""
import asyncio
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

try:
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.callbacks import CallbackManager
    from llama_index.llms.ollama import Ollama
except ImportError:  # pragma: no cover
    sys.path.insert(0, os.path.join(REPO, ".venv", "lib", "python3.12", "site-packages"))
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.callbacks import CallbackManager
    from llama_index.llms.ollama import Ollama

from components.stats_handler import RequestStatsHandler

MODEL = os.environ.get("TORVALDS_TEST_MODEL", "qwen2.5-coder:7b-instruct-q4_K_M")
QUERY = os.environ.get("TORVALDS_TEST_QUERY", "Say hi in three words.")


def _fmt(label: str, stats: dict) -> str:
    return (
        f"{label:38s} llm_calls={stats['llm_call_count']} "
        f"prompt={stats['total_prompt_tokens']} "
        f"completion={stats['total_completion_tokens']} "
        f"total={stats['total_tokens']} "
        f"tools={stats['tool_call_count']}"
    )


async def run_case(label: str, wire_llm: bool) -> dict:
    stats_handler = RequestStatsHandler(request_id=label, user_query=QUERY)
    callback_manager = CallbackManager([stats_handler])

    llm = Ollama(
        model=MODEL,
        request_timeout=120,
        temperature=0.0,
        callback_manager=callback_manager if wire_llm else None,
    )
    agent = FunctionAgent(tools=[], llm=llm, callback_manager=callback_manager)

    handler = agent.run(QUERY, callback_manager=callback_manager)
    try:
        await handler
    except Exception as exc:  # pragma: no cover
        print(f"  ({label} raised: {exc})")

    return stats_handler.finalize().to_dict()


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

    broken = await run_case("BROKEN (agent.run only)", wire_llm=False)
    fixed = await run_case("FIXED (llm.callback_manager)", wire_llm=True)

    print()
    print(_fmt("BROKEN (agent.run only)", broken))
    print(_fmt("FIXED (llm.callback_manager)", fixed))

    assert broken["llm_call_count"] == 0, "expected broken wiring to record 0 LLM calls"
    assert fixed["llm_call_count"] >= 1, "expected fixed wiring to record LLM calls"
    assert fixed["total_tokens"] > 0, "expected fixed wiring to record tokens"

    print()
    print("OK: live proof complete — the fix makes the metrics non-zero.")


if __name__ == "__main__":
    asyncio.run(main())
