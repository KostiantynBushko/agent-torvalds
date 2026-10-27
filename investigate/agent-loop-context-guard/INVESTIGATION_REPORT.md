# Investigation Report: the agent falls into a loop after the context guard

**Status:** root cause found, fix implemented, verified against a reproduction of the
failing run.
**Branch:** `fix/context-guard-agent-loop`
**Reported symptom:** `/home/kbush/torvald-log/agent-in-loop.md`
**Model:** `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (local, Ollama)

---

## 1. The symptom

The operator started the agent with 27 tools and asked it to deploy a project on a
remote host. The agent read `DEPLOYMENT.md`, checked whether `sshpass` was
installed — and then asked the same question again, and again, and again:

```
11:21:00  read_file called with path: self-development/DEPLOYMENT.md
11:21:00  Context guard: trimmed the prompt from 16 to 4 messages (head 2 / tail 2, ~3343 tokens, budget 3343)
11:30:30  POST http://localhost:11434/api/chat
11:35:22  check_command_exists called with command: sshpass
11:35:23  Context guard: trimmed the prompt from 18 to 4 messages (head 2 / tail 2, ~3343 tokens, budget 3343)
11:40:14  check_command_exists called with command: sshpass
11:40:14  Context guard: trimmed the prompt from 18 to 4 messages (head 2 / tail 2, ~3343 tokens, budget 3343)
11:45:16  check_command_exists called with command: sshpass
          ... the same two lines, every five minutes, for hours ...
```

`MAX_ITERATIONS` is 50 by default (`TORVALDS_MAX_ITERATIONS`), and every iteration
costs a full model round-trip — five minutes on this model. The run was therefore
going to burn four hours before it stopped on its own.

The operator's observation is exact: the loop started **after**
`components/context_guard.py` was introduced, and it is only visible **on the local
model**.

---

## 2. Root cause

Three defects in the context guard combine into the loop. All three are in the
*selection* of the prompt — the part that decides **which turns are sent**.

### 2.1 The arithmetic of the failing run (it matches the log exactly)

| quantity | value | where it comes from |
|---|---|---|
| context window | 8192 | `PARAMETER num_ctx 8192` in the model's Modelfile |
| reserve for the answer | 1638 | `context_budget()` → 20 % of 8192 |
| prompt budget | 6554 | 8192 − 1638 |
| tool schemas (27 tools) | 3211 | measured, see below |
| **budget for the conversation** | **3343** | 6554 − 3211 — *the number in the log* |
| chat memory limit | 5000 | the operator's `chat_token_limit` |
| chat history queue | 3500 | 5000 × `chat_history_token_ratio` (0.7) |

The tool schema cost is not a guess — it is what the 27 tools the operator
selected actually cost:

```console
$ .venv/bin/python - <<'PY'
from agent_tool_selection import _discover_tools, group_tools_by_category
from components.context_guard import get_tokenizer, context_budget
groups = group_tools_by_category(_discover_tools())
tools = [t for c in ("System / Package Management", "Operating System", "System")
           for t in groups[c]]                       # the 27 tools of the run
blob = json.dumps([t.metadata.to_openai_tool(skip_length_check=True) for t in tools])
print("tool schema tokens:", len(get_tokenizer()(blob)))     # 3211
print("budget:", context_budget(8192) - 3211)                # 3343
PY
tool schema tokens: 3211
budget: 3343
```

**3343 is exactly the budget printed in the failing log.** The run is therefore
fully explained by the code, not by a coincidence.

### 2.2 Defect D1 — the guard keeps the **oldest** turns instead of the newest

`_select_window()` grouped the conversation and then filled the window like this:

```python
    # Fill with the most recent turns, newest first.
    selected = []
    for group in groups:              # <-- groups are in CHRONOLOGICAL order
        if used + group_tokens <= budget_tokens:
            selected.append(group)
            used += group_tokens
            continue
        ...
        break                         # <-- stops at the first group that does not fit
