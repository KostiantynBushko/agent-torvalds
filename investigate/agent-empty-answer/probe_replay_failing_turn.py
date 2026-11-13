"""Read-only probe: replay the turn that went silent.

The session of the operator is in the chat store.  The probe rebuilds the
prompt of two consecutive turns of the second request — the turn that
worked (the model called two tools) and the turn that went silent (the
model answered with nothing) — and sends both to the model server through
the *same* LLM wrapper the agent uses.

The two prompts differ by exactly three messages: the assistant message
that called the tools and the two results of the tools.  Everything else
is the same conversation.

Nothing is written; the store is only read.
"""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("TORVALDS_PG_HOST", "127.0.0.1")
os.environ.setdefault("TORVALDS_PG_USER", "postgres")
os.environ.setdefault("TORVALDS_PG_PASSWORD", "postgres")

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

KEY = "chat-custom-698f061f-df3c-4454-8b85-3b2794f430c2-9d39436d"
URI = "postgresql://postgres:postgres@127.0.0.1:5432/llama_index_db"

MODEL = os.environ.get("PROBE_MODEL", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")


def load() -> list[ChatMessage]:
    engine = create_engine(URI)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT value FROM chatstore WHERE key = :k"), {"k": KEY}
        ).scalar()
    return [ChatMessage.model_validate(m) for m in row]


def describe(m: ChatMessage) -> str:
    parts = []
    for block in (m.blocks or []):
        kind = getattr(block, "block_type", "")
        if kind == "text":
            parts.append(getattr(block, "text", "") or "")
    body = "\n".join(parts) if parts else (m.content or "")
    return " ".join(body.split())[:80]


#: The categories the operator selected.  11 (Operating System) + 7
#: (System) + 19 (Project Management) = 37 — the number the log of the
#: run names ("Starting agent with 37 selected tool(s)"), and every tool
#: the run used is in this set.
OPERATOR_CATEGORIES = ("Operating System", "System", "Project Management")


def tools():
    from agent_tool_selection import _discover_tools, group_tools_by_category

    groups = group_tools_by_category(_discover_tools())
    return [
        tool
        for category, items in groups.items()
        if category in OPERATOR_CATEGORIES
        for tool in items
    ]


def report(name: str, response) -> None:
    message = response.message
    thinking = ""
    text = ""
    calls = []
    for block in message.blocks or []:
        kind = getattr(block, "block_type", "")
        if kind == "thinking":
            thinking = getattr(block, "content", "") or ""
        elif kind == "text":
            text = getattr(block, "text", "") or ""
        elif kind == "tool_call":
            calls.append(getattr(block, "tool_name", ""))
    usage = response.additional_kwargs.get("usage") or {}
    print(f"\n--- {name} ---")
    print(f"    thinking ({len(thinking):5d} chars): {thinking[-160:]!r}")
    print(f"    text    ({len(text):5d} chars): {text[:160]!r}")
    print(f"    tool calls        : {calls}")
    print(f"    prompt tokens     : {usage.get('prompt_tokens')}")
    print(f"    completion tokens : {usage.get('completion_tokens')}")


async def main() -> None:
    from components.llm_retry import RetryingOllama
    from components.ollama_config import apply_context_window

    messages = load()
    print(f"messages in the store: {len(messages)}")

    # The system prompt of the run: the static template of the project
    # and the project context of the operator's session.
    project_context = ""
    for message in messages:
        if message.role == MessageRole.USER and describe(message).startswith("CONTEXT:"):
            project_context = describe(message)[len("CONTEXT:"):].strip()
            break
    system = ChatMessage(role=MessageRole.SYSTEM, content=(
        "You are Torvalds, a technical AI assistant that interacts with the operating system, "
        "supports software development, and assists with engineering and analytical tasks."
        "Capabilities:"
        "Work with the system environment: files, processes, commands, configurations."
        "Assist with development: code creation, refactoring, debugging, architectural guidance."
        "Support analytical and scientific workflows: computation, data handling, reasoning."
        "Help with operational tasks: automation, diagnostics, environment inspection."
        "Operating Principles:"
        "Use available system interfaces and tools when performing actions."
        "Request explicit confirmation before destructive or irreversible operations."
        "For version control: never commit or push without explicit approval; always show changes first."
        "Be clear about actions, reasoning, and expected outcomes."
        "Source:"
        "Repository: git@github.com:KostiantynBushko/agent-torvalds.git"
        ""
        f"{project_context}"
    ))

    llm = RetryingOllama(
        model=MODEL,
        base_url="http://localhost:11434",
        request_timeout=99999,
        temperature=0.0,
        top_p=0.1,
        max_retries=0,
        retry_delay=1,
    )
    window = apply_context_window(llm)
    print(f"model: {MODEL}  context window: {window}")

    tool_list = tools()
    specs = [t.metadata.to_openai_tool(skip_length_check=True) for t in tool_list]
    print(f"tools: {len(tool_list)}")

    # The turn that worked: the prompt ended with the request of the
    # operator (message 63).  The turn that went silent: the same
    # prompt plus the three messages of the tool round.
    turns = {
        "WORKING turn (prompt ends with the request)": messages[:63],
        "SILENT turn (prompt ends with the tool results)": messages[:66],
    }

    for name, history in turns.items():
        chat_history = [system, *history]
        print(f"\n{'=' * 78}\n{name}  ({len(chat_history)} messages)")
        response = await llm.achat_with_tools(
            chat_history=chat_history,
            tools=tool_list,
            allow_parallel_tool_calls=True,
        )
        report(name, response)


if __name__ == "__main__":
    asyncio.run(main())
