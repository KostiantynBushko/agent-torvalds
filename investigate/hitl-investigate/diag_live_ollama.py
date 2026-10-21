#!/usr/bin/env python3
"""
Diagnostic 6 — Live proof against a real Ollama instance.

Reproduces the *production* symptom end-to-end:

  1. Build the agent exactly like ``agent-torvalds.py`` does
     (``create_agent`` + ``bind_callback_manager``).
  2. Ask the model something that ends in a question.
  3. Observe whether the HITL handler detects a question and prompts.

This uses the real ``Ollama`` LLM, so the ``raw`` payload shape is the
production one (``{"message": {"role": ..., "content": ...}, ...}``) and the
streaming path (``astream_chat``) is exercised.

Requires a running Ollama server.  Override the model with::

    HITL_DIAG_MODEL=<model> python investigate/hitl-investigate/diag_live_ollama.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.base import BaseCallbackHandler
from llama_index.core.callbacks.schema import EventPayload
from llama_index.llms.ollama import Ollama
from rich.console import Console

from components.human_loop_handler import HumanLoopHandler
from components.stats_handler import bind_callback_manager

MODEL = os.environ.get("HITL_DIAG_MODEL", "qwen2.5-coder:7b-instruct-q4_K_M")

QUESTION_PROMPT = (
    "Before you answer, ask the user one short confirmation question that ends "
    "with a question mark, for example: 'Shall I proceed?'. "
    "Then answer briefly."
)


class ProbeHandler(BaseCallbackHandler):
    """Records LLM callback payloads so we can see the real raw shape."""

    def __init__(self) -> None:
        super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])
        self.llm_ends: List[dict] = []

    def on_event_end(self, event_type, payload=None, event_id="", **kwargs):
        name = str(getattr(event_type, "value", event_type))
        if name == "llm":
            self.llm_ends.append(payload or {})

    def on_event_start(self, event_type, payload=None, event_id="", **kwargs):
        return event_id

    def start_trace(self, trace_id=None):
        pass

    def end_trace(self, trace_id=None, trace_map=None):
        pass


async def main() -> int:
    print("=" * 78)
    print(f"DIAG 6 — Live proof against Ollama (model={MODEL})")
    print("=" * 78)

    console = Console()
    probe = ProbeHandler()
    hitl = HumanLoopHandler(
        input_method="console",
        default_timeout=5,
        enable_hitl=True,
        console=console,
    )

    cm = CallbackManager([probe, hitl])
    llm = Ollama(model=MODEL, base_url=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    bind_callback_manager(None, None)  # no-op sanity check
    llm.callback_manager = cm

    print("\n--- calling the live LLM ---")
    try:
        resp = await llm.achat([ChatMessage(role="user", content=QUESTION_PROMPT)])
    except Exception as exc:
        print(f"[ERROR] could not reach Ollama: {exc}")
        return 1

    print(f"response type : {type(resp).__name__}")
    print(f"response text : {resp.message.content!r}")

    print("\n--- LLM event-end payload (real Ollama shape) ---")
    if not probe.llm_ends:
        print("  NO LLM EVENT RECEIVED")
    for p in probe.llm_ends:
        r = p.get(EventPayload.RESPONSE)
        print(f"  payload keys : {sorted(p.keys())}")
        print(f"  RESPONSE type: {type(r).__name__}")
        print(f"  has .text?   : {hasattr(r, 'text')}")
        print(f"  .message.content: {getattr(getattr(r, 'message', None), 'content', None)!r}")
        raw = getattr(r, "raw", None)
        if isinstance(raw, dict):
            print(f"  .raw keys    : {sorted(raw.keys())}")
            print(f"  .raw['message']: {raw.get('message')!r}")
            print(f"  .raw.get('content'): {raw.get('content')!r}")
            print(f"  .raw.get('text')   : {raw.get('text')!r}")

        extracted = hitl._extract_text(r)
        print(f"  >>> _extract_text() -> {extracted!r}")
        print(f"  >>> _is_question()  -> {hitl._is_question(extracted)}")

    # Now the same question, but with the FIXED extractor.
    print("\n--- with the FIXED extractor ---")
    for p in probe.llm_ends:
        r = p.get(EventPayload.RESPONSE)
        message = getattr(r, "message", None)
        fixed = getattr(message, "content", None) or ""
        print(f"  fixed extraction -> {fixed!r}")
        print(f"  _is_question()   -> {hitl._is_question(fixed)}")
        break

    print("\n--- VERDICT (live) ---")
    if probe.llm_ends:
        r = probe.llm_ends[0].get(EventPayload.RESPONSE)
        extracted = hitl._extract_text(r)
        if not extracted:
            print("[CONFIRMED] The live Ollama payload breaks _extract_text() ->")
            print("            HITL cannot detect a question in production.")
        else:
            print("[?] _extract_text() returned:", extracted[:80])
    else:
        print("[?] No LLM event was recorded.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
