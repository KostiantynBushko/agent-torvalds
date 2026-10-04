"""
Human-in-the-Loop (HITL) Event Classes

Custom event types for the HITL system that enable communication between
the agent workflow and the human user. These events serve as the primary
mechanism for asking questions, collecting answers, and managing timeouts.

Usage:
    from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent

    # Create a question event
    q = AgentQuestionEvent(
        question="Should I install this package?",
        question_id="pkg-install-001",
        timeout=60,
        default_answer="yes",
        input_type="yesno",
        context="User requested to install nginx",
    )

    # Create an answer event
    a = AgentAnswerEvent(
        question_id="pkg-install-001",
        answer="yes",
        was_timeout=False,
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from workflows.events import Event


# Valid input types for HITL questions
VALID_INPUT_TYPES: frozenset = frozenset({
    "text",       # Free-form text input
    "yesno",      # Yes/No confirmation
    "menu",       # Selection from a list of options
    "password",   # Sensitive input (hidden)
})


class AgentQuestionEvent(Event):
    """Event signalling that the agent has a question requiring human input.

    This event is emitted by the agent when it needs to ask the user a
    question before it can proceed.  The HITL handler listens for this
    event, prompts the user (via console or whiptail), and emits an
    ``AgentAnswerEvent`` in response.

    Fields:
        question: The question text to display to the user.
        question_id: Unique identifier for this question (used to match
                     answers back to questions).
        timeout: Seconds to wait for a response before falling back to
                 ``default_answer``.  Default is 30.
        default_answer: Fallback value used when the user does not respond
                        within the timeout.  Default is ``""``.
        input_type: Expected input format — one of ``"text"``, ``"yesno"``,
                    ``"menu"``, or ``"password"``.  Default is ``"text"``.
        options: List of choice strings for ``"menu"``-type questions.
        context: Optional additional context explaining *why* the agent
                 is asking this question.
    """

    question: str
    question_id: str
    timeout: int = 30
    default_answer: str = ""
    input_type: str = "text"
    options: List[str] = []
    context: Optional[str] = None

    def __init__(
        self,
        question: str,
        question_id: str,
        timeout: int = 30,
        default_answer: str = "",
        input_type: str = "text",
        options: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> None:
        # Pass all Pydantic model fields to super().__init__() so validation succeeds
        super().__init__(
            question=question,
            question_id=question_id,
            timeout=timeout,
            default_answer=default_answer,
            input_type=input_type,
            options=options or [],
            context=context,
        )

    def validate(self) -> None:
        """Validate event fields, raising ``ValueError`` on problems."""
        if not self.question:
            raise ValueError("question must not be empty")
        if not self.question_id:
            raise ValueError("question_id must not be empty")
        if self.timeout < 0:
            raise ValueError("timeout must be non-negative")
        if self.input_type not in VALID_INPUT_TYPES:
            raise ValueError(
                f"input_type must be one of {VALID_INPUT_TYPES}, "
                f"got '{self.input_type}'"
            )
        if self.input_type == "menu" and not self.options:
            raise ValueError(
                "menu input_type requires at least one option"
            )

    def __repr__(self) -> str:
        return (
            f"AgentQuestionEvent(question_id={self.question_id!r}, "
            f"input_type={self.input_type!r}, "
            f"timeout={self.timeout})"
        )


class AgentAnswerEvent(Event):
    """Event carrying the human's response back to the agent.

    This event is emitted after the user answers (or times out on) a
    question.  The ``question_id`` links the answer back to the original
    ``AgentQuestionEvent``.

    Fields:
        question_id: ID of the question being answered.
        answer: The user's response string.
        was_timeout: ``True`` if this answer came from a timeout fallback
                     rather than an explicit user response.
    """

    question_id: str
    answer: str
    was_timeout: bool = False

    def __init__(
        self,
        question_id: str,
        answer: str,
        was_timeout: bool = False,
    ) -> None:
        # Pass all Pydantic model fields to super().__init__() so validation succeeds
        super().__init__(
            question_id=question_id,
            answer=answer,
            was_timeout=was_timeout,
        )

    def validate(self) -> None:
        """Validate event fields, raising ``ValueError`` on problems."""
        if not self.question_id:
            raise ValueError("question_id must not be empty")

    def __repr__(self) -> str:
        timeout_flag = " (timeout)" if self.was_timeout else ""
        return (
            f"AgentAnswerEvent(question_id={self.question_id!r}, "
            f"answer={self.answer!r}{timeout_flag})"
        )