```

The comment says *newest first*, the code does the opposite. The loop walks the
groups from the **oldest** to the newest and stops at the first one that does not
fit — so the **oldest** turns survive and the **newest** ones, the ones the model
has just produced, are thrown away.

The window is then assembled with `for group in reversed(selected)`, so the tail is
emitted in **reverse chronological order** as well (defect D2).

The practical consequence is the heart of the bug:

* the model never sees the result of its own last action (that result is in the
  newest turn, which was dropped),
* so it re-derives the same plan from the same old turn,
* and the window it is shown is **the same on every iteration**.

Before / after, same input, same budget:

```
BEFORE (master)                      AFTER (this branch)
system    You are Torvalds.          system    You are Torvalds.
user      merge the files            user      merge the files
assistant CALL read_xlsx_file        assistant thinking      <- newest
tool      payload payload payload    assistant CALL read_xlsx_file
assistant thinking                   tool      payload payload payload
assistant CALL read_xlsx_file        assistant thinking
tool      payload payload payload
assistant thinking
```

### 2.3 Defect D3 — the chat history before the request was thrown away

`core_items` was `[system prompt, request]` and `tail_start` was the index *after*
the request. Everything between the system prompt and the request — the chat
history of the session — was in neither, so it was dropped on **every** step. The
operator's session had 13 memory messages; the prompt kept 2.

The agent therefore started every step with nothing but the current request.

### 2.4 Why the loop is infinite: `temperature=0.0`

`agent-torvalds.py` configures the model with

```python
    llm = Ollama(
        model=MODEL,
        ...
        temperature=0.0,
    )
```

Greedy decoding means **the same prompt always produces the same answer**. Once
the guard had frozen the prompt, the model kept asking for `sshpass` — with the
same arguments, getting the same result, and being shown the same prompt again.

### 2.5 Why it only happens on the local model

Two conditions have to hold, and only the local model has both:

1. **The guard has to fire.** A cloud model with a 200 000-token window never
   exceeds the budget, so the guard never trims and the prompt keeps growing — the
   prompt changes, the answer changes, the agent moves on. The local model runs
   with `num_ctx 8192`, and 27 tool schemas (3211 tokens) plus the chat memory
   (3500 tokens) blow through the 6554-token budget on the very first step, so
   the guard trims on **every** step.
2. **The answer has to be deterministic.** `temperature=0.0` makes it so.

The `--select` path is what makes condition 1 hold. The default *on-demand tool
retrieval* loads only `top_k = 8` tools per query, and the schemas then cost
roughly 950 tokens instead of 3211 — the budget is then large enough for the
session to fit, and the guard does not fire.

---

## 3. The reproduction

`investigate/agent-loop-context-guard/repro_loop.py` drives the **real**
`HITLFunctionAgent` workflow with

* the **real** 27 tools of the failing run,
* the **real** context window (8192) and chat memory limit (5000),
* a fake LLM that decodes greedily, exactly like the configured model.

It reproduces the failing run's numbers **exactly**:

```
Context guard: trimmed the prompt from 16 to 4 messages (head 2 / tail 2, ~3343 tokens, budget 3343)
check_command_exists called with command: sshpass
Context guard: trimmed the prompt from 18 to 4 messages (head 2 / tail 2, ~3343 tokens, budget 3343)
check_command_exists called with command: sshpass
...
```

and it shows the mechanism — the prompt is **byte-identical** from the second
iteration onwards:

```
  prompt  0 == prompt  1: False
  prompt  1 == prompt  2: True
  prompt  2 == prompt  3: True
  ...
```

The script has two scenarios:

* **A — the prompt freezes** (the defect). It asserts that the prompt changes on
  every iteration.
* **B — the model is stuck** (the model repeats the same call whatever the
  prompt says). It asserts that the agent stops instead of repeating itself for
  the whole iteration budget.

---

## 4. The fix

### 4.1 `components/context_guard.py` — the window keeps the newest turns

* The groups are now filled **newest first** (`_fill_groups()`), so the turn the
  model has just produced — the one that carries the result of its last action —
  always survives. The oldest turns are the ones that are dropped.
* The window is assembled in **chronological order**. The reversed order of the
  tail is gone.
* The **newest group is mandatory**: it is truncated when it does not fit, but it
  is never dropped. A model that cannot see the result of its last action is a
  model that repeats its last action.
* The **chat history that precedes the request** is now part of the window
  (`_select_window()` splits the conversation into *history* and *tail*). It is
  filled after the scratchpad, because the scratchpad is newer and belongs to
  the task at hand.
* `truncate_message()` no longer turns an assistant turn that carries a tool
  call into a piece of text. It used to rebuild the message from its content,
  which silently destroyed the tool call.
* `_enforce_budget()` is the safety net: whole turns are dropped, never single
  messages, so a tool result never loses the call that produced it.

### 4.2 `components/hitl_agent.py` — a loop is broken, not waited out

* The **frozen prompt** is gone: the window that is written back into the
  scratchpad always ends with the newest turn, so the prompt changes with every
  iteration.
* The guard stands down when the tool schemas leave less than
  `MIN_PROMPT_BUDGET` (256) tokens for the conversation. Below that the window
  could not hold the request *and* a usable turn, and cutting into the request
  would bring back the "No user query found in messages." failure.
* **Repetition detection.** The result of every tool call is fingerprinted
  (tool name + arguments + result). When the same fingerprint comes back
  `REPEAT_CALL_THRESHOLD` (3) times in a row, the run is **stopped** with a
  report:

  > [Stopped] The agent called `read_xlsx_file` with the same arguments 3 times
  > in a row and got the same result every time. Repeating the call cannot make
  > progress, so the run was stopped.

  The result is part of the fingerprint on purpose: the same call with the same
  arguments that returns something *different* is polling, not looping, and the
  run continues.

### 4.3 What was deliberately *not* changed

* **The chat memory is not clamped to the prompt budget.** The scratchpad (the
  task at hand) is worth more than the session history, and the guard now fills
  the budget with the scratchpad first and the history with what is left. The
  real remedy for the remaining pressure is operational — see below.
* **The tool schemas are not shrunk.** 27 tools cost 3211 of the 8192 tokens.
  That is a property of the tool set, not of the guard.

---

## 5. Verification

### 5.1 The reproduction

```console
$ .venv/bin/python investigate/agent-loop-context-guard/repro_loop.py
...
RESULT: PASS — the prompt changes on every iteration (no fixed point).

