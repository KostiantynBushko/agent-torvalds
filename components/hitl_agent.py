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
from components.hitl_question import (
    QUESTION_PATTERNS,
    Question,
    detect_input_type,
    is_question,
    normalise_question,
    split_question,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Question detection patterns (compiled regexes for performance)
# ---------------------------------------------------------------------------

# The shared question-detection patterns.  They live in
# ``components.hitl_question`` so that the agent, the consumer and the
# callback handler agree on what a question is — the copy that used to live
# here and the one in ``human_loop_handler`` had already drifted apart.
_QUESTION_PATTERNS: List[re.Pattern] = QUESTION_PATTERNS

# Key used to persist the pending question across workflow step replays.
_PENDING_QUESTION_KEY = "hitl_pending_question"

# Key used to remember which questions were already answered, so the agent
# never asks the same question twice in one run.
_ANSWERED_QUESTIONS_KEY = "hitl_answered_questions"


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

    # Cached context-window information for the context guard.  Reading the
    # LLM metadata costs a round-trip to the Ollama server, so it is done
    # once per agent instance.
    _context_window_cache: Optional[int] = None
    _tokenizer_cache: Optional[Any] = None
    _tool_schema_cache: Optional[int] = None

    # ------------------------------------------------------------------
    # Context guard
    # ------------------------------------------------------------------

    async def take_step(
        self,
        ctx: Context,
        llm_input: List[ChatMessage],
        tools: Any,
        memory: Any,
    ) -> Any:
        """Trim the prompt to the model's context window before the call.

        ``FunctionAgent`` never trims its scratchpad, so a long tool-using
        run can grow the prompt past the model's context window.  The
        Ollama server then truncates the prompt, keeping the most recent
        tokens, which drops the user query at the front of the conversation
        — and the model template refuses to render a conversation without a
        user message ("No user query found in messages.").

        The guard keeps the request the user made and the most recent turns
        that still fit.  It also restores the request when the chat memory
        trimmed it away.
        """
        from components.context_guard import select_context_window_split

        scratchpad: List[ChatMessage] = await ctx.store.get(
            self.scratchpad_key, default=[]
        )

        budget = self._context_budget()
        if budget <= 0:
            return await super().take_step(ctx, llm_input, tools, memory)

        # The tool schemas are sent with every request and take up prompt
        # space as well, so they have to be part of the budget.
        budget -= self._tool_schema_tokens(tools)
        if budget <= 0:
            return await super().take_step(ctx, llm_input, tools, memory)

        original_request = await ctx.store.get("user_msg_str")
        combined = [*llm_input, *scratchpad]

        head, tail = select_context_window_split(
            combined,
            split_at=len(llm_input),
            budget_tokens=budget,
            tokenizer=self._tokenizer(),
            original_request=original_request or None,
        )

        if (head, tail) != (list(llm_input), list(scratchpad)):
            # Keep the scratchpad in sync with what was actually sent, so the
            # next iteration starts from the trimmed conversation instead of
            # re-growing the prompt.
            await ctx.store.set(self.scratchpad_key, tail)

        return await super().take_step(ctx, head, tools, memory)

    def _context_budget(self) -> int:
        """Return the number of prompt tokens the agent may use.

        The context window is read from the LLM metadata, which for Ollama
        means a round-trip to the server.  The value is cached because
        ``take_step`` runs on every iteration.
        """
        if self._context_window_cache is None:
            try:
                self._context_window_cache = int(
                    self.llm.metadata.context_window
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not read the context window from the LLM (%s) — "
                    "the context guard is disabled for this run.",
                    exc,
                )
                self._context_window_cache = 0

        if self._context_window_cache <= 0:
            return 0

        from components.context_guard import context_budget

        return context_budget(self._context_window_cache)

    def _tokenizer(self):
        """Return the cached tokenizer used to size the prompt."""
        if self._tokenizer_cache is None:
            from components.context_guard import get_tokenizer

            self._tokenizer_cache = get_tokenizer()
        return self._tokenizer_cache

    def _tool_schema_tokens(self, tools) -> int:
        """Return the number of tokens the tool schemas take up.

        The schemas are part of the prompt but not part of the message
        list, so they have to be accounted for separately.
        """
        if not tools:
            return 0
        if self._tool_schema_cache is None:
            import json

            try:
                specs = [
                    tool.metadata.to_openai_tool(skip_length_check=True)
                    for tool in tools
                ]
                blob = json.dumps(specs)
            except Exception as exc:  # noqa: BLE001 - be forgiving here
                logger.debug("Could not size the tool schemas: %s", exc)
                blob = ""
            self._tool_schema_cache = len(self._tokenizer()(blob))
        return self._tool_schema_cache

    # ------------------------------------------------------------------
    # Question detection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(obj: Any) -> str:
        """Extract the assistant text from a response payload."""
        return extract_text(obj)

    def _split_question(self, text: str) -> Optional[Question]:
        """Split *text* into the question and the report around it.

        When the operator configured their own detection patterns the whole
        message is kept as the question: the custom patterns define what a
        question is, and the splitter cannot know that.
        """
        if self.hitl_question_patterns is not None:
            if not self._is_question(text):
                return None
            return Question(question=text.strip(), context="", options=())
        return split_question(text)

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

        # The question is separated from the report around it: the whole
        # message is *not* the question (investigation defect D1).  What
        # surrounds the question travels in the event's ``context``.
        split = self._split_question(text)
        if split is None:
            return await super().parse_agent_output(ctx, ev)

        question_text = split.question

        # Never ask the same question twice in one run: the answer may well
        # be "no", and re-asking would loop until the iteration budget runs
        # out.  The comparison uses the *normalised* question, so a
        # rephrasing of the same question is recognised as well (D4).
        if await self._was_answered(ctx, question_text):
            logger.debug(
                "HITL question already answered — continuing: %r",
                question_text[:80],
            )
            return await super().parse_agent_output(ctx, ev)

        question_id, waiter_id, is_new = await self._resolve_question_identity(
            ctx, question_text
        )

        timeout = self.hitl_default_timeout
        default_answer = self.hitl_default_answer
        # The input type follows the *question*, never the answer (D2).
        input_type = detect_input_type(question_text, split.options)

        if is_new:
            # The workflow replays the step when the answer arrives, so this
            # body runs twice for one question.  Log the detection once (D5).
            logger.info(
                "HITL question detected (%s, type=%s, timeout=%s)",
                question_id,
                input_type,
                describe_timeout(timeout),
            )

        question_event = AgentQuestionEvent(
            prefix="Agent asks: ",
            question=question_text,
            question_id=question_id,
            timeout=timeout,
            default_answer=default_answer,
            input_type=input_type,
            options=list(split.options),
            # The report around the question travels with it.
            context=split.context or None,
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
        await self._mark_answered(ctx, question_text)

        # Feed the human's answer back into the conversation so the agent
        # can act on it.  The assistant message is already in the
        # scratchpad (appended by ``take_step``), so the answer follows it
        # as a user turn.
        scratchpad: List[ChatMessage] = await ctx.store.get(
            self.scratchpad_key, default=[]
        )
        scratchpad.append(
            ChatMessage(
                role="user",
                content=self._answer_message(answer, was_timeout, timeout),
            )
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

    @staticmethod
    def _answer_message(answer: str, was_timeout: bool, timeout: int) -> str:
        """Return the message the model receives as the human's answer.

        A timeout is not an answer.  When the timeout expires the model
        has to be told that nobody answered, otherwise it reads the
        fallback answer as the human's own decision — and with the shipped
        default (no fallback answer at all) it reads an empty turn, which
        for a yes/no question is indistinguishable from a "no".

        The operator's rule: the agent waits, and when the timeout expires
        it acts on its own judgement.  For that to happen the model has to
        know that the question went unanswered.
        """
        if not was_timeout:
            return f"[Human response] {answer}"

        limit = "unlimited" if is_no_timeout(timeout) else describe_timeout(timeout)
        return (
            f"[No human response — the {limit} wait ended without an answer. "
            f"The question was not answered; act on your own judgement.]"
        )

    async def _was_answered(self, ctx: Context, text: str) -> bool:
        """Return ``True`` if *text* was already answered in this run.

        The key is the *normalised* question, so "Shall I create the branch
        X?" and "Should I create the branch X?" are recognised as the same
        question — the agent must not ask again after the answer was "no".
        """
        key = normalise_question(text)
        if not key:
            return False
        answered = await ctx.store.get(_ANSWERED_QUESTIONS_KEY, default=None)
        if not isinstance(answered, list):
            return False
        return key in answered

    async def _mark_answered(self, ctx: Context, text: str) -> None:
        """Remember that *text* has been answered in this run."""
        key = normalise_question(text)
        if not key:
            return
        answered = await ctx.store.get(_ANSWERED_QUESTIONS_KEY, default=None)
        if not isinstance(answered, list):
            answered = []
        if key not in answered:
            answered.append(key)
        await ctx.store.set(_ANSWERED_QUESTIONS_KEY, answered)

    async def _resolve_question_identity(
        self, ctx: Context, text: str
    ) -> tuple[str, str, bool]:
        """Return ``(question_id, waiter_id, is_new)`` for the pending question.

        The workflow runtime replays a suspended step from the beginning when
        the awaited event arrives.  A fresh id on every replay would publish
        a new question each time and the run would never settle, so the
        identity is persisted in the workflow store and reused until the
        question is answered.

        ``is_new`` tells the caller whether this is the *first* sighting of
        the question.  On the replay the same identity comes back, so the
        "HITL question detected" line is logged once and not once per
        replay (investigation defect D5).
        """
        pending = await ctx.store.get(_PENDING_QUESTION_KEY, default=None)
        if isinstance(pending, dict) and pending.get("question") == text:
            return str(pending["question_id"]), str(pending["waiter_id"]), False

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
        return question_id, waiter_id, True
