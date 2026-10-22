"""
HITL Agent — Human-in-the-Loop support for the LlamaIndex FunctionAgent.

This module provides :class:`HITLFunctionAgent`, a drop-in replacement for
``llama_index.core.agent.workflow.FunctionAgent`` that adds a genuine
Human-in-the-Loop round-trip.

Why a custom agent?
-------------------
The previous implementation tried to implement HITL *around* the agent:

* the callback handler detected a question in the LLM output and emitted an
  ``AgentQuestionEvent`` with ``ctx.send_event()``;
* the consumer received it and sent an ``AgentAnswerEvent`` back.

That never worked, for three independent reasons (see
``investigate/hitl-investigate/``):

1. ``ctx.send_event()`` dispatches to *step queues*; it does **not** write to
   the event stream that the consumer reads, and external code cannot call
   ``ctx.write_event_to_stream()`` at all — so the question was silently
   dropped.
2. No workflow step accepted ``AgentAnswerEvent``, so the answer could never
   reach the agent.
3. The agent never *waited*, so it continued as if the human had never
   spoken.

The framework already ships the correct mechanism: a step that waits for an
``InputRequiredEvent`` publishes the question to the event stream and the
workflow pauses; the caller answers with a ``HumanResponseEvent``, which
resumes the waiting step.  This module implements exactly that.

Flow
----
::

    parse_agent_output (overridden)
        │
        ├─ output has tool calls ─────► delegate to the base implementation
        │
        ├─ output is not a question ───► delegate to the base implementation
        │
        └─ output is a question
              │
              ├─ ctx.wait_for_event(AgentAnswerEvent,
              │                     waiter_event=AgentQuestionEvent(...))
              │        └─ the framework publishes AgentQuestionEvent
              │           to the event stream and suspends the step
              │
              ├─ consumer prompts the user and sends AgentAnswerEvent
              │
              └─ the step is replayed with the answer, the answer is fed
                 back into the agent scratchpad, and the agent continues
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any, List, Optional, Union

from llama_index.core.agent.workflow import (
    AgentInput,
    AgentOutput,
    FunctionAgent,
    ToolCall,
)
from llama_index.core.base.llms.types import ChatMessage
from workflows import Context, step
from workflows.events import StopEvent

from components.hitl_timeout import (
    NO_TIMEOUT,
    describe_timeout,
    is_no_timeout,
    normalize_timeout,
)
from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Question detection patterns (compiled regexes for performance)
# ---------------------------------------------------------------------------

_QUESTION_PATTERNS: List[re.Pattern] = [
    # Explicit question mark at end of sentence
    re.compile(r"\w+\s*\?$", re.MULTILINE),
    # Direct requests for confirmation / approval
    re.compile(r"\b(confirm|approve|proceed|continue|go ahead)\b", re.IGNORECASE),
    # Destructive operations phrased as an implicit request.  The verb must
    # start a sentence (optionally after a politeness word) so that ordinary
    # prose which merely *mentions* the operation — "Understood, I will not
    # delete it." — is not mistaken for a question.  Without that anchor the
    # agent would keep asking the human the same thing forever.
    re.compile(
        r"(?:^|[.!?]\s*)\s*"
        r"(?:please\s+|could you\s+|can you\s+|would you\s+|do you\s+)?"
        r"\b(delete|drop|remove|overwrite|destroy|format|uninstall)\b",
        re.IGNORECASE,
    ),
    # Yes/No prompts
    re.compile(r"\b(yes|no|y|n)\b.*\b(yes|no|y|n)\b", re.IGNORECASE),
    # "Do you want to ..." / "Would you like to ..."
    re.compile(r"\b(do you|would you)\b.*\b(want|like|prefer)\b", re.IGNORECASE),
    # Explicit HITL markers (agent can be instructed to emit these)
    re.compile(r"\[HITL\]|\[QUESTION\]|\[NEEDS_INPUT\]", re.IGNORECASE),
]

# Key used to persist the pending question across workflow step replays.
_PENDING_QUESTION_KEY = "hitl_pending_question"

# Key used to remember which questions were already answered, so the agent
# never asks the same question twice in one run.
_ANSWERED_QUESTIONS_KEY = "hitl_answered_questions"


def detect_input_type(message: str) -> str:
    """Heuristically detect the best input type from the message text."""
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in ("password", "secret", "credential")):
        return "password"
    if any(kw in msg_lower for kw in ("yes", "no", "confirm", "proceed", "continue")):
        return "yesno"
    return "text"


def is_question(text: str) -> bool:
    """Return ``True`` if *text* appears to contain a question."""
    if not text:
        return False
    for pattern in _QUESTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


def extract_text(obj: Any) -> str:
    """Best-effort text extraction from LlamaIndex response objects.

    The payload that reaches the agent is a ``ChatResponse`` whose text lives
    in ``response.message.content`` — *not* in ``.text`` and *not* directly in
    ``.raw``.  The old extractor missed every branch and returned ``""``, so
    no question was ever detected (investigation defect #1).

    The following shapes are handled:

    * ``str`` — returned as-is.
    * ``ChatResponse`` — ``response.message.content`` (or the text blocks).
    * ``ChatMessage`` — ``.content`` / text blocks.
    * ``CompletionResponse`` — ``.text``.
    * ``raw`` dicts — ``{"content": ...}`` (LlamaIndex mocks) and
      ``{"message": {"content": ...}}`` (Ollama), where ``raw["message"]``
      may be either a dict or a pydantic model.
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj

    # ChatResponse -> response.message.content
    message = getattr(obj, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if content:
            return str(content)
        blocks = getattr(message, "blocks", None)
        if blocks:
            parts = [
                getattr(b, "text", "")
                for b in blocks
                if getattr(b, "text", None)
            ]
            if parts:
                return "".join(parts)

    # ChatMessage -> .content
    content = getattr(obj, "content", None)
    if isinstance(content, str) and content:
        return content

    # CompletionResponse -> .text
    text = getattr(obj, "text", None)
    if text:
        return str(text)

    # raw dict shapes
    raw = getattr(obj, "raw", None)
    if isinstance(raw, dict):
        for key in ("text", "content"):
            if raw.get(key):
                return str(raw[key])
        raw_message = raw.get("message")
        if isinstance(raw_message, dict) and raw_message.get("content"):
            return str(raw_message["content"])
        # Ollama's raw["message"] is a pydantic Message, not a dict
        if raw_message is not None:
            raw_content = getattr(raw_message, "content", None)
            if raw_content:
                return str(raw_content)

    return ""


class HITLFunctionAgent(FunctionAgent):
    """``FunctionAgent`` with a real Human-in-the-Loop round-trip.

    The agent asks the human a question when the LLM produces a final
    textual answer that looks like a question, waits for the answer, feeds
    the answer back into the conversation and continues.

    Attributes:
        hitl_enabled: Master switch for HITL.  When ``False`` the agent
            behaves exactly like a plain ``FunctionAgent``.
        hitl_default_timeout: Default number of seconds to wait for an
            answer before falling back to ``hitl_default_answer``.  ``-1``
            (the default) means *no timeout*: the agent waits for the
            human indefinitely.
        hitl_default_answer: Fallback answer used on timeout.
        hitl_question_patterns: Optional list of regex strings overriding
            the built-in question detection patterns.
    """

    hitl_enabled: bool = True
    hitl_default_timeout: int = NO_TIMEOUT
    hitl_default_answer: str = ""
    hitl_question_patterns: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # Question detection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(obj: Any) -> str:
        """Extract the assistant text from a response payload."""
        return extract_text(obj)

    def _is_question(self, text: str) -> bool:
        """Return ``True`` if *text* appears to contain a question."""
        if not text:
            return False
        if self.hitl_question_patterns is not None:
            patterns = [
                re.compile(p, re.IGNORECASE | re.MULTILINE)
                for p in self.hitl_question_patterns
            ]
        else:
            patterns = _QUESTION_PATTERNS
        for pattern in patterns:
            if pattern.search(text):
                return True
        return False

    # ------------------------------------------------------------------
    # The HITL round-trip
    # ------------------------------------------------------------------

    @step
    async def parse_agent_output(
        self, ctx: Context, ev: AgentOutput
    ) -> Union[StopEvent, AgentInput, ToolCall, None]:
        """Parse the agent output, asking the human when it is a question.

        This overrides ``BaseWorkflowAgent.parse_agent_output``.  When the
        LLM output is not a question the base implementation is used
        verbatim, so the normal agent flow is completely unaffected.

        When the output *is* a question, the step waits for an
        ``AgentAnswerEvent``.  The framework publishes the
        ``AgentQuestionEvent`` to the event stream and suspends the step;
        the consumer prompts the user and sends the answer back, which
        resumes this step with the answer in hand.
        """
        # Tool calls take priority: the agent wants to act, not to ask.
        if ev.tool_calls:
            return await super().parse_agent_output(ctx, ev)

        if not self.hitl_enabled:
            return await super().parse_agent_output(ctx, ev)

        text = self._extract_text(ev.response)
        if not self._is_question(text):
            return await super().parse_agent_output(ctx, ev)

        # Never ask the same question twice in one run: the answer may well
        # be "no", and re-asking would loop until the iteration budget runs
        # out.
        if await self._was_answered(ctx, text):
            logger.debug("HITL question already answered — continuing: %r", text[:80])
            return await super().parse_agent_output(ctx, ev)

        question_id, waiter_id = await self._resolve_question_identity(ctx, text)

        timeout = self.hitl_default_timeout
        default_answer = self.hitl_default_answer
        input_type = detect_input_type(text)

        logger.info(
            "HITL question detected (%s, type=%s, timeout=%s)",
            question_id,
            input_type,
            describe_timeout(timeout),
        )

        question_event = AgentQuestionEvent(
            prefix="Agent asks: ",
            question=text,
            question_id=question_id,
            timeout=timeout,
            default_answer=default_answer,
            input_type=input_type,
        )

        # Wait for the human.  ``wait_for_event`` publishes the
        # ``waiter_event`` to the event stream and suspends this step until
        # an ``AgentAnswerEvent`` with a matching ``question_id`` arrives.
        try:
            answer_event = await ctx.wait_for_event(
                AgentAnswerEvent,
                waiter_event=question_event,
                waiter_id=waiter_id,
                requirements={"question_id": question_id},
                # ``None`` means "wait forever".  The extra 5 seconds are a
                # grace period on top of a *finite* timeout, so the step
                # does not give up before the consumer had a chance to
                # answer.  With no timeout (-1) there is nothing to pad:
                # the agent waits for the human for as long as it takes.
                timeout=(
                    None
                    if is_no_timeout(timeout)
                    else normalize_timeout(timeout) + 5
                ),
            )
        except asyncio.TimeoutError:
            logger.warning(
                "HITL answer timed out for %s — using default", question_id
            )
            answer_event = AgentAnswerEvent(
                question_id=question_id,
                answer=default_answer,
                was_timeout=True,
            )

        answer = getattr(answer_event, "answer", "") or ""
        was_timeout = bool(getattr(answer_event, "was_timeout", False))
        logger.info(
            "HITL answer received for %s: %r (timeout=%s)",
            question_id,
            answer,
            was_timeout,
        )

        # The question is resolved — forget the pending identity so a later
        # question gets a fresh one, and remember it so the agent does not
        # ask the very same thing again.
        await ctx.store.set(_PENDING_QUESTION_KEY, None)
        await self._mark_answered(ctx, text)

        # Feed the human's answer back into the conversation so the agent
        # can act on it.  The assistant message is already in the
        # scratchpad (appended by ``take_step``), so the answer follows it
        # as a user turn.
        scratchpad: List[ChatMessage] = await ctx.store.get(
            self.scratchpad_key, default=[]
        )
        scratchpad.append(
            ChatMessage(role="user", content=f"[Human response] {answer}")
        )
        await ctx.store.set(self.scratchpad_key, scratchpad)

        memory = await ctx.store.get("memory")
        return AgentInput(
            input=await memory.aget(),
            current_agent_name=self.name,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _was_answered(self, ctx: Context, text: str) -> bool:
        """Return ``True`` if *text* was already answered in this run."""
        answered = await ctx.store.get(_ANSWERED_QUESTIONS_KEY, default=None)
        if not isinstance(answered, list):
            return False
        return text in answered

    async def _mark_answered(self, ctx: Context, text: str) -> None:
        """Remember that *text* has been answered in this run."""
        answered = await ctx.store.get(_ANSWERED_QUESTIONS_KEY, default=None)
        if not isinstance(answered, list):
            answered = []
        if text not in answered:
            answered.append(text)
        await ctx.store.set(_ANSWERED_QUESTIONS_KEY, answered)

    async def _resolve_question_identity(
        self, ctx: Context, text: str
    ) -> tuple[str, str]:
        """Return a stable ``(question_id, waiter_id)`` for the pending question.

        The workflow runtime replays a suspended step from the beginning when
        the awaited event arrives.  A fresh id on every replay would publish
        a new question each time and the run would never settle, so the
        identity is persisted in the workflow store and reused until the
        question is answered.
        """
        pending = await ctx.store.get(_PENDING_QUESTION_KEY, default=None)
        if isinstance(pending, dict) and pending.get("question") == text:
            return str(pending["question_id"]), str(pending["waiter_id"])

        question_id = f"hitl-{uuid.uuid4().hex[:8]}"
        waiter_id = f"hitl_waiter_{question_id}"
        await ctx.store.set(
            _PENDING_QUESTION_KEY,
            {
                "question": text,
                "question_id": question_id,
                "waiter_id": waiter_id,
            },
        )
        return question_id, waiter_id
