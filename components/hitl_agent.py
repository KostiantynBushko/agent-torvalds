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
import hashlib
import json
import logging
import re
import uuid
from typing import Any, Callable, List, Optional, Union

from llama_index.core.agent.workflow import (
    AgentInput,
    AgentOutput,
    FunctionAgent,
    ToolCall,
)
from llama_index.core.base.llms.types import ChatMessage, MessageRole
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

# Key used to remember what the tools returned, so that a repetition can
# be spotted.
_TOOL_RESULTS_KEY = "hitl_tool_results"

#: The smallest prompt budget the context guard is willing to work with.
#: Below it the window cannot hold the request *and* a usable turn, and
#: the guard would have to cut into the user request — the very failure
#: it exists to prevent.  The guard is switched off instead.
MIN_PROMPT_BUDGET = 256

#: How many identical tool results in a row end the run.  Every iteration
#: of a loop costs a full model round-trip — on a local model that is
#: minutes — and the result of the repeated call does not change, so the
#: repetition cannot lead anywhere.
REPEAT_CALL_THRESHOLD = 3

#: How many tool results are remembered for the repetition check.
REPEAT_CALL_HISTORY = 8

#: Key used to remember that the model has already ended a turn without
#: saying anything in this run.
_SILENT_TURN_KEY = "hitl_silent_turn"

#: What the agent says to the model when it ended a turn without an
#: answer.  The empty turn of the model stays in the conversation, so the
#: note follows it and the model can see what it did.
SILENT_TURN_NUDGE = (
    "[Your last turn was empty: it carried no text and no tool call, so "
    "nothing happened and nothing was said. Carry on with the task — "
    "call the tools you need, and answer with text when there is "
    "nothing left to do.]"
)


