#!/usr/bin/env python3
"""
Diagnostic #4 — a decorated question is prompted as a yes/no question.

What the operator reported (``wrong-user-input.txt``)
-----------------------------------------------------
The agent answered a question about the D11/D12 fix with a long report.
The last line of that report was a *labelled, quoted* question::

    question: 'Which one should I use?'

The console answered it with::

    [y/N]

The question cannot be answered with a yes or a no — it asks which of the
three options the agent should use — so the prompt told the operator the
wrong thing, and the answer he typed was wrong because of it.

Why
---
``components.hitl_question._is_yes_no()`` looks at the **raw** question
string:

* the wh-question veto (``_WH_HEAD``) only fires when the question word is
  at the *head* of the string.  A quote (``'…'``), a pair of Markdown
  emphasis markers (``**…**``) or a label (``question:``) in front of it
  hides the question word;
* the offer rules (``"should I"``, ``"shall I"``, …) then match the
  *"should I"* **inside** the question and turn it into a confirmation.

The wrapping is not part of the question.  The question is what the
operator has to answer, and it has to be read through its *core* — the
question without the quotes, the emphasis and the label.

This script measures the classification on the operator's payload and on
the variants of the same question.

Usage::

    .venv/bin/python investigate/hitl-questions-issue/diag_decorated_question.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SELF_DEV = _HERE.parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from components.hitl_question import detect_input_type, split_question  # noqa: E402


#: The operator's report, condensed: the same shape, the same last line.
OPERATOR_REPORT = (
    "That deletion is already in place \u2014 it was the D12 fix, committed "
    "and pushed.\n"
    "\n"
    "What gets deleted, and what doesn't\n"
    "\n"
    "Case A concretely:\n"
    "\n"
    "  message:  \"I inspected the repo and found the following.\"\n"
    "  context:  'I inspected the repo and found the following.'\n"
    "  options:  ('patch the config file', 'add an env var', "
    "'regenerate the file')\n"
    "\n"
    "The rule is deliberately narrow: only the block immediately before a "
    "marked list is cut out of the report.\n"
    "\n"
    "question: 'Which one should I use?'"
)

#: The prompt the console shows for every input type.
PROMPTS = {
    "text": "Your response: ",
    "yesno": "[y/N]",
    "menu": "Select option [1]: ",
    "password": "Enter password: ",
}

#: The variants of the same question, and the type each of them wants.
VARIANTS = [
    ("plain", "Which one should I use?", "text"),
    ("quoted", "'Which one should I use?'", "text"),
    ("double quoted", '"Which one should I use?"', "text"),
    ("emphasised", "**Which one should I use?**", "text"),
    ("labelled", "question: 'Which one should I use?'", "text"),
    ("short label", "Q: Which one should I use?", "text"),
    ("clause", "I found three options, so which one should I use?", "text"),
    ("ask verb", "I need to know which one should I use?", "text"),
]

#: The traps: the fix must not turn these into open questions.
TRAPS = [
    ("offer", "Shall I run the cleanup?", "yesno"),
    ("offer", "Do you want me to delete it?", "yesno"),
    ("relative clause", "Should I use the tool which deletes the branch?", "yesno"),
    ("relative clause", "Do you want me to check which branches are stale?", "yesno"),
    ("relative offer", "What is the name of the branch you want me to create?", "text"),
]


def _classify(message: str) -> tuple[str, str]:
    """Return ``(question, input_type)`` for *message*."""
    split = split_question(message)
    if split is None:
        return "", "n/a"
    return split.question, detect_input_type(split.question, split.options)


def main() -> int:
    print("=" * 78)
    print("DIAGNOSTIC #4 — a decorated question is prompted as yes/no")
    print("=" * 78)

    failures = 0

    # ------------------------------------------------------------------
    # The operator's payload
    # ------------------------------------------------------------------
    question, detected = _classify(OPERATOR_REPORT)
    print()
    print("--- the operator's report " + "-" * 49)
    print("last line                : question: 'Which one should I use?'")
    print(f"question the operator sees: {question!r}")
    print(f"input type                : {detected!r}")
    print(f"prompt the operator gets  : {PROMPTS.get(detected, '?')!r}")
    if detected == "yesno":
        print(
            "  => VERDICT: DEFECT — the question asks for a choice and is "
            "prompted\n     as a confirmation."
        )
        failures += 1
    else:
        print("  => VERDICT: no defect — the question is prompted for what it asks.")

    # ------------------------------------------------------------------
    # The variants
    # ------------------------------------------------------------------
    print()
    print("--- the variants of the same question " + "-" * 34)
    print(f"{'variant':16s} {'type':7s} {'expected':9s} prompt")
    for name, message, expected in VARIANTS:
        _question, detected = _classify(message)
        prompt = PROMPTS.get(detected, "?")
        mark = "ok" if detected == expected else "BUG"
        print(f"{name:16s} {detected:7s} {expected:9s} {prompt!r}  {mark}")
        if detected != expected:
            failures += 1

    # ------------------------------------------------------------------
    # The traps
    # ------------------------------------------------------------------
    print()
    print("--- the traps " + "-" * 62)
    print(f"{'kind':16s} {'type':7s} {'expected':9s} question")
    for name, message, expected in TRAPS:
        _question, detected = _classify(message)
        mark = "ok" if detected == expected else "BUG"
        print(f"{name:16s} {detected:7s} {expected:9s} {message!r}  {mark}")
        if detected != expected:
            failures += 1

    print()
    print("=" * 78)
    if failures:
        print(f"RESULT: {failures} mis-classification(s) — the defect is CONFIRMED.")
    else:
        print(
            "RESULT: no mis-classification — the wrapping of a question does "
            "not change\n        the kind of answer it asks for."
        )
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
