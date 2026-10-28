# Investigation Report: the empty *Agent Response* section

**Status:** root cause found, fix implemented, verified.
**Branch:** `investigate/empty-agent-response`
**Reported symptom:** `/home/kbush/torvald-log/ebent-empty-response.md`

---

## 1. The symptom

The operator's report carries two runs. In both of them the section under
the **Agent Response** rule was empty at the end of the run, while the run
itself had produced something:

```
2026-10-28 15:22:07,997 [DEBUG] components.stats_handler:   → LLM call #2 finished — prompt=7494, completion=1, total=7495 tokens
2026-10-28 15:22:07,997 [DEBUG] components.event_consumer: EventConsumer._on_agent_stream: delta=''
2026-10-28 15:22:07,998 [DEBUG] components.event_consumer: EventConsumer._on_agent_output: assistant: (empty)
2026-10-28 15:22:08,294 [DEBUG] components.event_consumer: EventConsumer._on_stop_event: tool result: execute_shell_command: {'stdout': 'List of relations\n Schema | Name | ...', 'returncode': 0, 'success': True}
...
────────────────────────────────────────────────────────────── Agent Response ───────────────────────────────────────────────────────────────
─────────────────────────────────────────────────────────────────────────────────────────────
```

The operator's own words: *"The answer in the last stop event is the tool
result, but Agent Response remains empty!"*

Nothing in the pipeline reported a failure. Both runs ended with

```
Stats finalized — request_id=0e4b0aa1, duration=1342249.3ms, llm_calls=2, tokens=14844 (📥14727 📤117), tools=1, errors=0
EventConsumer.consume_events: workflow completed successfully
```

**errors=0** — the run was a success, with nothing to show for it.

The two runs of the report:

| | run 1 (11:04) | run 2 (15:21) |
|---|---|---|
| duration | 4452 s | 1342 s |
| LLM calls | 13 | 2 |
| tokens (in/out) | 82684 / 1521 | 14727 / 117 |
| tool calls | 11 | 1 |
| the last model call | `prompt=7173, completion=22` | `prompt=7494, completion=1` |
| what the model wrote | a *thinking* block, no text | an empty text block |
| the debug log says | `assistant: thinking: user` | `assistant: (empty)` |
| the tool result | in the output | in the output |
| the Agent Response section | **empty** | **empty** |

## 2. The chain that loses the answer

The answer of a run is rendered from the **text blocks** of the model's
message and from nothing else. Five lines of the framework and one line of
this project are enough to lose it.

**1. The model answered in the *thinking* channel.**

The Ollama adapter writes what the server sent as it came:

```python
# llama_index/llms/ollama/base.py — astream_chat()
output_blocks: List[ToolCallBlock | ThinkingBlock | TextBlock] = [
    TextBlock(text=response_txt)
]
if thinking_txt:
    output_blocks.insert(0, ThinkingBlock(content=thinking_txt))
```

A model that reasons but does not write an answer leaves a message with a
`ThinkingBlock` and an **empty** `TextBlock`.

**2. `ChatMessage.content` is the text of the TextBlocks only.**

```python
# llama_index/core/base/llms/types.py
@property
def content(self) -> str | None:
    content_strs = []
    for block in self.blocks:
        if isinstance(block, TextBlock):
            content_strs.append(block.text)
    ct = "\n".join(content_strs) or None
    if ct is None and len(content_strs) == 1:
        return ""
    return ct
```

The *thinking* is not part of it. The three shapes that a run can end in:

| the message carries | `response.content` | `str(AgentOutput)` |
|---|---|---|
| a thinking block only | `None` | `""` |
| a thinking block and an empty text block | `""` | `""` |
| no blocks at all | `None` | `""` |

**3. `AgentOutput.__str__` reads that property.**

```python
# llama_index/core/agent/workflow/workflow_events.py
def __str__(self) -> str:
    return self.response.content or ""
```

**4. This project printed the result with `str()`.**

```python
# agent-torvalds.py — prompt_handler()
response_text = (
    result.get("output")
    if isinstance(result, dict)
    else str(result)
)
```

