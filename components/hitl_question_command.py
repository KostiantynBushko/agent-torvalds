"""
The ``\\question`` command — a *predefined* Human-in-the-Loop test.

Why this command exists
-----------------------
The Human-in-the-Loop is only as good as its evidence.  When the operator
reports "the agent never asked me anything", the question is whether the
HITL path works at all — and the fastest way to find out is to ask a
question that is *known*: a fixed question, asked on demand, without the
model in the loop and without a single tool call.

The operator asked for exactly this on 2026-11-10: *"a predefined
hardcoded test — when the operator runs a predefined command, for example
``\\question``, the agent must run HITL to ask some predefined question for
the operator, the agent should not run any tools, just ask the question and
process the response."*

What the command does
---------------------
1. It picks a question from the **bank** (:data:`PREDEFINED_QUESTIONS`) —
   the next one in the rotation, or the one the operator named;
2. it asks it through the **real** HITL path: the question is rendered by
   ``EventConsumer._render_question`` and the answer is collected by
   ``EventConsumer._collect_answer``, so the command exercises the same
   code an agent question travels;
3. it **processes the answer** — the answer is checked against what the
   question asked for (a yes/no, a choice of the menu, free text, a
   secret), and the outcome is reported;
4. it runs **no tool at all**: the agent is never called, so a failure of
   the command says something about the HITL path and nothing about the
   model or the tools.

The answer is *not* written into the conversation memory: the command is a
test of the machinery, and a test answer must not become context for the
next turn of the agent.

Usage::

    from components.hitl_question_command import (
        QuestionCommandRunner, is_question_command,
    )

    runner = QuestionCommandRunner()
    if is_question_command(cmd):
        report = await runner.run(cmd, event_consumer)
        console.print(Markdown(report))

Category: HITL / Commands
Retriever Keywords: hitl, question, command, predefined, test, round trip
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from components.hitl_events import AgentQuestionEvent
from components.hitl_question import detect_input_type

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------

#: The command itself.
QUESTION_COMMAND = "\\question"

#: The aliases that answer to the same command.
QUESTION_COMMAND_ALIASES: Tuple[str, ...] = ("\\q",)

#: Every spelling of the command.
QUESTION_COMMAND_NAMES: Tuple[str, ...] = (
    QUESTION_COMMAND,
    *QUESTION_COMMAND_ALIASES,
)

#: The argument that asks for the list of the predefined questions.
LIST_ARGUMENT = "list"


def is_question_command(cmd: str) -> bool:
    """Return ``True`` when *cmd* is the ``\\question`` command.

    The argument does not matter: ``\\question``, ``\\question list`` and
    ``\\question text-01`` are all the same command.

    Args:
        cmd: The line the operator typed.
    """
    if not cmd:
        return False
    name = cmd.strip().split(" ", 1)[0].strip().lower()
    return name in QUESTION_COMMAND_NAMES


def command_argument(cmd: str) -> str:
    """Return the argument of *cmd* — the text after the command name."""
    if not cmd:
        return ""
    parts = cmd.strip().split(" ", 1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


# ---------------------------------------------------------------------------
# The bank of predefined questions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PredefinedQuestion:
    """One question of the bank.

    Attributes:
        id: The identifier the operator types to ask this exact question
            (``\\question text-01``).
        question: The question the operator is asked.
        input_type: The kind of answer the question wants — ``"text"``,
            ``"yesno"``, ``"menu"`` or ``"password"``.
        options: The choices of a menu question.
        context: The report around the question, when the question needs
            one.
    """

    id: str
    question: str
    input_type: str = "text"
    options: Tuple[str, ...] = ()
    context: str = ""


#: The questions the command asks.  One per input type, so that a run of
#: the command covers every kind of prompt the HITL path can produce.
PREDEFINED_QUESTIONS: Tuple[PredefinedQuestion, ...] = (
    PredefinedQuestion(
        id="text-01",
        question="What is the name of the branch you want me to create?",
        input_type="text",
    ),
    PredefinedQuestion(
        id="yesno-01",
        question="Shall I continue with the deployment?",
        input_type="yesno",
    ),
    PredefinedQuestion(
        id="menu-01",
        question="Which of these should I check first?",
        input_type="menu",
        options=(
            "the disk usage",
            "the open ports",
            "the running services",
        ),
    ),
    PredefinedQuestion(
        id="password-01",
        question="Please enter the passphrase of the deployment key.",
        input_type="password",
    ),
)


def question_by_id(identifier: str) -> Optional[PredefinedQuestion]:
    """Return the question with that *identifier*.

    The identifier is matched exactly first and case-insensitively after
    that, so ``text-01`` and ``TEXT-01`` are the same question.

    Args:
        identifier: The identifier the operator typed.
    """
    if not identifier:
        return None
    wanted = identifier.strip()
    for question in PREDEFINED_QUESTIONS:
        if question.id == wanted:
            return question
    lowered = wanted.lower()
    for question in PREDEFINED_QUESTIONS:
        if question.id.lower() == lowered:
            return question
    return None


def detected_input_type(question: PredefinedQuestion) -> str:
    """Return the input type the *rules* produce for *question*.

    The bank declares the type every question is meant to have.  The rules
    in :mod:`components.hitl_question` decide the type from the question
    itself.  The two must agree — the bank is the acceptance criterion of
    the rules — and the command says so in the log when they do not.
    """
    return detect_input_type(question.question, question.options)


# ---------------------------------------------------------------------------
# The answer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QuestionOutcome:
    """What came out of one question.

    Attributes:
        question: The question that was asked.
        answer: The answer of the operator — empty for a secret, which is
            never echoed.
        was_timeout: ``True`` when nobody answered.
        valid: ``True`` when the answer is what the question asked for.
        note: A line about the outcome, for the operator.
    """

    question: PredefinedQuestion
    answer: str = ""
    was_timeout: bool = False
    valid: bool = False
    note: str = ""


def process_answer(
    question: PredefinedQuestion,
    answer: str,
    was_timeout: bool = False,
) -> QuestionOutcome:
    """Check *answer* against what *question* asked for.

    The processing is what turns a raw answer into a result:

    * a **yes/no** question wants ``yes`` or ``no`` — ``y`` and ``n`` are
      the same answers, and anything else is reported as "not a yes/no
      answer";
    * a **menu** question wants one of the choices — the answer is matched
      against the options of the question;
    * a **password** question wants a secret — the answer is *never*
      echoed, not even into the report;
    * a **text** question wants anything the operator typed.

    A timeout is never reported as an answer: the operator has to be able
    to tell "nobody answered" from "the operator said so".

    Args:
        question: The question that was asked.
        answer: The raw answer.
        was_timeout: Whether the wait ended without an answer.
    """
    text = (answer or "").strip()

    if was_timeout:
        return QuestionOutcome(
            question=question,
            answer="",
            was_timeout=True,
            valid=False,
            note="Nobody answered — the wait ended without an answer.",
        )

    if question.input_type == "yesno":
        lowered = text.lower()
        if lowered in ("y", "yes"):
            return QuestionOutcome(question, "yes", False, True)
        if lowered in ("n", "no"):
            return QuestionOutcome(question, "no", False, True)
        return QuestionOutcome(
            question,
            text,
            False,
            False,
            "The answer is neither 'yes' nor 'no'.",
        )

    if question.input_type == "menu":
        for option in question.options:
            if text.lower() == option.lower():
                return QuestionOutcome(question, option, False, True)
        return QuestionOutcome(
            question,
            text,
            False,
            False,
            "The answer is not one of the choices of the question.",
        )

    if question.input_type == "password":
        # The secret is never echoed — not into the report, not into the
        # log, not into the history of the questions.
        return QuestionOutcome(
            question,
            "",
            False,
            bool(text),
            "The passphrase was received (it is not shown).",
        )

    return QuestionOutcome(
        question,
        text,
        False,
        bool(text),
        "" if text else "The answer was empty.",
    )


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def render_list(questions: Sequence[PredefinedQuestion] = PREDEFINED_QUESTIONS) -> str:
    """Return the Markdown report of the bank."""
    lines = [
        "# Predefined HITL questions",
        "",
        "The `\\question` command asks one of these questions through the "
        "Human-in-the-Loop.  No tool is run and the model is not called.",
        "",
        "| Id | Input type | Question |",
        "|---|---|---|",
    ]
    for question in questions:
        lines.append(
            f"| `{question.id}` | `{question.input_type}` | {question.question} |"
        )
    lines += [
        "",
        "Ask the next one with `\\question`, a specific one with "
        "`\\question <id>`.",
    ]
    return "\n".join(lines)


def render_outcome(outcome: QuestionOutcome) -> str:
    """Return the Markdown report of one answered question."""
    question = outcome.question
    lines = [
        f"# HITL question — `{question.id}`",
        "",
        question.question,
        "",
        "| | |",
        "|---|---|",
        f"| Input type | `{question.input_type}` |",
    ]

    if outcome.was_timeout:
        lines.append("| Answer | *nobody answered* |")
        lines.append("| Timed out | yes |")
    else:
        if question.input_type == "password":
            # The secret is not shown — and the report says so, so that an
            # empty answer is not read as "nobody answered".
            answer = outcome.answer or "*(not shown)*"
        else:
            answer = outcome.answer or "*(empty)*"
        lines.append(f"| Answer | {answer} |")
        lines.append("| Timed out | no |")

    lines.append("| Tools run | none |")

    if outcome.note:
        lines += ["", outcome.note]

    lines += [
        "",
        "*The answer was not written into the conversation memory — the "
        "command is a test of the HITL path.*",
    ]
    return "\n".join(lines)


def render_disabled(question: PredefinedQuestion) -> str:
    """Return the report of a question that was not asked."""
    return "\n".join(
        [
            "# HITL question — not asked",
            "",
            f"The Human-in-the-Loop is **disabled**, so `{question.id}` was "
            "not asked.",
            "",
            "Enable it with `\\hitl-on` and run the command again.",
        ]
    )


def render_unknown(identifier: str) -> str:
    """Return the report of an identifier that is not in the bank."""
    known = ", ".join(f"`{q.id}`" for q in PREDEFINED_QUESTIONS)
    return "\n".join(
        [
            "# HITL question — unknown question",
            "",
            f"There is no predefined question called `{identifier}`.",
            "",
            f"The known questions are: {known}.",
            "",
            "Run `\\question list` to see them.",
        ]
    )


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

class QuestionCommandRunner:
    """Runs the ``\\question`` command.

    The runner keeps the position in the bank, so that the command walks
    through the questions instead of asking the same one over and over.

    Attributes:
        questions: The bank the runner asks from.
    """

    def __init__(
        self,
        questions: Sequence[PredefinedQuestion] = PREDEFINED_QUESTIONS,
    ) -> None:
        self.questions: Tuple[PredefinedQuestion, ...] = tuple(questions)
        self._index = 0

    # -- the bank ------------------------------------------------------

    def next_question(self) -> Optional[PredefinedQuestion]:
        """Return the next question of the rotation.

        The position moves on with every call, so the command covers the
        whole bank.
        """
        if not self.questions:
            return None
        question = self.questions[self._index % len(self.questions)]
        self._index = (self._index + 1) % len(self.questions)
        return question

    def resolve(self, identifier: str) -> Optional[PredefinedQuestion]:
        """Return the question *identifier* names.

        An empty identifier means "the next one of the rotation".
        """
        if not identifier:
            return self.next_question()
        if identifier.lower() == LIST_ARGUMENT:
            return None
        return question_by_id(identifier)

    # -- the command ---------------------------------------------------

    async def run(
        self,
        cmd: str,
        consumer: Any,
        *,
        hitl_enabled: bool = True,
    ) -> Optional[str]:
        """Run the command and return the Markdown report.

        Args:
            cmd: The line the operator typed.
            consumer: The ``EventConsumer`` that asks the question.  The
                real HITL path is used — the question is rendered and the
                answer collected by the consumer, exactly as an agent
                question is.
            hitl_enabled: Whether the Human-in-the-Loop is active.  When
                it is not, the question is not asked and the report says
                so.

        Returns:
            The Markdown report, or ``None`` when *cmd* is not the
            command.
        """
        if not is_question_command(cmd):
            return None

        identifier = command_argument(cmd)
        if identifier.lower() == LIST_ARGUMENT:
            return render_list(self.questions)

        question = self.resolve(identifier)
        if question is None:
            return render_unknown(identifier)

        if not hitl_enabled:
            logger.info(
                "The \\question command was not run: the Human-in-the-Loop "
                "is disabled."
            )
            return render_disabled(question)

        detected = detected_input_type(question)
        if detected != question.input_type:
            # The bank says one thing and the rules say another.  The
            # question is asked as the bank declares it — the command is a
            # test of a *known* prompt — but the disagreement is logged,
            # because it means one of the two is wrong.
            logger.warning(
                "The predefined question %r declares the input type %r, but "
                "the rules detect %r — the question is asked as declared.",
                question.id,
                question.input_type,
                detected,
            )

        event = AgentQuestionEvent(
            prefix="Agent asks: ",
            question=question.question,
            question_id=f"question-cmd-{question.id}-{uuid.uuid4().hex[:8]}",
            timeout=getattr(consumer, "hitl_timeout", -1),
            default_answer=getattr(consumer, "hitl_default_answer", ""),
            input_type=question.input_type,
            options=list(question.options),
            context=question.context or None,
        )

        logger.info(
            "The \\question command asks the predefined question %r "
            "(input_type=%s).",
            question.id,
            question.input_type,
        )

        answer, was_timeout = await consumer.ask_question(event)
        outcome = process_answer(question, answer, was_timeout)

        logger.info(
            "The predefined question %r was answered: %s.",
            question.id,
            "timed out" if outcome.was_timeout else "answered",
        )

        return render_outcome(outcome)


#: The runner the orchestrators use.  One instance, so that the position
#: in the bank is shared by the whole session.
DEFAULT_RUNNER = QuestionCommandRunner()


async def run_question_command(
    cmd: str,
    consumer: Any,
    *,
    hitl_enabled: bool = True,
    runner: Optional[QuestionCommandRunner] = None,
) -> Optional[str]:
    """Run the ``\\question`` command with the default runner.

    A thin wrapper around :meth:`QuestionCommandRunner.run`, for the
    orchestrators that do not need a runner of their own.
    """
    active = runner or DEFAULT_RUNNER
    return await active.run(cmd, consumer, hitl_enabled=hitl_enabled)


__all__: List[str] = [
    "DEFAULT_RUNNER",
    "LIST_ARGUMENT",
    "PREDEFINED_QUESTIONS",
    "PredefinedQuestion",
    "QUESTION_COMMAND",
    "QUESTION_COMMAND_ALIASES",
    "QUESTION_COMMAND_NAMES",
    "QuestionCommandRunner",
    "QuestionOutcome",
    "command_argument",
    "detected_input_type",
    "is_question_command",
    "process_answer",
    "question_by_id",
    "render_disabled",
    "render_list",
    "render_outcome",
    "render_unknown",
    "run_question_command",
]
