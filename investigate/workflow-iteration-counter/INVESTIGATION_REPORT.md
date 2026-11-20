# Investigation Report: the iteration of the workflow never leaves zero

**Status:** root cause found, fix implemented, verified by a test that fails without it.
**Branch:** `fix/workflow-iteration-counter`
**Reported by:** the operator, on 2026-11-19 — *"please investigate 'Workflow Iteration:'
in the 'Workflow & Tool Progress' panel, it always remains 0"*

**Probe:** [`probe_workflow_iteration.py`](probe_workflow_iteration.py) — read-only.  It
renders the pane, reads the source of the repository, and runs the real agent against a
scripted model that lives in the probe.  It writes nothing and talks to no service.

---

## 1. The question

The progress pane of the multi-window console carries a row:

```
⚡ Workflow & Tool Progress
│ Workflow Iteration: [░░░░░░░░░░░░] 0/10 (0%)
```

The number in that row stayed at zero for every run of every operator.  The question is
not *"why does it look wrong"* — it is *"where is the number that should be there"*.

## 2. The measurement

The probe was run on the tree **before** the fix.  Its output, verbatim:

```
========================================================================
1. What the operator sees
========================================================================
  a fresh state carries: workflow_iteration=0, max_iterations=10
  the progress pane of a fresh state:
    │ Workflow Iteration: [░░░░░░░░░░░░] 0/10 (0%)             │
  the budget the agent is really run with: 500

========================================================================
2. The call graph
========================================================================
  who writes the attribute `workflow_iteration`:
    components/tui/state_bridge.py
  who calls `TuiState.update_workflow_iteration`:
    components/tui/state_bridge.py
    investigate/workflow-iteration-counter/probe_workflow_iteration.py
  who calls `TuiEventAdapter.on_workflow_iteration`:
    (nobody)
  the event types the TUI adapter registers with the consumer:
    register_callback is called 3 time(s) in components/tui/state_bridge.py

========================================================================
3. What the framework knows
========================================================================
  the agent asked the model 3 times
  request | num_iterations | max_iterations
      1    |        0      |       500
      2    |        1      |       500
      3    |        2      |       500

========================================================================
4. What the pane would show if the number were published
========================================================================
  after request 1:
    │ Workflow Iteration: [░░░░░░░░░░░░] 1/500 (0%)            │
  after request 2:
    │ Workflow Iteration: [░░░░░░░░░░░░] 2/500 (0%)            │
  after request 3:
    │ Workflow Iteration: [░░░░░░░░░░░░] 3/500 (0%)            │

The number is there.  Nothing publishes it.
```

Three numbers carry the measurement:

| | the number | where it came from |
|---|---|---|
| the pane showed | `0/10` | the initial value of the state, and the initial value of the budget |
| the run really had | 3 requests to the model | the script of the probe |
| the budget really was | 500 | `agent.run(max_iterations=500)` — `agent-torvalds-mw.py` |

The **denominator** was wrong as well: the state carried a budget of ten, and the agent
of the multi-window console is run with a budget of five hundred
(`MAX_ITERATIONS = config.get("llm.max_iterations", default=500)`).  Ten was never
measured by anything — it was the number in the constructor of the state.

## 3. The root cause

### 3.1 The number had no publisher

The state of the TUI carried the iteration:

```python
# components/tui/state_bridge.py
self.workflow_iteration: int = 0
```

and the only way to write it was `TuiState.update_workflow_iteration()`.  The only caller
of that method was `TuiEventAdapter.on_workflow_iteration()` — **and nothing called
that**.  The probe says it in one line: *who calls `TuiEventAdapter.on_workflow_iteration`:
(nobody)*.

The reason is that the hook was waiting for an event that does not exist.  The adapter
registers three callbacks with the event consumer — `ToolCall`, `ToolCallResult`,
`AgentStream` — and the vocabulary of the consumer carries no iteration event at all
(`AgentWorkflowStartEvent`, `AgentInput`, `AgentSetup`, `AgentOutput`, `AgentStream`,
`ToolCall`, `ToolCallResult`, `StopEvent`, and the two HITL events).  There is no
"iteration" event to listen for, so the hook could never fire.  It looked like wiring,
and it was a shape where wiring would go.

