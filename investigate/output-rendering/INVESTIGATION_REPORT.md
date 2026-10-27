# The answer in the debug log

## What the operator asked for

> can you check is there another place in EventConsumer ChatMessage we can
> update output formating to make it human redable

The prompt was made readable in the last change.  The question is
whether the **answer** — the other half of the run — is in the log in a
form a person can read.

**It is not.  It is not even there.**

| Path | What it is |
|---|---|
| `probe_output_rendering.py` | The probe — it runs the **real** handlers with the **real** event the framework emits, and prints what they log. |
| `verify_output_rendering.py` | The harness — six invariants, written against the log records the consumer produces. |
| `verify_harness_catches_regressions.py` | The drift proof — six deliberate breaks, each caught by the invariant it attacks. |

---

## The finding

The event consumer has two handlers that deal with the answer:

```python
async def _on_stop_event(self, event: StopEvent) -> None:
    logger.debug("EventConsumer._on_stop_event: workflow stopping, result=%r", event.result)

async def _on_agent_output(self, event: AgentOutput) -> None:
    output_val = getattr(event, 'output', None)
    logger.debug("EventConsumer._on_agent_output: output=%r", output_val)
```

Both were wrong, and the second one was wrong in a way that a
formatting fix would have hidden.

### The answer was never logged

`AgentOutput` has **no `output` field**.  The installed LlamaIndex says
so:

```
=== AgentOutput fields ===
  response: <class 'llama_index.core.base.llms.types.ChatMessage'>
  structured_response: typing.Optional[typing.Dict[str, typing.Any]]
  current_agent_name: <class 'str'>
  raw: typing.Optional[typing.Any]
  tool_calls: list[llama_index.core.llms.llm.ToolSelection]
  retry_messages: list[llama_index.core.base.llms.types.ChatMessage]

hasattr(AgentOutput, "output") = False
```

The handler read `event.output`, so `getattr(event, 'output', None)`
returned `None` **every single time**.  The probe shows it:

```
EventConsumer._on_agent_output: received agent output
EventConsumer._on_agent_output: output=None
```

The answer was in `event.response`.

**Why the code looked right:** `event_consumer.py` defines dummy event
classes for the case where LlamaIndex is not installed, and the dummy
`AgentOutput` has `self.output`.  The fallback masked the real API —
the code was written against the fallback and never checked against the
framework.  The framework was right there in the same file, five
imports above.

### The answer was buried in a model repr

`StopEvent.result` **is** the `AgentOutput` — the framework returns the
answer event as the result of the workflow:

```python
ctx.write_event_to_stream(output)
return StopEvent(result=output)
```

So the answer *was* in the log, inside the repr of the whole model:

```
EventConsumer._on_stop_event: workflow stopping, result=AgentOutput(response=ChatMessage(role=<MessageRole.ASSISTANT: 'assistant'>, additional_kwargs={}, blocks=[TextBlock(block_type='text', text='Let me look at the disk.')]), structured_response=None, current_agent_name='torvalds', raw=None, tool_calls=[ToolSelection(tool_id='call-1', tool_name='execute_shell_command', tool_kwargs={'command': 'df -h /'})], retry_messages=[])
```

One record, the whole model, the answer somewhere inside it, and
nothing that a reader can pick out.

### The same defect, one level further down

The prompt was fixed by rendering the messages.  The answer is the same
problem: the same `ChatMessage` class, the same kind of object syntax,
logged the same way.  The fix is the same kind of fix — and it is worth
noting that **the readability fix and the missing-answer fix are the
same fix**: a handler that reads the wrong field cannot be made
readable.

---

## The fix

### `components/chat_message.py` — `to_output_string()`

The answer event carries more than the text: the tool calls the agent
asked for, the structured response, and the messages it was asked to
retry with.  All of it is rendered, one thing per line:

```
assistant: The disk is 78% full: 12 GB of 16 GB are in use.
tool call: execute_shell_command(command=df -h /)
structured: {'answer': '78%'}
retry 1: assistant: I was not sure.
```

A call that the answer already shows as a block is **not** shown twice:
the reader has to see the same tools the model is shown, once.

The renderer is a function and not a method, for the same reason
`to_string` is: `ChatMessage` and `AgentOutput` are classes of the
framework, and a method on them would have to be monkey-patched onto it.

### `components/event_consumer.py` — the two handlers

```python
answer = to_output_string(event)
if answer:
    for line in answer.splitlines():
        logger.debug("EventConsumer._on_agent_output: %s", line)
    self.state.set("agent_output", answer)
else:
    output_val = getattr(event, "output", None)
    logger.debug("EventConsumer._on_agent_output: output=%r", output_val)
```

One thing per line, like the prompt.  The `else` branch keeps the old
behaviour for a payload that cannot be read, so nothing is ever lost.

