"""
Verification: the context guard prevents the "No user query found in
messages." failure against the real Ollama server.

``probe_truncation.py`` reproduces the failure: a message list larger than
the model's context window makes the Ollama server truncate the prompt, the
user query at the front is dropped, and the model template raises.

This script takes the very same message list, runs it through
``select_context_window()`` and sends the result to the server.  The server
must answer normally — no "No user query found in messages.".

Usage:
    python investigate/no-user-query-error/verify_fix_live.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from llama_index.core.base.llms.types import ChatMessage, MessageRole

from components.context_guard import (
    context_budget,
    count_tokens,
    get_tokenizer,
    has_user_query,
    select_context_window,
)
from components.ollama_config import resolve_context_window

OLLAMA = "http://localhost:11434"
MODEL = "richardyoung/qwen3.6-27b-abliterated:Q4_K_M"
CONTEXT_TOKENS = 262144

REQUEST = (
    "in project folder: take a file A = OV_2026_10.xlsx file B = shtab.xlsx "
    "for person 'Митлушко Андрій Романович' merge entities from column 'D' in "
    "file A and column C in file B, the result must be in copy of file B in "
    "the project directory, the source of truth is file A."
)


def send(messages, label):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 1},
    }
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            body = resp.read().decode()
            print(f"[{label}] HTTP 200 in {time.time() - t0:.1f}s")
            return 200, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[{label}] HTTP {e.code} in {time.time() - t0:.1f}s")
        print(f"    {body[:500]}")
        return e.code, body
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] EXC {type(e).__name__}: {e}")
        return None, str(e)


def main() -> int:
    tokenizer = get_tokenizer()

    # The context window the server really uses — not the model's maximum.
    from llama_index.llms.ollama.base import Ollama

    probe = Ollama(model=MODEL, base_url=OLLAMA)
    real_window = resolve_context_window(probe) or CONTEXT_TOKENS
    budget = context_budget(real_window)

    # ------------------------------------------------------------------
    # Build the same oversized conversation that reproduces the failure.
    # ------------------------------------------------------------------
    filler = (
        "Митлушко Андрій Романович | 12,5 | 3400,00 | ХАРКІВ | 2026-10-01 | "
        "мережа | активна | договір | 1234567890\n"
    )
    target_chars = int(CONTEXT_TOKENS * 3.5 * 1.4)  # deliberately huge
    chunk = filler * 2000

    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are Torvalds."),
        ChatMessage(role=MessageRole.USER, content=REQUEST),
    ]
    total = 0
    idx = 0
    while total < target_chars:
        messages.append(
            ChatMessage(
                role=MessageRole.ASSISTANT,
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "function": {
                                "name": "read_xlsx_file",
                                "arguments": {"path": f"file_{idx}.xlsx"},
                            }
                        }
                    ]
                },
            )
        )
        messages.append(ChatMessage(role=MessageRole.TOOL, content=chunk))
        total += len(chunk)
        idx += 1

    size_mb = sum(len(str(m.content or "")) for m in messages) / 1e6
    print("=" * 78)
    print("VERIFY THE FIX — same oversized prompt, guarded")
    print("=" * 78)
    print(f"conversation : {len(messages)} messages, {size_mb:.2f} MB")
    print(f"tokens       : ~{count_tokens(messages, tokenizer)} "
          f"(real context window {real_window}, budget {budget})")
    print(f"user query   : {has_user_query(messages)}")

    # ------------------------------------------------------------------
    # 1. Without the guard — the known failure.
    # ------------------------------------------------------------------
    raw = [
        {
            "role": m.role.value,
            "content": m.content or "",
            **(
                {"tool_calls": m.additional_kwargs["tool_calls"]}
                if m.additional_kwargs.get("tool_calls")
                else {}
            ),
        }
        for m in messages
    ]
    status, body = send(raw, "unguarded")
    reproduced = status == 500 and "No user query found" in body
    print(f"    => failure reproduced without the guard: {reproduced}")

    # ------------------------------------------------------------------
    # 2. With the guard — the fix.
    # ------------------------------------------------------------------
    window = select_context_window(
        messages,
        budget_tokens=budget,
        tokenizer=tokenizer,
        original_request=REQUEST,
    )
    print(f"\nguarded      : {len(window)} messages, "
          f"~{count_tokens(window, tokenizer)} tokens")
    print(f"user query   : {has_user_query(window)}")

    guarded = [
        {
            "role": m.role.value,
            "content": m.content or "",
            **(
                {"tool_calls": m.additional_kwargs["tool_calls"]}
                if m.additional_kwargs.get("tool_calls")
                else {}
            ),
        }
        for m in window
    ]
    status, body = send(guarded, "guarded")
    fixed = status == 200

    print("\n" + "=" * 78)
    if reproduced and fixed:
        print("RESULT: PASS — the failure reproduces without the guard and is")
        print("        gone with it.")
        return 0
    if fixed:
        print("RESULT: PASS — the guarded prompt is accepted by the server.")
        return 0
    print("RESULT: FAIL — the guarded prompt was rejected:")
    print(body[:800])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
