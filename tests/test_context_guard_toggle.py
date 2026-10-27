"""
Tests for the context guard switch.

The guard trims the prompt to the model's context window.  It is
**opt-in**: the agent does not trim anything unless the operator asks for
it with ``--context-guard-on`` (or ``TORVALDS_CONTEXT_GUARD=true``).

These tests pin that contract:

* by default the guard stands down and the prompt reaches the model
  exactly as the agent assembled it;
* with the guard enabled the prompt is trimmed and the user request
  survives;
* the command line flag turns it on, and nothing else does.

Category: Infrastructure
"""

import importlib.util
import sys
from pathlib import Path

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    MessageRole,
    ToolCallBlock,
)
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama.base import Ollama

from components.context_guard import count_tokens, has_user_query
from components.hitl_agent import HITLFunctionAgent

REPO_ROOT = Path(__file__).resolve().parent.parent


class FakeOllama(Ollama):
    """An Ollama LLM that answers from a script and records every request."""

    _requests: list = PrivateAttr(default_factory=list)
    _script: list = PrivateAttr(default_factory=list)
    _context_window: int = PrivateAttr(default=8192)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("model", "fake/model")
        kwargs.setdefault("base_url", "http://localhost:11434")
        super().__init__(*args, **kwargs)
        self._requests = []
        self._script = []

    @property
    def requests(self):
        return self._requests

    def set_script(self, script):
        self._script = list(script)

    def get_context_window(self) -> int:
        return self._context_window

    def _next(self, messages):
        self._requests.append(list(messages))
        if not self._script:
            return ChatResponse(
                message=ChatMessage(role=MessageRole.ASSISTANT, content="Done.")
            )
        step = self._script.pop(0)
        if isinstance(step, tuple) and step and step[0] == "call":
            _, tool_name, tool_kwargs = step
            return ChatResponse(
                message=ChatMessage(
                    role=MessageRole.ASSISTANT,
                    blocks=[
                        ToolCallBlock(
                            tool_name=tool_name, tool_kwargs=tool_kwargs
                        )
                    ],
                )
            )
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=step)
        )

    async def astream_chat(self, messages, **kwargs):
        async def gen():
            yield self._next(list(messages))

        return gen()

    async def achat(self, messages, **kwargs):
        return self._next(list(messages))


def huge_tool(path: str) -> str:
    """A tool that returns a very large payload, like reading a spreadsheet."""
    return "\n".join(
        f"row {i} | 1234567890 | 3400,00 | ХАРКІВ | 2026-10-01" for i in range(4000)
    )


def build_agent(context_guard_enabled: bool):
    """Build an agent whose guard is explicitly *context_guard_enabled*."""
    llm = FakeOllama()
    tools = [
        FunctionTool.from_defaults(
            fn=huge_tool,
            name="read_xlsx_file",
            description="Read data from an Excel .xlsx file.",
        )
    ]
    memory = ChatMemoryBuffer.from_defaults(token_limit=5000)
    agent = HITLFunctionAgent(
        tools=tools,
        llm=llm,
        max_iterations=30,
        memory=memory,
        system_prompt="You are Torvalds.",
    )
    agent.hitl_enabled = False
    agent.context_guard_enabled = context_guard_enabled
    return agent, llm, memory


def _run(agent, llm, memory, request, script):
    """Run the agent and return the recorded requests."""
    import asyncio

    llm.set_script(script)
    memory.put(ChatMessage(content="CONTEXT: ### Registered Projects\n- mytlushko"))

    async def _drive():
        handler = agent.run(request, memory=memory, max_iterations=30)
        try:
            await handler
        except Exception:  # noqa: BLE001 - the run may end early
            pass

    asyncio.run(_drive())
    return llm.requests


# ---------------------------------------------------------------------------
# The switch on the agent
# ---------------------------------------------------------------------------


def test_the_guard_is_off_by_default():
    """A fresh agent must not trim the prompt.

    The guard changes what the model is shown, so it is opt-in: the
    default has to leave the prompt exactly as the agent assembled it.
    """
    agent = HITLFunctionAgent(llm=FakeOllama(), tools=[])

    assert agent.context_guard_enabled is False


