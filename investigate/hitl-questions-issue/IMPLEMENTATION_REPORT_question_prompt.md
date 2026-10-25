# Implementation report — the question prompt, the Markdown and the secret

**Date**: 2026-10-25
**Branch**: `fix/hitl-question-detection`
**Scope**: `components/hitl_question.py`, `components/console_markdown.py` (new),
`components/console_input_module.py`, `components/event_consumer.py`,
`components/tui/state_bridge.py`, `components/tui/layout_manager.py`,
`scripts/hitl_question_bank.py`, `scripts/hitl_interactive_test.py`,
`tests/test_hitl_question_bank.py` (new), `tests/test_hitl_question_presentation.py`,
`tests/test_console_input_module.py`
**Companion to**: `INVESTIGATION_REPORT.md`, `PROPOSAL_hitl_question_presentation.md`
**Nothing in the main repository was touched** (SELF_DEVELOPMENT_RULES.md, rule 1 and 2).

---

## 1. What the operator asked for

Three things, in the operator's words:

1. *the agent question must be rendered as markdown text*;
2. *do not use `getpass` — it sometimes fails, and even after terminating the agent it
   applied to the terminal; instead hide the real value with asterisks*;
3. *investigate why the prompt always starts with `[y/N]`, even for a multiple-choice
   question*.

The third one is the defect that made the first two visible: the operator was asked
*"Which of these should I investigate first?"* and got a `[y/N]` prompt.

---

## 2. The root cause of the `[y/N]` prompt

The `[y/N]` prompt is not a bug in the prompt — it is the **correct** prompt for a
yes/no question.  The bug is that **every** question was classified as a yes/no
question.

`components/hitl_question.py` decided the input type from a list of substring
patterns.  Three of them were far too loose:

| pattern | what it matched | why it is wrong |
|---|---|---|
| `\b(want\|need)\s+me\s+to\b` | *"What is the name of the branch **you want me to** create?"* | the operator is asked for a **value**; the phrase is a relative clause inside a noun phrase, not an offer |
| `\bshould\s+i\b` | *"**Which of these should I** investigate first?"* | a **choice** between the findings, not a binary offer |
| `\b(confirm\|proceed\|go ahead\|continue)\b` | any prose that mentions the word | too loose in general |

The consequence was that `detect_input_type()` returned `"yesno"` for **every**
question, and the consumer — correctly — rendered `[y/N]`.

Measured on the question bank (`scripts/hitl_question_bank.py`, 16 real assistant
messages), **9 of the 16 cases were mis-routed**:

| case | expected | was |
|---|---|---|
| `text-01-simple` — *"What is the name of the branch you want me to create?"* | `text` | `yesno` |
| `text-02-with-context` — *"Which of these should I investigate first?"* | `text` | `yesno` |
| `text-03-explicit-marker` — *"[HITL:text] Enter the hostname…"* | `text` | *not a question at all* |
| `menu-01-three-options` | `menu` | `yesno` |
| `menu-02-lead-in-colon` | `menu` | `yesno` |
| `menu-03-two-options` | `menu` | `yesno` |
| `password-01-api-key` — *"Please enter the API key…"* | `password` | *not a question at all* |
| `password-02-passphrase` — *"[HITL:password] Enter the passphrase…"* | `password` | *not a question at all* |
| `llm-01-inline-options` — *"(a) … (b) … (c) …"* | `menu` | `yesno` |

Three separate causes:

* **A.** the yes/no heuristics (§2.1);
* **B.** the *question detection* did not know the ask verbs (*"enter"*, *"provide"*)
  or the typed markers (`[HITL:text]`) — so a password question was not a question at
  all and never reached the operator (§2.2);
* **C.** the *menu detection* only understood a Markdown list that carried its own
  lead-in — not a list in its own block, and not the inline `(a) … (b) … (c)` a model
  really produces (§2.3).

---

## 3. The fix

### 3.1 The yes/no decision is now a decision, not a substring match

`detect_input_type()` asks a new helper, `_is_yes_no()`, which applies two rules in
order:

1. **an open question is never a binary offer.**  A wh-question at the head of the
   question — *"Which …"*, *"What …"*, *"Who …"*, *"Where …"*, *"When …"*,
   *"Why …"*, *"How …"* — wants a value or a choice.  It is never prompted as
   `[y/N]`;
2. **otherwise the question has to *offer* something.**  *"shall I …?"*, *"do you
   want …?"*, *"is it ok …?"*, *"confirm …"*, and — with one exception — *"want me to
   …"*.

