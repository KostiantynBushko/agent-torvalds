# PROPOSAL: Unified Voice Interface for the Torvalds Agent

**Status:** Accepted — **architecture reworked**, see the banner below
**Scope:** Give `agent-torvalds` a single, configurable interface that lets it
produce voice (and, later, accept it) using the local `audio.cpp` stack.
**Companion document:** [`INVESTIGATION_REPORT.md`](./INVESTIGATION_REPORT.md)
**Build document:** [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) — the
authoritative plan, reworked to the component shape.

---

> ## ⚠️ The architecture changed after this document was written
>
> This proposal was written around a **toolkit**: a `toolkits/audio-toolkit/`
> library plus an `agent_voice_toolkit.py` LlamaIndex adapter that exposed
> four tools to the model.
>
> **That was the wrong shape, and the decision has been taken:** the voice
> feature is a **component** — `components/voice/` — with an **on/off
> switch**, and it exposes **no tools to the model at all**.
>
> The reasoning, in one line each:
>
> - Voice is *infrastructure*, not a model capability. The repository already
>   has the convention for it: `components/README.md` says the folder holds
>   "helper components and utility modules, **NOT** the agent's callable
>   tools".
> - The model has no business deciding *when* to speak, and a tool surface
>   drags the feature into the retriever, the `--select` menu and the top-k
>   retrieval budget for no benefit.
> - **There is no "Torvalds voice".** The default is the stock Kokoro preset
>   **`af_heart`**. Kokoro cannot clone (`supports_speaker_reference=false`),
>   so a clone is not an option with the current stack.
>
> **What is still valid in this document:** the problem statement (§2), the
> three-axis interface (§5), the backend contract and the HTTP/CLI/C-API
> design (§6), the output sinks (§7), the text-preparation layer (§8), the
> command surface (§10), the configuration reference (§12), the risks (§14)
> and the metrics (§15). The empirical numbers in the investigation report
> are unaffected.
>
> **What is superseded:** the file layout and the layering rules (§4.2, §4.3),
> the tool API (§9), the integration points (§11) and the phase list (§13).
> They are corrected inline below, and the reworked
> [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) is the authoritative
> build document.

> ## ⚠️ The listening half is now proposed — see the companion proposal
>
> This document is about the **output** half. The operator asked whether the
> **listening** half (ASR) should be combined with it in a single module. The
> answer is **yes, with a caveat**, and it is written up in
> **[`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md)**.
>
> **What that changes here:**
>
> - **§2.3** (the scope boundary) deferred Capability C — "speak *to* the
>   agent" — as a separate proposal. That deferral is now **partly lifted**:
>   the *push-to-talk* case (Level 1) is proposed for the same component,
>   while continuous listening (Level 2) and full duplex (Level 3) remain
>   deferred, for the reasons given in the companion proposal.
> - **§16, question 4** (the open questions) refers to the same question.
>
> **What does not change:** the "no tools" decision. The listening half
> contributes **no** tool either — the `transcribe_audio` tool stays deleted,
> and the capability is reachable through `\voice transcribe <path>` instead.
>
> **The shape:** one component (`components/voice/`), two managers
> (`VoiceSessionManager`, `ListeningSessionManager`), **one server**, one
> command family (`\voice`), one error table — and a **separate microphone
> switch that is off by default**, independent of the speaker.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Problem Statement](#2-problem-statement)
3. [Design Principles](#3-design-principles)
4. [Proposed Architecture](#4-proposed-architecture)
5. [The Unified Interface](#5-the-unified-interface)
6. [Backends](#6-backends)
7. [Output Sinks](#7-output-sinks)
8. [Text Preparation](#8-text-preparation)
9. [The Component API](#9-the-component-api)
10. [Command Surface](#10-command-surface)
11. [Integration Points](#11-integration-points)
12. [Configuration Reference](#12-configuration-reference)
13. [Implementation Plan](#13-implementation-plan)
14. [Risks & Mitigations](#14-risks--mitigations)
15. [Success Metrics](#15-success-metrics)
16. [Open Questions](#16-open-questions)

---

## 1. Overview

The Torvalds agent speaks only in text. A local `audio.cpp` stack that can
synthesise speech at **14.4× real time** on this machine sits two directories
away, fully built, with its TTS weights already downloaded — and the two
projects do not know about each other.

This proposal adds a **voice component** to the agent:

- an internal component (`components/voice/`) that knows how to turn text
  into audio through `audio.cpp`, with **no** LlamaIndex dependency and
  **no** tools exposed to the model;
- a **unified interface** defined as three orthogonal axes — *trigger*,
  *backend*, *output* — so that "speak the answer" and "announce progress"
  are configurations of one core rather than two subsystems;
- a `VoiceSessionManager` that wires the interface into both orchestrators;
- an **on/off switch** at three levels — environment, CLI flag and a runtime
  command — so the operator decides whether the agent speaks at all, and can
  change its mind mid-session.

The headline capability: **every agent response can be spoken aloud**, with the
text still shown. Voice is *additive* — the text is never replaced — and the
component is **off by default**, so nothing is lost if the operator never
turns it on.

---

## 2. Problem Statement

### 2.1 Current limitations

The agent has no audio capability whatsoever:

- `agent-torvalds.py` renders `Markdown(response)` to the terminal and nothing
  else. There is no path from a response to a sound.
- There is no ASR path, so the agent cannot be spoken to.
- There is no voice catalogue, so there is no way to pick a voice.
- No configuration, no commands, no tests.

The consequence for the operator is that a long, structured, technical answer —
exactly the kind this agent produces — must be read on a screen. For a
hands-free, screen-sharing, or accessibility workflow, that is a hard stop.

### 2.2 Why this is not simply "call `audiocpp_cli`"

Three reasons, each of which is a component of the proposal:

1. **The response is Markdown, and Markdown is not speech.** Reading it raw
   says "hash hash" per heading, "asterisk asterisk" per bold, and spells out
   fenced code. A text-preparation layer is mandatory.
2. **Answers are long.** The TTS route takes one `input` string; real answers
   need sentence-aware chunking and a WAV merge.
3. **The TUI is a live render loop.** Synthesis must not block it, and playback
   must be interruptible. That is an architectural requirement, not a detail.

### 2.3 Scope boundary — what is **in** and **out**

| In scope | Out of scope (separate proposal) |
|---|---|
| Agent response → speech (Capability A) | Microphone capture → ASR → agent (Capability C) |
| Runtime announcements (Capability B) | Full-duplex conversation, barge-in at the *recognition* level |
| Voice catalogue: presets | Speaker diarisation, voice conversion chains |
| Output sinks: speaker, file | Subtitle/lyric generation, audio editing |
| An on/off switch and a command surface | Replacing the text UI |
| **No LLM-facing tools** | Agent-initiated speech via a tool |

Capability C is deliberately deferred: it needs a different UI model (a
continuous listening mode), turn detection, and a different failure contract.
The interface below is designed so that adding it later is a new **input**
axis, not a rewrite.

> **Updated 2026-10-22.** The deferral above is **partly lifted** by
> [`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md), which
> argues that Capability C is really *three* capabilities — push-to-talk
> dictation (L1), continuous open-mic listening (L2) and full duplex (L3) —
> and that **L1 fits this proposal's contracts exactly** while L2 and L3 do
> not. L1 is proposed as an addition to this same component; L2 and L3 remain
> deferred.

