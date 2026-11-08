---
name: run-tests
description: Run the test suite of this project and read the result. Use it when the user asks to run the tests, to check that a change did not break anything, or before a commit, a push or a pull request.
---

# Run the tests

**The suite of this project does not pass.**  It carries 40 known failures, so
a plain `pytest` run always exits non-zero.  The signal is the **gate**, and
the gate fails only when a failure appears that is *not* in the baseline.

A run that ends in "39 failed" is the normal state of this repository, not a
regression.  Do not report it as a break, and do not try to fix the 40.

## The run that decides

```bash
.venv/bin/python scripts/ci_test_gate.py
```

| exit code | meaning |
|---|---|
| 0 | no new failures — the build may proceed |
| 1 | a new failure appeared — the build must not proceed |
| 2 | the gate itself could not run |

The gate prints the comparison it makes:

```
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
fixed since the baseline        : 0
```

**`new failures` is the line that decides.**  It must be `0`.  The other
three numbers move on their own: a non-zero `known failures` is the state of
the repository, and a non-zero `fixed since the baseline` is good news — it
means a known failure was repaired and the baseline can be tightened.

## Working on one thing

```bash
.venv/bin/python -m pytest tests/test_skills.py -q          # one file
.venv/bin/python -m pytest tests/ -q -k "skills or tokens"   # a subset
.venv/bin/python scripts/ci_test_gate.py -k hitl             # the gate, a subset
```

The gate passes the arguments it does not know to pytest, so `-k` works with
it.  Plain pytest gives the better output when reading a failure; the gate is
the run that decides whether the build may proceed.

## Where the known failures are

`tests/ci_baseline.txt` holds one node id per line.  The failures sit in nine
files:

| file | failures |
|---|---:|
| `tests/test_events_manual.py` | 10 |
| `tests/test_hitl_runtime_toggle.py` | 8 |
| `toolkits/math-toolkit/tests/test_operations.py` | 7 |
| `tests/test_project_manager.py` | 6 |
| `toolkits/apt-toolkit/tests/test_operations.py` | 4 |
| `tests/test_whiptail_workflow_integration.py` | 2 |
| `tests/test_whiptail_password.py` | 1 |
| `tests/test_stats.py` | 1 |
| `tests/test_event_consumer_hitl.py` | 1 |

Every other test file passes, and that is where the gate is strict.  The whole
story is in `docs/ci.md`.

## When a known failure is fixed

The gate reports it under `fixed since the baseline`.  Tighten the baseline
and commit the result — the diff is the proof that the baseline shrank:

```bash
.venv/bin/python scripts/ci_test_gate.py --write-baseline
```

The baseline is a ratchet: it should only get shorter.

## Before you report a result

1. Run the gate.
2. `new failures` must be `0`.
3. If the gate could not run at all, say that.  Do not report the suite as
   green because pytest was not run.
