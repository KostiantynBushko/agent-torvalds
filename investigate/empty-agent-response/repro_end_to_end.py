#!/usr/bin/env python3
"""
Reproduction: a run that *has* an answer ends with an empty answer.

The reported run looks like this:

    LLM call #2 finished — prompt=7494, completion=1, total=7495 tokens
    EventConsumer._on_agent_stream: delta=''
    EventConsumer._on_agent_output: assistant: (empty)
    EventConsumer._on_stop_event: tool result: execute_shell_command:
        {'stdout': 'List of relations ...', 'returncode': 0, 'success': True}
    ...
    ────────── Agent Response ──────────
    ─────────────────────────────────────   <- nothing under the rule

The script below reproduces the whole thing with a mock LLM, so it runs in
seconds and needs no model:

* turn 1 — the model calls ``execute_shell_command`` (as in the report);
* turn 2 — the model answers with a **thinking block and no text**, which is
  what the log shows (``assistant: (empty)``).

It then runs the *real* code paths: the real ``EventConsumer``, the real
``prompt_handler`` extraction and the real rendering, and shows that the
Agent Response section comes out empty while the tool result is sitting
right there in the output.

Usage:
    python repro_end_to_end.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from typing import Any, List, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llama_index.core.agent.workflow import FunctionAgent  # noqa: E402
from llama_index.core.base.llms.types import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
)
from llama_index.core.llms.callbacks import llm_chat_callback  # noqa: E402
from llama_index.core.llms.mock import MockFunctionCallingLLM  # noqa: E402
from llama_index.core.tools import FunctionTool  # noqa: E402
from pydantic import Field  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.markdown import Markdown  # noqa: E402

from components.agent_answer import extract_answer  # noqa: E402
from components.event_consumer import EventConsumer  # noqa: E402
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

#: What the tool really answered in the reported run.
TOOL_RESULT = (
    "List of relations\n"
    " Schema |       Name       |   Type   |  Owner   | Persistence | "
    "Access method |    Size    | Description \n"
    "--------+------------------+----------+----------+-------------+"
    "---------------+------------+-------------\n"
    " public | chat_sessions    | table    | postgres | permanent   | heap"
    "          | 16 kB      | \n"
    " public | chatstore        | table    | llama    | permanent   | heap"
    "          | 138 MB     | \n"
    " public | chatstore_id_seq | sequence | llama    | permanent   |       "
    "        | 8192 bytes | \n"
    " public | users            | table    | postgres | permanent   | heap"
    "          | 16 kB      | \n"
    "(4 rows)"
)


def execute_shell_command(command: str, timeout: int = 10) -> str:
    """Return the output of a shell command (a stand-in for the real tool)."""
    return TOOL_RESULT


class SilentLLM(MockFunctionCallingLLM):
    """An LLM that behaves like the one in the reported run.

    Turn 1 calls the tool.  Turn 2 — the turn that ends the run — answers
    with a **thinking block and no text at all**, which is what the log of
    the reported run shows.
    """

    call_count: int = Field(default=0)
    thinking_text: str = Field(
        default="The user wants the schema of the database."
    )

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.call_count += 1

        if self.call_count == 1:
            # The tool call, as in the report.
            # The Ollama adapter puts the tool call in a ``ToolCallBlock``;
            # the mock mirrors that, so the framework reads it the same way.
            call = ChatMessage(
                role="assistant",
                blocks=[
                    ThinkingBlock(content=self.thinking_text),
                    ToolCallBlock(
                        tool_name="execute_shell_command",
                        tool_kwargs={
                            "command": "psql -d llama_index_db -c '\\d+'",
                            "timeout": 10,
                        },
                        tool_call_id="call-1",
                    ),
                    TextBlock(text=""),
                ],
            )
            async def gen_tool():
                yield ChatResponse(
                    message=call,
                    delta="",
                    raw={"message": {"role": "assistant", "content": ""}},
                )

            return gen_tool()

        # The final turn: a thinking block, and **no text**.
        async def gen_silent():
            yield ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    blocks=[ThinkingBlock(content=self.thinking_text)],
                ),
                delta="",
                raw={"message": {"role": "assistant", "content": ""}},
            )

        return gen_silent()

    @llm_chat_callback()
    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        raise NotImplementedError("the agent streams")


async def main() -> int:
    console = Console(record=True, width=100)
    tool = FunctionTool.from_defaults(
        fn=execute_shell_command, name="execute_shell_command"
    )
    llm = SilentLLM()
    agent = FunctionAgent(tools=[tool], llm=llm)

    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
    )

    handler = agent.run("show me the schema of every table in llama_index_db")
    result = await consumer.consume_events(handler, "show me the schema")

    # ---- the extraction of agent-torvalds.py -------------------------
    response_text = (
        result.get("output") if isinstance(result, dict) else str(result)
    )

    print("=" * 78)
    print("The run finished.  What the operator sees:")
    print("=" * 78)
    console.rule("[blue]Agent Response[/blue]")
    console.print(response_text)
    console.rule()
    print()

    print("=" * 78)
    print("What is actually in the result")
    print("=" * 78)
    print(f"  type(result)                : {type(result).__name__}")
    print(f"  result.response.content     : {result.response.content!r}")
    print(f"  result.response.blocks      : {result.response.blocks}")
    print(f"  len(result.tool_calls)      : {len(result.tool_calls)}")
    for call in result.tool_calls:
        content = getattr(getattr(call, "tool_output", None), "content", "")
        print(f"    - {call.tool_name}: {str(content)[:60]!r}...")
    print()
    print(f"  what prompt_handler returns : {response_text!r}")
    print(f"  is the Agent Response empty?: {not response_text.strip()}")
    print()
    print("  -> the answer was in the run the whole time; the extraction")
    print("     never looks at it.")
    print()

    # ---- the extraction of agent-torvalds.py, after the fix ---------
    fixed_text = extract_answer(result)

    print("=" * 78)
    print("The same run, read through components/agent_answer.py")
    print("=" * 78)
    console.rule("[blue]Agent Response[/blue]")
    console.print(Markdown(fixed_text))
    console.rule()
    print()
    print(f"  is the Agent Response empty?: {not fixed_text.strip()}")
    print("  -> the section is never empty: the operator is told that the")
    print("     model wrote nothing, and shown what the run found.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