**5. The section under the rule was therefore empty** — while the tool
result that held the answer sat in `result.tool_calls`, which nobody read.

`investigate/empty-agent-response/probe_response_extraction.py` runs the
whole chain without a model and shows the two cases side by side:

```
--- the reported case: an empty text block ---
  response.content          : ''
  str(AgentOutput)          : ''
  what the Agent Response   : ''
  is it empty?              : True
  what the log shows        :
      assistant: (empty)
      tool result: execute_shell_command: List of relations
      ...
```

```
The tool result is in the output the whole time:
  output.tool_calls[0]: execute_shell_command
  its content         : 'List of relations\n Schema |       Name       |   Type   |  O'...
  but str(output) is  : ''
```

**The answer was never lost — it was never looked for.**

### 2.1 The first run of the report is the same failure

The debug log of run 1 shows two lines:

```
EventConsumer._on_agent_output: assistant: thinking: user
EventConsumer._on_agent_output: [Human response] **Switch to `llama_index_db`** and check there?
```

Those are the two lines of **one** record: the thinking block of the model
carried the text

```
user
[Human response] **Switch to `llama_index_db`** and check there?
```

— the model repeated the human's own message (the agent injects it as
`[Human response] <answer>`) instead of answering. There was **no text
block at all**, so `response.content` was `None` and the section was empty,
exactly as in run 2.

## 3. Why the model answered with nothing

The empty answer is the **model's** behaviour, and it is reproducible
without the agent. `investigate/empty-agent-response/probe_long_prompt.py`
asks the running server the same question at several prompt sizes; the
result (`sweep.log`):

```
model      : richardyoung/qwen3.6-27b-abliterated:Q4_K_M
num_ctx    : 8192
reported   : prompt=7494 tokens, completion=1

repeats=   0  prompt=564  completion=173  content_len=0  thinking_len=317  chunks=83
             thinking only: 'The user wants to see the schema of every table in the `llama_index_db` database.\nThe previous command showed the list of tables: `chat_sessions`, `chatstore`, '
repeats= 100  prompt=4664  completion=210  content_len=0  thinking_len=500  chunks=120
             thinking only: "The user wants to see the schema of every table in the `llama_index_db` database.\nThe previous command listed the relations but didn't show the detailed schema "
repeats= 200  ERROR: 500 Server Error: Internal Server Error for url: http://localhost:11434/api/chat
```

**`content_len=0` with `thinking_len` in the hundreds** — the model reasons
and writes no answer at all. The reported run's `completion=1` is the same
thing at its smallest: the model produced one token and stopped.

Two things make it more likely, and both are visible in the report:

**The prompt was nearly full.** The last model call of run 2 carried
**7494 prompt tokens against a window of 8192** — 91 % of it. The server
truncates a prompt that does not fit, keeping the most recent tokens
(`truncation.log`, produced with a small model so the boundary is visible
in seconds):

```
  filler x   ~prompt  server prompt_eval  completion  done_reason  answer
         1       488                 456           3         stop  'Paris.'
         2       938                 856           2         stop  'Paris'
         4      1838                 514       10240       length  'The quick brown fox jumps over the lazy '
         8      3638                 514          67         stop  "It looks like you've been using the famo"
        16      7238                 514          51         stop  "I'm sorry, but it looks like you've type"
```

The server evaluated **514** prompt tokens for a prompt of 3638 — it kept
the *newest* tokens and dropped the request at the front, and the model
answered with the filler. That is the same failure
`investigate/no-user-query-error/` documented as *"No user query found in
messages."*, and it is the reason the request is lost.

**A prompt that fills the window confuses the model**
(`window_exhaustion.log`, window 1024):

```
  filler x  server prompt  completion  done_reason  answer
         1             79         142         stop  "I apologize for any confusion, but I'm an AI"
         3            161         278         stop  "I'm sorry, but I'm not able to access or des"
         5            243         111         stop  "I apologize, but I'm not able to provide a l"
         9            407          85         stop  "I'm sorry, but I don't have any information "
        13            571          73         stop  "It seems like you're asking me to describe t"
```

