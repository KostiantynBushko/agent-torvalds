# Proposal: the HITL question must be a question — and shown once

**Date**: 2026-10-24
**Status**: Proposal — awaiting operator decisions on the four open questions
**Companion to**: `INVESTIGATION_REPORT.md`
**Branch**: `investigate/hitl-questions-issue`
**Scope**: `components/hitl_question.py` (new), `components/hitl_agent.py`,
`components/event_consumer.py`, `components/console_input_module.py`,
`components/whiptail_input_module.py`, `components/human_loop_handler.py`,
`tests/test_hitl_question_presentation.py` (new)

---

## 1. The shape of the fix

```
                       ┌──────────────────────────────────────────┐
  assistant message ──►│ components/hitl_question.py  (NEW)        │
                       │                                          │
                       │   split_question(text)                   │
                       │     -> (question, context)               │
                       │   detect_input_type(question)            │
                       │   normalise_question(question)           │
                       └───────────────┬──────────────────────────┘
                                       │
            ┌──────────────────────────┼───────────────────────────┐
            ▼                          ▼                           ▼
  AgentQuestionEvent          re-ask guard              input type
  .question = question        (normalised key)          (from question)
  .context  = report
            │
            ▼
  EventConsumer._on_agent_question
      prints  context  (once)
      prints  question (once)
      ──► input module receives a SHORT prompt, never the question
```

Three rules make the whole thing work:

1. **Separate the question from the answer** — once, in one module, before
   anything else looks at the text.
2. **Render in exactly one place** — the consumer. The input modules never
   see the question.
3. **Key every decision on the question, never on the answer** — the input
   type, the re-ask guard, the identity.

---

## 2. `components/hitl_question.py` (new)

A small, pure, dependency-free module. Every function is a pure function of
its input, so the whole thing is unit-testable without a workflow, an LLM
or a console.

### 2.1 `split_question(text) -> Question | None`

Splits an assistant message into the question and its context.

```python
@dataclass(frozen=True)
class Question:
    question: str          # what the operator is asked
    context: str           # the surrounding report (may be "")
    options: tuple[str, ...]  # the choices, when the question is a list
```

Algorithm:

1. Normalise line endings, strip trailing whitespace.
2. Split into **paragraphs** on blank lines.
3. Walk the paragraphs from the last to the first:
   * split the paragraph into **lines**;
   * if the paragraph is a **list** (every non-empty line starts with a
     Markdown list marker — `-`, `*`, `+`, `1.`, `1)`), and any line carries
     an interrogative → the whole paragraph is the question, and the list
     items become `options`;
   * otherwise find the last line with an interrogative, and within it the
     last **interrogative sentence**;
   * extend the question backwards over an immediately preceding **lead-in**
     line that ends with `:` (e.g. *"Also, would you like me to:"*).
4. The **context** is everything before the question, trimmed. If the
   context is empty, it is `""`.
5. If no paragraph carries an interrogative → return `None` (the message is
   not a question at all).
6. If the extracted question is longer than `MAX_QUESTION_CHARS` (default
   400), fall back to the last interrogative sentence; if that is still too
   long, truncate on a word boundary with an ellipsis.

**Worked example — `hitl-wrong-question.md`:**

| part | content |
|---|---|
| question | `Want me to start **Phase 0** (the `text.py` preparation layer — pure functions, fully unit-tested, zero risk to the agent) on a `feature/voice-toolkit` branch?` |
| context | the 3 000-character Voice-Output report |
| options | `()` |

**Worked example — `hitl_dublicate_question.md`:**

| part | content |
|---|---|
| question | `Also, would you like me to:` + the two numbered options |
| context | the status report and the branch-name question |
| options | `("Set up sqitch for database version control?", "Start with documentation for the sqitch integration?")` |

