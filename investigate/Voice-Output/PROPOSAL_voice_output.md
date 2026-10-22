# PROPOSAL: Unified Voice Interface for the Torvalds Agent

**Status:** Proposed — awaiting operator review
**Scope:** Give `agent-torvalds` a single, configurable interface that lets it
produce voice (and, later, accept it) using the local `audio.cpp` stack.
**Companion document:** [`INVESTIGATION_REPORT.md`](./INVESTIGATION_REPORT.md)

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
9. [Tool API](#9-tool-api)
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

This proposal adds a **voice subsystem** to the agent:

- a reusable toolkit (`toolkits/audio-toolkit/`) that knows how to turn text
  into audio through `audio.cpp`, with no LlamaIndex dependency;
- a **unified interface** defined as three orthogonal axes — *trigger*,
  *backend*, *output* — so that "speak the answer", "announce progress" and
  "speak to the agent" are configurations of one core rather than three
  subsystems;
- a `VoiceSessionManager` in `components/voice/` that wires the interface into
  both orchestrators;
- a `Voice` tool category so the agent can speak on its own initiative.

The headline capability: **every agent response can be spoken aloud**, with the
text still shown. Voice is *additive* — the text is never replaced — so nothing
is lost if the operator turns it off.

---

## 2. Problem Statement

### 2.1 Current limitations

The agent has no audio capability whatsoever:

- `agent-torvalds.py` renders `Markdown(response)` to the terminal and nothing
  else. There is no path from a response to a sound.
- There is no ASR path, so the agent cannot be spoken to.
- There is no voice catalogue, so there is no way to pick or clone a voice.
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
| Agent-initiated announcements (Capability B) | Full-duplex conversation, barge-in at the *recognition* level |
| Voice catalogue: presets, cloning references | Speaker diarisation, voice conversion chains |
| Output sinks: speaker, file | Subtitle/lyric generation, audio editing |
| A `Voice` tool category | Replacing the text UI |

Capability C is deliberately deferred: it needs a different UI model (a
continuous listening mode), turn detection, and a different failure contract.
The interface below is designed so that adding it later is a new **input**
axis, not a rewrite.

---

## 3. Design Principles

| # | Principle | Consequence |
|---|---|---|
| **P1** | **Voice is additive, never a replacement** | The text is always printed. If synthesis fails, the turn is unaffected. |
| **P2** | **The agent must never break because audio is missing** | Guarded imports; a missing `audio.cpp` yields a disabled feature and a clear message, never a traceback. |
| **P3** | **One interface, many capabilities** | Trigger × Backend × Output. No capability gets its own subsystem. |
| **P4** | **Synthesis is not the agent's job** | The agent decides *what* to say; the voice subsystem decides *how* it is said. |
| **P5** | **Fail fast, fail structured** | Every error path returns a machine-readable code, following the repo's existing convention. |
| **P6** | **Never speak secrets** | Redaction plus code-block suppression by default. |
| **P7** | **Follow the house pattern exactly** | `toolkits/` core + root adapter + `Category:` tag + `include_*_tools` flag + `\command` in the registry. |
| **P8** | **Non-blocking and interruptible** | Synthesis and playback run off the event loop; playback can be stopped at any time. |

---

## 4. Proposed Architecture

### 4.1 Component map

```
┌──────────────────────────────────────────────────────────────────────────┐
│  agent-torvalds.py  /  agent-torvalds-mw.py  (TUI)                      │
│                                                                          │
│   prompt_handler(...) ──► response_text ──┬──► console.print(Markdown)   │
│                                              │                           │
│                                              └──► VoiceSessionManager    │
│                                                     .narrate(response)   │
└─────────────────────────────────────────────────────────┬────────────────┘
                                                          │
        ┌─────────────────────────────────────────────────┼──────────────┐
        │                                                 │              │
        ▼                                                 ▼              ▼
┌────────────────┐   ┌──────────────────┐   ┌───────────────────┐   ┌──────────┐
│ VoiceSession   │   │  VoiceToolkit    │   │  TextPreparation  │   │ Command  │
│ Manager        │   │  (toolkits/)     │   │  to_speakable()   │   │ Surface  │
│ components/    │   │                  │   │  chunk_text()     │   │ \voice   │
│ voice/         │   │  backends/       │   │  redact()         │   │ \voices  │
│                │   │   base.py        │   │                   │   │ \speak   │
│  config.py     │   │   http.py        │   └───────────────────┘   └──────────┘
│  session.py    │   │   cli.py         │            ▲
│  narrator.py   │   │   capi.py (p3)   │────────────┘
│                │   │  output.py       │
│                │   │  voices.py       │
└───────┬────────┘   └────────┬─────────┘
        │                     │
        └──────────┬──────────┘
                   ▼
        ┌────────────────────────────────┐
        │  audio.cpp runtime             │
        │  audiocpp_server (default)     │
        │  audiocpp_cli   (fallback)     │
        │  libaudiocpp    (phase 3)      │
        └────────────────────────────────┘
```

### 4.2 File layout

```
toolkits/audio-toolkit/                 # core library — NO LlamaIndex imports
    __init__.py                         # public API re-exports
    config.py                           # VoiceConfig dataclass + env resolution
    backends/
        __init__.py
        base.py                         # SpeechBackend ABC, SpeechRequest, SpeechResult
        http.py                         # audiocpp_server REST client
        cli.py                          # audiocpp_cli subprocess backend
        capi.py                         # ctypes → libaudiocpp (phase 3, stub first)
    output.py                           # SpeakerSink, FileSink, NullSink
    voices.py                           # voice catalogue + capability probing
    text.py                             # to_speakable_text(), chunk_text(), redact()
    errors.py                           # VoiceError + error codes

agent_voice_toolkit.py                  # LlamaIndex adapter (the ONLY LlamaIndex file)
components/voice/
    __init__.py
    config.py                           # VoiceConfig resolution (env + CLI)
    session.py                          # VoiceSessionManager — the runtime facade
    narrator.py                         # post-response narration hook

docs/voice-toolkit.md                   # operator documentation
docs/audiocpp-server.json.example       # recommended server config
tests/test_voice_text.py                # text preparation
tests/test_voice_backends.py            # backend contract (mocked)
tests/test_voice_output.py              # sinks
tests/test_voice_toolkit.py             # adapter
tests/test_voice_menu.py                # \voice commands + --select parity
```

### 4.3 Layering rules (binding)

| Layer | May import | Must NOT import |
|---|---|---|
| `toolkits/audio-toolkit/**` | stdlib, `requests`/`httpx` (optional) | `llama_index.*`, `components.*`, `agent_*.py` |
| `agent_voice_toolkit.py` | `toolkits.audio_toolkit`, `llama_index.core.tools` | `components.voice.*` (keeps the adapter independent) |
| `components/voice/**` | `toolkits.audio_toolkit` | `llama_index.*` |
| `agent-torvalds*.py` | `components.voice`, `agent_voice_toolkit` | `toolkits.audio_toolkit` internals |

The dependency direction is strictly inward: orchestrator → components → toolkit.
This is the same rule the MikroTik toolkit established.

---

## 5. The Unified Interface

### 5.1 The three axes

```python
class VoiceTrigger(str, Enum):
    NEVER       = "never"        # voice disabled entirely
    ON_RESPONSE = "on_response"  # speak each final response (Capability A)
    ANNOUNCE    = "announce"     # only when the agent calls speak_text (B)

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
    trigger: VoiceTrigger = VoiceTrigger.NEVER

    # --- axis 2: backend ---
    backend: VoiceBackend = VoiceBackend.HTTP
    server_url: str = "http://127.0.0.1:8080"
    server_model: str = ""              # model id registered in audiocpp_server
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
    voice_id: str = ""                  # preset voice, e.g. "af_heart"
    voice_ref: str = ""                 # reference WAV for cloning
    reference_text: str = ""
    language: str = ""                  # must match the voice for Kokoro

    # --- behaviour ---
    speak_code_blocks: bool = False     # default: skip fenced code
    redact_secrets: bool = True
    max_chars: int = 1200               # per-utterance chunk budget
    min_chunk_chars: int = 120          # below this, merge with the next
    interruptible: bool = True
    rate_limit_s: float = 0.0           # min gap between utterances
```

### 5.3 The runtime facade

`VoiceSessionManager` is the single object both orchestrators talk to.

```python
class VoiceSessionManager:
    def __init__(self, config: VoiceConfig): ...

    # --- capability ---
    def available(self) -> bool: ...          # is a backend usable at all?
    def status(self) -> dict: ...             # {enabled, backend, trigger, output, model, ...}

    # --- production ---
    def narrate(self, text: str) -> None: ...  # post-response hook; non-blocking
    async def speak(self, text: str, **opts) -> dict: ...  # awaited, tool-facing
    def stop(self) -> bool: ...                 # interrupt playback

    # --- discovery ---
    def list_voices(self) -> list[dict]: ...
    def probe(self) -> dict: ...                # health of the configured backend
```

**`narrate()` is non-blocking by contract.** It prepares the text, dispatches
synthesis to a worker thread, and returns immediately. The caller never awaits
it. This is what keeps the TUI render loop free.

**`speak()` is awaited** and returns the structured result — this is the tool
path, where the agent wants to know whether the utterance was produced.

### 5.4 How the three capabilities map onto the axes

| Capability | Configuration | Extra machinery |
|---|---|---|
| **A — speak the answer** | `trigger=on_response` | `narrate()` hook after `prompt_handler` |
| **B — announce mid-workflow** | `trigger=announce` | the `speak_text` tool |
| **C — speak *to* the agent** | *(future)* `trigger=on_speech_input` | mic capture + ASR + turn detection — **separate proposal** |

---

## 6. Backends

All backends implement one contract, so they are interchangeable:

```python
class SpeechBackend(ABC):
    @abstractmethod
    def probe(self) -> BackendStatus: ...
    @abstractmethod
    def list_voices(self) -> list[dict]: ...
    @abstractmethod
    def synthesize(self, request: SpeechRequest) -> SpeechResult: ...
```

```python
@dataclass
class SpeechRequest:
    text: str
    voice_id: str = ""
    voice_ref: str = ""
    reference_text: str = ""
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
`probe()` fails at startup, the manager:

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
like a broken robot. It lives in `toolkits/audio-toolkit/text.py` and is
purely functional — fully unit-testable, no I/O.

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
`text_chunk_size` (default 240 codepoints), so the toolkit may pass
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

## 9. Tool API

The adapter `agent_voice_toolkit.py` exposes four tools under the
**`Category: Voice`** tag.

### 9.1 `speak_text`

```python
async def speak_text(
    text: str,
    voice_id: str = "",
    language: str = "",
    output: str = "",          # "", "speaker", "file"
) -> dict
```

Speaks arbitrary text immediately. Returns:

```json
{
  "ok": true,
  "spoken": "Torvalds agent, operational.",
  "voice_id": "af_heart",
  "output": "speaker",
  "duration_ms": 2100.4,
  "wall_ms": 213.5,
  "rtf": 0.069,
  "sample_rate": 24000,
  "audio_path": ""
}
```

Failure:

```json
{
  "ok": false,
  "error": "VOICE_SERVER_UNAVAILABLE",
  "detail": "Could not connect to http://127.0.0.1:8080 (connection refused)"
}
```

### 9.2 `list_voices`

```python
async def list_voices(model: str = "") -> dict
```

Returns the catalogue from `GET /v1/audio/voices`, or the model-local list for
the CLI backend, plus a `capabilities` block stating whether the model supports
preset voices, speaker reference (cloning) and style control — so the agent
knows that Kokoro cannot clone but MagpieTTS can.

### 9.3 `stop_speaking`

```python
async def stop_speaking() -> dict
```

Interrupts the current playback. Returns `{"ok": true, "stopped": true}`.

### 9.4 `transcribe_audio` (phase 2, optional)

```python
async def transcribe_audio(path: str, language: str = "") -> dict
```

Wraps `POST /v1/audio/transcriptions`. Exposed as a *tool* (not an input
channel) so the agent can transcribe a file the user points it at, without
committing to a full voice-assistant mode.

### 9.5 Adapter conventions (compliance with the house pattern)

- Module docstring ends with `Category: Voice` and a
  `Retriever Keywords: voice, speech, speak, say, read aloud, tts, audio, ...`
  line.
- The core package is imported inside `try/except`; `VOICE_AVAILABLE` and
  `VOICE_IMPORT_ERROR` are module-level, mirroring the MikroTik adapter.
- No tool raises. Every failure is a structured payload.
- `get_all_tools()` returns `[]` when the toolkit is unavailable — the agent
  simply has no Voice category, and the `--select` menu shows nothing for it.

---

## 10. Command Surface

Registered in `components/command_registry.py` behind a new
`FEATURE_VOICE = "voice"` flag, so the help screen only advertises them when
the feature is enabled.

| Command | Description |
|---|---|
| `\voice` | Show the voice status: backend, trigger, output, model, voice, device |
| `\voice on` / `\voice off` | Enable / disable speaking the response at runtime |
| `\voice trigger <never\|on_response\|announce>` | Set the trigger axis at runtime |
| `\voice voice <id>` | Change the active preset voice |
| `\voice voices` | List the available voices |
| `\voice speak <text>` | Speak a line immediately (bypasses the trigger) |
| `\voice stop` | Stop the current playback |
| `\voice test` | Synthesise and play a short test phrase |

`\voice` is a **runtime toggle**, like the existing `\toggle-hitl`, so the
operator can enable voice mid-session without restarting.

The dispatch follows the existing pattern: a `components/voice/commands.py`
module with `is_voice_command(cmd)` and `handle_voice_command(cmd)`, wired into
both orchestrators next to `is_mikrotik_command` / `is_project_command`.

---

## 11. Integration Points

Every wiring point the feature touches, listed exhaustively so nothing is
missed:

| File | Change |
|---|---|
| `toolkits/audio-toolkit/**` | **New** — the core library |
| `agent_voice_toolkit.py` | **New** — the LlamaIndex adapter |
| `components/voice/{__init__,config,session,narrator,commands}.py` | **New** — the runtime facade |
| `agent_tool_retriever.py` | New `include_voice_tools: bool = True` flag; load the adapter in the retriever path |
| `agent_tool_selection.py` | `_discover_tools()` imports the adapter (inside `try/except`) so the **Voice** category appears in `--select`; add a dedicated action pattern for the Voice category so the summary is not generic |
| `components/command_registry.py` | `FEATURE_VOICE` flag + the eight `\voice*` `CommandSpec`s |
| `agent-torvalds.py` | Build the `VoiceConfig` from env + CLI flags; construct the `VoiceSessionManager`; call `narrate(response)` after `prompt_handler`; dispatch `\voice` commands; add the CLI flags |
| `agent-torvalds-mw.py` | The same, plus the TUI state fields and a `\voice` command handler |
| `components/tui/state_bridge.py` | `voice_active: bool`, `voice_status: str`, `voice_last_spoken: str` on `TuiState` |
| `components/tui/tui_app.py` | Show the voice state in the telemetry pane; stop playback on `\exit` |
| `components/ollama_config.py` (analogue) | New `components/voice/config.py` resolving `TORVALDS_VOICE_SERVER_URL` → `AUDIO_CPP_SERVER_URL` → `http://127.0.0.1:8080` |
| `pytest.ini` | Add `toolkits/audio-toolkit/tests` to `testpaths` (if the toolkit ships its own suite) |
| `requirements.txt` | `requests>=2.31.0` is **already present** — no new mandatory dependency |
| `docs/voice-toolkit.md` | **New** — the operator guide |
| `README.md`, `CHANGELOG.md` | Document the feature |

### 11.1 The narration hook (both orchestrators)

Classic REPL — `agent-torvalds.py`:

```python
response, stats = await prompt_handler(cmd, agent, enable_stats=stats_enabled,
                                       event_consumer=event_consumer)
...
console.rule("[blue]Agent Response[/blue]")
console.print(Markdown(response))
console.rule()

# --- voice ---
if voice_session is not None:
    voice_session.narrate(response)      # non-blocking
```

TUI — `agent-torvalds-mw.py` / `components/tui/tui_app.py`:

```python
response, stats = await self.prompt_handler_fn(...)
self.state.set_markdown_content(response)
if self.voice_session is not None:
    self.voice_session.narrate(response)  # non-blocking
```

Because `narrate()` returns immediately, the TUI's render loop is unaffected.

### 11.2 Interruption (barge-in)

The classic REPL already handles `KeyboardInterrupt` around `console.input`.
The TUI has an `input_reader` and a key handler. Both call:

```python
voice_session.stop()      # terminate the player process
```

before dispatching the new input, so typing during playback cuts the audio
short rather than queueing behind it.

---

## 12. Configuration Reference

### 12.1 Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `TORVALDS_VOICE_ENABLED` | `false` | Master switch. Voice is **off** by default. |
| `TORVALDS_VOICE_TRIGGER` | `never` | `never` · `on_response` · `announce` |
| `TORVALDS_VOICE_BACKEND` | `http` | `http` · `cli` · `capi` · `none` |
| `TORVALDS_VOICE_SERVER_URL` | `http://127.0.0.1:8080` | `audiocpp_server` base URL |
| `TORVALDS_VOICE_SERVER_MODEL` | *(empty)* | Model id registered in the server config |
| `TORVALDS_VOICE_CLI_PATH` | *(empty)* | Path to `audiocpp_cli` |
| `TORVALDS_VOICE_CLI_FAMILY` | *(empty)* | e.g. `kokoro_tts` |
| `TORVALDS_VOICE_CLI_MODEL` | *(empty)* | Path to the GGUF |
| `TORVALDS_VOICE_CLI_BACKEND` | `cuda` | `cuda` · `cpu` · `vulkan` · `metal` |
| `TORVALDS_VOICE_OUTPUT` | `speaker` | `speaker` · `file` · `none` |
| `TORVALDS_VOICE_DIR` | `~/.cache/torvalds/voice` | Where `file` output is written |
| `TORVALDS_VOICE_ID` | *(empty)* | Preset voice id, e.g. `af_heart` |
| `TORVALDS_VOICE_REF` | *(empty)* | Reference WAV for cloning |
| `TORVALDS_VOICE_REF_TEXT` | *(empty)* | Transcript of the reference audio |
| `TORVALDS_VOICE_LANGUAGE` | *(empty)* | Language code; must match the voice |
| `TORVALDS_VOICE_SPEAK_CODE` | `false` | Speak fenced code blocks |
| `TORVALDS_VOICE_REDACT` | `true` | Redact secret-looking strings |
| `TORVALDS_VOICE_MAX_CHARS` | `1200` | Chunk budget per utterance |
| `TORVALDS_VOICE_TIMEOUT` | `30` | Per-request timeout, seconds |

### 12.2 CLI flags

`--voice` / `--no-voice` (enable/disable), `--voice-trigger`,
`--voice-backend`, `--voice-server-url`, `--voice-model`, `--voice-id`,
`--voice-language`, `--voice-output`, `--voice-dir`, `--voice-timeout`.

CLI flags override environment variables, exactly as `--hitl-timeout` overrides
`TORVALDS_HITL_TIMEOUT`.

### 12.3 Recommended `audiocpp_server` config

```json
{
  "host": "127.0.0.1",
  "port": 8080,
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
      "id": "torvalds-voice",
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

---

## 13. Implementation Plan

### Phase 0 — Foundation (no behaviour change)

| Item | Detail |
|---|---|
| `toolkits/audio-toolkit/` skeleton | `errors.py`, `config.py`, `text.py` |
| `text.py` | `to_speakable_text()`, `chunk_text()`, `redact()` — pure functions, fully unit-tested |
| `tests/test_voice_text.py` | Table-driven tests: headings, emphasis, code blocks, lists, tables, URLs, unicode punctuation, chunk boundaries, redaction patterns |
| Exit criterion | `pytest tests/test_voice_text.py` green; no agent files touched |

**Why first:** the text layer is where the quality lives, it is the cheapest to
test, and it is completely independent of `audio.cpp`.

### Phase 1 — Backend + output (the engine half)

| Item | Detail |
|---|---|
| `backends/base.py` | `SpeechBackend`, `SpeechRequest`, `SpeechResult` |
| `backends/http.py` | `audiocpp_server` client: `probe`, `list_voices`, `synthesize`, error mapping |
| `backends/cli.py` | `audiocpp_cli` subprocess backend, `--request-sequence` for multi-chunk |
| `backends/capi.py` | **Stub** — raises `VOICE_BACKEND_UNAVAILABLE` with a build hint |
| `output.py` | `SpeakerSink` (ffplay → aplay), `FileSink`, `NullSink`; device detection |
| `voices.py` | Catalogue normalisation across backends + capability probing |
| `tests/test_voice_backends.py` | Contract tests against a mocked HTTP server and a mocked subprocess |
| Exit criterion | The backends pass the same contract test suite |

### Phase 2 — The unified interface (the seam)

| Item | Detail |
|---|---|
| `components/voice/config.py` | `VoiceConfig` resolution: env → CLI override |
| `components/voice/session.py` | `VoiceSessionManager`: backend selection, fallback, worker thread, `stop()` |
| `components/voice/narrator.py` | The post-response hook: prepare → dispatch → play |
| `tests/test_voice_session.py` | Manager behaviour: fallback, no-backend, stop, non-blocking |
| Exit criterion | The manager can speak a string to a file sink in a unit test |

### Phase 3 — Agent integration (the product)

| Item | Detail |
|---|---|
| `agent_voice_toolkit.py` | The adapter: four tools, `Category: Voice` |
| `agent_tool_retriever.py` | `include_voice_tools` flag + load path |
| `agent_tool_selection.py` | `_discover_tools()` + a dedicated Voice action pattern |
| `agent-torvalds.py` | CLI flags, manager construction, `narrate()` hook, `\voice` dispatch |
| `agent-torvalds-mw.py` | Same, plus the TUI state fields and the telemetry pane entry |
| `components/command_registry.py` | `FEATURE_VOICE` + the eight command specs |
| `components/tui/state_bridge.py` | `voice_active`, `voice_status`, `voice_last_spoken` |
| `tests/test_voice_toolkit.py` | Adapter contract |
| `tests/test_voice_menu.py` | The Voice category is reachable through **every** load path (mirrors `TestMenuParity`) |
| Exit criterion | `--voice` on the classic REPL speaks the answer; the `--select` menu shows a Voice category; the agent can call `speak_text` |

### Phase 4 — Hardening

| Item | Detail |
|---|---|
| Barge-in | `stop()` wired into the REPL's `KeyboardInterrupt` path and the TUI key handler |
| Secret redaction | End-to-end test with a fake API key in the response |
| Long-answer handling | A 20 000-character response speaks in order, in bounded chunks |
| Degradation | Server down → CLI fallback → silent disable, each verified |
| Headless | No audio device → automatic fallback to `file` output with a notice |

### Phase 5 — Optional (each is a separate decision)

| Item | Note |
|---|---|
| `capi` backend | Requires the third-party rebuild; only worth it if the HTTP hop ever shows up in a profile |
| Streaming TTS | `mode: streaming` + SSE; lowers time-to-first-audio for long answers |
| `transcribe_audio` tool | Wraps `/v1/audio/transcriptions`; the ASR half of Capability C |
| Voice cloning | Requires a cloning-capable model (MagpieTTS, OmniVoice, VoxCPM2) and a reference WAV |

**Scope discipline:** Phases 0–4 constitute the deliverable "the agent can
produce voice". Phase 5 is explicitly out of the initial scope and is
individually approvable.

---

## 14. Risks & Mitigations

See the full register in the investigation report (§8). The four that shape the
implementation:

| Risk | Mitigation | Where it lives |
|---|---|---|
| **The agent boot breaks without `audio.cpp`** | The core package is imported in a `try/except`; `get_all_tools()` returns `[]`; the manager is constructed lazily and probes the backend. A missing `ffplay` is detected at sink-selection time, not import time. | `agent_voice_toolkit.py`, `components/voice/session.py` |
| **The TUI terminal is corrupted by the player** | `ffplay -nodisp`, `stdout`/`stderr` → `DEVNULL`, the player never inherits the TUI terminal. The TUI renders the voice state in its own pane. | `output.py` |
| **The agent reads secrets aloud** | Redaction is **on by default**; code blocks are skipped by default; the voice feature is **off by default**; the full text is still printed. | `text.py` |
| **The render loop blocks on synthesis** | `narrate()` is non-blocking by contract; synthesis and playback run in a worker thread; the TUI never awaits speech. | `components/voice/session.py` |

---

## 15. Success Metrics

| Metric | Target | How it is measured |
|---|---|---|
| Agent boot time with voice enabled | +< 50 ms | The manager is lazy; the backend is probed in the background |
| Time to first audio, typical response | < 1.5 s | `wall_ms` from the backend + player start-up |
| Synthesis RTF (Kokoro, CUDA) | < 0.15 | `--metrics` / server `timing` |
| Response latency impact (classic REPL) | 0 ms blocking | `narrate()` returns before the next prompt is shown |
| Turn success rate with the server down | 100 % (text unaffected) | Degradation test |
| Toolkit convention compliance | 100 % | The `TestMenuParity` mirror test |
| Test coverage of `text.py` | > 90 % | `pytest --cov` |
| Secret leakage in spoken output | 0 | Redaction test with a seeded key set |

---

## 16. Open Questions

These need an operator decision before Phase 3 closes:

1. **Default voice.** Which preset should be the default for the `torvalds-voice`
   model id? Kokoro ships 54 presets across 9 languages
   (`af_heart`, `bf_emma`, `zf_xiaobei`, …). The English set is the obvious
   default; the multilingual choice matters for a non-English operator.
2. **Should the agent speak by default once enabled?** Currently
   `TORVALDS_VOICE_ENABLED=1` implies `trigger=on_response`. A more
   conservative option is `enabled` + `trigger=announce`, so only the
   agent's *own* announcements are spoken until the operator opts into
   "speak every answer".
3. **Is a "Torvalds voice" (cloned) required?** Cloning needs a
   cloning-capable family (MagpieTTS 1.9 GB, OmniVoice 1.2 GB) rather than
   Kokoro's 212 MB preset-only model, and a reference recording. The VRAM
   budget allows it; the recording is an operator task.
4. **Should the spoken text be persisted in the chat history?** The chat
   memory already stores the response; storing the *spoken* variant separately
   would let a future search find "what the agent said aloud".
5. **Is the `audiocpp_server` lifecycle managed by the agent?** Options:
   (a) the operator runs it (recommended — it keeps the model warm across
   turns); (b) the agent spawns it on demand and reaps it on exit;
   (c) a systemd user unit. Option (a) is the simplest and is what the
   proposal assumes.
6. **Multi-turn continuity.** Should consecutive answers be spoken as one
   continuous stream (sentence-level streaming) rather than one file per
   turn? This is the `mode: streaming` route and it needs a different audio
   path (a persistent player fed by a pipe).

---

*Next step: operator review of this proposal, then Phase 0 in the
`self-development` clone on a `feature/voice-toolkit` branch.*
