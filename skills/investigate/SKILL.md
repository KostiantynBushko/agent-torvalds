---
name: investigate
description: Investigate a question about this project and write the report. Use it when the user asks to find out why something happens, to measure the cost of a feature, or to look into a defect before changing the code.
---

# Investigate

An investigation is a **question, evidence, and a report** that the evidence
supports.  The work lives in `investigate/<topic>/`, and the question is
answered before the code is changed.

## The folder

```
investigate/<topic>/
├── PROPOSAL.md            # what is proposed, and why — before the work
├── INVESTIGATION_REPORT.md # the report: the question and the evidence
└── <probe>.py             # the script that produces the evidence
```

The topic is the name of the question, not the name of the fix:
`investigate/agent-skills/`, `investigate/context-window-proof/`,
`investigate/apt-toolkit-module/`.

`PROPOSAL.md` is optional — it is written before the work, when there is
something to propose.  `IMPLEMENTATION_PLAN.md` and `REQUIREMENTS.md` are
optional too.  The **report** is not optional: it is the deliverable.

## The probe

The probe is the evidence, and it has one rule: **it is read-only.**  It
measures, prints and returns — it never writes to the repository, never
changes a configuration and never talks to a service that is not there for
the purpose.  A probe that changes something cannot be run twice, and a
measurement that cannot be reproduced is not a measurement.

The report names the probe at the top, next to the question:

```markdown
**Probe:** [`probe_skill_costs.py`](probe_skill_costs.py) — read-only, prints the
cost of the catalog in tokens.
```

Run the probe and paste its output into the report.  The numbers in the report
are the numbers the probe printed — not numbers written from memory.

## The shape of the report

The reports of this project follow the same shape:

```markdown
# Investigation Report: <the question, as a sentence>

<the question, and why it was asked>
**Probe:** [`<probe>.py`](<probe>.py) — read-only, ...

## 1. The question
## 2. The measurement      # or: The evidence
## 3. The root cause
## 4. The fix
## 5. Verification
## 6. What is *not* in this change, and why
## 7. The recommendation to the operator
```

Two of these sections carry the weight:

* **The measurement** — the numbers, and the budget they are measured
  against.  A number without its denominator is not a measurement.
* **What is *not* in this change, and why** — the scope that was deliberately
  left out, and the reason it was left out.  A report that does not say this
  leaves the reader guessing.

The last section is addressed to the operator: what the investigation
recommends, and what it costs to accept.

## The rules

* **Measure before you design.**  The measurement is the part that changes the
  design — that is why it is the first thing in the folder.
* **One question per folder.**  Two questions make two folders.
* **The report is for a reader who has not seen the code.**  It explains the
  defect in terms of what the user sees, not in terms of the function that
  raises it.
* **The changelog entry links the folder.**  The entry in `CHANGELOG.md`
  says what changed and points at `investigate/<topic>/` for the evidence.
* **The work that follows the report is a separate change**, with its own
  branch and its own pull request.
