# Investigation Report: Why the agent said nothing at all after it had done the work

The operator ran the agent on 2026-11-13, between 18:22 and 18:38, on the
branch `fix/tui-session-selection-background`, and kept the log
(`~/torvald-log/agent-torvalds-misbehavior.md`).  Three requests went in.
The first one worked for three minutes — twenty-three model calls,
thirty-six tool calls, a project scaffolded on disk — and the agent
answered **nothing**.  The second request answered **nothing** as well.
The third one answered with a promise: *"Let me complete the
implementation first, then update the README to document it
accurately."* — and did nothing either.

The operator's words: *"the agent misbehaviour"*.

**Probe:** [`probe_empty_answer.py`](probe_empty_answer.py) — read-only,
reads the session of the run from the chat store of PostgreSQL and shows
what the console path puts on the screen for each answer.
Supporting probes: [`probe_trimmed_prompt.py`](probe_trimmed_prompt.py) —
the memory buffer of the branch, measured against the one of LlamaIndex;
[`probe_replay_failing_turn.py`](probe_replay_failing_turn.py) — the two
turns of the run, replayed against the model server.

## 1. The question

Why did the agent finish a request of three minutes with **no answer at
all** — no text, no error, no explanation — and why did it accept a
promise as the answer of the third request?

## 2. The measurement

The session of the run is still in the chat store of PostgreSQL, under the
key `chat-custom-698f061f-df3c-4454-8b85-3b2794f430c2-9d39436d`
(`chat_sessions` / `chatstore`, 70 messages).  The probe reads it and
prints, for every turn the agent ended a run on, what the console path
prints:

```
=== message 61: the answer the run ended on ===
    thinking        : '...Let me fix the Kconfig: remove the VIEWPRO_UART_PORT_NUM_OTHER.'
    text            : ''
    tool calls      : []
    str(AgentOutput): ''
    the operator sees : NOTHING AT ALL

=== message 67: the answer the run ended on ===
    thinking        : 'Let me fix the Kconfig UART port config (remove the awkward duplicate) and then write the source files.'
    text            : ''
    tool calls      : []
    str(AgentOutput): ''
    the operator sees : NOTHING AT ALL

=== message 70: the answer the run ended on ===
    thinking        : '...Let me write them all in parallel batches.'
    text            : 'Let me complete the implementation first, then update the README to document it accurately.'
    tool calls      : []
    str(AgentOutput): 'Let me complete the implementation first, then update the README to document it accurately.'
    the operator sees : Let me complete the implementation first, then update the README to document it
```

The prediction of the probe and the log of the operator agree, line for
line:

| | log of the operator | probe |
|---|---|---|
| request 1 | line 129 `Agent Response`, line 130 the closing rule — **nothing in between** | message 61 → `''` |
| request 2 | line 148 `Agent Response`, line 149 the closing rule — **nothing in between** | message 67 → `''` |
| request 3 | line 164 `Let me complete the implementation first, ...` | message 70 → the same sentence |

The three requests, from the log:

| request | model calls | tool calls | time | tokens (in/out) | answer |
|---|---:|---:|---:|---|---|
| initialize the project | 23 | 36 | 173.23 s | 295 918 / 14 003 | **empty** |
| update the README | 2 | 2 | 9.68 s | 51 114 / 537 | **empty** |
| update the README with the details | 1 | 0 | — | 15 319 of prompt | a promise |

**The model answered.**  Every turn of the session carries a `thinking`
block, and on the three turns above the thinking says exactly what the
model intended to do — *"Let me fix the Kconfig: remove the
VIEWPRO_UART_PORT_NUM_OTHER."*, *"Let me fix the Kconfig UART port config
... and then write the source files."*, *"Let me write them all in
parallel batches."*  On those three turns the model wrote **no text** and
called **no tool**.

### 2.1 The memory buffer of this branch is not the cause

The headline of the branch is *"the memory buffer of the agent trims the
history in one pass"* (`chat_manager/memory.py`, commit `89fd3a7`).  It is
the obvious suspect, so it was measured first: the probe rebuilds the
history of each request from the store and runs both buffers over it.

```
REQUEST: please update a README file acordingly
history at the start of the request: 63 messages
--- LlamaIndex ChatMemoryBuffer ---        messages: 63   opens with role: user   request in window: True
--- TrimmingChatMemoryBuffer (this project) messages: 63  opens with role: user   request in window: True
    the two windows are identical: True
```

