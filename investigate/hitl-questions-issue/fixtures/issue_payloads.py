"""
Verbatim payloads from the two operator-reported HITL issues.

Source files (read-only, outside the repository):

* ``~/torvald-log/hitl_questions_issue/hitl-wrong-question.md``
* ``~/torvald-log/hitl_questions_issue/hitl_dublicate_question.md``

The two texts below are the *assistant messages* that the agent produced in
the sessions the operator reported.  They are the payload that reached
``HITLFunctionAgent.parse_agent_output()`` and therefore the payload that
became the ``AgentQuestionEvent.question``.

They are kept verbatim (not paraphrased) so every diagnostic in this
directory measures the real thing and not a reconstruction.

Category: HITL / Investigation
Retriever Keywords: hitl, question, password, duplicate, input type, fixtures
"""

from __future__ import annotations

import re
from typing import Dict

# ---------------------------------------------------------------------------
# Issue #1 — "hitl-wrong-question.md"
#
# The agent finished a long investigation report and closed it with a single
# yes/no question ("Want me to start Phase 0 ...?").  The operator saw the
# console prompt "Enter password: " instead of a yes/no prompt.
# ---------------------------------------------------------------------------

WRONG_QUESTION_TEXT = """## Done — investigation and proposal delivered

**Deliverables** (in `self-development/investigate/Voice-Output/`, per Rule 1; main repo untouched, nothing committed per Rule 4):

- `INVESTIGATION_REPORT.md` (683 lines)
- `PROPOSAL_voice_output.md` (883 lines)

### Key findings

**1. `text-to-speach/audio.cpp` is a directory, not a file** — it's the full `0xShug0/audio.cpp` framework (v0.8.0, 80+ model families), and it's **already built with CUDA** on this host:
```
audio.cpp/build/linux-cuda-release/bin/audiocpp_server
audio.cpp/build/linux-cuda-release/bin/audiocpp_cli
```
TTS weights are already downloaded too (`models/TTS/`: Kokoro 82M 212 MB, MagpieTTS 1.9 GB, OmniVoice 1.2 GB).

**2. I validated it empirically rather than trusting the docs:**

| Measurement | Result |
|---|---|
| Kokoro TTS, CUDA | **RTF 0.069 — 14.4× real time** (3.1 s of speech in 213 ms) |
| `POST /v1/audio/speech` | HTTP 200, valid WAV |
| GPU | RTX 4060, 8 GB — **no LLM contention** (the 27B Q4_K_M can't fit in 8 GB, so it runs on CPU) |
| Playback | `ffplay`/`aplay` present; **no** `sounddevice`/`pyaudio` — so the sink must be a subprocess |
| C ABI | `libaudiocpp.so` **not built** (`-DAUDIOCPP_BUILD_C_API=ON` is off by default) |

**3. The agent has zero audio capability** — a grep for `tts|speech|audio|voice` across the repo returns exactly **2 hits**, both incidental mentions in a proposal doc.

**4. The hard part isn't synthesis — it's the interface.** Three genuinely different capabilities are hiding in "produce voice": speak the answer / announce mid-workflow / speak *to* the
agent. So the proposal decomposes the feature into **three orthogonal axes** — `TRIGGER × BACKEND × OUTPUT` — where every capability is an enum value, not a subsystem. Both orchestrators
converge on one hook (`prompt_handler`'s return value), so one integration covers REPL and TUI.

**5. Two non-obvious must-haves:** the agent's output is Markdown (speaking it raw says "hash hash" per heading, spells out code fences), and long answers need sentence-aware chunking. Both
get dedicated modules and unit tests.

**6. Recommended shape:** `toolkits/audio-toolkit/` (no LlamaIndex) + `agent_voice_toolkit.py` (adapter, `Category: Voice`) + `components/voice/` (session manager). Default backend =
**HTTP** against the already-built `audiocpp_server`; CLI fallback; C ABI deferred to phase 3. Opt-in, off by default, additive (text is always still printed), with secret redaction on by
default.

### Six open questions I need you to decide before Phase 3

1. Default Kokoro voice (English `af_heart` vs multilingual)?
2. Should enabling voice immediately speak every answer, or only agent announcements until opted in?
3. Is a *cloned* "Torvalds voice" required? (Needs MagpieTTS/OmniVoice + a reference recording — VRAM allows it.)
4. Persist the spoken variant in chat history separately?
5. Who owns the `audiocpp_server` lifecycle? (Proposal assumes the operator runs it.)
6. One file per turn, or a continuous streaming stream?

Want me to start **Phase 0** (the `text.py` preparation layer — pure functions, fully unit-tested, zero risk to the agent) on a `feature/voice-toolkit` branch?
"""


# ---------------------------------------------------------------------------
# Issue #2 — "hitl_dublicate_question.md"
#
# The agent reported the project state and asked two questions in one
# message.  The operator saw the *whole message* twice.
# ---------------------------------------------------------------------------

DUPLICATE_QUESTION_TEXT = """I see the project structure. There's no sqitch configuration yet, but there is a `setup_postgres_db.sql` file.

**Current status:**
- On branch `master`, up to date with `origin/master`
- DNS resolution is failing, so I can't pull from remote right now
- No sqitch config found in the project

Let me create a new branch for the feature. What would you like to name it? For example:
- `feature/sqitch-database-migrations`
- `feature/db-migrations`
- Or another name?

Also, would you like me to:
1. Set up sqitch for database version control?
2. Start with documentation for the sqitch integration?"""


#: Both payloads, keyed by the issue they came from.
ISSUE_PAYLOADS: Dict[str, str] = {
    "wrong-question": WRONG_QUESTION_TEXT,
    "duplicate-question": DUPLICATE_QUESTION_TEXT,
}


#: The exact console line the operator saw at the end of issue #1.
WRONG_QUESTION_OBSERVED_PROMPT = "Enter password: "


def sentences(text: str) -> list[str]:
    """Split *text* into sentences (used by the diagnostics)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]
