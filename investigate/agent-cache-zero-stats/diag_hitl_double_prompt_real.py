#!/usr/bin/env python3
"""Diagnostic: double-prompt check in the REAL flow.

In the real flow the HumanLoopHandler sends AgentQuestionEvent into the
workflow context, and the EventConsumer is consuming that same workflow's
event stream. So the consumer can see its own question event and prompt a
second time.

This runs a real agent whose output contains a question, with the handler
wired to the consumer exactly like agent-torvalds.py does.
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
# A prompt whose natural answer ends with a question mark.
QUERY = os.environ.get(
    "TORVALDS_TEST_QUERY",
    "In one short sentence, what is the capital of France? End your answer with a question.",
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
    agent = FunctionAgent(tools=[tool], llm=llm, max_iterations=3)

    stats = RequestStatsHandler(request_id="dp", user_query=QUERY)
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
    orig_prompt_user = hitl._prompt_user

    async def spy_prompt_user(question, input_type, timeout, default_answer):
        handler_prompts.append(question)
        return "yes", False

    hitl._prompt_user = spy_prompt_user

    consumer_prompts = []
    orig_consumer_prompt = consumer.console_input.prompt

    async def spy_consumer_prompt(message, default="", timeout=30):
        consumer_prompts.append(message)
        return "yes"

    consumer.console_input.prompt = spy_consumer_prompt

    cm = CallbackManager([stats, hitl])
    bind_callback_manager(agent, cm)

    handler = agent.run(QUERY)
    result = await consumer.consume_events(handler, QUERY)
    await asyncio.sleep(0.5)

    out = result.get("output") if isinstance(result, dict) else result
    print()
    print("=== REAL FLOW prompt counts ===")
    print(f"  output: {str(out)[:200]!r}")
    print(f"  HumanLoopHandler._prompt_user calls : {len(handler_prompts)}")
    print(f"  EventConsumer console_input.prompt  : {len(consumer_prompts)}")
    total = len(handler_prompts) + len(consumer_prompts)
    print(f"  TOTAL user prompts                  : {total}")
    for p in handler_prompts:
        print(f"    handler  : {str(p)[:100]!r}")
    for p in consumer_prompts:
        print(f"    consumer : {str(p)[:100]!r}")
    if total > 1:
        print("  >>> DOUBLE PROMPT DETECTED <<<")
    else:
        print("  >>> single prompt (ok) <<<")


if __name__ == "__main__":
    asyncio.run(main())
