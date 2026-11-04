# Development Rules

These rules govern how the Torvalds agent modifies this codebase. They are
**persisted here** so that they survive across sessions and are available to
any future agent invocation.

**Last updated:** 2026-11-03 — the **self-development clone is gone**. There is no
second copy of the repository any more: the agent works in the working copy it is
running in, on a branch of its own, and the operator's tree is the place where the
work happens. The rules that did not depend on the clone — the approval, the
destructive operations, the timeout contract and the privacy of the operator's
home folder — stayed.

---

## Rule 1 — The agent works in the current working copy

There is **no** separate clone. The agent modifies the repository it is running
in, on a branch of its own:

```bash
git checkout -b feature/<name> master
```

The branch is what makes the work reviewable: the changes are inspected, and
they reach `master` through a pull request or through the operator merging the
branch — deliberately, and not as uncommitted noise in the operator's tree.

The working copy is **not** read-only. The agent may edit the source, the
toolkits, the components, the tests and the documentation in it.

## Rule 2 — Commit and push require explicit approval

The agent must never `git commit` or `git push` without the operator's
explicit approval for that specific action. Before asking, the agent shows the
staged diff and a summary of the changes.

## Rule 3 — Show changes before committing

`git status` and `git diff` (or `git diff --staged`) are presented to the
operator before any commit is created.

## Rule 4 — Destructive operations require explicit confirmation

`rm`, branch deletion, force-push, history rewriting (rebase/reset) and any
irreversible action on the operator's data must be confirmed first.

## Rule 5 — Waiting for the operator follows the timeout

When the agent asks the operator a question, the timeout decides what the
agent is allowed to do:

* **`timeout = -1`** (no timeout) — the agent **stops and waits**.  It must
  not decide the question on its own; the answer arrives when the operator
  answers, however long that takes.
* **`timeout = N`** (a finite timeout) — the agent waits up to N seconds.
  When the timeout expires, the agent **acts on its own judgement** — and it
  says so in the report.

The operator stated this on 2026-10-22.  It is the contract the HITL timeout
machinery implements (`components/hitl_timeout.py`, `components/hitl_agent.py`),
and it is verified end to end by
`investigate/hitl-timeout-policy/verify_timeout_policy.py`.

A timed-out question is never reported as if it had been answered: the
operator must be able to tell "nobody answered, the agent decided" from "the
operator said so".  Defect **D16** (the model was fed the fallback answer as
if the human had said it) is fixed in `components/hitl_agent.py`; the model
now reads *"No human response — the wait ended without an answer. The
question was not answered; act on your own judgement."*

---

## Rule 6 — Never expose the private folder of the operator

The repository is **public**. The home directory of the operator — the
name of the account, and the path that carries it — is **private**, and it
must never be published: not in the source, not in the documentation,
not in a commit message, not in the body of a pull request, not in a
comment.

What is published is the **system default**, written the way the
documentation of a project writes it:

| | |
|---|---|
| `/home/<user>/.config/torvalds/config.toml` | `~/.config/torvalds/config.toml` |
| `/home/<user>/.torvalds/logs/agent.log` | `~/.torvalds/logs/agent.log` |
| the name of the account | `the-operator` |
| `<user>@example.com` | `operator@example.com` |

The examples of this rule are written with a **placeholder**, on purpose:
a rule that names the private folder in order to forbid it has already
published it.

The same holds for the **name** of the account, on its own: it is
private even without the path in front of it.

This is not only about the home directory.  Nothing that identifies the
operator — the account, the machine, the directories of the machine —
belongs in a public repository.

**In the code, a path that has to work on the machine of the operator is
computed, not written down.**  A literal path in the source is a path
that is wrong on every other machine:

```python
# wrong — it names one operator and one machine
sys.path.insert(0, '/home/<user>/<project>')

# right — it is the directory of the file itself
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

**A check before every push.**  The agent searches the staged content,
the commit message and the body of the pull request for the home
directory of the operator before it pushes, and it reports what it
found.  A finding is fixed, not explained away.

The check is not a habit either — it is a test:
`tests/test_no_private_paths.py` fails the build when a home directory
reaches the repository.

The operator stated this on 2026-10-29, after finding the home
directory of the operator in the body of a pull request.

---

---

## Rule 7 — These rules are persisted

This file **is** the persistence mechanism. It must be kept up to date whenever the
rules change, and must be read at the start of every session in which the agent
modifies the codebase.

If this file is missing, recreate it from the rules in the agent's operating
instructions before performing any modification.

The history of the work — every change, the reason for it and the evidence
that it works — is in `CHANGELOG.md` and in the `investigate/` folder. It is
not repeated here.
