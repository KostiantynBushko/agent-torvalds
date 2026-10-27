# Investigation: the HITL question is wrong, and it is shown twice

**Date**: 2026-10-24
**Status**: Investigation complete — 7 defects found, all reproduced empirically
**Location**: `self-development/investigate/hitl-questions-issue/`
**Reported by**: the operator, in `/home/kbush/torvald-log/hitl_questions_issue/`
**Affected components**: `components/hitl_agent.py`, `components/event_consumer.py`, `components/console_input_module.py`, `components/human_loop_handler.py`
**Base commit**: `16bbd83` (master)
**Branch**: `investigate/hitl-questions-issue`

---

## 1. Objective

The operator filed two reports:

| File | Complaint |
|---|---|
| `hitl-wrong-question.md` | The agent asked a **wrong question** — the console showed `Enter password: ` instead of the yes/no question the agent had actually asked. |
| `hitl_dublicate_question.md` | The agent asked the **same question twice** — the operator saw the whole message rendered twice. |

Determine why the Human-in-the-Loop round-trip presents the wrong question to
the operator, why the same question reaches the terminal twice, and what has
to change.

**Result**: the HITL *plumbing* is sound (the previous investigation,
`investigate/hitl-investigate/`, fixed that) but the *presentation* layer was
never designed. The entire assistant answer is used as the question, the
input type is guessed from that answer with substring matching, and the
consumer renders the payload a second time through the input prompt.
**Seven independent defects**, all reproduced below.

---

## 2. The two reports, decoded

Both files are terminal transcripts. The interesting part is what the HITL
machinery did with the agent's answer.

### 2.1 `hitl-wrong-question.md` — the wrong question

The agent delivered the Voice-Output investigation report and closed it with
one ordinary yes/no question:

> Want me to start **Phase 0** (the `text.py` preparation layer — pure
> functions, fully unit-tested, zero risk to the agent) on a
> `feature/voice-toolkit` branch?

What the operator saw instead of a yes/no prompt:

```
Enter password:
```

Three things went wrong at once:

1. the **entire 3 180-character report** was used as "the question";
2. the input type was derived from that report — and the report contains the
   word "secret" (in *"with secret redaction on by default"*), so
   `detect_input_type()` classified the whole thing as a **password
   request**;
3. the password branch of the consumer never shows the question at all — it
   shows the fixed string `Enter password: `.

So the operator was asked for a password, the real question was buried 3 KB
deep in a block labelled `🤖 Agent asks:`, and the report was never
delivered as the agent's answer.

### 2.2 `hitl_dublicate_question.md` — the same question twice

The agent reported the project state and asked two questions. The operator
saw the **same 598-character message twice** — once as

```
🤖 Agent asks: I see the project structure. There's no sqitch configuration …
```

and once more as the `input()` prompt, followed by ` [y/N]`.

The operator's log excerpt shows the same thing from the other side:

```
19:26:22,428 HITL question detected (hitl-d267a4eb, type=yesno, timeout=none)
19:26:22,429 HITL answer received for hitl-d267a4eb: 'no' (timeout=False)
```

**One millisecond** between "question detected" and "answer received". No
human answers that fast. The explanation is the workflow replay (§3.5): the
*second* "HITL question detected" line is the replay, and on the replay the
waiter is already resolved, so the answer comes back instantly.

---

## 3. Findings

Seven defects, grouped by the layer they live in.

| # | Defect | Layer | Severity |
|---|---|---|---|
| **D1** | The whole assistant answer becomes the question | agent | **Blocker** |
| **D2** | The input type is guessed from the whole answer with substring matching | agent | **Blocker** |
| **D3** | The consumer renders the question a second time through the input prompt | consumer | **High** |
| **D4** | The re-ask guard compares the question text for exact equality (a *separate* weakness, not the reported symptom) | agent | Medium |
| **D5** | The step re-detects the question on every workflow replay | agent | Medium |
| **D6** | An empty answer (Enter) is recorded as an explicit "no" | consumer | Medium |
| **D7** | A question ending with a code span or a quote is not detected at all | agent | Medium |

### 3.1 D1 — the whole assistant answer becomes the question

`components/hitl_agent.py:384` `HITLFunctionAgent.parse_agent_output()`:

```python
text = self._extract_text(ev.response)
if not self._is_question(text):
    return await super().parse_agent_output(ctx, ev)
...
question_event = AgentQuestionEvent(
    prefix="Agent asks: ",
    question=text,          # <-- the ENTIRE assistant message
    ...
)
```

`text` is the complete assistant message. The detection only asks *"does
this message contain a question?"* — it never asks *"which part of this
message is the question?"*. So a 3 180-character report that happens to end
in a question mark is presented as a 3 180-character question.

