#!/usr/bin/env python3
"""
The verification harness for the answer of a run.

The reported symptom is an empty *Agent Response* section after a long
run, while the log shows that the run *had* a tool result to show:

    EventConsumer._on_stop_event: tool result: execute_shell_command:
        {'stdout': 'List of relations ...', 'returncode': 0, 'success': True}
    ────────────── Agent Response ──────────────
    ─────────────────────────────────────────────

The harness checks six invariants:

    E1  the answer of a run is never empty — a run that has something to
        show always says something
    E2  an answer that is missing is *reported*: the operator is told
        that the model wrote nothing
    E3  the last tool result of the run is shown when the model wrote
        nothing — the answer is where the agent found it
    E4  an answer that exists is returned unchanged
    E5  a payload that cannot be read does not break the run
    E6  a run in which the model wrote nothing is given another turn —
        and only one

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/empty-agent-response/verify_empty_response.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# The module root may be pointed elsewhere, so the drift harness can run
# the checks against a broken copy of the code.
MODULE_ROOT = Path(
    os.environ.get("TORVALDS_MODULE_ROOT", str(Path(__file__).resolve().parents[2]))
)
sys.path.insert(0, str(MODULE_ROOT))

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
from pydantic import Field  # noqa: E402

from components.agent_answer import (  # noqa: E402
    NO_ANSWER_NOTICE,
    answer_is_missing,
    extract_answer,
)

logger = logging.getLogger("components.agent_answer")


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------

class Harness:
    """Collects the checks and prints the verdict."""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, invariant: str, ok: bool, detail: str = "") -> None:
        self.results.append((invariant, ok, detail))
        mark = "OK  " if ok else "FAIL"
        print(f"[{mark}] {invariant}  {detail}")

    def report(self) -> int:
        failed = [r for r in self.results if not r[1]]
        names = list(dict.fromkeys(r[0] for r in failed))
        print()
        print(f"{len(self.results) - len(failed)}/{len(self.results)} checks hold")
        if failed:
            print("FAILED: " + ", ".join(names))
            return 1
        return 0


class Capture(logging.Handler):
    """Collects the log records the module emits."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def text(self) -> str:
        return "\n".join(record.getMessage() for record in self.records)


# ---------------------------------------------------------------------------
# The fixtures
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


def output_with_text() -> AgentOutput:
    """The normal run: the model answered."""
    return AgentOutput(
        response=ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[TextBlock(text="The database has three tables.")],
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
# The checks
# ---------------------------------------------------------------------------

def check_e1_never_empty(h: Harness) -> None:
    """E1 — the answer of a run is never empty."""
    answer = extract_answer(output_with_thinking())
    h.check(
        "E1",
        bool(answer.strip()),
        f"the answer of a run with a tool result is {len(answer)} characters",
    )

    h.check(
        "E1",
        bool(extract_answer(output_with_text()).strip()),
        "the answer of a run with an answer is not empty",
    )

    h.check(
        "E1",
        bool(extract_answer({"output": "a legacy answer"}).strip()),
        "the legacy dict shape is read",
    )

    h.check(
        "E1",
        bool(extract_answer("a plain answer").strip()),
        "a plain string is read",
    )


def check_e2_the_missing_answer_is_reported(h: Harness) -> None:
    """E2 — an answer that is missing is reported."""
    answer = extract_answer(output_with_thinking())
    h.check(
        "E2",
        NO_ANSWER_NOTICE.split("\n")[0] in answer,
        "the operator is told that the model wrote nothing",
    )

    h.check(
        "E2",
        answer_is_missing(output_with_thinking()),
        "the missing answer is recognised as missing",
    )

    h.check(
        "E2",
        not answer_is_missing(output_with_text()),
        "an answer that exists is not reported as missing",
    )

    capture = Capture()
    logger.addHandler(capture)
    try:
        extract_answer(output_with_thinking())
    finally:
        logger.removeHandler(capture)

    h.check(
        "E2",
        "no answer" in capture.text().lower(),
        "the log says that the model wrote nothing",
    )


def check_e3_the_tool_result_is_shown(h: Harness) -> None:
    """E3 — the last tool result of the run is shown."""
    answer = extract_answer(output_with_thinking())
    h.check(
        "E3",
        "List of relations" in answer,
        "the tool result is in the answer",
    )
    h.check(
        "E3",
        "execute_shell_command" in answer,
        "the tool that produced it is named",
    )


def check_e4_an_answer_is_unchanged(h: Harness) -> None:
    """E4 — an answer that exists is returned unchanged."""
    answer = extract_answer(output_with_text())
    h.check(
        "E4",
        answer == "The database has three tables.",
        f"the answer is returned as it is ({answer!r})",
    )

    h.check(
        "E4",
        extract_answer({"output": "a legacy answer"}) == "a legacy answer",
        "the legacy dict shape is returned as it is",
    )


def check_e5_a_broken_payload(h: Harness) -> None:
    """E5 — a payload that cannot be read does not break the run."""
    raised = False
    try:
        extract_answer(Broken())
    except Exception:  # noqa: BLE001 — the point of the check
        raised = True
    h.check("E5", not raised, "the extraction survives a payload that raises")


class SilentThenAnsweringLLM(MockFunctionCallingLLM):
    """An LLM that answers with nothing, and then answers.

    The first turn returns a **thinking block and no text** — the reported
    failure.  The second turn returns a real answer, so the check can see
    whether the run was given the second turn at all.
    """

    call_count: int = Field(default=0)
    thinking_text: str = Field(default="The user wants the schema.")

    @llm_chat_callback()
    async def astream_chat(self, messages, **kwargs):
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


def check_e6_the_run_gets_another_turn(h: Harness) -> None:
    """E6 — a run in which the model wrote nothing is given another turn."""
    from components.hitl_agent import EMPTY_ANSWER_RETRIES, HITLFunctionAgent

    h.check(
        "E6",
        EMPTY_ANSWER_RETRIES >= 1,
        f"the run is given {EMPTY_ANSWER_RETRIES} more turn(s) at most",
    )

    llm = SilentThenAnsweringLLM()
    agent = HITLFunctionAgent(tools=[], llm=llm)

    async def run() -> str:
        handler = agent.run("show me the schema")
        result = await handler
        return str(result)

    answer = asyncio.run(run())

    h.check(
        "E6",
        llm.call_count == 2,
        f"the model was asked twice (it was asked {llm.call_count} times)",
    )

    h.check(
        "E6",
        answer.strip() == "The database has three tables.",
        f"the run ended with the answer of the second turn ({answer!r})",
    )


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def main() -> int:
    print("The answer-of-a-run invariants")
    print("=" * 70)
    h = Harness()

    check_e1_never_empty(h)
    check_e2_the_missing_answer_is_reported(h)
    check_e3_the_tool_result_is_shown(h)
    check_e4_an_answer_is_unchanged(h)
    check_e5_a_broken_payload(h)
    check_e6_the_run_gets_another_turn(h)

    return h.report()


if __name__ == "__main__":
    sys.exit(main())
