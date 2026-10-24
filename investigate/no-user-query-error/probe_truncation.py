"""
Test: what does Ollama do when the prompt exceeds the model's context window?

The qwen3.5-family template raises "No user query found in messages." when
the message list it receives has no ``user`` message that is not a
``<tool_response>`` wrapper.

Hypothesis under test: when a long agent run pushes the prompt past the
context window, the Ollama server truncates the prompt (keeping the most
recent tokens).  The user query sits at the *front* of the message list, so
it is truncated away, and the template then raises the target error.

This script sends a message list that is deliberately larger than the
model's context window and reports what the server does.

Usage:
    python investigate/no-user-query-error/probe_truncation.py
"""

import json
import time
import urllib.error
import urllib.request

OLLAMA = "http://localhost:11434"
MODEL = "richardyoung/qwen3.6-27b-abliterated:Q4_K_M"

# The model's context window, from `ollama show`.
CONTEXT_TOKENS = 262144


def approx_tokens(text: str) -> int:
    """Rough token estimate (~3.5 chars/token for English+cyrillic)."""
    return len(text) // 3


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
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = resp.read().decode()
            print(f"[{label}] HTTP 200 in {time.time() - t0:.1f}s")
            print(f"    {body[:200]}")
            return 200, body
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[{label}] HTTP {e.code} in {time.time() - t0:.1f}s")
        print(f"    {body[:600]}")
        return e.code, body
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] EXC {type(e).__name__}: {e}")
        return None, str(e)


def main() -> None:
    print("=" * 78)
    print("TRUNCATION PROBE")
    print(f"model: {MODEL}   context window: {CONTEXT_TOKENS} tokens")
    print("=" * 78)

    # ------------------------------------------------------------------
    # A message list shaped exactly like the agent's: the user query first,
    # then a long run of assistant/tool pairs.
    # ------------------------------------------------------------------
    filler_unit = (
        "Митлушко Андрій Романович | 12,5 | 3400,00 | ХАРКІВ | 2026-10-01 | "
        "мережа | активна | договір | 1234567890\n"
    )
    # Aim for ~1.4x the context window so truncation is guaranteed.
    target_chars = int(CONTEXT_TOKENS * 3.5 * 1.4)
    print(f"building a prompt of about {target_chars} characters "
          f"(~{target_chars // 3} tokens)...")

    messages = [
        {
            "role": "user",
            "content": (
                "in project folder: take a file A = OV_2026_10.xlsx file B = "
                "shtab.xlsx for person 'Митлушко Андрій Романович' merge "
                "entities from column 'D' in file A and column C in file B"
            ),
        }
    ]

    chunk = filler_unit * 2000
    total = 0
    idx = 0
    while total < target_chars:
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_xlsx_file",
                            "arguments": {"path": f"file_{idx}.xlsx"},
                        }
                    }
                ],
            }
        )
        messages.append({"role": "tool", "content": chunk})
        total += len(chunk)
        idx += 1

    size_mb = sum(len(json.dumps(m)) for m in messages) / 1e6
    print(f"message list: {len(messages)} messages, {size_mb:.2f} MB, "
          f"~{total // 3} tokens of tool output")

    status, body = send(messages, "over-context")

    if status == 500 and "No user query found" in body:
        print("\n==> CONFIRMED: the server truncated the prompt, the user query")
        print("    at the front was dropped, and the template raised the")
        print("    target error.")
    elif body and "context" in body.lower():
        print("\n==> The server reports a context-length error instead of "
              "truncating.")
    else:
        print("\n==> inconclusive — see the raw response above.")


if __name__ == "__main__":
    main()
