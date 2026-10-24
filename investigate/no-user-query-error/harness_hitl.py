"""
Harness for the HITL (Human-in-the-Loop) path.

HITL is enabled by default (``TORVALDS_HITL_ENABLED`` defaults to true) and
``components/hitl_agent.HITLFunctionAgent.parse_agent_output`` overrides the
base implementation.  When the agent's final answer looks like a question the
step waits for a human, the answer is appended to the scratchpad as a
``user`` message and the agent continues.

This harness drives the real agent with a mock LLM that:
  * asks a question  -> the HITL round-trip is exercised
  * then answers     -> the run finishes

and records every message list the agent sends, so we can see whether the
user query survives the round-trip.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.llms.ollama.base import Ollama

from components.hitl_agent import HITLFunctionAgent
from components.hitl_events import AgentAnswerEvent

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from harness_agent_flow import has_user_query, template_would_fail  # noqa: E402


class ScriptedOllama(Ollama):
    """Mock LLM that follows a script of answers and records every request."""

    _requests: List[Dict[str, Any]] = PrivateAttr(default_factory=list)
    _script: List[Dict[str, Any]] = PrivateAttr(default_factory=list)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("model", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
        kwargs.setdefault("base_url", "http://localhost:11434")
        super().__init__(*args, **kwargs)
        self._requests = []
        self._script = []

    @property
    def requests(self):
        return self._requests

    def set_script(self, script):
        self._script = list(script)

    def _next(self, messages):
        self._requests.append({"messages": list(messages)})
        if not self._script:
            return ChatResponse(
                message=ChatMessage(role="assistant", content="All done.")
            )
        step = self._script.pop(0)
        return ChatResponse(
            message=ChatMessage(role="assistant", content=step.get("content", ""))
        )

    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs):
        async def gen():
            yield self._next(list(messages))

        return gen()

    async def achat(self, messages: Sequence[ChatMessage], **kwargs):
        return self._next(list(messages))


def read_file(path: str) -> str:
    return "\n".join(f"row {i}: value" for i in range(50))


async def main() -> None:
    from llama_index.core.memory import ChatMemoryBuffer
    from llama_index.core.tools import FunctionTool

    tools = [
        FunctionTool.from_defaults(
            fn=read_file,
            name="read_file",
            description="Read a file from the project folder.",
        )
    ]

    llm = ScriptedOllama()
    memory = ChatMemoryBuffer.from_defaults(token_limit=5000)

    agent = HITLFunctionAgent(
        tools=tools,
        llm=llm,
        max_iterations=20,
        memory=memory,
        system_prompt="You are a helpful assistant.",
    )
    agent.hitl_enabled = True
    agent.hitl_default_timeout = 5
    agent.hitl_default_answer = "no"

    # The agent asks a question -> HITL round-trip -> then it answers.
    llm.set_script(
        [
            {"content": "I found two candidate columns. Should I use column D?"},
            {"content": "Done, merged."},
        ]
    )

    memory.put(ChatMessage(content="CONTEXT: ### Registered Projects\n- mytlushko"))

    request = (
        "in project folder: take a file A = OV_2026_10.xlsx file B = shtab.xlsx "
        "merge entities from column 'D' in file A and column C in file B"
    )

    handler = agent.run(request, memory=memory, max_iterations=20)

    # Auto-answer the HITL question as soon as it is asked.
    async def answer_later() -> None:
        await asyncio.sleep(1.0)
        try:
            handler.write_event_to_stream(
                AgentAnswerEvent(question_id="*", answer="yes, use column D")
            )
        except Exception as exc:  # noqa: BLE001
            print(f"    (could not answer: {exc})")

    task = asyncio.create_task(answer_later())
    try:
        result = await handler
        print(f"agent finished: {str(result)[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"!! agent raised {type(exc).__name__}: {exc}")
    finally:
        task.cancel()

    print("\nrecorded LLM calls:")
    for i, req in enumerate(llm.requests):
        msgs = req["messages"]
        roles = [m.role for m in msgs]
        fails = template_would_fail(msgs)
        flag = "   <== TEMPLATE WOULD FAIL" if fails else ""
        print(f"  call {i}: {len(msgs)} msgs roles={roles}{flag}")
        if fails:
            for m in msgs:
                print(f"        {m.role}: {(m.content or '')[:100]!r}")


if __name__ == "__main__":
    asyncio.run(main())
