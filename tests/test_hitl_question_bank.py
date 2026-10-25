"""
The HITL question bank is the acceptance criterion of the question rules.

``scripts/hitl_question_bank.py`` holds 16 real assistant messages — the
four input types, the traps and one real LLM output — together with the
input type each of them *should* produce.  The rules that decide the type
live in :mod:`components.hitl_question`; this suite runs every case of the
bank through them.

The operator reported that every question was prompted with ``[y/N]`` —
including the questions that asked for a name and the ones that offered
three choices.  Nine of the sixteen cases caught that.

Category: HITL / Tests
Retriever Keywords: hitl, question bank, input type, acceptance, regression
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SELF_DEV = Path(__file__).resolve().parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from components.hitl_question import detect_input_type, split_question  # noqa: E402
from scripts.hitl_question_bank import QUESTION_BANK  # noqa: E402


def _ids() -> list:
    return [case.id for case in QUESTION_BANK]


@pytest.mark.parametrize("case", QUESTION_BANK, ids=_ids())
def test_the_bank_case_produces_the_expected_type(case) -> None:
    """Every case of the bank gets the input type it asks for."""
    split = split_question(case.message)

    assert split is not None, (
        f"{case.id}: the message was not recognised as a question"
    )

    actual = detect_input_type(split.question, split.options)
    assert actual == case.expected_type, (
        f"{case.id}: expected {case.expected_type!r}, got {actual!r} "
        f"(question={split.question!r}, options={split.options!r})"
    )


@pytest.mark.parametrize("case", QUESTION_BANK, ids=_ids())
def test_the_bank_case_is_a_question(case) -> None:
    """Every case of the bank is a question — none is swallowed."""
    assert split_question(case.message) is not None, case.id


@pytest.mark.parametrize("case", QUESTION_BANK, ids=_ids())
def test_the_question_is_not_repeated_in_the_context(case) -> None:
    """The question is the question — the report does not repeat it.

    A lead-in that ends with a colon was both the question *and* the last
    line of the report, so the operator read it twice and the report
    itself was lost.
    """
    split = split_question(case.message)

    assert split is not None, case.id
    if not split.context.strip():
        return
    assert split.question not in split.context, (
        f"{case.id}: the question is repeated in the context "
        f"(question={split.question!r}, context={split.context!r})"
    )


def test_the_report_before_the_question_survives() -> None:
    """The text before the question is the report — it must not be lost.

    "The commit touches 4 files. Also, would you like me to:" is one line
    with two sentences.  The question is the second one; the first one is
    the report and belongs in the context.
    """
    message = (
        "The commit touches 4 files. Also, would you like me to:\n"
        "\n"
        "- squash the commits into one\n"
        "- keep the history as it is\n"
    )
    split = split_question(message)

    assert split is not None
    assert split.question == "Also, would you like me to:"
    assert split.context == "The commit touches 4 files."
    assert split.options == ("squash the commits into one", "keep the history as it is")


def test_the_bank_covers_every_input_type() -> None:
    """The bank is only a criterion when it covers the whole vocabulary."""
    types = {case.expected_type for case in QUESTION_BANK}
    assert types == {"text", "yesno", "menu", "password"}


def test_every_case_is_answered_by_its_validator() -> None:
    """A case that no answer can satisfy would be a broken criterion."""
    for case in QUESTION_BANK:
        candidates = [
            "yes",
            "1",
            "42",
            "s3cret",
            "an answer",
            case.options[0] if case.options else "x",
        ]
        assert any(case.validate(answer)[0] for answer in candidates), case.id


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
