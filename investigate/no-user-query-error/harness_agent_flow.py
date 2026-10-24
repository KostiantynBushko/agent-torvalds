"""
Harness: reproduce "No user query found in messages." against the REAL agent
code path, with a recording mock LLM.

Nothing here talks to a model.  The mock LLM records every message list the
agent sends, and answers with a scripted sequence of tool calls / text.  The
real ``HITLFunctionAgent``, the real ``ChatMemoryBuffer`` and the real
LlamaIndex workflow machinery do the rest, so whatever we observe here is
exactly what the agent would put on the wire.

The check that mirrors the Ollama Jinja template is ``has_user_query()``:

    scan messages in reverse; the first message with role == "user" whose
    content is not wrapped in <tool_response>...</tool_response> wins.
    If there is none -> the server raises
    "No user query found in messages.".

Usage:
    python investigate/no-user-query-error/harness_agent_flow.py [scenario]
"""

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.llms.ollama.base import Ollama
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool

from components.hitl_agent import HITLFunctionAgent


# ---------------------------------------------------------------------------
# The exact predicate from the model's Jinja template
# ---------------------------------------------------------------------------

def has_user_query(messages: Sequence[ChatMessage]) -> bool:
    """Mirror of the template's ``multi_step_tool`` scan."""
    for message in reversed(list(messages)):
        if message.role != "user":
            continue
        content = (message.content or "").strip()
        if not (
            content.startswith("<tool_response>")
            and content.endswith("</tool_response>")
        ):
            return True
    return False


def template_would_fail(messages: Sequence[ChatMessage]) -> bool:
    """True when the Ollama template raises the target exception."""
    if not messages:
        return True  # "No messages provided."
    return not has_user_query(messages)


# ---------------------------------------------------------------------------
# Recording mock LLM
# ---------------------------------------------------------------------------

