# Investigation: the HITL question is wrong, and it is shown twice

**Reported by**: the operator — `/home/kbush/torvald-log/hitl_questions_issue/`
(`hitl-wrong-question.md`, `hitl_dublicate_question.md`)
**Date**: 2026-10-24
**Branch**: `investigate/hitl-questions-issue` (in the `self-development` clone)
**Status**: **implemented and verified** — 7 defects closed, the harness reports 8/8; not committed (awaiting the operator's approval)

---

## The short version

The Human-in-the-Loop *plumbing* works: the question reaches the consumer,
the answer reaches the agent, and the event is published exactly once. What
is broken is the *content* of the event and the *rendering* of it.

* The **entire assistant answer** is used as the question. A 3 180-character
  report that ends in a question mark becomes a 3 180-character question.
* The **input type** is guessed from that answer with substring matching, so
  a report that merely mentions *"secret redaction"* turns a yes/no
  question into a masked `Enter password: ` prompt.
* The consumer **renders the question twice** — once itself, once through the
  input module's prompt.

Seven defects in total; three of them are the operator's two complaints.

---

## Documents

| File | Contents |
|---|---|
| [`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md) | The full analysis: the two reports decoded, the seven defects with their code references and measurements, the root cause, and the fix in one page. |
| [`PROPOSAL_hitl_question_presentation.md`](PROPOSAL_hitl_question_presentation.md) | The design: the new `components/hitl_question.py`, the changes to the agent, the consumer and the input modules, the test plan, five phases, and the four decisions needed from the operator. |
| [`IMPLEMENTATION_REPORT.md`](IMPLEMENTATION_REPORT.md) | What was implemented, the three deviations from the proposal, the verification results, and what was left out. |

---

## Diagnostics

Every claim in the report is measured, not asserted. Run them from the
`self-development` clone:

```bash
cd self-development

# D2 — the input type is guessed from the whole answer
.venv/bin/python investigate/hitl-questions-issue/diag_input_type.py

# D3 — the question is rendered twice (and the render matrix per input type)
.venv/bin/python investigate/hitl-questions-issue/diag_duplicate_prompt.py

# D1 + D3 end to end: the real agent, the real workflow runtime, the real consumer
.venv/bin/python investigate/hitl-questions-issue/diag_roundtrip.py

# D4 + D5 + D6 + D7 — the re-ask guard, the workflow replay, the empty answer, the detection pattern
.venv/bin/python investigate/hitl-questions-issue/diag_reask.py
```

## Acceptance harness

The eight invariants a correct HITL question presentation must satisfy:

```bash
.venv/bin/python investigate/hitl-questions-issue/verify_hitl_question_presentation.py
```

| | invariant |
|---|---|
| I1 | the question is rendered exactly once |
| I2 | the event carries the question, not the whole answer; the rest is `context` |
| I3 | the input type follows the question alone |
| I4 | a password question is still shown |
| I5 | a rephrased question is not asked twice |
| I6 | an empty answer is reported as a timeout |
| I7 | a question ending with a code span is detected |
| I8 | a question is detected once per question |

**Current result: 8 of 8 hold.** The harness was written before the fix
and reported 1/8 against the unfixed tree. It was not modified when the
fix landed; when the `menu` input type was enabled afterwards, its input
double gained `menu_with_status()` so that it mirrors the production API
— the eight invariants themselves are unchanged.

---

## Layout

```
investigate/hitl-questions-issue/
├── README.md
├── INVESTIGATION_REPORT.md
├── PROPOSAL_hitl_question_presentation.md
├── fixtures/
│   └── issue_payloads.py          the operator's verbatim payloads
├── diag_input_type.py             D2
├── diag_duplicate_prompt.py       D3
├── diag_roundtrip.py              D1 + D3, end to end
├── diag_reask.py                  D4 + D5 + D6 + D7
└── verify_hitl_question_presentation.py    the acceptance harness
```

The payloads in `fixtures/issue_payloads.py` are the operator's text,
verbatim — the diagnostics measure the real thing and not a
reconstruction.

---

## Code touched by the defects

| Path | Line | Defect |
|---|---|---|
| `components/hitl_agent.py` | 119 `detect_input_type()` | D2 — the input type is guessed from the answer |
| `components/hitl_agent.py` | 87 `_QUESTION_PATTERNS` | D7 — a code-span question is not detected |
| `components/hitl_agent.py` | 384 `parse_agent_output()` | D1 — the whole answer becomes the question |
| `components/hitl_agent.py` | 506 `_was_answered()` | D4 — the exact-text re-ask guard |
| `components/hitl_agent.py` | 522 `_resolve_question_identity()` | D5 — the replay re-detects the question |
| `components/event_consumer.py` | 665 `_on_agent_question()` | D3 — the question is rendered |
| `components/event_consumer.py` | 748 `_collect_answer()` | D3, D6 — the question is rendered again; the empty answer |
| `components/console_input_module.py` | 229 `confirm()` | D3 — the prompt carries the question |
| `components/human_loop_handler.py` | 59, 89 | D2 — the duplicated heuristic and pattern list |

---

## Related work

| Investigation | Subject |
|---|---|
| `investigate/hitl-investigate/` | The HITL plumbing — why the feature never prompted at all (fixed). |
| `investigate/no-user-query-error/` | The prompt exceeding the context window (fixed). |
| `investigate/hitl-questions-issue/` | **This one** — what the operator sees when the HITL round-trip *does* work. |
