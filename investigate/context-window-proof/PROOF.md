# The context window the agent reports is the server's

## The question

> can you prove we actually see context window?

The number the agent logs is not a detail — it is the number the prompt
is sized against.  The model advertises its **maximum** context length,
the server usually runs with a much smaller window, and a prompt that
exceeds the real window is truncated **from the front** by the server.
The user request sits at the front of the prompt, so it is the first
thing to go — and the model template then refuses the conversation with
"No user query found in messages.".

So "the context window" has to mean the window the **server** uses.  This
folder proves that it does.

## The evidence

The agent's model, the local Ollama server, and the number the agent
reports:

| | Tokens | Where it comes from |
|---|---:|---|
| The model **advertises** | 262144 | `llm.metadata.context_window` — the maximum the model was trained for |
| The server is **configured** | 8192 | `PARAMETER num_ctx` in the model's Modelfile |
| The server **allocated** | 8192 | `context_length` in `/api/ps` — the running model |
| The **agent reports** | **8192** | `components/ollama_config.py` |

The advertised maximum is **32 times larger** than the window the server
actually uses.  An implementation that logged `llm.metadata.context_window`
would size the prompt for 262144 tokens, and the server would truncate
every prompt that exceeded 8192 — dropping the user request every time.

The number is not the same whichever probe answers it: the running model
(`/api/ps`) and the Modelfile (`num_ctx 8192`) both say 8192, and so
does the agent.

## The invariants

| | Invariant | Caught by |
|---|---|---|
| **P1** | The number the agent reports is the number the **server** uses — the Modelfile's `num_ctx`, and the running model's `context_length`. | dropping the server's probes |
| **P2** | The number the agent reports is **not** the model's advertised maximum. | reporting the advertisement |
| **P3** | The `INFO` log names the size **and** the source it came from. | dropping the size or the source from the log |
| **P4** | The number is **read** from the server, not baked into the code. | hardcoding the number |

## Running it

```bash
self-development/.venv/bin/python self-development/investigate/context-window-proof/verify_context_window.py
self-development/.venv/bin/python self-development/investigate/context-window-proof/verify_harness_catches_regressions.py
```

`replay_the_operator_log.py` replays the log the operator sent with the
request through the new rendering — it is the before-and-after of the
empty lines, on a real prompt.

The first script needs a running Ollama server with the agent's model
available; it says so and exits with 2 when the server is unreachable.
The second script needs the first one.

## What it prints

```
The evidence
----------------------------------------------------------------------
  model                       richardyoung/qwen3.6-27b-abliterated:Q4_K_M
  server                      http://localhost:11434
  the model advertises        262144 tokens
  the server is configured    8192 tokens (num_ctx)
  the running model has       8192 tokens
  the agent reports           8192 tokens (the running model (/api/ps))
----------------------------------------------------------------------

  [PASS] P1  the number is the server's: reported 8192 (the running model (/api/ps)); server num_ctx 8192; running model 8192 — the running model agrees
  [PASS] P2  it is not the advertised maximum: advertised maximum 262144; the agent reports 8192 (253952 tokens smaller)
  [PASS] P3  the log names the size and the source: Context window: 8192 tokens — the running model (/api/ps)
  [PASS] P4  the number is read, not baked in: with the server: 8192; the override: 12345 (the TORVALDS_CONTEXT_LENGTH override); without the server: 262144 (the model's advertised maximum)
```

The `running model` line is `None` when the model is not loaded — the
Ollama server keeps a model in memory for five minutes after the last
request.  The number does not change: the Modelfile says the same
thing, and the source in the log says which probe answered.

## The last invariant is the one that matters

P1, P2 and P3 can be satisfied by a number that happens to be right.
P4 cannot.  It takes the server away and checks that the number
changes:

* with the server: **8192**, from the running model;
* with `TORVALDS_CONTEXT_LENGTH=12345`: **12345**, from the override;
* with the server's probes disabled: **262144**, from the model's
  advertisement.

A hardcoded number would answer 8192 in all three cases.  This one does
not, so the number is read.

## The drift proof

*A check that has never failed proves nothing.*  The second script
introduces four deliberate drifts one at a time, runs the harness after
each, and restores the file:

```
  [OK] the harness passes on the clean tree
  [OK]   P1/P2 — the server's probes are dropped and the advertised maximum is reported: caught (3 invariant(s))
  [OK]   P3 — the log does not carry the size: caught (1 invariant(s))
  [OK]   P3 — the log does not name the source: caught (1 invariant(s))
  [OK]   P4 — the number is hardcoded instead of read: caught (1 invariant(s))
PASS — every deliberate drift is caught.
```

## Where the number is logged

`components/ollama_config.py` — `apply_context_window()`, at the `INFO`
level, at the start of the run:

```
2026-10-27 21:24:03,517 [INFO] components.ollama_config: Context window: 8192 tokens — the running model (/api/ps)
```

and, when the context guard is on, the budget it derives from it:

```
2026-10-27 21:24:03,601 [INFO] components.hitl_agent: Context guard: the context window is 8192 tokens — the prompt may use 6554 of them.
```

## A note on the model in use

The proof runs against the model the agent uses **by default** —
`richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (see `MODEL` in
`agent-torvalds.py`).  It deliberately does **not** read `TORVALDS_MODEL`:
that variable is often pointed at a cloud model
(`minimax-m3.1-flash:cloud`, for instance), and the local Ollama server
knows nothing about it.  `CONTEXT_WINDOW_PROOF_MODEL` names a different
model when one is wanted.
