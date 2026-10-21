#!/usr/bin/env python3
"""Diagnostic: real-flow HITL double prompt (forced question detection).

With the callback manager now bound to the LLM, the HumanLoopHandler starts
receiving LLM events. For providers whose raw payload exposes the text
(``raw["content"]``), its question detection becomes live.

When it fires, the handler prompts the user AND sends AgentQuestionEvent
into the workflow, which the EventConsumer also consumes -> a second prompt.

This forces the text to be extractable so the HITL path actually runs.
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

import components.human_loop_handler as hlh
from components.stats_handler import RequestStatsHandler, bind_callback_manager
from components.event_consumer import EventConsumer
from components.state_handler import StateHandler
from components.human_loop_handler import HumanLoopHandler

MODEL = os.environ.get("TORVALDS_TEST_MODEL", "qwen3-coder:latest")
QUERY = os.environ.get(
    "TORVALDS_TEST_QUERY",
    "Ask me a question about the weather, then wait for my answer.",
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


# Force the text to be extractable so the HITL detection path runs.
def _forced_extract_text(obj):
    if isinstance(obj, str):
        return obj
    msg = getattr(obj, "message", None)
    if msg is not None and getattr(msg, "content", None):
        return str(msg.content)
    return hlh.HumanLoopHandler._extract_text(obj)


hlh.HumanLoopHandler._extract_text = staticmethod(_forced_extract_text)


async def main() -> None:
    console = Console()
    llm = Ollama(model=MODEL, request_timeout=180, temperature=0.0)
    tool = FunctionTool.from_defaults(fn=add_two)
    agent = FunctionAgent(tools=[tool], llm=llm, max_iterations=3)

    stats = RequestStatsHandler(request_id="dp2", user_query=QUERY)
    hitl = HumanLoopHandler(
        input_method="console",
        default_timeout=3,
        default_answer="",
        console=console,
        spinner=_NullSpinner(),
        enable_hitl=True,
    )

    consumer = EventConsumer(
        spinner_controller=_NullSpinner(),
        state_handler=StateHandler(),
        console=console,
        stats_handler=stats,
    )
    hitl.event_consumer = consumer

    handler_prompts = []

    async def spy_prompt_user(question, input_type, timeout, default_answer):
        handler_prompts.append(("handler", question))
        return "yes", False

    hitl._prompt_user = spy_prompt_user

    consumer_prompts = []

    async def spy_consumer_prompt(message, default="", timeout=30):
        consumer_prompts.append(("consumer", message))
        return "yes"

    consumer.console_input.prompt = spy_consumer_prompt

    cm = CallbackManager([stats, hitl])
    bind_callback_manager(agent, cm)

    handler = agent.run(QUERY)
    result = await consumer.consume_events(handler, QUERY)
    await asyncio.sleep(0.6)

    out = result.get("output") if isinstance(result, dict) else result
    print()
    print("=== REAL FLOW prompt counts (forced extraction) ===")
    print(f"  output: {str(out)[:200]!r}")
    print(f"  handler prompts  : {len(handler_prompts)}")
    print(f"  consumer prompts : {len(consumer_prompts)}")
    total = len(handler_prompts) + len(consumer_prompts)
    print(f"  TOTAL            : {total}")
    for src, p in handler_prompts:
        print(f"    {src:9s}: {str(p)[:90]!r}")
    for src, p in consumer_prompts:
        print(f"    {src:9s}: {str(p)[:90]!r}")
    if total > 1:
        print("  >>> DOUBLE PROMPT DETECTED <<<")
    else:
        print("  >>> single prompt (ok) <<<")


if __name__ == "__main__":
    asyncio.run(main())
