# Investigation Report: Why the agent stopped when the model server answered 500, and what it should do instead

The operator met a failed request on 2026-11-09 and brought the log:

```
2026-11-09 08:00:29,622 [ERROR] components.event_consumer: EventConsumer.consume_events: exception: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500)
ollama._types.ResponseError: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500)
```

The chat got a sentence that says what happened and what to do about it.
The log got the frames of the agent — twice — and the request was never
sent again.

The operator asked for two things: **the stack trace under the DEBUG
level**, and **a retry after the error**.

**Probe:** [`probe_server_500.py`](probe_server_500.py) — read-only, prints
what the log holds after one failed request, whether the request is worth
sending again, and how many times it is sent. The model server is
replaced by a fake client that fails the way the real one failed; the
probe talks to no server and writes nothing.

---

## 1. The question

What does the agent do with a failure of the **model server**, and what
should it do with it?

The question is asked in the words of the operator, because that is where
the defect is: the agent stopped. The server had failed, the request was
fine, and a request that is fine is worth sending again.

## 2. The measurement

The probe was run on the code as it was, before the change:

```
==============================================================================
1. WHAT THE LOG HOLDS AFTER ONE FAILED REQUEST
==============================================================================

--- every record the log received ---
  DEBUG    components.event_consumer    no frames    EventConsumer.__init__: spinner=<components.spinner_controller.Spinner
  DEBUG    components.event_consumer    no frames    EventConsumer.__init__: initialized successfully
  DEBUG    components.event_consumer    no frames    EventConsumer.consume_events: handler=<__main__.FailingHandler object
  DEBUG    components.event_consumer    no frames    EventConsumer.consume_events: getting final result from handler
  ERROR    components.event_consumer    with frames  EventConsumer.consume_events: exception: Internal Server Error (ref: b
  ERROR    components.llm_errors        with frames  The request failed: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7c

  records in total              : 6
  records carrying the frames   : 2
  ... of them at ERROR or above : 2

==============================================================================
3. HOW MANY TIMES IS THE REQUEST SENT?
==============================================================================
  the LLM of the agent         : Ollama (no retry)
  the request failed           : Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500) (status code: 500)
  requests sent to the server  : 1
  the request answered          : False
```

Three numbers carry the answer:

| Measurement | Before | After |
|---|---|---|
| Records carrying the frames of the agent | 2 | 2 |
| ... of them at ERROR or above | **2** | **0** |
| Requests sent to the server | **1** | **2** |
| The request answered | **no** | **yes** |

And the question of whether the request was worth sending again — asked
of the code as it was, with a server that has recovered:

```
==============================================================================
2. IS THE REQUEST WORTH SENDING AGAIN?
==============================================================================
  the first attempt failed     : ResponseError: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500) (status code: 500)
  the second attempt answered  : 'the model answered'
  requests sent to the server  : 2
```

**The request is worth sending again.** The very same request, to a
server that has recovered, works. The agent sent it once and gave up.

## 3. The root cause

There are two defects, and they are separate.

**The frames are written twice, at the ERROR level.**
`components/event_consumer.py` logged the failure with `exc_info=True`,
and `components/llm_errors.py` logged the same failure with `exc_info=exc`.
Two records, two copies of the same thirty frames, both at the level that
says *"something is wrong and the operator has to look"*. The frames say
where the failure happened **inside the agent** — they are of no use to
anybody who did not write the agent, and they bury the one line that
matters: what the server said.

**The request is never sent again.**
The failure of the server ended the request. `ollama._client` raises
`ResponseError` when the status is not a success, the exception travels
up through `FunctionAgent.take_step` → the workflow runner → the event
consumer → the orchestrator, and nothing in that path asks whether the
failure is worth another attempt. A 500 from Ollama means *the model
died* — usually out of memory, or a crash while it was loading. The
server serves the next request; the agent does not make one.

The two failures that must **not** be retried are the failures of the
*request*: a prompt that was too long (400), a model that is not pulled
(404), a key that is wrong (401). Those fail the same way every time, and
retrying them only makes the failure slower.

## 4. The fix

**The frames move to the DEBUG level** (`components/llm_errors.py`,
`components/event_consumer.py`). The ERROR record keeps the message —
*"The request failed: Internal Server Error (ref: …) (status code: 500)"* —
and the frames are written as a second record, under the DEBUG level,
where they are found when they are looked for and stay out of the way
when they are not.

**The request is sent again** (`components/llm_retry.py`). The new
module tells the two kinds of failure apart:

| The failure | Retried? | Why |
|---|---|---|
| 500, 502, 503, 504, 429, 408 | yes | the server, not the request |
| a connection that never came about | yes | the server was not there |
| a server that did not answer in time | yes | it may be loading the model |
| 400, 401, 403, 404 | no | the request will fail the same way |
| an error in the body of the response | no | the server answered, and it said why |

