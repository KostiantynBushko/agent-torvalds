# INVESTIGATION REPORT: Unified Voice Interface for the Torvalds Agent

**Subject:** Can `agent-torvalds` be given a unified interface that lets it produce voice instead of only text, using the local `audio.cpp` stack?
**Date:** 2026-10-22
**Investigated by:** Torvalds (self-development session)
**Status:** Investigation complete — proposal follows in `PROPOSAL_voice_output.md`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Scope and Method](#2-scope-and-method)
3. [Part A — The `audio.cpp` Stack](#3-part-a--the-audiocpp-stack)
4. [Part B — The `agent-torvalds` Codebase](#4-part-b--the-agent-torvalds-codebase)
5. [Part C — Gap Analysis](#5-part-c--gap-analysis)
6. [Integration Surface Options](#6-integration-surface-options)
7. [Empirical Validation](#7-empirical-validation)
8. [Risk Register](#8-risk-register)
9. [Conclusion](#9-conclusion)

---

## 1. Executive Summary

**The request has a favourable answer, and the two halves already exist on this machine.**

`text-to-speach/audio.cpp` is a fully built, CUDA-enabled local audio inference
framework (v0.8.0, 80+ model families) with a REST server, a CLI, a C ABI and an
embedded WebUI. The TTS models are already downloaded to `models/TTS/`. The
`agent-torvalds` codebase is a LlamaIndex `FunctionAgent` orchestrator with two
front ends (classic REPL and a multi-window TUI) and a strict, well-documented
toolkit pattern.

**What is missing is only the seam between them.** The agent has *no* audio
capability at all today — a grep for `tts|speech|audio|voice` across the
repository returns exactly two hits, both of them incidental mentions inside a
proposal document. There is no toolkit, no adapter, no config, no command, no
test.

Three findings shape the proposal:

1. **The synthesis side is solved and fast.** Kokoro 82M on this RTX 4060
   measured **RTF 0.069 (14.4× faster than real time)** — a 3.1-second
   utterance rendered in 213 ms of wall time. Even the heavy models
   (MagpieTTS 1.9 GB, OmniVoice 1.2 GB + tokenizer) fit the 7.3 GB of free
   VRAM, because the LLM (a 27B Q4_K_M served by Ollama) does **not** live on
   this GPU. There is no GPU contention.

2. **The hard part is not synthesis — it is the *interface*.** "Produce voice
   instead of only text" is three different capabilities (speak the response,
   speak mid-workflow, speak *to* the agent) with three different triggers,
   three different transports and three different failure modes. Folding them
   into one monolithic feature is the main risk. The proposal therefore
   decomposes the feature along **three orthogonal axes** — *trigger*,
   *backend*, *output* — so that each capability is a configuration of a small
   shared core rather than a separate subsystem.

3. **Text is not speech.** The agent's answers are Markdown, rendered through
   `rich.markdown`. Speaking that raw would read "hash hash" for every
   heading, spell out code fences and mispronounce URLs. A Markdown→speakable
   text converter plus a sentence-aware chunker is a mandatory, non-obvious
   component of the feature, not an afterthought.

**Recommendation:** build the voice subsystem as a standard toolkit
(`toolkits/audio-toolkit/` + `agent_voice_toolkit.py`), add a
`VoiceSessionManager` in `components/voice/`, and default the HTTP backend
against `audiocpp_server`, which is already built and already keeps the model
warm between requests. The C ABI is a genuine option but requires a rebuild
with `-DAUDIOCPP_BUILD_C_API=ON` (off by default), so it belongs in a later
phase. The feature stays **opt-in** (`TORVALDS_VOICE_ENABLED=1`) and must
never break the agent boot when audio.cpp is absent.

---

## 2. Scope and Method

Two repositories were inspected read-only. The self-development rules
(`SELF_DEVELOPMENT_RULES.md`, Rules 1–2) forbid writing to the main checkout, so
this report and the accompanying proposal live under
`self-development/investigate/Voice-Output/`.

| Path | Role in the investigation |
|---|---|
| `~/ai-agent-investiagte/text-to-speach/audio.cpp` | The audio inference framework (the *engine* side) |
| `~/ai-agent-investiagte/models/TTS/` | Locally downloaded TTS weights (Kokoro, MagpieTTS, OmniVoice) |
| `~/ai-agent-investiagte/agent-torvalds/` | The agent (the *consumer* side) |
| `~/ai-agent-investiagte/agent-torvalds/self-development/` | Where this report and the proposal are written |

**Method.** Static reading of both code bases against the repository's own
conventions; then empirical validation — the `audio.cpp` CLI and HTTP server
were actually built, started and exercised on this host to measure real
latency, real VRAM use and real failure behaviour. Every number quoted in
§7 was measured here, not quoted from upstream documentation.

---

## 3. Part A — The `audio.cpp` Stack

### 3.1 What it is

`audio.cpp` is a C++ audio inference framework built on `ggml`, positioned as a
native, dependency-light replacement for the "a dozen Conda environments"
approach to local audio models. It covers far more than TTS:

| Task family | Examples | Relevant here |
|---|---|---|
| **TTS** | Kokoro 82M, MagpieTTS, OmniVoice, Qwen3-TTS, VoxCPM2, Supertonic, Chatterbox | **Yes — the core need** |
| **Clone / Design** | zero-shot cloning, voice design, emotion control | Yes — the "Torvalds voice" |
| **ASR** | Qwen3-ASR, Whisper-class, SenseVoice, Parakeet-TDT | Yes — the *input* direction |
| **VC** | SeedVC, RVC, MeanVC2 | Maybe — voice conversion |
| **VAD / Align / Diar** | Silero VAD, MMS aligner, Sortformer | Maybe — turn detection, subtitles |

The framework is organised as a shared runtime (`engine::runtime`) with a
`ModelRegistry` → `ILoadedVoiceModel` → `IVoiceTaskSession` chain. Every
integration surface (CLI, server, C ABI) is a thin adapter over that same
chain, which is what makes it safe to pick any of them.

### 3.2 The four integration surfaces

| Surface | What it is | Cost to adopt | Notes |
|---|---|---|---|
| **`audiocpp_cli`** | Batch-oriented command line | Zero — already built | One process per utterance; pays model load each time unless `--request-sequence` is used |
| **`audiocpp_server`** | HTTP server over the runtime registry | Zero — already built | **Keeps the model and session warm** between requests. The obvious default. |
| **`libaudiocpp` (C ABI)** | `extern "C"` facade, ABI 0.2.0, 69 symbols | **Requires a rebuild** (`-DAUDIOCPP_BUILD_C_API=ON`, off by default; only static `.a` archives exist today) | Lowest latency, in-process, no HTTP hop. But: a build-step prerequisite, a ctypes marshalling surface, and manual handle-lifetime rules. |
| **Embedded WebUI** | SvelteKit/TypeScript compiled into the server | n/a | Browser-facing; not an agent integration surface |

The C ABI is the technically most elegant option (it is explicitly designed for
embedding: opaque handles, no exceptions crossing the boundary, borrowed
pointers), but it is gated behind a non-default build option. A proposal that
requires a C++ rebuild of a third-party project to deliver a *voice* feature to
a *Python* agent is a proposal with a worse cost/benefit ratio than one that
talks HTTP to a binary that is already running.

### 3.3 The HTTP API (the surface that matters)

`audiocpp_server` exposes an OpenAI-compatible set of routes:

| Route | Purpose |
|---|---|
| `GET /health` | Readiness + configured model count |
| `GET /v1/models` | OpenAI-style model list (id, family, task, mode, loaded, path) |
| `GET /v1/audio/voices?model=<id>` | **Voice catalogue** — cached voice ids, configured presets, `voice_dir` names |
| `POST /v1/audio/speech` | **TTS.** `audio/wav` by default; `response_format: json` → base64; `mp3` with the optional frontend module; SSE streaming for `mode: streaming` models |
| `POST /v1/audio/transcriptions` | ASR. JSON path or `multipart/form-data` upload; optional SSE |
| `POST /v1/audio/transcriptions/details` | ASR + word timestamps / speaker turns / segments |
| `POST /v1/audio/alignments` | Forced alignment (word timings) |
| `POST /v1/tasks/run` | Generic task route, same JSON shape as the CLI request sequence |
| `POST /v1/tasks/unload_models`, `/unload_all_models` | Free VRAM on demand |

The TTS request body is exactly the OpenAI speech shape, with audio.cpp
extensions:

```json
{
  "model": "kokoro",
  "input": "text to speak",
  "voice": "af_heart",
  "voice_ref": { "type": "base64", "data": "UklGRh..." },
  "reference_text": "transcript of the reference audio",
  "response_format": "wav",
  "max_tokens": 96,
  "seed": 1234
}
```

Voice resolution precedence is well-defined: `voice_ref` wins, then a
configured `voice_preset`, then a `voice_dir` library name, then the
model-native cached voice id. `voice_ref` accepts a path *or* an inline
base64 payload (≤ 5 MiB), so a client that cannot stage a file on the server
still works.

**Server-side policy that matters for an agent:**

- `lazy_load: true` — models are registered at startup, loaded on first use.
- `max_loaded_models` — bounds resident VRAM; the least-recently-used idle
  model is evicted to make room.
- `idle_unload_ms` — frees VRAM after a quiet period.
- `busy_timeout_ms` — a request that would wait behind a running inference
  fails fast with `503 server_busy` instead of parking forever. The effective
  bound is `min(request, model ceiling, server default)` — a client can
  shorten its own wait but never weaken the guard.
- `min_free_memory_mb` — refuses a model load that would leave the host or GPU
  short of memory, returning `503 insufficient_memory`.

These are exactly the knobs an agent integration needs: the agent must be able
to fail *loudly and quickly* rather than hang a user turn.

### 3.4 The CLI

```
audiocpp_cli --task <task> --family <family> --model <path> --backend <backend> [options]
```

TTS-relevant options: `--voice-id`, `--language`, `--text`, `--out`,
`--metrics`, `--load-option/--session-option/--request-option key=value`,
`--request-sequence <json>` (multi-request in one warm session),
`--batch-text-file <txt>` (one request per line, one warm session),
`--batch-text-dir`, `--pipeline <json>` (multi-step workflows),
`--inspect` (discover configs/weights/capabilities of a model),
`--list-loaders --json` (machine-readable family contract).

`--request-sequence` and `--batch-text-file` matter: they let **one** process
serve **many** utterances against a **warm** session, which is exactly the
access pattern an agent wants for a multi-turn conversation.

### 3.5 Local inventory (this host)

**Build present and working:**

```
text-to-speach/audio.cpp/build/linux-cuda-release/bin/audiocpp_cli
text-to-speach/audio.cpp/build/linux-cuda-release/bin/audiocpp_server
```

CUDA backend, 1 device, CUDA 13.3 driver. Built artifacts are **static
archives only** (`libengine_runtime.a`, `libggml-cuda.a`, …) — there is no
`libaudiocpp.so`, confirming that the C ABI route needs a rebuild.

**TTS weights already on disk (`models/TTS/`, 4.2 GB total):**

| Model | Size | Family | Notes |
|---|---|---|---|
| `kokoro-82m-bf16.gguf` | 212 MB | `kokoro_tts` | 54 preset voices, 9 languages, tiny, fast |
| `magpie-tts-multilingual-357m-orig.gguf` | 1.9 GB | `magpie_tts` | 18 languages, baked speaker prompts |
| `omnivoice/` (`omnivoice-base-BF16.gguf` + tokenizer + audio tokenizer) | 1.2 GB + | `omnivoice` | Qwen3-0.6B based, 646+ languages, **streaming** |
| `mms-forced-aligner-f16.gguf` | 631 MB | `mms_forced_aligner` | Word timestamps (useful for subtitles, not voice) |

**Also present:** `models/embedding/all-MiniLM-L6-v2` (retriever embeddings),
`models/lapa-llm/` (15 GB), `models/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf`.

**Host capabilities relevant to voice:**

| Capability | State |
|---|---|
| GPU | NVIDIA RTX 4060 Laptop, **8188 MiB total**, 7.3 GB free |
| LLM residency | Ollama `serve` running, `/api/ps` **empty** — no model resident |
| Chat model | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (~16 GB at Q4) → **cannot** fit 8 GB VRAM → runs mostly on CPU |
| **GPU contention with the LLM** | **None.** The GPU is free for TTS. |
| Playback | `ffplay` ✅, `ffmpeg` ✅, `aplay` ✅ · `paplay` ❌, `sox` ❌, `mpv` ❌, `cvlc` ❌ |
| Python audio libs | `sounddevice` ❌, `pyaudio` ❌ — **not** installed in either venv |
| Agent venv HTTP | `requests 2.34.2` ✅, `httpx 0.28.1` ✅, `aiohttp 3.14.5` ✅ |

The absence of `sounddevice`/`pyaudio` is not a blocker: `ffplay` is the
better-constrained option anyway (it handles format conversion, and `-nodisp`
keeps it from touching the terminal the TUI owns).

---

## 4. Part B — The `agent-torvalds` Codebase

### 4.1 Orchestrator topology

Two front ends share one core:

| File | Lines | Mode |
|---|---|---|
| `agent-torvalds.py` | 1323 | Classic linear REPL. `console.input()` loop, Rich-rendered output. |
| `agent-torvalds-mw.py` | 1409 | Multi-window TUI. Background asyncio task + Rich Live render loop; falls back to the classic REPL via `--no-tui` or in headless/piped environments. |

Both are built on the same primitives:

- **LLM** — `Ollama` (local, `get_ollama_base_url()`), `temperature=0.0`.
- **Agent** — `HITLFunctionAgent` (a `FunctionAgent` subclass) with
  `max_iterations=50`, a `ChatMemoryBuffer` from `agent_chat_memory.py`
  (PostgreSQL-backed with in-memory fallback), and runtime prompt injection
  from `project_manager/prompt_engine.py`.
- **Tool loading** — three modes: default (on-demand retriever, top-k=8 via
  `agent_tool_retriever.py`), `--full` (all tools upfront), `--select`
  (interactive category picker via `agent_tool_selection.py`).
- **Event stream** — `components/event_consumer.py` (957 lines) turns the
  LlamaIndex workflow event stream into console output, drives the spinner,
  feeds the stats handler and mediates HITL.
- **HITL** — `components/human_loop_handler.py`, `hitl_agent.py`,
  `hitl_events.py`, `timeout_manager.py`, `hitl_timeout.py` (no-timeout by
  default), `hitl_runtime_toggle.py`.

### 4.2 The response path — where a voice hook belongs

This is the single most important structural fact for the feature.

```
user input
   │
   ├─► prompt_handler(cmd, agent, ...)                       agent-torvalds.py:772
   │      │
   │      ├─ builds CallbackManager (stats + human_loop_handler)
   │      ├─ agent.run(cmd, memory=..., max_iterations=...)
   │      └─ event_consumer.consume_events(workflow_handler, cmd)
   │             └─ returns result["output"]  →  response_text
   │
   ├─► response, stats = await prompt_handler(...)
   │
   ├─► console.rule("[blue]Agent Response[/blue]")
   ├─► console.print(Markdown(response))        ◄── THE RENDER POINT
   └─► stats_renderer.render(stats)
```

In the TUI the same `prompt_handler` is awaited by `TuiApp._execute_agent_query`
(`components/tui/tui_app.py:363`), which writes the result into
`TuiState.markdown_content`; `components/tui/markdown_view.py` renders it.

**Consequence:** the natural, single, framework-agnostic place to inject voice
is *after* `prompt_handler` returns the final text and *before/alongside* the
render. Both front ends converge on that one value, so one hook covers both.

### 4.3 The toolkit pattern (the mandatory conformance target)

The repository enforces a strict, well-documented pattern (established by the
MikroTik RouterOS and Shodan toolkits, and specified in
`investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md`):

```
toolkits/<hyphenated-name>/      # core library — imports NO LlamaIndex code
    src/… or flat package
agent_<name>_toolkit.py          # LlamaIndex adapter — the ONLY LlamaIndex-aware file
```

The adapter rules, restated from `agent_mikrotik_toolkit.py` and
`agent_shodan_toolkit.py`:

1. **Category tag** — the module docstring ends with `Category: <Name>`, and
   the tool descriptions carry the same tag. `agent_tool_selection._extract_category()`
   parses it to build the `--select` menu.
2. **Retriever keywords** — a `Retriever Keywords: …` line drives on-demand
   tool retrieval.
3. **Structured errors, never exceptions** — a tool returns
   `{"ok": False, "error": "<MACHINE_CODE>", …}` instead of raising, so the
   model can react to a failure rather than read a traceback.
4. **Guarded import** — the core package is imported inside `try/except`; a
   missing optional dependency degrades the toolkit to "unavailable", and must
   never break the agent boot.
5. **Opt-in for mutating capabilities** — a single env var, read by the
   adapter itself, so every load path (retriever, `--select`, both
   orchestrators) behaves identically.
6. **No re-implementation** — the adapter re-uses the core functions verbatim
   and only rewrites descriptions.

### 4.4 Configuration conventions

| Mechanism | Pattern | Example |
|---|---|---|
| Environment | `TORVALDS_<FEATURE>_<KEY>`, read at module import | `TORVALDS_HITL_ENABLED`, `TORVALDS_MODEL` |
| CLI flag | mirrors the env var, overrides it | `--hitl-timeout` |
| Boolean | `os.environ.get(..., "true").lower() in ("true","1","yes")` | — |
| Endpoint | `components/ollama_config.py` resolves `TORVALDS_OLLAMA_HOST` → `OLLAMA_HOST` → `http://localhost:11434` | — |

The precedent for a *separate* small config module (`components/ollama_config.py`)
is exactly right for a voice endpoint, which has the same "which host / which
port / which model" shape.

### 4.5 Command surface conventions

`components/command_registry.py` is the single source of truth for interactive
commands: a `COMMAND_SPECS` tuple of frozen `CommandSpec(name, description,
usage, category, aliases, feature)`, with feature flags
(`FEATURE_HITL`, `FEATURE_CHAT_HISTORY`, `FEATURE_PROJECT_MANAGER`,
`FEATURE_MIKROTIK`, `FEATURE_TUI`) gating visibility. Both orchestrators render
`\help` from it, so the help screen cannot drift from reality.

Any new interactive command — `\voice`, `\voices`, `\speak` — **must** be
registered here.

### 4.6 Gap summary

| Capability | Status in `agent-torvalds` |
|---|---|
| TTS / speech synthesis | **Absent** |
| ASR / speech input | **Absent** |
| Voice catalogue | **Absent** |
| Playback / audio output | **Absent** |
| Voice-related config, env vars, CLI flags | **Absent** |
| Voice-related commands | **Absent** |
| Voice-related tests | **Absent** |
| Toolkit slot for it | `toolkits/` has 2 entries; `agent_voice_toolkit.py` does not exist |
| Retriever / `--select` integration points | Not wired |

---

## 5. Part C — Gap Analysis

"Produce voice instead of only text" bundles three genuinely different
capabilities. Treating them as one feature is the primary risk of this work.

| # | Capability | Trigger | Direction | Complexity |
|---|---|---|---|---|
| **A** | **Speak the answer** — the agent's response is spoken | End of every turn | Out | **Low.** One hook after `prompt_handler`. |
| **B** | **Speak mid-workflow** — the agent announces progress, warnings, confirmations | LLM decides to call a tool | Out | **Low.** One more `FunctionTool`. |
| **C** | **Speak *to* the agent** — the user dictates, the agent answers aloud | Continuous | In + Out | **High.** Needs mic capture, VAD/turn detection, ASR, barge-in, and a different UI mode. |

Capability **C** is a different product (a voice assistant), not a different
implementation of the same one. It deserves its own proposal. This proposal
delivers **A** and **B** behind one interface, and designs the interface so
that **C** can be added later without a rewrite.

### 5.1 The three axes of the interface

The proposal's core idea: the voice feature is the **cartesian product of
three independent axes**, not a single switch.

```
TRIGGER   ×   BACKEND   ×   OUTPUT
```

| Axis | Values | Meaning |
|---|---|---|
| **Trigger** | `never` · `on_response` · `announce` | *When* speech is produced |
| **Backend** | `none` · `http` · `cli` · `cabi` | *How* it is synthesized |
| **Output** | `none` · `speaker` · `file` | *Where* the audio goes |

Capability A is `trigger=on_response`. Capability B is `trigger=announce` plus
the `speak_text` tool. Capability C adds a fourth trigger (`on_speech_input`)
and a new input axis, but changes nothing else.

This decomposition is what makes the feature *unified*: one config object, one
manager, one tool surface, and every capability is a value of an enum rather
than a separate subsystem.

### 5.2 The three things that are genuinely hard

**(1) Markdown is not speakable text.**
The agent's output is Markdown. Read verbatim it says "hash hash" for every
heading, "asterisk asterisk" for bold, spells out fenced code, and
mispronounces URLs and file paths. A `to_speakable_text()` converter is
mandatory:

- strip fenced code blocks entirely (or replace with a one-line cue);
- strip inline emphasis markers, keeping the emphasised words;
- convert headings to plain sentences (no "hash");
- flatten bullet lists into sentences;
- rewrite URLs as "link" (or drop them);
- collapse whitespace, normalise Unicode punctuation (em-dash → comma).

**(2) Long text must be chunked, and chunks must be merged.**
Agent answers routinely run to thousands of characters. Kokoro's documented
request option `text_chunk_size` defaults to 240 codepoints, but the *model
loader* still needs a sensible input length, and the HTTP route takes one
`input` string. The interface therefore needs sentence-aware chunking
(split on `.!?…` boundaries, pack chunks under a limit, never split a
sentence) and a WAV concat step. The CLI backend gets this for free via
`--batch-text-file`; the HTTP backend needs it in the toolkit.

**(3) Voice must not block, and must be interruptible.**
In the TUI, the agent workflow runs as a background asyncio task while the
render loop runs concurrently. Synthesis plus playback must happen off the
event loop, and the user must be able to interrupt playback (barge-in) — which
means the playback subprocess handle must be retained and killable, not
fire-and-forget.

---

## 6. Integration Surface Options

### 6.1 Backend comparison for the agent

| Criterion | `http` (audiocpp_server) | `cli` (audiocpp_cli) | `cabi` (libaudiocpp) |
|---|---|---|---|
| Already available on this host | ✅ **yes** | ✅ **yes** | ❌ needs `-DAUDIOCPP_BUILD_C_API=ON` rebuild |
| Model stays warm between turns | ✅ server keeps the session | ⚠️ only via `--request-sequence` / `--batch-text-file` | ✅ in-process |
| Per-request latency | + HTTP hop (negligible: RTF 0.07) | + process start (~200–400 ms) | lowest |
| Voice catalogue | ✅ `GET /v1/audio/voices` | ⚠️ `--inspect` (model-local) | ✅ model introspection |
| Streaming TTS | ✅ SSE for `mode: streaming` models | ❌ | ⚠️ `audiocpp_stream_start` exists |
| Long-text chunking | ⚠️ ours to implement | ✅ built in | ⚠️ ours |
| Failure modes | `503` (busy / insufficient memory) | non-zero exit + stderr | `audiocpp_status` codes |
| Blast radius if it breaks | server process only | subprocess only | agent process (segfault risk) |
| Python surface | `requests`/`httpx` (present ✅) | `subprocess` | `ctypes` (new) |

### 6.2 Decision

**Default: `http`.** It is already built, already running-capable, keeps the
model warm, exposes a voice catalogue, has explicit busy/memory semantics, and
fails without taking the agent down.

**`cli` as the fallback** for operators who do not want a long-lived server,
and as the escape hatch when the HTTP route is unavailable. It also has the
best long-text story (built-in batch mode).

**`cabi` deferred to a later phase.** It is the right long-term answer for
latency and for avoiding a second process, but it carries a C++ rebuild
prerequisite and a ctypes marshalling surface with manual handle-lifetime
rules. It is worth a phase-3 spike, not a phase-1 dependency.

### 6.3 Output sink comparison

| Sink | Mechanism | Interruption | Use |
|---|---|---|---|
| `speaker` | `ffplay -nodisp -autoexit -loglevel quiet <wav>` | ✅ keep the `Popen`, `terminate()` | Default on a workstation |
| `file` | write WAV into `TORVALDS_VOICE_DIR` | n/a | Headless / SSH sessions; also the fallback when no audio device exists |
| `none` | synthesize and discard | n/a | Diagnostics; measuring latency without noise |

`ffplay` is preferred over `aplay` because it decodes any format and
`-nodisp` guarantees it will not fight the TUI for the terminal. `aplay` is the
fallback for a pure-ALSA host.

**Degradation rule:** if no playback device is available (SSH, container
without `/dev/snd`), the sink must fall back to `file` and *say so* rather than
fail the turn.

---

## 7. Empirical Validation

All measurements on this host, 2026-10-22, CUDA backend, RTX 4060 Laptop.

### 7.1 CLI — Kokoro 82M, single utterance

```bash
audiocpp_cli --task tts --family kokoro_tts \
  --model ~/ai-agent-investiagte/models/TTS/kokoro-82m-bf16.gguf \
  --backend cuda --text "Torvalds agent, voice interface operational." \
  --out /tmp/kokoro_test.wav --metrics
```

```
metrics.wall_ms=384.199
metrics.audio_duration_ms=3475
metrics.rtf=0.110561
metrics.x_realtime=9.04478
metrics.sample_rate=24000
metrics.channels=1
```

### 7.2 CLI — with an explicit voice

```bash
audiocpp_cli --task tts --family kokoro_tts --model .../kokoro-82m-bf16.gguf \
  --backend cuda --voice-id af_heart --language en-us \
  --text "Voice interface test with a specific voice." --out /tmp/kokoro_voice.wav --metrics
```

```
metrics.wall_ms=213.47
metrics.audio_duration_ms=3075
metrics.rtf=0.0694212
metrics.x_realtime=14.4048
metrics.sample_rate=24000
metrics.channels=1
```

**Interpretation.** 3.1 s of speech in 213 ms. Even with a conservative
2× safety margin for chunking, concatenation and I/O, a typical agent answer
can be spoken in well under a second of synthesis time. **Voice output is not
a latency problem on this hardware** — the perceived latency will be dominated
by the *playback duration*, which is inherent to speech.

### 7.3 CLI — model introspection

```bash
audiocpp_cli --task tts --model .../kokoro-82m-bf16.gguf --inspect
```

```
family=kokoro_tts
variant=Kokoro 82M
supported_tasks=1
task=tts modes=offline
supports_speaker_reference=false
supports_style_condition=false
languages=en-us,en-gb,es,fr-fr,hi,it,ja,pt-br,zh
configs=3
config=vocabulary:…/vocab.tsv
config=voices:…/voices.json
config=config:…/config.json
weights=1
weight=weights:…/kokoro-82m-bf16.gguf
```

Note `supports_speaker_reference=false` for Kokoro: it is a **preset-voice**
model, not a cloning model. Cloning the "Torvalds" voice requires a different
family (MagpieTTS, OmniVoice, IndexTTS2, VoxCPM2 …). This distinction must
survive into the tool API, because "make the agent sound like X" is a
different request from "make the agent sound like *this specific* voice".

### 7.4 HTTP server — end to end

Config: `kokoro` model id, `kokoro_tts` family, `lazy_load: true`, CUDA.

```
GET  /health
  → {"status":"ok","backend":"cuda","models":1,"ui":false,"ui_management":false}

GET  /v1/models
  → {"object":"list","data":[{"id":"kokoro","object":"model","owned_by":"engine",
       "family":"kokoro_tts","task":"tts","mode":"offline","loaded":false,
       "path":"…/kokoro-82m-bf16.gguf"}]}

POST /v1/audio/speech   {"model":"kokoro","input":"Server mode is operational."}
  → HTTP 200, 114044 bytes of WAV
```

**Interpretation.** The HTTP surface is fully functional with the already-built
binary and the already-downloaded weights. The first request pays the model
load; subsequent requests reuse the warm session.

### 7.5 VRAM behaviour

| Observation | Value |
|---|---|
| Total VRAM | 8188 MiB |
| Idle (Xorg only) | 72 MiB |
| `audiocpp_server` with Kokoro loaded | +778 MiB |
| Free for TTS models | ~7.3 GB |
| Ollama resident models | none (`/api/ps` empty) |
| Chat model VRAM need (27B Q4_K_M) | ~16 GB → does not fit → CPU-resident |

**Interpretation.** The LLM does not compete for the GPU. A 1.9 GB MagpieTTS or
a 1.2 GB OmniVoice coexists with the LLM comfortably. The `min_free_memory_mb`
server guard and `max_loaded_models` remain worth setting in a production
config, because the *TTS* models are the things that accumulate.

### 7.6 Playback

`ffplay`, `ffmpeg` and `aplay` are present. `paplay`, `sox`, `mpv` and `cvlc`
are not. No Python audio library (`sounddevice`, `pyaudio`) is installed in
either venv.

**Interpretation.** The playback sink must be implemented on top of an
**external binary** (`ffplay` first, `aplay` second), never on a Python audio
library that is not installed. The toolkit must detect availability and
degrade to `file` output.

### 7.7 What was *not* validated

Stated explicitly, because a proposal that hides its gaps is worse than one
that names them:

- **OmniVoice / MagpieTTS were not run.** Only Kokoro was exercised
  end-to-end. The other weights are present and their families are registered
  in `model_specs/`, but their load paths are unproven on this host.
- **Streaming TTS** (`mode: streaming`, SSE `speech.audio.delta`) was not
  exercised; it is a documented server feature, not a measured one.
- **No microphone input path was tested.** There is no `arecord`/`ffmpeg`
  capture validation, and no ASR round-trip.
- **Long-text chunking was not exercised** through the HTTP route (Kokoro
  documents `text_chunk_size`, default 240 codepoints).
- **No concurrent GPU load test** — TTS synthesis while the LLM is generating.

---

## 8. Risk Register

| # | Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|---|
| R1 | The agent boot breaks when audio.cpp is absent | **High** | Medium | Guarded imports everywhere; the voice manager is constructed lazily and reports "unavailable"; never imported at module scope in the orchestrators |
| R2 | The TUI's terminal is corrupted by the player writing to stdout | Medium | High | `ffplay -nodisp`, stdout/stderr redirected to `DEVNULL`; the player never inherits the TUI's terminal |
| R3 | The render loop blocks on synthesis | Medium | Medium | Synthesis + playback run in a worker thread; the event loop only ever awaits a future it can abandon |
| R4 | Playback cannot be interrupted | Medium | Medium | Retain the `Popen` handle; `stop_speaking()` terminates the process group |
| R5 | The agent reads secrets aloud (API keys inside tool output) | **High** | Medium | Redaction pass over the speakable text (token-like patterns) + a default that skips code blocks + explicit opt-in |
| R6 | The user cannot read the text that is being spoken | Medium | Low | The text is *always* printed as well; voice is additive, never a replacement |
| R7 | Server busy / OOM makes the turn hang | Medium | Low | `busy_timeout_ms` on both sides; the client aborts and reports a structured error rather than blocking |
| R8 | VRAM exhaustion when a heavy TTS model is loaded | Medium | Low | `max_loaded_models: 1` + `min_free_memory_mb` in the recommended server config |
| R9 | Long answers produce a long, unskippable audio file | Medium | Medium | Sentence-aware chunking; each chunk is a separate utterance; barge-in supported |
| R10 | The feature diverges from the repo's toolkit conventions | High | Medium | The proposal is explicitly built on the MikroTik/Shodan pattern and lists every wiring point |
| R11 | C ABI route needs a third-party C++ rebuild | Low | — | Deferred to phase 3; HTTP needs no build step |
| R12 | A "speak everything" default becomes annoying | Medium | Medium | Opt-in by default (`TORVALDS_VOICE_ENABLED` defaults to off) |

---

## 9. Conclusion

The technical case is sound and empirically supported:

- The synthesis engine is **already built, already CUDA-enabled, already
  populated with TTS weights**, and measured at **14.4× real time**.
- The integration surface is **already running** (`audiocpp_server`), with a
  documented OpenAI-compatible `/v1/audio/speech` route and a voice catalogue
  endpoint.
- The agent side has **exactly one natural hook** (the value returned by
  `prompt_handler`) that both front ends share.
- The repository's toolkit pattern gives a proven template for adding a new
  capability cleanly, with an established error convention, an established
  opt-in convention, and established integration points.

The real engineering content of this work is **not** the synthesis — it is
(a) the interface decomposition, (b) the Markdown→speech text preparation,
(c) the non-blocking, interruptible playback, and (d) the security posture
around reading tool output aloud.

The proposal that follows turns those four into a concrete, phased design.

---

*Next: [`PROPOSAL_voice_output.md`](./PROPOSAL_voice_output.md)*
