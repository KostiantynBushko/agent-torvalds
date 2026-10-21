#!/usr/bin/env python3
"""
Diagnostic 1 — Which callback events actually reach the HITL handler?

Registers a probe handler on a CallbackManager, binds it to the LLM the
same way production does (via components.stats_handler.bind_callback_manager),
and records every (event_type, payload) pair that arrives.

Then it answers:
  Q1: Is CBEventType.AGENT_STEP ever emitted?
  Q2: What does the LLM event-end payload contain, and does
      HumanLoopHandler._extract_text() recover the assistant text from it?

Also compares the ``raw`` payload shape of the Mock LLM
(``{"content": ...}``) against the real Ollama shape
(``{"message": {"content": ...}, ...}``) because the two differ in exactly
the way that breaks ``_extract_text()``.

No network access required.

Run from the repository root (self-development/):
    python investigate/hitl-investigate/diag_callback_events.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, List, Sequence

from pydantic import Field

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.base import BaseCallbackHandler
from llama_index.core.callbacks.schema import EventPayload
from llama_index.core.llms.mock import MockFunctionCallingLLM

from components.human_loop_handler import HumanLoopHandler

QUESTION_TEXT = (
    "Before I delete the database, shall I proceed? "
    "Do you want to continue?"
)


class QuestionLLM(MockFunctionCallingLLM):
    """Mock function-calling LLM that always answers with a question.

    ``raw`` is set to the *Ollama* shape ({"message": {"content": ...}}) so
    that the diagnostic reflects what the real production LLM emits.
    """

    call_count: int = Field(default=0)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        self.call_count += 1
        return ChatResponse(
            message=ChatMessage(role="assistant", content=QUESTION_TEXT),
            raw={
                "model": "mock",
                "message": {"role": "assistant", "content": QUESTION_TEXT},
                "done": True,
            },
        )


class ProbeHandler(BaseCallbackHandler):
    """Records every callback event it receives."""

    def __init__(self) -> None:
        super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])
        self.starts: List[tuple] = []
        self.ends: List[tuple] = []

    @staticmethod
    def _name(event_type) -> str:
        return str(getattr(event_type, "value", event_type))

    def on_event_start(self, event_type, payload=None, event_id="", **kwargs):
        self.starts.append((self._name(event_type), payload or {}))
        return event_id

    def on_event_end(self, event_type, payload=None, event_id="", **kwargs):
        self.ends.append((self._name(event_type), payload or {}))

    def start_trace(self, trace_id=None):
        pass

    def end_trace(self, trace_id=None, trace_map=None):
        pass


def describe(obj) -> str:
    if obj is None:
        return "None"
    if isinstance(obj, str):
        return f"str(len={len(obj)}) {obj[:70]!r}"
    if isinstance(obj, dict):
        return f"dict(keys={sorted(obj.keys())})"
    return type(obj).__name__


async def main() -> int:
    print("=" * 78)
    print("DIAG 1 — Callback events reaching the HITL handler")
    print("=" * 78)

    probe = ProbeHandler()
    hitl = HumanLoopHandler(input_method="console", default_timeout=5, enable_hitl=True)
    cm = CallbackManager([probe, hitl])

    llm = QuestionLLM()
    print(f"\nllm.callback_manager handlers (before bind): {llm.callback_manager.handlers}")

    # Direct LLM call with the manager bound, exactly like production does
    llm.callback_manager = cm
    print(f"llm.callback_manager is cm ? {llm.callback_manager is cm}")

    resp = await llm.achat([ChatMessage(role="user", content="delete the db")])
    print(f"\nLLM answered: {resp.message.content!r}")

    print("\n--- EVENTS RECEIVED BY PROBE ---")
    print(f"on_event_start: {len(probe.starts)}")
    for et, p in probe.starts:
        print(f"   START {et:12s} payload={describe(p)}")
    print(f"on_event_end:   {len(probe.ends)}")
    for et, p in probe.ends:
        print(f"   END   {et:12s} payload={describe(p)}")

    all_types = {t for t, _ in probe.starts} | {t for t, _ in probe.ends}
    print(f"\nAll event types seen : {sorted(all_types)}")
    print(f"AGENT_STEP emitted?  : {'agent_step' in all_types}")

    llm_ends = [(t, p) for t, p in probe.ends if t == "llm"]
    print(f"\n--- LLM EVENT-END PAYLOAD DETAIL ({len(llm_ends)}) ---")
    for i, (t, p) in enumerate(llm_ends):
        print(f"[{i}] payload keys: {sorted(p.keys())}")
        r = p.get(EventPayload.RESPONSE)
        print(f"    RESPONSE type       : {type(r).__name__}")
        print(f"    has .text attr?     : {hasattr(r, 'text')}")
        print(f"    .text value         : {getattr(r, 'text', '<absent>')!r}")
        print(f"    has .message?       : {hasattr(r, 'message')}")
        if hasattr(r, "message"):
            print(f"    .message.content    : {getattr(r.message, 'content', None)!r}")
        raw = getattr(r, "raw", None)
        print(f"    .raw type           : {type(raw).__name__}")
        if isinstance(raw, dict):
            print(f"    .raw keys           : {sorted(raw.keys())}")
            print(f"    .raw['message']     : {raw.get('message')!r}")
            print(f"    .raw.get('content') : {raw.get('content')!r}")
            print(f"    .raw.get('text')    : {raw.get('text')!r}")

        extracted = hitl._extract_text(r)
        print(f"    >>> _extract_text()  -> {extracted!r}")
        print(f"    >>> _is_question()   -> {hitl._is_question(extracted)}")
        if i == 0:
            break

    print("\n--- WHAT _extract_text ACTUALLY CHECKS (Ollama raw shape) ---")
    r = llm_ends[0][1].get(EventPayload.RESPONSE) if llm_ends else None
    if r is not None:
        print(f"  getattr(r,'text',None)  = {getattr(r, 'text', None)!r}   <- ChatResponse has NO .text")
        raw = getattr(r, "raw", None)
        if isinstance(raw, dict):
            print(f"  raw.get('text')         = {raw.get('text')!r}   <- Ollama raw has NO 'text'")
            print(f"  raw.get('content')      = {raw.get('content')!r}   <- Ollama raw has NO 'content'")
        print(f"  str(r) fallback         = {str(r)[:70]!r}   <- pydantic repr, not the answer")

    print("\n--- COMPARE: Mock raw shape (raw={'content': ...}) ---")
    mock_raw = {"content": QUESTION_TEXT}
    print(f"  raw.get('text')    = {mock_raw.get('text')!r}")
    print(f"  raw.get('content') = {mock_raw.get('content')!r}   <- Mock WOULD work by accident")
    print("  (MockFunctionCallingLLM.chat() uses raw={'content': content};")
    print("   the real Ollama LLM uses raw={'message': {'content': ...}, ...})")

    print("\n--- VERDICT (after the fix) ---")
    if "agent_step" not in all_types:
        print("[OK] CBEventType.AGENT_STEP is NEVER emitted by llama-index 0.14.x")
        print("       -> the dead AGENT_STEP branch was removed from the handler")
    if llm_ends:
        r = llm_ends[0][1].get(EventPayload.RESPONSE)
        extracted = hitl._extract_text(r)
        if not extracted or not hitl._is_question(extracted):
            print("[FAIL] _extract_text() cannot recover the assistant text from ChatResponse")
            print("       -> _is_question() always False -> HITL never prompts")
        else:
            print("[OK] question detected — the extractor reads response.message.content")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
