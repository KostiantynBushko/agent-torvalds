# Proposal: a failed model request is sent again, and the frames of the agent are written under the DEBUG level

**Written:** 2026-11-09, before the work.

## The problem

The agent stopped when the model server answered **500**. The failure of
the report:

```
2026-11-09 08:00:29,622 [ERROR] components.event_consumer: EventConsumer.consume_events: exception: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500)
```

A 500 from Ollama means the **model died** — out of memory, or a crash
while it was loading. The request was fine. The agent sent it once and
gave up, and the operator was left with a sentence that says what
happened and nothing more.

The log got the frames of the agent **twice**, both at the ERROR level:
once from `components/event_consumer.py` and once from
`components/llm_errors.py`, both with `exc_info=True`. The frames say
where the failure happened *inside the agent*; they bury the one line
that matters, which is what the server said.

## What is proposed

1. **The frames are written under the DEBUG level.** The ERROR record
   keeps the message — what failed, in one line — and a second record
   under the DEBUG level carries the frames. The operator asks for them
   with `--log-level DEBUG`, and they are there.

2. **The request is sent again when the failure is worth it.** A new
   module, `components/llm_retry.py`, tells the two kinds of failure
   apart:

   - the **server** failed (500, 502, 503, 504, 429, 408, a connection
     that never came about, a server that did not answer in time) — the
     request is sent again;
   - the **request** failed (400, 401, 403, 404, an error in the body of
     the response) — it is not, because it will fail the same way.

   The retry is around the **request**: the tools that already ran are
   not run again, and the conversation is not lost.

3. **The retry is bounded and it is a setting.** `llm.max_retries`
   (2 by default) and `llm.retry_delay` (2 seconds by default), both in
   the configuration file and both with an environment variable. The wait
   grows with every attempt.

## What is *not* proposed

- Repairing the model server. The agent cannot give a model the memory
  it wants; the operator does that with `ollama ps` and `ollama stop`.
- Retrying the synchronous paths of the LLM, which the agent does not
  use.
- Retrying a failure of the request.

## The evidence

[`probe_server_500.py`](probe_server_500.py) — read-only. The numbers it
printed are in [`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md).
