#!/usr/bin/env python3
"""
Probe: how a run that *has* an answer ends up with an empty answer.

The reported run is not a run without an answer.  The log shows that the
tool returned the schema of the database:

    EventConsumer._on_stop_event: tool result: execute_shell_command:
    {'stdout': 'List of relations\\n Schema | Name | Type | ...', 'returncode': 0,
    'success': True}

and that the run then ended with an empty *Agent Response* section.

This probe shows where the answer is lost, without a model: it builds the
very objects the workflow produces and runs them through the very code
paths that render the answer.

The chain under test:

1. ``FunctionAgent.take_step`` returns ``AgentOutput(response=<ChatMessage>)``.
2. ``prompt_handler`` turns the workflow result into the text that is
   printed: ``result.get("output")`` for a dict, ``str(result)`` otherwise.
3. ``AgentOutput.__str__`` returns ``self.response.content or ""``.
4. ``ChatMessage.content`` is the text of the **TextBlocks** only.

So a message that carries a *thinking* block and no text block — or a
message that carries nothing at all — renders as the empty string, and the
Agent Response section is empty even though the run has a tool result to
show.

Usage:
    python probe_response_extraction.py
"""
from __future__ import annotations

import pathlib
import sys

from llama_index.core.agent.workflow import AgentOutput
from llama_index.core.base.llms.types import (
    ChatMessage,
    MessageRole,
    TextBlock,
    ThinkingBlock,
)
from llama_index.core.agent.workflow import ToolCallResult
from llama_index.core.tools import ToolOutput

#: The repository root, so that ``components`` can be imported.
ROOT = pathlib.Path(__file__).resolve()
for _ in range(6):
    if (ROOT / "components" / "chat_message.py").exists():
        break
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from components.chat_message import to_output_string  # noqa: E402

#: What the tool really returned in the reported run.
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


def build_output(response: ChatMessage) -> AgentOutput:
    """Return the ``AgentOutput`` the workflow would produce.

    The tool result is attached, exactly as ``FunctionAgent.take_step`` and
    ``handle_tool_call_results`` attach it: the run *has* the answer.
    """
    output = AgentOutput(
        response=response,
        structured_response=None,
        current_agent_name="torvalds",
        tool_calls=[],
    )
    # The framework attaches the tool results the same way: the list is
    # extended in place, so the ``ToolCallResult`` objects keep their
    # ``tool_output`` (see ``base_agent.parse_agent_output``).
    output.tool_calls.extend(
        [
            ToolCallResult(
                tool_name="execute_shell_command",
                tool_kwargs={"command": "psql -d llama_index_db -c '\\d+'"},
                tool_output=ToolOutput(
                    tool_name="execute_shell_command",
                    content=TOOL_RESULT,
                    raw_input={"command": "psql -d llama_index_db -c '\\d+'"},
                ),
                tool_id="call-1",
                return_direct=False,
            )
        ]
    )
    return output


def as_prompt_handler_would(output: AgentOutput) -> str:
    """Return the text ``prompt_handler`` prints.

    This is the code of ``agent-torvalds.py``:

        response_text = (
            result.get("output")
            if isinstance(result, dict)
            else str(result)
        )
    """
    result: object = output
    if isinstance(result, dict):
        return result.get("output")
    return str(result)


CASES = [
    (
        "the reported case: a thinking block and no text",
        ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content="The user wants the schema.")],
        ),
    ),
    (
        "the reported case: nothing at all",
        ChatMessage(role=MessageRole.ASSISTANT),
    ),
    (
        "the reported case: an empty text block",
        ChatMessage(
            role=MessageRole.ASSISTANT, blocks=[TextBlock(text="")],
        ),
    ),
    (
        "the first run of the report: the model repeated the human's "
        "answer in its thinking",
        ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[
                ThinkingBlock(
                    content=(
                        "user\n[Human response] **Switch to `llama_index_db`** "
                        "and check there?"
                    )
                )
            ],
        ),
    ),
    (
        "the case that works: the model answered",
        ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[TextBlock(text="The database has three tables.")],
        ),
    ),
]


def main() -> int:
    print("=" * 78)
    print("How the answer is lost")
    print("=" * 78)

    for title, response in CASES:
        output = build_output(response)
        printed = as_prompt_handler_would(output)
        log = to_output_string(output)

        print(f"\n--- {title} ---")
        print(f"  response.content          : {response.content!r}")
        print(f"  str(AgentOutput)          : {str(output)!r}")
        print(f"  what the Agent Response   : {printed!r}")
        print(f"  is it empty?              : {not printed.strip()}")
        print("  what the log shows        :")
        for line in log.splitlines():
            print(f"      {line}")

    print()
    print("=" * 78)
    print("The first run of the report, reconstructed")
    print("=" * 78)
    print("  The log of that run carries two records:")
    print()
    output = build_output(CASES[3][1])
    answer_lines = to_output_string(output).splitlines()
    for line in answer_lines[:2]:
        print(f"    EventConsumer._on_agent_output: {line}")
    print()
    print("  They are the two lines of ONE record: the thinking block of")
    print("  the model carried the human's own message, and there was no")
    print("  text block at all - so the section under the rule was empty.")
    print()
    print(f"  response.content          : {CASES[3][1].content!r}")
    print(f"  what the Agent Response   : {as_prompt_handler_would(output)!r}")
    print()
    print("=" * 78)
    print("The tool result is in the output the whole time:")
    output = build_output(CASES[0][1])
    print(f"  output.tool_calls[0]: {output.tool_calls[0].tool_name}")
    print(f"  its content         : {output.tool_calls[0].tool_output.content[:60]!r}...")
    print(f"  but str(output) is  : {str(output)!r}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