---

## 3. Design Principles

| # | Principle | Consequence |
|---|---|---|
| **P1** | **Voice is additive, never a replacement** | The text is always printed. If synthesis fails, the turn is unaffected. |
| **P2** | **The agent must never break because audio is missing** | Guarded imports; a missing `audio.cpp` yields a disabled component and a clear message, never a traceback. |
| **P3** | **One interface, many capabilities** | Trigger × Backend × Output. No capability gets its own subsystem. |
| **P4** | **Synthesis is not the agent's job** | The agent decides *what* to say; the voice component decides *how* it is said. |
| **P5** | **Fail fast, fail structured** | Every error path returns a machine-readable code, following the repo's existing convention. |
| **P6** | **Never speak secrets** | Redaction plus code-block suppression by default. |
| **P7** | **Be a component, not a tool** | The feature lives in `components/voice/`, is switched on and off, and exposes no tools. The `components/` convention is followed exactly. |
| **P8** | **Non-blocking and interruptible** | Synthesis and playback run off the event loop; playback can be stopped at any time. |
| **P9** | **Off means off** | With the component off, no backend is probed, no thread is started, and the agent behaves identically to a build without it. |

---

## 4. Proposed Architecture

### 4.1 Component map

```
┌──────────────────────────────────────────────────────────────────────────┐
│  agent-torvalds.py  /  agent-torvalds-mw.py  (TUI)                      │
│                                                                          │
│   prompt_handler(...) ──► response_text ──┬──► console.print(Markdown)   │
│                                              │                           │
│                                              └──► narrate_response()     │
│                                                     └─► VoiceSessionManager
│                                                             .narrate()  │
└─────────────────────────────────────────────────────────┬────────────────┘
                                                          │
        ┌─────────────────────────────────────────────────┼──────────────┐
        │                                                 │              │
        ▼                                                 ▼              ▼
┌────────────────┐   ┌──────────────────┐   ┌───────────────────┐   ┌──────────┐
│ VoiceSession   │   │  Voice Component |   │  TextPreparation  │   │ Command  │
│ Manager        │   │  (components/)   │   │  to_speakable()   │   │ Surface  │
│ components/    │   │                  │   │  chunk_text()     │   │ \voice   │
│ voice/         │   │  backends/       │   │  redact()         │   │          │
│                │   │   base.py        │   └───────────────────┘   └──────────┘
│  config.py     │   │   http.py        │            ▲
│  session.py    │   │   cli.py         │────────────┘
│  narrator.py   │   │   capi.py (p3)   │
│  commands.py   │   │  output.py       │
│  runtime.py    │   │  voices.py       │
│  transport.py  │   └────────┬─────────┘
│  server.py     │            │
└───────┬────────┘   ┌────────┴─────────┐
        │            │                  │
        │   ┌────────▼────────┐  ┌──────▼──────────────────────┐
        │   │ Listening       │  │  audio.cpp runtime           │
        │   │ Session Manager │  │  audiocpp_server (default)   │
        │   │ (the input half)│  │  audiocpp_cli   (fallback)   │
        │   │  capture.py     │  │  libaudiocpp    (phase 3)    │
        │   │  transcribe.py  │  └───────────────────────────────┘
        │   │  silence.py     │      ▲        ▲
        │   └─────────────────┘      │        │
        └────────────────────────────┴────────┘
                    one server, one transport
```