The whole history fits the 10 000-token limit of the buffer, the request
of the operator is in the window, and the two buffers return the same
messages in the same order.  **The branch's change did not cause the
misbehaviour.**

### 2.2 The context window the agent sent was fiction

The log says the agent believed in a window of a million tokens:

```
2026-11-13 18:22:56,776 [INFO] components.ollama_config: Context window resolved from the model's advertised maximum: 1000000 tokens
2026-11-13 18:22:56,776 [INFO] components.ollama_config: Context window: 1000000 tokens — the model's advertised maximum
```

`resolve_context_window_with_source()` tries the running model
(`/api/ps`), then the Modelfile of the model (`PARAMETER num_ctx`), and
falls back to **the advertised maximum** — the number the model *could*
hold, not the number the server *uses*.  Both real probes failed for that
model, and the fallback was taken.  The same happens today, and is
reproducible:

```
model                                            advertised  modelfile resolution
north-mini-code-1.0:latest                           500000       None (500000, "the model's advertised maximum")
qwen3-coder:latest                                   262144       None (262144, "the model's advertised maximum")
richardyoung/qwen3.6-27b-abliterated:Q4_K_M          262144     8192 (8192, "the model's Modelfile (PARAMETER num_ctx)")
```

The Modelfile of `north-mini-code-1.0` carries no `PARAMETER num_ctx`
at all, and `/api/ps` was empty because the model was not loaded yet at
the moment of the probe.  The agent therefore asked the server for a
window of a million tokens.

**What that costs is measurable.**  The server clamps the request to what
the hardware allows — and the model stops fitting on the GPU:

```
request with num_ctx=1000000   /api/ps: context_length=500000  size_vram=3086399569   (3.09 GB)
request with num_ctx=8192      /api/ps: context_length=8192     size_vram=6643431505   (6.64 GB)
```

With the window the agent asked for, the weights and the cache of the
model are split across the GPU and the CPU.  The run paid for it:
173 seconds and twenty-three calls for the first request, one call alone
39.6 seconds.

### 2.3 The replay

The model that ran the session is gone: the server was restarted at
19:03, and the model of the run advertised a window of 1 000 000 tokens —
none of the installed models does today (500 000 and 262 144).  The two
turns of the second request were therefore replayed against the model
that is installed now, with the operator's own selection of tools
(**37** — the 11 of *Operating System*, the 7 of *System* and the 19 of
*Project Management*, which is exactly the number the log names) and the
system prompt of the project:

```
WORKING turn (prompt ends with the request)  (64 messages)
    thinking (  370 chars): "...Let me read the current README first."
    text    (    0 chars): ''
    tool calls        : ['read_file']

SILENT turn (prompt ends with the tool results)  (67 messages)
    thinking (  621 chars): "...I'll keep it simple: one config.\n\nLet me rewrite the Kconfig.projbuild."
    text    (    0 chars): ''
    tool calls        : ['write_file']
```

