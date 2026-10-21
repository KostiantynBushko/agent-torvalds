#!/usr/bin/env python3
"""Diagnostic: HITL revival — does an output containing '?' now trigger a prompt?

The HumanLoopHandler shares the callback manager with the stats handler, so
binding the manager to the LLM revives HITL detection as a side effect.

This checks whether an ordinary answer containing a question mark causes the
agent to block waiting for user input.
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
from components.human_loop_handler import HumanLoopHandler

MODEL = os.environ.get("TORVALDS_TEST_MODEL", "qwen3-coder:latest")
QUERY = os.environ.get(
    "TORVALDS_TEST_QUERY",
    "What is 2+2? Answer with just the number.",
)


def add_two(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return a + b


class _NullSpinner:
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    @property
    def is_paused(self): return False


async def main() -> None:
    console = Console()
    llm = Ollama(model=MODEL, request_timeout=180, temperature=0.0)
    tool = FunctionTool.from_defaults(fn=add_two)
    agent = FunctionAgent(tools=[tool], llm=llm, max_iterations=5)

    stats = RequestStatsHandler(request_id="hitl2", user_query=QUERY)
    hitl = HumanLoopHandler(
        input_method="console",
        default_timeout=2,
        default_answer="",
        console=console,
        spinner=_NullSpinner(),
        enable_hitl=True,
    )

    prompts = []
    orig_handle = hitl._handle_question

    async def spy(question, question_id, timeout, default_answer):
        prompts.append(question[:160])
        return await orig_handle(question, question_id, timeout, default_answer)

    hitl._handle_question = spy

    cm = CallbackManager([stats, hitl])
    bind_callback_manager(agent, cm)

    consumer = EventConsumer(
        spinner_controller=_NullSpinner(),
        state_handler=StateHandler(),
        console=console,
        stats_handler=stats,
    )
    hitl.event_consumer = consumer

    handler = agent.run(QUERY)
    result = await consumer.consume_events(handler, QUERY)
    await asyncio.sleep(0.3)

    print()
    print("=== HITL outcome ===")
    print(f"  prompts triggered: {len(prompts)}")
    for p in prompts:
        print(f"    -> {p!r}")
    out = result.get("output") if isinstance(result, dict) else result
    print(f"  output: {str(out)[:200]!r}")
    print()
    print("=== stats ===")
    d = stats.finalize().to_dict()
    for k in ("llm_call_count", "total_tokens", "tool_call_count", "tools_used"):
        print(f"  {k:20s} = {d[k]!r}")


if __name__ == "__main__":
    asyncio.run(main())