> The **listening** half at the bottom of the diagram is the addition proposed
> in [`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md). It
> shares the `audiocpp_server` process, the transport and the error table
> with the output half, and has **its own manager and its own switch**.

### 4.2 File layout

```
components/voice/                      # the component — NO LlamaIndex imports
    __init__.py                        # public API re-exports
    config.py                          # VoiceConfig dataclass + env/CLI resolution
    errors.py                          # VoiceError + error codes
    text.py                            # to_speakable_text(), chunk_text(), redact()
    output.py                          # SpeakerSink, FileSink, NullSink
    voices.py                          # voice catalogue + capability probing
    session.py                         # VoiceSessionManager — the runtime facade
    narrator.py                        # post-response narration hook
    commands.py                        # is_voice_command(), handle_voice_command()
    runtime.py                         # the process-wide instance + close()
    backends/
        __init__.py
        base.py                        # SpeechBackend ABC, SpeechRequest, SpeechResult
        http.py                        # audiocpp_server REST client
        cli.py                         # audiocpp_cli subprocess backend
        capi.py                        # ctypes → libaudiocpp (phase 3, stub first)

docs/voice-component.md                # operator documentation
docs/audiocpp-server.json.example      # recommended server config
tests/test_voice_text.py               # text preparation
tests/test_voice_backends.py           # backend contract (mocked)
tests/test_voice_output.py             # sinks
tests/test_voice_voices.py             # catalogue
tests/test_voice_config.py             # configuration
tests/test_voice_session.py            # the manager
tests/test_voice_narrator.py           # the hook
tests/test_voice_commands.py           # the \voice commands
tests/test_voice_registry.py           # the command registry
tests/test_voice_wiring.py             # the orchestrator integration + the "not a tool" guard
```

**There is no `toolkits/audio-toolkit/` and no `agent_voice_toolkit.py`.**
The component is an ordinary Python package: `components.voice` is a valid
identifier, so it needs no import alias, no `sys.modules` trickery and no
`pytest.ini` testpath — the tests live in `tests/`, which is already
collected.

### 4.3 Layering rules (binding)

| Layer | May import | Must NOT import |
|---|---|---|
| `components/voice/**` | stdlib, `requests` (optional, lazy) | `llama_index.*`, any `agent_*.py`, any `toolkits.*` |
| `agent-torvalds*.py` | `components.voice` (public API only) | `components.voice` internals |

The dependency direction is strictly inward: **orchestrator → component**.

**There is no adapter layer.** A `components/voice/**` module that imports
`llama_index` or an `agent_*.py` module is a defect, and the implementation
plan enforces it mechanically with a test.

---

## 5. The Unified Interface

### 5.1 The three axes

```python
class VoiceTrigger(str, Enum):
    NEVER       = "never"        # the component never speaks on its own
    ON_RESPONSE = "on_response"  # speak each final response (Capability A)
    ANNOUNCE    = "announce"     # only when the runtime hands over text (B)

class VoiceBackend(str, Enum):
    NONE = "none"   # no synthesis available
    HTTP = "http"   # audiocpp_server  (default)
    CLI  = "cli"    # audiocpp_cli
    CAPI = "capi"   # libaudiocpp, in-process (phase 3)

class VoiceOutput(str, Enum):
    NONE    = "none"     # synthesize and discard (diagnostics)
    SPEAKER = "speaker"  # play through the local audio device
    FILE    = "file"     # write WAV files into the voice directory
```

### 5.2 The configuration object

```python
@dataclass(frozen=True)
class VoiceConfig:
    # --- axis 1: trigger ---
    trigger: VoiceTrigger = VoiceTrigger.ON_RESPONSE

    # --- axis 2: backend ---
    backend: VoiceBackend = VoiceBackend.HTTP
    server_url: str = "http://127.0.0.1:8099"
    server_model: str = "kokoro"        # model id registered in audiocpp_server
    cli_path: str = ""                  # path to audiocpp_cli
    cli_family: str = ""                # e.g. "kokoro_tts"
    cli_model_path: str = ""            # path to the GGUF
    cli_backend: str = "cuda"           # cuda | cpu | vulkan | metal
    timeout_s: float = 30.0

    # --- axis 3: output ---
    output: VoiceOutput = VoiceOutput.SPEAKER
    output_dir: str = ""                # for FILE output
    player_cmd: str = ""                # override; default auto-detected

    # --- voice selection ---
    voice_id: str = "af_heart"          # a Kokoro preset
    language: str = ""                  # must match the voice for Kokoro

    # --- behaviour ---
    speak_code_blocks: bool = False     # default: skip fenced code
    redact_secrets: bool = True
    max_chars: int = 1200               # per-utterance chunk budget
    min_chunk_chars: int = 120          # below this, merge with the next
    interruptible: bool = True
    rate_limit_s: float = 0.0           # min gap between utterances
```

> **`voice_ref` / `reference_text` are not in the dataclass.** The default
> backend cannot clone, and a config field that is silently ignored is worse
> than no field at all. They come back *with* a cloning-capable backend.

### 5.3 The runtime facade

`VoiceSessionManager` is the single object both orchestrators talk to.

```python
class VoiceSessionManager:
    def __init__(self, config: VoiceConfig): ...

    # --- the switch ---
    @property
    def enabled(self) -> bool: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...
    def toggle(self) -> bool: ...
    def set_trigger(self, trigger: VoiceTrigger) -> None: ...
    def set_voice(self, voice_id: str) -> None: ...

    # --- capability ---
    def available(self) -> bool: ...          # is a backend usable at all?
    def status(self) -> dict: ...             # {enabled, backend, trigger, output, model, ...}

    # --- production ---
    def narrate(self, text: str) -> None: ...   # post-response hook; non-blocking
    def announce(self, text: str) -> None: ...  # runtime announcement; non-blocking
    async def speak(self, text: str, **opts) -> dict: ...  # awaited, command-facing
    def stop(self) -> bool: ...                 # interrupt playback

    # --- discovery ---
    def list_voices(self) -> list[dict]: ...
    def probe(self) -> dict: ...                # health of the configured backend
    def close(self) -> None: ...                # stop playback, shut the worker down
```

**`narrate()` is non-blocking by contract.** It prepares the text, dispatches
synthesis to a worker thread, and returns immediately. The caller never awaits
it. This is what keeps the TUI render loop free.

**`speak()` is awaited** and returns the structured result — this is the path
the `\voice speak` and `\voice test` commands use, where the operator wants
to know whether the utterance was produced.

**The "off" contract.** When `enabled` is `False`, `narrate()` and
`announce()` return immediately without preparing the text, without
constructing a backend and without starting a thread; `speak()` returns
`VOICE_DISABLED`. The backend is built **lazily**, on the first synthesis
after the component is enabled.

### 5.4 How the two capabilities map onto the axes

| Capability | Configuration | Extra machinery |
|---|---|---|
| **A — speak the answer** | `trigger=on_response` | `narrate()` hook after `prompt_handler` |
| **B — speak mid-workflow** | `trigger=announce` | the `announce()` call from another component |
| **C — speak *to* the agent** | *(future)* `trigger=on_speech_input` | mic capture + ASR + turn detection — **separate proposal** |

> The last row is superseded in part by
> [`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md), which
> splits C into L1/L2/L3 and proposes adding L1 to this component.

---

## 6. Backends

All backends implement one contract, so they are interchangeable:

```python
class SpeechBackend(ABC):
    @abstractmethod
    def probe(self) -> BackendStatus: ...
    @abstractmethod
    def list_voices(self, model: str = "") -> list[dict]: ...
    @abstractmethod
    def synthesize(self, request: SpeechRequest) -> SpeechResult: ...
```

```python
@dataclass
class SpeechRequest:
    text: str
    voice_id: str = ""
    language: str = ""
    seed: int | None = None

@dataclass
class SpeechResult:
    ok: bool
    audio_path: str = ""      # written WAV, when the backend writes to disk
    audio_bytes: bytes = b""  # in-memory, when it does not
    sample_rate: int = 0
    duration_ms: float = 0.0
    wall_ms: float = 0.0
    error: str = ""           # machine-readable code
    detail: str = ""          # human-readable
```

### 6.1 `http` backend (default)

- `GET {server_url}/health` → probe.
- `GET {server_url}/v1/audio/voices?model={id}` → voice catalogue.
- `POST {server_url}/v1/audio/speech` with the OpenAI body → WAV bytes.

Error mapping:

| HTTP | Code | Meaning |
|---|---|---|
| 200 | — | ok |
| 404 | `VOICE_MODEL_NOT_FOUND` | the model id is not configured on the server |
| 503 + `server_busy` | `VOICE_SERVER_BUSY` | inference in progress; retry later |
| 503 + `insufficient_memory` | `VOICE_INSUFFICIENT_MEMORY` | VRAM/host memory guard tripped |
| 400 | `VOICE_BAD_REQUEST` | the request was rejected (bad voice, bad options) |
| connection refused | `VOICE_SERVER_UNAVAILABLE` | the server is not running |
| timeout | `VOICE_TIMEOUT` | exceeded `timeout_s` |

The client sends `busy_timeout_ms` in the request body so it can bound its own
wait — the server clamps this to the model/server ceiling, so the client can
only ever *shorten* it.

### 6.2 `cli` backend (fallback)

Invokes `audiocpp_cli --task tts --family <family> --model <path> --backend <b>
--text <t> --out <tmp.wav> --metrics`, parsing the `metrics.*` lines for
`rtf`/`wall_ms`/`sample_rate`.

For multi-chunk text it uses `--request-sequence <json>` so that one process
serves all chunks against a **warm** session — the CLI's batch mode does the
chunk/merge internally.

Failure detection: non-zero exit status, or a missing output file. The stderr
tail is captured into `detail` (truncated) for diagnostics.

### 6.3 `capi` backend (phase 3)

A `ctypes` binding over `libaudiocpp` (ABI 0.2.0). The C ABI is explicitly
designed for embedding — opaque handles, no exceptions across the boundary,
borrowed pointers, free-in-any-order lifetime.

**Prerequisite:** the shared library is not built today. It requires:

```bash
cmake -S . -B build/linux-cuda-release \
  -DENGINE_ENABLE_CUDA=ON -DAUDIOCPP_BUILD_C_API=ON
cmake --build build/linux-cuda-release --target audiocpp_c_api
```

The backend is therefore written **behind an interface and stubbed in phase 1**,
so the phase-3 work is an implementation, not a redesign.

### 6.4 Backend selection and fallback

`TORVALDS_VOICE_BACKEND` selects the backend. If the selected backend's
`probe()` fails, the manager:

1. logs a clear warning naming the backend and the reason;
2. falls back to `cli` if a CLI path is configured and the CLI backend probes
   OK;
3. otherwise disables voice (`trigger` effectively `never`) and **the agent
   continues normally**.

It never raises into the orchestrator.

---

## 7. Output Sinks

```python
class AudioSink(ABC):
    @abstractmethod
    def play(self, wav_path: str) -> PlaybackHandle: ...
```

### 7.1 `SpeakerSink`

```bash
ffplay -nodisp -autoexit -loglevel quiet <wav>
```

- `-nodisp` — no video window.
- stdout/stderr → `DEVNULL` (the player must never write to the TUI terminal).
- The `Popen` handle is retained so `stop()` can `terminate()` it → **barge-in**.
- Fallback chain: `ffplay` → `aplay` → (none).

**Device detection:** if no playback device is present (SSH session, container
without `/dev/snd`), the sink reports `no_output_device` and the manager
degrades to `FILE` output, saying so in one line. It never fails the turn.

### 7.2 `FileSink`

Writes `<output_dir>/torvalds-<timestamp>-<n>.wav`. Useful for headless hosts,
for reviewing what was said, and for a later "what did the agent say?" search
over the chat history.

### 7.3 `NullSink`

Synthesizes and discards. Used for latency measurement and for a "warm the
model" call at startup.

---

## 8. Text Preparation

This is the component that decides whether the feature sounds competent or
like a broken robot. It lives in `components/voice/text.py` and is purely
functional — fully unit-testable, no I/O.

### 8.1 `to_speakable_text(markdown: str) -> str`

| Input | Output |
|---|---|
| `## Heading` | `Heading` (the `##` is removed, not spoken) |
| `**bold**` / `_italic_` | `bold` / `italic` (markers dropped, words kept) |
| ```` ```code``` ```` | *(omitted entirely by default)* or `Code block omitted.` |
| `> quote` | `quote` |
| `- item` / `1. item` | `item.` (flattened into a sentence flow) |
| `---` (rule) | *(removed)* |
| `https://example.com/x` | `link` (or dropped) |
| `\| table \|` | *(removed — tables are unreadable aloud)* |
| `` `inline_code` `` | `inline code` (backticks dropped) |
| `—` / `–` | `, ` / `, ` |

The rule: **the spoken output must contain no Markdown punctuation at all.**

### 8.2 `chunk_text(text: str, max_chars: int, min_chars: int) -> list[str]`

Sentence-aware:

1. Split on sentence terminators (`.`, `!`, `?`, `…`, plus CJK `。！？`),
   keeping the terminator.
2. Split over-long sentences on `,` / `;` / ` — `.
3. Split anything still too long on whitespace.
4. Pack consecutive sentences into chunks up to `max_chars`, but never emit a
   chunk shorter than `min_chars` unless it is the last one.

The split points are respected by the *model* too: Kokoro accepts
`text_chunk_size` (default 240 codepoints), so the component may pass
`text_chunk_size=min(max_chars, 240)` for families that support it.

### 8.3 `redact(text: str) -> str`

Applied by default (`redact_secrets=True`). Replaces with `[redacted]`:

- `sk-…`, `ghp_…`, `gho_…`, `github_pat_…` style tokens;
- `Bearer <token>`;
- `AKIA…` AWS access key ids;
- `xox[baprs]-…` Slack tokens;
- JWT-shaped strings (`eyJ…\.eyJ…\.…`);
- `-----BEGIN … PRIVATE KEY-----` blocks;
- `password=` / `api_key=` / `secret=` / `token=` followed by a value.

### 8.4 What is *not* spoken

- Fenced code blocks (unless `speak_code_blocks=True`).
- Markdown tables.
- Raw URLs (replaced with "link").
- Anything matching the redaction patterns.

The **full original text is still printed** — redaction only affects the audio.

---

## 9. The Component API

> **This section replaces the "Tool API" of the original proposal.** The
> voice component exposes **no tools**. There is no `agent_voice_toolkit.py`,
> no `Category: Voice`, no `speak_text` and no `transcribe_audio`.

### 9.1 The public API

```python
from components.voice import (
    VoiceConfig, VoiceTrigger, VoiceBackend, VoiceOutput,
    VoiceSessionManager, build_voice_config, narrate_response,
    get_voice_manager, set_voice_manager, close_voice_manager,
)
```

Everything outside `components/voice/` uses only these names.

### 9.2 The narration hook

```python
def narrate_response(manager: Optional[VoiceSessionManager], text: str) -> None:
    """Narrate a final agent response. A no-op when the manager is None."""
```

It is a no-op when the manager is `None`, when the component is disabled, or
when the trigger is not `on_response`. It never raises.

### 9.3 The switch

```python
manager.enabled          # -> bool
manager.enable()         # turn the component on
manager.disable()        # turn it off
manager.toggle()         # flip it; returns the new state
```

The switch is also reachable from the environment
(`TORVALDS_VOICE_ENABLED`), from the CLI (`--voice` / `--no-voice`) and from
the runtime (`\voice on` / `\voice off` / `\voice toggle`).

### 9.4 The status

```python
manager.status()
# {
#   "enabled": True,
#   "available": True,
#   "trigger": "on_response",
#   "backend": "http",
#   "output": "speaker",
#   "server_url": "http://127.0.0.1:8099",
#   "server_model": "kokoro",
#   "voice_id": "af_heart",
#   "device": "speaker",
#   "detail": "...",
# }
```

### 9.5 The catalogue

```python
manager.list_voices()
# [
#   {"id": "af_heart", "name": "Heart", "language": "en-us",
#    "gender": "female", "source": "preset",
#    "capabilities": {"preset_voices": True,
#                     "speaker_reference": False,
#                     "style_control": False}},
#   ...
# ]
```

The `capabilities` block states whether the model supports preset voices,
speaker reference (cloning) and style control. With the default Kokoro model,
`speaker_reference` is `False` — which is exactly why there is no "Torvalds
voice".

---

## 10. Command Surface

Registered in `components/command_registry.py` behind a new
`FEATURE_VOICE = "voice"` flag, so the help screen only advertises them when
the voice runtime toggle is permitted.

| Command | Description |
|---|---|
| `\voice` | Show the voice status: enabled, trigger, backend, output, model, voice, device |
| `\voice on` / `\voice off` / `\voice toggle` | Enable / disable speaking the response at runtime |
| `\voice trigger <never\|on_response\|announce>` | Set the trigger axis at runtime |
| `\voice voice <id>` | Change the active preset voice |
| `\voice voices` | List the available voices |
| `\voice speak <text>` | Speak a line immediately (bypasses the trigger) |
| `\voice stop` | Stop the current playback |
| `\voice test` | Synthesise and play a short test phrase |
| `\voice help` | The cheat sheet |

`\voice` is a **runtime toggle**, like the existing `\toggle-hitl`, so the
operator can enable voice mid-session without restarting. The commands stay
visible even when voice is off, because `\voice on` is precisely how you turn
it on.

The dispatch follows the existing pattern: a `components/voice/commands.py`
module with `is_voice_command(cmd)` and `handle_voice_command(cmd)`, wired into
both orchestrators next to `is_mikrotik_command` / `is_project_command`.

> **If the listening proposal is approved**, this same family gains
> `\voice listen on|off`, `\voice dictate`, `\voice transcribe <path>` and
> `\voice devices`, and the status line splits into two halves — the output
> state and the microphone state. **No new registry entry, no new category
> and no new feature flag.**

---

## 11. Integration Points

Every wiring point the feature touches, listed exhaustively so nothing is
missed:

| File | Change |
|---|---|
| `components/voice/**` | **New** — the component |
| `components/command_registry.py` | `FEATURE_VOICE` flag + the `\voice` `CommandSpec` + the `Voice` category |
| `agent-torvalds.py` | Build the `VoiceConfig` from env + CLI flags; construct the `VoiceSessionManager`; call `narrate_response(response)` after `prompt_handler`; dispatch the `\voice` commands; add the CLI flags; close the manager on exit |
| `agent-torvalds-mw.py` | The same, plus the TUI state fields and a `\voice` command handler |
| `components/tui/state_bridge.py` | `voice_enabled: bool`, `voice_status: str`, `voice_last_spoken: str` on `TuiState` |
| `components/tui/telemetry_view.py` | Show the voice state in the telemetry pane |
| `components/tui/tui_app.py` | Handle the `\voice` commands; stop playback on `\exit` |
| `components/README.md` | A new section for the `voice/` component |
| `requirements.txt` | `requests>=2.31.0` is **already present** — no new mandatory dependency |
| `docs/voice-component.md` | **New** — the operator guide |
| `README.md`, `CHANGELOG.md` | Document the feature |

**And what is deliberately NOT touched:**

| File | Why it stays as it is |
|---|---|
| `agent_tool_retriever.py` | There are no tools to retrieve. No `include_voice_tools` flag. |
| `agent_tool_selection.py` | There is no `Voice` category in the `--select` menu. |
| `_collect_all_tools()` in both orchestrators | Voice contributes no tools. |
| `toolkits/__init__.py` | `components.voice` is a normal package — no import alias. |
| `pytest.ini` | The tests live in `tests/`, which is already collected. |

### 11.1 The narration hook (both orchestrators)

Classic REPL — `agent-torvalds.py`:

```python
response, stats = await prompt_handler(cmd, agent, enable_stats=stats_enabled,
                                       event_consumer=event_consumer)
...
console.rule("[blue]Agent Response[/blue]")
console.print(Markdown(response))
console.rule()

# --- voice (component, off by default, never blocks) ---
narrate_response(voice_session, response)
```

TUI — `agent-torvalds-mw.py` / `components/tui/tui_app.py`:

```python
response, stats = await self.prompt_handler_fn(...)
self.state.set_markdown_content(response)
narrate_response(self.voice_session, response)
```

Because `narrate()` returns immediately, the TUI's render loop is unaffected.

### 11.2 Interruption (barge-in)

Both front ends call `voice_session.stop()` **before** dispatching a new user
input, so typing during playback cuts the audio short rather than queueing
behind it.

---

## 12. Configuration Reference

### 12.1 Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `TORVALDS_VOICE_ENABLED` | `false` | **The initial state of the component.** Off by default. |
| `TORVALDS_VOICE_RUNTIME_TOGGLE` | `true` | Whether the `\voice` commands exist. |
| `TORVALDS_VOICE_TRIGGER` | `on_response` | `never` · `on_response` · `announce` |
| `TORVALDS_VOICE_BACKEND` | `http` | `http` · `cli` · `capi` · `none` |
| `TORVALDS_VOICE_SERVER_URL` | `http://127.0.0.1:8099` | `audiocpp_server` base URL. Must match the operator's server config |
| `TORVALDS_VOICE_SERVER_MODEL` | `kokoro` | Model id registered in the server config |
| `TORVALDS_VOICE_CLI_PATH` | *(empty)* | Path to `audiocpp_cli` |
| `TORVALDS_VOICE_CLI_FAMILY` | *(empty)* | e.g. `kokoro_tts` |
| `TORVALDS_VOICE_CLI_MODEL` | *(empty)* | Path to the GGUF |
| `TORVALDS_VOICE_CLI_BACKEND` | `cuda` | `cuda` · `cpu` · `vulkan` · `metal` |
| `TORVALDS_VOICE_OUTPUT` | `speaker` | `speaker` · `file` · `none` |
| `TORVALDS_VOICE_DIR` | `~/.cache/torvalds/voice` | Where `file` output is written |
| `TORVALDS_VOICE_ID` | `af_heart` | Preset voice id. See §12.4 for the catalogue and the alternatives |
| `TORVALDS_VOICE_LANGUAGE` | *(empty)* | Language code; must match the voice |
| `TORVALDS_VOICE_SPEAK_CODE` | `false` | Speak fenced code blocks |
| `TORVALDS_VOICE_REDACT` | `true` | Redact secret-looking strings |
| `TORVALDS_VOICE_MAX_CHARS` | `1200` | Chunk budget per utterance |
| `TORVALDS_VOICE_TIMEOUT` | `30` | Per-request timeout, seconds |

### 12.2 CLI flags

`--voice` / `--no-voice` (enable/disable), `--voice-trigger`,
`--voice-backend`, `--voice-server-url`, `--voice-model`, `--voice-id`,
`--voice-language`, `--voice-output`, `--voice-dir`, `--voice-timeout`,
`--no-voice-runtime-toggle`.

CLI flags override environment variables, exactly as `--hitl-timeout` overrides
`TORVALDS_HITL_TIMEOUT`.

### 12.3 Recommended `audiocpp_server` config

```json
{
  "host": "127.0.0.1",
  "port": 8099,
  "backend": "cuda",
  "device": 0,
  "threads": 2,
  "lazy_load": true,
  "max_loaded_models": 1,
  "min_free_memory_mb": 2048,
  "busy_timeout_ms": 30000,
  "idle_unload_ms": 300000,
  "models": [
    {
      "id": "kokoro",
      "family": "kokoro_tts",
      "path": "/home/kbush/ai-agent-investiagte/models/TTS/kokoro-82m-bf16.gguf",
      "task": "tts",
      "mode": "offline",
      "busy_timeout_ms": 15000
    }
  ]
}
```

`max_loaded_models: 1` keeps exactly one TTS model resident, which bounds VRAM
to a single model and is the right choice on an 8 GB card.

> **If the listening proposal is approved**, this config gains a second model
> entry and `max_loaded_models` becomes **2** — otherwise the server would
> evict the TTS model every time the ASR model is needed.

### 12.4 The default voice

**Default: `af_heart`** - a clear American English female preset. It is the
most legible of the Kokoro English voices, and English is what the agent
speaks most of the time.

**There is no cloned "Torvalds voice" in v1 - and there cannot be one with the
current stack.** Kokoro 82M is a *preset-voice* model:
`supports_speaker_reference=false`. It has no cloning head, so a `voice_ref`
is ignored by the model. Cloning needs a cloning-capable family - MagpieTTS
(1.9 GB) or OmniVoice (1.2 GB) - **plus** a reference recording, which is an
operator task. Until then the preset catalogue is the whole story.

The `torvalds-voice` string in the server config is therefore a **model id**,
not a voice: it is the name the model is registered under. Naming it `kokoro`
is more honest, and it is what the local server config already uses.

**The catalogue** - 54 presets across 9 languages. The prefix is
`<language><gender>`:

| Prefix | Language | Gender | Voices |
|---|---|---|---|
| `af_` | American English | female | `alloy`, `aoede`, `bella`, `heart`, `jessica`, `kore`, `nicole`, `nova`, `river`, `sarah`, `sky` |
| `am_` | American English | male | `adam`, `echo`, `eric`, `fenrir`, `liam`, `michael`, `onyx`, `puck`, `santa` |
| `bf_` | British English | female | `alice`, `emma`, `isabella`, `lily` |
| `bm_` | British English | male | `daniel`, `fable`, `george`, `lewis` |
| `ef_` / `em_` | Spanish | female / male | `dora` / `alex`, `santa` |
| `ff_` | French | female | `siwis` |
| `hf_` / `hm_` | Hindi | female / male | `alpha`, `beta` / `omega`, `psi` |
| `if_` / `im_` | Italian | female / male | `sara` / `nicola` |
| `jf_` / `jm_` | Japanese | female / male | `alpha`, `gongitsune`, `nezumi`, `tebukuro` / `kumo` |
| `pf_` / `pm_` | Portuguese | female / male | `dora` / `alex`, `santa` |
| `zf_` / `zm_` | Chinese | female / male | `xiaobei`, `xiaoni`, `xiaoxiao`, `xiaoyi` / `yunjian`, `yunxi`, `yunxia`, `yunyang` |

**Changing it** - three ways, in precedence order:

```bash
TORVALDS_VOICE_ID=am_michael python agent-torvalds.py    # 1. environment
python agent-torvalds.py --voice-id am_michael            # 2. CLI flag
\voice voice am_michael                                   # 3. runtime command
```

A male American English preset (`am_michael`, `am_onyx`) is the usual
alternative when a less "assistant"-like tone is wanted.

---

## 13. Implementation Plan

> The authoritative, phase-by-phase plan is
> **[`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)**, reworked to the
> component shape. The summary below is the outline; the plan carries the
> file-level detail, the binding contracts and the exit criteria.

| Phase | Item | Detail |
|---|---|---|
| **0** | **Scaffolding** | `components/voice/` skeleton with the final public API; the baseline test run; no agent files touched |
| **1** | **The text layer** | `to_speakable_text()`, `chunk_text()`, `redact()` — pure functions, fully unit-tested |
| **2** | **The backend contract + HTTP** | `SpeechBackend`, `SpeechRequest`, `SpeechResult`; the `audiocpp_server` client with its error mapping |
| **3** | **The CLI backend + the sinks** | `audiocpp_cli` with `--request-sequence`; the C-API stub; `SpeakerSink` / `FileSink` / `NullSink` with device detection |
| **4** | **The voice catalogue** | Normalisation across the backends, the capability block, **and the default voice: `af_heart`, no clone** |
| **5** | **Configuration** | `VoiceConfig` + `build_voice_config()`: env → CLI override, invalid values fall back and warn |
| **6** | **The session manager** | The on/off switch, the lazy backend, the fallback ladder, the worker thread, `stop()`, `close()` |
| **7** | **The narration hook** | `narrate_response()` — a no-op when the component is off; never raises |
| **8** | **The command surface** | `components/voice/commands.py` + `FEATURE_VOICE` in the central registry |
| **9** | **Orchestrator integration** | The CLI flags, the manager construction, the hook, the dispatch, the barge-in, the TUI state and telemetry |
| **10** | **Hardening** | Barge-in, redaction, long answers, the degradation ladder, headless, the layering guard and the "not a tool" guard |
| **11** | **Documentation** | `docs/voice-component.md`, the server config example, `components/README.md`, `README.md`, `CHANGELOG.md` |

**Scope discipline:** Phases 0–11 constitute the deliverable "the agent can
produce voice, and the operator can switch it off". The `capi` backend,
streaming TTS, ASR and voice cloning are explicitly out of the initial scope
and are individually approvable.

> **The ASR clause above is superseded in part** by
> [`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md), which
> proposes adding the **L1 (push-to-talk dictation)** case as Phases 12–18.
> The `capi` backend, streaming TTS and voice cloning remain out of scope.

---

## 14. Risks & Mitigations

See the full register in the investigation report (§8). The four that shape
the implementation:

| Risk | Mitigation | Where it lives |
|---|---|---|
| **The agent boot breaks without `audio.cpp`** | The component imports nothing optional at module scope; `requests` is imported lazily inside the HTTP backend; the backend itself is built lazily; a missing `ffplay` is detected at sink-selection time, not import time. | `components/voice/session.py`, `components/voice/backends/http.py` |
| **The TUI terminal is corrupted by the player** | `ffplay -nodisp`, `stdout`/`stderr` → `DEVNULL`, the player never inherits the TUI terminal. The TUI renders the voice state in its own pane. | `components/voice/output.py` |
| **The agent reads secrets aloud** | Redaction is **on by default**; code blocks are skipped by default; the component is **off by default**; the full text is still printed. | `components/voice/text.py` |
| **The render loop blocks on synthesis** | `narrate()` is non-blocking by contract; synthesis and playback run in a worker thread; the TUI never awaits speech. | `components/voice/session.py` |

*Risk R10 from the original register — "the feature diverges from the repo's
toolkit conventions" — is **removed** by this rework: the feature is now a
component, which is the convention it should have followed from the start.*

> The input half adds its own register — ambient capture, ASR hallucination,
> spoken prompt injection, capture/TUI contention — in
> [`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md) §13.

---

## 15. Success Metrics

| Metric | Target | How it is measured |
|---|---|---|
| Agent boot time with the component on | +< 50 ms | The manager is cheap; the backend is built lazily |
| Agent boot time with the component off | +0 ms | No backend, no thread, no probe |
| Time to first audio, typical response | < 1.5 s | `wall_ms` from the backend + player start-up |
| Synthesis RTF (Kokoro, CUDA) | < 0.15 | `--metrics` / server `timing` |
| Response latency impact (classic REPL) | 0 ms blocking | `narrate()` returns before the next prompt is shown |
| Turn success rate with the server down | 100 % (text unaffected) | Degradation test |
| Component convention compliance | 100 % | The layering test + the "not a tool" test |
| Test coverage of `text.py` | > 90 % | `pytest --cov` |
| Secret leakage in spoken output | 0 | Redaction test with a seeded key set |

---

## 16. Open Questions

These need an operator decision before the integration phase closes:

1. ~~**Default voice.**~~ **DECIDED: `af_heart`.** The 54-preset catalogue is
   documented in §12.4. Kokoro cannot clone, so a preset *is* the default voice;
   `am_michael` / `am_onyx` are the male-English alternatives and
   `TORVALDS_VOICE_ID` switches at runtime.
2. ~~**Is a "Torvalds voice" (cloned) required?**~~ **DECIDED: no, not for v1.**
   The operator does not have a cloned voice, and Kokoro cannot clone anyway
   (`supports_speaker_reference=false`). v1 ships the preset catalogue; cloning
   (MagpieTTS / OmniVoice + a reference recording) is out of scope.
3. ~~**Toolkit or component?**~~ **DECIDED: component.** The feature lives in
   `components/voice/`, exposes no tools to the model, and is switched on and
   off at three levels (environment, CLI flag, runtime command).
4. **Should the agent speak by default once enabled?** Currently
   `TORVALDS_VOICE_ENABLED=1` implies `trigger=on_response`. A more
   conservative option is `enabled` + `trigger=announce`, so only explicit
   announcements are spoken until the operator opts into "speak every answer".
5. **Should the spoken text be persisted in the chat history?** The chat
   memory already stores the response; storing the *spoken* variant separately
   would let a future search find "what the agent said aloud".
6. **Is the `audiocpp_server` lifecycle managed by the agent?** Options:
   (a) the operator runs it (recommended — it keeps the model warm across
   turns); (b) the agent spawns it on demand and reaps it on exit;
   (c) a systemd user unit. Option (a) is the simplest and is what the
   proposal assumes.
7. **Multi-turn continuity.** Should consecutive answers be spoken as one
   continuous stream (sentence-level streaming) rather than one file per
   turn? This is the `mode: streaming` route and it needs a different audio
   path (a persistent player fed by a pipe).
8. **Should other components be able to announce themselves?** (e.g. the HITL
   handler speaking "the agent is asking you a question".) The `announce()`
   API exists for it, but nothing calls it in v1.
9. **Should the component also *receive* speech?** (the ASR question) — this
   is the question the operator asked. The answer is **partly yes**: the
   push-to-talk case is proposed in
   [`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md); continuous
   listening and full duplex remain out of scope.

---

*Next step: the reworked [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md),
then Phase 0 in the `self-development` clone on a `feature/voice-toolkit`
branch. The input half, if approved, is specified in
[`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md).*