The conversation of the run, the tools of the run and the system prompt
of the run — and the model answers with the tool call the run lacked.  The
**intent** of the model in the replay is the same as in the run (*"Let me
rewrite the Kconfig.projbuild"* / *"Let me fix the Kconfig: remove the
VIEWPRO_UART_PORT_NUM_OTHER."*); what was missing in the run was the tool
call itself.  The trigger is therefore the model build that served the
session, and that build is not on the machine any more.

## 3. The root cause

Two defects, one behind the other.

### 3.1 The answer was dropped twice on the way to the screen

The console path of `agent-torvalds-mw.py` prints the answer like this:

```python
response_text = (result.get("output") if isinstance(result, dict) else str(result))
...
console.rule("[blue]Agent Response[/blue]")
console.print(Markdown(response))
console.rule()
```

`result` is the `AgentOutput` of the framework, and `AgentOutput` says:

```python
def __str__(self) -> str:
    return self.response.content or ""
```

`response.content` is the text of the **text blocks** of the message —
nothing else.  The `thinking` block of the model is not part of it, and
an answer that carries nothing but a thinking block has a content of
`""`.  So:

1. `str(result)` returns `""` — the thinking of the model is **gone**;
2. `console.print(Markdown(""))` prints **nothing at all** — not an
   error, not a warning, not a note.

That is the whole of the silence.  The agent had an answer in its hands —
a thinking that said *"Let me fix the Kconfig: remove the
VIEWPRO_UART_PORT_NUM_OTHER."* — and it showed the operator an empty
box, twice.

The TUI path has the guard the console path does not have
(`components/tui/tui_app.py`):

```python
# If response is None or empty, provide fallback
if not response:
    response = "*No output returned from agent.*"
```

The console path of `agent-torvalds-mw.py` and of `agent-torvalds.py` has
no such guard.  The project already owns the renderer that does the job
right — `components/chat_message.py::to_output_string()` renders the
thinking, the text and the tool calls, one thing per line — and the
event consumer uses it for the log.  The answer that reaches the
operator does not go through it.

### 3.2 A run ends on the first turn without a tool call, whatever it says

`HITLFunctionAgent.parse_agent_output()` ends the workflow on the first
turn that carries no tool call (`components/hitl_agent.py`, the four
`return await super().parse_agent_output(ctx, ev)`).  Nothing checks
that the model actually said something, and nothing checks that it did
what it said it would do.

So the third request is the same defect seen from the other side: the
model wrote *"Let me complete the implementation first, then update the
README to document it accurately."*, called no tool, and the agent took
the sentence for the answer of the request and stopped.  The operator
asked for a README and was told the agent would do something else first
— and the agent believed it.

## 4. The fix

Three changes, in the order the operator would feel them.

**(a) The operator must never be left in silence.**  The answer that goes
to the screen is built with `to_output_string()` instead of
`str(result)`, so the thinking of the model is shown next to its answer;
and when the answer is empty, the console path says so — the guard the
TUI already has.  *Affected:* `agent-torvalds-mw.py`, `agent-torvalds.py`,
`agent-torvalds-cpp.py`.

**(b) A run must not end on a turn that says nothing.**  When the model
returns neither text nor a tool call, the run is not finished: the agent
asks again, once, and if the model says nothing again, the answer says
so plainly — *"the model ended the turn without an answer"* — instead of
ending in silence.  *Affected:* `components/hitl_agent.py`.

**(c) The window the agent sends must be the window of the server.**  The
advertised maximum of a model is not the window the server uses, and
sending it pushes the model off the GPU (measured: 3.09 GB instead of
6.64 GB of VRAM).  When neither `/api/ps` nor the Modelfile answers, the
agent must not invent a number: it must use the configured window, or a
conservative default, and say in the log that the window is unknown.
*Affected:* `components/ollama_config.py`.

## 5. Verification

* A test that feeds the agent a model which answers with a thinking and
  no text: the run must not end in silence, and the operator must be
  told what happened.
* A test for the console path: an empty answer must produce a line on the
  screen, not an empty box.
* A test for the context window: a model whose Modelfile carries no
  `PARAMETER num_ctx` must not be sent the advertised maximum.
* The gate of the repository must stay green: 40 known failures, 0 new,
  0 fixed.

## 6. What is *not* in this change, and why

* **Why the model build of the run stopped mid-turn is not answered.**
  The build is not on the machine any more (the server was restarted at
  19:03), and the replay with the installed model and the operator's own
  37 tools produces the tool call the run lacked.  The two candidates
  that remain — a generation limit in that build, and the model
  answering "nothing" when the conversation has grown long — are not
  separated by the evidence that is left.  What *is* answered is the
  part the operator can act on: whatever the model says, the agent must
  not be silent about it.
* **The memory buffer of this branch is not touched.**  It was measured
  (§2.1) and it is not the cause.
* **The rendering problems of the TUI** — the ones of
  `~/torvald-log/torvalds-mw-issue.txt`, where the text of the main
  window cannot be selected without the progress window — are a
  different question and belong in a different folder.
* **The tool selection of the operator** is not touched.  The 37 tools
  were the right ones for the task.

## 7. The recommendation to the operator

Take **(a)** and **(b)** first: they are the difference between an agent
that is quiet and an agent that says what happened.  The cost is small —
the renderer is already written (`components/chat_message.py`), and the
guard is already written (in the TUI).

Take **(c)** with them: the window of a million tokens is a number the
server never used, and it cost the run the GPU.

And one thing that is not code: **keep the model that misbehaves under a
name you can point at.**  The build that served the session is gone, and
that is the reason the last question of this report cannot be answered
from the machine.  When a model says nothing, the log should say *which*
model said nothing.

The work that follows this report is a separate change, on its own
branch, with its own pull request.