The closer the window gets, the less the model says — and what it says is
an apology.

### 3.1 It is the model, and it happens with a short prompt too

The same conversation, sent to two models on the same server
(`probe_raw_chunks.py`, `raw_chunks.log`):

| model | prompt tokens | `content_len` | `thinking_len` |
|---|---|---|---|
| `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (**the reported model**) | 564 | **0** | 236 |
| `richardyoung/qwen3-8b-abliterated:Q4_K_M` | 424 | 904 | 1245 |

The 27b model **is the reported failure**, reproduced directly against the
real server: it reasons in the thinking channel and writes no answer at
all. The 8b model answers the very same question in the very same
conversation.

So the empty answer is not a consequence of the full window — the window
makes it worse (the sweep above), but the model alone is enough. It is
also not something this project can configure away: the answer of a
thinking model lands in `content` or in `thinking` depending on the
model, the prompt and the state the model is in.

**The conclusion:** the model *can* end a run without an answer, and when
it does the agent must not render nothing. The model is not the part this
project controls; the rendering is.

## 4. The fix

### 4.1 `components/agent_answer.py` (new)

One place that says what the run has:

* `extract_answer(result)` returns the text of the model when there is one,
  **unchanged**;
* when there is none, it returns a readable notice — *"The model returned
  no answer"* — **and the last tool result of the run** (which is usually
  the thing the operator asked for) **and the thinking of the model**;
* it never returns an empty string, and it never raises: a payload from
  the framework must not be able to break the run.

The shapes that are read: the `AgentOutput` of the workflow, the legacy
`{"output": ...}` dict, and a plain string.

### 4.2 `components/hitl_agent.py` — one more turn

A run in which the model wrote nothing is given **one** more turn before it
is given up on:

* the check happens in `parse_agent_output()`, before the question
  detection and before the tool calls — a run that wants to *act* is never
  interrupted, and a run that *asked* a question is never interrupted;
* the nudge follows the empty answer in the scratchpad, so the model sees
  what happened before it is asked again;
* the iteration is counted, because the base implementation is not called
  on that path and the budget of the run has to include it;
* **one** turn, not more: every turn is a full round-trip to a local
  model, and a model that answered nothing once usually answers nothing
  again.

### 4.3 The entry points

`agent-torvalds.py`, `agent-torvalds-mw.py` and `agent-torvalds-cpp.py`
read the answer through `extract_answer(result)` instead of
`str(result)`.

## 5. Verification

### 5.1 The invariants (`verify_empty_response.py`)

```
$ self-development/.venv/bin/python \
      self-development/investigate/empty-agent-response/verify_empty_response.py
[OK  ] E1  the answer of a run with a tool result is 859 characters
[OK  ] E1  the answer of a run with an answer is not empty
[OK  ] E1  the legacy dict shape is read
[OK  ] E1  a plain string is read
[OK  ] E2  the operator is told that the model wrote nothing
[OK  ] E2  the missing answer is recognised as missing
[OK  ] E2  an answer that exists is not reported as missing
[OK  ] E2  the log says that the model wrote nothing
[OK  ] E3  the tool result is in the answer
[OK  ] E3  the tool that produced it is named
[OK  ] E4  the answer is returned as it is ('The database has three tables.')
[OK  ] E4  the legacy dict shape is returned as it is
[OK  ] E5  the extraction survives a payload that raises
[OK  ] E6  the run is given 1 more turn(s) at most
[OK  ] E6  the model was asked twice (it was asked 2 times)
[OK  ] E6  the run ended with the answer of the second turn ('The database has three tables.')

