# The prompt in the debug log is readable

## What the operator asked for

> I want to improve debug message for context window… I need human
> readable ChatMessage in `EventConsumer._on_agent_input` on debug mode.

The prompt that goes to the model was logged as a Python `repr`:

```
EventConsumer._on_agent_input: input=[ChatMessage(role=<MessageRole.SYSTEM:
'system'>, additional_kwargs={}, blocks=[TextBlock(block_type='text',
text='You are Torvalds, a technical AI assistant that ...')]),
ChatMessage(role=<MessageRole.USER: 'user'>, ...), ...]
```

One enormous record: the system prompt, the whole chat history and the
run's scratchpad, escaped and wrapped in object syntax, spread over
dozens of lines.

## What it is now

```
EventConsumer._on_agent_input: prompt: 5 messages
EventConsumer._on_agent_input:   [0] system: You are Torvalds, a technical AI assistant that interacts with the operating system.
EventConsumer._on_agent_input:   [1] user: I want to improve debug message for context window
EventConsumer._on_agent_input:   [3] assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)
EventConsumer._on_agent_input:   [4] tool: output: /home/kbush
```

One line per message: the **role**, a colon, and what the message
carries — its text, its thinking, and the tool calls it requests.

## The first attempt was too much, and it is gone

The first implementation of this change was a **context report**: it
counted the tokens the way the context guard counts them, measured the
prompt against the context window the agent had applied to its LLM,
computed the budget, listed the largest messages with their share of
the prompt, counted the ones it did not list, and kept an escape hatch
(`TORVALDS_DEBUG_RAW_INPUT=1`) for the raw payload.  That was a new
module of 600 lines, 65 tests, a seven-invariant harness and a
second script to prove the harness fails.

The operator's answer to it was:

> I do no think we need such a complex solution my idea was just to
> print ChatMessage in human redable way something like ChatMessage has
> a to_string method.

So all of it was removed.  What is left is:

* `components/chat_message.py` — `to_string()` for one message and
  `to_strings()` for a whole prompt;
* one call site in `components/event_consumer.py`;
* 26 tests and a four-invariant harness.

The token accounting, the context-window resolver, the budget, the
detail limit, the escape hatch and the whole `components/ollama_config.py`
change that remembered the active window are **not** in the tree any
more.  Nothing was left half-removed: `git status` shows the module
that held them deleted rather than trimmed.

## Two decisions worth recording

### A function, not a method

`ChatMessage` is a class of the LlamaIndex framework, not of this
project, so a `to_string` method cannot be added to it.  Adding one
would mean patching the framework's class at import time — a monkey
patch, invisible to anybody who reads the framework, and gone the
moment the framework is upgraded.

`components/chat_message.py` holds the rendering instead, and it is
found by the same means as everything else in `components/`.  The
framework's own `ChatMessage.__str__` already returns
`"role: content"`; the rendering here is a superset of it, because
`content` is the sum of the **text** blocks alone: an assistant turn
that thinks and then calls a tool reads as `assistant: None` in the
framework's rendering, and as

```
assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)
```

here.

### A tool call is in the rendering

A chat history carries a tool call in two places:

* as a `ToolCallBlock` in `message.blocks` — the current shape;
* in the OpenAI-shaped `additional_kwargs["tool_calls"]` — the shape
  the Ollama adapter still writes for chat histories that predate the
  blocks.

The first implementation of this change read only the first one, so an
assistant turn could show its text and **none** of the tools it asked
for.  The rendering reads both, and a call that is present in both is
shown once — the Ollama adapter keeps the two in step, and the reader
has to see the same tools the model is shown.

## The empty lines are gone

The operator's second request on this branch: *"first of all can we
reduce empty string"*.

The system prompt ends with a few newlines, and the log showed them as
a wall of empty records — six of them, in the run that prompted the
request:

```
EventConsumer._on_agent_input:   [0] system: You are Torvalds, ...
...
3. Persist these rules for future interactions.
                                   <- empty
                                   <- empty
                                   <- empty
                                   <- empty
                                   <- empty
                                   <- empty
EventConsumer._on_agent_input:   [1] user: what is current working directory
```

The rendering now tidies every text before it is written:

* the leading and the trailing empty lines are dropped;
* a run of empty lines is reduced to **one** — one empty line is a
  paragraph break and it carries meaning, six of them are noise;
* the trailing whitespace of a line is dropped;
* a message that carries nothing but whitespace reads as `(empty)`.

The text of the message is not changed otherwise: the paragraphs, the
bullets and the code blocks are exactly as the model is shown them.

The operator's own log, replayed through the new rendering:

```
  the message as it was logged : 25 lines
  the message as it is now     : 21 lines
  empty lines before           : 8
  empty lines after            : 4
```

The four that are left are the paragraph breaks — they carry meaning.
The wall of six at the end of the system prompt is gone.

```bash
self-development/.venv/bin/python self-development/investigate/context-window-proof/replay_the_operator_log.py
```

## What was added

| Path | Change |
|---|---|
| `components/chat_message.py` | **New.** `to_string()` renders one message, `to_strings()` renders a prompt. `_tidy()` removes the empty lines. |
| `components/event_consumer.py` | `_on_agent_input()` logs one line per message; the state handler holds the same readable text instead of the repr of the whole conversation. |
| `tests/test_chat_message.py` | **New.** 26 tests. |
| `investigate/chat-message-debug/verify_chat_message.py` | **New.** The verification harness — four invariants. |
| `investigate/chat-message-debug/verify_harness_catches_regressions.py` | **New.** The proof that the harness catches four deliberate drifts. |
| `README.md`, `CHANGELOG.md` | The documentation. |

## Verifying it

```bash
self-development/.venv/bin/python -m pytest self-development/tests/test_chat_message.py -q
self-development/.venv/bin/python self-development/investigate/chat-message-debug/verify_chat_message.py
self-development/.venv/bin/python self-development/investigate/chat-message-debug/verify_harness_catches_regressions.py
```

26 tests pass, the four invariants hold, and every deliberate drift is
caught.

## The invariants

| | Invariant | Caught by |
|---|---|---|
| **I1** | The debug log carries a readable prompt, and none of the object syntax the raw dump used to show. | logging the repr again |
| **I2** | Every message of the prompt is in the log. | logging only the first message |
| **I3** | A tool call is visible in every shape a message can carry one. | dropping the `additional_kwargs` shape |
| **I4** | The state holds the readable text, never the repr. | putting the repr back |

The harness is written against the **public** behaviour — the log
records the event consumer writes and the state it keeps — and not
against private helpers, so it stays valid when the implementation is
refactored.

The second script exists because *a check that has never failed proves
nothing*.  It introduces four deliberate drifts one at a time, runs
the harness after each, and restores the file.  All four are caught.