`RetryingOllama` is the LLM of the agent with that rule: it wraps
`astream_chat` and `achat`, and sends the request again when the failure
passes. The retry is bounded by `llm.max_retries` (2 by default) and
waits `llm.retry_delay` seconds before the first attempt again — 2, 4 and
8 seconds with the default, because the wait grows with every attempt.

The retry is around the **request**, not around the run: the tools that
already ran are not run again, the conversation is not lost, and the
answer of the attempt that works is the answer of the request.

One thing had to change for the wording to stay right.
`provider_of_the_llm()` looked at the module of the class of the LLM, and
`RetryingOllama` lives in a module of its own — the failure would have
been described as *"The model server failed"* instead of *"The Ollama
server failed"*. The whole line of ancestors of the LLM is looked at
now, so a subclass of the LLM of a provider is still that provider.

## 5. Verification

The probe, run again on the code as it is now:

```
==============================================================================
1. WHAT THE LOG HOLDS AFTER ONE FAILED REQUEST
==============================================================================

--- every record the log received ---
  DEBUG    components.event_consumer    no frames    EventConsumer.__init__: spinner=<components.spinner_controller.Spinner
  DEBUG    components.event_consumer    no frames    EventConsumer.__init__: initialized successfully
  DEBUG    components.event_consumer    no frames    EventConsumer.consume_events: handler=<__main__.FailingHandler object
  DEBUG    components.event_consumer    no frames    EventConsumer.consume_events: getting final result from handler
  ERROR    components.event_consumer    no frames    EventConsumer.consume_events: exception: Internal Server Error (ref: b
  DEBUG    components.event_consumer    with frames  EventConsumer.consume_events: the frames of the failure:
  ERROR    components.llm_errors        no frames    The request failed: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7c
  DEBUG    components.llm_errors        with frames  The request failed — the frames of the agent:

  records in total              : 8
  records carrying the frames   : 2
  ... of them at ERROR or above : 0

==============================================================================
3. HOW MANY TIMES IS THE REQUEST SENT?
==============================================================================
  the LLM of the agent         : RetryingOllama
  requests sent to the server  : 2
  the request answered          : True
```

The frames are still in the log — under the DEBUG level, where they
belong. The ERROR records hold the message alone. The request is sent
again, and the run answers.

The suite that proves it is `tests/test_llm_retry.py` (26 tests): the
classification of the failures, the retry itself, the bound on the
number of attempts, the wording of the failure, and the level of the
frames. The gate is green:

```
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
```

## 6. What is *not* in this change, and why

- **The failure of the model server is not fixed.** The agent cannot
  repair a model that ran out of memory; only the operator can, with a
  smaller model or with more memory. The retry hides a stumble of the
  server — it does not make the server fit in the memory.
- **The synchronous paths of the LLM are not retried.** The agent talks
  to the model through `astream_chat` and `achat`; `chat()`,
  `stream_chat()` and the completion API are not used by the agent, and
  they are left alone.
- **The request is not shortened.** A prompt that is too long is a
  failure of the request, and the context guard
  (`components/context_guard.py`) is what deals with it.
- **The frames are not removed.** They are the frames of the agent, and
  they are what the operator needs when the agent itself is at fault.
  They are under the DEBUG level, and the operator asks for them with
  `--log-level DEBUG`.
- **The tools are not run again.** The retry is around the request. A
  tool that writes to the disk is not run a second time, because the
  step that failed was the step that asked the model, and the tools of
  the earlier steps had already succeeded.
- **A stream that failed half way through is streamed again.** The
  tokens that were already sent are sent again with it, so the live
  display of the multi-window agent shows them twice. The **answer** is
  not affected: it is the message of the attempt that worked. The
  failure of the report came before the first token — the status is
  checked when the stream starts — so there was nothing to show twice.
- **The count of the requests counts the attempts.** The statistics of a
  request that was sent again report two LLM calls, because two
  requests were made. The tokens are counted as they were used: the
  failed attempt used none.

## 7. The recommendation to the operator

The retry is **on** by default: two attempts again, 2 and 4 seconds
after the first one, and 8 seconds before the last attempt. The chat
still says what the server said — the frames were never in the chat.

If the model of the server runs out of memory on every request, the
retry will not help: the failure will come back three times, and the
chat will say the same thing. That is the signal to give the model
less memory to want:

```bash
ollama ps        # what is resident
ollama stop <model>   # unload it, and free the memory
```

To turn the retry off:

```toml
[llm]
max_retries = 0
```

To wait longer between the attempts — the server is busy, not broken:

```toml
[llm]
retry_delay = 10
```
