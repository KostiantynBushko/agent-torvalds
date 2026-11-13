# Implementation Report: the agent must never answer in silence

**Status:** implemented — the change that follows the
[`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md) is written, tested
and green.  The proposal it implements is in
[`PROPOSAL.md`](PROPOSAL.md).

## What was changed

Three changes, in the order the operator feels them.

### (a) The answer on the screen is never empty

The answer of the model used to reach the console through `str(result)`,
which returns the **text** of the answer and nothing else.  The
`thinking` block of a reasoning model was dropped there, and an answer
that carried nothing but a thinking became an empty string — the console
printed nothing at all, and the operator could not tell that from a run
that had never started.

`components/chat_message.py` now owns the answer the operator reads:

| | before | after |
|---|---|---|
| the text of the model | the answer | the answer |
| a thinking and no text | `""` | the fact that there was no answer, and the thinking under it |
| nothing at all | `""` | the fact that there was no answer |

The function is `to_answer_string()`.  It **never returns an empty
string**: an answer that cannot be rendered is still an answer, and the
operator is told that the model ended the turn without one.

```python
from components.chat_message import NO_ANSWER, to_answer_string

answer = to_answer_string(result)
```

The three console paths use it — `agent-torvalds.py`,
`agent-torvalds-mw.py` and `agent-torvalds-cpp.py`.  The TUI path needs
no change: it calls the same `prompt_handler`, so it receives the
rendered answer, and its own `*No output returned from agent.*` guard
stays as the backstop it always was.

### (b) A turn that says nothing does not end the run

`HITLFunctionAgent.parse_agent_output()` ended the workflow on the first
turn without a tool call, whatever the model said in it — including a
sentence that promises work instead of doing it, and including nothing
at all.

The agent now recognises the silent turn — no text, no tool call — and
gives the model **one more turn**:

* the empty turn of the model stays in the scratchpad, and a note that
  says what went wrong follows it, so the model can see what it did;
* a model that has something to say about that says it, and the run
  carries on;
* a model that says nothing a second time ends the run — and the answer
  says plainly that the model ended the turn without an answer.

One turn, not two: a model that says nothing once has usually sampled
nothing once, and every empty turn costs a full round-trip.

### (c) The window the agent sends is not the advertised maximum

The agent used to ask the server for the **advertised maximum** of the
model when neither `/api/ps` nor the Modelfile answered — a number the
server never used, and a number that pushes the model off the GPU
(measured: 3.09 GB of VRAM instead of 6.64 GB).

Now:

* the advertised maximum is **not sent**.  The window is *unknown*, the
  log says so, and the configured window — the environment variable, the
  configuration file, or the `default` of the caller — is used when
  there is one;
* the window that is sent is **sized to the prompt** that is about to
  go out, with room above it for the answer, and it is **never lowered**
  — a window that changes in both directions makes the server give the
  cache back and take it again with every request.

```python
# components/ollama_config.py
window_for_prompt(prompt_tokens)   # the window a prompt of that size needs
fit_context_window(llm, tokens)    # raise the window of the LLM to hold it
```

## What was verified

| | where | what it pins |
|---|---|---|
| the silent turn | `tests/test_silent_turn.py` | the model is asked again; the note reaches it; a second silence ends the run; a tool call is not a silence |
| the answer | `tests/test_silent_turn.py` | the answer is never empty; the thinking is shown; the text wins over the thinking |
| the console | `tests/test_silent_turn.py` | a silent answer produces a line on the screen, not an empty box |
| the window | `tests/test_ollama_context_window.py` | the advertised maximum is not sent; the configured default is used; the window is raised and never lowered |

```
.venv/bin/pytest tests/test_silent_turn.py tests/test_ollama_context_window.py -v
```

The gate of the repository stays green — 40 known failures, **0 new**,
**0 fixed**:

```
python scripts/ci_test_gate.py
```

## What is *not* in this change

* **The model build that served the session is not explained.**  It is
  gone from the machine, and the evidence that is left does not separate
  the remaining candidates.  What *is* answered is the part the
  operator can act on: whatever the model says, the agent is not
  silent about it.
* **The memory buffer of the branch is not touched.**  It was measured
  (§2.1 of the investigation) and it is not the cause.
* **The tools, the model and the prompt are not touched.**  The 37 tools
  of the operator were the right ones for the task.
