#!/usr/bin/env python3
"""
Probe: the raw chunks of one request, so the empty answer can be seen.

``probe_long_prompt.py`` showed that the model produces tokens and that
*all* of them land in ``thinking`` while ``content`` stays empty.  This
probe prints the chunks themselves — the first ones, the last ones and the
``done`` record — so the shape of the answer is visible.

Usage:
    python probe_raw_chunks.py --repeats 0
    python probe_raw_chunks.py --repeats 0 --think false
"""
from __future__ import annotations

import argparse
import json
import sys

import requests

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from probe_long_prompt import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_URL,
    NUM_CTX,
    TOOL_SCHEMA,
    build_conversation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--num-ctx", type=int, default=NUM_CTX)
    parser.add_argument("--repeats", type=int, default=0)
    parser.add_argument("--think", default="unset", choices=["unset", "true", "false"])
    parser.add_argument("--head", type=int, default=6)
    parser.add_argument("--tail", type=int, default=8)
    args = parser.parse_args()

    payload = {
        "model": args.model,
        "messages": build_conversation(args.repeats),
        "tools": TOOL_SCHEMA,
        "stream": True,
        "options": {"num_ctx": args.num_ctx},
    }
    if args.think != "unset":
        payload["think"] = args.think == "true"

    chunks = []
    with requests.post(
        f"{args.url}/api/chat", json=payload, stream=True, timeout=900
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunks.append(json.loads(line))

    print(f"chunks: {len(chunks)}")
    print("--- first ---")
    for chunk in chunks[: args.head]:
        print(" ", json.dumps(chunk.get("message")), "done=", chunk.get("done"))
    print("--- last ---")
    for chunk in chunks[-args.tail :]:
        print(" ", json.dumps(chunk.get("message")), "done=", chunk.get("done"))

    final = chunks[-1] if chunks else {}
    print("--- done record ---")
    for key in ("done", "done_reason", "prompt_eval_count", "eval_count",
                "total_duration", "load_duration", "context"):
        if key in final:
            print(f"  {key}: {final[key]!r}")

    content = "".join((c.get("message") or {}).get("content") or "" for c in chunks)
    thinking = "".join((c.get("message") or {}).get("thinking") or "" for c in chunks)
    print(f"--- totals --- content_len={len(content)} thinking_len={len(thinking)}")
    if content:
        print("CONTENT:", repr(content))
    print("THINKING (last 400):", repr(thinking[-400:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