`AgentQuestionEvent` already has a `context` field
(`components/hitl_events.py:104`) for exactly this — the surrounding
explanation — and the agent never fills it in.

**Measured** (`diag_roundtrip.py`):

```
AgentQuestionEvent objects on the stream : 1
    question_id=hitl-5012f214 input_type='password' timeout=-1 question_len=3180
```

The event carries 3 180 characters. The whole answer is the question.

### 3.2 D2 — the input type is guessed from the whole answer

`components/hitl_agent.py:119`:

```python
def detect_input_type(message: str) -> str:
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in ("password", "secret", "credential")):
        return "password"
    if any(kw in msg_lower for kw in ("yes", "no", "confirm", "proceed", "continue")):
        return "yesno"
    return "text"
```

Four separate problems:

1. **It is applied to the answer, not to the question.** Any report that
   mentions a secret becomes a password prompt.
2. **The keywords are not word-boundary aware.** `"no"` matches "no**thing**",
   "docu**no**tation", "**no**tification". The sqitch payload matches on
   the standalone "no" in *"There's **no** sqitch configuration yet"* — by
   accident the right answer, but for the wrong reason; the wrong-question
   payload matches on the "no" inside *"**no**thing committed per Rule 4"*.
3. **The order is wrong.** "password" is checked first, so a message that
   mentions a secret *and* asks a yes/no question always becomes a password
   prompt.
4. **It is duplicated.** `components/human_loop_handler.py:89`
   `_detect_input_type()` is a copy-paste of the same heuristic, with the
   same defects. Two copies, two places to fix.

**Measured** (`diag_input_type.py`):

```
--- payload: wrong-question --------------------------------------------
length                 : 3180 characters
hitl_agent.detect_input_type()          -> 'password'
human_loop_handler._detect_input_type() -> 'password'
password-keyword hits   : ['secret']
    'secret' found in: …(text is always still printed), with secret redaction on by …
```

The word "secret" in a sentence about *redaction* turned a yes/no question
into a masked password field.

### 3.3 D3 — the question is rendered twice

`components/event_consumer.py:665` `_on_agent_question()`:

```python
self.console.print(f"\n[magenta]🤖 Agent asks: {event.question}[/magenta]{context_str}")
```

and then `components/event_consumer.py:748` `_collect_answer()`:

```python
if input_type == "yesno":
    result = await self.console_input.confirm(
        message=event.question,      # <-- the same text, again
        ...
    )
```

`ConsoleInputModule.confirm()` (`components/console_input_module.py:229`)
builds `f"{message}{suffix}"` and hands it to `input()`, which writes it to
stdout. The payload therefore reaches the terminal **twice**.

The render matrix, measured (`diag_duplicate_prompt.py`):

