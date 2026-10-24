"""
End-to-end reproduction of "No user query found in messages."

Uses a REAL session that is stored in PostgreSQL (one that the trimming probe
showed loses its user query) as the agent's chat memory, then runs the real
agent with the real Excel request against the real Ollama server.

Chain proven here:

  1. ``ChatMemoryBuffer.get()`` trims the stored history from the front and,
     when the window collapses, returns ``chat_history[-1:]`` -- whatever the
     last message is.  If that is an assistant/tool message, the user query
     is gone.
  2. ``FunctionAgent.take_step`` builds ``[*llm_input, *scratchpad]`` from
     that trimmed memory, so the query never reaches the model.
  3. The model's Jinja template scans the messages in reverse for a
     ``user`` message that is not a ``<tool_response>`` wrapper.  Finding
     none, it raises "No user query found in messages.".

Usage:
    python investigate/no-user-query-error/repro_end_to_end.py [--send]
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.ollama.base import Ollama
from llama_index.storage.chat_store.postgres import PostgresChatStore

URI = os.environ.get(
    "TORVALDS_LLAMA_URI",
    "postgresql://postgres:postgres@127.0.0.1:5432/llama_index_db",
)

# A real session that the trimming probe showed loses its user query.
VICTIM_KEY = "chat-custom-698f061f-df3c-4454-8b85-3b2794f430c2-38d8d8d6"

REQUEST = (
    "in project folder: take a file A = OV_2026_10.xlsx file B = shtab.xlsx "
    "for person 'Митлушко Андрій Романович' merge entities from column 'D' in "
    "file A and column C in file B, the result must be in copy of file B in "
    "the project directory, the source of truth is file A. Original files "
    "must be untoched."
)

CONTEXT = "CONTEXT: ### Registered Projects\n- **mytlushko** (Unknown): ."


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


async def main() -> int:
    send = "--send" in sys.argv

    store = PostgresChatStore.from_uri(uri=URI)
    keys = store.get_keys()
    if VICTIM_KEY not in keys:
        print(f"session {VICTIM_KEY} not found; available: {keys}")
        return 1

    stored = store.get_messages(VICTIM_KEY)
    print("=" * 78)
    print("STEP 1 — the stored session the agent starts from")
    print("=" * 78)
    print(f"key            : {VICTIM_KEY}")
    print(f"stored messages: {len(stored)}")
    print(f"roles (tail)   : {[m.role for m in stored[-6:]]}")

    # Work on a COPY of the session so the user's stored history is untouched.
    repro_key = VICTIM_KEY + "-repro"
    store.set_messages(repro_key, list(stored))

    buffer = ChatMemoryBuffer.from_defaults(
        token_limit=5000,
        chat_store=store,
        chat_store_key=repro_key,
    )

    trimmed = buffer.get()
    print(f"\n(repro copy key: {repro_key})")
    print(f"after ChatMemoryBuffer.get(): {len(trimmed)} message(s)")
    print(f"  roles   : {[m.role for m in trimmed]}")
    print(f"  query present? {has_user_query(trimmed)}")

    # Now do exactly what prompt_handler() does: inject the project context
    # and the user request, then let the agent build its LLM input.
    print("\n" + "=" * 78)
    print("STEP 2 — the agent builds the LLM input from that memory")
    print("=" * 78)

    buffer.put(ChatMessage(content=CONTEXT))
    buffer.put(ChatMessage(role="user", content=REQUEST))

    llm_input = buffer.get()
    print(f"memory.get() -> {len(llm_input)} message(s)")
    print(f"  roles   : {[m.role for m in llm_input]}")
    print(f"  query present? {has_user_query(llm_input)}")

    if has_user_query(llm_input):
        print("\n!! the user query survived — this session does not reproduce it")
        return 2

    print("\n  ==> THE USER QUERY IS GONE. The template will raise.")

    # ---------------------------------------------------------------
    # STEP 3 — prove the real Ollama server raises the exact error
    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("STEP 3 — the real model template on the real server")
    print("=" * 78)

    llm = Ollama(
        model="richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
        base_url="http://localhost:11434",
        request_timeout=300.0,
    )
    ollama_messages = llm._convert_to_ollama_messages(llm_input)
    print(f"messages on the wire: {len(ollama_messages)}")
    for m in ollama_messages:
        print(f"   role={m['role']!r} content={m['content'][:90]!r}")

    if not send:
        print("\n(--send not given: stopping before the live request)")
        return 0

    import urllib.error
    import urllib.request

    payload = {
        "model": "richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
        "messages": ollama_messages,
        "stream": False,
        "options": {"num_predict": 1},
    }
    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            print(f"\nserver replied OK: {resp.read()[:200]!r}")
            return 3
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\nserver replied HTTP {e.code}")
        print(body[:900])
        if "No user query found in messages" in body:
            print("\n==> REPRODUCED: the exact error from exel.txt")
            return 0
        return 4


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
