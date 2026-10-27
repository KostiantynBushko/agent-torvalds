# Proposal: fix the agent loop caused by the context guard

**Branch:** `fix/context-guard-agent-loop` (in `self-development/`)
**Investigation:** [`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md)
**Reproduction:** [`repro_loop.py`](repro_loop.py)

---

## The problem in one paragraph

`components/context_guard.py` was introduced to stop the model template from
rejecting a prompt without a user request ("No user query found in messages.").
It does that job — but it fills the prompt window with the **oldest** turns
instead of the **newest** ones, and emits them in reverse order. The model
therefore never sees the result of its own last action, the window it is shown
stops changing, and — because the agent decodes greedily (`temperature=0.0`) —
it keeps asking for the same thing. On the local model (8192-token window, 27
tool schemas) the run burned four hours asking whether `sshpass` was installed.

## The fix in one paragraph

The window is now filled **newest first** and assembled in **chronological
order**, the newest turn is never dropped (it is shortened instead), and the
chat history that precedes the request is kept instead of being thrown away.
On top of that the agent **stops the run** when the same tool call returns the
same result three times in a row, so that a model which is stuck cannot eat
the whole iteration budget.

---

## What changes

### 1. `components/context_guard.py`

| change | why |
|---|---|
| `_fill_groups()` fills the window **newest first** | the turn the model has just produced carries the result of its last action. The old code kept the oldest turns and dropped the newest — the model was blind. |
| the window is assembled in **chronological order** | the old code emitted the tail reversed (`for group in reversed(selected)`). |
| the **newest turn is mandatory** | it is shortened when it does not fit, but never dropped. A model that cannot see the result of its last action repeats that action. |
| the **chat history before the request** is part of the window | the old code dropped every message between the system prompt and the request — the agent forgot the session on every step. The scratchpad is filled first (it is newer and belongs to the task), the history takes what is left. |
| `truncate_message()` no longer **destroys a tool call** | it used to rebuild a tool-call message from its content, which turned the call into a piece of text. |
| `truncate_message()` guarantees the **final** size | tokenisation is not additive — appending the truncation marker used to push the message over its budget. |
| the truncation marker is **adaptive** | a budget of a few tokens cannot afford the long marker. |
| `_enforce_budget()` drops **whole turns**, never single messages | a tool result must never lose the call that produced it. |
| `_fit_core()` shortens the **system prompt** as well | the old code only shortened the request; a large system prompt could still push the window over the budget. |

### 2. `components/hitl_agent.py`

| change | why |
|---|---|
| the guard stands down below `MIN_PROMPT_BUDGET` (256 tokens) | below that the window cannot hold the request *and* a usable turn, and cutting into the request would bring back the very failure the guard exists to prevent. |
| the **frozen prompt** is gone | the window that is written back into the scratchpad now always ends with the newest turn, so the prompt changes with every iteration. |
| **repetition detection** | every tool result is fingerprinted (tool name + arguments + result). The same fingerprint three times in a row ends the run with a report. The result is part of the fingerprint on purpose: the same call that returns something *different* is polling, not looping. |

### 3. Tests

* `tests/test_context_guard.py` — 6 new unit tests (the order of the window, the
  newest turn, the chat history, the tool call that survives a truncation).
* `tests/test_context_guard_agent.py` — 3 new integration tests (the window ends
  with the newest turn, the run stops on a repetition, a repetition with a
  changing result is not a loop).

---

## Verification

```console
$ .venv/bin/python -m pytest tests/test_context_guard.py tests/test_context_guard_agent.py -q
33 passed

$ .venv/bin/python investigate/agent-loop-context-guard/repro_loop.py
RESULT: PASS — the prompt changes on every iteration (no fixed point).
SCENARIO B: the model is stuck and repeats the same call
RESULT: PASS — the agent noticed the repetition and stopped the run instead of
          repeating itself for the whole iteration budget.
```

The full suite, base commit `ce6fef3` against this branch:

| | failed | passed |
|---|---|---|
| base | 39 | 2365 |
| branch | 39 | 2374 |

The **failure sets are identical** (`diff` of the two lists is empty): the branch
adds 9 passing tests and breaks nothing. The 39 failures are pre-existing and
unrelated (git toolkit, HITL runtime toggle, math toolkit, project manager,
whiptail, apt toolkit).

A randomised check over 2000 conversations (varying turn counts, tool result
sizes, history lengths and budgets from 10 to 900 tokens) confirms that the
window always contains the user request, always ends with the newest turn, and
never exceeds the budget by more than **one token** — the imprecision of
"join the messages and tokenize" counting.

---

## What is *not* in this change, and why

* **The chat memory is not clamped to the prompt budget.** The scratchpad — the
  task at hand — is worth more than the session history, and the guard now
  fills the budget with the scratchpad first. Clamping the memory would trade
  the current task for old history.
* **The tool schemas are not shrunk.** 27 tools cost 3211 of the 8192 tokens.
  That is a property of the tool set, not of the guard.

## Recommendation to the operator (not a code change)

The arithmetic of the failing run is tight:

```
8192  context window
-1638 reserve for the answer
-3211 tool schemas (27 tools)
=3343 tokens for the whole conversation
```

Two things give the agent more room on a local model:

1. **Raise the server's context window** — `OLLAMA_CONTEXT_LENGTH=32768 ollama serve`
   (or `PARAMETER num_ctx 32768` in the Modelfile). The guard picks the new
   value up automatically: `components/ollama_config.py` resolves the real
   window from `/api/ps` and from the Modelfile.
2. **Use the on-demand tool retriever** (the default) instead of `--select`
   with 27 tools. It loads `top_k = 8` tools per query, so the schemas cost
   roughly 950 tokens instead of 3211 — and the session history fits into the
   prompt again.

Neither is needed for the fix, but together they are the difference between an
agent that works in a cramped window and one that fights for every token.

---

## Next step

The work is on the branch `fix/context-guard-agent-loop` in the
`self-development/` clone. It is **not committed** — per Rule 4 of
`SELF_DEVELOPMENT_RULES.md` a commit needs the operator's explicit approval.