SCENARIO B: the model is stuck and repeats the same call
the model was called 4 times
RESULT: PASS — the agent noticed the repetition and stopped the run instead of
          repeating itself for the whole iteration budget.
```

Before the fix the same script reported:

```
  prompt  1 == prompt  2: True
  prompt  2 == prompt  3: True
  ...
RESULT: FAIL — from iteration 2 onwards the prompt is IDENTICAL on every iteration.
```

### 5.2 Tests

| file | what it covers |
|---|---|
| `tests/test_context_guard.py` | 27 unit tests — the order of the window, the newest turn, the chat history, the tool call that survives a truncation |
| `tests/test_context_guard_agent.py` | 6 integration tests — the window ends with the newest turn, the run stops on a repetition, a repetition with a changing result is not a loop |

```
33 passed
```

### 5.3 No regressions

The full suite was run on the branch and on a clean worktree at the base commit
(`ce6fef3`):

| | failed | passed | skipped | error |
|---|---|---|---|---|
| base (`ce6fef3`) | 39 | 2365 | 9 | 1 |
| branch | 39 | 2374 | 9 | 1 |

The **failure sets are identical** — the `diff` of the two lists of failed test
ids is empty. The branch adds 9 passing tests and breaks nothing. The 39
failures are pre-existing and unrelated (git toolkit, HITL runtime toggle, math
toolkit, project manager, whiptail, apt toolkit).

### 5.4 A randomised check of the window

2000 random conversations — varying turn counts, tool result sizes, history
lengths and budgets from 10 to 900 tokens — confirm that the window

* always contains the user request,
* always ends with the newest turn (the tool result of the last action),
* never exceeds the budget by more than **one token** (the imprecision of
  "join the messages and tokenize" counting).

---

## 6. Operational recommendations

The guard now behaves correctly, but the arithmetic of the failing run is worth
looking at, because it is tight:

```
8192  context window
-1638 reserve for the answer
-3211 tool schemas (27 tools)
=3343 tokens for the whole conversation
```

Two things give the agent more room, and both are worth doing on a local model:

1. **Raise the server's context window.** `OLLAMA_CONTEXT_LENGTH=32768 ollama serve`
   (or `PARAMETER num_ctx 32768` in the Modelfile) quadruples the room. The
   guard picks the new value up automatically — `components/ollama_config.py`
   resolves the real window from `/api/ps` and from the Modelfile.
2. **Use the on-demand tool retriever** (the default) instead of `--select` with
   27 tools. It loads `top_k = 8` tools per query, so the schemas cost roughly
   950 tokens instead of 3211, and the session history fits into the prompt
   again.

Neither is required for the fix — the agent no longer loops either way — but they
are the difference between an agent that works in a cramped window and one that
has to fight for every token.

---

## 7. Files

| file | purpose |
|---|---|
| `components/context_guard.py` | the guard — the window is built newest-first and in chronological order, the chat history is kept, the tool call survives a truncation |
| `components/hitl_agent.py` | the guard is applied with a budget floor; a repeated tool call stops the run |
| `tests/test_context_guard.py` | unit tests (new cases) |
| `tests/test_context_guard_agent.py` | integration tests (new cases) |
| `investigate/agent-loop-context-guard/repro_loop.py` | the reproduction, with the real tools and the real budget |
| `investigate/agent-loop-context-guard/INVESTIGATION_REPORT.md` | this report |
