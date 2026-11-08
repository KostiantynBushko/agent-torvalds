---
name: develop
description: Carry a change through a software project, from the request to the pull request. Use it when the user asks for a feature, a fix, or any other change to the code.
---

# Develop

A change is **a branch, a diff, a green gate and a pull request**.  The
operator merges it.  The agent never merges, and never commits or pushes
without the approval for that action.

This skill is the **order** of the work, for any software project.  The
procedures live in the skills that cover them — `investigate`, `run-tests`,
`add-toolkit`, `release` — and are loaded when the task calls for them.
Nothing is repeated here.

Where a step names a file or a command, the name belongs to the project the
work is done in: `DEVELOPMENT_RULES.md`, `scripts/ci_test_gate.py` and
`investigate/<topic>/` are the names of *this* repository.  In another
project the same steps are carried by that project's own files.

## 1. Read the contract

The rules of a change — in this repository `DEVELOPMENT_RULES.md` and its
seven rules — are read at the start of every session that touches the code.
A project that carries no such file has no contract to read, and the steps
below are the whole procedure.  The contract is the persistence mechanism,
and this skill does not repeat it.

## 2. Understand the thing before changing it

The cause of a defect is not known until it is measured.  When the request
is that something is broken, slow or wrong, load `investigate` and follow
it: a folder under `investigate/<topic>/`, a **read-only** probe, and a
report that carries the evidence.

A feature that has not been measured does not need a probe, but it needs
the shape of the thing written down before the code is written.

## 3. Branch

```bash
git checkout -b feature/<name> <base-branch>
```

The name says what the change is, in the words of the request.  The branch
is what makes the work reviewable — the operator's tree is not the place
where the work happens.

## 4. Implement the smallest change that answers the request

* The change does what was asked, and nothing else.
* A path in the source is **computed**, never written down.
* A test that proves the fix — and it fails without it.

## 5. The gate

```bash
.venv/bin/python scripts/ci_test_gate.py
```

`new failures` must be `0`.  The suite of this project is always red — it
carries known failures — so a run that ends in "40 failed" is the normal
state of the repository and not a regression.  `run-tests` carries the run
and the baseline.

## 6. The changelog

Under `## [Unreleased]`, in the section that fits: **what changed and
why** — what was wrong, what was measured, and why this fix and not
another.  The entry links `investigate/<topic>/` when there is one.

## 7. The documentation

A change that changes what the project *does* changes what the project
*says*.  `docs/` and the README follow the code.  A procedure that is too
long for the prompt belongs in a skill of its own.

## 8. Show the diff, and ask

```bash
git status
git diff
```

The operator sees the diff and a summary of the changes **before** anything
is committed.  The commit message says what changed and why.

## 9. Push, and open the pull request

Before every push: the staged content, the commit message and the body of
the pull request are searched for the home directory of the operator, and
what was found is reported.  A finding is fixed, not explained away.

The pull request carries the reason, the evidence, and what is **not** in
the change and why.

## The rules that hold at every step

* **Never commit, push, tag or merge without the approval for that
  action.**  The approval is per action, not per session.
* **Never merge.**  The pull request is opened and reviewed; the operator
  merges it.
* **Destructive operations are confirmed first** — `rm`, a deleted branch,
  a force-push, a rebase, a reset.
* **The private folder of the operator is never published** — not in the
  source, not in the documentation, not in a commit message, not in the
  body of a pull request.
* **A question asked of the operator follows the timeout** — `-1` means
  stop and wait; a finite timeout means wait, and when it expires the
  agent acts on its own judgement and says so.

## What the operator is told

At every step: what changed, what was measured, what was deliberately left
out and why, and what needs the approval.
