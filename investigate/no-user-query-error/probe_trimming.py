"""
Decisive test: does ``ChatMemoryBuffer.get()`` drop the user query from a
real stored session?

The model template raises "No user query found in messages." whenever the
message list it receives contains no ``user`` message whose content is not a
``<tool_response>`` wrapper.

``ChatMemoryBuffer.get()`` trims from the *front* of the history and, when
the window collapses to a single message, returns ``chat_history[-1:]`` —
whatever that last message happens to be.  If the last message is a ``tool``
message, the user query is gone and the template raises.

This script loads every session that is really stored in PostgreSQL, runs the
real trimming on it, and reports whether the user query survives.

Usage:
    python investigate/no-user-query-error/probe_trimming.py [token_limit]
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.storage.chat_store.postgres import PostgresChatStore


URI = os.environ.get(
    "TORVALDS_LLAMA_URI",
    "postgresql://postgres:postgres@127.0.0.1:5432/llama_index_db",
)


def has_user_query(messages) -> bool:
    for m in reversed(list(messages)):
        if m.role != "user":
            continue
        content = (m.content or "").strip()
        if not (
            content.startswith("<tool_response>")
            and content.endswith("</tool_response>")
        ):
            return True
    return False


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

    store = PostgresChatStore.from_uri(uri=URI)
    keys = store.get_keys()
    print("=" * 78)
    print(f"TRIMMING PROBE — token_limit={limit} — {len(keys)} stored sessions")
    print("=" * 78)

    for key in keys:
        messages = store.get_messages(key)
        if not messages:
            print(f"\n{key}: (empty)")
            continue

        buffer = ChatMemoryBuffer.from_defaults(
            token_limit=limit,
            chat_store=store,
            chat_store_key=key,
        )
        trimmed = buffer.get()

        roles = [m.role for m in trimmed]
        tail_roles = [m.role for m in messages[-3:]]
        kept = has_user_query(trimmed)
        lost = not kept

        flag = "  <== USER QUERY LOST" if lost else ""
        print(f"\n{key}")
        print(f"   stored messages : {len(messages)}")
        print(f"   after trimming  : {len(trimmed)}  roles={roles[:12]}{'...' if len(roles) > 12 else ''}")
        print(f"   last stored role: {tail_roles}")
        if lost:
            print(f"   !! trimmed window has NO user query -> template raises{flag}")
            for m in trimmed:
                print(f"      {m.role}: {(m.content or '')[:120]!r}")
        else:
            print("   ok: user query present after trimming")


if __name__ == "__main__":
    asyncio.run(main())
