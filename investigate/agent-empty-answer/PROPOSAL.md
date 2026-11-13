# Proposal: the agent must never answer in silence

**Status:** implemented — the investigation is in
[`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md), and the change
that follows it is written: see
[`IMPLEMENTATION_REPORT.md`](IMPLEMENTATION_REPORT.md).

## What was asked

The operator kept a log of a session of 2026-11-13
(`~/torvald-log/agent-torvalds-misbehavior.md`) in which the agent worked
for three minutes and answered nothing at all, twice, and answered with a
promise the third time.

## What the investigation found

Two defects, one behind the other:

1. the answer of the model reaches the screen through `str(AgentOutput)`,
   which returns the **text** of the answer and nothing else — the
   `thinking` block of the model is dropped there, and an answer with
   nothing but a thinking prints **nothing at all**;
2. the run ends on the first turn without a tool call, whatever the model
   says in it — including a sentence that promises work instead of doing
   it.

A third, measured on the side: the context window the agent sends is the
**advertised maximum** of the model, not the window of the server, and
the server answers by pushing the model off the GPU (3.09 GB of VRAM
instead of 6.64 GB, measured).

## What is proposed

One branch, one pull request, three changes:

| # | change | where |
|---|---|---|
| a | the answer on the screen is built with `to_output_string()`, and an empty answer says so | `agent-torvalds-mw.py`, `agent-torvalds.py`, `agent-torvalds-cpp.py` |
| b | a turn with neither text nor a tool call does not end the run: the agent asks again once, and then reports plainly | `components/hitl_agent.py` |
| c | the window the agent sends is the window of the server, or a configured default — never the advertised maximum | `components/ollama_config.py` |

## What it costs

* (a) and (b): the renderer (`components/chat_message.py`) and the guard
  (`components/tui/tui_app.py`) are already written — this is a matter of
  using them where they are missing.
* (c): one fallback branch in one function.

## What was done

All three changes are written, and the tests of the proposal are green:

| # | change | where | verified by |
|---|---|---|---|
| a | the answer on the screen is built with `to_answer_string()`, and an empty answer says so | `agent-torvalds-mw.py`, `agent-torvalds.py`, `agent-torvalds-cpp.py`, `components/chat_message.py` | `tests/test_silent_turn.py` |
| b | a turn with neither text nor a tool call does not end the run: the agent asks again once, and then reports plainly | `components/hitl_agent.py` | `tests/test_silent_turn.py` |
| c | the window the agent sends is the window of the server, or a configured default — never the advertised maximum | `components/ollama_config.py` | `tests/test_ollama_context_window.py` |

## What is not proposed

* A change of the memory buffer of the branch — it was measured and it is
  not the cause.
* A change of the tools, of the model, or of the prompt.
* Any attempt to explain the empty turn of the model build that served
  the session: the build is gone, and the evidence that is left does not
  separate the remaining candidates.
