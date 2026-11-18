# The size of the context, on the screen

## What the operator asked for

The size of the prompt is logged with every request to the model since
2026-11-04:

> *"I need to see in the log the context size in tokens and size of
> bytes. So when request is made to LLM I want to see current context
> size"*

The log carries it (`components/context_metrics.py`):

```
Context: 75 messages, 39,691 tokens, 155.6 KB, 4.0% of the 1,000,000-token window
```

The operator reads that line in the log file, in another terminal. The
multi-window console has a panel that shows the state of the agent while
it works — the **Agent Telemetry & State** pane — and the size of the
context is not in it. The operator has to look away from the agent to
find out how full the context is, and the question the panel exists for
is answered somewhere else.

**The ask:** the size of the context belongs in the telemetry panel, next
to the other numbers of the agent, updated live.

## What the panel shows

```
Prompt │ 39,691 tok (4.0% of 1M window)
       │ 75 msgs · 155.6 KB
```

Two lines, because the panel has room for two and the operator asked
for both numbers:

* the **tokens of the prompt** and the **share of the context window**
  they take — the number that decides whether the next request fits;
* the **number of messages** and the **size of the prompt** — what the
  tokens are made of.

The share is coloured: green below 50%, yellow from 50%, red from 80%.
A context that is three quarters full is a context the operator has to
know about before the next tool result lands in it.

## The panel names every number

The operator looked at the panel on 2026-11-14 and said:

> *"it is not clear from the panel what current prompt size is, in the
> Telemetry window currently I see 41,834 tok (77.0% of 54K)"*

The number was on the screen, and it was the right number.  The row
was called **Context**, and *context* is what the **window** of the
model is called: two numbers stood side by side — "41,834 tok" and
"54K" — and the row did not say which of them was the size of the
prompt that goes to the model.

Two words were wrong, and both were in the wording:

* the **row** was called *Context* — it is called **Prompt** now.  The
  name of the thing is the name of the measurement;
* the **share** said "77.0% of 54K" — the 54K are the window of the
  model, and the readout says so: "77.0% of 54K window".

Only the percentage carries the colour now; the words around it are the
plain text of the panel.  The colour belongs to the share, not to the
window it is a share of.

There is no article in front of the number.  "a 8K window" is wrong,
and the window of a model is not always a number that wants an "a".

The wording was measured against the room the panel has.  The sidebar
is 35% of the terminal, the telemetry pane is half of the sidebar:

| terminal | the sidebar | the panel needs | the pane has | before |
|---|---|---|---|---|
| 80×24 | 28 | 18 lines | 9 — cropped, as before | 18 lines |
| 100×30 | 35 | 15 lines | 12 — cropped, as before | 15 lines |
| 120×40 (the reference size) | 42 | 13 lines | 17 — fits | 13 lines |
| 160×50 | 56 | 13 lines | 22 — fits | 12 lines |

The panel is **not taller** at 80, at 100 and at 120 columns.  At 160
columns it takes one line more, and the telemetry pane has 22 lines
there.

## The measurement is the one that already exists

This is the part that matters most.

The agent measures the prompt before every request — `measure_context()`
in `components/context_metrics.py`, called from `take_step()` in
`components/hitl_agent.py`. The log line is rendered from that
measurement by `describe_context()`.

**The panel shows the same measurement.** Not a second one, not an
approximation of it, not the size of the stored chat history: the same
`ContextSize` object, rendered in two lines instead of one.

The reason is not elegance. A second measurement would be a second
number that can disagree with the first, and the operator would have to
work out which one is the truth before acting on it. The number in the
panel and the number in the log are the same number, and when one of
them moves the other moves with it.

The share of the window is computed from the window the LLM carries
(`_model_context_window()`), which is the same source the log line uses.

## How the measurement reaches the panel

The agent knows the size of the prompt. The panel needs it. Nothing
connects the two today, and the connection has to be explicit — the
agent must not know about the TUI, and the TUI must not reach into the
agent while it works.

An **observer**:

```python
agent.context_observer = callback      # callback(size, window)
```

The agent calls it in `take_step()`, right after the measurement and
**before** `_log_context_size()`:

```
size = self._measure_context([*head, *tail], tools)
self._fit_window_to_prompt(size)
self._publish_context_size(size)       # ← the panel hears about it
self._log_context_size([*head, *tail], tools, size)
```

