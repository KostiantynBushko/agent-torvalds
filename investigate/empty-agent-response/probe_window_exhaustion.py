#!/usr/bin/env python3
"""
Probe: the window fills up while the model is still answering.

The reported runs ended with an answer that was **empty**, and the last
model call of the run carried 7494 prompt tokens against a window of 8192
— 91 % of it.  Only 698 tokens were left for the answer.

This probe puts the model in exactly that position — a prompt that fills
the window — and watches what comes back:

* does the answer arrive at all?
* does the server shift the context while the model is answering?

The small model is used, so a prompt can be built that fills a small
window in seconds.  The server's behaviour does not depend on the size of
the model.

Usage:
    python probe_window_exhaustion.py
"""

from __future__ import annotations

import argparse
import json
import sys

import requests

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
DEFAULT_URL = "http://localhost:11434"

FILLER = (
    "The operator asked the agent to describe the tables of the "
    "llama_index_db database. The agent listed the relations and reported "
    "the owner, the persistence, the access method and the size of every "
    "relation it found. "
)


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
        f"{url}/api/chat", json=payload, stream=True, timeout=900
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
    print(f"{'filler x':>10} {'server prompt':>14} {'completion':>11} "
          f"{'done_reason':>12}  answer")
    print("-" * 100)

    for repeats in (1, 3, 5, 7, 9, 11, 13):
        text = (
            "List the tables of the llama_index_db database and describe "
            "every one of them in detail. " + FILLER * repeats
        )
        result = ask(args.url, args.model, text, args.num_ctx)
        answer = result["content"].strip().replace("\n", " ")[:44]
        print(
            f"{repeats:>10} {str(result['prompt_eval_count']):>14} "
            f"{str(result['eval_count']):>11} "
            f"{str(result['done_reason']):>12}  {answer!r}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
