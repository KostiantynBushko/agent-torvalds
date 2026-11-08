#!/usr/bin/env python3
"""
Skills in the LlamaIndex FunctionalAgent — the integration points, and what
each of them costs.

Read-only.  It measures and prints; it changes nothing in the repository,
talks to no model server and writes no file.  Run it as often as the reader
likes — the numbers in ``INVESTIGATION_REPORT.md`` are the numbers it prints.

What it measures
----------------

1. **The integration points** — the hooks ``FunctionAgent`` offers, read out
   of the class that is installed.
2. **The question the tool retriever is asked** — the retriever is asked with
   the *name of the tool* when the tool is called, not with the question of
   the user.  That decides where a skill tool has to live.
3. **Where the body of a skill ends up** — the lifecycle of one turn, from
   the tool result to the memory that the next request carries.
4. **The price of each channel** — the same procedure, delivered four ways.

Usage::

    .venv/bin/python investigate/skills-in-function-agent/probe_skills_in_function_agent.py

Category: Infrastructure
Retriever Keywords: skills, function agent, llamaindex, probe, integration points
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llama_index.core.agent.workflow import FunctionAgent  # noqa: E402
from llama_index.core.base.llms.types import (  # noqa: E402
    ChatMessage,
    MessageRole,
    ToolCallBlock,
)
from llama_index.core.llms.mock import MockFunctionCallingLLM  # noqa: E402
from llama_index.core.memory import ChatMemoryBuffer  # noqa: E402
from llama_index.core.objects import ObjectRetriever  # noqa: E402
from llama_index.core.tools import FunctionTool  # noqa: E402
from pydantic import Field, create_model  # noqa: E402

from components.context_guard import context_budget, select_context_window  # noqa: E402
from components.tokens import count_tokens_of, get_tokenizer  # noqa: E402

#: The context window of the model of the operator (local, Ollama).
CONTEXT_WINDOW = 8192

#: The procedure the probe delivers, in the four channels of section 4.
PROCEDURE = """# Deploy

