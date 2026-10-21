#!/usr/bin/env python3
"""Diagnostic: what workflow events actually reach the EventConsumer?"""
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

MODEL = os.environ.get("TORVALDS_TEST_MODEL", "qwen2.5-coder:7b-instruct-q4_K_M")
QUERY = os.environ.get(
    "TORVALDS_TEST_QUERY",
    "Use the add_two tool to add 17 and 25, then tell me the result.",
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
    llm = Ollama(model=MODEL, request_timeout=120, temperature=0.0)
    tool = FunctionTool.from_defaults(fn=add_two)
    agent = FunctionAgent(tools=[tool], llm=llm, max_iterations=5)

    stats = RequestStatsHandler(request_id="diag", user_query=QUERY)
    cm = CallbackManager([stats])
    bind_callback_manager(agent, cm)

    console = Console()
    consumer = EventConsumer(
        spinner_controller=_NullSpinner(),
        state_handler=StateHandler(),
        console=console,
        stats_handler=stats,
    )

    # Wrap the consumer's dispatch so we can SEE every event that arrives.
    seen = []
    orig = consumer._handle_event

    async def spy(event):
        seen.append(type(event).__name__)
        return await orig(event)

    consumer._handle_event = spy

    handler = agent.run(QUERY)
    result = await consumer.consume_events(handler, QUERY)

    print("=== event types seen by EventConsumer ===")
    for name in seen:
        print("   ", name)
    print()
    print("=== result ===")
    print("  output:", str(result.get("output"))[:400] if isinstance(result, dict) else str(result)[:400])
    print()
    print("=== stats ===")
    d = stats.finalize().to_dict()
    for k in ("llm_call_count", "total_tokens", "tool_call_count", "tools_used"):
        print(f"  {k:20s} = {d[k]!r}")


if __name__ == "__main__":
    asyncio.run(main())