The exception is the *"you want me to"* relative clause: *"the branch **you want me
to** create"* is not an offer, so it no longer makes the question a yes/no question.
The look-behinds in `_RELATIVE_OFFER` skip the genuine offers (*"**Do** you want me
to …?"*, *"**Would** you like me to …?"*).

### 3.2 The question detection learned to ask

* `_REQUESTS` gained an **imperative-ask** pattern: *"Please enter the API key …"*,
  *"Provide the passphrase …"*.  The verb has to start the sentence, so ordinary prose
  that happens to contain *"enter"* is not a request.
* The HITL marker pattern now accepts a **type**: `[HITL:text]`, `[HITL:password]`,
  `[HITL:menu]`, `[HITL:yesno]`.  The type was already honoured by
  `detect_input_type()`; the *detection* ignored it, so a marked message was not
  recognised as a question at all.

### 3.3 A choice is a choice

`split_question()` now finds the options in three shapes, and — this is the part that
changed the contract — **the question no longer repeats the options**:

| shape | example | options |
|---|---|---|
| a list in the question block | *"Also, would you like me to:"* + `1. …` `2. …` | the list items |
| a list in the **next** block | *"Which environment should I deploy to?"* + a blank line + `1. staging` `2. production` | the list items |
| an **inline** choice | *"Options: **(a)** proceed, **(b)** point me at the file, or **(c)** cancel."* | the three segments |

The options travel in `Question.options` → `AgentQuestionEvent.options`, and the
consumer renders them as the menu.  A question that used to be read twice (once as
the question, once as the menu) is now read once.

The `•` bullet is a list marker as well — a report that uses `•` bullets is a list,
not a paragraph.

### 3.4 The question is rendered as Markdown

`EventConsumer._render_question()` used `rich.markup.escape()`, which prints the
Markdown **source**: the operator read `**Current status:**` and
`` `origin/master` ``.  It now renders the Markdown:

* `components/console_markdown.py` (new) — `render_markdown()` and `render_options()`;
* `AgentMarkdown` — `rich.markdown.Markdown` with one fix: `rich` renders the marker
  of an ordered list as the bare number (` 1 item`), which makes a numbered menu
  unreadable.  The list item is subclassed so the marker is `1.` again;
* the question and the report are rendered as Markdown, the `[HITL:…]` marker is
  stripped (it is an instruction to the detector, not something to read), and the
  choices of a menu are rendered as the numbered list the prompt refers to.

### 3.5 The secret is masked with asterisks — and the terminal survives it

`getpass` is **gone** from the input module.  `getpass.getpass()` opens `/dev/tty`,
which fails when the agent runs without a controlling terminal, and it can leave the
terminal with the echo flag cleared when the process dies inside the prompt — the
operator is left with a mute terminal that has to be fixed with `stty sane`.

`components/console_input_module.py` now has `read_masked()`:

* the echo is switched off with `termios` and switched on again in a `finally`
  block, so neither an exception, nor a Ctrl-C, nor a timeout can leave the terminal
  mute;
* an `atexit` hook covers a clean shutdown (the agent's SIGINT/SIGTERM handler ends in
  `sys.exit()`);
* the read is **polled**, so a timeout is honoured — a blocking read could not give
  the terminal back until the operator pressed a key;
* each character is echoed as an asterisk, so the operator sees that something was
  typed and never the secret itself.

Verified in a real pty:

| path | result |
|---|---|
| type `s3cr3t` | the terminal shows `******`, the reader returns `s3cr3t` |
| Ctrl-C | `ECHO` restored — the terminal is not mute |
| timeout | `ECHO` restored, the value is empty |

### 3.6 The TUI keeps up

The TUI prints the consumer's output into a *silent* console, so the question reaches
the operator through the command bar.  The choices no longer travel inside the
question, so `TuiInputModule.menu_with_status()` now shows them:

```
🤖 AGENT QUESTION: Which one should I use?
1. Patch the config file directly
2. Add an environment variable override
3. Regenerate the file from the schema
Option: _
```

`render_footer()` escapes the question — it is agent text and may contain square
brackets, which `rich` would read as markup.

---

## 4. The result

### 4.1 The question bank — the acceptance criterion

`scripts/hitl_question_bank.py` is 16 real assistant messages with the input type
each of them must produce.  It is now the criterion of the whole feature, and
`tests/test_hitl_question_bank.py` runs every case through the rules:

| | before | after |
|---|---|---|
| cases with the expected type | **7 / 16** | **16 / 16** |

The `known_issue` field of the bank — "the current rules are known to mis-route this
case" — became `regression`: "what defect this case caught".  The cases stay in the
bank forever; the text names the bug a failure would be a regression of.

### 4.2 The verification harness

`investigate/hitl-questions-issue/verify_hitl_question_presentation.py`:

```
8/8 invariants hold, 0 violated.
```

I1 changed with the contract: the *payload* is no longer one contiguous block (the
report, the question and the menu are three blocks now), so I1 counts the renderings
of the **question** and checks that the report above it is still shown.

### 4.3 The prompts, before and after

| question | before | after |
|---|---|---|
| *"What is the name of the branch you want me to create?"* | `[y/N]` | `Your response: ` |
| *"Shall I delete the old `auth_v1` directory?"* | `[y/N]` | `[y/N]` ✓ (a genuine yes/no) |
| *"I can apply the fix in three ways. Which one should I use?"* + 3 options | `[y/N]` | the numbered menu + `Select option [1]: ` |
| *"Please enter the API key for the GitHub remote."* | *never asked* | `Enter password: ` + `*****` |

### 4.4 The test suite

| | before | after |
|---|---|---|
| full suite | 41 failed, 1384 passed | 39 failed, 1432 passed |
| HITL suites | — | 209 passed |

The remaining failures are **pre-existing** and unrelated (the apt toolkit, the
manual event scripts, the HITL runtime toggle, the whiptail workflow, and a flaky
pty-timing test in `tests/test_tui_input_reader.py` — that one alone makes the count
move between 39 and 41).  The comparison is a diff of the two failure lists:
**no new failure was introduced**.

### How the comparison was made

The baseline is the same tree with the change stashed — the *same* command, the
*same* interpreter, the *same* machine:

```bash
cd self-development
git stash -u                       # the change goes away, the tree is master again
python3 -m pytest -q > /tmp/base_suite.log
git stash pop                      # the change comes back
python3 -m pytest -q > /tmp/new_suite.log

grep "^FAILED\|^ERROR" /tmp/base_suite.log | sed 's/ - .*//' | sort > /tmp/fail_base.txt
grep "^FAILED\|^ERROR" /tmp/new_suite.log  | sed 's/ - .*//' | sort > /tmp/fail_new.txt

comm -13 /tmp/fail_base.txt /tmp/fail_new.txt   # the failures this change introduced
comm -23 /tmp/fail_base.txt /tmp/fail_new.txt   # the failures it removed
```

`comm -13` printed nothing: the change introduced no failure.  The run is
reproducible — the two counts move only because of the pty-timing test.

---

## 5. What changed in the contract

Two contracts changed, deliberately, and both are visible in the tests:

1. **the question does not repeat the choices.**  The choices travel in
   `Question.options` → `AgentQuestionEvent.options`, and the consumer renders them
   as the menu.  Before, a menu question showed the list twice — once inside the
   question, once as the menu.
2. **the question is Markdown.**  `EventConsumer._render_question()` renders it;
   the input module still receives only a short prompt, and the question is never
   shown twice.

---

## 6. What was not changed

* the HITL plumbing — the event stream, the waiter, the answer round trip;
* the timeout convention (`-1` = wait forever);
* the CLI flags and the environment variables;
* the chat-history format;
* the behaviour with HITL disabled;
* the whiptail dialog (it has its own layout and shows the choices itself).

---

## 7. How to verify it

```bash
cd self-development

# The question bank — the acceptance criterion (16 cases).
.venv/bin/python -m pytest tests/test_hitl_question_bank.py -v

# The HITL suites.
.venv/bin/python -m pytest \
    tests/test_hitl_question_presentation.py \
    tests/test_console_input_module.py -v

# The eight presentation invariants.
.venv/bin/python investigate/hitl-questions-issue/verify_hitl_question_presentation.py

# The interactive harness — the operator drives it:
.venv/bin/python scripts/hitl_interactive_test.py
```

The interactive harness now renders the question as Markdown, shows the menu, and
masks the secret with asterisks — the same three changes the operator asked for.

---

## 8. The defects this closes

| # | Defect | Closed by |
|---|---|---|
| **D1** | every question was prompted as yes/no — the `[y/N]` prompt | `_is_yes_no()`: the wh-question veto and the relative-clause guard |
| **D2** | *"Please enter the API key …" was not a question at all | the imperative-ask pattern in `_REQUESTS` |
| **D3** | the `[HITL:type]` marker was not honoured by the detection | the marker pattern accepts a type |
| **D4** | a list of choices was not a menu | the list-in-the-next-block and the inline-choice rules |
| **D5** | the question was shown as Markdown **source** | `components/console_markdown.py` |
| **D6** | the menu was rendered without a number — `rich` drops the dot | `AgentMarkdown._NumberedListItem` |
| **D7** | `getpass` could leave the terminal mute | `read_masked()`: `termios` + `finally` + `atexit` + a polled read |
| **D8** | the secret was never masked with asterisks | `read_masked()` echoes one `*` per character |
