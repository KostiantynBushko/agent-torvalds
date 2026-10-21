"""
Human Loop Handler — HITL Callback for LlamaIndex.

This module provides a LlamaIndex ``BaseCallbackHandler`` that inspects LLM
output for questions and keeps track of Human-in-the-Loop activity.

Scope change (see ``investigate/hitl-investigate/``)
----------------------------------------------------
The handler used to *also* prompt the user.  That produced a double prompt
(defect #5) as soon as the detection path was repaired, because the
workflow event stream path (``EventConsumer``) prompts as well.  The
prompting now lives in exactly one place — the ``EventConsumer``, which
consumes the ``AgentQuestionEvent`` from the workflow event stream — and
this handler is responsible for:

* detecting questions in LLM output (the ``_extract_text`` fix, defect #1),
* recording question / answer / timeout history,
* exposing the runtime toggle state,
* removing the dead ``CBEventType.AGENT_STEP`` branch (defect #2), which
  llama-index never emits.

The question itself is raised by :class:`components.hitl_agent.HITLFunctionAgent`
using the framework's supported ``InputRequiredEvent`` /
``HumanResponseEvent`` mechanism, so the question reaches the consumer and
the answer reaches the agent (defects #3 and #4).

Category: HITL / Callbacks
Retriever Keywords: hitl, human-in-the-loop, callback, question, prompt, timeout
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from llama_index.core.callbacks.base import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload

from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent
from components.console_input_module import ConsoleInputModule
from components.whiptail_input_module import WhiptailInputModule
from components.spinner_controller import SpinnerController
from rich.console import Console

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
    # delete it." — is not mistaken for a question.
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

# ---------------------------------------------------------------------------
# Input type helpers
# ---------------------------------------------------------------------------

_INPUT_METHODS: frozenset = frozenset({"console", "whiptail"})


def _detect_input_type(message: str) -> str:
    """Heuristically detect the best input type from the message text."""
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in ("password", "secret", "credential")):
        return "password"
    if any(kw in msg_lower for kw in ("yes", "no", "confirm", "proceed", "continue")):
        return "yesno"
    return "text"


# ---------------------------------------------------------------------------
# HumanLoopHandler
# ---------------------------------------------------------------------------


class HumanLoopHandler(BaseCallbackHandler):
    """LlamaIndex callback handler for Human-in-the-Loop interactions.

    Responsibilities:
    - Detect questions in LLM responses.
    - Track question history, answers and timeouts.
    - Integrate with the runtime toggle for dynamic HITL enable/disable.

    The handler deliberately does **not** prompt the user: the prompt is
    issued by the ``EventConsumer`` when it receives the
    ``AgentQuestionEvent`` from the workflow event stream.  Two prompting
    paths is what caused the double prompt reported by the investigation.

    Usage::

        handler = HumanLoopHandler(
            input_method="console",
            default_timeout=30,
            default_answer="yes",
            enable_hitl=True,
            runtime_toggle=hitl_toggle,  # Optional runtime toggle
        )
        # Register with LlamaIndex callback manager
        from llama_index.core.callbacks import CallbackManager
        CallbackManager.global_handlers.append(handler)
    """

    def __init__(
        self,
        input_method: str = "console",
        default_timeout: int = 30,
        default_answer: str = "",
        console: Optional[Console] = None,
        spinner: Optional[SpinnerController] = None,
        enable_hitl: bool = True,
        event_consumer: Any = None,
        question_patterns: Optional[List[str]] = None,
        runtime_toggle: Any = None,
    ) -> None:
        """Initialise the HITL callback handler.

        Args:
            input_method: ``"console"`` or ``"whiptail"``.
            default_timeout: Seconds to wait for user input.
            default_answer: Fallback value on timeout.
            console: Rich ``Console`` instance for display.
            spinner: ``SpinnerController`` to pause/resume during prompts.
            enable_hitl: Toggle HITL on/off at runtime.
            event_consumer: Optional workflow ``EventConsumer`` to push
                ``AgentQuestionEvent`` / ``AgentAnswerEvent`` into.
            question_patterns: Optional list of regex strings to override
                the built-in question detection patterns.
            runtime_toggle: Optional ``HITLRuntimeToggle`` instance for
                dynamic HITL enable/disable during execution.
        """
        # BaseCallbackHandler requires ignore lists
        super().__init__(
            event_starts_to_ignore=[],
            event_ends_to_ignore=[],
        )

        self.input_method = input_method if input_method in _INPUT_METHODS else "console"
        self.default_timeout = max(1, default_timeout)
        self.default_answer = default_answer
        self.console = console or Console()
        self.spinner = spinner
        self.enable_hitl = enable_hitl
        self.event_consumer = event_consumer
        self.runtime_toggle = runtime_toggle

        # Input modules (kept so the handler can be used standalone, and so
        # the multi-window TUI can swap in its own input module).
        self.console_input = ConsoleInputModule(self.console)
        self.whiptail_input = (
            WhiptailInputModule() if self.input_method == "whiptail" else None
        )

        # Question detection
        if question_patterns is not None:
            self._question_patterns: List[re.Pattern] = [
                re.compile(p, re.IGNORECASE | re.MULTILINE) for p in question_patterns
            ]
        else:
            self._question_patterns = _QUESTION_PATTERNS

        # State tracking
        self._pending_futures: Dict[str, asyncio.Future] = {}
        self._timeout_log: List[Dict[str, Any]] = []
        self._question_history: List[Dict[str, Any]] = []
        self._asked_question_ids: set = set()  # Prevent duplicate prompts

        # Internal flags
        self._is_prompting: bool = False
        self._lock = asyncio.Lock()

        logger.debug(
            "HumanLoopHandler initialised — method=%s, timeout=%ds, hitl=%s, runtime_toggle=%s",
            self.input_method,
            self.default_timeout,
            self.enable_hitl,
            bool(self.runtime_toggle),
        )

    # ------------------------------------------------------------------
    # BaseCallbackHandler overrides
    # ------------------------------------------------------------------

    def start_trace(self, trace_id: Optional[str] = None) -> None:
        logger.debug("HITL start_trace — trace_id=%s", trace_id)

    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        logger.debug("HITL end_trace — trace_id=%s", trace_id)

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        parent_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Called when a LlamaIndex event starts.

        ``CBEventType.AGENT_STEP`` is *never* emitted by llama-index — the
        enum member exists but nothing raises it — so the previous branch
        here was dead code (investigation defect #2).  Agent progress is
        reported through the workflow event stream, which the
        ``EventConsumer`` handles.  The method is kept because it is part of
        the ``BaseCallbackHandler`` contract.
        """
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Called when a LlamaIndex event ends.

        ``CBEventType.LLM`` is the only event llama-index emits for agent
        output, so it is used to *observe* questions.  The observation is
        recorded in the history; the actual prompt is issued by the
        ``EventConsumer`` from the workflow event stream, so that there is
        exactly one prompt per question.
        """
        if not self._is_hitl_enabled():
            return

        if event_type != CBEventType.LLM or not payload:
            return

        output = payload.get(EventPayload.RESPONSE) or payload.get(
            EventPayload.COMPLETION
        )
        if not output:
            return

        text = self._extract_text(output)
        if not text or not self._is_question(text):
            return

        # The question itself is raised by the HITL agent step; this only
        # records that a question was observed.
        self._record_observation(text, event_id)

    # ------------------------------------------------------------------
    # HITL Enable Check (with runtime toggle support)
    # ------------------------------------------------------------------

    def _is_hitl_enabled(self) -> bool:
        """Check if HITL is enabled (considering runtime toggle).

        Returns:
            True if HITL is enabled, False otherwise.
        """
        if self.runtime_toggle is not None:
            return self.enable_hitl and self.runtime_toggle.is_enabled
        return self.enable_hitl

    # ------------------------------------------------------------------
    # Question detection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(obj: Any) -> str:
        """Best-effort text extraction from LlamaIndex response objects.

        The LLM payload is a ``ChatResponse``; the assistant text lives in
        ``response.message.content``.  The previous implementation looked at
        ``.text`` and at the top level of ``.raw`` only, so it always
        returned ``""`` and no question was ever detected
        (investigation defect #1).
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

        # raw dict shapes: {"content": ...} (mocks) and
        # {"message": {"content": ...}} (Ollama).
        raw = getattr(obj, "raw", None)
        if isinstance(raw, dict):
            for key in ("text", "content"):
                if raw.get(key):
                    return str(raw[key])
            raw_message = raw.get("message")
            if isinstance(raw_message, dict) and raw_message.get("content"):
                return str(raw_message["content"])
            if raw_message is not None:
                raw_content = getattr(raw_message, "content", None)
                if raw_content:
                    return str(raw_content)

        return ""

    def _is_question(self, text: str) -> bool:
        """Return ``True`` if *text* appears to contain a question."""
        if not text:
            return False
        for pattern in self._question_patterns:
            if pattern.search(text):
                return True
        return False

    # ------------------------------------------------------------------
    # History recording
    # ------------------------------------------------------------------

    def _record_observation(self, text: str, event_id: str = "") -> None:
        """Record that a question was observed in the LLM output."""
        question_id = event_id or str(uuid.uuid4())[:8]
        if question_id in self._asked_question_ids:
            return
        self._asked_question_ids.add(question_id)
        self._question_history.append(
            {
                "question_id": question_id,
                "question": text[:200],
                "answer": None,
                "was_timeout": False,
                "input_type": _detect_input_type(text),
                "timestamp": time.monotonic(),
            }
        )

    def record_answer(
        self,
        question_id: str,
        answer: str,
        was_timeout: bool = False,
        question: str = "",
        timeout: Optional[int] = None,
        default_answer: str = "",
    ) -> None:
        """Record the human's answer for a previously observed question.

        Args:
            question_id: ID of the question that was answered.
            answer: The answer text.
            was_timeout: ``True`` when the answer is a timeout fallback.
            question: The question text (used when the question was not
                observed through a callback event).
            timeout: The timeout that applied to the question.
            default_answer: The fallback answer that was configured.
        """
        for entry in self._question_history:
            if entry.get("question_id") == question_id:
                entry["answer"] = answer
                entry["was_timeout"] = was_timeout
                if was_timeout:
                    self._log_timeout(
                        question_id,
                        entry.get("question", ""),
                        timeout=timeout,
                        default_answer=default_answer,
                    )
                return

        # The question was raised by the agent (not observed via a callback
        # event) — record it anyway so the history is complete.
        self._question_history.append(
            {
                "question_id": question_id,
                "question": (question or "")[:200],
                "answer": answer,
                "was_timeout": was_timeout,
                "input_type": "text",
                "timestamp": time.monotonic(),
            }
        )
        if was_timeout:
            self._log_timeout(
                question_id,
                question,
                timeout=timeout,
                default_answer=default_answer,
            )

    # ------------------------------------------------------------------
    # Convenience setters
    # ------------------------------------------------------------------

    def set_menu_options(self, options: List[str]) -> None:
        """Pre-set menu options for the next ``menu``-type prompt."""
        self._menu_options = options

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------

    def get_timeout_log(self) -> List[Dict[str, Any]]:
        """Return a copy of the timeout log."""
        return list(self._timeout_log)

    def get_question_history(self) -> List[Dict[str, Any]]:
        """Return a copy of the question history."""
        return list(self._question_history)

    def _log_timeout(
        self,
        question_id: str,
        question: str,
        timeout: Optional[int] = None,
        default_answer: str = "",
    ) -> None:
        self._timeout_log.append(
            {
                "question_id": question_id,
                "question": (question or "")[:200],
                "timeout": self.default_timeout if timeout is None else timeout,
                "default_answer": (
                    self.default_answer if not default_answer else default_answer
                ),
                "timestamp": time.monotonic(),
            }
        )

    def reset(self) -> None:
        """Clear all internal state."""
        self._pending_futures.clear()
        self._timeout_log.clear()
        self._question_history.clear()
        self._asked_question_ids.clear()
        self._is_prompting = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_prompting(self) -> bool:
        return self._is_prompting

    @property
    def question_count(self) -> int:
        return len(self._question_history)

    @property
    def timeout_count(self) -> int:
        return len(self._timeout_log)