Note that the *first* question of the message ("What would you like to name
it?") stays in the context: the HITL round-trip can only carry one
question, so the rest must remain visible.

### 2.2 `detect_input_type(question, options=()) -> str`

Replaces both copies of the current heuristic. It is applied to the
**extracted question**, never to the answer.

| type | rule |
|---|---|
| `password` | the question **asks for** a secret: it contains a secret noun (`password`, `passphrase`, `passcode`, `pin`, `secret`, `credential`, `token`, `api key`) **and** an ask (`what is`, `enter`, `provide`, `type`, `give me`, `supply`) — or it carries an explicit `[HITL:password]` marker. Mentioning a secret is **not** enough. |
| `menu` | the question is a list with two or more options. |
| `yesno` | the question offers a binary choice: `shall I`, `should I`, `do you want`, `would you like`, `do you prefer`, `can I`, `may I`, `is it (ok|fine|alright)`, `confirm`, `proceed`, `go ahead`, `continue` — or it carries `[HITL:yesno]`. |
| `text` | everything else. |

All matching is on **word boundaries** (`\b`), case-insensitive, and the
secret nouns are matched as whole words.

The current behaviour is preserved for the *actual* password case:

| question | before | after |
|---|---|---|
| `What is the sudo password?` | `password` | `password` |
| `Enter the database password:` | `password` | `password` |
| `…with secret redaction on by default.` | `password` ❌ | `text` ✅ |
| `Shall I create the branch feature/x?` | `yesno` | `yesno` |
| `What is the name of the project?` | `yesno` ❌ (`"no"` in *"name"*) | `text` ✅ |

### 2.3 `normalise_question(question) -> str`

The key of the re-ask guard.

* lower-case;
* strip Markdown emphasis (`` ` ``, `*`, `_`, `**`);
* strip punctuation;
* collapse whitespace;
* drop a leading interrogative politeness word (`please`, `could you`,
  `would you`, `do you`, `can you`, `will you`) — no: that would make
  *"Would you like X?"* and *"Do you want X?"* collide. Instead, **keep**
  the wording and only normalise case/punctuation/whitespace.

So:

| question | normalised |
|---|---|
| `Shall I create the branch feature/sqitch-database-migrations?` | `shall i create the branch feature/sqitch database migrations` |
| `Should I create the branch feature/sqitch-database-migrations?` | `should i create the branch feature/sqitch database migrations` |

The two are still different — and that is **correct**: they are genuinely
different questions and the operator may answer them differently. The
re-ask guard is meant to stop the *same* question from being asked twice,
not to merge different ones. The normalisation removes the noise that
makes an identical question look different (trailing whitespace, a
different capitalisation, a stray full stop, a Markdown code span around
the same words).

**So the re-ask guard is about the *same* question, and the operator's
"asked twice" observation is D3 (the double rendering), not D4.** D4 remains
a real weakness — the guard is text-based, so a rephrasing is asked again —
but it is a *different* defect from the one reported, and the fix for the
reported one does not depend on it. §7 lists it as a separate, optional
improvement.

> **Correction to the investigation report.** The report lists D4 (exact-text
> re-ask guard) as one of the causes of the operator's "asked twice"
> complaint. It is not. The operator's transcript shows the *same message*
> rendered twice in one prompt, which is D3. D4 is a real weakness, but a
> different one, and it is not what the operator reported. This proposal
> therefore treats D3 as the fix for the reported symptom and D4 as an
> optional hardening.

---

## 3. `components/hitl_agent.py`

### 3.1 `parse_agent_output()` — use the splitter

```python
text = self._extract_text(ev.response)
split = split_question(text)
if split is None:
    return await super().parse_agent_output(ctx, ev)

if await self._was_answered(ctx, split.question):
    ...
    return await super().parse_agent_output(ctx, ev)

question_id, waiter_id, is_new = await self._resolve_question_identity(ctx, split.question)

if is_new:                      # <-- D5: the replay must not re-log
    logger.info("HITL question detected (%s, type=%s, timeout=%s)", ...)

question_event = AgentQuestionEvent(
    prefix="Agent asks: ",
    question=split.question,
    context=split.context or None,   # <-- the report travels with the question
    input_type=detect_input_type(split.question, split.options),
    options=list(split.options),
    ...
)
```

The `context` field already exists on `AgentQuestionEvent`
(`components/hitl_events.py:104`) and is already rendered by the consumer
(`components/event_consumer.py:697`) — it was simply never filled in.

### 3.2 `_resolve_question_identity()` — report whether the id is new

```python
async def _resolve_question_identity(self, ctx, text) -> tuple[str, str, bool]:
    pending = await ctx.store.get(_PENDING_QUESTION_KEY, default=None)
    if isinstance(pending, dict) and pending.get("question") == text:
        return str(pending["question_id"]), str(pending["waiter_id"]), False   # replay
    ...
    return question_id, waiter_id, True
```

The third element tells the caller whether this is the *first* sighting of
the question. On the workflow replay the same `(question_id, waiter_id)` is
returned, so the "HITL question detected" line is logged once. This is
**D5**.

### 3.3 `_was_answered()` / `_mark_answered()` — key on the normalised question

```python
async def _was_answered(self, ctx, question: str) -> bool:
    key = normalise_question(question)
    answered = await ctx.store.get(_ANSWERED_QUESTIONS_KEY, default=None)
    return isinstance(answered, list) and key in answered
```

The stored value is the *normalised* question, so the history stays
readable. The raw question is still recorded by the `HumanLoopHandler`.

### 3.4 `_QUESTION_PATTERNS` — widen the question-mark pattern (D7)

```python
# before
re.compile(r"\w+\s*\?$", re.MULTILINE),
# after
re.compile(r"[\w`\"')\]]*\s*\?$", re.MULTILINE),
```

A question may end with a code span, a quote or a closing bracket.

The same pattern list is duplicated in `components/human_loop_handler.py:59`
— the copy should import from one place. (`hitl_agent` already imports
from `hitl_events` and `hitl_timeout`; a shared `hitl_question` module is
the natural home.)

---

## 4. `components/event_consumer.py`

### 4.1 `_on_agent_question()` — render once (D3)

```python
# before
self.console.print(f"\n[magenta]🤖 Agent asks: {event.question}[/magenta]{context_str}")
...
result = await self.console_input.confirm(message=event.question, ...)   # renders again

# after
if event.context:
    self.console.print(f"\n[dim]{event.context}[/dim]")
self.console.print(f"\n[magenta]🤖 Agent asks: {event.question}[/magenta]")
...
result = await self.console_input.confirm(message="[y/N] ", ...)   # short prompt
```

The input module never receives the question text. It receives a *prompt
suffix* — the part that is genuinely part of the input widget:

| input type | prompt |
|---|---|
| `text` | `"Your response: "` |
| `yesno` | `"[y/N] "` (or `"[Y/n] "`) |
| `menu` | `"Select option [1]: "` — the options are printed by the consumer |
| `password` | `"Enter password: "` — and the **question is printed by the consumer** (D-I4) |

This also fixes the `menu` duplication (`ConsoleInputModule.menu()` prints
the message itself) and the `password` case (the question is currently
never shown next to the password prompt).

### 4.2 `_collect_answer()` — an empty answer is a timeout (D6)

The yes/no branch hard-codes `was_timeout=False`. It has to distinguish
"the operator pressed Enter" from "the operator said no".

`ConsoleInputModule.confirm()` currently swallows that distinction, so it
gains a sibling:

```python
async def confirm_with_status(self, message, default_yes=True, timeout=NO_TIMEOUT) -> tuple[bool, bool]:
    """Return ``(confirmed, was_timeout)``."""
```

and `confirm()` becomes a thin wrapper over it.

Then:

```python
if input_type == "yesno":
    confirmed, was_timeout = await self.console_input.confirm_with_status(
        message="[y/N] ", default_yes=default_yes, timeout=timeout,
    )
    if was_timeout:
        return default_answer, True
    return ("yes" if confirmed else "no"), False
```

The same treatment applies to the `password` branch (which already returns
`not result` as the timeout flag) and to the `menu` branch (whose
`result == options[0] and not default_answer` heuristic is a guess).

The `WhiptailInputModule` needs the same `confirm_with_status()`.

---

## 5. `components/human_loop_handler.py`

* **delete** `_detect_input_type()` (line 89) and import
  `detect_input_type` from `components/hitl_question.py` — the copy is the
  second source of truth for the same heuristic;
* import `_QUESTION_PATTERNS` from `components/hitl_question.py` instead of
  keeping its own copy (line 59);
* `_record_observation()` should record the **question**, not the whole
  message: `split_question(text)` first, then store
  `split.question` and `split.context`.

---

## 6. Tests

`tests/test_hitl_question_presentation.py` (new) — the unit tests for the
pure module, plus the integration tests for the wiring.

### 6.1 `components/hitl_question.py` — pure unit tests

| test | asserts |
|---|---|
| `test_splits_report_from_question` | the Voice-Output payload → a 1-sentence question and a 3 000-character context |
| `test_splits_list_question` | the sqitch payload → the list is the question, the status report is the context |
| `test_returns_none_without_interrogative` | "All done." → `None` |
| `test_lead_in_is_kept` | "Also, would you like me to:" + a list → the lead-in stays with the question |
| `test_long_question_is_truncated` | a 2 000-character question → capped at `MAX_QUESTION_CHARS` |
| `test_password_needs_an_ask` | "…with secret redaction on by default." → `text`, not `password` |
| `test_password_question_is_password` | "What is the sudo password?" → `password` |
| `test_yesno_needs_a_binary_offer` | "Shall I create the branch x?" → `yesno`; "What is the name of the project?" → `text` |
| `test_word_boundaries` | "name", "notification", "documentation" do not trigger `yesno` |
| `test_menu_when_options_present` | a numbered list of two options → `menu` |
| `test_normalisation_is_stable` | case, punctuation and whitespace do not change the key |

### 6.2 Integration tests

| test | asserts |
|---|---|
| `test_question_rendered_once` | the payload appears exactly once in the console output |
| `test_context_is_rendered` | the report is shown above the question |
| `test_password_prompt_shows_the_question` | the question is visible next to `Enter password: ` |
| `test_input_module_never_receives_the_question` | the recorded prompts contain no part of the question |
| `test_empty_answer_is_a_timeout` | Enter → `was_timeout=True` in the log and in the history |
| `test_question_detected_once` | exactly one "HITL question detected" log line |
| `test_code_span_question_is_detected` | "Shall I use `feature/x`?" is a question |
| `test_answer_still_reaches_the_agent` | the existing round-trip behaviour is unchanged |

### 6.3 The acceptance harness

`investigate/hitl-questions-issue/verify_hitl_question_presentation.py`
already encodes the eight invariants and currently reports **1/8**. It must
report **8/8** when the change is complete.

---

## 7. Phases

| Phase | Content | Risk |
|---|---|---|
| **P0** | `components/hitl_question.py` + its unit tests. Pure functions, no wiring. | none — nothing imports it yet |
| **P1** | Wire the splitter into `HITLFunctionAgent`; fill in `context`; derive the input type from the question; widen the question-mark pattern; make the detection idempotent across the replay. | low — the agent side only |
| **P2** | Fix the rendering: the consumer owns the display, the input modules get short prompts, `confirm_with_status()` for the empty answer. | low — the consumer side only |
| **P3** | Delete the duplicated heuristic and pattern list from `human_loop_handler.py`; record the question (not the message) in the history. | low |
| **P4** | TUI parity: `TuiInputModule` gets the same short-prompt treatment; the TUI shows the context in the markdown view and the question in the footer. | medium — the TUI has its own layout |
| **P5** | Optional hardening: semantic re-ask guard, `menu` input type, explicit `[HITL:type]` markers. | optional |

P0–P3 are the fix for the reported defects. P4 and P5 are follow-ups.

---

## 8. What this does *not* change

* the HITL plumbing (event stream, waiter, answer round-trip) — it works;
* the timeout convention (`-1` = wait forever);
* the CLI flags and the environment variables;
* the chat-history format;
* the behaviour with HITL disabled.

---

## 9. Decisions needed from the operator

1. **How much context is shown?** The full report above the question, or
   the first N lines with a "… full report above" marker?
2. **Should the model be allowed to declare the input type?** An explicit
   `[HITL:yesno]` marker is unambiguous; guessing is a fallback. Both?
3. **Is the `menu` input type worth wiring up?** The sqitch payload is
   naturally a two-option menu, and the machinery already exists
   (`AgentQuestionEvent.options`, `ConsoleInputModule.menu()`), but the
   agent never produces it today.
4. **Should the re-ask guard become semantic?** The text-based guard only
   catches the identical question. An embedding comparison catches
   rephrasings but costs a model call per question.

---

## 10. Appendix — the defects this proposal closes

| # | Defect | Closed by | Phase |
|---|---|---|---|
| **D1** | the whole answer becomes the question | `split_question()` + `AgentQuestionEvent.context` | P1 |
| **D2** | the input type is guessed from the answer | `detect_input_type(question)` on the extracted question, word-boundary matched, one copy | P1, P3 |
| **D3** | the question is rendered twice | the consumer owns the rendering; the input modules get short prompts | P2 |
| **D4** | the re-ask guard compares exact text | `normalise_question()` | P1 (hardening) |
| **D5** | the question is re-detected on the replay | `_resolve_question_identity()` reports "is new" | P1 |
| **D6** | an empty answer is recorded as "no" | `confirm_with_status()` | P2 |
| **D7** | a code-span question is not detected | the widened question-mark pattern | P1 |