So the row of the pane was a number that nobody wrote, rendered on every frame.

### 3.2 The iteration itself was nowhere to be seen

The agent does know how many times it has asked the model — but the count was in the
store of the workflow, and nothing looked at it:

* `ctx.store["num_iterations"]` — the counter of the framework, incremented once per
  turn of the run (`llama_index/core/agent/workflow/base_agent.py`).
* `ctx.store["max_iterations"]` — the budget the run was started with.

Both are there, both are per-run, and both were invisible to the TUI.

### 3.3 A related finding: the turns that do not reach the budget check

The probe lists the returns of the override of the agent (`parse_agent_output`).  The
base implementation counts the iteration and stops the run when the budget is spent;
the override answers a question itself and returns without calling it:

```
  the returns of parse_agent_output():
    line  954  does NOT                     return AgentInput(
    line  828  counts and checks the budget return await super().parse_agent_output(ctx, ev)
    line  835  does NOT                     return await self._handle_silent_turn(ctx, ev)
    line  838  counts and checks the budget return await super().parse_agent_output(ctx, ev)
    line  847  counts and checks the budget return await super().parse_agent_output(ctx, ev)
    line  860  counts and checks the budget return await super().parse_agent_output(ctx, ev)
    line  827  does NOT                     return await self._stop_for_repetition(ctx, ev, repetition
```

A turn in which the model asks a question is therefore neither counted against the
budget nor checked against it.  The guard against asking the same question twice
(`_was_answered`) stops a *repetition*, not a *series*: a model that asks a different
question every turn is not stopped by `max_iterations`, and every question costs a
full model round-trip.

This is a **separate defect** — it changes when a run stops, not what the panel shows —
and it is **not fixed in this change**.  It is in section 7.

## 4. The fix

The number is counted where an iteration actually happens — in the agent, right before
the request goes out to the model — and it is handed to whoever is watching, in the
same shape as the measurement of the context that the telemetry panel already shows.

* **`components/hitl_agent.py`** — the agent carries an observer of the iteration
  (`iteration_observer`), and `take_step()` counts the iteration and tells the observer
  before the request goes out to the model.  The counter lives in the store of the
  workflow, and the store belongs to one run: the number starts at one with every run,
  and nobody has to reset it.  The budget that goes with it is the one the workflow was
  started with — the same number the workflow itself compares against.

* **`components/tui/state_bridge.py`** — the state holds the number and the budget.
  The budget it carried (ten) was never measured; it is now zero, which means *not
  known yet*, and the console tells the state the real budget.  A new request resets
  the iteration, because a new request is a new run.  The hook that nothing called
  (`on_workflow_iteration`) is gone: the number comes from the agent, and a hook that
  waits for an event that does not exist is what made the defect invisible.

* **`agent-torvalds-mw.py`** — the console installs the observer next to the observer
  of the context, and tells the state the budget of the run before the first request.

* **`components/tui/progress_view.py`** — the pane shows the budget it was given.  A
  budget that nobody gave is not shown as `1`: the row shows the number of the
  iteration alone, and no bar that would be full because of a budget of one.

## 5. Verification

The test `tests/test_tui_iteration_readout.py` drives the real agent against a
scripted model and checks the number that reaches the state and the pane.

Without the fix, **eleven of the sixteen tests fail**:

