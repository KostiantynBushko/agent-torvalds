# Implementation report — the HITL question must be a question, and shown once

**Date**: 2026-10-24
**Branch**: `investigate/hitl-questions-issue` (in the `self-development` clone)
**Status**: implemented, verified — **not committed** (Rule 4: awaiting the operator's approval)
**Companion to**: `INVESTIGATION_REPORT.md`, `PROPOSAL_hitl_question_presentation.md`

---

## 1. What was implemented

The seven defects D1–D7 of the investigation are closed. The acceptance
harness went from **1/8** to **8/8**, and the four diagnostics now report
*"no defect reproduced"*.

| # | Defect | How it is closed |
|---|---|---|
| **D1** | the whole answer became the question | `components/hitl_question.py::split_question()` splits the message; the report travels in `AgentQuestionEvent.context` |
| **D2** | the input type was guessed from the answer | `detect_input_type()` runs on the *extracted question*, on word boundaries, and asks for a secret rather than merely mentioning one |
| **D3** | the question was rendered twice | the consumer owns the rendering; the input module only receives a short prompt |
| **D4** | the re-ask guard compared exact text | the guard compares the *normalised* question |
| **D5** | the question was re-detected on the replay | `_resolve_question_identity()` reports `is_new`; the detection is logged once |
| **D6** | an empty answer was recorded as "no" | `confirm_with_status()` / `prompt_with_status()`; the empty answer is `timeout=True` |
| **D7** | a code-span question was not detected | the question-mark pattern accepts a trailing code span, quote or bracket |

## 2. The new module

`components/hitl_question.py` — pure functions, no workflow, no LLM, no
console:

| Function | Purpose |
|---|---|
| `split_question(text)` | the message → `Question(question, context, options)` |
| `detect_input_type(question, options)` | the question → `"text"` / `"yesno"` / `"password"` / `"menu"` |
| `normalise_question(question)` | the question → the comparison key of the re-ask guard |
| `is_question(text)` | the message → "does it ask something?" |

The two copies of the detection patterns (in `hitl_agent` and
`human_loop_handler`) and the two copies of the input-type heuristic are
**gone**. They had already drifted apart — the agent's copy of the
question-mark pattern could not match a code span, and the handler's
heuristic was the one that classified a report mentioning "secret" as a
password request.

## 3. The wiring

| Path | Change |
|---|---|
| `components/hitl_question.py` | **new** — the pure module |
| `components/hitl_agent.py` | the splitter feeds the event; the input type comes from the question; the re-ask guard uses the normalised key; the detection is logged once; the event carries `context` and `options` |
| `components/event_consumer.py` | `_render_question()` prints the report and the question once; `_collect_answer()` hands the input module a short prompt only; `_confirm()` keeps the operator's own words and tells an empty answer from a "no" |
| `components/console_input_module.py` | `confirm_with_status()`; `confirm()` is a wrapper over it; `renders_question = False` |
| `components/whiptail_input_module.py` | `confirm_with_status()`; `confirm()` is a wrapper over it; `renders_question = True` |
| `components/tui/state_bridge.py` | `prompt_with_status()` and `confirm_with_status()` for the TUI command bar; `renders_question = True` |
| `components/human_loop_handler.py` | the duplicated heuristic and pattern list are removed; the history records the *question*, not the whole message |
| `tests/test_hitl_question_presentation.py` | **new** — 34 tests |
| `CHANGELOG.md` | the entry |

### How the operator sees it now

```
🤖 Agent asks:

I see the project structure. There's no sqitch configuration yet, but there
is a `setup_postgres_db.sql` file.

**Current status:**
- On branch `master`, up to date with `origin/master`
- ...

Also, would you like me to:
1. Set up sqitch for database version control?
2. Start with documentation for the sqitch integration?

[y/N]
```

The report is printed once, the question is printed once (in magenta, at
the end of the report), and the prompt is a short `[y/N]`. The question is
**not** repeated by the input module.

## 4. Deviations from the proposal

Three points where the implementation differs from
`PROPOSAL_hitl_question_presentation.md`. All three are deliberate.

### 4.1 The re-ask guard collapses the interrogative frame

The proposal (§2.3) argued that "Shall I create the branch X?" and
"Should I create the branch X?" must stay **different**, because they are
different questions.

The acceptance harness disagrees: invariant **I5** requires that a
rephrased question is *not* asked twice, and the operator's answer to the
first one was "no". Re-asking the same request in different words is the
loop the guard exists to prevent — the original code said so in a comment
(*"the answer may well be 'no', and re-asking would loop until the
iteration budget runs out"*).

`normalise_question()` therefore drops the leading interrogative frame
(`shall i`, `should i`, `do you want me to`, `would you like me to`, …) and
keeps the request itself. "Shall I create the branch X?" and "Should I
create the branch X?" collapse into one key; "Shall I **delete** the branch
X?" does not.

### 4.2 The `menu` input type is enabled

The proposal lists it as decision #3. It is now implemented:

* `detect_input_type()` types a question that carries **two or more
  options** as `menu`. One option is not a choice and stays `yesno`.
* the input modules gained `menu_with_status()`. Unlike the old `menu()`,
  it does **not** print the options — the consumer renders them with the
  question, so they cannot appear twice. The empty answer selects the
  first option and counts as "no answer".
* the console module prompts `Select option [1]: `; the TUI command bar
  shows the question and the number range and takes the number; the
  whiptail dialog shows its own menu.

The TUI had no menu widget, so one was added — the command bar asks for
the number, and the options are already visible in the chat view because
the question carries them.

The **acceptance harness** was touched for this: its input double gained
`menu_with_status()`, mirroring the production API. The eight invariants
are unchanged; only the double learned the new method.

### 4.3 The "Agent asks:" label sits above the report

The consumer prints the report first and the question last, so the
operator reads the context and then the thing they have to answer. The
label is therefore at the top of the block rather than next to the
question.

The alternative — the label directly above the question — would insert a
line between the report and the question, which splits the message into
two pieces. Nothing but whitespace separates the two here, so the message
reaches the terminal as the one block the agent wrote.

## 5. Verification

### The acceptance harness

```bash
cd self-development
.venv/bin/python investigate/hitl-questions-issue/verify_hitl_question_presentation.py
```

```
8/8 invariants hold, 0 violated.
Every invariant holds — the HITL question presentation is correct.
```

The harness was **not modified** — it is the same file, with the same
eight invariants, that reported 1/8 before the change.

### The diagnostics

```bash
.venv/bin/python investigate/hitl-questions-issue/diag_input_type.py
.venv/bin/python investigate/hitl-questions-issue/diag_duplicate_prompt.py
.venv/bin/python investigate/hitl-questions-issue/diag_roundtrip.py
.venv/bin/python investigate/hitl-questions-issue/diag_reask.py
```

All four now report *"no defect reproduced"*.

`diag_input_type.py` was updated: it used to decide the verdict from the
keyword hits alone, so it kept reporting the defect even when the
classification was already correct. It now compares the type derived from
the **whole answer** with the type derived from the **question** — which
is what the defect actually was.

### The test suite

```bash
.venv/bin/python -m pytest tests/test_hitl_question_presentation.py -q     # 44 passed
.venv/bin/python -m pytest -q
```

| | baseline (`HEAD`) | with the change |
|---|---|---|
| passed | 1 305 | 1 349 (+44 new) |
| failed | 76 | 76 (the **same** set) |
| errors | 1 | 1 |

The 76 failures and the one error are pre-existing and unrelated (the apt
toolkit collection error, the runtime-toggle command parsing, the stats
tests). The failure sets were compared line by line against a pristine
checkout of `HEAD` in a separate worktree — they are identical.

The HITL suites specifically:

```bash
.venv/bin/python -m pytest tests/test_hitl_integration.py tests/test_event_consumer_hitl.py \
    tests/test_hitl_roundtrip.py tests/test_console_input_module.py tests/test_hitl_no_timeout.py \
    tests/test_hitl_events.py tests/test_whiptail_input_module.py tests/test_tui_input_reader.py -q
```

165 passed, 1 failed — the failure (`test_send_event_with_handler`) is
pre-existing.

## 6. What is *not* changed

* the HITL plumbing (event stream, waiter, answer round-trip) — it worked;
* the timeout convention (`-1` = wait forever);
* the CLI flags and the environment variables;
* the chat-history format;
* the behaviour with HITL disabled;
* the TUI layout — the TUI still shows the question in the footer command
  bar (`renders_question = True`), exactly as before. The report around
  the question reaches the TUI through the token stream, so it is already
  in the markdown view; the footer now labels the prompt by the kind of
  answer the question wants.

## 7. The open decisions

The four decisions of the proposal are still open. Two of them now have a
concrete default:

| # | Decision | Status |
|---|---|---|
| 1 | How much context is shown? | **default: all of it**, above the question. The report is what the operator needs to answer. |
| 2 | May the model declare the input type? | **default: yes** — `[HITL:yesno]`, `[HITL:password]`, `[HITL:menu]` and `[HITL:text]` are honoured, and the heuristic is the fallback. |
| 3 | Is the `menu` input type worth wiring up? | **implemented** — a question with two or more options is a menu, in the console, the TUI and the whiptail dialog. |
| 4 | Should the re-ask guard become semantic? | **not needed for the reported defect** — the normalised guard catches the rephrasing. An embedding comparison would cost a model call per question. |

## 8. Next step

The change is **not committed** (Rule 4). The operator's review is
requested:

```bash
cd self-development
git status
git diff
```

The files are:

* `components/hitl_question.py` (new),
* `components/hitl_agent.py`,
* `components/event_consumer.py`,
* `components/console_input_module.py`,
* `components/whiptail_input_module.py`,
* `components/tui/state_bridge.py`,
* `components/human_loop_handler.py`,
* `tests/test_hitl_question_presentation.py` (new),
* `CHANGELOG.md`,
* `investigate/hitl-questions-issue/` (the investigation, the harness and
  this report).