def _stable_kwargs(kwargs: Any) -> str:
    """Return a stable, comparable representation of tool call arguments.

    The arguments decide whether two tool calls are *the same* call, so
    they have to be compared by value and not by insertion order.
    """
    try:
        return json.dumps(kwargs, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(kwargs)


def _blocks_of(message: Any) -> List[Any]:
    """Return the content blocks of *message*, or an empty list.

    Args:
        message: The message of the model.

    Returns:
        The blocks of the message.  An empty list when it carries none,
        or when it is not a message at all.
    """
    try:
        blocks = getattr(message, "blocks", None)
    except Exception:  # noqa: BLE001 — a payload must not break the run
        return []
    return list(blocks or [])


def _tool_result_fingerprint(result: Any) -> str:
    """Return a fingerprint of a tool call and its result.

    Two tool calls have the same fingerprint when they call the same tool
    with the same arguments and get the same answer back.  A run in which
    the same fingerprint comes back several times in a row is a loop.
    """
    name = str(getattr(result, "tool_name", "") or "")
    kwargs = _stable_kwargs(getattr(result, "tool_kwargs", None))

    output = getattr(result, "tool_output", None)
    content = getattr(output, "content", None)
    if content is None:
        content = str(output)
    try:
        content = json.dumps(content, sort_keys=True, default=str)
    except (TypeError, ValueError):
        content = str(content)

    digest = hashlib.sha256(
        f"{name}|{kwargs}|{content}".encode("utf-8", errors="replace")
    ).hexdigest()
    return f"{name}|{digest}"


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
            asks the human nothing and behaves like a plain
            ``FunctionAgent`` — with one exception, which has nothing to
            do with the human: a turn that says nothing does not end the
            run (see :meth:`_handle_silent_turn`).
        hitl_default_timeout: Default number of seconds to wait for an
            answer before falling back to ``hitl_default_answer``.  ``-1``
            (the default) means *no timeout*: the agent waits for the
            human indefinitely.
        hitl_default_answer: Fallback answer used on timeout.
        hitl_question_patterns: Optional list of regex strings overriding
            the built-in question detection patterns.
        context_guard_enabled: Master switch for the context guard.  When
            ``False`` (the default) the prompt is sent to the model exactly
            as the agent assembled it, and nothing is trimmed.  The guard
            is opt-in, because turning it on changes what the model sees.
        context_logging_enabled: Whether the size of the prompt is logged
            with every request.  On by default: the operator asked to see
            the size of the context when the request is made to the model.
    """

    hitl_enabled: bool = True
    hitl_default_timeout: int = NO_TIMEOUT
    hitl_default_answer: str = ""
    hitl_question_patterns: Optional[List[str]] = None

    #: Whether the context guard trims the prompt to the model's context
    #: window.  Off by default: the guard is opt-in
    #: (``--context-guard-on``), because turning it on changes what the
    #: model is shown, and that decision belongs to the operator.
    context_guard_enabled: bool = False

    #: Whether the size of the prompt is logged with every request.
    #:
    #: The operator asked for it on 2026-11-04: *"I need to see in the log
    #: the context size in tokens and size of bytes.  So when request is
    #: made to LLM I want to see current context size"*.  A prompt that
    #: grows silently is a prompt that one day does not fit, and the
    #: operator cannot see it coming.
    context_logging_enabled: bool = True

    #: Called with the size of the prompt and the context window of the
    #: model, every time a request goes out to the model.  The multi-window
    #: console uses it to show the size of the context in the telemetry
    #: panel; ``None`` means nobody is watching.
    #:
    #: The observer is called **before** the logging flag is checked:
    #: ``--no-context-log`` turns the *log* off, not the readout on the
    #: screen off.  An operator who does not want the size of the prompt
    #: in the log file still wants to see it while the agent works.
    context_observer: Optional[Callable[[Any, int], None]] = None

    # Cached context-window information for the context guard.  Reading the
    # LLM metadata costs a round-trip to the Ollama server, so it is done
    # once per agent instance.
    _context_window_cache: Optional[int] = None
    _tokenizer_cache: Optional[Any] = None
    _tool_schema_cache: Optional[int] = None

    # Whether the tokenizer is known to be unavailable.  The failure is
    # remembered, so it is not retried with every request.
    _tokenizer_unavailable: bool = False

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
        """Send the prompt to the model, and say how big it was.

        The prompt is the chat memory plus the scratchpad of the run, and
        the size of it is logged **before** the request goes out — so the
        line in the log describes the request that follows it.

        ``FunctionAgent`` never trims its scratchpad, so a long tool-using
        run can grow the prompt past the model's context window.  The
        Ollama server then truncates the prompt, keeping the most recent
        tokens, which drops the user query at the front of the conversation
        — and the model template refuses to render a conversation without a
        user message ("No user query found in messages.").

        The context guard keeps the request the user made and the most
        recent turns that still fit.  It also restores the request when
        the chat memory trimmed it away.

        The guard is **off by default** (``context_guard_enabled`` is
        ``False``): the prompt is then sent to the model exactly as the
        agent assembled it, and nothing is trimmed.  The operator turns it
        on with ``--context-guard-on`` (or ``TORVALDS_CONTEXT_GUARD=true``).
        """
        scratchpad: List[ChatMessage] = await ctx.store.get(
            self.scratchpad_key, default=[]
        )

        head, tail = await self._prompt_window(ctx, llm_input, scratchpad, tools)

        # The prompt is measured before the request goes out: the window
        # the agent asks the server for has to hold it.
        size = self._measure_context([*head, *tail], tools)

        # The window the server reports is the window it uses by itself.
        # When it reports none, the window is sized to the prompt — a
        # window that fits the prompt is a real one, the server honours
        # it, and it is the only one that is guaranteed to hold the
        # request.
        self._fit_window_to_prompt(size)

        # Whoever is watching is told the size of the prompt.  This
        # happens before the logging flag is checked: the flag turns the
        # log off, not the readout off.
        self._publish_context_size(size)

        # The size of the prompt is logged for every request, whether the
        # guard trimmed it or not: the operator has to see the context grow
        # to know that it is about to overflow.
        self._log_context_size([*head, *tail], tools, size)

        return await super().take_step(ctx, head, tools, memory)

    async def _prompt_window(
        self,
        ctx: Context,
        llm_input: List[ChatMessage],
        scratchpad: List[ChatMessage],
        tools: Any,
    ) -> tuple[List[ChatMessage], List[ChatMessage]]:
        """Return the messages that go to the model.

        The result is the pair ``(head, tail)``: *head* holds the messages
        of the chat memory, *tail* the turns of the run.  The base class
        assembles the prompt as ``[*llm_input, *scratchpad]``, so the
        scratchpad has to hold exactly what is sent — otherwise the prompt
        would grow without bound and the server would truncate it.

        The guard is **off by default**: the window is then the memory and
        the scratchpad exactly as they are, and nothing is trimmed.  When
        the guard is on, the window is cut down to the context window of
        the model, and the scratchpad is rewritten.
        """
        if not self.context_guard_enabled:
            # The guard stands down: the prompt goes to the model untouched.
            return list(llm_input), list(scratchpad)

        from components.context_guard import select_context_window_split

        budget = self._context_budget()
        if budget <= 0:
            return list(llm_input), list(scratchpad)

        # The tool schemas are sent with every request and take up prompt
        # space as well, so they have to be part of the budget.
        schema_tokens = self._tool_schema_tokens(tools)
        budget -= schema_tokens
        if budget < MIN_PROMPT_BUDGET:
            # The tool schemas leave so little room that the window could
            # not hold the request and a usable turn.  Cutting into the
            # request would bring back the "No user query found in
            # messages." failure the guard exists to prevent, so the
            # guard stands down.
            logger.warning(
                "Context guard: the prompt budget of %d tokens is too small "
                "(the tool schemas use %d of %d) — the guard is disabled "
                "for this run.",
                budget,
                schema_tokens,
                self._context_budget(),
            )
            return list(llm_input), list(scratchpad)

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
            # The window that is written back always ends with the *newest*
            # turn (the context guard keeps the newest turns and drops the
            # oldest ones), so the prompt changes with every iteration.
            # That is what keeps the agent moving: a window that kept the
            # same old turn would hand the model the same prompt over and
            # over, and a greedy model would answer it the same way —
            # the loop reported in
            # ``investigate/agent-loop-context-guard/``.
            await ctx.store.set(self.scratchpad_key, tail)

        return head, tail

    def _measure_context(self, messages: List[ChatMessage], tools: Any) -> Any:
        """Measure the prompt, or return ``None`` when it cannot be measured.

        A measurement is never worth a run: a tokenizer that cannot be
        loaded, a tool whose schema cannot be read and an exception of any
        kind leave the agent running, and the size is simply not there.

        Args:
            messages: The prompt that is about to be sent.
            tools: The tools that go with it.

        Returns:
            The measured size of the prompt, or ``None``.
        """
        from components.context_metrics import measure_context

        try:
            return measure_context(
                messages, tools=tools, tokenizer=self._safe_tokenizer()
            )
        except Exception as exc:  # noqa: BLE001 - a size is never worth a run
            logger.debug("Could not measure the context: %s", exc)
            return None

    def _fit_window_to_prompt(self, size: Any) -> None:
        """Make the window of the LLM hold the prompt that is about to be sent.

        The window is raised and never lowered: the server keeps the
        window it was given, and a window that changes in both directions
        makes it give the cache back and take it again with every request.

        Args:
            size: The measured size of the prompt, or ``None`` when it
                could not be measured.
        """
        if size is None:
            return

        from components.ollama_config import fit_context_window

        try:
            fit_context_window(self.llm, size.total_tokens)
        except Exception as exc:  # noqa: BLE001 - a window is never worth a run
            logger.debug(
                "Could not fit the context window to the prompt: %s", exc
            )

    def _publish_context_size(self, size: Any) -> None:
        """Show the size of the prompt to whoever is watching.

        The observer is called with the measurements of the prompt and
        the context window of the model — the two numbers the readout
        of the TUI is built from.

        It is called **before** the logging flag is checked, and that is
        the point of it: ``--no-context-log`` turns the *log* off.  The
        readout on the screen is a different thing, and the operator who
        turns the log off still wants to see the size of the context
        while the agent works.

        A measurement is never worth a run: an observer that raises is
        logged and ignored, and the agent carries on.

        Args:
            size: The measured size of the prompt, or ``None`` when it
                could not be measured.
        """
        observer = self.context_observer
        if observer is None or size is None:
            return

        try:
            observer(size, self._model_context_window())
        except Exception as exc:  # noqa: BLE001 - a size is never worth a run
            logger.debug("The context observer failed: %s", exc)

    def _log_context_size(
        self,
        messages: List[ChatMessage],
        tools: Any,
        size: Any = None,
    ) -> None:
        """Log the size of the prompt that is about to go to the model.

        The operator asked for it on 2026-11-04: *"I need to see in the log
        the context size in tokens and size of bytes.  So when request is
        made to LLM I want to see current context size"*.

        The line carries the number of messages, the number of tokens and
        the size in bytes — and the share of the context window the prompt
        takes, when the window is known.

        A measurement is never worth a run: a tokenizer that cannot be
        loaded, a tool whose schema cannot be read and an exception of any
        kind leave the agent running, and the line is simply not written.
        """
        if not self.context_logging_enabled:
            return

        from components.context_metrics import describe_context

        if size is None:
            size = self._measure_context(messages, tools)
        if size is None:
            return

        budget = self._context_budget() if self.context_guard_enabled else 0

        # The window the LLM carries is the one the server really uses.
        # When the guard is on, the window it read from the LLM is known
        # as well — it is the fallback for an LLM that does not carry one.
        window = self._model_context_window() or (self._context_window_cache or 0)

        logger.info(
            "Context: %s",
            describe_context(
                size,
                window=window or None,
                budget=budget or None,
            ),
        )
        logger.debug(
            "Context: %d messages, %d tokens (%d of them in the tool "
            "schemas), %d bytes (%d of them in the tool schemas)",
            size.messages,
            size.total_tokens,
            size.tool_schema_tokens,
            size.total_bytes,
            size.tool_schema_bytes,
        )

    def _model_context_window(self) -> int:
        """The context window of the model, or 0 when it is not known.

        The value is read from the LLM **directly** and never through
        ``llm.metadata``: the metadata asks the model server for the window
        when the LLM does not carry one, and a line in the log must not
        cost a round-trip to the server.
        """
        window = getattr(self.llm, "context_window", None)
        try:
            value = int(window)
        except (TypeError, ValueError):
            return 0
        return value if value > 0 else 0

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
            else:
                # The window the guard sizes the prompt against, and how
                # much of it the prompt may take.  The value was set on
                # the LLM by ``apply_context_window()``, so it is the
                # window the server really uses — not the maximum the
                # model advertises.
                from components.context_guard import context_budget

                logger.info(
                    "Context guard: the context window is %d tokens — the "
                    "prompt may use %d of them.",
                    self._context_window_cache,
                    context_budget(self._context_window_cache),
                )

        if self._context_window_cache <= 0:
            return 0

        from components.context_guard import context_budget

        return context_budget(self._context_window_cache)

    def _safe_tokenizer(self):
        """Return the cached tokenizer, or ``None`` when there is none.

        ``None`` means "no tokenizer": the tokens of the prompt are then
        *estimated*, and the log line says so.  A tokenizer that cannot be
        loaded is remembered, so the failure is not retried with every
        request — and it never takes the agent down.
        """
        if self._tokenizer_cache is None and not self._tokenizer_unavailable:
            from components.tokens import get_tokenizer

            self._tokenizer_cache = get_tokenizer()
            if self._tokenizer_cache is None:
                self._tokenizer_unavailable = True
        return self._tokenizer_cache

    def _tokenizer(self):
        """Return the cached tokenizer used to size the prompt.

        Raises:
            RuntimeError: when no tokenizer can be loaded.  The context
                guard needs a real tokenizer — an estimate would not fit
                the prompt to the context window of the model.
        """
        tokenizer = self._safe_tokenizer()
        if tokenizer is None:
            raise RuntimeError(
                "the tokenizer of the agent is not available — the context "
                "guard cannot size the prompt"
            )
        return tokenizer

    def _tool_schema_tokens(self, tools) -> int:
        """Return the number of tokens the tool schemas take up.

        The schemas are part of the prompt but not part of the message
        list, so they have to be accounted for separately.
        """
        if not tools:
            return 0
        if self._tool_schema_cache is None:
            from components.context_metrics import count_tokens_of, tool_schema_text

            tokens, _ = count_tokens_of(
                tool_schema_text(tools), self._safe_tokenizer()
            )
            self._tool_schema_cache = tokens
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
            # An agent that repeats the same action cannot make progress.
            # The run is stopped instead of burning the whole iteration
            # budget on it.
            repetition = await self._detect_repetition(ctx)
            if repetition is not None:
                return await self._stop_for_repetition(ctx, ev, repetition)
            return await super().parse_agent_output(ctx, ev)

        # A turn that carries neither text nor a tool call says nothing:
        # the model ended it without doing anything and without
        # answering.  The run must not end there — the operator would be
        # left with an empty box and no idea what had happened.
        if self._is_silent(ev):
            return await self._handle_silent_turn(ctx, ev)

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
    # The turn that says nothing
    # ------------------------------------------------------------------

    @staticmethod
    def _is_silent(ev: AgentOutput) -> bool:
        """Whether the turn of the model says nothing at all.

        A turn is silent when it carries no text and no tool call: the
        model ended it without doing anything and without answering.

        Args:
            ev: The output of the model.

        Returns:
            ``True`` when the turn says nothing.
        """
        if ev.tool_calls:
            return False

        # A tool call that is carried in the message itself counts as
        # well: the base class looks at ``ev.tool_calls``, but a message
        # that carries a call is not a silent turn either.
        for block in _blocks_of(ev.response):
            if str(getattr(block, "block_type", "") or "") == "tool_call":
                return False

        return not HITLFunctionAgent._extract_text(ev.response).strip()

    async def _handle_silent_turn(
        self, ctx: Context, ev: AgentOutput
    ) -> Union[StopEvent, AgentInput]:
        """Give the model one more turn when it ends the turn with nothing.

        The model ended the turn without text and without a tool call:
        nothing happened and nothing was said.  The run ended there with
        an empty answer — the operator saw an empty box and had no way
        of telling that from a run that had never started.

        So the model gets one more turn.  Its empty turn is already in
        the scratchpad — the base class puts it there — and a note that
        says what went wrong follows it.  A model that has something to
        say about that says it, and the run carries on.

        One turn, not two.  A model that says nothing once has usually
        sampled nothing once; a model that says nothing twice will say
        nothing twice, and every empty turn costs a full round-trip.

        When the model says nothing for the second time, the run ends —
        and the answer says plainly that the model ended the turn
        without an answer.

        Args:
            ctx: The context of the workflow.
            ev: The output of the model.

        Returns:
            The input of the next turn, or the end of the run.
        """
        retried = await ctx.store.get(_SILENT_TURN_KEY, default=False)
        if not retried:
            await ctx.store.set(_SILENT_TURN_KEY, True)

            scratchpad: List[ChatMessage] = await ctx.store.get(
                self.scratchpad_key, default=[]
            )
            scratchpad.append(ChatMessage(role="user", content=SILENT_TURN_NUDGE))
            await ctx.store.set(self.scratchpad_key, scratchpad)

            memory = await ctx.store.get("memory")
            if memory is None:
                logger.warning(
                    "The model ended the turn without an answer, and there "
                    "is no memory to continue the conversation with — the "
                    "run ends."
                )
                return await super().parse_agent_output(ctx, ev)

            logger.info(
                "The model ended the turn without an answer — the agent "
                "gives it one more turn."
            )
            return AgentInput(
                input=await memory.aget(),
                current_agent_name=self.name,
            )

        logger.warning(
            "The model ended the turn without an answer for the second "
            "time — the run ends, and the answer says so."
        )
        return await super().parse_agent_output(ctx, ev)

    # ------------------------------------------------------------------
    # Loop detection
    # ------------------------------------------------------------------

    async def handle_tool_call_results(self, ctx: Context, results, memory) -> None:
        """Remember what the tools returned, then let the base class work.

        The results are the fingerprint of an action: the same call with
        the same arguments that returns the same thing is a repetition,
        and a repetition in a row is a loop.  See
        ``investigate/agent-loop-context-guard/``.
        """
        await super().handle_tool_call_results(ctx, results, memory)

        history = await ctx.store.get(_TOOL_RESULTS_KEY, default=[])
        if not isinstance(history, list):
            history = []

        for result in results:
            history.append(_tool_result_fingerprint(result))

        await ctx.store.set(_TOOL_RESULTS_KEY, history[-REPEAT_CALL_HISTORY:])

    async def _detect_repetition(self, ctx: Context) -> Optional[str]:
        """Return the name of the tool that is being repeated, if any.

        A repetition is *the same call with the same arguments that
        returned the same result*, several times in a row.  The result
        matters: the same read-only call repeated on purpose (checking
        whether a file appeared, for instance) is legitimate, as long as
        the answer changes.
        """
        history = await ctx.store.get(_TOOL_RESULTS_KEY, default=[])
        if not isinstance(history, list) or len(history) < REPEAT_CALL_THRESHOLD:
            return None

        recent = history[-REPEAT_CALL_THRESHOLD:]
        if len(set(recent)) != 1:
            return None

        return recent[-1].split("|", 1)[0]

    async def _stop_for_repetition(
        self, ctx: Context, ev: AgentOutput, tool_name: str
    ) -> StopEvent:
        """End the run: the agent is repeating itself and cannot progress.

        The run is stopped instead of being left to burn the whole
        iteration budget: every iteration costs a full model round-trip,
        and on a local model that is minutes.  The operator gets a report
        of what the agent did and why it stopped.
        """
        memory = await ctx.store.get("memory")
        output = await self.finalize(ctx, ev, memory)

        cur_tool_calls = await ctx.store.get("current_tool_calls", default=[])
        output.tool_calls.extend(cur_tool_calls)
        await ctx.store.set("current_tool_calls", [])

        output.response = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=(
                f"[Stopped] The agent called `{tool_name}` with the same "
                f"arguments {REPEAT_CALL_THRESHOLD} times in a row and got "
                f"the same result every time. Repeating the call cannot "
                f"make progress, so the run was stopped. Please tell the "
                f"agent how to continue, or run the task with a hint of "
                f"what to do instead."
            ),
        )

        logger.warning(
            "The agent repeated `%s` with the same arguments %d times in a "
            "row and got the same result — the run was stopped.",
            tool_name,
            REPEAT_CALL_THRESHOLD,
        )
        return StopEvent(result=output)

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
