#!/usr/bin/env python3
"""
Probe: what does the Ollama server answer when the prompt grows long?

The reported symptom is that a long run ends with an **empty** answer.
The log of the reported run shows the last model call of the run:

    LLM call #2 finished — prompt=7494, completion=1, total=7495 tokens
    EventConsumer._on_agent_stream: delta=''
    EventConsumer._on_agent_output: assistant: (empty)

``completion=1`` and an empty delta mean the model produced *one* token and
stopped.  This probe asks the running server the same question at several
prompt sizes, so the boundary can be seen instead of guessed at.

It reproduces the *shape* of the real conversation — a system message, a
user request, an assistant turn that calls a tool, and the tool's answer —
and grows the filler until the prompt reaches the size that was logged.

Usage:
    python probe_long_prompt.py                 # default sweep
    python probe_long_prompt.py --model <name>
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import requests

DEFAULT_MODEL = "richardyoung/qwen3.6-27b-abliterated:Q4_K_M"
DEFAULT_URL = "http://localhost:11434"

#: The context window the reported run used (``PARAMETER num_ctx``).
NUM_CTX = 8192

#: The prompt size that was logged when the answer came back empty.
REPORTED_PROMPT_TOKENS = 7494

#: The tool the real run called.
TOOL_NAME = "execute_shell_command"

#: The answer the real run got back.
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
    " public | chatstore_id_seq | sequence | llama    | permanent   |       "
    "        | 8192 bytes | \n"
    " public | users            | table    | postgres | permanent   | heap"
    "          | 16 kB      | \n"
    "(4 rows)"
)

FILLER = (
    "The operator asked the agent to describe the tables of the "
    "llama_index_db database. The agent listed the relations and reported "
    "the owner, the persistence, the access method and the size of every "
    "relation it found. "
)

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "Execute a shell command and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "the command"},
                    "timeout": {"type": "integer", "description": "seconds"},
                },
                "required": ["command"],
            },
        },
    }
]


def build_conversation(filler_repeats: int) -> list[dict]:
    """Return a conversation whose prompt grows with *filler_repeats*."""
    return [
        {
            "role": "system",
            "content": (
                "You are Torvalds, a technical AI assistant that interacts "
                "with the operating system."
            ),
        },
        {
            "role": "user",
            "content": (
                "Switch to `llama_index_db` and show me the schema of every "
                "table in it. " + FILLER * filler_repeats
            ),
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": TOOL_NAME,
                        "arguments": {
                            "command": (
                                "PGPASSWORD=postgres psql -h 127.0.0.1 -U "
                                "postgres -d llama_index_db -c '\\d+'"
                            ),
                            "timeout": 10,
                        },
                    }
                }
            ],
        },
        {
            "role": "tool",
            "content": TOOL_RESULT,
        },
    ]


def ask(url: str, model: str, messages: list[dict], num_ctx: int) -> dict:
    """Send one streaming chat request and summarise what came back.

    Returns:
        A mapping with the token counts the server reported, the text the
        model produced, the text it thought, and the number of chunks.
    """
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOL_SCHEMA,
        "stream": True,
        "options": {"num_ctx": num_ctx},
    }

    content: list[str] = []
    thinking: list[str] = []
    prompt_eval = None
    eval_count = None
    chunks = 0
    saw_none_content = False

    with requests.post(f"{url}/api/chat", json=payload, stream=True, timeout=900) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            chunks += 1
            message = chunk.get("message") or {}
            if "content" not in message or message.get("content") is None:
                saw_none_content = True
            content.append(message.get("content") or "")
            thinking.append(message.get("thinking") or "")
            if chunk.get("done"):
                prompt_eval = chunk.get("prompt_eval_count")
                eval_count = chunk.get("eval_count")
                if chunk.get("done_reason"):
                    pass

    return {
        "chunks": chunks,
        "content": "".join(content),
        "thinking": "".join(thinking),
        "prompt_eval_count": prompt_eval,
        "eval_count": eval_count,
        "saw_none_content": saw_none_content,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--num-ctx", type=int, default=NUM_CTX)
    parser.add_argument(
        "--repeats",
        type=int,
        nargs="*",
        default=[0, 40, 80, 120, 160, 200],
        help="filler sizes to try, in order",
    )
    args = parser.parse_args()

    print(f"model      : {args.model}")
    print(f"num_ctx    : {args.num_ctx}")
    print(f"reported   : prompt={REPORTED_PROMPT_TOKENS} tokens, completion=1")
    print()

    for repeats in args.repeats:
        messages = build_conversation(repeats)
        started = time.time()
        try:
            result = ask(args.url, args.model, messages, args.num_ctx)
        except Exception as exc:  # noqa: BLE001 - the probe reports, it does not fail
            print(f"repeats={repeats:>4}  ERROR: {exc}")
            continue
        elapsed = time.time() - started

        content = result["content"]
        thinking = result["thinking"]
        print(
            f"repeats={repeats:>4}  prompt={result['prompt_eval_count']}  "
            f"completion={result['eval_count']}  "
            f"content_len={len(content)}  thinking_len={len(thinking)}  "
            f"chunks={result['chunks']}  "
            f"none_content={result['saw_none_content']}  "
            f"{elapsed:.1f}s"
        )
        if content:
            print(f"             content: {content[:160]!r}")
        elif thinking:
            print(f"             thinking only: {thinking[:160]!r}")
        else:
            print("             NOTHING AT ALL")

    return 0


if __name__ == "__main__":
    sys.exit(main())