The answer also goes into the **state**, as the readable text and not
as the repr — the state is a debugging aid, and the repr of a long
answer is a wall of object syntax.

### Before and after

```
--- before -------------------------------------------------
EventConsumer._on_agent_output: output=None
EventConsumer._on_stop_event: workflow stopping, result=AgentOutput(response=ChatMessage(role=<MessageRole.ASSISTANT: 'assistant'>, additional_kwargs={}, blocks=[TextBlock(block_type='text', text='Let me look at the disk.')]), structured_response=None, current_agent_name='torvalds', raw=None, tool_calls=[ToolSelection(tool_id='call-1', tool_name='execute_shell_command', tool_kwargs={'command': 'df -h /'})], retry_messages=[])

--- after --------------------------------------------------
EventConsumer._on_agent_output: assistant: Let me look at the disk.
EventConsumer._on_agent_output: tool call: execute_shell_command(command=df -h /)
EventConsumer._on_stop_event: assistant: Let me look at the disk.
EventConsumer._on_stop_event: tool call: execute_shell_command(command=df -h /)
```

---

## What the harness found

**A payload that raises would have broken the run.**  The rendering
reads the payload with `getattr`, and `getattr` only swallows the
`AttributeError` of a *missing* attribute — a property that *raises*
propagates.  A chat history written by an older version, or a payload
from a tool, would have taken the agent down with it, in the middle of
a run, over a **debug log**.

The invariant caught it:

```
[FAIL] O6  the handler survives a payload that raises
```

Every `getattr` in `components/chat_message.py` now goes through
`_safe_getattr()`, which treats anything that goes wrong as "not there".
The module is exception-proof.

---

## The invariants

| | Invariant | Caught by |
|---|---|---|
| **O1** | The answer is in the log, and the record does not say `output=None`. | the handler reading the field the framework does not have again |
| **O2** | The tool calls of the answer are in the log, each of them once. | the tool calls not being rendered |
| **O3** | The structured response is in the log. | it not being rendered |
| **O4** | The retry messages are in the log. | them not being rendered |
| **O5** | No object syntax leaks into the log — no `ChatMessage(`, no `MessageRole.`, no `AgentOutput(`. | the stop event logging the repr of the model again |
| **O6** | A payload that cannot be read does not break the run. | the renderer not being exception-proof |

### Running it

```bash
self-development/.venv/bin/python investigate/output-rendering/probe_output_rendering.py
self-development/.venv/bin/python investigate/output-rendering/verify_output_rendering.py
self-development/.venv/bin/python investigate/output-rendering/verify_harness_catches_regressions.py
```

**8 checks hold**, **6 of 6 drifts are caught**, and the 45 tests of
`tests/test_chat_message.py` pass.  The CI gate reports **0 new
failures**.

---

## The places that are left

The operator asked about `ChatMessage`.  These are the remaining places
in the consumer where something is logged as a Python `repr` that is
not a chat message.  They are **not** changed by this work — they are
plain strings and plain dicts, and the gain is smaller.

| Place | What it logs | What it costs |
|---|---|---|
| `event_consumer.py:484` | `delta=%r` — the streamed token | A multi-line delta shows as `'a\nb'`. It fires for **every token**, so it is also the hottest line in the file. |
| `event_consumer.py:493` | `kwargs=%r` — the tool arguments | A dict repr: `{'command': 'df -h /'}`. Readable enough. |
| `event_consumer.py:667` | `question=%r` — the agent's question | The question is rendered as Markdown for the console; in the log its newlines are escaped. |
| `event_consumer.py:685` | `response=%r` — the operator's own answer | The operator's words, with their newlines escaped. |
| `event_consumer.py:744` | `response=%r` — the human's answer | The same. |
| `event_consumer.py:306` | `handler=%r` — the workflow handler | The repr of an object the operator never asked about. |

Every one of them is a one-character change — `%r` to `%s` — except the
tool arguments, which could use the `name=value` rendering the module
already has for a tool call.  They are worth doing together, and worth
doing when the operator says so.

## The other question the finding raises

The dummy event classes at the top of `event_consumer.py` — the ones
that exist for the case where LlamaIndex is not installed — have **a
different shape from the real events**.  The dummy `AgentOutput` has
`output`, the real one has `response`.  The dummy `ToolCall` has
`tool_kwargs`, `tool_id`; the real one has `tool_name`, `tool_kwargs`,
`tool_id` — that one matches.  The dummies are a hazard of their own:
they let code be written against a shape the framework does not have,
and the compiler and the tests are happy with it.

The fix is to make the dummies **match the framework**: the same field
names, so a mistake like this one cannot be made silently.  It is a
small change and it is not part of this work.
