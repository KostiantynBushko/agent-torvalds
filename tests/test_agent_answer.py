"""
Unit tests for the answer of a run — and for the run that has none.

The reported symptom is an empty *Agent Response* section at the end of a
long run, while the log shows that the run *had* a tool result to show::

    EventConsumer._on_stop_event: tool result: execute_shell_command:
        {'stdout': 'List of relations ...', 'returncode': 0, 'success': True}
    ────────────── Agent Response ──────────────
    ─────────────────────────────────────────────

The chain that loses the answer:

1. the model answers with a *thinking* block and no text (the log shows
   ``assistant: (empty)``);
2. ``AgentOutput.__str__`` returns ``self.response.content or ""``;
3. ``ChatMessage.content`` is the text of the **TextBlocks** only — the
   thinking is not part of it;
4. ``prompt_handler`` printed ``str(result)``, so the section was blank.

What is covered here:

* ``components/agent_answer.py`` — the answer is never empty: a run that
  has nothing to say says so, and shows what it found;
* ``components/hitl_agent.py`` — a run in which the model wrote nothing is
  given **one** more turn before it is given up on;
* the entry points — the answer is read through ``extract_answer``.

Run with:
    pytest tests/test_agent_answer.py -v
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest
from pydantic import Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llama_index.core.agent.workflow import AgentOutput, ToolCallResult  # noqa: E402
from llama_index.core.base.llms.types import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    MessageRole,
    TextBlock,
    ThinkingBlock,
)
from llama_index.core.llms.callbacks import llm_chat_callback  # noqa: E402
from llama_index.core.llms.mock import MockFunctionCallingLLM  # noqa: E402
from llama_index.core.tools import ToolOutput  # noqa: E402

from components.agent_answer import (  # noqa: E402
    NO_ANSWER_NOTICE,
    THINKING_LIMIT,
    TOOL_RESULT_LIMIT,
    answer_is_missing,
    extract_answer,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

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
    " public | users            | table    | postgres | permanent   | heap"
    "          | 16 kB      | \n"
    "(4 rows)"
)

#: The thinking of the model in the reported run.
THINKING = "The user wants to see the schema of the llama_index_db database."


def output_with_thinking() -> AgentOutput:
    """The reported run: a thinking block and no text."""
    output = AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content=THINKING)],
        ),
        structured_response=None,
        current_agent_name="torvalds",
        tool_calls=[],
    )
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


def output_with_empty_text_block() -> AgentOutput:
    """The shape the Ollama adapter writes: an empty text block.

    The adapter always adds a ``TextBlock`` — even when the model wrote
    nothing, so the block is there and its text is empty.  The run then
    renders as an empty answer, exactly as the reported one did.
    """
    return AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[ThinkingBlock(content=THINKING), TextBlock(text="")],
        ),
        structured_response=None,
        current_agent_name="torvalds",
        tool_calls=[],
    )


def output_with_text(text: str = "The database has three tables.") -> AgentOutput:
    """The normal run: the model answered."""
    return AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[TextBlock(text=text)],
        ),
        structured_response=None,
        current_agent_name="torvalds",
        tool_calls=[],
    )


class Broken:
    """A payload whose attributes raise."""

    def __getattr__(self, name: str):
        raise RuntimeError("the payload is broken")


# ---------------------------------------------------------------------------
# extract_answer
# ---------------------------------------------------------------------------


class TestExtractAnswer:
    """The answer of a run."""

    def test_an_answer_is_returned_as_it_is(self):
        answer = extract_answer(output_with_text())
        assert answer == "The database has three tables."

    def test_the_legacy_dict_shape_is_read(self):
        assert extract_answer({"output": "a legacy answer"}) == "a legacy answer"

    def test_a_plain_string_is_read(self):
        assert extract_answer("a plain answer") == "a plain answer"

    def test_the_answer_of_a_run_is_never_empty(self):
        """E1 — the section under the rule is never blank."""
        for output in (
            output_with_thinking(),
            output_with_empty_text_block(),
            AgentOutput(
                response=ChatMessage(role=MessageRole.ASSISTANT),
                structured_response=None,
                current_agent_name="torvalds",
                tool_calls=[],
            ),
        ):
            assert extract_answer(output).strip()

    def test_a_missing_answer_is_reported(self):
        """E2 — the operator is told that the model wrote nothing."""
        answer = extract_answer(output_with_thinking())
        assert NO_ANSWER_NOTICE.split("\n")[0] in answer

    def test_the_tool_result_is_shown(self):
        """E3 — the answer is where the agent found it."""
        answer = extract_answer(output_with_thinking())
        assert "List of relations" in answer
        assert "execute_shell_command" in answer

    def test_the_thinking_of_the_model_is_shown(self):
        answer = extract_answer(output_with_thinking())
        assert THINKING in answer

    def test_the_last_tool_result_is_the_one_shown(self):
        output = output_with_thinking()
        output.tool_calls.append(
            ToolCallResult(
                tool_name="read_file",
                tool_kwargs={"path": "/etc/hosts"},
                tool_output=ToolOutput(
                    tool_name="read_file",
                    content="127.0.0.1 localhost",
                    raw_input={"path": "/etc/hosts"},
                ),
                tool_id="call-2",
                return_direct=False,
            )
        )
        answer = extract_answer(output)
        assert "127.0.0.1 localhost" in answer
        assert "List of relations" not in answer

    def test_a_huge_tool_result_is_truncated(self):
        output = output_with_thinking()
        output.tool_calls[0].tool_output.content = "x" * (TOOL_RESULT_LIMIT * 2)
        answer = extract_answer(output)
        assert len(answer) < TOOL_RESULT_LIMIT * 2
        assert "truncated" in answer

    def test_a_huge_thinking_is_truncated(self):
        output = output_with_thinking()
        output.response.blocks[0].content = "y" * (THINKING_LIMIT * 2)
        answer = extract_answer(output)
        assert len(answer) < THINKING_LIMIT * 2

    def test_a_run_without_a_tool_result_still_says_something(self):
        output = AgentOutput(
            response=ChatMessage(role=MessageRole.ASSISTANT),
            structured_response=None,
            current_agent_name="torvalds",
            tool_calls=[],
        )
        answer = extract_answer(output)
        assert NO_ANSWER_NOTICE.split("\n")[0] in answer

    def test_a_payload_that_raises_does_not_break_the_run(self):
        """E5 — a debugging aid must not be able to break a run."""
        assert extract_answer(Broken()).strip()

    def test_nothing_raises(self):
        for payload in (None, 42, [], {}, object()):
            assert isinstance(extract_answer(payload), str)


class TestAnswerIsMissing:
    """The difference between "no answer" and "a broken renderer"."""

    def test_a_run_without_an_answer_is_missing(self):
        assert answer_is_missing(output_with_thinking())
        assert answer_is_missing(output_with_empty_text_block())

    def test_a_run_with_an_answer_is_not_missing(self):
        assert not answer_is_missing(output_with_text())

    def test_a_legacy_answer_is_not_missing(self):
        assert not answer_is_missing({"output": "a legacy answer"})


# ---------------------------------------------------------------------------
# The run that is given another turn
# ---------------------------------------------------------------------------


class SilentThenAnsweringLLM(MockFunctionCallingLLM):
    """An LLM that answers with nothing, and then answers.

    The first turn returns a **thinking block and no text** — the reported
    failure.  The second turn returns a real answer, so the test can see
    whether the run was given the second turn at all.
    """

    call_count: int = Field(default=0)
    thinking_text: str = Field(default="The user wants the schema.")

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.call_count += 1
        silent = self.call_count == 1

        async def gen():
            yield ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    blocks=(
                        [ThinkingBlock(content=self.thinking_text)]
                        if silent
                        else [TextBlock(text="The database has three tables.")]
                    ),
                ),
                delta="",
                raw={"message": {"role": "assistant", "content": ""}},
            )

        return gen()

    @llm_chat_callback()
    def chat(self, messages, **kwargs) -> ChatResponse:
        raise NotImplementedError("the agent streams")


class SilentLLM(MockFunctionCallingLLM):
    """An LLM that never answers — the worst case."""

    call_count: int = Field(default=0)

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.call_count += 1

        async def gen():
            yield ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    blocks=[ThinkingBlock(content="thinking and nothing else")],
                ),
                delta="",
                raw={"message": {"role": "assistant", "content": ""}},
            )

        return gen()

    @llm_chat_callback()
    def chat(self, messages, **kwargs) -> ChatResponse:
        raise NotImplementedError("the agent streams")


class AnsweringLLM(MockFunctionCallingLLM):
    """An LLM that answers straight away."""

    call_count: int = Field(default=0)

    @llm_chat_callback()
    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        self.call_count += 1

        async def gen():
            yield ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    blocks=[TextBlock(text="The database has three tables.")],
                ),
                delta="",
                raw={"message": {"role": "assistant", "content": ""}},
            )

        return gen()

    @llm_chat_callback()
    def chat(self, messages, **kwargs) -> ChatResponse:
        raise NotImplementedError("the agent streams")


def _run(llm) -> str:
    """Run the real HITL agent with *llm* and return the answer of the run."""
    import asyncio

    from components.hitl_agent import HITLFunctionAgent

    agent = HITLFunctionAgent(tools=[], llm=llm)

    async def go() -> str:
        handler = agent.run("show me the schema")
        result = await handler
        return str(result)

    return asyncio.run(go())


class TestTheRunGetsAnotherTurn:
    """E6 — a run in which the model wrote nothing is given another turn."""

    def test_the_model_is_asked_again(self):
        llm = SilentThenAnsweringLLM()
        _run(llm)
        assert llm.call_count == 2

    def test_the_run_ends_with_the_answer_of_the_second_turn(self):
        llm = SilentThenAnsweringLLM()
        answer = _run(llm)
        assert answer.strip() == "The database has three tables."

    def test_a_run_with_an_answer_is_not_asked_again(self):
        llm = AnsweringLLM()
        answer = _run(llm)
        assert llm.call_count == 1
        assert answer.strip() == "The database has three tables."

    def test_the_run_gives_up_after_the_budget(self):
        """The model is not asked forever — one more turn, and no more."""
        from components.hitl_agent import EMPTY_ANSWER_RETRIES

        llm = SilentLLM()
        answer = _run(llm)
        assert llm.call_count == EMPTY_ANSWER_RETRIES + 1
        assert answer.strip() == "", "the model wrote nothing, and nothing is faked"

    def test_the_budget_is_one_turn(self):
        from components.hitl_agent import EMPTY_ANSWER_RETRIES

        assert EMPTY_ANSWER_RETRIES == 1


# ---------------------------------------------------------------------------
# The entry points
# ---------------------------------------------------------------------------


ENTRY_POINTS = ("agent-torvalds.py", "agent-torvalds-mw.py", "agent-torvalds-cpp.py")


class TestTheEntryPoints:
    """The answer is read through ``extract_answer``, everywhere."""

    @pytest.mark.parametrize("name", ENTRY_POINTS)
    def test_the_entry_point_imports_extract_answer(self, name):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "from components.agent_answer import extract_answer" in source

    @pytest.mark.parametrize("name", ENTRY_POINTS)
    def test_the_entry_point_calls_extract_answer(self, name):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        called = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "extract_answer"
            for node in ast.walk(tree)
        )
        assert called, f"{name} does not read the answer through extract_answer"

    @pytest.mark.parametrize("name", ENTRY_POINTS)
    def test_the_entry_point_does_not_read_the_answer_off_the_result(self, name):
        """The old extraction — ``str(result)`` — is what lost the answer.

        The check reads the *code*, not the text of the file: the comments
        of the entry points mention ``str(result)`` to explain what the
        old code did.
        """
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            # ``str(result)``
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "str"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "result"
            ):
                pytest.fail(f"{name} still reads the answer with str(result)")

            # ``result.get("output")``
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "result"
            ):
                pytest.fail(f"{name} still reads the answer off the result")


# ---------------------------------------------------------------------------
# The module itself
# ---------------------------------------------------------------------------


class TestTheModule:
    """The module is importable on its own and does not need the agent."""

    def test_it_has_no_import_of_the_agent(self):
        source = (ROOT / "components" / "agent_answer.py").read_text(
            encoding="utf-8"
        )
        assert "hitl_agent" not in source
        assert "event_consumer" not in source

    def test_it_is_documented(self):
        source = (ROOT / "components" / "agent_answer.py").read_text(
            encoding="utf-8"
        )
        assert source.startswith('"""')
        assert "Category: Infrastructure" in source
