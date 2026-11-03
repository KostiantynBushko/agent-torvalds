# The `test_*.py` files in the repository root

**Date:** 2026-10-29

---

## 1. The question

Why are `test_callback_events_debug.py` and `test_live_agent_hitl.py` in the
repository root, and not under `tests/`?

## 2. The answer

**They are not tests.** They are **manual scripts** — a debug harness and a
live smoke test — that were named `test_*` out of habit. The root is where
the author was standing.

They must **not** go under `tests/`:

* `tests/` is on pytest's `testpaths`, so anything put there is collected.
* Both files are `async def` functions that pytest cannot run without
  `asyncio_mode`, and both need a **real LLM** (Ollama) and the network.

Putting them under `tests/` would add **seven failing tests** to the suite.

They belong in `scripts/`, which is where the project's other manual and
live scripts already live and which pytest does not collect.

---

## 3. What they are

| | `test_callback_events_debug.py` | `test_live_agent_hitl.py` |
|---|---|---|
| Lines | 815 | 118 |
| What it is | a **debug harness** for the callback event stream | a **live smoke test** of the agent |
| Its CLI | `--test <name>`, `--list` | none |
| Its entry point | `if __name__ == "__main__": main()` | `if __name__ == "__main__": asyncio.run(test_agent())` |
| What it needs | a live LLM | a live LLM |
| Near-twin | — | `scripts/hitl_live_llm_test.py` — a **different** script: one focused HITL scenario against a destructive action, answer read from stdin |

Neither is a pytest module. Both define `async def test_*` functions, which
pytest collects and then fails:

```
$ pytest test_live_agent_hitl.py test_callback_events_debug.py -q
FAILED test_live_agent_hitl.py::test_agent - Failed: async def functions are not natively supported.
FAILED test_callback_events_debug.py::test_event_consumer_basic - Failed: async def functions are not natively supported.
...
7 failed in 1.22s
```

(`pytest-asyncio` is installed, but `pytest.ini` sets no `asyncio_mode`, so
the plugin leaves the bare `async def` functions alone.)

---

## 4. Why the root, and when

Both files were added in **one** commit — `43a88e5`, *"feat: Implement
Human-in-the-Loop (HITL) console input and whiptail password workflows
(#10)"*, on **2026-10-05**.

The `tests/` directory was **already organised** by then: `dcb1e39`, on
**2026-09-11**, *"Add math calculation toolkit functionality, organize tests
in tests/ directory"*. So "there was no `tests/` folder yet" is not the
reason. They were simply written as scripts and left next to
`agent-torvalds.py`, which they import.

The file was touched once afterwards — `efa969a` (#74) — and the change was
the `sys.path` line, not a move.

---

## 5. What the naming costs

This is the part that matters, and it is not cosmetic.

### 5.1 A test file the CI gate cannot see

`pytest.ini` collects only the directories in `testpaths`. The repository
root is not among them, so **the two files are never run by the suite**:

```
$ pytest --collect-only -q | grep -E "test_live_agent_hitl|test_callback_events_debug"
(no output — not collected)
```

**This is not hypothetical.** PR #76 removed the unused `spinner=`
argument of `HumanLoopHandler`. `test_live_agent_hitl.py` passed that
argument, so the file broke:

```
TypeError: HumanLoopHandler.__init__() got an unexpected keyword argument 'spinner'
```

…and the CI gate reported **0 new failures**, because it never looked at
the file. The break was found by reading the file, not by the suite.

### 5.2 Seven confusing failures, if pytest is ever pointed at them

The moment anything collects the root — a change to `testpaths`, a
`pytest .` instead of `pytest`, a new test path added by hand — the two
files contribute **seven failures**, none of which says anything about the
code: all seven are *"async def functions are not natively supported"*.

---

## 6. What was done

| From | To |
|---|---|
| `test_callback_events_debug.py` | `scripts/debug_callback_events.py` |
| `test_live_agent_hitl.py` | `scripts/live_agent_hitl.py` |

The names no longer start with `test_`, so pytest's `python_files =
test_*.py` cannot match them — the same way `scripts/hitl_live_llm_test.py`
and `scripts/hitl_interactive_test.py` are already named.

Two things had to change with the move:

* **The `sys.path` line.** Both files put *their own directory* on the
  path. From `scripts/` that is the wrong directory, so both now put the
  **repository root** on it — the same fix `scripts/hitl_live_llm_test.py`
  already uses.
* **The `spinner=` argument** in `scripts/live_agent_hitl.py`, which PR #76
  broke. Fixed.

Both scripts were checked from their new location: the debug harness lists
its six scenarios with `--list`, and the live script imports cleanly.

### The rule

`tests/test_no_stray_test_files.py` is new, and it says one thing: **a test
file must be somewhere pytest collects, or under `investigate/`** — the
record of a piece of work, which is outside the suite on purpose.

It reads the `testpaths` out of `pytest.ini`, so it follows pytest rather
than repeating it, and a test asserts that the two agree.

The rule is tested against deliberate strays: a file in the root, a file in
an uncollected directory, a helper in the record (allowed), a test in a
collected directory (allowed), and the virtual environment (not walked).

---

## 7. What was verified

```
$ pytest tests/test_no_stray_test_files.py -q
9 passed in 0.39s

$ python scripts/ci_test_gate.py
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
fixed since the baseline        : 0
```

And the rule was checked against a real stray: putting a `test_*.py` back
into the root makes it fail, naming the file.

---

## 8. One thing left alone

`investigate/claude-contributor-purge/test_strip_claude_trailer.py` and
`investigate/whiptail/test_python_whiptail.py` are also named `test_*.py`
and are also outside `testpaths`. They are helper scripts of two
investigations — they define **no** pytest test functions at all — and they
belong to the record of that work. The rule exempts `investigate/`
explicitly, and says so in a comment, so the exemption is visible rather
than implied.
