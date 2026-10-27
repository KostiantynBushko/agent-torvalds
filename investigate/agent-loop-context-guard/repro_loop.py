"""
Reproduction of the agent loop caused by the context guard.

What this script shows
----------------------
``components/context_guard.py`` is applied inside
``HITLFunctionAgent.take_step()``.  When the prompt does not fit into the
budget the guard returns a *window* of messages **and the agent writes
that window back into the scratchpad**::

    await ctx.store.set(self.scratchpad_key, tail)

Two defects in the guard combine into an infinite loop:

**D1 — the guard keeps the OLDEST turns, not the newest.**
``_select_window()`` iterates over the groups in chronological order and
stops at the first group that does not fit, so the *oldest* turns survive
and the *newest* ones — the ones the model just produced — are thrown
away.  The code even says "Fill with the most recent turns, newest first"
while doing the opposite.

**D2 — the window is emitted in reverse chronological order.**
``for group in reversed(selected)`` reverses the tail, so the model sees
the conversation backwards.

With D1 + D2 the window stops changing: the same (oldest) turn is kept
forever, the scratchpad is rewritten with it, and the next iteration
produces the *identical* window.  The agent is therefore shown exactly
the same prompt on every iteration.

The agent configures the model with ``temperature=0.0`` (see
``agent-torvalds.py``), so a greedy model answers an identical prompt
with an identical tool call.  The agent calls the same tool with the
same arguments, gets the same result, and loops until
``MAX_ITERATIONS`` (50) is reached — hours of wall-clock time.

The script drives the **real** ``HITLFunctionAgent`` workflow with:

* the **real** 27 tools the operator selected in the failing run
  (``System / Package Management`` + ``Operating System`` + ``System``),
* the **real** context window of the local model (``num_ctx 8192``),
* the **real** chat memory limit (5000 tokens),
* a fake LLM that behaves like a greedy model: it answers an identical
  prompt with an identical answer, and a different prompt with the next
  scripted answer.

Category: Infrastructure
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llama_index.core.base.llms.types import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    MessageRole,
    ToolCallBlock,
)
from llama_index.core.bridge.pydantic import PrivateAttr  # noqa: E402
from llama_index.core.memory import ChatMemoryBuffer  # noqa: E402
from llama_index.llms.ollama.base import Ollama  # noqa: E402

from agent_tool_selection import _discover_tools, group_tools_by_category  # noqa: E402
from components.context_guard import context_budget, count_tokens  # noqa: E402
from components.hitl_agent import HITLFunctionAgent  # noqa: E402

#: The categories the operator picked in the failing run
#: ("Select categories [example: 1,2,5 or 1-3] (1-12): 3,5,12").
CATEGORIES = ("System / Package Management", "Operating System", "System")

#: The real context window of the local model (``PARAMETER num_ctx 8192``).
CONTEXT_WINDOW = 8192

#: The real chat memory limit of the failing session.
MEMORY_TOKEN_LIMIT = 5000

#: The size of the DEPLOYMENT.md document the agent read in the failing run.
#: It is what exhausted the prompt budget and made the guard drop the
#: newest turn.
DEPLOYMENT_DOC_TOKENS = 3270

#: A deployment document of roughly the size the agent read in the failing
#: run.  It is written to a temporary directory and removed afterwards.
DEPLOYMENT_DOC = (
    "# Deployment\n\n"
    "## Prerequisites\n\n"
    "The target host must be reachable over SSH and the `sshpass` utility "
    "must be available on the workstation. The agent clones the "
    "`agent-torvalds` repository into the home folder of the remote user "
    "and then runs the deployment script described below.\n\n"
    "## Steps\n\n"
    "1. Verify that `git` and `sshpass` are installed locally.\n"
    "2. Verify that the remote host answers on port 22.\n"
    "3. Clone the repository into `~/agent-torvalds` on the remote host.\n"
    "4. Copy the deployment configuration into the repository.\n"
    "5. Run `python3 agent-torvalds.py --deploy` inside the clone.\n"
    "6. Verify that the service is up and that the log file is written.\n\n"
    "## Rollback\n\n"
    "If the deployment fails, remove the clone, restore the previous "
    "configuration backup and restart the service.\n\n"
    "## Notes\n\n"
    "The deployment is idempotent: running it twice produces the same "
    "result. The script must never be interrupted while it rewrites the "
    "configuration, because the service reads the configuration only at "
    "start-up.\n\n"
) + (
    "## Appendix — environment matrix\n\n"
    "| component | version | notes |\n"
    "|---|---|---|\n"
    "| python | 3.12 | required for the deployment script |\n"
    "| git | 2.43 | the repository is cloned over ssh |\n"
    "| sshpass | 1.10 | used for the non-interactive password |\n"
    "| ollama | 0.5 | the local model is used for the verification step |\n\n"
) * 30


class GreedyOllama(Ollama):
    """An Ollama LLM that decodes greedily, like the real agent configures it.

    ``temperature=0.0`` means: *the same prompt always produces the same
    answer*.  The fake LLM models exactly that.  A different prompt moves
    on to the next scripted answer.
    """

    _requests: list = PrivateAttr(default_factory=list)
    _script: list = PrivateAttr(default_factory=list)
    _last_prompt: str = PrivateAttr(default="")
    _last_answer: dict = PrivateAttr(default_factory=dict)
    _stuck: bool = PrivateAttr(default=False)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("model", "fake/model")
        kwargs.setdefault("base_url", "http://localhost:11434")
        super().__init__(*args, **kwargs)
        self._requests = []

    @property
    def requests(self):
        return self._requests

    def get_context_window(self) -> int:
        return CONTEXT_WINDOW

    @staticmethod
    def _fingerprint(messages) -> str:
        return json.dumps(
            [m.model_dump() for m in messages], sort_keys=True, default=str
        )

    def _answer(self, messages):
        self._requests.append(list(messages))
        prompt = self._fingerprint(messages)

        if self._stuck and self._last_answer:
            # A model that is stuck: the same call, whatever the prompt.
            answer = self._last_answer
        elif prompt == self._last_prompt and self._last_answer:
            # Greedy decoding: the same prompt, the same answer.
            answer = self._last_answer
        else:
            answer = (
                self._script.pop(0)
                if self._script
                else {"tool": None, "args": {}}
            )
            self._last_prompt = prompt
            self._last_answer = answer

        if answer["tool"] is None:
            return ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content="Done.")
            )

        return ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT,
                blocks=[
                    ToolCallBlock(
                        tool_name=answer["tool"], tool_kwargs=answer["args"]
                    )
                ],
            )
        )

    async def astream_chat(self, messages, **kwargs):
        async def gen():
            yield self._answer(list(messages))

        return gen()

    async def achat(self, messages, **kwargs):
        return self._answer(list(messages))


def write_deployment_doc(directory: Path) -> Path:
    """Write a DEPLOYMENT.md of the size the agent read in the failing run.

    The size matters: the document has to be large enough to exhaust the
    prompt budget on its own, so that the guard has to drop a turn.  The
    document is therefore measured and grown until it reaches the target
    token count.
    """
    from components.context_guard import get_tokenizer

    tokenizer = get_tokenizer()
    path = directory / "DEPLOYMENT.md"

    text = DEPLOYMENT_DOC
    chunk = (
        "\n## Appendix — verification checklist\n\n"
        "The verification step confirms that the remote service answers on "
        "the expected port, that the configuration file was rewritten with "
        "the new values, and that the log file contains the start-up "
        "banner. Every check is idempotent and safe to repeat.\n"
    )
    while len(tokenizer(text)) < DEPLOYMENT_DOC_TOKENS:
        text += chunk

    path.write_text(text, encoding="utf-8")
    return path


def build_real_tools():
    """Return the 27 tools the operator selected in the failing run."""
    groups = group_tools_by_category(_discover_tools())
    tools = []
    for category in CATEGORIES:
        tools.extend(groups[category])
    return tools


def seed_memory(memory, count: int) -> None:
    """Fill the memory so that ``llm_input`` looks like the failing run.

    The failing run had a 14-message ``llm_input`` (the system prompt plus
    13 memory messages) and a budget of 3343 tokens.
    """
    memory.put(
        ChatMessage(
            role=MessageRole.USER,
            content="CONTEXT: ### Registered Projects\n- torvalds-deployment",
        )
    )
    filler = (
        "Deployment session: the target host is 192.168.0.102, the user is itv, "
        "the agent-torvalds repository has to be cloned into the home folder "
        "and the deployment is described in DEPLOYMENT.md. "
    ) * 8
    for index in range(count - 2):
        memory.put(
            ChatMessage(
                role=MessageRole.ASSISTANT,
                content=f"Earlier turn {index}: {filler}",
            )
        )


def render(messages, limit: int = 90) -> str:
    parts = []
    for message in messages:
        role = message.role.value if hasattr(message.role, "value") else message.role
        text = message.content or ""
        for block in getattr(message, "blocks", None) or []:
            if getattr(block, "block_type", None) == "tool_call":
                text = (
                    f"[tool_call {getattr(block, 'tool_name', '')} "
                    f"{getattr(block, 'tool_kwargs', '')}]"
                )
        parts.append(f"{role}: {text[:limit]}")
    return "\n".join(parts)


def fingerprint(messages) -> str:
    return json.dumps(
        [m.model_dump() for m in messages], sort_keys=True, default=str
    )


async def drive(agent, memory, request: str) -> None:
    handler = agent.run(request, memory=memory, max_iterations=12)
    try:
        await handler
    except Exception as exc:  # noqa: BLE001 - the run may end early
        print(f"  (run ended: {type(exc).__name__})")


def run_scenario_stuck(tools) -> int:
    """A model that asks for the same thing whatever the prompt says.

    The context guard cannot stop a model that is stuck on its own — the
    prompt changes, the answer does not.  The agent has to notice and
    break the repetition, otherwise every iteration costs a full model
    round-trip (minutes, on a local model) until ``MAX_ITERATIONS``.
    """
    print("=" * 78)
    print("SCENARIO B: the model is stuck and repeats the same call")
    print("=" * 78)
    print()

    llm = GreedyOllama()
    llm._stuck = True
    llm._script = [
        {"tool": "check_command_exists", "args": {"command": "sshpass"}},
    ]

    memory = ChatMemoryBuffer.from_defaults(token_limit=MEMORY_TOKEN_LIMIT)
    agent = HITLFunctionAgent(
        tools=tools,
        llm=llm,
        max_iterations=12,
        memory=memory,
        system_prompt="You are Torvalds.",
    )
    agent.hitl_enabled = False
    seed_memory(memory, 13)

    request = "deploy the project on 192.168.0.102"

    asyncio.run(drive(agent, memory, request))

    requests = llm.requests

    print(f"the model was called {len(requests)} times")
    print()
    if len(requests) >= 12:
        print(
            "RESULT: FAIL — the agent repeated the same call for the whole "
            "run without stopping."
        )
        return 1

    print(
        "RESULT: PASS — the agent noticed the repetition and stopped the "
        "run instead of repeating itself for the whole iteration budget."
    )
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    tools = build_real_tools()
    import tempfile

    tmpdir = Path(tempfile.mkdtemp(prefix="torvalds-loop-"))
    doc = write_deployment_doc(tmpdir)
    print(f"DEPLOYMENT.md written to {doc} "
          f"({len(doc.read_text())} bytes)")

    llm = GreedyOllama()
    # The model reads DEPLOYMENT.md first, then checks for sshpass — the
    # exact sequence of the failing run.
    llm._script = [
        {"tool": "read_file", "args": {"path": str(doc)}},
        {"tool": "check_command_exists", "args": {"command": "sshpass"}},
    ]

    memory = ChatMemoryBuffer.from_defaults(token_limit=MEMORY_TOKEN_LIMIT)
    agent = HITLFunctionAgent(
        tools=tools,
        llm=llm,
        max_iterations=12,
        memory=memory,
        system_prompt="You are Torvalds.",
    )
    agent.hitl_enabled = False

    seed_memory(memory, 13)

    request = (
        "connect to the another machine, clone the agent torval repo into the "
        "home folder and start deployment based on the description in "
        "DEPLOYMENT.md. Here is credential for ssh connection user: itv, "
        "IP 192.168.0.102 and password 2615"
    )

    print("=" * 78)
    print("REPRODUCTION: the agent loop caused by the context guard")
    print("=" * 78)
    print()
    print(f"tools selected     : {len(tools)}  {list(CATEGORIES)}")
    print(f"context window     : {CONTEXT_WINDOW} (the real num_ctx)")
    print(f"prompt budget      : {context_budget(CONTEXT_WINDOW)} - tool schemas")
    print(f"memory limit       : {MEMORY_TOKEN_LIMIT} tokens")
    print(f"model              : greedy (temperature=0.0)")
    print()

    asyncio.run(drive(agent, memory, request))

    requests = llm.requests
    print()
    print(f"the model was called {len(requests)} times")
    print()
    print("-" * 78)
    print("prompt of every iteration")
    print("-" * 78)
    for index, messages in enumerate(requests):
        print(
            f"[{index:2d}] {len(messages):2d} msgs, "
            f"{count_tokens(messages):5d} tokens"
        )
        for line in render(messages).splitlines():
            print(f"       {line}")
        print()

    print("-" * 78)
    print("are consecutive prompts identical?")
    print("-" * 78)
    identical = []
    for index in range(1, len(requests)):
        same = fingerprint(requests[index - 1]) == fingerprint(requests[index])
        identical.append(same)
        print(f"  prompt {index - 1:2d} == prompt {index:2d}: {same}")

    fixed_point = bool(identical) and all(identical[1:])
    print()
    if fixed_point:
        print(
            "RESULT: FAIL — from iteration 2 onwards the prompt is IDENTICAL on\n"
            "        every iteration.  A greedy model answers it with the same\n"
            "        tool call, so the agent loops forever."
        )
        return 1

    print("RESULT: PASS — the prompt changes on every iteration (no fixed point).")
    print()
    return run_scenario_stuck(tools)


if __name__ == "__main__":
    raise SystemExit(main())
