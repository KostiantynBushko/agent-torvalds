# IMPLEMENTATION PLAN: Voice Output Component

**Date:** 2026-10-22 (reworked)
**Repository:** agent-torvalds
**Branch:** `feature/voice-toolkit` (in the `self-development` clone, off `master` @ `e21d97c`)
**Status:** Planned — Phase 0 not yet started
**Estimated Effort:** ~8.5 working days (was ~9.5 in the toolkit plan)
**Authoritative design:** [PROPOSAL_voice_output.md](PROPOSAL_voice_output.md)
**Evidence base:** [INVESTIGATION_REPORT.md](INVESTIGATION_REPORT.md)

> ⚠️ **All work happens in the `self-development` clone only.** The main
> checkout is the operator's working copy and is read-only for this work
> (Rule 1 & Rule 2 of `SELF_DEVELOPMENT_RULES.md`). Nothing in this plan may
> touch the main repository.
>
> ⚠️ **Commits and pushes require explicit operator approval** (Rule 4). Each
> phase below ends with a "checkpoint" that presents `git status` and
> `git diff` for review. Do not commit on your own initiative.

> ## ⚠️ A listening proposal exists — Q9 is reopened
>
> The operator asked whether the *listening* half (ASR) should be combined
> with the *speaking* half in one module. The answer is **yes, with a
> caveat**, and it is written up in
> **[`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md)**.
>
> **What it changes in this plan:**
>
> - **Appendix C, Q9** ("Should the component be able to *receive* speech
>   (ASR)?") is **reopened**. The answer recorded there — "No, it is a
>   different product" — is **correct for continuous listening (L2) and
>   wrong for push-to-talk dictation (L1)**.
> - **Nothing else in this plan changes.** Phases 0–11 stand as written.
>
> **The shape it proposes:** one component (`components/voice/`) with two
> managers (`VoiceSessionManager` and `ListeningSessionManager`), one
> server, one command family (`\voice`), one error table, and — importantly
> — **the microphone gets its own switch, off by default**, independent of
> the speaker. The "no LLM-facing tools" decision is preserved.
>
> **It is not part of this plan yet.** The input half would become
> Phases 12–18, and it is **parallel** to Phases 0–11, not sequential: it
> depends only on the shared transport and the command registry, not on the
> text layer, the sinks, the catalogue or the TTS backends. It becomes part
> of the plan when the operator answers LQ1–LQ9 in the listening proposal.

---

## Table of Contents

0. [Summary of the rework](#0-summary-of-the-rework)
1. [What changed and why](#1-what-changed-and-why)
2. [The On/Off Switch](#2-the-onoff-switch)
3. [The Default Voice](#3-the-default-voice)
4. [Preconditions](#4-preconditions)
5. [Phase 0 — Branch & Scaffolding](#5-phase-0--branch--scaffolding)
6. [Phase 1 — The Text Preparation Layer](#6-phase-1--the-text-preparation-layer)
7. [Phase 2 — The Backend Contract & the HTTP Backend](#7-phase-2--the-backend-contract--the-http-backend)
8. [Phase 3 — The CLI Backend & the Output Sinks](#8-phase-3--the-cli-backend--the-output-sinks)
9. [Phase 4 — The Voice Catalogue](#9-phase-4--the-voice-catalogue)
10. [Phase 5 — Configuration](#10-phase-5--configuration)
11. [Phase 6 — The Voice Session Manager](#11-phase-6--the-voice-session-manager)
12. [Phase 7 — The Narration Hook](#12-phase-7--the-narration-hook)
13. [Phase 8 — The Command Surface](#13-phase-8--the-command-surface)
14. [Phase 9 — Orchestrator Integration](#14-phase-9--orchestrator-integration)
15. [Phase 10 — Hardening](#15-phase-10--hardening)
16. [Phase 11 — Documentation](#16-phase-11--documentation)
17. [Definition of Done](#17-definition-of-done)
18. [Appendix A — Error Code Table](#18-appendix-a--error-code-table)
19. [Appendix B — File Manifest](#19-appendix-b--file-manifest)
20. [Appendix C — Open Questions](#20-appendix-c--open-questions)
21. [Appendix D — What was removed from the toolkit plan](#21-appendix-d--what-was-removed-from-the-toolkit-plan)

---

## 0. Summary of the rework

The first version of this plan built the voice feature as a **toolkit** — a
`toolkits/audio-toolkit/` library plus an `agent_voice_toolkit.py` LlamaIndex
adapter that exposed four tools (`speak_text`, `list_voices`,
`stop_speaking`, `transcribe_audio`) to the model.

**That was the wrong shape.** Voice is not a capability the *model* invokes;
it is a facility the *agent runtime* uses. The repository already has the
convention for exactly that, and it is written down in `components/README.md`:

> **Note:** This folder contains **helper components and utility modules**,
> NOT the agent's callable tools.
> - **Agent Tools** = The MCP functions the agent can invoke
> - **Components** = Internal helper modules that support the agent's
>   infrastructure

So the feature becomes **`components/voice/`** — a self-contained internal
component with an **on/off switch** that the operator can flip at runtime.

### 0.1 What changed, and why

| # | Before (toolkit plan) | Now (component plan) | Why |
|---|---|---|---|
| 1 | `toolkits/audio-toolkit/` — a separate, distributable library | `components/voice/` — an internal component package | Voice is infrastructure, not a model capability. The `components/` convention already exists for this. |
| 2 | `agent_voice_toolkit.py` — a LlamaIndex adapter with four tools | **removed** | The model has no business deciding *when* to speak. A tool surface also drags the feature into the retriever, the `--select` menu and the top-k retrieval budget for no benefit. |
| 3 | A `Category: Voice` entry in the startup tool menu | **removed** | There is nothing to select: the component is not a tool. |
| 4 | `include_voice_tools` in `agent_tool_retriever.py` | **removed** | No tools to retrieve. |
| 5 | `pytest.ini` — a testpath for `toolkits/audio-toolkit/tests` | **removed** | The tests live in `tests/`, which is **already** collected. `pytest.ini` does not change at all. |
| 6 | An `audio_toolkit` alias in `toolkits/__init__.py` | **removed** | `components.voice` is an ordinary, importable package — no alias needed. |
| 7 | The trigger axis was driven by an LLM tool | The trigger axis is driven by the **runtime** | `on_response` narrates the answer; `announce` speaks what the runtime explicitly hands over. |
| 8 | A "Torvalds voice" (a clone) was on the table | **The `af_heart` preset** | Decided: no clone. Kokoro is a preset-voice model (`supports_speaker_reference=false`) and cannot clone. See §3. |
| 9 | "Off" meant "no Voice category in the menu" | "Off" means **the component does not run** | A component that is switched off must be indistinguishable from one that was never installed: no backend probe, no worker thread, no playback, no import cost. |

### 0.2 What did **not** change

The engineering content of the feature is untouched. The reworked plan keeps
the text-preparation layer, the backend contract, the HTTP and CLI backends,
the output sinks, the voice catalogue, the redaction rules, the
non-blocking contract, the barge-in path, the degradation ladder and the
error-code table exactly as they were. They simply move from
`toolkits/audio-toolkit/**` to `components/voice/**`, and the toolkit
adapter phase is replaced by the on/off switch and the command surface.

---

## 1. What changed and why

*(See §0 above — the rework summary table.)*

The rest of this plan assumes the component shape. The rules that follow from
it are **binding**.

### 1.1 The layering rules (rewritten)

The old rules had three layers (core library → adapter → component). The
component shape has two:

| Layer | May import | Must **NOT** import |
|---|---|---|
| `components/voice/**` | stdlib, `requests` (optional, lazy), other `components.*` that do not import `llama_index` | `llama_index.*`, any `agent_*.py`, any `toolkits.*` |
| `agent-torvalds*.py` | `components.voice` | `components.voice` internals (only the public API) |

**There is no adapter layer.** A `components/voice/**` module that imports
`llama_index` or an `agent_*.py` module is a defect, and Phase 10 enforces
it mechanically with a test.

### 1.2 The public API of the component

Everything outside `components/voice/` may only use these names:

```python
from components.voice import (
    VoiceConfig,           # the frozen configuration object
    VoiceTrigger,          # never | on_response | announce
    VoiceBackend,          # none | http | cli | capi
    VoiceOutput,           # none | speaker | file
    VoiceSessionManager,   # the runtime facade
    build_voice_config,    # env + CLI -> VoiceConfig
    narrate_response,      # the post-response hook
    get_voice_manager,     # the process-wide instance
    set_voice_manager,
    close_voice_manager,
)
```

plus the two command helpers:

```python
from components.voice.commands import is_voice_command, handle_voice_command
```

---

## 2. The On/Off Switch

This is the feature's defining property: **the operator can turn voice on and
off, and "off" costs nothing.**

### 2.1 Three levels of control

| Level | Mechanism | Effect |
|---|---|---|
| **Environment** | `TORVALDS_VOICE_ENABLED` | The **initial** state of the component. Default `false`. |
| **CLI** | `--voice` / `--no-voice` | Overrides the environment for this session. |
| **Runtime** | `\voice on` / `\voice off` / `\voice toggle` | Flips the state mid-session, without a restart. |

This mirrors the HITL feature exactly (`TORVALDS_HITL_ENABLED` →
`--no-hitl` → `\toggle-hitl`), so the operator already knows the pattern.

### 2.2 What "off" means — the hard guarantee

When the component is **off**, all of the following are true:

- [ ] no backend is probed (no HTTP request, no subprocess);
- [ ] no worker thread is created (the `ThreadPoolExecutor` is not started);
- [ ] no audio file is written;
- [ ] `narrate()` and `announce()` return immediately, in well under a millisecond;
- [ ] the agent's response rendering is **byte-identical** to a build without
      the component;
- [ ] the agent's boot time is not measurably different.

The component is *present* in the repository — it is not a plugin that has to
be installed — but it is **inert**. Phase 10 verifies this with a test that
asserts no backend was constructed and no thread was started.

### 2.3 Turning it on at runtime

`\voice on` must work even when the component was off at boot. That means
the manager is **always constructed** (it is a cheap object), but the
**backend is constructed lazily**, on the first synthesis after the
component is enabled. The lazy construction is what keeps the "off" case free
and what makes the runtime switch instant.

### 2.4 The trigger axis

The three-axis model from the proposal survives, but the first axis is now
driven by the runtime instead of by a tool:

| Value | Behaviour |
|---|---|
| `never` | The component never speaks on its own. Only an explicit `speak()` (from the `\voice speak` command) produces audio. |
| `on_response` | **The default.** Every final agent response is narrated. |
| `announce` | Only text handed to `announce()` is spoken. The response is *not* narrated. |

`announce()` is the hook for other components (for example, a future HITL
announcement: "the agent is asking you a question"). It is an ordinary Python
call — `voice_session.announce("...")` — not a tool.

### 2.5 The command surface

One command, with subcommands, registered once in the central registry:

| Command | Description |
|---|---|
| `\voice` | Show the voice status (enabled, trigger, backend, output, voice, device) |
| `\voice on` | Enable speaking |
| `\voice off` | Disable speaking |
| `\voice toggle` | Toggle speaking |
| `\voice trigger <t>` | Set the trigger axis (`never`, `on_response`, `announce`) |
| `\voice voice <id>` | Change the active preset voice |
| `\voice voices` | List the available voices |
| `\voice speak <text>` | Speak a line immediately, whatever the trigger is |
| `\voice stop` | Stop the current playback |
| `\voice test` | Synthesise and play a test phrase |
| `\voice help` | The cheat sheet |

The commands appear in `\help` under a new **Voice** category, and only when
the voice runtime toggle is permitted (`TORVALDS_VOICE_RUNTIME_TOGGLE`,
default `true`; `--no-voice-runtime-toggle` to remove them).

> **The commands are visible even when voice is off**, because `\voice on` is
> precisely how you turn it on. The status line shows the current state.

---

## 3. The Default Voice

**There is no "Torvalds voice".** The feature speaks with a stock preset from
the Kokoro catalogue, and that is the whole story for v1.

| Question | Answer |
|---|---|
| What is the default voice? | **`af_heart`** — a clear American English female preset. |
| Is there a cloned "Torvalds voice"? | **No.** Not now, and not with the current stack. |
| Why not? | Kokoro 82M is a **preset-voice** model: `supports_speaker_reference=false`. It has no cloning head, so a `voice_ref` is ignored by the model. Cloning needs a cloning-capable family (MagpieTTS 1.9 GB, OmniVoice 1.2 GB) **plus** a reference recording — an operator task, deferred. |
| What is `torvalds-voice` then? | Nothing. The model is registered under the id `kokoro` in the server config, which is more honest than pretending it is a persona. |
| Can the voice be changed? | Yes — `TORVALDS_VOICE_ID`, `--voice-id`, or `\voice voice <id>` at runtime. |

The full 54-voice catalogue is documented in `PROPOSAL_voice_output.md` §12.4.
`am_michael` and `am_onyx` are the male-American-English alternatives.

---

## 4. Preconditions

| # | Precondition | Status |
|---|---|---|
| P1 | Work happens **only** in the `self-development` clone | ✅ Rule 1 & 2 |
| P2 | Dedicated branch off `master` | ✅ `feature/voice-toolkit` created at `e21d97c` |
| P3 | `requests` importable in `self-development/.venv` | ✅ Verified (2.34.2) |
| P4 | `pytest` available in `self-development/.venv` | ✅ Verified (9.1.1) |
| P5 | `audio.cpp` built and `audiocpp_server` startable | ✅ Verified in the investigation (§7.4) |
| P6 | TTS weights present (`models/TTS/kokoro-82m-bf16.gguf`) | ✅ Verified (212 MB, 54 preset voices) |
| P7 | A playback binary available (`ffplay` or `aplay`) | ✅ `ffplay` present; `aplay` present |
| P8 | Baseline test suite recorded | ⬜ Run at Phase 0 (see Step 0.1) |
| P9 | Operator decisions on the Open Questions in Appendix C | ⬜ Needed before Phase 9 closes |

> **P8 matters.** The repository has a known set of pre-existing test
> failures. Record the baseline (fail count and pass count) in Phase 0 so
> that every later phase can be judged against it, instead of discovering
> at the end that a "new" failure was actually always there.

---

## 5. Phase 0 — Branch & Scaffolding

**Duration:** 0.5 day
**Goal:** an empty, correctly-shaped skeleton that imports cleanly and breaks
nothing.

### Step 0.1 — Record the baseline

```bash
cd self-development
.venv/bin/python -m pytest -q 2>&1 | tail -5
```

Write the exact numbers into the phase checkpoint. Every later phase must
reproduce this failure set byte-for-byte. A **new** failure is a regression
and blocks the phase.

### Step 0.2 — Create the component directory

```bash
cd self-development
mkdir -p components/voice/backends
```

**Naming is binding.** The package is `components/voice/` — a normal Python
package, imported as `components.voice`. It needs **no** import alias and
**no** `sys.modules` trickery, because the name is a valid identifier. (The
hyphen problem that forced the `toolkits.audio_toolkit` alias does not exist
here — which is one of the simpler wins of the component shape.)

### Step 0.3 — Create the package skeletons

Each file is created with its **final public API** and a `NotImplementedError`
(or an empty body) for the functions — the implementations land in the later
phases. This keeps every later step a pure *fill-in*, never a *redesign*.

| File | Contents in this phase |
|---|---|
| `components/voice/__init__.py` | Docstring + `__all__` + the public API re-exports |
| `components/voice/errors.py` | `VoiceError` + the `VoiceErrorCode` constants (Appendix A) |
| `components/voice/config.py` | `VoiceConfig` dataclass + `VoiceTrigger`/`VoiceBackend`/`VoiceOutput` enums + `build_voice_config()` — **stub** |
| `components/voice/text.py` | `to_speakable_text()`, `chunk_text()`, `redact()` — **stub** |
| `components/voice/voices.py` | Voice catalogue normalisation — **stub** |
| `components/voice/output.py` | `SpeakerSink`, `FileSink`, `NullSink`, `PlaybackHandle` — **stub** |
| `components/voice/backends/__init__.py` | Re-exports the backend API |
| `components/voice/backends/base.py` | `SpeechBackend` ABC, `SpeechRequest`, `SpeechResult`, `BackendStatus` |
| `components/voice/backends/http.py` | `HttpSpeechBackend` — **stub** |
| `components/voice/backends/cli.py` | `CliSpeechBackend` — **stub** |
| `components/voice/backends/capi.py` | `CApiSpeechBackend` — **stub that raises** (Phase 3) |
| `components/voice/session.py` | `VoiceSessionManager` — **stub** |
| `components/voice/narrator.py` | `narrate_response()` — **stub** |
| `components/voice/commands.py` | `is_voice_command()`, `handle_voice_command()` — **stub** |
| `components/voice/runtime.py` | `get_voice_manager()`, `set_voice_manager()`, `close_voice_manager()` |

### Step 0.4 — The binding import rules

These rules are **not** negotiable. They are the house pattern, restated in
§1.1:

| Layer | May import | Must **NOT** import |
|---|---|---|
| `components/voice/**` | stdlib, `requests` (optional, lazy) | `llama_index.*`, any `agent_*.py`, any `toolkits.*` |
| `agent-torvalds*.py` | `components.voice` (public API only) | `components.voice` internals |

The dependency direction is strictly inward: **orchestrator → component**.
A test in Phase 10 enforces it mechanically.

> **Note what is *not* in this table.** There is no adapter layer, so there
> is no `llama_index.core.tools` anywhere in the feature. The component never
> appears in `agent_tool_retriever.py`, `agent_tool_selection.py` or
> `_collect_all_tools()`.

### Step 0.5 — Register the test path

**Nothing to do.** `pytest.ini` already has `testpaths = tests …`, and the
component's tests go into the root `tests/` directory, next to every other
component's tests (`tests/test_hitl_no_timeout.py`,
`tests/test_ollama_config.py`, `tests/test_help_command.py`, …).

This is the second simplification the component shape buys: the toolkit
version had to add a testpath and fight pytest's import-mode rules, because
`toolkits/audio-toolkit/` is a hyphenated directory. `tests/` has neither
problem.

### Step 0.6 — Phase 0 checkpoint

- [ ] `import components.voice` succeeds
- [ ] `from components.voice import VoiceSessionManager, build_voice_config` works
- [ ] `self-development/.venv/bin/python -m pytest -q` reports the **same** failure set as the baseline
- [ ] `git status` shows only the new files
- [ ] Present the diff to the operator; **do not commit** without approval

---

## 6. Phase 1 — The Text Preparation Layer

**Duration:** 1 day
**Location:** `self-development/components/voice/text.py`
**Why first:** this is where the quality of the feature lives, it is the
cheapest thing to test, and it has **zero** dependency on `audio.cpp`.

### Step 1.1 — `to_speakable_text(markdown: str) -> str`

The single rule: **the output contains no Markdown punctuation at all.**

| Input | Output |
|---|---|
| `## Heading` | `Heading` |
| `**bold**` | `bold` |
| `_italic_` | `italic` |
| ```` ```code``` ```` | *(omitted)* or `Code block omitted.` |
| `> quote` | `quote` |
| `- item` / `1. item` | `item.` |
| `---` | *(removed)* |
| `https://example.com/x` | `link` |
| `\| a \| b \|` | *(removed — tables are unreadable aloud)* |
| `` `inline_code` `` | `inline code` |
| `—` / `–` | `, ` / `, ` |

Implementation requirements:

- Process **fenced code blocks first**, before any other rule — otherwise a
  `#` inside a code block would be read as a heading.
- Handle **both** `~~~` and ` ``` ` fences, and unterminated fences (the rest
  of the document is code).
- Strip **inline code** backticks but keep the content.
- Remove Markdown **tables** — a pipe-delimited row read aloud is noise.
- Replace **URLs** with the word `link`. A bare `www.` prefix is handled too.
- Convert **list items** into sentences with a trailing period, so the chunker
  sees clean sentence boundaries.
- Normalise **Unicode punctuation**: `—`/`–` → `, `, `…` → `...`, curly
  quotes → straight quotes, and collapse repeated whitespace.
- The function must be **idempotent**: `to_speakable_text(to_speakable_text(x)) == to_speakable_text(x)`.

### Step 1.2 — `chunk_text(text: str, max_chars: int, min_chars: int) -> list[str]`

Sentence-aware, in this order:

1. Split on sentence terminators (`.`, `!`, `?`, `…`, plus CJK `。！？`),
   **keeping** the terminator.
2. Split over-long sentences on `,` / `;` / ` — `.
3. Split anything still too long on whitespace.
4. Pack consecutive sentences into chunks up to `max_chars`.
5. Never emit a chunk shorter than `min_chars` **unless it is the last one**.

Edge cases that must be covered by tests: empty input, whitespace-only input,
a single sentence longer than `max_chars`, a text with no sentence terminator
at all, and CJK text with no spaces.

### Step 1.3 — `redact(text: str) -> str`

Applied by default. Replaces the match with `[redacted]`.

| Pattern | Example |
|---|---|
| OpenAI-style | `sk-…` |
| GitHub tokens | `ghp_…`, `gho_…`, `ghu_…`, `ghs_…`, `ghr_…`, `github_pat_…` |
| Bearer tokens | `Bearer <token>` |
| AWS access key ids | `AKIA…` |
| Slack tokens | `xox[baprs]-…` |
| JWTs | `eyJ….eyJ….…` |
| PEM private keys | `-----BEGIN … PRIVATE KEY-----` blocks |
| Assignments | `password=…`, `api_key=…`, `secret=…`, `token=…` |

Requirements:

- The `[redacted]` marker itself must not be re-redacted (idempotence).
- A PEM block is replaced **whole**, including the newlines.
- The redaction must be applied to the text **after** Markdown stripping, so
  that a key inside a code fence is caught by the code-fence rule *and* the
  redaction rule independently.

### Step 1.4 — `tests/test_voice_text.py`

Table-driven, one row per case. Minimum coverage:

- [ ] every row of the `to_speakable_text` table above
- [ ] a heading inside a code block is **not** treated as a heading
- [ ] an unterminated fence swallows the rest of the document
- [ ] `to_speakable_text` is idempotent
- [ ] chunk boundaries never split a sentence
- [ ] the last chunk may be shorter than `min_chars`; no other may
- [ ] a single sentence longer than `max_chars` is split on whitespace
- [ ] CJK text is chunked on `。！？`
- [ ] empty and whitespace-only input return `[]` / `""`
- [ ] every redaction pattern in the table above
- [ ] a seeded corpus of 20 fake secrets is fully redacted

**Exit criterion:** `pytest tests/test_voice_text.py -q` is green, and the
coverage of `text.py` exceeds 90 %.

---

## 7. Phase 2 — The Backend Contract & the HTTP Backend

**Duration:** 1 day
**Location:** `components/voice/backends/base.py`, `components/voice/backends/http.py`

### Step 2.1 — The contract

```python
class SpeechBackend(ABC):
    @abstractmethod
    def probe(self) -> BackendStatus: ...
    @abstractmethod
    def list_voices(self, model: str = "") -> list[dict]: ...
    @abstractmethod
    def synthesize(self, request: SpeechRequest) -> SpeechResult: ...
```

`SpeechRequest` carries `text`, `voice_id`, `language`, `seed`.

`SpeechResult` carries `ok`, `audio_path`, `audio_bytes`, `sample_rate`,
`duration_ms`, `wall_ms`, `rtf`, `error`, `detail`.

`BackendStatus` carries `ok`, `available`, `detail`, and the backend's
`capabilities` block.

**Binding rules:**

- `synthesize()` **never raises**. Every failure becomes
  `SpeechResult(ok=False, error=<CODE>, detail=<human text>)`.
- `probe()` **never raises** either — a backend that cannot be reached
  reports `available=False`, it does not explode.

### Step 2.2 — `HttpSpeechBackend`

| Operation | Request |
|---|---|
| `probe()` | `GET {base_url}/health` |
| `list_voices()` | `GET {base_url}/v1/audio/voices?model={id}` |
| `synthesize()` | `POST {base_url}/v1/audio/speech` |

The TTS body is the OpenAI speech shape, extended with `audio.cpp`'s fields:

```json
{
  "model": "<server_model>",
  "input": "<text>",
  "voice": "<voice_id>",
  "response_format": "wav",
  "seed": 1234
}
```

**Error mapping** (binding — the codes in Appendix A):

| Condition | Code |
|---|---|
| HTTP 200 | ok |
| HTTP 404 | `VOICE_MODEL_NOT_FOUND` |
| HTTP 503 + body `server_busy` | `VOICE_SERVER_BUSY` |
| HTTP 503 + body `insufficient_memory` | `VOICE_INSUFFICIENT_MEMORY` |
| HTTP 400 / 422 | `VOICE_BAD_REQUEST` |
| Connection refused / DNS failure | `VOICE_SERVER_UNAVAILABLE` |
| Timeout | `VOICE_TIMEOUT` |
| Any other HTTP status | `VOICE_BAD_REQUEST` (with the status in `detail`) |

The client sends `busy_timeout_ms` in the body so it can bound its own wait.
The server clamps this value to its own ceiling, so the client can only ever
**shorten** the wait — never weaken the guard.

**Requirements:**

- `requests` is imported **inside** the method, in a `try/except`; a missing
  `requests` degrades the backend to unavailable rather than breaking the
  import. (The import cost of the component must stay at zero when the
  feature is off — see §2.2.)
- The base URL is normalised: a bare `host:port` becomes `http://host:port`
  (the same rule as `components/ollama_config.py`).
- A trailing slash on the base URL is stripped, so `http://host:8080/` and
  `http://host:8080` behave identically.
- The response body is read as **bytes**; the WAV header is inspected to
  recover the sample rate and the duration, so the result reports real
  numbers without an extra dependency.

### Step 2.3 — `tests/test_voice_backends.py` (the HTTP half)

No network access. The transport is mocked.

- [ ] `probe()` returns `available=True` for a healthy `/health` response
- [ ] `probe()` returns `available=False` on a connection error
- [ ] every row of the error-mapping table above
- [ ] the request body carries `model`, `input` and `voice`
- [ ] `busy_timeout_ms` is present in the body
- [ ] the base URL is normalised in all three shapes
- [ ] a WAV response yields the correct `sample_rate` and `duration_ms`
- [ ] `synthesize()` never raises, even for a malformed body

---

## 8. Phase 3 — The CLI Backend & the Output Sinks

**Duration:** 1 day
**Location:** `components/voice/backends/cli.py`, `components/voice/backends/capi.py`, `components/voice/output.py`

### Step 3.1 — `CliSpeechBackend`

Invokes:

```
audiocpp_cli --task tts --family <family> --model <path> --backend <backend> \
             --voice-id <id> --language <lang> --text <text> --out <tmp.wav> --metrics
```

For **multi-chunk** text it uses `--request-sequence <json>` so that one
process serves every chunk against a **warm** session — the CLI's batch mode
does the chunking and the merge internally.

**Metric parsing.** The CLI emits `metrics.*` lines. Parse `wall_ms`,
`audio_duration_ms`, `rtf`, `sample_rate`, `channels` with a regex over
`key=value` pairs. A missing metric is `0.0`, never an exception.

**Failure detection:** a non-zero exit status, or a missing output file, or
an empty output file. The **tail of stderr** (truncated to ~500 characters)
goes into `detail` for diagnostics.

**Timeouts:** the subprocess is killed after `timeout_s`. The temporary file is
always cleaned up, including on the timeout path.

### Step 3.2 — `CApiSpeechBackend` (a deliberate stub)

This ships as a stub that **always** fails with
`VOICE_BACKEND_UNAVAILABLE` and a `detail` explaining the build prerequisite:

```bash
cmake -S . -B build/linux-cuda-release \
  -DENGINE_ENABLE_CUDA=ON -DAUDIOCPP_BUILD_C_API=ON
cmake --build build/linux-cuda-release --target audiocpp_c_api
```

The stub exists so the *interface* is settled and a later spike is an
implementation rather than a redesign. It is **not** wired into the default
configuration.

### Step 3.3 — The output sinks

```python
class AudioSink(ABC):
    @abstractmethod
    def play(self, wav_path: str) -> PlaybackHandle: ...
    @abstractmethod
    def available(self) -> bool: ...
```

| Sink | Behaviour |
|---|---|
| `SpeakerSink` | `ffplay -nodisp -autoexit -loglevel quiet <wav>`, falling back to `aplay` |
| `FileSink` | writes `<output_dir>/torvalds-<timestamp>-<n>.wav` |
| `NullSink` | synthesises and discards |

**Binding requirements for `SpeakerSink`:**

- `stdout` and `stderr` go to `subprocess.DEVNULL`. The player must **never**
  write to the terminal the TUI owns (risk R2).
- The `Popen` handle is **retained** on the `PlaybackHandle` so that `stop()`
  can `terminate()` it. This is what makes barge-in possible.
- `terminate()` is called on a grace period, then `kill()` if the process
  does not exit.
- The player is started in its **own process group** (`start_new_session=True`)
  so that terminating it does not signal the agent.

**Device detection.** If no playback device is present (an SSH session, a
container without `/dev/snd`), `available()` returns `False` and the manager
degrades to `FILE` output with a one-line notice. It never fails the turn.

### Step 3.4 — `tests/test_voice_backends.py` (the CLI half) & `tests/test_voice_output.py`

- [ ] the CLI command line is exactly as specified above
- [ ] `--request-sequence` is used for more than one chunk, and **not** used
      for a single chunk
- [ ] the `metrics.*` lines are parsed into the result
- [ ] a missing metric does not raise
- [ ] a non-zero exit produces `VOICE_BAD_REQUEST` with the stderr tail in `detail`
- [ ] the temporary file is removed on the success path **and** on the timeout path
- [ ] `SpeakerSink` builds the `ffplay` command with `-nodisp` and `DEVNULL`
- [ ] `stop()` terminates the player process (mocked `Popen`)
- [ ] `FileSink` writes a file with a `.wav` extension and a unique name
- [ ] `NullSink` writes nothing
- [ ] `available()` is `False` when neither `ffplay` nor `aplay` is on `PATH`

---

## 9. Phase 4 — The Voice Catalogue

**Duration:** 0.5 day
**Location:** `components/voice/voices.py`

### Step 4.1 — The normalised catalogue

Every backend returns the catalogue in its own shape. `voices.py` normalises
them into a single list of dictionaries:

```python
{
    "id": "af_heart",
    "name": "Heart",
    "language": "en-us",
    "gender": "female",
    "source": "preset",        # preset | library | cached
    "capabilities": {
        "preset_voices": True,
        "speaker_reference": False,
        "style_control": False,
    },
}
```

### Step 4.2 — The capability distinction (important)

Kokoro is a **preset-voice** model: `supports_speaker_reference=false`. It
cannot clone. MagpieTTS and OmniVoice can.

This distinction **must** survive into the catalogue, because *"make the agent
sound like X"* and *"make the agent sound like this specific recording"* are
different requests. The catalogue reports the capability block per model, so
the operator (and the `\voice voices` listing) can tell the difference
instead of guessing.

> In the toolkit plan this capability block existed so the *LLM* could reason
> about it. There is no LLM in the picture any more, so the block is now
> purely **informational** — it is shown in `\voice voices` and in
> `\voice status`. It is still worth keeping: it is the thing that tells the
> operator that the default backend cannot clone.

### Step 4.3 — The default voice (binding)

- [ ] the default `voice_id` is **`af_heart`**;
- [ ] an empty `TORVALDS_VOICE_ID` resolves to `af_heart`, **never** to
      "no voice" and **never** to a clone;
- [ ] there is **no** `torvalds-voice` id, no `torvalds` persona and no
      clone path in v1 — see §3;
- [ ] the `voice_ref` / `reference_text` config fields are **absent** from
      `VoiceConfig` (Phase 5, Step 5.1) — a field the default backend would
      silently ignore is worse than no field at all;
- [ ] the status output states that the active model cannot clone.

### Step 4.4 — `tests/test_voice_voices.py`

- [ ] the HTTP catalogue shape is normalised
- [ ] the CLI `--inspect` shape is normalised
- [ ] a model with no cloning support reports `speaker_reference: False`
- [ ] an empty catalogue returns `[]`, never `None`
- [ ] a malformed catalogue entry is skipped, not fatal
- [ ] the default voice is `af_heart` and the catalogue contains it

---

## 10. Phase 5 — Configuration

**Duration:** 0.5 day
**Location:** `components/voice/config.py`

### Step 5.1 — The axes and the dataclass

```python
class VoiceTrigger(str, Enum):
    NEVER       = "never"        # the component never speaks on its own
    ON_RESPONSE = "on_response"  # speak each final response (the default)
    ANNOUNCE    = "announce"     # only speak what the runtime hands over

class VoiceBackend(str, Enum):
    NONE = "none"   # no synthesis available
    HTTP = "http"   # audiocpp_server  (default)
    CLI  = "cli"    # audiocpp_cli
    CAPI = "capi"   # libaudiocpp, in-process (stub)

class VoiceOutput(str, Enum):
    NONE    = "none"     # synthesize and discard (diagnostics)
    SPEAKER = "speaker"  # play through the local audio device
    FILE    = "file"     # write WAV files into the voice directory
```

```python
@dataclass(frozen=True)
class VoiceConfig:
    # --- axis 1: trigger ---
    trigger: VoiceTrigger = VoiceTrigger.ON_RESPONSE

    # --- axis 2: backend ---
    backend: VoiceBackend = VoiceBackend.HTTP
    server_url: str = "http://127.0.0.1:8099"
    server_model: str = "kokoro"
    cli_path: str = ""
    cli_family: str = ""
    cli_model_path: str = ""
    cli_backend: str = "cuda"           # cuda | cpu | vulkan | metal
    timeout_s: float = 30.0

    # --- axis 3: output ---
    output: VoiceOutput = VoiceOutput.SPEAKER
    output_dir: str = ""                # for FILE output
    player_cmd: str = ""                # override; default auto-detected

    # --- voice selection ---
    voice_id: str = "af_heart"          # a Kokoro preset - see §3
    language: str = ""                  # must match the voice for Kokoro

    # --- behaviour ---
    speak_code_blocks: bool = False     # default: skip fenced code
    redact_secrets: bool = True
    max_chars: int = 1200               # per-utterance chunk budget
    min_chunk_chars: int = 120          # below this, merge with the next
    interruptible: bool = True
    rate_limit_s: float = 0.0           # min gap between utterances
```

> **`voice_ref` and `reference_text` are gone from the dataclass.** The
> default backend cannot clone, and a config field that is silently ignored
> is worse than no field at all. If a cloning-capable backend is ever added,
> the field comes back *with* that backend — and the status output says what
> it does.

### Step 5.2 — `build_voice_config(overrides=None, env=None) -> VoiceConfig`

Resolves the configuration from **environment → CLI override**, exactly as
`--hitl-timeout` overrides `TORVALDS_HITL_TIMEOUT`.

The resolution rules:

- The server URL is resolved in the order
  `TORVALDS_VOICE_SERVER_URL` → `AUDIO_CPP_SERVER_URL` → `http://127.0.0.1:8099`,
  mirroring the `components/ollama_config.py` precedent.
- The **voice id** defaults to `af_heart` — a Kokoro preset. The default is
  always a *preset*, never a clone.
- The **server model id** defaults to `kokoro`, the id the model is registered
  under in the server config.
- The output directory defaults to `~/.cache/torvalds/voice` and is created
  lazily, on first use.
- An **unknown value for any axis falls back to the documented default and
  logs a warning** — it never raises. A typo in an environment variable must
  not take the agent down.
- A malformed number (a non-numeric `TORVALDS_VOICE_TIMEOUT`) falls back to
  the default and warns, in the same way.

### Step 5.3 — The environment variable reference

| Variable | Default | Meaning |
|---|---|---|
| `TORVALDS_VOICE_ENABLED` | `false` | **The initial state of the component.** `false` = off. |
| `TORVALDS_VOICE_RUNTIME_TOGGLE` | `true` | Whether the `\voice` commands exist. |
| `TORVALDS_VOICE_TRIGGER` | `on_response` | `never` · `on_response` · `announce` |
| `TORVALDS_VOICE_BACKEND` | `http` | `none` · `http` · `cli` · `capi` |
| `TORVALDS_VOICE_SERVER_URL` | `http://127.0.0.1:8099` | `audiocpp_server` base URL |
| `TORVALDS_VOICE_SERVER_MODEL` | `kokoro` | Model id registered in the server config |
| `TORVALDS_VOICE_CLI_PATH` | *(empty)* | Path to `audiocpp_cli` |
| `TORVALDS_VOICE_CLI_FAMILY` | *(empty)* | e.g. `kokoro_tts` |
| `TORVALDS_VOICE_CLI_MODEL` | *(empty)* | Path to the GGUF |
| `TORVALDS_VOICE_CLI_BACKEND` | `cuda` | `cuda` · `cpu` · `vulkan` · `metal` |
| `TORVALDS_VOICE_OUTPUT` | `speaker` | `none` · `speaker` · `file` |
| `TORVALDS_VOICE_DIR` | `~/.cache/torvalds/voice` | Where `file` output is written |
| `TORVALDS_VOICE_ID` | `af_heart` | Preset voice id (see §3) |
| `TORVALDS_VOICE_LANGUAGE` | *(empty)* | Language code; must match the voice |
| `TORVALDS_VOICE_SPEAK_CODE` | `false` | Speak fenced code blocks |
| `TORVALDS_VOICE_REDACT` | `true` | Redact secret-looking strings |
| `TORVALDS_VOICE_MAX_CHARS` | `1200` | Chunk budget per utterance |
| `TORVALDS_VOICE_TIMEOUT` | `30` | Per-request timeout, seconds |

### Step 5.4 — `tests/test_voice_config.py`

- [ ] every environment variable is read
- [ ] the CLI override beats the environment variable
- [ ] an invalid enum value falls back to the default and **does not raise**
- [ ] an invalid number falls back to the default and does not raise
- [ ] the server URL falls back through `TORVALDS_VOICE_SERVER_URL` →
      `AUDIO_CPP_SERVER_URL` → the default
- [ ] the default voice id is `af_heart`
- [ ] the dataclass is frozen
- [ ] `VoiceConfig` has **no** `voice_ref` / `reference_text` field

---

## 11. Phase 6 — The Voice Session Manager

**Duration:** 1.5 days
**Location:** `components/voice/session.py`, `components/voice/runtime.py`

This is the phase that turns three capabilities into configurations of one
core — and that owns the on/off switch.

### Step 6.1 — `VoiceSessionManager`

The single object both orchestrators talk to.

```python
class VoiceSessionManager:
    def __init__(self, config: VoiceConfig) -> None: ...

    # --- the switch ---
    @property
    def enabled(self) -> bool: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...
    def toggle(self) -> bool: ...
    def set_trigger(self, trigger: VoiceTrigger) -> None: ...
    def set_voice(self, voice_id: str) -> None: ...

    # --- capability ---
    def available(self) -> bool: ...
    def status(self) -> dict: ...

    # --- production ---
    def narrate(self, text: str) -> None: ...          # NON-BLOCKING
    def announce(self, text: str) -> None: ...         # NON-BLOCKING
    async def speak(self, text: str, **opts) -> dict: ...
    def stop(self) -> bool: ...
    def list_voices(self) -> list[dict]: ...
    def probe(self) -> dict: ...
    def close(self) -> None: ...
```

**Binding contract for `narrate()` and `announce()`:** they prepare the text,
dispatch the synthesis to a worker thread and **return immediately**. The
caller never awaits them. This is what keeps the TUI render loop free (risk
R3).

**The "off" contract (binding, see §2.2).** When `enabled` is `False`:

- `narrate()` and `announce()` return immediately, without preparing the
  text, without constructing a backend and without starting a thread;
- `speak()` returns `{"ok": False, "error": "VOICE_DISABLED", ...}`;
- `available()` returns `False`;
- no backend is constructed — the backend is built **lazily**, on the first
  synthesis after the component is enabled.

**Backend selection and fallback.** If the configured backend's `probe()`
fails:

1. log a clear warning naming the backend and the reason;
2. fall back to `cli` **if** a CLI path is configured **and** the CLI backend
   probes OK;
3. otherwise disable voice (the trigger becomes effectively `never`) and
   **the agent continues normally**.

It **never** raises into the orchestrator.

**Worker thread.** A single `ThreadPoolExecutor(max_workers=1)` serialises
the speech, so two turns cannot overlap their audio. The executor is created
**on first use** and shut down on `stop()` / `close()`.

**`speak()`** is awaited and returns the structured result — this is the path
the `\voice speak` and `\voice test` commands use, where the operator wants
to know whether the utterance was produced.

### Step 6.2 — The process-wide instance (`components/voice/runtime.py`)

```python
_voice_manager: Optional[VoiceSessionManager] = None

def get_voice_manager() -> Optional[VoiceSessionManager]: ...
def set_voice_manager(manager: Optional[VoiceSessionManager]) -> None: ...
def close_voice_manager() -> None: ...
```

The orchestrators build the manager in `main()` (after the CLI flags are
parsed) and hand it over with `set_voice_manager()`. The command module
reads it with `get_voice_manager()`. `close_voice_manager()` stops the
playback and shuts the worker thread down — it is called on exit and on
`SIGTERM`.

This mirrors the way `human_loop_handler` and `hitl_toggle` are module-level
globals in the orchestrators, so the pattern is familiar.

### Step 6.3 — `tests/test_voice_session.py`

- [ ] `narrate()` returns in under 50 ms with a slow (mocked) backend
- [ ] a **disabled** manager creates no backend and starts no thread
- [ ] `enable()` makes the component speak again
- [ ] a failed HTTP backend falls back to the CLI backend
- [ ] a failed HTTP backend with no CLI configured disables voice and does
      **not** raise
- [ ] the manager returns `available() == False` when no backend is usable
- [ ] `stop()` terminates the playback handle
- [ ] two `narrate()` calls do not overlap (the executor is serialised)
- [ ] `status()` reports the three axes plus the backend detail
- [ ] `speak()` on a disabled manager returns `VOICE_DISABLED`
- [ ] the manager can speak a string to a `FileSink` in a unit test
- [ ] `close()` shuts the executor down and leaves no thread behind

---

## 12. Phase 7 — The Narration Hook

**Duration:** 0.5 day
**Location:** `components/voice/narrator.py`

The post-response hook: prepare → dispatch → play. It is a thin function over
the manager, kept separate so that the orchestrators depend on a
*function*, not on the manager's internals.

```python
def narrate_response(manager: Optional[VoiceSessionManager], text: str) -> None:
    """Narrate a final agent response. A no-op when the manager is None."""
```

Binding requirements:

- It must be a **no-op** when the manager is `None`, when the component is
  disabled, or when the trigger is not `on_response`.
- It must **never raise** — a failure in the voice path must not break the
  turn. Any exception is caught and logged at `WARNING`.
- It must not block: it calls `manager.narrate(text)`, which returns
  immediately.

### Step 7.1 — `tests/test_voice_narrator.py`

- [ ] a `None` manager is a no-op
- [ ] a disabled manager is a no-op
- [ ] a manager with the trigger `never` is a no-op
- [ ] a manager with the trigger `on_response` narrates exactly once
- [ ] an exception in the manager is swallowed and logged, not raised

---

## 13. Phase 8 — The Command Surface

**Duration:** 0.5 day
**Files:** `components/voice/commands.py`, `components/command_registry.py`

### Step 8.1 — `components/voice/commands.py`

- [ ] `is_voice_command(cmd) -> bool` — matches `\voice` and `\voice …`
- [ ] `handle_voice_command(cmd, manager=None) -> str` — returns the text to
      print; **never raises**
- [ ] the manager is resolved with `get_voice_manager()` when none is passed
- [ ] a missing manager produces a clear "voice is not available" note, not a
      traceback
- [ ] every subcommand from §2.5 is implemented
- [ ] an unknown subcommand returns a usage line, not an error
- [ ] `\voice speak <text>` speaks the text whatever the trigger is
- [ ] `\voice test` speaks a fixed test phrase
- [ ] `\voice stop` stops the current playback and reports whether anything
      was stopped

### Step 8.2 — `components/command_registry.py`

- [ ] add `FEATURE_VOICE = "voice"` to the feature flags
- [ ] add `voice: bool = True` to `HelpOptions`
- [ ] add the `Voice` category to `CATEGORY_ORDER` and `CATEGORY_TITLES`
- [ ] register the command spec:

```python
CommandSpec(
    name="\\voice",
    description="Voice output: status, on/off, trigger, voice, speak, stop, test.",
    usage="\\voice [on|off|toggle|status|trigger <t>|voice <id>|voices|speak <text>|stop|test]",
    category="Voice",
    feature=FEATURE_VOICE,
)
```

- [ ] the commands appear in `\help` when the voice runtime toggle is
      permitted, and are hidden when it is not

### Step 8.3 — `tests/test_voice_commands.py`

- [ ] `is_voice_command` matches `\voice` and its subcommands, case-insensitively
- [ ] `is_voice_command` does **not** match `\voices` or `\voice-test`
- [ ] every subcommand returns a non-empty string
- [ ] an unknown subcommand returns a usage line
- [ ] a `None` manager returns the "not available" note
- [ ] `handle_voice_command` never raises, even with a broken manager

### Step 8.4 — `tests/test_voice_registry.py`

- [ ] the registry contains exactly one `\voice` spec
- [ ] the spec carries the `Voice` category and the `FEATURE_VOICE` flag
- [ ] `HelpOptions(voice=False)` hides it, `HelpOptions(voice=True)` shows it
- [ ] the help text renders the usage line
- [ ] the registry's `\voice` spec matches what `is_voice_command` accepts
      (the two cannot drift)

---

## 14. Phase 9 — Orchestrator Integration

**Duration:** 1 day
**Files:** `agent-torvalds.py`, `agent-torvalds-mw.py`, `components/tui/state_bridge.py`, `components/tui/telemetry_view.py`, `components/tui/tui_app.py`

### Step 9.1 — The classic REPL (`agent-torvalds.py`)

- [ ] CLI flags: `--voice` / `--no-voice`, `--voice-trigger`,
      `--voice-backend`, `--voice-server-url`, `--voice-model`,
      `--voice-id`, `--voice-language`, `--voice-output`, `--voice-dir`,
      `--voice-timeout`, `--no-voice-runtime-toggle`
- [ ] build the `VoiceConfig` from env + CLI flags with `build_voice_config()`
- [ ] construct the `VoiceSessionManager` and hand it to
      `set_voice_manager()`
- [ ] the banner shows the state:

```python
if voice_session.enabled:
    console.print(
        f"[dim]Voice: enabled (backend={voice_config.backend.value}, "
        f"trigger={voice_config.trigger.value}, "
        f"voice={voice_config.voice_id})[/dim]"
    )
else:
    console.print("[dim]Voice: disabled (use \\voice on to enable)[/dim]")
```

- [ ] the narration hook, immediately after the render:

```python
console.rule("[blue]Agent Response[/blue]")
console.print(Markdown(response))
console.rule()

# --- voice (component, off by default, never blocks) ---
narrate_response(voice_session, response)
```

- [ ] dispatch the `\voice` commands next to `is_mikrotik_command` /
      `is_project_command`
- [ ] `close_voice_manager()` on exit (`\exit`, EOF, `Ctrl+C`, `SIGTERM`)

### Step 9.2 — The TUI (`agent-torvalds-mw.py` + `components/tui/`)

- [ ] the same flags and the same manager construction
- [ ] the narration hook, after the response is set into the TUI state
- [ ] `components/tui/state_bridge.py` — add `voice_enabled: bool`,
      `voice_status: str` and `voice_last_spoken: str` to `TuiState`
- [ ] `components/tui/telemetry_view.py` — show the voice state in the
      telemetry pane
- [ ] `components/tui/tui_app.py` — handle the `\voice` commands (render the
      result as Markdown in the document pane)
- [ ] `components/tui/tui_app.py` — stop playback on `\exit`

### Step 9.3 — The barge-in path

Both front ends call `voice_session.stop()` **before** dispatching a new
user input, so typing during playback cuts the audio short rather than
queueing behind it:

- the classic REPL: right before the `prompt_handler()` call;
- the TUI: in `_handle_enter_pressed()`, before the query is dispatched.

The call must be cheap and safe when the component is off — `stop()` returns
`False` immediately when nothing is playing.

### Step 9.4 — What must **not** change

- [ ] `agent_tool_retriever.py` is **untouched** — there is no
      `include_voice_tools` flag;
- [ ] `agent_tool_selection.py` is **untouched** — there is no `Voice`
      category in the `--select` menu;
- [ ] `_collect_all_tools()` in both orchestrators is **untouched** — voice
      contributes no tools;
- [ ] `toolkits/__init__.py` is **untouched** — there is no import alias;
- [ ] `pytest.ini` is **untouched** — the tests live in `tests/`.

### Step 9.5 — The end-to-end check

With `audiocpp_server` running and `--voice` passed:

- [ ] the agent boots, answers, and the answer is **spoken**
- [ ] the text is still printed — voice is additive, never a replacement
- [ ] the response latency is not visibly affected (`narrate()` returns
      before the next prompt)
- [ ] the TUI render loop does not stall during synthesis
- [ ] `\voice off` silences the next answer; `\voice on` brings it back
- [ ] the agent behaves **identically** to a build without the component
      when the feature is off

---

## 15. Phase 10 — Hardening

**Duration:** 0.5 day

| # | Item | Verification |
|---|---|---|
| H1 | **Barge-in** | Typing during playback truncates the audio; the player process is gone afterwards |
| H2 | **Secret redaction** | A response containing a seeded API key is spoken **without** the key; the printed text still has it |
| H3 | **Long answers** | A 20 000-character response speaks in order, in bounded chunks, without truncation |
| H4 | **Degradation: server down** | The turn still completes; the text is unaffected; a one-line notice is printed |
| H5 | **Degradation: server down, CLI available** | The CLI backend takes over transparently |
| H6 | **Degradation: no backend at all** | The agent runs exactly as before the feature existed |
| H7 | **Headless** | No audio device → automatic fallback to `file` output, with a notice |
| H8 | **Missing `ffplay`** | The `FileSink` is used instead; the turn is not failed |
| H9 | **The component is off** | No backend is constructed, no thread is started, the response rendering is byte-identical |
| H10 | **Layering** | A test asserts that **no** file under `components/voice/` imports `llama_index`, an `agent_*.py` module or a `toolkits.*` module |
| H11 | **The player never writes to the TUI** | A test asserts `stdout`/`stderr` are `DEVNULL` in the `ffplay` invocation |
| H12 | **The feature is not a tool** | A test asserts that the discovered tool inventory contains **no** voice tool, and that the `--select` menu has **no** Voice category |
| H13 | **The switch is honest** | A test asserts that `narrate()` on a disabled manager touches no backend and starts no thread |

> **H12 is the regression test for this rework.** It is the test that fails
> if somebody later re-adds a `speak_text` tool "just in case", and it is the
> mechanical expression of the decision recorded in §0.1.

---

## 16. Phase 11 — Documentation

**Duration:** 0.5 day

- [ ] `docs/voice-component.md` — the operator guide: the on/off switch (all
      three levels), the three axes, the environment-variable reference, the
      CLI flags, the `\voice` commands, the default voice and the catalogue,
      the recommended `audiocpp_server` config, the security model
      (redaction, code-block suppression) and a troubleshooting table.
- [ ] `docs/audiocpp-server.json.example` — the recommended server config
      (`max_loaded_models: 1`, `min_free_memory_mb: 2048`,
      `busy_timeout_ms: 30000`).
- [ ] `components/README.md` — a new section for `voice/`, in the format the
      other components use.
- [ ] `README.md` — a short "Voice output" section.
- [ ] `CHANGELOG.md` — an entry under `## [Unreleased]`.
- [ ] `SELF_DEVELOPMENT_RULES.md` — update the "Current self-development
      work" table, per Rule 3.

---

## 17. Definition of Done

| # | Criterion |
|---|---|
| D1 | `pytest` failure set is **byte-identical** to the Phase 0 baseline |
| D2 | `components/voice/` imports with **zero** optional dependencies installed |
| D3 | No `llama_index` / `agent_*.py` / `toolkits.*` import exists under `components/voice/` |
| D4 | `from components.voice import ...` works from a consumer module |
| D5 | `to_speakable_text` output contains **no** Markdown punctuation |
| D6 | Chunking never splits a sentence, except when a single sentence exceeds the limit |
| D7 | A seeded secret corpus is fully redacted from the spoken text |
| D8 | The HTTP and CLI backends pass the **same** contract suite |
| D9 | A failing backend returns a structured error and never raises |
| D10 | The agent boots and behaves **identically** when the component is off |
| D11 | With the component off, no backend is constructed and no thread is started |
| D12 | The agent boots when `audio.cpp` is absent |
| D13 | The component can be switched on and off **at runtime**, without a restart |
| D14 | The text is **always** printed; voice is additive |
| D15 | Playback is interruptible; the player process is not leaked |
| D16 | The player never writes to the terminal |
| D17 | **No voice tool exists** — the tool inventory and the `--select` menu are unchanged |
| D18 | The default voice is `af_heart`; there is no "Torvalds voice" and no clone path |
| D19 | All work is confined to the `self-development` clone on `feature/voice-toolkit` |
| D20 | `docs/voice-component.md` exists and documents every environment variable |
| D21 | The operator has approved the merge back to the main repository |

---

## 18. Appendix A — Error Code Table

Every failure path in the feature uses one of these codes. They are
**stable**: they may appear in the status output and in the log, so they must
not be renamed without updating this table and the `CHANGELOG.md`.

| Code | Meaning | Raised by |
|---|---|---|
| `VOICE_DISABLED` | The component is switched off | manager |
| `VOICE_CONFIG_INVALID` | A configuration value could not be used | config |
| `VOICE_BACKEND_UNAVAILABLE` | The selected backend cannot be used | backend |
| `VOICE_SERVER_UNAVAILABLE` | `audiocpp_server` is not reachable | HTTP |
| `VOICE_SERVER_BUSY` | The server is busy (`503 server_busy`) | HTTP |
| `VOICE_INSUFFICIENT_MEMORY` | The memory guard tripped (`503 insufficient_memory`) | HTTP |
| `VOICE_MODEL_NOT_FOUND` | The model id is not registered on the server | HTTP |
| `VOICE_BAD_REQUEST` | The request was rejected | HTTP / CLI |
| `VOICE_TIMEOUT` | The request exceeded `timeout_s` | HTTP / CLI |
| `VOICE_NO_OUTPUT_DEVICE` | No playback device is available | sink |
| `VOICE_PLAYER_FAILED` | The player exited non-zero | sink |
| `VOICE_OUTPUT_FAILED` | The output file could not be written | sink |
| `VOICE_NOTHING_TO_SPEAK` | The prepared text was empty | narrator |
| `VOICE_CLI_NOT_FOUND` | `audiocpp_cli` is not on `PATH` | CLI |

> **If the listening proposal is approved**, this table is **extended, not
> forked** — with `VOICE_INPUT_DISABLED`, `VOICE_INPUT_BUSY`,
> `VOICE_NO_INPUT_DEVICE`, `VOICE_CAPTURE_FAILED`, `VOICE_CAPTURE_TIMEOUT`,
> `VOICE_NO_SPEECH_DETECTED`, `VOICE_TRANSCRIBE_FAILED`,
> `VOICE_TRANSCRIPT_EMPTY` and `VOICE_ASR_MODEL_NOT_FOUND`. The existing
> server-level codes are reused verbatim, because they describe server
> conditions rather than direction-specific ones. See
> `PROPOSAL_voice_listening.md` §4.6.

---

## 19. Appendix B — File Manifest

**New files**

```
components/voice/__init__.py
components/voice/errors.py
components/voice/config.py
components/voice/text.py
components/voice/voices.py
components/voice/output.py
components/voice/session.py
components/voice/narrator.py
components/voice/commands.py
components/voice/runtime.py
components/voice/backends/__init__.py
components/voice/backends/base.py
components/voice/backends/http.py
components/voice/backends/cli.py
components/voice/backends/capi.py
tests/test_voice_text.py
tests/test_voice_backends.py
tests/test_voice_output.py
tests/test_voice_voices.py
tests/test_voice_config.py
tests/test_voice_session.py
tests/test_voice_narrator.py
tests/test_voice_commands.py
tests/test_voice_registry.py
tests/test_voice_wiring.py
docs/voice-component.md
docs/audiocpp-server.json.example
```

**Modified files**

```
components/command_registry.py             # FEATURE_VOICE + the \voice spec
components/README.md                       # the new component section
components/tui/state_bridge.py             # the voice state fields
components/tui/telemetry_view.py            # the voice telemetry row
components/tui/tui_app.py                  # the \voice commands, the hook, the exit stop
agent-torvalds.py                          # the flags, the manager, the hook, the dispatch
agent-torvalds-mw.py                       # the same, plus the TUI
README.md
CHANGELOG.md
SELF_DEVELOPMENT_RULES.md
```

**Deliberately NOT modified**

```
agent_tool_retriever.py                    # no tools to retrieve
agent_tool_selection.py                    # no menu category
toolkits/__init__.py                       # no import alias
pytest.ini                                 # the tests live in tests/, already collected
```

---

## 20. Appendix C — Open Questions

These need an operator decision before Phase 9 closes. The recommendation is
given so the work is not blocked if no answer arrives.

| # | Question | Recommendation | Owner |
|---|---|---|---|
| Q1 | **Default voice.** Which Kokoro preset is the default? | **DECIDED: `af_heart`** — a clear American English female preset. The full 54-voice catalogue is documented in `PROPOSAL_voice_output.md` §12.4; `TORVALDS_VOICE_ID` switches it at runtime. | Operator (decided) |
| Q2 | **Is a cloned "Torvalds voice" required?** | **DECIDED: no, not for v1.** There is no cloned voice available, and Kokoro cannot clone in any case (`supports_speaker_reference=false`). v1 speaks with the preset catalogue; cloning (MagpieTTS / OmniVoice + a reference recording) is out of scope. | Operator (decided) |
| Q3 | **Should the component speak every answer once enabled?** | `on_response`. The feature is opt-in as a whole, so a second opt-in inside it is redundant friction. | Operator |
| Q4 | **Should the spoken text be persisted in the chat history?** | **No, not for v1.** The chat memory already stores the response; a separate "spoken" column adds a migration for a feature nobody has asked for. | Maintainer |
| Q5 | **Who manages the `audiocpp_server` lifecycle?** | **(a) the operator runs it.** It keeps the model warm between turns, which is the whole point of the HTTP backend. The agent may *probe* it, but must not spawn it. | Operator |
| Q6 | **Multi-turn continuity** — one continuous stream per turn, or one file per turn? | **One file per turn** for v1. Continuous streaming needs a pipe-fed player and a different audio path; it is a later streaming item. | Maintainer |
| Q7 | **What is the `audiocpp_server` port?** | **DECIDED: `8099`** — the port the operator's server already listens on (`/tmp/audiocpp_server.json`). The agent reads it from the environment, so any port works. | Operator (decided) |
| Q8 | **Should other components be able to announce themselves?** (e.g. the HITL handler speaking "the agent is asking you a question") | **Yes, via `announce()`** — but nothing calls it in v1. The `announce` trigger exists so the capability can be wired later without a redesign. | Maintainer |
| Q9 | **Should the component be able to *receive* speech** (ASR)? | **REOPENED — see [`PROPOSAL_voice_listening.md`](./PROPOSAL_voice_listening.md).** The answer recorded here was "**No** — it is a different product with a different UI model (a listening mode, turn detection, a different failure contract)". That remains **correct for continuous listening (L2) and for full duplex (L3)**, and it is **wrong for push-to-talk dictation (L1)**, which fits this plan's contracts exactly: one bounded recording, one transcript, handed to the existing input path. The proposal recommends adding L1 to this component — a second manager, one shared server, one command family, and a **separate microphone switch that is off by default**. It adds ~7.5 days and is **parallel** to Phases 0–11, not sequential. It becomes part of this plan when the operator answers LQ1–LQ9. | Operator (reopened) |

---

## 21. Appendix D — What was removed from the toolkit plan

A complete, auditable list of what the rework deleted, so nothing is lost by
accident.

| Removed artifact | Fate |
|---|---|
| `toolkits/audio-toolkit/` — 12 files (`__init__`, `errors`, `config`, `text`, `output`, `voices`, `backends/{__init__,base,http,cli,capi}`) | **Moved** to `components/voice/` with the same responsibilities. |
| `agent_voice_toolkit.py` — the LlamaIndex adapter | **Deleted.** Voice exposes no LLM tools. |
| The four LLM tools: `speak_text`, `list_voices`, `stop_speaking`, `transcribe_audio` | **Deleted as tools.** The same capabilities are reachable through `\voice speak`, `\voice voices`, `\voice stop` and `\voice test`, and through the component's Python API. |
| The `Category: Voice` tag and the menu entry | **Deleted.** The `--select` menu is unchanged. |
| `agent_tool_retriever.py` — the `include_voice_tools` flag | **Deleted.** No tools to retrieve. |
| `toolkits/__init__.py` — the `audio_toolkit` import alias | **Deleted.** `components.voice` is a normal package. |
| `pytest.ini` — the `toolkits/audio-toolkit/tests` testpath | **Deleted.** The tests live in `tests/`, which is already collected. |
| The `voice_ref` / `reference_text` config fields | **Deleted.** The default backend ignores them, and a silently-ignored field is worse than none. They come back with a cloning-capable backend. |
| The "Torvalds voice" (a clone) as a v1 feature | **Deleted from scope.** The default is the `af_heart` preset. |
| The `transcribe_audio` tool (ASR) | **Deleted from scope.** It was already deferred; it is now simply not in the plan. **The listening proposal keeps it deleted** — the input half contributes no tools either, and the capability is reachable through `\voice transcribe <path>`. |
| Phase 6 of the old plan ("The Agent Adapter") | **Replaced** by Phase 6 ("The Voice Session Manager") + Phase 7 ("The Narration Hook") + Phase 8 ("The Command Surface"). |
| Phase 7 of the old plan ("Wiring: Retriever, Menu, Command Registry") | **Reduced** to Phase 8 ("The Command Surface") — the registry only. The retriever and the menu are untouched. |

**And what was kept, unchanged:** the text-preparation layer, the redaction
rules, the backend contract, the HTTP backend and its error mapping, the CLI
backend and its metrics parsing, the C-API stub, the three output sinks, the
device-detection degradation, the voice catalogue and its capability block,
the non-blocking contract, the worker-thread serialisation, the barge-in
path, the error-code table, the recommended `audiocpp_server` config, the
empirical numbers from the investigation, and every risk and mitigation
except R10 (the toolkit-convention divergence risk), which this rework
**removes**.

---

*Plan derived from `PROPOSAL_voice_output.md` and `INVESTIGATION_REPORT.md`,
reworked from the toolkit shape to the component shape.
All implementation work is to be performed in the `self-development` clone on
branch `feature/voice-toolkit`.*