The observer is called *before* the logging flag is checked, and that
ordering is the whole point of it:

> `--no-context-log` turns the **log** off. It does not turn the
> readout off.

An operator who does not want the size of the prompt in the log file
still wants to see it on the screen — that is the whole reason the panel
gets it. Gating the observer on `context_logging_enabled` would have
made the two switches one, and the flag would have taken the panel with
it.

The observer is optional: `None` means nobody is watching, which is the
case for the classic console (`agent-torvalds.py`) and for every test.

A failing observer never takes the run down. A size is never worth a
run — that is the rule the whole of `components/context_metrics.py` is
built on, and the observer follows it.

## The state of the TUI

`TuiState` carries the measurement to the panel:

| field | what it holds |
|---|---|
| `context_measured` | a measurement arrived (before the first one the panel shows a dash) |
| `context_tokens` | the tokens of the prompt |
| `context_messages` | the messages of the prompt |
| `context_bytes` | the size of the prompt, in bytes |
| `context_window` | the context window of the model |
| `context_estimated` | the tokens were estimated, not counted |

`update_context_size()` writes them under the lock of the state — the
agent runs in the workflow thread, the panel is painted in the render
loop, and the two are not the same thread.

The panel is rendered on every frame, and the numbers are read from the
state, never from the agent. The agent is not asked anything while the
screen is painted.

## The room the panel needs

The telemetry pane grew by two lines — four at the width of a narrow
terminal, where the value of a row wraps.

**The sidebar was left alone**, and that was measured rather than
assumed:

| terminal | the readout | the tool tasks of the progress pane |
|---|---|---|
| 120×40 (the reference size) | complete | 6 of 6 |
| 80×30 | complete | 6 of 6 |
| 80×24 (the smallest supported) | its first line | 3 of 6 |

At 120×40 and at 80×30 the panel has the room for the readout, and
nothing else is lost. At 80×24 the sidebar is 28 characters wide, every
value of the panel wraps, and the panel needs more lines than the
terminal has: the readout keeps its first line — the tokens and the
share — and the bottom of the panel is cut, as it was before this
change.

The alternative was measured too: the telemetry pane taking two thirds
of the sidebar. It buys the second line of the readout at 80×24 **only**,
and it costs the progress pane its tool tasks at *every* size — 3 → 0 at
80×24, 6 → 2 at 80×30, 6 → 5 at 120×40. The layout is left alone, and
the readout sits fourth in the panel, high enough that it is never the
thing that is cropped.

Fitting the panel exactly would mean measuring it and giving the
partition the room it needs — the way the footer is fitted
(`fit_footer()` in `components/tui/layout_manager.py`). That is a
change to the sidebar for its own sake, and it is not part of this one:
the crop of the bottom of the panel is pre-existing.

## What is deliberately left out

* **A second number for the stored chat history.** The panel shows the
  prompt. The stored history is a different thing (it grows with every
  turn and is never trimmed by the agent), it is already shown by
  `\chat-info`, and the header already carries the count of the messages
  (`Mem: N msgs`). Two different "sizes" in one panel would be two
  numbers to reconcile.

* **A graph of the growth.** The panel is a table of numbers, and the
  numbers are what the operator reads.

* **The tokens of the tool schemas separately.** They are part of the
  prompt and they are counted in it — that is what makes the number the
  number that goes on the wire. The log line breaks them out at `DEBUG`
  level; the panel does not.

* **A change of the classic console.** `agent-torvalds.py` has no
  panel. The observer is installed by the multi-window console only.

## The tests

* The observer is called with the size of the prompt and the window of
  the model, during a real run of the agent.
* The observer is called **when the logging is off** — the flag turns
  the log off, not the panel.
* A failing observer does not take the run down.
* The state holds the measurement, and the panel renders it: the tokens,
  the share, the number of messages and the size.
* The row is called **Prompt**, and the share names the window it is a
  share of — the readout says what every number is.
* The share is coloured by the threshold, and an estimated number says
  so (`≈`).
* Before the first measurement the panel shows a dash and not a zero —
  a context of "0 tokens" would be a lie: the size of the prompt is not
  known yet.

Category: Infrastructure