1. Check that the tests pass: `.venv/bin/python -m pytest -q`.
2. Build the image: `docker build -t agent-torvalds .`.
3. Push it to the registry: `docker push registry.example/agent-torvalds:latest`.
4. Restart the service: `systemctl restart agent-torvalds`.
5. Check the log: `journalctl -u agent-torvalds -n 50 --no-pager`.
"""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rule(title: str) -> None:
    """Print a section header."""
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _role(message: ChatMessage) -> str:
    """Return the role of a message as a plain string."""
    role = message.role
    return getattr(role, "value", role)


def _describe(message: ChatMessage) -> str:
    """Return a one-line description of a chat message."""
    text = (message.content or "").strip().replace("\n", " ")
    if len(text) > 68:
        text = text[:65] + "..."
    extra = ""
    if message.additional_kwargs.get("tool_call_id"):
        extra = f"  [tool_call_id={message.additional_kwargs['tool_call_id']}]"
    calls = [
        block.tool_name for block in message.blocks if isinstance(block, ToolCallBlock)
    ]
    if calls:
        extra += f"  [calls: {', '.join(calls)}]"
    return (
        f"{_role(message):<10} {len(message.content or ''):>6} chars  "
        f"{text!r}{extra}"
    )


def _tokens(text: str) -> int:
    """Return the number of tokens of *text*, with the tokenizer of the agent."""
    count, _estimated = count_tokens_of(text, get_tokenizer())
    return count


# ---------------------------------------------------------------------------
# 1. the integration points
# ---------------------------------------------------------------------------


def section_integration_points() -> None:
    """Print the hooks the installed FunctionAgent offers."""
    _rule("1. The integration points of the installed FunctionAgent")

    import llama_index.core

    print(f"llama-index-core          : {llama_index.core.__version__}")
    print(f"FunctionAgent             : {FunctionAgent.__module__}")
    print(f"defined in                : {inspect.getsourcefile(FunctionAgent)}")
    print()

    print("-- the fields that carry content to the model --")
    for name in ("system_prompt", "tools", "tool_retriever", "llm", "streaming"):
        field = FunctionAgent.model_fields.get(name)
        if field is None:
            print(f"  {name:<16} (no such field)")
            continue
        print(f"  {name:<16} {str(field.annotation)[:70]}")
    print()

    print("-- the hooks a subclass may override --")
    hooks = (
        "get_tools",
        "take_step",
        "handle_tool_call_results",
        "finalize",
        "parse_agent_output",
        "call_tool",
        "aggregate_tool_results",
        "init_run",
        "setup_agent",
        "run_agent_step",
    )
    for name in hooks:
        fn = getattr(FunctionAgent, name, None)
        if fn is None:
            print(f"  {name:<26} (not present)")
            continue
        owner = "FunctionAgent" if name in vars(FunctionAgent) else "BaseWorkflowAgent"
        source = inspect.getsourcefile(fn) or "?"
        line = inspect.getsourcelines(fn)[1]
        try:
            signature = str(inspect.signature(fn))
        except (TypeError, ValueError):
            signature = "(?)"
        print(f"  {name:<26} {owner:<18} line {line:<5} {signature}")

    print()
    print("  the two that carry a message to the model:")
    print("    take_step(ctx, llm_input, tools, memory)")
    print("      llm_input  = the system prompt + the chat memory")
    print("      tools      = the tools of this iteration")
    print("      the scratchpad is read from ctx.store['scratchpad'] and added")
    print("    handle_tool_call_results(ctx, results, memory)")
    print("      the results of the tools are put into the scratchpad")


# ---------------------------------------------------------------------------
# 2. the question the tool retriever is asked
# ---------------------------------------------------------------------------


class RecordingRetriever(ObjectRetriever):
    """An ``ObjectRetriever`` that remembers every question it was asked."""

    def __init__(self, tools: Sequence[Any]) -> None:
        super().__init__(retriever=None, object_node_mapping=None)  # type: ignore[arg-type]
        self._tools = list(tools)
        self.queries: List[str] = []

    def _query(self, str_or_query_bundle: Any) -> str:
        if isinstance(str_or_query_bundle, str):
            return str_or_query_bundle
        return getattr(str_or_query_bundle, "query_str", str(str_or_query_bundle))

    def retrieve(self, str_or_query_bundle: Any) -> List[Any]:
        self.queries.append(self._query(str_or_query_bundle))
        return list(self._tools)

    async def aretrieve(self, str_or_query_bundle: Any) -> List[Any]:
        self.queries.append(self._query(str_or_query_bundle))
        return list(self._tools)


def _skill_llm(
    tool_name: str = "activate_skill",
    tool_kwargs: Optional[Dict[str, Any]] = None,
    answer: str = "The service is deployed.",
) -> MockFunctionCallingLLM:
    """Return an LLM that calls one tool and then answers."""

    def generator(messages: Sequence[ChatMessage], **kwargs: Any) -> ChatMessage:
        if any(message.role == MessageRole.TOOL for message in messages):
            return ChatMessage(role=MessageRole.ASSISTANT, content=answer)
        return ChatMessage(
            role=MessageRole.ASSISTANT,
            blocks=[
                ToolCallBlock(
                    tool_call_id="call-1",
                    tool_name=tool_name,
                    tool_kwargs=tool_kwargs or {},
                )
            ],
        )

    return MockFunctionCallingLLM(response_generator=generator, is_chat_model=True)


def _activate_skill_tool(body: str = PROCEDURE) -> FunctionTool:
    """Return the tool that carries a skill, as the agent has it today."""
    schema = create_model(
        "ActivateSkillArgs",
        name=(str, Field(description="The name of the skill to load.")),
    )

    def activate_skill(name: str) -> str:
        return f"Skill: {name}\n\n{body}"

    return FunctionTool.from_defaults(
        fn=activate_skill,
        name="activate_skill",
        description="Load the instructions of a named skill.",
        fn_schema=schema,
    )


async def section_retriever_question() -> None:
    """Print the questions the tool retriever is asked during one turn."""
    _rule("2. The question the tool retriever is asked")

    llm = _skill_llm(tool_kwargs={"name": "deploy"})
    tool = _activate_skill_tool()
    retriever = RecordingRetriever([tool])

    agent = FunctionAgent(
        llm=llm,
        tool_retriever=retriever,
        tools=[],
        streaming=False,
        max_iterations=5,
    )

    await agent.run("deploy the service to the remote host")

    print("The retriever was asked:")
    for index, query in enumerate(retriever.queries, start=1):
        print(f"  {index}. {query!r}")
    print()
    print("  run_agent_step() asks with the question of the user:")
    print("      get_tools(user_msg_str)")
    print("  call_tool() asks with the NAME OF THE TOOL:")
    print("      get_tools(ev.tool_name)")
    print()
    print("  A tool that is only in the retriever is therefore not found when")
    print("  it is called: the retriever is asked for the tool name, and a")
    print("  retriever that matches on meaning does not match on a name.")
    print()
    print("  => a skill tool has to be in agent.tools, not in the retriever.")


# ---------------------------------------------------------------------------
# 3. where the body of a skill ends up
# ---------------------------------------------------------------------------


class RecordingAgent(FunctionAgent):
    """A ``FunctionAgent`` that shows where the messages are."""

    seen_scratchpads: List[List[str]] = Field(default_factory=list)
    seen_llm_inputs: List[List[str]] = Field(default_factory=list)
    seen_tool_sets: List[List[str]] = Field(default_factory=list)

    async def take_step(
        self,
        ctx: Any,
        llm_input: List[ChatMessage],
        tools: Sequence[Any],
        memory: Any,
    ) -> Any:
        scratchpad = await ctx.store.get(self.scratchpad_key, default=[])
        self.seen_scratchpads.append([_describe(m) for m in scratchpad])
        self.seen_llm_inputs.append([_describe(m) for m in llm_input])
        self.seen_tool_sets.append([t.metadata.name for t in tools])
        return await super().take_step(ctx, llm_input, tools, memory)


async def section_where_the_body_ends_up() -> None:
    """Print the lifecycle of one turn that activates a skill."""
    _rule("3. Where the body of a skill ends up")

    llm = _skill_llm(tool_kwargs={"name": "deploy"})
    tool = _activate_skill_tool()
    memory = ChatMemoryBuffer.from_defaults(llm=llm)

    agent = RecordingAgent(
        llm=llm,
        tools=[tool],
        streaming=False,
        max_iterations=5,
    )

    await agent.run("deploy the service to the remote host", memory=memory)

    print("-- the scratchpad at every iteration --")
    for index, scratchpad in enumerate(agent.seen_scratchpads, start=1):
        print(f"  iteration {index}:")
        if not scratchpad:
            print("      (empty)")
        for line in scratchpad:
            print(f"      {line}")

    print()
    print("-- the memory after the turn (what the next request carries) --")
    messages = await memory.aget()
    for message in messages:
        print(f"      {_describe(message)}")

    body_tokens = _tokens(PROCEDURE)
    print()
    print(f"  the body of the skill      : {body_tokens} tokens")
    print(f"  the memory after the turn  : {len(messages)} messages")
    print()
    print("  finalize() puts the whole scratchpad into the memory:")
    print("      await memory.aput_messages(scratchpad)")
    print("  so the body of the skill is in the memory of the next request,")
    print("  and it is paid again by every request that follows.")

    # -- what the next request carries, and what the guard does to it --
    budget = context_budget(CONTEXT_WINDOW)
    prompt_tokens = _tokens("\n".join(m.content or "" for m in messages))
    share = body_tokens * 100 // max(prompt_tokens, 1)
    print()
    print("-- the prompt of the next request --")
    print(f"  the budget of the model      : {budget} tokens "
          f"(window {CONTEXT_WINDOW}, reserve 20%)")
    print(f"  the prompt                   : {prompt_tokens} tokens")
    print(f"  the share of the body        : {body_tokens} tokens ({share}%)")

    # -- a long conversation: when does the guard drop the body? --
    print()
    print("-- the guard, on a conversation that grows --")
    filler = "The tests pass and the image is built. " * 40
    conversation: List[ChatMessage] = [
        ChatMessage(role="user", content="deploy the service to the remote host")
    ]
    conversation.append(
        ChatMessage(role="assistant", content="I will follow the procedure.")
    )
    conversation.append(ChatMessage(role="tool", content=PROCEDURE))
    conversation.append(
        ChatMessage(role="assistant", content="The service is deployed.")
    )
    for round_number in range(1, 21):
        conversation.append(ChatMessage(role="user", content=filler))
        conversation.append(
            ChatMessage(role="assistant", content=f"Round {round_number} is done.")
        )
        window = select_context_window(conversation, budget, get_tokenizer())
        body_kept = any(message.role == MessageRole.TOOL for message in window)
        if not body_kept:
            print(f"  the body of the skill is dropped at round {round_number} "
                  f"(the window keeps {len(window)} of {len(conversation)} messages)")
            break
    else:
        print("  the body of the skill is still in the window after 20 rounds")


# ---------------------------------------------------------------------------
# 4. the price of each channel
# ---------------------------------------------------------------------------


def section_price_of_each_channel() -> None:
    """Print the price of the same procedure in the four channels."""
    _rule("4. The price of each channel")

    body_tokens = _tokens(PROCEDURE)
    catalog = (
        "- deploy: Deploy this project to the remote host over SSH.\n"
        "- release: Prepare and publish a release of this project.\n"
    )

    channels = {
        "in the system prompt (every request)": _tokens(catalog + "\n" + PROCEDURE),
        "in the schema of a tool (every request)": _tokens(
            "Load the instructions of a named skill. The procedure: "
            + PROCEDURE.replace("\n", " ")
        ),
        "as the result of the tool (this request)": body_tokens,
        "in the memory (every request after)": body_tokens,
    }

    print(f"  the procedure is {body_tokens} tokens long")
    print()
    for name, tokens in channels.items():
        print(f"  {name:<48} {tokens:>6} tokens")
    print()
    print("  The first two are paid by every request, whether the run touches")
    print("  a skill or not.  The third is paid once, by the run that asks for")
    print("  the skill.  The fourth is the one that is easy to forget: the")
    print("  body is in the memory, and the memory is in every request that")
    print("  follows, until the guard drops it.")


# ---------------------------------------------------------------------------
# 5. the transient channel
# ---------------------------------------------------------------------------


class TransientAgent(FunctionAgent):
    """An agent that shows the body of a skill exactly once.

    The body is marked when the tool result lands in the scratchpad, and it
    is dropped from the scratchpad as soon as the model has read it.  The
    body therefore costs the request that reads it, and nothing after.
    """

    delivered: List[bool] = Field(default_factory=list)
    stripped: int = Field(default=0)
    seen_body: bool = False

    async def handle_tool_call_results(self, ctx: Any, results: Any, memory: Any) -> None:
        await super().handle_tool_call_results(ctx, results, memory)
        scratchpad = await ctx.store.get(self.scratchpad_key, default=[])
        for message in scratchpad:
            if message.role == MessageRole.TOOL:
                message.additional_kwargs["skill_body"] = True

    async def take_step(
        self,
        ctx: Any,
        llm_input: List[ChatMessage],
        tools: Sequence[Any],
        memory: Any,
    ) -> Any:
        scratchpad = await ctx.store.get(self.scratchpad_key, default=[])
        has_body = any(
            message.additional_kwargs.get("skill_body") for message in scratchpad
        )
        if has_body and self.seen_body:
            kept = [
                message
                for message in scratchpad
                if not message.additional_kwargs.get("skill_body")
            ]
            await ctx.store.set(self.scratchpad_key, kept)
            self.stripped += len(scratchpad) - len(kept)
            has_body = False
        self.delivered.append(has_body)
        if has_body:
            self.seen_body = True
        return await super().take_step(ctx, llm_input, tools, memory)


async def section_transient_channel() -> None:
    """Compare the channel that keeps the body with the one that drops it."""
    _rule("5. The transient channel")

    llm = _skill_llm(tool_kwargs={"name": "deploy"})
    tool = _activate_skill_tool()
    memory = ChatMemoryBuffer.from_defaults(llm=llm)

    agent = TransientAgent(
        llm=llm,
        tools=[tool],
        streaming=False,
        max_iterations=5,
    )

    await agent.run("deploy the service to the remote host", memory=memory)

    print("-- the persistent channel (the tool result stays) --")
    agent_persistent = RecordingAgent(
        llm=_skill_llm(tool_kwargs={"name": "deploy"}),
        tools=[tool],
        streaming=False,
        max_iterations=5,
    )
    memory_persistent = ChatMemoryBuffer.from_defaults(llm=llm)
    await agent_persistent.run(
        "deploy the service to the remote host", memory=memory_persistent
    )
    persistent_memory = await memory_persistent.aget()
    persistent_body = sum(
        1 for message in persistent_memory if message.role == MessageRole.TOOL
    )
    print(f"  the body is in the memory of the next request : {persistent_body} times")
    print(f"  the memory holds {len(persistent_memory)} messages")
    print()

    print("-- the transient channel (the body is dropped once it was read) --")
    print(f"  the iterations that carried the body : {agent.delivered}")
    print(f"  the bodies dropped from the scratchpad : {agent.stripped}")
    transient_memory = await memory.aget()
    transient_body = sum(
        1 for message in transient_memory if message.role == MessageRole.TOOL
    )
    print(f"  the body is in the memory of the next request : {transient_body} times")
    print(f"  the memory holds {len(transient_memory)} messages")
    print()
    print("  The price of the body is paid by the requests that carry it.")
    print("  The persistent channel keeps it in the memory of the session,")
    print("  and the memory is in every request that follows, until the guard")
    print("  drops it.  The transient channel pays the body once, and the model")
    print("  has to be told again what the procedure was if it is asked again.")


# ---------------------------------------------------------------------------
# the main
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run every section of the probe."""
    print("Skills in the LlamaIndex FunctionalAgent — a probe")
    print(f"repository: {REPO_ROOT}")

    section_integration_points()
    await section_retriever_question()
    await section_where_the_body_ends_up()
    section_price_of_each_channel()
    await section_transient_channel()

    print()
    print("=" * 78)
    print("end of the probe")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
