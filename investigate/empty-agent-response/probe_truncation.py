#!/usr/bin/env python3
"""
Probe: what the server does with a prompt that is larger than the window.

The reported run's last model call carried 7494 prompt tokens against a
window of 8192 — 91 % of it.  The question this probe answers is what the
server does when the prompt does *not* fit: does it truncate, does it shift,
and what does the model answer then?

A small model with a small window is used, so the answer comes in seconds
instead of minutes.  The server's behaviour does not depend on the size of
the model.

Usage:
    python probe_truncation.py
    python probe_truncation.py --model qwen2.5-coder:7b-instruct-q4_K_M
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
DEFAULT_URL = "http://localhost:11434"

FILLER = "The quick brown fox jumps over the lazy dog. " * 40


def ask(url: str, model: str, text: str, num_ctx: int) -> dict:
    """Send one streaming request and report what came back."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": text},
        ],
        "stream": True,
        "options": {"num_ctx": num_ctx},
    }

    content: list[str] = []
    final: dict = {}
    with requests.post(
        f"{url}/api/chat", json=payload, stream=True, timeout=600
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            content.append((chunk.get("message") or {}).get("content") or "")
            if chunk.get("done"):
                final = chunk

    return {
        "content": "".join(content),
        "prompt_eval_count": final.get("prompt_eval_count"),
        "eval_count": final.get("eval_count"),
        "done_reason": final.get("done_reason"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--num-ctx", type=int, default=1024)
    args = parser.parse_args()

    print(f"model    : {args.model}")
    print(f"num_ctx  : {args.num_ctx}")
    print()
    print(f"{'filler x':>10} {'~prompt':>9} {'server prompt_eval':>19} "
          f"{'completion':>11} {'done_reason':>12}  answer")
    print("-" * 100)

    for repeats in (1, 2, 4, 8, 16):
        text = ("What is the capital of France? Answer in one word. " * 3
                + FILLER * repeats)
        result = ask(args.url, args.model, text, args.num_ctx)
        answer = result["content"].strip().replace("\n", " ")[:40]
        print(
            f"{repeats:>10} {len(text) // 4:>9} "
            f"{str(result['prompt_eval_count']):>19} "
            f"{str(result['eval_count']):>11} "
            f"{str(result['done_reason']):>12}  {answer!r}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
