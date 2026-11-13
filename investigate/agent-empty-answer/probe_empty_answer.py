"""Read-only probe: where the answer of the agent went.

The session of the operator is in the chat store of PostgreSQL.  The probe
reads the messages of the session, takes the three answers the agent gave,
and shows what the console path prints for each of them:

* the text the model wrote,
* the thinking the model left behind,
* ``str(AgentOutput)`` — the value the console path puts on the screen.

Nothing is written; the database is only read.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("TORVALDS_PG_HOST", "127.0.0.1")
os.environ.setdefault("TORVALDS_PG_USER", "postgres")
os.environ.setdefault("TORVALDS_PG_PASSWORD", "postgres")

from llama_index.core.agent.workflow import AgentOutput
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

KEY = "chat-custom-698f061f-df3c-4454-8b85-3b2794f430c2-9d39436d"
URI = "postgresql://postgres:postgres@127.0.0.1:5432/llama_index_db"


def load() -> list[ChatMessage]:
    engine = create_engine(URI)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT value FROM chatstore WHERE key = :k"), {"k": KEY}
        ).scalar()
    return [ChatMessage.model_validate(m) for m in row]


def parts(message: ChatMessage) -> tuple[str, str, list[str]]:
    thinking = ""
    body = ""
    calls = []
    for block in message.blocks or []:
        kind = getattr(block, "block_type", "")
        if kind == "thinking":
            thinking = getattr(block, "content", "") or ""
        elif kind == "text":
            body = getattr(block, "text", "") or ""
        elif kind == "tool_call":
            calls.append(getattr(block, "tool_name", ""))
    return thinking, body, calls


def main() -> None:
    messages = load()
    print(f"messages in the store: {len(messages)}")

    # The answers are the assistant messages that are not followed by a
    # tool result: they are the turns the agent ended the run on.
    for index, message in enumerate(messages):
        if message.role != MessageRole.ASSISTANT:
            continue
        following = messages[index + 1] if index + 1 < len(messages) else None
        if following is not None and following.role == MessageRole.TOOL:
            continue

        thinking, body, calls = parts(message)
        output = AgentOutput(response=message, current_agent_name="torvalds")
        printed = str(output)

        print(f"\n=== message {index + 1}: the answer the run ended on ===")
        print(f"    thinking        : {thinking[-120:]!r}")
        print(f"    text            : {body[:120]!r}")
        print(f"    tool calls      : {calls}")
        print(f"    ---")
        print(f"    str(AgentOutput): {printed[:120]!r}")
        print(f"    the console prints: {printed[:120]!r}")
        print(f"    the operator sees : "
              f"{'NOTHING AT ALL' if not printed.strip() else printed[:80]}")


if __name__ == "__main__":
    main()
