#!/usr/bin/env python3
"""
Diagnostic #1 — the HITL *input type* is derived from the whole answer.

What the operator reported (``hitl-wrong-question.md``)
-------------------------------------------------------
The agent delivered a long report that ended with a perfectly ordinary
yes/no question:

    "Want me to start **Phase 0** (...) on a `feature/voice-toolkit` branch?"

The console answered it with::

    Enter password:

i.e. the prompt was a *masked password* prompt, not a yes/no prompt.

Why
---
``components.hitl_agent.detect_input_type()`` scans the **entire** message
for bare substrings::

    if any(kw in msg_lower for kw in ("password", "secret", "credential")):
        return "password"

The report contains the word "secret" (in "with secret redaction on by
default"), so the whole message was classified as a password request.
``components/human_loop_handler._detect_input_type()`` is a copy of the
same heuristic and has the same defect.

Two aggravating factors:

* the substrings are not word-boundary aware — "no" matches "**no**thing",
  "notification", "dns resolution is failing, so I can**no**t pull", and
  "docu**no**tation";
* "password" / "secret" / "credential" are checked *before* "yesno", so
  any report that merely mentions a secret wins over the yes/no check.

This script measures the classification on the two verbatim payloads.

Usage::

    .venv/bin/python investigate/hitl-questions-issue/diag_input_type.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SELF_DEV = _HERE.parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from components.hitl_agent import detect_input_type  # noqa: E402
from components.hitl_question import split_question  # noqa: E402
from components.human_loop_handler import _detect_input_type as hdl_detect  # noqa: E402

sys.path.insert(0, str(_HERE / "fixtures"))
from issue_payloads import ISSUE_PAYLOADS  # noqa: E402


#: The keyword sets the two detectors use.
PASSWORD_KEYWORDS = ("password", "secret", "credential")
YESNO_KEYWORDS = ("yes", "no", "confirm", "proceed", "continue")


def keyword_hits(text: str, keywords) -> list[str]:
    """Return every keyword that occurs in *text* (substring match)."""
    lowered = text.lower()
    return [kw for kw in keywords if kw in lowered]


def show_context(text: str, keyword: str, width: int = 70) -> str:
    """Return the snippet of *text* around the first occurrence of *keyword*."""
    lowered = text.lower()
    idx = lowered.find(keyword)
    if idx < 0:
        return ""
    start = max(0, idx - width // 2)
    end = min(len(text), idx + len(keyword) + width // 2)
    snippet = text[start:end].replace("\n", " ⏎ ")
    return f"…{snippet}…"


def main() -> int:
    print("=" * 78)
    print("DIAGNOSTIC #1 — HITL input type is inferred from the whole answer")
    print("=" * 78)

    failures = 0

    for name, text in ISSUE_PAYLOADS.items():
        detected = detect_input_type(text)
        hdl = hdl_detect(text)

        print()
        print(f"--- payload: {name} " + "-" * (58 - len(name)))
        print(f"length                 : {len(text)} characters")
        print(f"hitl_agent.detect_input_type()      -> {detected!r}")
        print(f"human_loop_handler._detect_input_type() -> {hdl!r}")

        pw_hits = keyword_hits(text, PASSWORD_KEYWORDS)
        yn_hits = keyword_hits(text, YESNO_KEYWORDS)

        print(f"password-keyword hits   : {pw_hits}")
        for kw in pw_hits:
            print(f"    {kw!r} found in: {show_context(text, kw)}")
        print(f"yes/no-keyword hits     : {yn_hits}")
        for kw in yn_hits:
            print(f"    {kw!r} found in: {show_context(text, kw)}")

        # The defect is: the type is derived from the *answer* instead of
        # from the *question*.  Both classifications are shown, and the
        # verdict compares them.
        split = split_question(text)
        question_type = (
            detect_input_type(split.question, split.options)
            if split is not None
            else "n/a"
        )
        print(f"type from the whole answer -> {detected!r}")
        print(f"type from the question    -> {question_type!r}")
        if split is not None:
            print(f"question ({len(split.question)} chars): {split.question[:90]!r}")

        if detected == "password" and question_type != "password":
            # The defect the operator reported: the report talked the agent
            # into a password prompt although the question asks nothing of
            # the sort.
            print(
                "  => VERDICT: DEFECT — the answer is typed 'password' but "
                "the question is not: the report decides the prompt."
            )
            failures += 1
        elif detected != question_type:
            # A question that carries options is a menu, while the same
            # text without the extracted options is a yes/no question.  That
            # difference comes from the question, not from the report.
            print(
                f"  => VERDICT: no defect — the difference ({detected!r} vs "
                f"{question_type!r}) comes from the options of the question "
                "itself, not from the report."
            )
        else:
            print(
                "  => VERDICT: no defect — the type follows the question, "
                f"and the report mentioning {pw_hits!r} does not decide the "
                "prompt."
            )

    # The operator's exact observation.
    print()
    print("-" * 78)
    print("Operator observation (hitl-wrong-question.md):")
    print("    the prompt shown was  'Enter password: '")
    print(
        "    components/event_consumer.py::_collect_answer() prints exactly that "
        "string\n    when input_type == 'password' — and it never prints the "
        "question."
    )
    print(
        "    So the operator never saw the question at all: the report was "
        "swallowed\n    by the password branch."
    )

    print()
    print("=" * 78)
    if failures:
        print(f"RESULT: {failures} payload(s) mis-classified.")
        if failures:
            print("        The defect is CONFIRMED.")
        else:
            print(
                "        The defect is NOT reproduced — the type follows the "
                "question."
            )
    else:
        print("RESULT: no mis-classification detected.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