class RecordingOllama(Ollama):
    """An Ollama LLM that never calls the server but records every request."""

    _requests: List[Dict[str, Any]] = PrivateAttr(default_factory=list)
    _script: List[Dict[str, Any]] = PrivateAttr(default_factory=list)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("model", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
        kwargs.setdefault("base_url", "http://localhost:11434")
        super().__init__(*args, **kwargs)
        self._requests = []
        self._script = []

    @property
    def requests(self) -> List[Dict[str, Any]]:
        return self._requests

    def set_script(self, script: List[Dict[str, Any]]) -> None:
        self._script = list(script)

    def _next(self, messages: List[ChatMessage]) -> ChatResponse:
        self._requests.append(
            {
                "messages": list(messages),
                "ollama_messages": self._convert_to_ollama_messages(messages),
            }
        )
        if not self._script:
            return ChatResponse(
                message=ChatMessage(role="assistant", content="done")
            )
        step = self._script.pop(0)
        if step["type"] == "tool":
            from llama_index.core.base.llms.types import ToolCallBlock

            block = ToolCallBlock(
                tool_name=step["name"],
                tool_kwargs=step.get("args", {}),
                tool_call_id=step.get("id"),
            )
            # NOTE: do not pass ``content`` here — ChatMessage.__init__
            # overwrites ``blocks`` with a TextBlock when content is given.
            return ChatResponse(
                message=ChatMessage(role="assistant", blocks=[block])
            )
        return ChatResponse(
            message=ChatMessage(role="assistant", content=step.get("content", ""))
        )

    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        # Must be a coroutine that RETURNS an async generator: the caller does
        # ``await self.astream_chat(...)`` and then iterates the result.
        async def gen():
            yield self._next(list(messages))

        return gen()

    async def achat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        return self._next(list(messages))

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        return self._next(list(messages))

    def stream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        def gen():
            yield self._next(list(messages))

        return gen()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

BIG_ROW = "Митлушко Андрій Романович | 12,5 | 3400,00 | ХАРКІВ | 2026-10-01"


def read_file(path: str) -> str:
    """Simulate reading a spreadsheet: returns a large payload."""
    return "\n".join(f"{i}: {BIG_ROW}" for i in range(400))


def write_file(path: str, content: str) -> str:
    """Simulate writing a spreadsheet."""
    return f"wrote {len(content)} chars to {path}"


TOOLS = [
    FunctionTool.from_defaults(
        fn=read_file,
        name="read_file",
        description="Read a file from the project folder and return its content.",
    ),
    FunctionTool.from_defaults(
        fn=write_file,
        name="write_file",
        description="Write a file into the project folder.",
    ),
]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

REQUEST = (
    "in project folder: take a file A = OV_2026_10.xlsx file B = shtab.xlsx "
    "for person 'Митлушко Андрій Романович' merge entities from column 'D' in "
    "file A and column C in file B, the result must be in copy of file B in "
    "the project directory, the source of truth is file A."
)

CONTEXT = (
    "Project: mytlushko\nFiles:\n- OV_2026_10.xlsx\n- shtab.xlsx\n"
)


async def run_scenario(
    name: str,
    script: List[Dict[str, Any]],
    turns: List[str],
    token_limit: int = 5000,
    hitl: bool = False,
) -> Dict[str, Any]:
    print("=" * 78)
    print(f"SCENARIO: {name}   (token_limit={token_limit}, hitl={hitl})")
    print("=" * 78)

    llm = RecordingOllama(request_timeout=5.0)
    memory = ChatMemoryBuffer.from_defaults(token_limit=token_limit)

    agent = HITLFunctionAgent(
        tools=TOOLS,
        llm=llm,
        max_iterations=50,
        memory=memory,
        system_prompt="You are a helpful assistant.",
    )
    agent.hitl_enabled = hitl
    agent.hitl_default_timeout = 0
    agent.hitl_default_answer = "no"

    for turn_index, turn in enumerate(turns):
        llm.set_script(script)
        print(f"\n--- turn {turn_index + 1}: {turn[:70]!r}")

        # Mirror prompt_handler(): project context is injected as a USER message
        memory.put(ChatMessage(content=f"CONTEXT: {CONTEXT}"))

        handler = agent.run(turn, memory=memory, max_iterations=50)
        try:
            await handler
        except Exception as exc:  # noqa: BLE001
            import traceback

            print(f"    !! agent raised {type(exc).__name__}: {exc}")
            traceback.print_exc()

        # Replay what the LLM actually saw
        for i, req in enumerate(llm.requests):
            msgs = req["messages"]
            fails = template_would_fail(msgs)
            roles = [m.role for m in msgs]
            flag = "  <== TEMPLATE WOULD FAIL" if fails else ""
            print(
                f"    llm call {i}: {len(msgs)} msgs roles={roles}{flag}"
            )
            if fails:
                for m in msgs:
                    print(f"        - {m.role}: {(m.content or '')[:90]!r}")
        llm.requests.clear()

    print()
    return {"name": name}


SCRIPTS = {
    # read file A, read file B, write result, then answer
    "excel": [
        {"type": "tool", "name": "read_file", "args": {"path": "OV_2026_10.xlsx"}},
        {"type": "tool", "name": "read_file", "args": {"path": "shtab.xlsx"}},
        {"type": "tool", "name": "write_file", "args": {"path": "shtab_merged.xlsx", "content": "x"}},
        {"type": "text", "content": "Done, merged into shtab_merged.xlsx."},
    ],
}


async def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("all", "single"):
        await run_scenario(
            "single turn, several large tool calls",
            SCRIPTS["excel"],
            [REQUEST],
        )

    if which in ("all", "two-turns"):
        await run_scenario(
            "two turns in the same session (memory carries tool messages)",
            SCRIPTS["excel"],
            [REQUEST, "now also do the same for shtab2.xlsx"],
        )

    if which in ("all", "small-limit"):
        await run_scenario(
            "single turn but with a small token limit",
            SCRIPTS["excel"],
            [REQUEST],
            token_limit=400,
        )


if __name__ == "__main__":
    asyncio.run(main())
