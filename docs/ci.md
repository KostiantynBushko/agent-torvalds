# Continuous Integration

The repository has a GitHub Actions workflow that runs the test suite on
every push to `master` and on every pull request.

The suite does **not** pass yet. It carries a set of known failures — 40 of
them at the time of writing — so a plain `pytest` run is always red. A CI
workflow that is red before anyone writes a line of code is not a safety
net; it is noise, and everyone learns to ignore it.

The workflow therefore runs a **gate** instead of pytest directly.

---

## Table of Contents

1. [How it works](#1-how-it-works)
2. [The gate](#2-the-gate)
3. [The known-failure baseline](#3-the-known-failure-baseline)
4. [The pinned environment](#4-the-pinned-environment)
5. [Running it locally](#5-running-it-locally)
6. [Tightening the baseline](#6-tightening-the-baseline)
7. [The check of the user paths](#7-the-check-of-the-user-paths)
8. [What is not covered](#8-what-is-not-covered)

---

## 1. How it works

```
pytest runs
     │
     ▼
the failure list is compared with tests/ci_baseline.txt
     │
     ├── a failure that is NOT in the baseline  → the build fails
     └── only known failures                    → the build passes
```

A new regression breaks the build. The known failures do not.

The workflow is [`.github/workflows/tests.yml`](../.github/workflows/tests.yml).
It runs on `ubuntu-latest` with Python 3.12, installs the pinned
dependencies, and runs the gate. When the build is red, the failure list is
uploaded as the artifact `pytest-failures`.

## 2. The gate

`scripts/ci_test_gate.py` is the gate. It runs pytest in-process with a
small plugin that collects the node id of every failing test, and compares
the result with the baseline.

```bash
# the whole suite
python scripts/ci_test_gate.py

# a subset
python scripts/ci_test_gate.py -k hitl

# regenerate the baseline
python scripts/ci_test_gate.py --write-baseline
```

| Exit code | Meaning |
|---|---|
| `0` | no new failures — the build may proceed |
| `1` | a new failure appeared — the build must not proceed |
| `2` | the gate itself could not run |

The gate reports the failures that have been *fixed* as well, so the
baseline can be tightened as the underlying bugs are repaired.

## 3. The known-failure baseline

`tests/ci_baseline.txt` lists the node id of every test that is known to
fail — one per line, with a header explaining how to regenerate it.

The failures are concentrated in nine files:

| File | Failures | What is wrong |
|---|---:|---|
| `tests/test_events_manual.py` | 10 | the manual event scripts assert on a flow that no longer matches the consumer |
| `tests/test_hitl_runtime_toggle.py` | 8 | the command parser does not recognise the `hitl-*` commands |
| `toolkits/math-toolkit/tests/test_operations.py` | 7 | the toolkit does not raise on a division by zero, a negative root or a bad RPN expression |
| `tests/test_project_manager.py` | 6 | the scanner scores the fixture projects below the expected confidence |
| `toolkits/apt-toolkit/tests/test_operations.py` | 4 | the apt toolkit's contract tests disagree with the implementation (one of them is a collection error) |
| `tests/test_whiptail_workflow_integration.py` | 2 | the whiptail workflow's error-recovery path does not behave as the test expects |
| `tests/test_whiptail_password.py` | 1 | the test patches `__builtins__` as a module, which does not exist |
| `tests/test_stats.py` | 1 | an `async def` test without the `asyncio` marker |
| `tests/test_event_consumer_hitl.py` | 1 | the consumer's `send_event` is not reached in the mocked handler |

Every other test file passes. That is where the gate is strict.

## 4. The pinned environment

`requirements.txt` states the *minimum* versions the agent supports.
`requirements-ci.lock` pins the exact versions the baseline was recorded
with.

The pin matters: the baseline is a list of node ids, and a dependency
release that changes a failure would make the gate report it as new
breakage — a false alarm that teaches people to ignore the gate. Pinning
the environment keeps the baseline meaningful.

Three declared requirements are deliberately **not** in the lock, because
the baseline was recorded without them:

* `llama-index-llms-llama-cpp` pulls `llama-cpp-python`, which has no
  prebuilt wheel and is compiled from source; the test suite does not need
  it, and building it on every runner would cost minutes and add a
  toolchain dependency to CI;
* `asyncssh` — the SSH toolkit is not in `master` yet;
* `routeros_api` — the MikroTik toolkit's tests skip without it.

The lock mirrors the environment the baseline was recorded in, and that is
exactly what makes the baseline reproducible: the same skips, the same
failures, on every runner.

## 5. Running it locally

```bash
# the same gate CI runs
.venv/bin/python scripts/ci_test_gate.py

# a subset, with the raw pytest output
.venv/bin/python scripts/ci_test_gate.py -k hitl
```

The gate is the only thing that has to change when a test is added — a
passing test needs no baseline entry, and a failing one has to be either
fixed or recorded.

## 6. Tightening the baseline

The baseline is a ratchet: it should only get shorter.

When a known failure is fixed, the gate reports it:

```
Fixed — these no longer fail, so the baseline can be tightened:
  - toolkits/math-toolkit/tests/test_operations.py::TestBasicArithmetic::test_divide_by_zero
```

Regenerate the file with:

```bash
python scripts/ci_test_gate.py --write-baseline
```

and commit the result. The diff is the proof that the baseline shrank.

## 7. The check of the user paths

The machine of the operator is private, and every path of it must never
leave the machine: not in the source, not in a commit message, not in the
body of a pull request, not in an issue, not in a comment.  This is Rule 8
of `DEVELOPMENT_RULES.md`.

The test gate reads the files of the repository.  A second workflow —
`.github/workflows/user_paths.yml` — reads the surfaces that are **not**
files of the repository: the body of a pull request, the body of an issue,
the body of a comment, and the commits of a pull request.

```bash
# what the workflow runs
python scripts/check_no_user_paths.py files
python scripts/check_no_user_paths.py commits origin/master..HEAD
python scripts/check_no_user_paths.py text body.md
```

The checker finds a path by the **shape** of a home — `/home/<account>`,
`/Users/<account>`, `C:\Users\<account>` — and by the **identity** of the
machine it runs on: the account, the home, the private folders of the
working copy.  The identity is computed at runtime and never written down,
so the rule does not publish the account it forbids.  The placeholders a
documentation writes (`/home/user/...`) are left alone.

A CI runner does not know the machine of the operator.  The names that
only the machine knows can be given to the check through the secret
`PRIVATE_NAMES` — a comma-separated list — which the workflow hands to
the script in `TORVALDS_PRIVATE_NAMES`.

The check reads the commits that are **new**, not the whole history: the
history carries the leaks of the past, and a gate that reads it would be
red before anyone writes a line of code — the same reason the test gate
has a baseline.  The audit of the history is the probe:
`investigate/user-path-exposure/probe_user_paths.py`.

## 8. What is not covered

* **The `menu` and the multi-window orchestrators** are exercised by the
  unit suites, but the agent's end-to-end behaviour against a live Ollama
  server is not — that needs a model, and the workflow deliberately does
  not pull 16 GB of weights onto every runner.
* **The MikroTik toolkit's real-router validation** needs a physical
  router or a CHR image. The tests are marked `integration` and are not
  part of the gate.
* **The tests in the nine files above** are covered only by the baseline.
  A *new* failure in one of them is caught, but a *changed* failure in one
  of them is not distinguished from the known one — the gate compares node
  ids, not assertions.
* **The history is not rewritten by the check.**  A path that was
  published in an old commit is still published in it; the check keeps
  the *new* commits clean, and the audit of the history is a report for
  the operator, not a gate.  Removing the leaks of the past is a rewrite
  of the history and a force-push — Rule 4 asks for the confirmation
  first.