16/16 checks hold
```

### 5.2 The proof that the harness catches the drifts (`verify_harness_catches_regressions.py`)

Six deliberate drifts, one per invariant, each applied to a **copy** of the
package:

```
[OK  ] D1 — the answer is read off the result again          caught by E1
[OK  ] D2 — the notice is not shown any more                  caught by E2
[OK  ] D3 — the tool results of the run are not shown         caught by E3
[OK  ] D4 — the answer is trimmed on the way out              caught by E4
[OK  ] D5 — a payload that raises takes the run down          caught by E5
[OK  ] D6 — the run is not given another turn                 caught by E6

6/6 drifts caught
```

### 5.3 The tests (`tests/test_agent_answer.py`)

32 tests: the extraction in every shape it can take, the run that is given
another turn (the real `HITLFunctionAgent` with a mock LLM), and the
wiring of the three entry points.

```
$ self-development/.venv/bin/python -m pytest tests/test_agent_answer.py -v
32 passed
```

### 5.4 No regressions

The CI gate compares the failures with the committed baseline:

```
$ self-development/.venv/bin/python scripts/ci_test_gate.py
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
fixed since the baseline        : 0

No new failures. The build may proceed.
```

## 6. Notes and follow-ups

* **The empty answer is the model's behaviour, not a bug in the agent.**
  The fix does not make the model answer — it makes the run *say* what it
  found, and it gives the model one more turn. A local model that is
  out of room will answer again with nothing, and then the notice and the
  tool result are what the operator gets.
* **The model is the lever the operator has.** The reported model
  (`richardyoung/qwen3.6-27b-abliterated:Q4_K_M`) answers the same
  question in the *thinking* channel only, while
  `richardyoung/qwen3-8b-abliterated:Q4_K_M` answers it normally
  (section 3.1). `TORVALDS_MODEL` chooses the model; the fix makes every
  model behave the same way *when it answers nothing*.
* **A full window makes it worse.** The run that reported the symptom
  carried 7494 of 8192 prompt tokens — 91 % of the window — and a prompt
  that does not fit is truncated by the server, which drops the request
  at the front (section 3). The context guard
  (`components/context_guard.py`, `--context-guard-on`) trims the prompt to
  the window the server really uses; it is **off by default**, and the
  operator's decision.
* **The nudge ends up in the chat history.** The retry appends the nudge
  to the scratchpad, and `finalize()` writes the scratchpad into the
  memory — so the next session sees *"Your previous reply was empty"*. It
  is honest, and it is a small price for a run that has an answer.
* **The statistics do not know about the empty answer.** A run without an
  answer is reported as a success (`errors=0`). The notice in the answer
  section is the only place the operator is told. A counter for it would
  be a separate change.

## 7. Files

| file | purpose |
|---|---|
| `components/agent_answer.py` | the answer of a run, and what to show when there is none (new) |
| `components/hitl_agent.py` | gives the run one more turn when the model wrote nothing |
| `agent-torvalds.py`, `agent-torvalds-mw.py`, `agent-torvalds-cpp.py` | read the answer through `extract_answer` |
| `tests/test_agent_answer.py` | the tests (new) |
| `investigate/empty-agent-response/probe_response_extraction.py` | the chain that loses the answer — no model needed |
| `investigate/empty-agent-response/probe_long_prompt.py` | the model at several prompt sizes (`sweep.log`) |
| `investigate/empty-agent-response/probe_sweep.py` | the same sweep, in the background |
| `investigate/empty-agent-response/probe_raw_chunks.py` | the chunks of one request, so the shape of the answer is visible (`raw_chunks.log`) |
| `investigate/empty-agent-response/probe_truncation.py` | what the server does with a prompt that does not fit (`truncation.log`) |
| `investigate/empty-agent-response/probe_window_exhaustion.py` | the window filling up while the model answers (`window_exhaustion.log`) |
| `investigate/empty-agent-response/probe_reported_prompt.py` | the reported conversation, sent to the real model |
| `investigate/empty-agent-response/repro_end_to_end.py` | the whole run with a mock LLM: the empty section, reproduced |
| `investigate/empty-agent-response/verify_empty_response.py` | the six invariants |
| `investigate/empty-agent-response/verify_harness_catches_regressions.py` | the proof that the harness catches six deliberate drifts |
