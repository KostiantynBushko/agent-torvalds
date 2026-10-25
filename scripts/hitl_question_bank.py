"""
HITL Question Bank — the questions used to exercise the Human-in-the-Loop.

Why a bank
----------
The HITL feature has four input types (``text``, ``yesno``, ``menu``,
``password``) and a set of detection rules that decide *which* one a
question wants.  The rules live in ``components/hitl_question.py``:

* the *question* is split out of the assistant message (the report around
  it is context, not the question);
* the *input type* is derived from the question alone — never from the
  answer, never from the context;
* mentioning a secret is not enough to ask for a password — the question
  must also *ask* for it;
* a question written as a list wants a *choice*, not a yes or a no.

Every entry in this bank is a real assistant message — context, question
and (for menus) options — exactly as the agent would emit it.  The
``expected_type`` is the type the detection rules *should* produce.

The bank is shared by the interactive harness
(``scripts/hitl_interactive_test.py``) and by the chat-driven test
session, so both exercise the same questions.

Category: HITL / Testing
Retriever Keywords: hitl, question bank, interactive test, input type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Answer validators
# ---------------------------------------------------------------------------

def _v_non_empty(answer: str) -> tuple[bool, str]:
    if answer.strip():
        return True, "non-empty answer"
    return False, "answer was empty"


def _v_yes_no(answer: str) -> tuple[bool, str]:
    if answer.strip().lower() in ("y", "yes", "n", "no"):
        return True, "valid yes/no"
    return False, f"'{answer}' is not a yes/no answer"


def _v_number(answer: str) -> tuple[bool, str]:
    try:
        int(answer.strip())
    except (TypeError, ValueError):
        return False, f"'{answer}' is not a number"
    return True, "valid number"


def _v_password(answer: str) -> tuple[bool, str]:
    if answer:
        return True, "secret received (not echoed)"
    return False, "no secret received"


def _v_menu(answer: str, options: List[str]) -> tuple[bool, str]:
    if answer in options:
        return True, f"selected a valid option: {answer}"
    return False, f"'{answer}' is not one of the options"


# ---------------------------------------------------------------------------
# Bank entry
# ---------------------------------------------------------------------------

@dataclass
class QuestionCase:
    """One question of the bank.

    Attributes:
        id: Stable identifier of the case.
        title: What the case tests.
        message: The full assistant message, as the agent would emit it.
        expected_type: The input type the detection rules should produce.
        default_answer: The fallback used when the human does not answer.
        timeout: Seconds to wait; ``-1`` means "wait forever".
        validator: Checks the answer the human gave.
        options: The options of a menu question (for the validator).
        regression: What defect this case caught.  The case stays in the
            bank forever: it is the regression test for that defect, and
            the harness prints the text so that a failure names the bug
            it guards against.
    """

    id: str
    title: str
    message: str
    expected_type: str
    default_answer: str = ""
    timeout: int = -1
    validator: Callable[..., tuple[bool, str]] = _v_non_empty
    options: List[str] = field(default_factory=list)
    regression: str = ""

    def validate(self, answer: str) -> tuple[bool, str]:
        """Return ``(ok, reason)`` for *answer*."""
        if self.validator is _v_menu:
            return self.validator(answer, self.options)
        return self.validator(answer)


# ---------------------------------------------------------------------------
# The bank
# ---------------------------------------------------------------------------

QUESTION_BANK: List[QuestionCase] = [
    # ---------------------------------------------------------------- text
    QuestionCase(
        id="text-01-simple",
        title="Plain free-text question",
        message="What is the name of the branch you want me to create?",
        expected_type="text",
        default_answer="feature/default",
        validator=_v_non_empty,
        regression=(
            "the open question 'What is the name of the branch you want me to create?' was prompted as yes/no: the 'want me to' heuristic won over the open-question frame"
        ),
    ),
    QuestionCase(
        id="text-02-with-context",
        title="Free text buried under a long report",
        message=(
            "I inspected the repository and found the following.\n"
            "\n"
            "* The working tree is clean — 3 commits ahead of `origin/main`.\n"
            "* The last CI run failed on the `integration` job, with the\n"
            "  error `connection reset by peer` coming from the artifact\n"
            "  download step, not from the test suite itself.\n"
            "* The `docs/` folder was regenerated during the last build and\n"
            "  carries 41 untracked changes that are not in the diff.\n"
            "\n"
            "Which of these should I investigate first?"
        ),
        expected_type="text",
        default_answer="the failing CI job",
        validator=_v_non_empty,
        regression=(
            "'Which of these should I investigate first?' is an open choice, but the 'should I' heuristic classified it as yes/no - the operator was asked for a yes or a no instead of a choice"
        ),
    ),
    QuestionCase(
        id="text-03-explicit-marker",
        title="Free text forced by an explicit [HITL:text] marker",
        message="[HITL:text] Enter the hostname of the MikroTik router to inspect.",
        expected_type="text",
        default_answer="192.168.88.1",
        validator=_v_non_empty,
        regression=(
            "the '[HITL:text]' marker was honoured by detect_input_type but not by the question detection, so the message was not seen as a question at all"
        ),
    ),
    QuestionCase(
        id="text-04-mentions-yes-and-no",
        title="Question that merely mentions 'yes' and 'no' (must stay text)",
        message=(
            "What is the difference between a `no-op` and a `yes` condition "
            "in this workflow?"
        ),
        expected_type="text",
        default_answer="a no-op changes nothing",
        validator=_v_non_empty,
    ),
    # -------------------------------------------------------------- yes/no
    QuestionCase(
        id="yesno-01-shall-i",
        title="Binary confirmation ('Shall I ...?')",
        message="Shall I run the destructive cleanup command against the staging database?",
        expected_type="yesno",
        default_answer="no",
        validator=_v_yes_no,
    ),
    QuestionCase(
        id="yesno-02-confirm-destructive",
        title="Confirmation of a destructive operation",
        message="Please confirm that I should delete the local branch `feature/legacy`.",
        expected_type="yesno",
        default_answer="no",
        validator=_v_yes_no,
    ),
    QuestionCase(
        id="yesno-03-password-mention-only",
        title="Mentions a password but does not ask for it (must stay yes/no)",
        message="Should I rotate the password for the service account in the deployment pipeline?",
        expected_type="yesno",
        default_answer="no",
        validator=_v_yes_no,
    ),
    QuestionCase(
        id="yesno-04-explicit-marker",
        title="Binary confirmation forced by an explicit [HITL:yesno] marker",
        message="[HITL:yesno] Force-push to `main` with `--force-with-lease`?",
        expected_type="yesno",
        default_answer="no",
        validator=_v_yes_no,
    ),
    # ---------------------------------------------------------------- menu
    QuestionCase(
        id="menu-01-three-options",
        title="Choice between three options",
        message=(
            "I can apply the fix in three ways. Which one should I use?\n"
            "\n"
            "- Patch the config file directly\n"
            "- Add an environment variable override\n"
            "- Regenerate the file from the schema"
        ),
        expected_type="menu",
        default_answer="Patch the config file directly",
        options=[
            "Patch the config file directly",
            "Add an environment variable override",
            "Regenerate the file from the schema",
        ],
        validator=_v_menu,
        regression=(
            "a list of choices that follows the question in its own block was not recognised as a menu, so a three-way choice was prompted as yes/no"
        ),
    ),
    QuestionCase(
        id="menu-02-lead-in-colon",
        title="Choice list introduced by a lead-in ending in a colon",
        message=(
            "The commit touches 4 files. Also, would you like me to:\n"
            "\n"
            "- squash the commits into one\n"
            "- keep the history as it is\n"
            "- rebase onto `origin/main` first"
        ),
        expected_type="menu",
        default_answer="keep the history as it is",
        options=[
            "squash the commits into one",
            "keep the history as it is",
            "rebase onto `origin/main` first",
        ],
        validator=_v_menu,
        regression=(
            "a list of choices that follows the question in its own block was not recognised as a menu, so a three-way choice was prompted as yes/no"
        ),
    ),
    QuestionCase(
        id="menu-03-two-options",
        title="Choice between two options",
        message=(
            "Which environment should I deploy to?\n"
            "\n"
            "1. staging\n"
            "2. production"
        ),
        expected_type="menu",
        default_answer="staging",
        options=["staging", "production"],
        validator=_v_menu,
        regression=(
            "a list of choices that follows the question in its own block was not recognised as a menu, so a two-way choice was prompted as yes/no"
        ),
    ),
    # ------------------------------------------------------------ password
    QuestionCase(
        id="password-01-api-key",
        title="Secret that is asked for by name",
        message="Please enter the API key for the GitHub remote.",
        expected_type="password",
        default_answer="",
        validator=_v_password,
        regression=(
            "'Please enter ...' was not recognised as a question: the detection vocabulary had no ask verbs ('enter', 'provide'), although the type detection uses exactly those verbs"
        ),
    ),
    QuestionCase(
        id="password-02-passphrase",
        title="Secret asked for with an explicit marker",
        message="[HITL:password] Enter the passphrase for the encrypted backup archive.",
        expected_type="password",
        default_answer="",
        validator=_v_password,
        regression=(
            "the '[HITL:password]' marker was not honoured by the question detection, so the message was not seen as a question at all"
        ),
    ),
    # ------------------------------------------------------------- timeout
    QuestionCase(
        id="timeout-01-short-timeout",
        title="Short timeout — the default answer is used",
        message="What is the target environment name?",
        expected_type="text",
        default_answer="staging",
        timeout=5,
        validator=_v_non_empty,
    ),
    # ------------------------------------------------------- real LLM output
    QuestionCase(
        id="llm-01-inline-options",
        title="Real LLM output with inline (a)/(b)/(c) options",
        message=(
            "A couple of things worth your input before I act:\n"
            "\n"
            "1. **There is nothing to delete right now** — the path is already\n"
            "   absent, so a delete would be a no-op.\n"
            "2. **Did you mean a different path?** Similar candidates in `/tmp`\n"
            "   include `dump.txt` and `ci-gate-failures.txt`.\n"
            "I have not deleted anything and will not until you reply. "
            "Options: **(a)** proceed with the delete as a no-op, "
            "**(b)** point me at the correct existing file, or **(c)** cancel."
        ),
        expected_type="menu",
        default_answer="cancel",
        options=[
            "proceed with the delete as a no-op",
            "point me at the correct existing file",
            "cancel",
        ],
        validator=_v_menu,
        regression=(
            "the menu detection only understood Markdown list items; the inline '(a) ... (b) ... (c)' options a real LLM produces were not recognised, so a three-way choice was prompted as yes/no"
        ),
    ),
    QuestionCase(
        id="llm-02-preceding-options",
        title="Real LLM output with the (a)/(b)/(c) options *before* the question",
        message=(
            "The file does not exist, so the delete would be a no-op. Nothing has "
            "been deleted at any point in this session, and I won't act until you "
            "answer.\n"
            "\n"
            "Reply with one of:\n"
            "\n"
            " \u2022 **(a)** \"yes, delete it\" \u2014 I run the rm anyway so the "
            "attempt is actually logged.\n"
            " \u2022 **(b)** a corrected path if you meant a different file.\n"
            " \u2022 **(c)** \"no\" / \"cancel\" \u2014 no action taken.\n"
            "\n"
            "Waiting for your answer.\n"
            "\n"
            "Confirmation requested: delete `/tmp/hitl-live-test.txt`?"
        ),
        expected_type="menu",
        default_answer="cancel",
        options=[
            '"yes, delete it" \u2014 I run the rm anyway so the attempt is actually logged',
            "a corrected path if you meant a different file",
            '"no" / "cancel" \u2014 no action taken',
        ],
        validator=_v_menu,
        regression=(
            "the menu detection only looked *forward* for the choices; a model that writes 'Reply with one of: (a) ... (b) ... (c) ...' and only then the question offered the choices first, so the three-way choice was prompted as free text"
        ),
    ),
    # --------------------------------------------------------- free answers
    QuestionCase(
        id="free-01-number",
        title="Free-text answer that should be a number",
        message="What is the timeout in seconds for the health check?",
        expected_type="text",
        default_answer="30",
        validator=_v_number,
    ),
]


def case_by_id(case_id: str) -> Optional[QuestionCase]:
    """Return the case with *case_id*, or ``None``."""
    for case in QUESTION_BANK:
        if case.id == case_id:
            return case
    return None


__all__ = [
    "QUESTION_BANK",
    "QuestionCase",
    "case_by_id",
]
