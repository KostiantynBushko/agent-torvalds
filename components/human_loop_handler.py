"""
Human Loop Handler — HITL Callback for LlamaIndex.

This module provides a LlamaIndex ``BaseCallbackHandler`` that intercepts
agent events, detects questions in LLM output, and prompts the human user
for input (via console or whiptail).  It handles timeouts, tracks question
history, and integrates with the spinner controller.

Category: HITL / Callbacks
Retriever Keywords: hitl, human-in-the-loop, callback, question, prompt, timeout
"""
from __future__ import annotations

import asyncio
import logging
import uuid
import time
import re
from typing import Any, Dict, List, Optional

from llama_index.core.callbacks.base import BaseCallbackHandler
from llama_index.core.callbacks.schema import CBEventType, EventPayload

from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent
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
    # Destructive operations that should always be confirmed
    re.compile(r"\b(delete|drop|remove|overwrite|destroy|format|uninstall)\b", re.IGNORECASE),
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
    - Detect questions in LLM responses and agent step outputs.
    - Pause the workflow spinner and prompt the human user.
    - Collect input via console or whiptail (configurable).
    - Handle timeouts with configurable fallback answers.
    - Track question history and timeout logs.
    - Emit ``AgentQuestionEvent`` and ``AgentAnswerEvent`` for external
      consumers (e.g. the EventConsumer workflow).

    Usage::

        handler = HumanLoopHandler(
            input_method="console",
            default_timeout=30,
            default_answer="yes",
            enable_hitl=True,
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

        # Input modules
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
            "HumanLoopHandler initialised — method=%s, timeout=%ds, hitl=%s",
            self.input_method,
            self.default_timeout,
            self.enable_hitl,
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

        We listen for ``AGENT_STEP`` starts to detect questions in
        intermediate agent outputs.
        """
        if not self.enable_hitl:
            return event_id

        if event_type == CBEventType.AGENT_STEP and payload:
            # Check the agent's current output for a question
            output = payload.get(EventPayload.COMPLETION) or payload.get(
                EventPayload.RESPONSE
            )
            if output:
                text = self._extract_text(output)
                if self._is_question(text):
                    asyncio.ensure_future(
                        self._handle_question(
                            question=text,
                            question_id=event_id,
                            timeout=self.default_timeout,
                            default_answer=self.default_answer,
                        )
                    )
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Called when a LlamaIndex event ends.

        We listen for ``LLM`` and ``AGENT_STEP`` ends to detect questions
        in final outputs.
        """
        if not self.enable_hitl:
            return

        if event_type in (CBEventType.LLM, CBEventType.AGENT_STEP) and payload:
            output = payload.get(EventPayload.RESPONSE) or payload.get(
                EventPayload.COMPLETION
            )
            if output:
                text = self._extract_text(output)
                if self._is_question(text):
                    qid = event_id or str(uuid.uuid4())[:8]
                    asyncio.ensure_future(
                        self._handle_question(
                            question=text,
                            question_id=qid,
                            timeout=self.default_timeout,
                            default_answer=self.default_answer,
                        )
                    )

    # ------------------------------------------------------------------
    # Question detection
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(obj: Any) -> str:
        """Best-effort text extraction from LlamaIndex response objects."""
        if isinstance(obj, str):
            return obj
        # Llama LLMResponse / ChatResponse have a .text or .raw attribute
        text = getattr(obj, "text", None)
        if text:
            return str(text)
        raw = getattr(obj, "raw", None)
        if isinstance(raw, dict):
            return str(raw.get("text", raw.get("content", "")))
        return str(obj)

    def _is_question(self, text: str) -> bool:
        """Return ``True`` if *text* appears to contain a question."""
        for pattern in self._question_patterns:
            if pattern.search(text):
                return True
        return False

    # ------------------------------------------------------------------
    # Core question handling
    # ------------------------------------------------------------------

    async def _handle_question(
        self,
        question: str,
        question_id: str,
        timeout: int,
        default_answer: str,
    ) -> None:
        """Orchestrate the full HITL flow for one question.

        1. Emit ``AgentQuestionEvent``.
        2. Pause spinner.
        3. Prompt the user (console / whiptail).
        4. Record answer and emit ``AgentAnswerEvent``.
        5. Resume spinner.
        """
        # Deduplicate
        if question_id in self._asked_question_ids:
            return
        self._asked_question_ids.add(question_id)

        async with self._lock:
            self._is_prompting = True

        # Determine input type
        input_type = _detect_input_type(question)

        # Emit question event
        q_event = AgentQuestionEvent(
            question=question,
            question_id=question_id,
            timeout=timeout,
            default_answer=default_answer,
            input_type=input_type,
        )
        await self._emit_event(q_event)

        logger.info("HITL question %s — type=%s", question_id, input_type)

        # Pause spinner
        if self.spinner:
            self.spinner.pause()
            self.console.print(
                f"\n[yellow]⏸  Pausing agent — waiting for your input[/yellow]"
            )

        try:
            answer, was_timeout = await self._prompt_user(
                question=question,
                input_type=input_type,
                timeout=timeout,
                default_answer=default_answer,
            )

            # Record history
            self._question_history.append(
                {
                    "question_id": question_id,
                    "question": question[:200],
                    "answer": answer,
                    "was_timeout": was_timeout,
                    "input_type": input_type,
                    "timestamp": time.monotonic(),
                }
            )

            if was_timeout:
                self._log_timeout(question_id, question)
                self.console.print(
                    f"[yellow]⏱️  Timeout — using default: '{answer}'[/yellow]"
                )
            else:
                self.console.print(f"[green]✓  Answer received[/green]")

            # Emit answer event
            a_event = AgentAnswerEvent(
                question_id=question_id,
                answer=answer,
                was_timeout=was_timeout,
            )
            await self._emit_event(a_event)

        except Exception as exc:
            logger.error("HITL prompt failed: %s", exc)
            self.console.print(f"[red]⚠  Prompt error: {exc}[/red]")
            self._question_history.append(
                {
                    "question_id": question_id,
                    "question": question[:200],
                    "answer": default_answer,
                    "was_timeout": True,
                    "input_type": input_type,
                    "timestamp": time.monotonic(),
                }
            )
        finally:
            # Resume spinner
            if self.spinner:
                self.spinner.resume()
            async with self._lock:
                self._is_prompting = False

    # ------------------------------------------------------------------
    # User prompting delegation
    # ------------------------------------------------------------------

    async def _prompt_user(
        self,
        question: str,
        input_type: str,
        timeout: int,
        default_answer: str,
    ) -> tuple[str, bool]:
        """Prompt the user via the configured input method.

        Returns:
            ``(answer, was_timeout)`` tuple.
        """
        if self.input_method == "whiptail" and self.whiptail_input:
            return await self._whiptail_prompt(
                question, input_type, timeout, default_answer
            )
        return await self._console_prompt(
            question, input_type, timeout, default_answer
        )

    async def _console_prompt(
        self,
        question: str,
        input_type: str,
        timeout: int,
        default_answer: str,
    ) -> tuple[str, bool]:
        """Prompt via console input module."""
        try:
            if input_type == "yesno":
                result = await self.console_input.confirm(
                    message=question,
                    default_yes=default_answer.lower() in ("yes", "y", "true", "1"),
                    timeout=timeout,
                )
                return ("yes" if result else "no", False)
            elif input_type == "password":
                result = await self.console_input.password(
                    message="Enter password: ",
                    timeout=timeout,
                )
                return (result, not result)
            else:
                result = await ConsoleInputModule.prompt(
                    message=f"{question}\nYour answer: ",
                    default=default_answer,
                    timeout=timeout,
                )
                # Detect timeout: if result == default and input was empty
                return (result, result == default_answer and not default_answer)
        except asyncio.TimeoutError:
            return (default_answer, True)

    async def _whiptail_prompt(
        self,
        question: str,
        input_type: str,
        timeout: int,
        default_answer: str,
    ) -> tuple[str, bool]:
        """Prompt via whiptail dialog module."""
        if not self.whiptail_input:
            return (default_answer, True)

        try:
            if input_type == "yesno":
                result = await self.whiptail_input.confirm(
                    message=question,
                    default_yes=default_answer.lower() in ("yes", "y", "true", "1"),
                    timeout=timeout,
                )
                return ("yes" if result else "no", False)
            elif input_type == "menu" and hasattr(self, "_menu_options"):
                result = await self.whiptail_input.menu(
                    message=question,
                    options=self._menu_options,
                    timeout=timeout,
                )
                return (result, False)
            else:
                result = await self.whiptail_input.prompt(
                    message=question,
                    default=default_answer,
                    timeout=timeout,
                )
                return (result, not result)
        except asyncio.TimeoutError:
            return (default_answer, True)

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    async def _emit_event(self, event: Any) -> None:
        """Push an event to the registered event consumer (if any)."""
        if self.event_consumer is not None:
            try:
                await self.event_consumer.send_event(event)
            except Exception as exc:
                logger.warning("Failed to emit event: %s", exc)

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

    def _log_timeout(self, question_id: str, question: str) -> None:
        self._timeout_log.append(
            {
                "question_id": question_id,
                "question": question[:200],
                "timeout": self.default_timeout,
                "default_answer": self.default_answer,
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