```
FAILED tests/test_tui_iteration_readout.py::TestTheObserver::test_the_observer_is_called_during_a_run - ValueError: "HITLFunctionAgent" object has no field "iteration_observer"
FAILED tests/test_tui_iteration_readout.py::TestTheObserver::test_the_number_counts_the_requests_to_the_model - ValueError: "HITLFunctionAgent" object has no field "iteration_observer"
FAILED tests/test_tui_iteration_readout.py::TestTheObserver::test_the_observer_is_told_the_budget_of_the_run - ValueError: "HITLFunctionAgent" object has no field "iteration_observer"
FAILED tests/test_tui_iteration_readout.py::TestTheObserver::test_the_number_starts_again_with_every_run - ValueError: "HITLFunctionAgent" object has no field "iteration_observer"
FAILED tests/test_tui_iteration_readout.py::TestTheObserver::test_a_failing_observer_does_not_take_the_run_down - ValueError: "HITLFunctionAgent" object has no field "iteration_observer"
FAILED tests/test_tui_iteration_readout.py::TestTheObserver::test_no_observer_is_no_problem - AttributeError: 'HITLFunctionAgent' object has no attribute 'iteration_observer'
FAILED tests/test_tui_iteration_readout.py::TestTheState::test_a_fresh_state_knows_no_budget - assert 10 == 0
FAILED tests/test_tui_iteration_readout.py::TestTheState::test_a_budget_of_zero_does_not_replace_a_known_budget - assert 0 == 500
FAILED tests/test_tui_iteration_readout.py::TestTheState::test_a_new_request_starts_the_iteration_again - assert 7 == 0
FAILED tests/test_tui_iteration_readout.py::TestTheState::test_a_negative_number_is_not_a_number - assert -5 == 0
FAILED tests/test_tui_iteration_readout.py::TestTheReadout::test_it_shows_the_iteration_of_the_run_that_is_running - ValueError: "HITLFunctionAgent" object has no field "iteration_observer"
11 failed, 4 passed, 28 warnings in 1.22s
```

With the fix: **16 passed**.

The probe, run on the fixed tree, shows the whole path:

```
========================================================================
4. The run, end to end
========================================================================
  the agent, the observer, the state of the TUI, and the pane:
    the state carries: workflow_iteration=3, max_iterations=500
  the progress pane after the run:
    │ Workflow Iteration: [░░░░░░░░░░░░] 3/500 (0%)            │
```

The gate of the repository is green: 40 known failures, 0 new, 0 fixed.

    .venv/bin/python scripts/ci_test_gate.py

## 6. What is *not* in this change, and why

* **The bar is coarse.**  The bar is twelve cells wide, and the budget of the run is
  five hundred: one cell is forty-two iterations, and a run that lasts ten iterations
  leaves the bar empty.  The number carries the information, and the bar is decoration
  at that budget.  Making the bar useful at a budget of five hundred means changing
  the design of the pane — the width of the bar, or the scale it is drawn on — and
  that is a change of the pane, not of the number.

* **The row does not fit in the sidebar.**  The row is forty-nine cells wide with a
  budget of five hundred, and the sidebar is thirty-five per cent of the body of the
  console: the row wraps onto two lines in a terminal of 120 columns, as it did
  before with a budget of ten.  This is how the pane was drawn before, and the change
  of the number does not make it worse by more than one cell.

* **The turn of the question is not counted against the budget** — see section 3.3.
  The count that is on the screen is the count of the requests to the model; the
  budget is the budget the workflow was started with.  They agree, except on the
  turns that the agent handles itself.  Changing what the budget bounds is a change of
  the behaviour of the agent, and it is not this change.

* **The classic console is untouched.**  It prints into the scrollback and draws no
  panes; the observer stays `None` there, and the agent does not care.

## 7. The recommendation to the operator

1. **Merge the change.**  The number of the iteration moves, the budget on the screen
   is the budget of the run, and a test pins both.  The cost of the change is three
   source files, one test file and this folder.

2. **Decide about the budget of the questions** (section 3.3).  A turn in which the
   model asks a question does not spend the budget of the run, so a model that asks a
   different question every turn is never stopped by `max_iterations` — and every
   question costs a full model round-trip, five minutes on the local model.  Two ways
   to close it: count the turn of the question against the budget as well, or give the
   agent a separate budget for the questions.  Both change when a run stops, so the
   choice is the operator's.  It is not fixed here, and nothing in this change makes
   it worse.

3. **Decide about the bar.**  At a budget of five hundred the bar of twelve cells
   stays empty for the whole of a normal run.  It can be widened, dropped, or drawn
   on a scale of its own — the number is what carries the information, and the bar can
   be left for a change of the design of the pane.