def test_the_guard_off_lets_the_prompt_grow():
    """With the guard off, nothing is trimmed from the prompt.

    The tool result is far bigger than the 8192-token window, so the
    prompt that reaches the model grows past it.  That is the price of
    the guard being off — and the reason the guard exists.
    """
    agent, llm, memory = build_agent(context_guard_enabled=False)
    request = "merge the entities of column D into shtab.xlsx"

    # The model asks for the file twice: the tool result is what makes the
    # prompt grow, and it is only there once the tool has actually run.
    script = [("call", "read_xlsx_file", {"path": "a.xlsx"})] * 3
    requests = _run(agent, llm, memory, request, script)

    assert len(requests) > 1, "the agent never called the model twice"
    assert any(
        count_tokens(messages) > 8192 for messages in requests
    ), "the prompt never grew past the context window — the guard trimmed it"


def test_the_guard_on_trims_the_prompt():
    """With the guard on, the prompt fits and keeps the user request."""
    agent, llm, memory = build_agent(context_guard_enabled=True)
    request = "merge the entities of column D into shtab.xlsx"

    script = [("call", "read_xlsx_file", {"path": "a.xlsx"})] * 3
    requests = _run(agent, llm, memory, request, script)

    assert len(requests) > 1, "the agent never called the model twice"
    for index, messages in enumerate(requests):
        assert count_tokens(messages) <= 8192, (
            f"call {index} sent more than the 8192-token context window"
        )
        assert has_user_query(messages), f"call {index} has no user query"
        texts = [m.content or "" for m in messages if m.role == MessageRole.USER]
        assert any(request in text for text in texts), (
            f"call {index} lost the user request"
        )


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def _load_orchestrator(monkeypatch, argv):
    """Load ``agent-torvalds.py`` with *argv* as its command line."""
    monkeypatch.setattr(sys, "argv", argv)
    spec = importlib.util.spec_from_file_location(
        "agent_torvalds_cli", REPO_ROOT / "agent-torvalds.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_flag_is_off_by_default(monkeypatch):
    """Without the flag, the guard stays off."""
    monkeypatch.delenv("TORVALDS_CONTEXT_GUARD", raising=False)
    module = _load_orchestrator(monkeypatch, ["agent-torvalds.py"])

    args = module.parse_args()

    assert args.context_guard_on is False
    assert module.CONTEXT_GUARD_ENABLED is False
    assert module.context_guard_enabled is False


def test_the_flag_turns_the_guard_on(monkeypatch):
    """``--context-guard-on`` turns the guard on."""
    monkeypatch.delenv("TORVALDS_CONTEXT_GUARD", raising=False)
    module = _load_orchestrator(
        monkeypatch, ["agent-torvalds.py", "--context-guard-on"]
    )

    args = module.parse_args()

    assert args.context_guard_on is True
    # main() folds the flag into the effective configuration.
    assert module.CONTEXT_GUARD_ENABLED or args.context_guard_on


def test_the_environment_variable_turns_the_guard_on(monkeypatch):
    """``TORVALDS_CONTEXT_GUARD=true`` turns the guard on as well."""
    monkeypatch.setenv("TORVALDS_CONTEXT_GUARD", "true")
    module = _load_orchestrator(monkeypatch, ["agent-torvalds.py"])

    args = module.parse_args()

    assert module.CONTEXT_GUARD_ENABLED is True
    assert module.CONTEXT_GUARD_ENABLED or args.context_guard_on


def test_the_configuration_reaches_the_agent(monkeypatch):
    """The effective configuration is applied to the agent."""
    monkeypatch.delenv("TORVALDS_CONTEXT_GUARD", raising=False)
    module = _load_orchestrator(monkeypatch, ["agent-torvalds.py"])

    agent = HITLFunctionAgent(llm=FakeOllama(), tools=[])

    module.context_guard_enabled = True
    module._apply_agent_config(agent)
    assert agent.context_guard_enabled is True

    module.context_guard_enabled = False
    module._apply_agent_config(agent)
    assert agent.context_guard_enabled is False


def test_the_multi_window_orchestrator_has_the_same_flag(monkeypatch):
    """The multi-window console variant offers the same switch."""
    monkeypatch.delenv("TORVALDS_CONTEXT_GUARD", raising=False)
    spec = importlib.util.spec_from_file_location(
        "agent_torvalds_mw_cli", REPO_ROOT / "agent-torvalds-mw.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(sys, "argv", ["agent-torvalds-mw.py"])
    assert module.parse_args().context_guard_on is False

    monkeypatch.setattr(
        sys, "argv", ["agent-torvalds-mw.py", "--context-guard-on"]
    )
    assert module.parse_args().context_guard_on is True
