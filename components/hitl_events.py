"""
Human-in-the-Loop (HITL) Event Classes

Custom event types for the HITL system that enable communication between
the agent workflow and the human user. These events serve as the primary
mechanism for asking questions, collecting answers, and managing timeouts.

Framework contract
-------------------
The ``workflows`` library provides a first-class HITL mechanism:

* ``InputRequiredEvent`` — *"Automatically written to the event stream if
  returned from a step.  If returned from a step, it does not need to be
  consumed by other steps and will pass validation.  It's expected that the
  caller will respond to this event and send back a HumanResponseEvent."*
* ``HumanResponseEvent`` — carries the human's answer back into the workflow;
  it is dispatched to the step that accepts it.

To comply with that contract the HITL events **subclass** the framework
events:

* ``AgentQuestionEvent`` extends ``InputRequiredEvent`` — it is the
  "terminal" event of a step, so the framework publishes it to the event
  stream automatically and the workflow *waits* for the answer.
* ``AgentAnswerEvent`` extends ``HumanResponseEvent`` — it is the event the
  caller sends back; a step that accepts it is resumed with the answer.

Subclassing keeps the existing class names (and therefore the existing
``EventConsumer`` routing) while making the events behave exactly as the
framework expects.  See ``investigate/hitl-investigate/`` for the
investigation that proved the previous, non-conforming implementation could
never deliver an answer to the agent.

Usage:
    from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent

    # Create a question event
    q = AgentQuestionEvent(
        question="Should I install this package?",
        question_id="pkg-install-001",
        timeout=60,          # -1 (the default) means "wait forever"
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

from workflows.events import HumanResponseEvent, InputRequiredEvent

from components.hitl_timeout import NO_TIMEOUT, validate_timeout


# Valid input types for HITL questions
VALID_INPUT_TYPES: frozenset = frozenset({
    "text",       # Free-form text input
    "yesno",      # Yes/No confirmation
    "menu",       # Selection from a list of options
    "password",   # Sensitive input (hidden)
})


class AgentQuestionEvent(InputRequiredEvent):
    """Event signalling that the agent has a question requiring human input.

    This event is produced by the HITL agent step when it needs to ask the
    user a question before it can proceed.  Because it extends
    ``InputRequiredEvent``, the ``workflows`` runtime publishes it to the
    event stream automatically and the workflow waits for the matching
    ``AgentAnswerEvent``.

    Fields:
        question: The question text to display to the user.
        question_id: Unique identifier for this question (used to match
                     answers back to questions).
        timeout: Seconds to wait for a response before falling back to
                 ``default_answer``.  ``-1`` (the default) means *no
                 timeout*: the agent waits for the human indefinitely.
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
    timeout: int = NO_TIMEOUT
    default_answer: str = ""
    input_type: str = "text"
    options: List[str] = []
    context: Optional[str] = None

    def __init__(
        self,
        question: str,
        question_id: str,
        timeout: int = NO_TIMEOUT,
        default_answer: str = "",
        input_type: str = "text",
        options: Optional[List[str]] = None,
        context: Optional[str] = None,
        prefix: str = "",
    ) -> None:
        # Pass all Pydantic model fields to super().__init__() so validation
        # succeeds.  ``prefix`` belongs to InputRequiredEvent and carries the
        # label the consumer shows in front of the question.
        super().__init__(
            prefix=prefix,
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
        # ``-1`` is valid and means "no timeout" — wait for the human
        # indefinitely.  Anything below that is a typo.
        validate_timeout(self.timeout)
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


class AgentAnswerEvent(HumanResponseEvent):
    """Event carrying the human's response back to the agent.

    This event is sent by the consumer after the user answers (or times out
    on) a question.  The ``question_id`` links the answer back to the
    original ``AgentQuestionEvent``.

    Because it extends ``HumanResponseEvent``, the ``workflows`` runtime
    dispatches it to the step that is waiting for it, and that step resumes
    with the answer in hand.

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
        response: Optional[str] = None,
    ) -> None:
        # ``response`` mirrors the HumanResponseEvent field so that the
        # framework's own consumers (and any code written against the
        # framework contract) see the answer in the expected place.
        super().__init__(
            response=answer if response is None else response,
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
