"""Read-only probe: what did the model see for the run that went silent?

The session of the operator is in the chat store of PostgreSQL.  The probe
reads the messages of the session, rebuilds the history as it was at the
start of each of the three requests, and runs the two memory buffers over
it:

* the buffer of LlamaIndex (``ChatMemoryBuffer``), and
* the buffer of this project (``TrimmingChatMemoryBuffer``).

It prints the window each buffer hands to the model: how many messages,
which role the window opens with, and whether the request of the operator
is in it.  Nothing is written; the database is only read.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("TORVALDS_PG_HOST", "127.0.0.1")
os.environ.setdefault("TORVALDS_PG_USER", "postgres")
os.environ.setdefault("TORVALDS_PG_PASSWORD", "postgres")

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.memory import ChatMemoryBuffer
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from chat_manager.memory import TrimmingChatMemoryBuffer  # noqa: E402

KEY = "chat-custom-698f061f-df3c-4454-8b85-3b2794f430c2-9d39436d"
LIMIT = 10000
URI = "postgresql://postgres:postgres@127.0.0.1:5432/llama_index_db"


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
        kind = getattr(block, "block_type", None) or (
            block.get("block_type") if isinstance(block, dict) else ""
        )
        if kind != "text":
            continue
        text_value = getattr(block, "text", None)
        if text_value is None and isinstance(block, dict):
            text_value = block.get("text", "")
        parts.append(text_value or "")
    body = "\n".join(parts) if parts else (m.content or "")
    return " ".join(body.split())[:90]


def window_report(name: str, window: list[ChatMessage], request: str) -> None:
    roles = [m.role.value for m in window]
    print(f"\n--- {name} ---")
    print(f"    messages            : {len(window)}")
    print(f"    opens with role     : {roles[0] if roles else '(empty)'}")
    print(f"    request in window   : {any(request in describe(m) for m in window)}")
    print(f"    first 3 messages    :")
    for m in window[:3]:
        print(f"        {m.role.value:9s} {describe(m)}")
    print(f"    last 3 messages     :")
    for m in window[-3:]:
        print(f"        {m.role.value:9s} {describe(m)}")


def main() -> None:
    messages = load()
    print(f"messages in the store: {len(messages)}")

    # The store holds the session as it ended.  The three requests of the
    # operator are the user messages in it; the history at the start of a
    # request is everything up to and including that request.
    requests = [
        ("please initialize project based on the description in README file", None),
        ("please update a README file acordingly", None),
        ("can you update readme file with the details of this solution", None),
    ]
    starts = []
    for request, _ in requests:
        for index, message in enumerate(messages):
            if message.role == MessageRole.USER and request in describe(message):
                starts.append((request, index))
                break

    for request, index in starts:
        history = messages[: index + 1]
        print("\n" + "=" * 78)
        print(f"REQUEST: {request}")
        print(f"history at the start of the request: {len(history)} messages")

        library = ChatMemoryBuffer.from_defaults(token_limit=LIMIT, chat_history=history)
        project = TrimmingChatMemoryBuffer.from_defaults(token_limit=LIMIT, chat_history=history)

        lib_window = library.get()
        prj_window = project.get()

        window_report("LlamaIndex ChatMemoryBuffer", lib_window, request)
        window_report("TrimmingChatMemoryBuffer (this project)", prj_window, request)

        same = [m.content for m in lib_window] == [m.content for m in prj_window]
        print(f"\n    the two windows are identical: {same}")


if __name__ == "__main__":
    main()
