#!/usr/bin/env python3
"""Diagnostic: what does the LLM event-end payload actually look like?

Before the fix the HumanLoopHandler never received any event (the callback
manager was dead). After the fix it receives LLM event ends, so its
question detection becomes live. This inspects the payload shape to
determine whether the text is actually extractable.
"""
import asyncio
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.base import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload
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
    "In one short sentence, what is the capital of France?",
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


class SpyHandler(BaseCallbackHandler):
    """Dumps the LLM event-end payload."""

    def __init__(self):
        super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])

    def start_trace(self, trace_id=""):
        pass

    def end_trace(self, trace_id="", **kwargs):
        pass

    def on_event_start(self, event_type, payload=None, event_id="", **kwargs):
        pass

    def on_event_end(self, event_type, payload=None, event_id="", **kwargs):
        if event_type != CBEventType.LLM:
            return
        print("\n--- LLM event end ---")
        print("  payload keys:", list(payload.keys()) if payload else None)
        resp = payload.get(EventPayload.RESPONSE) if payload else None
        print("  RESPONSE type:", type(resp).__name__ if resp is not None else None)
        if resp is not None:
            print("  has .text:", hasattr(resp, "text"))
            print("  has .message:", hasattr(resp, "message"))
            print("  has .raw:", hasattr(resp, "raw"))
            txt = getattr(resp, "text", None)
            print("  .text =", repr(txt)[:200])
            msg = getattr(resp, "message", None)
            if msg is not None:
                print("  .message.content =", repr(getattr(msg, "content", None))[:200])
            raw = getattr(resp, "raw", None)
            if isinstance(raw, dict):
                print("  .raw keys:", list(raw.keys()))
        # Also show what HumanLoopHandler._extract_text would produce.
        if resp is not None:
            from components.human_loop_handler import HumanLoopHandler
            extracted = HumanLoopHandler._extract_text(resp)
            print("  _extract_text() ->", repr(extracted)[:200])
            print("  _is_question() ->", hitl_ref[0]._is_question(extracted))


hitl_ref = [None]


async def main() -> None:
    console = Console()
    llm = Ollama(model=MODEL, request_timeout=180, temperature=0.0)
    tool = FunctionTool.from_defaults(fn=add_two)
    agent = FunctionAgent(tools=[tool], llm=llm, max_iterations=3)

    stats = RequestStatsHandler(request_id="shape", user_query=QUERY)
    hitl = HumanLoopHandler(
        input_method="console",
        default_timeout=3,
        default_answer="",
        console=console,
        spinner=_NullSpinner(),
        enable_hitl=True,
    )
    spy = SpyHandler()

    consumer = EventConsumer(
        spinner_controller=_NullSpinner(),
        state_handler=StateHandler(),
        console=console,
        stats_handler=stats,
    )
    hitl.event_consumer = consumer
    hitl_ref[0] = hitl

    cm = CallbackManager([stats, hitl, spy])
    bind_callback_manager(agent, cm)

    handler = agent.run(QUERY)
    await consumer.consume_events(handler, QUERY)
    await asyncio.sleep(0.3)


if __name__ == "__main__":
    asyncio.run(main())