| input type | how often the question is shown |
|---|---|
| `text` | 1 (the prompt is the fixed `"Your response: "`) |
| `yesno` | **2** (`console.print` + the `input()` prompt) |
| `menu` | 2 (`console.print` + `ConsoleInputModule.menu()`'s own `console.print`) |
| `password` | 1 (but the *prompt* is the fixed `"Enter password: "`, so the question text is not in the prompt) |

**Measured** (`diag_roundtrip.py`, real agent + real runtime):

```
--- payload: duplicate-question ----------------------------------------
AgentQuestionEvent objects on the stream : 1
    question_id=hitl-4934d309 input_type='yesno' timeout=-1 question_len=598
prompts handed to the console input module: 1
    prompt #1 (598 chars): "I see the project structure. There's no sqitch configuration yet, …"
payload rendered by console.print        : 1
payload rendered by the input prompt     : 1
TOTAL renderings of the payload          : 2
```

Exactly what the operator reported. The event is published **once**; the
duplication is purely in the rendering.

### 3.4 D4 — the re-ask guard compares the question text for exact equality

> **Not the reported symptom.** The operator's transcript shows the *same
> message* rendered twice inside one prompt — that is **D3**. D4 is a
> related but distinct weakness: it makes the agent ask a *rephrased*
> question again. It is reported here because it sits in the same code path
> and because the fix touches it, but the operator did not report it.

`components/hitl_agent.py:506`:

```python
async def _was_answered(self, ctx: Context, text: str) -> bool:
    answered = await ctx.store.get(_ANSWERED_QUESTIONS_KEY, default=None)
    if not isinstance(answered, list):
        return False
    return text in answered
```

The guard exists to stop the agent from asking the same thing twice. It
compares the *whole message* for exact equality, so:

* a rephrased question ("Shall I create the branch X?" → "Should I create
  the branch X?") is a different string and is asked again;
* the *same* question asked after any intervening message is asked again;
* the guard is keyed on the answer text, not on the question, so it also
  fails to recognise a question that was already answered.

**Measured** (`diag_reask.py`):

```
question #1 : Shall I create the branch feature/sqitch-database-migrations?
question #2 : Should I create the branch feature/sqitch-database-migrations?   <- the same question, rephrased
prompts shown to the operator : 2
  => VERDICT: the rephrased question is asked AGAIN
```

### 3.5 D5 — the step re-detects the question on every workflow replay

The `workflows` runtime suspends a step that calls `ctx.wait_for_event()` and
**replays it from the beginning** when the awaited event arrives
(`workflows/context/internal_context.py:210`, `workflows/runtime/control_loop/reduce.py:617`).

`parse_agent_output()` runs top-to-bottom on the replay, so the detection
runs again, the "HITL question detected" line is logged again with the same
`question_id`, and the already-resolved waiter hands the answer back
instantly.

That is exactly the one-millisecond gap in the operator's log.

**Measured** (`diag_reask.py`):

```
'HITL question detected' log lines : 2
    HITL question detected (hitl-c30af0fb, type=yesno, timeout=none)
    HITL question detected (hitl-c30af0fb, type=yesno, timeout=none)
'HITL answer received' log lines  : 1
    HITL answer received for hitl-c30af0fb: 'no' (timeout=False)
```

Two "detected" lines, one question. The `waiter_id` mechanism in the
runtime does prevent the *event* from being published twice — that part is
correct — but the step's own side effects (detection, logging, identity
resolution) are not idempotent.

### 3.6 D6 — an empty answer is recorded as an explicit "no"

`components/event_consumer.py:748` `_collect_answer()`:

```python
if input_type == "yesno":
    default_yes = default_answer.strip().lower() in ("yes", "y", "true", "1")
    result = await self.console_input.confirm(
        message=event.question, default_yes=default_yes, timeout=timeout,
    )
    return ("yes" if result else "no", False)   # <-- was_timeout is hard-coded
```

`was_timeout` is hard-coded to `False` for a yes/no question. If the
operator simply presses Enter, the default is taken and recorded as a clean
"no" — indistinguishable from a deliberate "no". The timeout log, the
statistics and the chat history all claim the human answered.

**Measured** (`diag_reask.py`):

```
HITL answer received for hitl-ceb4c1f5: 'no' (timeout=False)
  => VERDICT: the empty answer is recorded as an explicit 'no', not as a timeout
```

### 3.7 D7 — a question ending with a code span is not detected

`components/hitl_agent.py:87`:

```python
re.compile(r"\w+\s*\?$", re.MULTILINE),
```

`\w` does not match a backtick or a quote, so a question whose last
character before the `?` is a closing backtick or quote is **not** a
question at all.

**Measured** (`diag_reask.py`):

```
detected=True  Shall I create the branch feature/sqitch?
detected=False Shall I create the branch `feature/sqitch`?
detected=False Shall I create the branch "feature/sqitch"?
detected=True  Shall I proceed?
```

The agent's own output is Markdown and routinely ends a question with a code
span, so this pattern misses a large class of real questions — including
exactly the shape the operator used ("… on a `feature/voice-toolkit`
branch?" — that one survives because the trailing "branch?" is a word, but
"… use `feature/x`?" does not).

---

## 4. Root cause

One sentence:

> **The HITL layer was built to carry a question, but it is fed a whole
> answer, and nothing in the pipeline ever separates the two.**

Everything else follows:

* the agent has no notion of "the question" inside the answer, so it ships
  the whole thing (§3.1);
* the input type has to be guessed, and it guesses from the whole thing
  with substring matching (§3.2);
* the consumer shows the whole thing, and the input module shows it again
  (§3.3) — **this is what the operator reported**;
* the re-ask guard keys on the whole string (§3.4);
* the replay re-runs the detection (§3.5).

The plumbing — the workflow event stream, the waiter, the answer round-trip
— is correct. The defect is entirely in the *content* of the event and in
the *rendering* of it.

### 4.1 What is *not* broken

Worth stating explicitly, because these were the obvious suspects:

* the `waiter_id` mechanism **does** prevent the `AgentQuestionEvent` from
  being published twice (the runtime replaces an existing waiter instead of
  re-publishing it — `workflows/runtime/control_loop/reduce.py:617`);
* exactly **one** `AgentQuestionEvent` reaches the stream per question
  (measured: `AgentQuestionEvent objects on the stream : 1`);
* exactly **one** prompt is handed to the input module per question
  (measured: `prompts handed to the console input module: 1`);
* the human's answer **does** reach the agent — the round-trip works
  ("the human's answer was fed back into the conversation");
* the timeout convention (`-1` = wait forever) is honoured.

So the answer is not lost, and the agent is not asked twice. Only the
*presentation* is wrong.

---

## 5. Reproduction

Everything in this report is reproducible from the `self-development` clone:

```bash
cd self-development
.venv/bin/python investigate/hitl-questions-issue/diag_input_type.py
.venv/bin/python investigate/hitl-questions-issue/diag_duplicate_prompt.py
.venv/bin/python investigate/hitl-questions-issue/diag_roundtrip.py
.venv/bin/python investigate/hitl-questions-issue/diag_reask.py
```

The acceptance harness for the fix:

```bash
.venv/bin/python investigate/hitl-questions-issue/verify_hitl_question_presentation.py
```

Against the current tree it reports **1 of 8 invariants hold, 7 violated**:

```
  FAIL  I1  the question is rendered exactly once
  FAIL  I2  the event carries the question, not the whole answer
  FAIL  I3  the input type follows the question alone
  PASS  I4  a password question is still shown
  FAIL  I5  a rephrased question is not asked twice
  FAIL  I6  an empty answer is reported as a timeout
  FAIL  I7  a question ending with a code span is detected
  FAIL  I8  a question is detected once per question
```

The payloads are the operator's verbatim text, kept in
`fixtures/issue_payloads.py` so the diagnostics measure the real thing and
not a reconstruction.

---

## 6. The fix, in one page

The full design is in `PROPOSAL_hitl_question_presentation.md`. The short
version:

1. **Extract the question from the answer.** A new module
   `components/hitl_question.py` splits the assistant message into
   `question` + `context`:
   * the question is the trailing interrogative block (last paragraph that
     contains a question, or the sentence after the last "…?" boundary);
   * everything before it is the `context` — the report the agent wanted to
     deliver;
   * the question is capped at a sane length, and a message with no
     interrogative yields no question at all.

   The agent then puts the question in `AgentQuestionEvent.question` and the
   report in `AgentQuestionEvent.context` — the field that already exists
   and is already rendered by the consumer.

2. **Never render the question twice.** The consumer owns the rendering; the
   input module receives a *short* prompt ("Your response: ", "[y/N]") and
   never the question text. The question is shown exactly once, by the
   consumer, with the context above it.

3. **Derive the input type from the question, with word boundaries.** The
   heuristic moves into `components/hitl_question.py`, is applied to the
   extracted question only, matches on word boundaries, and is defined in
   **one** place (the copy in `human_loop_handler.py` is deleted).
   Password detection additionally requires the question to *ask* for a
   secret ("what is the … password?"), not to mention one.

4. **Key the re-ask guard on a normalised question.** Normalise case,
   punctuation and whitespace, then compare. This hardens D4 — it is
   *hardening*, not the fix for the reported symptom (that is D3).

5. **Make the step idempotent across the replay.** Record that the
   question was already detected for this `question_id` and skip the
   detection on the replay, so the log shows one "detected" line per
   question.

6. **Report an empty answer as a timeout.** The yes/no branch must not
   hard-code `was_timeout=False`; an empty answer is "no answer given".

7. **Widen the question-mark pattern.** `[\w`"')\]]*\s*\?$` — a question may
   end with a code span or a quote.

---

## 7. Files

| Path | Role |
|---|---|
| `README.md` | Index and how to run everything. |
| `INVESTIGATION_REPORT.md` | This document. |
| `PROPOSAL_hitl_question_presentation.md` | The design and the implementation plan. |
| `fixtures/issue_payloads.py` | The operator's verbatim payloads. |
| `diag_input_type.py` | D2 — the input-type misclassification. |
| `diag_duplicate_prompt.py` | D3 — the double rendering, and the render matrix. |
| `diag_roundtrip.py` | D1 + D3 end to end through the real runtime. |
| `diag_reask.py` | D4 + D5 + D6 + D7. |
| `verify_hitl_question_presentation.py` | The acceptance harness (8 invariants). |

---

## 8. Open questions for the operator

1. **Should the report be shown in full?** The `context` field carries it,
   and the consumer prints it above the question. That is the obvious
   behaviour, but a 3 KB report in the middle of a prompt is a lot of
   scroll. Alternative: show the first N lines and a "… (full report above)
   " marker.
2. **Should the input type be guessed at all?** The agent could be
   instructed to emit an explicit marker (`[HITL:yesno]`,
   `[HITL:password]`, …) — the pattern list already recognises
   `[HITL]`/`[QUESTION]`/`[NEEDS_INPUT]`. Guessing is a fallback for when
   the model does not cooperate.
3. **The re-ask guard — how strict?** Normalised equality catches
   rephrasing that keeps the same words. A semantic guard (embedding
   similarity) would catch more but adds a model call per question.
4. **Does the TUI need the same treatment?** The TUI path uses
   `TuiInputModule`, which stores the message in `state.hitl_prompt` and
   shows it in the footer, while the consumer *also* prints it. The same
   duplication exists there; the proposal covers both, but the TUI has its
   own layout to respect.
