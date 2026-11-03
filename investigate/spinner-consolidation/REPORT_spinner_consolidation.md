# The spinner — two implementations, one of them dead

**Date:** 2026-10-29
**Operator's request:** *"please make investigate of of the spinner feature, we
haev components/spinner_controller.py and spinner_manager.py which one is used?
We either have to merge them into a single feature or remove one of them if
they are identical. The solution must be placed in componnents folder."*

---

## 1. The answer in one line

**`components/spinner_controller.py` is the one that is used.**
`spinner_manager.py` has **never** been imported by anything — not by the
orchestrators, not by a component, not by a toolkit, not by a test.

They are **not** identical, so the operator's rule says *merge*. They are
merged into `components/spinner_controller.py`, and `spinner_manager.py` is
deleted.

---

## 2. The evidence

### `spinner_manager.py` — no importers

```
$ grep -rn "spinner_manager" --include="*.py" . | grep -v investigate/
./spinner_manager.py:9:    agent-torvalds.py  ──imports──>  spinner_manager.py  <──imports──  toolkits/apt-toolkit/
./spinner_manager.py:20:    from spinner_manager import get_spinner
```

Two hits, and **both are inside the file's own docstring**. There is no
third kind of hit: it is not in `components/__init__.py`, no test imports
it, no script imports it, and no `importlib` call names it.

### `components/spinner_controller.py` — used everywhere

| Where | How |
|---|---|
| `agent-torvalds.py` | `SpinnerController(console)` at line 536, handed to the `EventConsumer` |
| `agent-torvalds-mw.py` | the same, plus a second one for the TUI's silent console |
| `components/__init__.py` | exported as part of the package |
| `components/event_consumer.py` | the `spinner_controller` parameter |
| `components/signal_handler.py` | the `spinner` parameter |
| `components/human_loop_handler.py` | the `spinner` parameter — **see §6** |
| 10 test files | `tests/test_hitl_*.py`, `tests/test_events_manual.py`, … |
| 2 scripts | `scripts/hitl_live_llm_test.py`, `test_callback_events_debug.py` |

---

## 3. How it happened

Both files were created in the **same commit**.

```
b4c403c  refactor: extract SpinnerController to components and enhance APT toolkit
         with whiptail support
```

Its own message says what it did:

> - Extracted SpinnerController class into `components/spinner_controller.py`
> - **Added spinner_manager.py as shared spinner singleton with callback hooks**

So the extraction produced `components/spinner_controller.py`, and *alongside
it* a second implementation was written — a global singleton with callback
hooks — for a reason the message gives: *"Spinner can be paused during
interactive dialogs (whiptail)"*, which needed to be reachable from the
toolkits.

**That reason was never realised.** No toolkit references a spinner at all:

```
$ grep -rln "spinner" toolkits/ --include="*.py"
(no output)
```

The `spinner_manager.py` file was touched exactly once more, in `ce75ade`
("refactor: make the apt toolkit a module"), and that change was **one line
of its docstring** — the architecture diagram, from
`agent_apt_toolkit.py` to `toolkits/apt-toolkit/`:

```
-    agent-torvalds.py  ──imports──>  spinner_manager.py  <──imports──  agent_apt_toolkit.py
+    agent-torvalds.py  ──imports──>  spinner_manager.py  <──imports──  toolkits/apt-toolkit/
```

The diagram was kept current. The file it describes was not.

