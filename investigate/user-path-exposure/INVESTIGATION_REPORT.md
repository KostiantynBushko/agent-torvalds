# The user paths of the machine must never leave it

**The operator stated on 2026-11-23** that the agent may expose a user
path of the machine in the text, in the code and in the commits it
generates, that this is **completely forbidden**, and that the rule has
to be strict:

> *the agent should never ever expose user path to the external
> resources, like github*

This report is the evidence: what the old rule covered, what it let
through, what is already published, and what was built to close the gap.

---

## What was measured

The probe — `investigate/user-path-exposure/probe_user_paths.py` — asks
three questions.  It writes **no path of the machine** into its own
output: the examples are built at runtime, from the machine itself, and
everything it prints is masked — the account becomes `<account>`, the
home becomes `~`.  A probe that leaks what it investigates proves
nothing.

### 1. Where a path can leave

The surfaces are not the same, and this is the heart of the matter:

| the surface | is it a file of the repository? | who read it before |
| :--- | :--- | :--- |
| a file of the repository | yes | the test gate |
| the message of a commit | no | **nobody** |
| the body of a pull request | no | **nobody** |
| the body of an issue | no | **nobody** |
| the body of a comment | no | **nobody** |
| the answer the agent gives to the operator | no | **nobody** |

The last one is the surface the operator was looking at: the answer the
agent writes is copied into a pull request more often than anyone
thinks.

### 2. What the check catches

With the checker of this report, every surface is caught, and the generic
form is left alone:

```
  a file of the repository         leaking: CAUGHT  clean: clean
  the message of a commit          leaking: CAUGHT  clean: clean
  the body of a pull request       leaking: CAUGHT  clean: clean
  the body of an issue             leaking: CAUGHT  clean: clean
  the body of a comment            leaking: CAUGHT  clean: clean
  the answer of the agent          leaking: CAUGHT  clean: clean
```

### 3. What is already out there

The history is read, and it is not clean:

```
  commits of the history                  : 507
  commits whose tree carries the name     : 379
  commit messages that carry the name     : 2
```

**379 of 507 commits** carry the name of the account of the operator.
The two commit messages quote the instruction of the operator that
carries the name.  The shapes that were published include the home of the
operator, the working copy itself, the folder of the logs, the folder of
the models, and an external drive with its label.

The tree of the repository is **clean** — the files were fixed when they
were found.  The history was not: a blob that is fixed in the working
tree is still published in every commit that carried it.

---

## The gap

**Rule 6** was already in the rulebook, and it was already a test —
`tests/test_no_private_paths.py` fails the build when a home directory
reaches the repository.  It is a good rule, and it is not enough:

| | Rule 6 and its test | what was missing |
| :--- | :--- | :--- |
| the path | the **home** of the operator | every path: the account in a path that is not a home, the private folders of the disk, the working copy |
| the surface | the **files** of the repository | the commit messages, the body of a pull request, the body of an issue, the body of a comment, the answer of the agent |
| the identity | the home of the machine the test runs on | the name of the account on its own, and the private folders |

The rule was written on 2026-10-29, after the home of the operator was
found **in the body of a pull request** — and the fix was made in the
body, not in a check.  A rule that is not a check is a habit; this
repository asks for more than that.

The agent was never told, either.  The operating instructions of the
agent — `project_manager/prompt_engine.py` and the legacy template of
`agent-torvalds.py` — carry no rule about the paths at all.  The agent
that writes the text, the code and the commit message is the one that
has to be told.

---

## What was built

**The rule.**  Rule 8 of `DEVELOPMENT_RULES.md` — *Never expose a user
path to anything outside the machine*.  It forbids the path in every
surface, it names the published form (`~`, `/home/<user>`,
`operator@example.com`, `<project>`), and it says that a path in the
code is computed, not written down.

**The checker.**  `scripts/check_no_user_paths.py` reads the tracked
files, the messages of the commits and the free text of a pull request,
an issue or a comment.  It finds a path in two ways:

* **the shape** of a home — `/home/<account>`, `/Users/<account>`,
  `C:\Users\<account>` — which is known everywhere, so the check works
  in a CI that has never seen the machine of the operator;
* **the identity** of the machine the check runs on — the account, the
  home, the private folders of the working copy — which is **computed**,
  never written down.

The placeholders a documentation writes (`/home/user/...`) are not a path
of anybody, and are left alone.

**The test.**  `tests/test_no_user_paths.py` fails the build when a
tracked file or a new commit carries a path, and it holds the checker
itself to the rule — the file that defines the patterns is scanned like
any other file.

**The workflow.**  `.github/workflows/user_paths.yml` reads the surfaces
that are **not** files of the repository: the body of a pull request,
the body of an issue, the body of a comment, and the commits of a pull
request.  This is the workflow that closes the gap of Rule 6.

**The agent is told.**  The rule is in the operating instructions of the
agent, in both templates, so it is in front of the agent at every
invocation — not only in a file the agent reads once.

---

## What is not covered

Stated plainly, because a check that is trusted more than it deserves
is worse than no check.

* **The whole history is not the gate.**  The gate reads the commits
  that are **new** (`origin/master..HEAD`).  The history carries the
  leaks of the past, and a gate that reads it would be red before anyone
  writes a line of code — the same reason the test gate has a baseline.
* **A CI knows the shape, not the machine.**  The identity of the
  operator is computed from the machine the check runs on, and a CI
  runner is not that machine.  The names that only the machine knows can
  be given to the CI through the secret `PRIVATE_NAMES` — a
  comma-separated list.
* **The check reads the repository.**  A path in a file that is never
  committed is not read by it.  The probe of this report reads the
  history, and it is the instrument for that.
* **The history is published.**  The 379 commits that carry the name
  are on the remote.  Removing them is a rewrite of the history and a
  force-push — Rule 4 asks the operator for the confirmation first, and
  it has not been given.  **This is the open question.**