Meanwhile `components/spinner_controller.py` was **improved** in `c8d6927`
("feat: add real-time event streaming with state management and thread-safe
spinner"), which is where its lock and its error handling came from.

So the one that was used is the one that got better, and the one that was
not used is the one that sat still.

---

## 4. They are not identical

This is the whole reason the operator's rule says *merge* rather than
*remove*.

| | `spinner_manager.py` (root, 252 lines) | `components/spinner_controller.py` (139 lines) |
|---|---|---|
| **Used** | **no** | **yes** |
| Global singleton | `get_spinner()`, `reset_spinner()` | — |
| Module-level helpers | `pause_spinner()`, `resume_spinner()`, `spinner_pause_context()` | — |
| Lifecycle callbacks | `on_start`, `on_stop`, `on_pause`, `on_resume` | — |
| Global console | `get_console()` | — |
| Thread safety | — | `threading.Lock` around every transition |
| Error handling | none | `try`/`except` around start, stop, pause and resume |
| Cleanup on stop | — | `time.sleep(0.01)` for the render thread |
| Console | optional, falls back to the global one | required |
| Logging | `logger.info` on each transition | — |

Neither is a superset of the other. The live one is **better**; the dead
one has **API**.

---

## 5. What was merged, and what was not, and why

### Merged: the lifecycle callbacks

`on_start`, `on_stop`, `on_pause` and `on_resume` moved into
`components/spinner_controller.py`, together with the `_fire_callbacks()`
helper that calls each listener in its own guard, so a listener that raises
cannot take the spinner down.

This is not a relocation of dead code — it reconciles the code with a
contract the documentation had **already** written. `components/README.md`
said of `spinner_controller.py`:

> **Features:**
> - Thread-safe spinner with pause/resume functionality
> - Integration with rich console for styled output
> - **Callback hooks for lifecycle events**

That last bullet was false: the hooks were in the other file. After the
merge it is true.

### Not merged: the global singleton, the helpers, the global console

`get_spinner()`, `reset_spinner()`, `pause_spinner()`,
`resume_spinner()`, `spinner_pause_context()` and `get_console()` are
**not** carried over, for four reasons.

1. **Nothing calls them.** Every one of them was checked across the whole
   repository, excluding `.venv`: zero hits.

2. **The problem they solved does not exist.** The singleton existed so
   that a deep caller could reach the spinner without a reference to it.
   The one component that needs the spinner — the one that prompts the
   human — **already has it**, passed in explicitly.

3. **A global is the opposite of how this codebase passes a dependency.**
   The spinner is handed to `EventConsumer`, `SignalHandler` and
   `HumanLoopHandler` as a constructor argument, and ten test files build
   their own instance. A module-level singleton cannot be injected, so it
   cannot be tested in isolation.

4. **The live path already does the pausing** — see §6.

---

## 6. Two things the investigation turned up that were not in the question

### 6.1 The pause and resume work — and it works

The reason `spinner_manager.py` existed was to let the spinner be paused
during an interactive dialog. That capability **is live**, in
`components/event_consumer.py`, which is documented as *"the single place
where the user is prompted"*:

| Where | What |
|---|---|
| `_on_tool_call` / `_on_tool_call_result` | pauses around the interactive tools — the password prompts, the whiptail dialogs, the long-running installs |
| `_on_input_required` | pauses around a HITL question, resumes in a `finally` |
| `_on_agent_question` | pauses around a HITL question, resumes in a `finally` |

So the feature the orphan was built for is already delivered, by the other
implementation, through the explicit dependency.

### 6.2 A spinner was injected into a component that never used it

`components/human_loop_handler.py` took a `spinner` parameter, documented
as *"SpinnerController to pause/resume during prompts"*, and stored it:

```python
self.spinner = spinner
```

…and never touched it again. `self.spinner` appears **once** in the file —
the assignment. The `EventConsumer` does the pausing, because the
`EventConsumer` is where the prompt happens.

That is the same failure mode as the orphan: a spinner wired into a place
that does not use it, invisible because nothing reads it. It has been
removed — the parameter, the attribute, the import, and the five call
sites that passed it (`agent-torvalds.py`, `agent-torvalds-mw.py` twice,
`scripts/hitl_live_llm_test.py`, `tests/test_hitl_integration.py`). The
change is behaviour-neutral: the value was stored and never read.

### 6.3 The spinner had no tests at all

There was no test file for either implementation. The class was covered
only indirectly, by the tests of the components that use it — and those
pass a `MagicMock` or a `SpinnerController` that is never started.

`tests/test_spinner_controller.py` now covers the class on its own: the
state transitions, the idempotence, the pause context (including the
exception path), the console that refuses the spinner, the callbacks, and
the lock.

---

## 7. The documentation that named the orphan

| Where | What it said |
|---|---|
| `README.md` §12 | a whole section, *"Spinner Manager (`spinner_manager.py`)"*, listing the singleton and the helpers as features of the project |
| `README.md`, the project tree | `spinner_manager.py  # Global console spinner management` |
| `wiki/Architecture.md`, the tree | the same line |
| `wiki/Architecture.md`, the prose | *"`spinner_manager.py` manages the console spinner"* |
| `components/README.md` | claimed `spinner_controller.py` had callback hooks — **false** until this change |

All four are corrected. The wiki is its own repository
(`agent-torvalds.wiki.git`), so it was a separate commit there.

---

## 8. What was done

| | |
|---|---|
| `components/spinner_controller.py` | gained the lifecycle callbacks and the callback guard |
| `spinner_manager.py` | **deleted** from the project root |
| `components/human_loop_handler.py` | the unused `spinner` parameter removed |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | the two `spinner=` arguments removed |
| `scripts/hitl_live_llm_test.py`, `tests/test_hitl_integration.py` | the same |
| `tests/test_spinner_controller.py` | **new** — 21 tests |
| `README.md`, `components/README.md` | corrected |
| `wiki/Architecture.md` | corrected, in the wiki repository |

**There is one spinner feature now, and it is in `components/`.**

---

## 9. How it was verified

```
$ python -m pytest tests/test_spinner_controller.py -q
21 passed in 0.85s

$ python scripts/ci_test_gate.py
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
fixed since the baseline        : 0
No new failures. The build may proceed.
```

The 21 new tests pass, and the gate reports **no new failure** — the same
40 known failures as before the change, and nothing else.

---

## 10. A note on the name

The operator's rule was *"merge them into a single feature **or** remove
one of them **if they are identical**"*. They were not identical, so the
merge was the rule's answer, and the merge is what happened. The dead
file's API was not carried over wholesale — carrying it over would have
moved unused code rather than merged anything — and §5 says exactly which
part came with, and why the rest stayed behind.

The survivor kept its name, `SpinnerController`. It is the class the
orchestrators, the components and the tests have always used, and
renaming it would have touched every one of them for no gain.
