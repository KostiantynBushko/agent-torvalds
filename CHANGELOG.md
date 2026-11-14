# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

#### The size of the context is in the telemetry panel of the TUI

- **The operator asked for the size of the context to be visible while
  the agent works.**  The log line of 2026-11-04 — *"I need to see in the
  log the context size in tokens and size of bytes.  So when request is
  made to LLM I want to see current context size"* — is in a file in
  another terminal, and the multi-window console has a panel that shows
  the state of the agent while it works.  The size of the context was not
  in it.

- **The panel shows the measurement that already exists.**  The agent
  measures the prompt before every request (`measure_context()` in
  `components/context_metrics.py`), and the log line is rendered from
  that measurement.  The panel renders **the same** `ContextSize` — in
  two lines instead of one:

  ```
  Context │ 39,691 tok (4.0% of 1M)
          │ 75 msgs · 155.6 KB
  ```

  A second measurement would be a second number that can disagree with
  the first, and the operator would have to work out which one is the
  truth before acting on it.

- **The share of the window is coloured.**  Green below 50%, yellow from
  50%, red from 80%: a context that is three quarters full is a context
  the operator has to know about before the next tool result lands in
  it.  An estimated number (no tokenizer available) says so with `≈`.

- **The observer is called before the logging flag is checked.**
  `--no-context-log` turns the **log** off — it does not turn the
  readout on the screen off.  An operator who does not want the size of
  the prompt in the log file still wants to see it while the agent
  works.

- **The agent does not know about the TUI.**  The measurement reaches
  the panel through an observer (`agent.context_observer`) that the
  multi-window console installs.  The classic console has no panel, and
  the observer stays `None`.  An observer that raises never takes the
  run down: a size is never worth a run.

- **The sidebar was left alone.**  The telemetry pane grew by two lines —
  four at the width of a narrow terminal, where the value of a row wraps.
  At 120×40 (the reference size) and at 80×30 the readout is complete
  and nothing else is lost.  At 80×24 — the smallest supported
  terminal — the readout keeps its first line, the tokens and the share,
  and the bottom of the panel is cut, as it was before.  The alternative
  (the telemetry pane taking two thirds of the sidebar) was measured
  too: it buys the second line of the readout at 80×24 **only**, and it
  costs the progress pane its tool tasks at every size — 3 → 0 at 80×24,
  6 → 2 at 80×30, 6 → 5 at 120×40.

- **The design is in `investigate/tui-context-readout/`.**

#### The manual test of the question of the agent and of the password of root

- **The operator asked for it on 2026-11-10:**

  > *now I need a manual test to be able to test hitl and sudo passwrod,
  > since I have notices that running hitl question to operator and sudo
  > pkexec with UI Authentication dialog may be related to the issue with
  > hidded input in terminal*

- **The probes measure the hidden typing *for* the operator.**
  `investigate/tui-hidden-input/probe_hidden_input.py` and
  `investigate/privilege-terminal-echo/probe_privilege_terminal.py` render
  the TUI into a buffer of their own and measure it there — the typed
  text is on the screen, the terminal is given back.  What they cannot do
  is put the operator in front of the thing and ask *do you see it?*.

- **`scripts/manual_hitl_privilege_test.py` drives the real components in
  the terminal of the operator.**  Nothing is simulated: the layout, the
  panels, the reader and the input module of the TUI are the production
  ones, and the privilege part runs the production
  `execute_shell_command` of the Linux toolkit, behind the production
  gate.

  | Part | What the operator does | What is measured |
  |---|---|---|
  | the question of the agent | the real TUI is drawn, and the answer is typed into its footer | the answer arrives; the typed text is on the screen; the answer line is not cropped away; the terminal echoes again afterwards |
  | the password of root | a `sudo` command is run, and polkit asks for the password **in a window** of the desktop | the window opened; the terminal echoed again afterwards |

- **The two questions are not the same thing, and the script says so.**
  The question of the agent is asked *in the terminal* — the TUI draws
  what the operator types, so the text has to be on the screen.  The
  password of root is asked *in a window*, and the terminal of the
  operator is not involved in it at all.  What the two share is the
  state of the terminal: an application that owns the screen switches
  the echo off, and that state belongs to the **terminal**, not to the
  process.

- **The comparison is one flag away.**
  `--privilege-mode sudo` runs the command as it was written: the
  password is then asked on the terminal, and the terminal hides what is
  typed while it is read.  That is the path the hidden typing was
  reported on — and the script measures that the terminal is given back
  afterwards, even when the timeout kills the `sudo` in the middle of the
  question.

  ```bash
  python scripts/manual_hitl_privilege_test.py            # both parts
  python scripts/manual_hitl_privilege_test.py hitl       # only the question
  python scripts/manual_hitl_privilege_test.py privilege  # only the password
  python scripts/manual_hitl_privilege_test.py --privilege-mode sudo
  ```

#### A predefined question can be asked with `\question`

- **The operator asked for it on 2026-11-10:**

  > *I also noticed that it may happen after the agent runs HITL and asks
  > the operator a question, so I need a predefined hardcoded test — when
  > the operator runs a predefined command, for example `\question`, the
  > agent must run HITL to ask some predefined question for the operator.
  > The agent should not run any tools, just ask the question and process
  > the response.*

- **The HITL path could only be tested through the model.**  Every
  question the agent asked came out of an answer of the LLM: the model
  had to decide to ask, and the question had to survive the detection.
  A report that "the agent never asked me anything" therefore had two
  possible causes — the model did not ask, or the HITL path did not
  deliver the question — and nothing told them apart.

- **`\question` asks a question that is known.**  The command takes a
  question from a bank of **predefined** questions and asks it through
  the *real* HITL path: the question is rendered by the event consumer
  and the answer is collected by the input module, exactly as the answer
  of an agent question is.

  | Command | What it does |
  |---|---|
  | `\question` | Ask the next predefined question — the bank is walked in turn. |
  | `\question <id>` | Ask that exact question: `text-01`, `yesno-01`, `menu-01`, `password-01`. |
  | `\question list` | List the predefined questions. |

  The bank holds one question per input type — `text`, `yesno`, `menu`
  and `password` — so a run of the command covers every kind of prompt
  the HITL path can produce.

- **No tool is run, and the model is never called.**  The command tests
  the HITL path and nothing else: a failure of the command says
  something about the machinery, and nothing about the model or the
  tools.

- **The answer is processed, and the report is honest about it.**

  | Rule | Why |
  |---|---|
  | a timeout is reported as "nobody answered", never as an answer | the operator has to be able to tell the two apart — rule 5 of the development rules |
  | the passphrase of a `password` question is never echoed | a secret does not belong in a report |
  | the answer is not written into the conversation memory | a test answer must not become the context of the next turn of the agent |

- **The round trip was in one place, and it had to come out of it.**  The
  rendering of the question and the collection of the answer lived in
  `EventConsumer._on_agent_question`, which sends the answer into a
  workflow.  The command has no workflow — there is no agent to answer —
  so the round trip was pulled out into `EventConsumer.ask_question()`,
  and the workflow path calls it.  One implementation, two callers: a
  question asked by the agent and a question asked by the command travel
  the same road.

- **The tests are in `tests/test_hitl_question_command.py`** — the bank
  agrees with the rules of the detection, the question travels the HITL
  path, no tool is run, the answer is processed, a timeout is not an
  answer, a secret is not echoed, and the command asks nothing when the
  Human-in-the-Loop is off.

#### A command that needs root asks for the password in a window

- **The operator asked for it on 2026-11-09:**

  > *in the linux toolkit we can run a command so we need a solution to
  > handle 'sudo' in the command please consider "pkexec" it must run UI
  > window with a request to user to type sudo password*

- **`sudo` reads the password from the terminal, and the terminal of the
  agent is not a terminal the operator can answer.**  The TUI puts the
  terminal into cbreak mode — `components/tui/input_reader.py` does it
  with `tty.setcbreak`, which switches the echo off, because the
  application draws the screen itself.  A `sudo` prompt written into that
  terminal is painted over by the next frame, and the keystrokes are read
  by the input reader of the TUI, which never hands them to `sudo`.  The
  command hangs until the timeout kills it, and the operator is never
  asked anything.

- **A `sudo` in a command of the Linux toolkit is escalated through
  `pkexec`.**  `pkexec` asks **polkit** for the authorisation, and polkit
  puts the question in a **window** — the window the operator is already
  looking at.  The password never touches the terminal the agent is
  drawing on.

  ```
  sudo systemctl restart nginx
  → pkexec --keep-cwd systemctl restart nginx
  ```

  The rewrite is narrow on purpose:

  | Rule | Why |
  |---|---|
  | only a `sudo` **in command position** is rewritten | `grep sudo /etc/sudoers` is not an escalation |
  | `--keep-cwd` is always added | `pkexec` runs a program in the home of the target user, `sudo` does not |
  | `--disable-internal-agent` is added when the terminal belongs to an application | it stops `pkexec` from asking on the terminal — the thing this is about |
  | `--user` carries `sudo -u` over | `pkexec --user www-data cmd` runs the program as `www-data` |
  | the flags `pkexec` cannot express are dropped, and the drop is reported | `sudo -E` keeps the environment; `pkexec` sanitises it anyway |
  | `sudo -l`, `sudo -v` and `sudo -e` are left alone | they do not run a program, and `pkexec` cannot do them |
  | everything else is left byte for byte | the redirections, the quotes and the spacing survive |

  The command line is **scanned**, not matched with a regular expression:
  the scan knows where a shell starts a program and where it does not, so
  a `sudo` that is only an argument is left alone.

- **The measurements are in
  `investigate/linux-privilege-escalation/`.**  `pkexec(1)` was read on
  the machine of the operator, and the behaviour was measured there:

  | What | What it showed |
  |---|---|
  | `pkexec --keep-cwd /bin/pwd` | the working directory is kept — without the flag it is the home of the target user |
  | `pkexec --keep-cwd --user nobody /usr/bin/id` | `sudo -u` carries over, and it needs `--keep-cwd` as well |
  | `pkexec --disable-internal-agent` | without a graphical agent, `pkexec` **waits** (the command was still running after 8 seconds, and was killed) — so the toolkit only uses `pkexec` when there is a display **and** an agent |
  | `pkexec --version` → 126 / 127 | 126 is a dismissed dialog, 127 is "not authorised" — both are reported, neither is retried |

- **The password is never handled by the toolkit.**  polkit asks the
  operator, and the toolkit only ever sees the exit code.  There is
  nothing to leak, because there is nothing to keep.

- **The agent can say what is going to happen.**
  `check_privilege_backend()` reports whether a window will open, and the
  description of the two execution tools tells the model to warn the
  operator that a window is about to appear.

- **An escalated command gets 300 seconds** instead of the usual thirty:
  the window stays open until somebody answers it.  A timeout the caller
  asked for is respected.

- **The library half keeps its dependency profile.**  `privilege.py` is
  built on the standard library alone — `subprocess`, `os`, `shutil`,
  `re`, `shlex`, `dataclasses`, `termios` — and the toolkit still has no
  third-party dependency at all.

- **The tests are in `toolkits/linux-toolkit/tests/test_privilege.py`.**
  They are offline: no test runs `pkexec`, and no test opens a window.

#### A failed model request is sent again when the model server failed

- **The agent stopped when the model server answered 500.**  The failure
  of the report:

  ```
  2026-11-09 08:00:29,622 [ERROR] components.event_consumer: EventConsumer.consume_events: exception: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500)
  ollama._types.ResponseError: Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500)
  ```

  A 500 from Ollama means the **model died** — out of memory, or a crash
  while it was loading.  The request was fine, and a request that is
  fine is worth sending again.  The agent sent it once and gave up.

- **The request is now sent again when the failure is worth it.**  The
  new module `components/llm_retry.py` tells the two kinds of failure
  apart:

  | The failure | Sent again? |
  |---|---|
  | 500, 502, 503, 504, 429, 408 | yes — the server, not the request |
  | a connection that never came about | yes |
  | a server that did not answer in time | yes |
  | 400, 401, 403, 404 | no — it will fail the same way |
  | an error in the body of the response | no — the server said why |

  `RetryingOllama` is the LLM of the agent with that rule.  It wraps
  `astream_chat` and `achat`, and sends the request again when the
  failure passes.

- **The retry is around the request, not around the run.**  The tools
  that already ran are not run again, the conversation is not lost, and
  the answer of the attempt that works is the answer of the request.

- **The retry is bounded, and it is a setting.**  `llm.max_retries`
  (2 by default) and `llm.retry_delay` (2 seconds by default) are in the
  configuration file, with the environment variables
  `TORVALDS_MAX_RETRIES` and `TORVALDS_RETRY_DELAY`.  The wait grows
  with every attempt — 2 seconds and then 4 seconds with the default,
  which is three attempts in all.  `max_retries = 0` turns the retry
  off.

- **The failure of a retried request is written to the log as a
  warning**, so the operator sees that the server stumbled and that the
  agent carried on.

- **The evidence is in `investigate/llm-server-500/`.**  The probe
  (`probe_server_500.py`) is read-only and prints what the log holds
  after one failed request, whether the request is worth sending again,
  and how many times it is sent.  Before the change: one request, no
  answer.  After: two requests, an answer.

#### The export of a session, as JSON

- **The operator asked for a JSON export on 2026-11-08:**

  > *"can we export chat history as json?"*

  The text export is for a person to read.  A program that has to read
  the same session was left with a transcript and a problem: the role,
  the text, the thinking and the tool calls were all inside one line,
  separated by `|` and `:`.

- **`\chat-export --json` writes the same export as a JSON document.**

  ```
  \chat-export --json                 the JSON of the session, on stdout
  \chat-export --json <path>          the JSON of the session, in a file
  \chat-export --json --buffer        the JSON of the buffer
  ```

  It is not the text with brackets around it.  The role, the content, the
  thinking and the tool calls are **fields**:

  ```json
  {
    "session": {
      "id": "sess-1",
      "name": "General Chat",
      "type": "general",
      "created_at": "2026-11-08T14:00:00",
      "updated_at": "2026-11-08T14:42:12"
    },
    "source": "stored",
    "message_count": 2,
    "size_bytes": 27,
    "tokens": 4,
    "tokens_estimated": false,
    "messages": [
      {
        "role": "user",
        "content": "first message",
        "thinking": null,
        "tool_calls": [],
        "metadata": {}
      }
    ]
  }
  ```

- **The document says the same things the text says.**  The session, the
  source, the count, the size and the tokens are all there — a consumer
  of the JSON learns what a reader of the text learns.  The size and the
  tokens are the ones of the **exported** messages, and `tokens_estimated`
  says whether the tokenizer was there to count them.

- **The source and the format are independent.**  `--buffer` chooses
  which half of the session is exported, `--json` chooses how it is
  written, and the two can be combined: `--buffer --json` is the buffer
  in JSON.  Each group takes one option, and two options of the same
  group are reported with the usage line.

- **The characters of the session survive.**  The JSON is written with
  `ensure_ascii=False`, so the text of a session is the text of a
  session — in Cyrillic, in Japanese, in emoji — and not a wall of
  `\uXXXX`.  The file is UTF-8, like the text export.

- **The tests** are in `chat_manager/tests/test_export.py` — the
  document, the fields of a message, the thinking, the tool calls, the
  characters, and the dispatch of the two groups of options.

  ```
  $ .venv/bin/python -m pytest chat_manager/tests/test_export.py -q
  65 passed
  ```

#### The content of a session, printed or written to a file

- **The operator had no way to keep a copy of a session.**  The request
  asked for it on 2026-11-08:

  > *"I want to have a command under 'chat' section to be able to print
  > current session content into stdout or file"*

  `\chat-info` told the operator how big the session was — how many
  messages, how many bytes, how many tokens — and not one word of *what*
  was in it.  A session that cannot be read cannot be kept, cannot be
  pasted into a bug report, and cannot be read by the person who was not
  there when it was made.

- **`\chat-export` prints the session, or writes it to a file.**

  ```
  \chat-export                 the content of the active session, on stdout
  \chat-export <path>          the content of the active session, in a file
  ```

  One command, one optional argument.  There is no format flag: the text
  is the text — the same rendering the log uses
  (`components/chat_message.to_string`), so a session reads the same
  everywhere it is shown.  A header names the session and carries its
  size, because an export that does not say where it came from is a
  mystery file.

- **The export can carry either half of the session, and the operator
  says which.**

  ```
  \chat-export                      the stored history — every message
  \chat-export --buffer             the buffered tail — what the model sees
  \chat-export --store              the stored history, said out loud
  \chat-export --buffer <path>      the buffered tail, in a file
  ```

  Two things are called "the session": the messages the session keeps —
  they grow with every turn and are never trimmed — and the tail of them
  that reaches the model.  The stored history is the default, because an
  export that silently dropped the older half of a conversation would be
  a trap.  The buffer is the other half, and it is worth having on its
  own: it is what the model was shown, and it is what a report about a
  runaway context needs to quote.

  The header of the export names the source — `Source: stored` or
  `Source: buffer` — so a file is never a mystery, and the size and the
  tokens in it are the ones of the **exported** messages, not of the
  session behind them.

- **The file is written as UTF-8 and overwritten** — an export is a copy
  of a session, not a log to append to.  `~` is expanded, a relative path
  is taken from the working directory of the agent, and a directory that
  does not exist is **not** created: the command says which directory is
  missing, and the operator decides.

- **The content of a session is arbitrary text, and Rich ate it.**  The
  result of a chat command was printed with markup:

  ```
  console.print(f"[cyan]{chat_response}[/cyan]")
  ```

  and the content of a session is what the operator typed and what the
  model answered.  Rich reads square brackets as markup, and the effect
  was never cosmetic:

  ```
  '[dim]text[/dim]'  ->  'text'           the text is eaten
  'a [b] c'          ->  'a  c'           the text is eaten
  '[/nope] broken'   ->  MarkupError      the REPL dies
  ```

  So the chat commands are printed **verbatim** now
  (`components/console_output.print_verbatim`): the markup is not
  interpreted, the text is not highlighted and it is not wrapped.  The
  colour is kept — the chat commands stay cyan.

- **The tests** are `chat_manager/tests/test_export.py` — the renderer,
  the command, the dispatch, and the export against the manager the agent
  really runs — and `tests/test_console_output.py`, where the closing tag
  that used to raise is a test now.

  ```
  $ .venv/bin/python -m pytest chat_manager/tests/test_export.py tests/test_console_output.py -q
  33 passed
  ```

- **The design** is in `investigate/chat-export/PROPOSAL.md`, and it says
  what is **not** in this change: no format flag, no export of another
  session, no new setting, and no change to the history itself.

- **The options are parsed by hand, and the path is kept verbatim.**  The
  options come first, and what is left is the path — so a path with a
  space in it survives.  An unknown option, the same option twice, and
  two sources at once are all reported with the usage line, not guessed
  at.

#### The agent loads skills on demand — and the prompt does not pay for them

- **The Agent Skills feature was measured before it was built, and the
  measurement changed the design.**  The obvious way to build it is
  *progressive disclosure*: the prompt carries a catalog of the names and
  the descriptions of the skills, the model asks for the body of the one
  it needs, and the body is loaded at that moment.

  On the window of the operator's model (8192 tokens) that catalog is not
  cheap:

  ```
  catalog of 20 skills          : 908 tokens   (45 tokens per skill)
  activation tool schema        : 175 tokens   (the names, as an enum)
  the fixed cost of the feature : 1083 tokens  16.5% of the prompt budget
  left for the conversation     : 2260 tokens  (it was 3343)
  ```

  **That cost is paid on every request**, whether the run touches a skill
  or not, and it grows by 45 tokens for every skill the operator writes.
  A third of the room the conversation had left was gone for a feature
  that most requests never use.

- **The catalog is fetched on demand instead.**  The prompt carries **one
  line** — and only when there is at least one skill — the activation
  tool takes a **free string** rather than an enum of the names, and the
  catalog comes back as a *tool result* when the model calls
  `list_skills`.

  The fixed cost of the feature is therefore **220 tokens, whatever the
  number of skills** (3.4% of the budget), and the conversation gets 3123
  tokens instead of 2260.  The measurement is in
  `investigate/agent-skills/`, and the probe that produces it is
  read-only: `investigate/agent-skills/probe_skill_costs.py`.

- **A tool result is the right place for the catalog.**  It costs the
  runs that ask for it, and it lands in the conversation, where the
  context guard drops it once it grows old — the guard already knows
  how to drop the oldest turns.

- **The body of a skill is cut to a token limit** (`skills.body_token_limit`,
  2000 by default), and the cut is marked, so that the model knows it is
  reading a part of the procedure and not all of it.

  The limit applies to the **result**, the marker included: the count of
  the result is not the sum of the counts of its parts — the seam between
  the body and the marker may merge two tokens into one.  This is the
  lesson of the context guard, applied to the skills.

- **A skill is a directory with a `SKILL.md` in it** — a frontmatter block
  (`name`, `description`) and the procedure in the body.  They live in
  `~/.config/torvalds/skills` (the skills of the operator) and in
  `<project>/skills` (the skills of the project); the skill of the
  project overrides the skill of the operator with the same name.

- **The feature costs nothing when it is not used.**  A machine without a
  skill gets **no tools at all** and nothing in the prompt.

- **The catalog can be put in the prompt after all** — with
  `skills.catalog_in_prompt = true`, in the compact form (one line per
  skill, 26 tokens per skill instead of the 45 of the XML shape).  It is
  off by default, because it is paid by every request.

- **The new settings** are `skills.enabled`, `skills.dirs`,
  `skills.catalog_in_prompt` and `skills.body_token_limit`, each with its
  environment variable (`TORVALDS_SKILLS_*`).

- **The tests guard the invariant** the whole change is about: the fixed
  cost of the feature is the same for one skill and for fifty.  A test
  that measures the rejected design sits next to it — a check that has
  never failed proves nothing.

  ```
  $ .venv/bin/python -m pytest tests/test_skills.py -q
  40 passed
  ```

- **The documentation** is `docs/skills.md` — how to write a skill, and
  what the settings do.

#### The size of the prompt is in the log

- **The operator could not see how big the context was.**  The request asked
  for it on 2026-11-04:

  > *"I need to see in the log the context size in tokens and size of
  > bytes.  So when request is made to LLM I want to see current context
  > size"*

  The agent sent the prompt to the model and said nothing about it.  A
  prompt that grows silently is a prompt that one day does not fit — and
  the overflow is reported by the model server, in its own words, long
  after the moment it could still be prevented.

  Every request to the model is now preceded by one line:

  ```
  Context: 12 messages, 1,200 tokens, 4.5 KB, 14.6% of the 8,192-token window
  ```

  The line carries the number of messages, the number of tokens, the size
  in bytes, and the share of the context window the prompt takes.

- **What is measured is what goes on the wire.**  The prompt is the chat
  memory plus the scratchpad of the run — the system prompt, the history
  of the session, the request of the user, and the turns the run produced
  (the assistant turns that asked for a tool, and the tool results that
  answered them).  The base class assembles it exactly that way, so the
  number in the log describes the request that follows it.

- **The tokens are counted with the tokenizer the chat memory itself
  uses**, so the number is the number the token limit is enforced with.
  The bytes are the UTF-8 bytes of the text of the prompt.

- **The tool schemas are counted separately.**  They travel with every
  request and they take up room in the context window, but they are not
  chat messages — folding them into the message count would hide where
  the prompt actually goes.

- **The line is written whether the context guard trimmed the prompt or
  not.**  The guard is opt-in (`--context-guard-on`), and the operator has
  to see the context grow *before* the guard is needed — that is what
  tells them when to turn it on.

- **The measurement never takes the agent down.**  A tokenizer that cannot
  be loaded degrades into an estimate (four characters per token), and the
  line says that the tokens are estimated; the bytes are always exact.
  The context window is read from the LLM directly, so the line never
  costs a round-trip to the model server.

- **The logging can be turned off**: `--no-context-log`, the setting
  `logging.context_size` in the configuration file, or the environment
  variable `TORVALDS_LOG_CONTEXT_SIZE`.

#### The configuration is changed from the menu

- **`\config <setting> <value>` writes into the configuration file.**
  The command showed the configuration; now it changes it.

  The file is **edited**, not rewritten: the comments of the operator,
  the order of the settings and everything that is not the setting stay
  exactly as they were.  A setting that is not in the file yet is added
  to its section, and a setting that is **commented out** — where the
  template leaves every one of them — is uncommented and written into.

  The value is coerced exactly as a value that was **read** is coerced,
  so the file can never carry a value the agent would refuse.  The write
  is **atomic** — the file is written beside the old one and moved over
  it — and it stays `0600`.

  `\config <setting>` shows one setting in detail: its value, where it
  came from, its default and how to change it.

  The file is read **once**, when the agent starts: the settings that
  were resolved at the start of the session apply on the **next start**.

#### `\chat-info` shows what the session holds

- **`\chat-info` described the session but never measured it.**  The
  command named the session — its name, its type, its key, when it was
  created — and said nothing about what was *in* it.  The operator had
  no way to see how much of the conversation the agent keeps, and how
  much of it the model actually receives.

  Three lines were added:

  ```
  Messages: 84
  Size:     61.3 KB
  Tokens:   ≈15,404 stored, ≈4,980 in the buffer (limit 5,000)
  ```

  The size is the size of the text of the messages — in bytes below a
  kilobyte, in kilobytes below a megabyte, in megabytes above that.

  The two token counts are not the same number, and the difference is
  the point.  The **stored** history grows with every turn — the agent
  never trims it — while the **buffer** keeps only the tail that fits
  into the `chat_token_limit` of the user.  A session can hold 15,404
  tokens and still send 4,980 of them to the model, and the operator
  could not see that before.

  The tokens are counted with the tokenizer the memory buffer itself
  uses, so the numbers are the numbers the limit is enforced with.  That
  tokenizer counts the tokens of one model family; for the local models
  the agent usually talks to it is an estimate — the `≈` says so.  When
  no tokenizer can be loaded at all, the count falls back to an estimate
  of four characters per token, and the line says that it is estimated.

  The multi-window console shows the same three lines, as rows of the
  same table: both views are formatted by the same helpers, so they
  cannot drift apart.  A session that cannot be measured is still
  described — the measurement is never worth losing the session over.

#### The project carries skills of its own

- **A feature that ships with nothing to load is a feature that cannot be
  tried out.**  The skills of this project now live in `skills/`, next to
  the code they describe:

  | skill | what it is for |
  |---|---|
  | `run-tests` | how to run the suite, and how to read a run that ends in "39 failed" |
  | `release` | the release checklist, and the two files that declare the version |
  | `investigate` | the shape of an investigation folder, and the rule that the probe is read-only |
  | `add-toolkit` | the layout of a toolkit, and the four steps nobody skips |

  They are found by the second default root, so they are loaded whenever the
  agent works in this repository.

- **Each of them carries a fact that is easy to get wrong.**  The suite of
  this project does not pass — it carries 40 known failures — and a run that
  ends in "39 failed" is the normal state of the repository, not a
  regression.  The version of a release is *read* from two declarations
  (`deploy/deploy-torvalds.sh` and `project_manager/__init__.py`), not
  chosen.  The tests of a new toolkit are invisible to the CI gate until
  their directory is added to `testpaths` in `pytest.ini`.  A probe that
  changes something cannot be run twice.

- **The skills are guarded by a test.**  The feature skips a skill that
  cannot be read, and a skill without a name is skipped too — the right
  behaviour for a skill the operator writes on the machine, but it makes a
  broken skill in the **repository** invisible: nothing fails, nothing
  warns, and the procedure is simply never loaded.

  `tests/test_project_skills.py` is the eyes for that case.  It checks that
  every skill is found, that each one has a name and a description, that the
  description says *when* the skill is worth loading, that the body fits
  into the limit the feature cuts it to, and that no skill carries the path
  of a home directory.

#### The process of a change is a skill of its own

- **The project carried the *parts* of the work, and not the *work*.**
  `run-tests`, `release`, `investigate` and `add-toolkit` are procedures
  that each cover one part of a change — and nothing carried the order
  those parts happen in, the branch they happen on, or the approvals that
  stand between them.  The agent knew *how* to run the gate and not
  *when*, and the rules that govern a change — the approval, the
  destructive operations, the privacy of the operator — lived in
  `DEVELOPMENT_RULES.md`, which is read by hand.

- **`develop` is that procedure.**  It is the order of a change, from the
  request to the pull request:

  | step | what it holds |
  |---|---|
  | 1 | the contract — `DEVELOPMENT_RULES.md` is read first |
  | 2 | understand before changing — `investigate`, and its read-only probe |
  | 3 | the branch — `feature/<name>`, off `master` |
  | 4 | the smallest change that answers the request, with a test that fails without it |
  | 5 | the gate — `new failures` must be `0` |
  | 6 | the changelog — what changed, and why |
  | 7 | the documentation — the docs follow the code |
  | 8 | the diff, and the approval for the commit |
  | 9 | the push, the private-path check, and the pull request |

- **It repeats nothing.**  The procedures stay in the skills that carry
  them; `develop` names them and puts them in order.  A skill that copies
  a procedure is a skill that drifts from it.

- **The rules are in it, and not only in the file.**  The approval per
  action, the confirmation of a destructive operation, the privacy of the
  home folder of the operator and the timeout contract are named at the
  step where they apply — a rule that is read at the moment it is needed
  is a rule that is followed.

- **The tests guard it.**  `tests/test_project_skills.py` checks that the
  description says *when* the skill is worth loading, that the body fits
  into the limit the feature cuts it to, and that no skill carries the
  path of a home directory.  The body of `develop` takes **926 tokens**,
  and the catalog of the five skills takes **209**.

### Changed

#### The develop skill is software development — the "self development" is gone

- **The statements that framed the work as the agent developing *itself*
  are removed.**  `DEVELOPMENT_RULES.md` announced that the
  *self-development clone* was gone, `README.md` called the rules "how
  the agent modifies its own code", `wiki/Contributing.md` called the
  workflow "the agent's own development workflow", and `.gitignore`
  carried the entry of the retired clone.  The workflow they described is
  retired, and the words outlived it — they described a workflow that
  does not exist, and they described the develop skill as something other
  than what it is.

- **The develop skill is the procedure for any software development.**
  Its description said "carry a change through *this project*"; it now
  says "carry a change through *a software project*".  The body says which
  of the names belong to this repository — `DEVELOPMENT_RULES.md`,
  `scripts/ci_test_gate.py`, `investigate/<topic>/` — and which are the
  steps of every project: read the contract, understand the thing before
  changing it, branch, implement the smallest change, pass the gate,
  write the changelog, write the documentation, show the diff and ask,
  push and open the pull request.

- **The rules read as the rules of a change.**  `DEVELOPMENT_RULES.md`
  governs "how a change to this codebase is made — by the operator, or by
  the agent working in it", rule 1 is "the work happens in the working
  copy", and the note at the top carries the date of the rewrite instead
  of the history of the clone.

#### The tokenizer of the agent lives in one place now

- **The tokenizer is one thing, and it was reached in four ways.**  The
  context guard had the canonical one; the skills had a wrapper around
  it; the agent had a cached one that remembered its failure; the chat
  history had one that loaded it straight from LlamaIndex — and the
  "four characters per token" estimate was written out in three of those
  places.  Two copies of one rule are two rules that can drift apart.

  `components/tokens.py` holds them now, as free functions:

  ```
  load_tokenizer()    the tokenizer of the agent; it raises
  get_tokenizer()     the same tokenizer, but None instead of an exception
  estimate_tokens()   the estimate: four characters per token
  count_tokens_of()   the count of a text, with the estimate as the fallback
  ```

- **The numbers did not move.**  It is the same tokenizer — the one the
  chat memory uses, so the accounting is the one the chat-token limit is
  enforced with — and the same estimate.  The measurement of the skills
  feature still reads 908 tokens for a catalog of twenty skills and 16.5%
  of the prompt budget, and the report of the context loop still reads
  3211 tokens of tool schemas.

- **A tokenizer that cannot be loaded is still not worth losing a run
  over.**  The callers that can live without one ask for the safe
  `get_tokenizer()` and measure with the estimate; the callers that
  cannot — the context guard, which has to fit the prompt to the window
  of the model — ask for the raw `load_tokenizer()` and are told when it
  is not there.

### Fixed

#### The agent answered nothing at all, and the run ended on a turn that said nothing

- **The operator reported it on 2026-11-13.**  Three requests went in.
  The first one worked for three minutes — twenty-three model calls,
  thirty-six tool calls, a project scaffolded on disk — and the agent
  answered **nothing**.  The second request answered **nothing** as
  well.  The third one answered with a promise: *"Let me complete the
  implementation first, then update the README to document it
  accurately."* — and did nothing either.

- **The answer was dropped twice on the way to the screen.**  The console
  path built the answer with `str(result)`, and `AgentOutput.__str__`
  returns the **text** of the answer and nothing else — the `thinking`
  block of the model was dropped there.  An answer that carried nothing
  but a thinking therefore became an empty string, and
  `console.print(Markdown(""))` prints **nothing at all**: not an error,
  not a warning, not a note.

- **The answer the operator reads is rendered now.**
  `to_answer_string()` in `components/chat_message.py` returns the text
  of the model, and when there is none it says so and shows the thinking
  of the model under it — the operator sees what the model was about to
  do instead of nothing at all.  The function **never returns an empty
  string**: an answer that cannot be rendered is still an answer, and
  the operator is told that the model ended the turn without one.

  ```python
  from components.chat_message import NO_ANSWER, to_answer_string

  answer = to_answer_string(result)
  ```

- **A turn that says nothing does not end the run.**  The agent ended the
  workflow on the first turn without a tool call, whatever the model said
  in it — including a sentence that promises work instead of doing it.
  A turn with neither text nor a tool call now gets **one more turn**:
  the empty turn of the model stays in the scratchpad, a note that says
  what went wrong follows it, and the model can see what it did.  A model
  that says nothing a second time ends the run — and the answer says
  plainly that the model ended the turn without an answer.  One turn, not
  two: every empty turn costs a full round-trip.

- **The window the agent sent was fiction.**  When neither `/api/ps` nor
  the Modelfile answered, the agent asked the server for the
  **advertised maximum** of the model — a million tokens.  The server
  clamps the request to what the hardware allows, and the model stops
  fitting on the GPU: 3.09 GB of VRAM instead of 6.64 GB, measured.  The
  advertised maximum is the **capacity** of the model, not the window of
  the server, and it is not sent any more — the configured window is used
  when there is one, and the log says that the window is unknown when
  there is none.  The window that is sent is sized to the prompt that is
  about to go out, with room above it for the answer, and it is **never
  lowered**: a window that changes in both directions makes the server
  give the cache back and take it again with every request.

- **The tests are in `tests/test_silent_turn.py` and
  `tests/test_ollama_context_window.py`.**  They pin the silent turn,
  the answer that is never empty, the console that prints a line instead
  of an empty box, and the window that is not the advertised maximum.
  The gate of the repository stays green: 40 known failures, 0 new,
  0 fixed.

  ```bash
  .venv/bin/pytest tests/test_silent_turn.py tests/test_ollama_context_window.py -v
  ```

- **The whole story is in `investigate/agent-empty-answer/`.**  The
  investigation is in `INVESTIGATION_REPORT.md`, the change is in
  `IMPLEMENTATION_REPORT.md`, and the probes that measured the silence
  are next to them.

#### The memory buffer of the agent trimmed the history in quadratic time

- **The finding came out of the work on the session picker (2026-11-13).**
  The picker was slow because the **count of the messages in the header**
  was slow, and the count was slow because of the memory buffer of
  LlamaIndex:

  ```python
  # llama_index/core/memory/chat_memory_buffer.py
  while token_count > self.token_limit and message_count > 1:
      message_count -= 1
      ...
      cur_messages = chat_history[-message_count:]
      token_count = self._token_count_for_messages(cur_messages)   # again
  ```

  Every step of the loop counts the tokens of the **whole window
  again**.  The work is quadratic, and the agent pays it on **every
  turn**: the buffer is asked for its messages every time a request is
  built.  The history of the heaviest session of the operator is 15 MB
  — 6204 messages — and the trimming of it takes **forty seconds**.

- **The buffer of the project trims in one pass.**
  `chat_manager.memory.TrimmingChatMemoryBuffer` is the buffer of
  LlamaIndex with a `get()` that walks the tail of the history **once**
  and stops at the limit: the messages are counted one by one, from the
  end, and only the tail is ever counted.

  | | the buffer of LlamaIndex | the buffer of the project |
  |---|---|---|
  | 6204 messages (15 MB) | **39.467 s** | **0.009 s** |

- **The answer is the answer of the library.**  The same messages, in
  the same order — including the rule that a window may not open with
  an assistant or a tool message, and the rule that a message longer
  than the limit is kept on its own.  The tests compare the two, message
  by message, for a dozen histories, for the roles, and for a hundred
  random ones.

  ```python
  # chat_manager/tests/test_memory.py
  .venv/bin/python -m pytest chat_manager/tests/test_memory.py -v
  ```

- **What is left of a turn** is the reading of the whole history from
  the database — 15 MB for the heaviest session.  That is the design of
  the message store of LlamaIndex: the history of a session is one row,
  and the buffer asks for it on every turn.

#### The choice of the chat session froze the TUI, and the digit arrived too late

- **The operator reported it on 2026-11-13:**

  > *ok here is issue with chat session selection, by typing numeber and press
  > enter the agent hangs about a aouple of second and the digit after session
  > is loaded*

  > *we have an issue with chat session selection, first of all it takes a couple
  > of seonds to load session, the agent hangs for this time can we run it in
  > background as background job*

- **The answer was applied in the loop that paints the layout.**  The
  terminal is in cbreak mode — the echo of the terminal is off and the
  TUI draws what the operator types.  A character that is typed is put
  into the buffer of the state and painted by the **next frame**.  The
  work of the answer was done in that same loop, so there was no next
  frame until the work was done: the digit the operator typed showed up
  together with the confirmation, and it looked as if the answer had
  come *after* the session was loaded.

- **The answer is taken at once, and the work is a job.**  The answer
  leaves the command bar the moment the operator presses Enter, and the
  pane says what is being done:

  ```
  ╭─ 📄 Markdown Document Viewer ─────────────────────────────╮
  │                    💬 Select a Chat Session                │
  │                                                             │
  │  **Answer:** `2`                                            │
  │                                                             │
  │  ⏳ Loading the session…                                    │
  ╰─────────────────────────────────────────────────────────────╯
  ```

  The database and the tokenizer are touched in a **thread**
  (`asyncio.to_thread`), so the event loop keeps painting while they
  work.  The rules of the answer are not touched: the number, the
  `new <name>` and the empty answer mean what they meant before — see
  `chat_manager/session_selector.py`, which both front-ends share.

- **The seconds came from the count of the messages in the header.**
  The switch of the session takes **16 ms**; the count took **40
  seconds**.  The memory buffer of LlamaIndex answers that question
  with a loop that counts the tokens of the **whole window again on
  every step** — the work is quadratic, and the history of the heaviest
  session is 15 MB:

  ```python
  # llama_index/core/memory/chat_memory_buffer.py
  while token_count > self.token_limit and message_count > 1:
      message_count -= 1
      cur_messages = chat_history[-message_count:]
      token_count = self._token_count_for_messages(cur_messages)   # again
  ```

  `chat_manager.stats.count_messages_within_limit()` answers the same
  question by walking the history **once**, from the end, and stopping
  at the limit.  The answer is the answer of the buffer — the tests
  compare the two, message by message, for a dozen histories.

  | | the buffer of LlamaIndex | the count of the project |
  |---|---|---|
  | 6204 messages (15 MB) | **40.379 s** | **0.568 s** |

- **The measurements, with the probe of the investigation:**

  | | before | after |
  |---|---|---|
  | the Enter key cost the loop | 40 364 ms | **0.0 ms** |
  | the digit is on the screen at once | no | **yes** |
  | the pane named the session after | 40.36 s | **0.06 s** |
  | the count of the header arrived after | 40.26 s | **1.59 s** |
  | the frames painted while it was loaded | 0 | **65** |

  `investigate/tui-session-selection/probe_session_selection_background.py`
  drives the production `TuiApp` against the database of the operator,
  picks the session with the longest history, and restores the session
  that was active before it ran.

- **What the agent sends to the model is not changed.**  The memory
  buffer is the one of LlamaIndex, and the trimming of the history is
  the one of the library.  The fast count feeds the **number in the
  header** — a number for the operator, not a decision.

- **The new tests are in the suite:**
  `tests/test_tui_session_selection.py` (the answer is on the screen at
  once, the loop is not blocked while the job works, a second answer is
  ignored, the chat commands run in the background),
  `chat_manager/tests/test_stats.py` (the count is the answer of the
  memory buffer) and `chat_manager/tests/test_manager.py` (the manager
  counts the messages of the buffer).

#### The TUI loaded the last chat session and never asked which one

- **The operator reported it on 2026-11-13:**

  > *by running TUI agent I cannot chose chat from DB the agent does not
  > propose select one it just loads the last one*

- **The TUI skipped the menu, and nobody missed it.**  The multi-window
  orchestrator asked the operator which session to work in with one
  condition:

  ```python
  # agent-torvalds-mw.py
  if not args.no_session_select and not use_tui:
  ```

  `not use_tui` switched the whole block off.  The agent restored the
  session that was active at the end of the last run and started
  working in it — with **27 sessions** in the database and no way to
  pick one.  The classic orchestrator has no such condition, and it
  asks.

- **The TUI asks now — inside its own layout.**  The picker of the
  sessions is in the document pane, and **the agent waits for the
  answer**:

  ```
  ╭─ 📄 Markdown Document Viewer ─────────────────────────────╮
  │                    💬 Select a Chat Session                │
  │                                                             │
  │  Sessions: 27  •  the active one is marked ★               │
  │                                                             │
  │  How to select:                                             │
  │                                                             │
  │   • Type the number of the session and press Enter.         │
  │   • Press Enter alone to keep the session that is active now.│
  │   • \chat-select <session_id> also works — the id is in     │
  │     \chat-sessions.                                         │
  │                                                             │
  │    #  Session                      Type     Created         │
  │    1  objective-control-001        custom   2026-11-09 10:40 │
  │    2  agent-torvald-ollama-intern…  custom   2026-11-09 08:03 │
  │    4  ★ agent-torvald-project-002  custom   2026-11-08 12:15 │
  │    ...                                                        │
  ╰─────────────────────────────────────────────────────────────╯
  ```

  A question typed before the choice would run in the session that was
  active last — the defect the picker came to close.  So the agent is
  held idle until the operator has answered.

  The classic console asks the same question **in the terminal**,
  before the REPL starts, exactly as it always did.  The two
  front-ends share the rules and the numbering:
  `chat_manager.session_selector.apply_session_answer`.

- **Inside the TUI, a session was chosen by a 36-character id.**
  `\chat-select` took a session id, and the id had to be read off
  `\chat-sessions` — a table whose rows are wider than the document
  pane, so the id was folded in the middle and had to be copied by
  hand.

  | | before | after |
  |---|---|---|
  | choose a session in the TUI | `\chat-select <36-char-uuid>` | `\chat-select 4` |
  | see the sessions | the table with the ids | `\chat-select` — a numbered picker |
  | the numbering | — | the number of the session in the list — the same number in the startup menu, in `\chat-sessions` and in the picker |

  The picker leaves the id out on purpose.  A row of `\chat-sessions` is
  121 characters long in a document pane that is 74 characters wide,
  and the id in the middle of it is exactly what has to be copied by
  hand.  A *name* may still wrap — that is a name, and it stays
  readable.

- **The measurements, with the probe of the investigation:**

  | | before | after |
  |---|---|---|
  | the TUI asks the operator | **no** | **yes** |
  | the answer switches the session | — | **yes** |
  | the classic console asks the operator | yes | yes |
  | the answer switches the session | yes | yes |

  `investigate/tui-session-selection/probe_session_selection.py` runs
  the real `agent-torvalds-mw.py` and the real `agent-torvalds.py` on
  a pty of their own, waits for the question to appear on the screen,
  answers it with the number of a session, and looks for the outcome in
  the byte stream the operator receives.

- **The new tests are in the suite: `tests/test_tui_session_selection.py`**
  (32).  Among them the one that matters most: the buffer of the agent
  is rebuilt for the session that was picked, and it is bound to the
  `chat_key` of that session.

  ```bash
  .venv/bin/python scripts/ci_test_gate.py

  known failures in the baseline : 40
  failures in this run            : 40
  new failures                    : 0
  fixed since the baseline        : 0
  ```

  The 40 are the known state of the repository, not a regression.

#### The selection picked up the wrong pane, and the screen blinked

- **The operator reported it on 2026-11-13:**

  > *Please check the copied text from as you can see it is not posible to
  > select test from main window only, it also selects content from
  > "Workflow & Tools Progress" window.*

  and, separately:

  > *I have notised that the an entire screen is blinking diring processing
  > request*

- **Rich believes the terminal is a different size than it is.**  Rich
  reads `COLUMNS` and `LINES` from the environment *before* it asks the
  terminal, and the shell exports them as a snapshot of the size the
  terminal had when the shell started:

  ```python
  # rich/console.py - Console.size
          columns = self._environ.get("COLUMNS")
          if columns is not None and columns.isdigit():
              width = int(columns)          # ← the environment wins
          lines = self._environ.get("LINES")
          if lines is not None and lines.isdigit():
              height = int(lines)            # ← the environment wins
  ```

  The TUI therefore laid itself out for a terminal that is not there.
  The frame was wider than the screen, the terminal folded it, the panes
  left their columns — and the screen scrolled 26 rows on every one of
  the 15 frames a second.  A selection is made by *column*, so the
  border of the progress pane was standing in the answer of the agent,
  and the operator copied both.

- **The console of the TUI asks the terminal now.**
  `components/tui/terminal_size.py` builds the console with an
  environment that carries no `COLUMNS` and no `LINES`, so
  `Console.size` falls through to `os.get_terminal_size()` — the size
  that is true *now*, and that follows a resize.

- **The log of the agent landed on the alternate screen.**  The handler
  of the root logger writes to `stderr`, and the agent logs on every
  iteration of its loop (`components/hitl_agent.py`, `logger.info("Context:
  %s", ...)`).  With `Live(screen=True, redirect_stderr=False)` that
  line was written straight onto the layout and scrolled it — the part
  of the blink that showed exactly while a request ran.

  The operator decided: *"the log must go into file, not painted
  over"*.  `components/tui/log_routing.py` takes the terminal handlers
  of the root logger away for the time of the TUI, and a file handler
  takes their place: the file the operator configured
  (`--log-file`), or the default of the project
  (`~/.torvalds/logs/agent.log`).  It rotates, and it is private
  (`0600`) — the log carries the prompts, the tool output and the
  answers of the model.

  | terminal 120×40, 2.5 s of the TUI | before | after |
  |---|---|---|
  | the size Rich believes | 229×33 | **120×40** |
  | the frame overflows the terminal | yes | **no** |
  | screen scrolls | **988** | **0** |
  | the pane separator on the screen | column 27 | **column 77** |
  | rows with the panes misplaced | **14** | **0** |
  | the log of the agent on the screen | 6 lines | **0 lines** |
  | the log of the agent in the file | — | **6 lines** |

- **The probe never touches the terminal of the operator.**
  `investigate/tui-selection-and-flicker/probe_selection_and_flicker.py`
  runs the TUI four times in a pty of its own and replays the byte
  stream through a terminal emulator
  (`investigate/tui-selection-and-flicker/repro/term_emulator.py`).
  The investigation is in
  `investigate/tui-selection-and-flicker/investigation_tui_selection_and_flicker.md`.

#### The question of the agent never reached the operator in the TUI

- **Since 2026-10-25, every question in the multi-window TUI raised an
  `AttributeError` before it could wait for an answer.**  The commit
  `dca06b9` ("make a list of choices a menu, and teach the TUI the
  answer type") taught the *adapter* of the TUI the kind of answer the
  pending question wants:

  ```python
  class TuiEventAdapter:
      def __init__(self, state: TuiState):
          self.state = state
          self._input_type = "text"

      def set_input_type(self, input_type: str) -> None:
          ...
  ```

  and changed the **input module** to read that attribute:

  ```python
  class TuiInputModule:
      def __init__(self, state: TuiState):
          self.state = state          # ← no _input_type here

      async def prompt_with_status(self, ...):
          ...
          self.state.hitl_input_type = self._input_type   # ← AttributeError
  ```

  The module never defined it, and the consumer only calls
  `set_input_type()` when the module has one — so the attribute was
  never set, and the question died on the way to the operator.

- **What the operator saw was nothing at all.**  The question is
  rendered into the *silent* console of the TUI, and the footer — the
  only place the operator can see it — is filled by the module that
  crashed.  The exception was caught by `EventConsumer.ask_question`,
  which then answered the agent with the **default answer** and
  reported it as a timeout.  The agent carried on as if nobody had been
  asked anything, which is exactly what "the agent never asks me
  anything" and "what I type is invisible" describe.

- **The fix is the two lines the module was missing.**  The module knows
  the kind of answer now, and it can be told:

  ```python
  class TuiInputModule:
      def __init__(self, state: TuiState):
          self.state = state
          self._input_type = "text"

      def set_input_type(self, input_type: str) -> None:
          """Tell the module what kind of answer the pending question wants."""
          if input_type:
              self._input_type = input_type
  ```

  The footer labels the prompt by the kind of answer again — "Answer:",
  "Yes/No:", "Option:" or "Password:" — and the question reaches the
  operator.

- **The proof is `tests/test_tui_input_module.py`** — six tests, and
  every one of them fails without the fix:

  | | Without the fix | With the fix |
  |---|---|---|
  | `tests/test_tui_input_module.py` | **6 failed** | **6 passed** |
  | the manual test (`scripts/manual_hitl_privilege_test.py`) | the question never arrives | the answer arrives, and the typed text is on the screen |
  | the CI gate | — | no new failure — the same 40 known failures |

  The gate is the run that decides — `.venv/bin/python
  scripts/ci_test_gate.py` — and it counts the failures of the whole
  repository, `tests/` and `toolkits/` alike:

  ```
  known failures in the baseline : 40
  failures in this run            : 40
  new failures                    : 0
  fixed since the baseline        : 0
  ```

  **The 40 are the known failures of the repository** — 39 failures and
  1 error, listed one by one in `tests/ci_baseline.txt`.  They sit in
  nine files, and not one of them is in this path: the change breaks
  nothing.

#### The terminal is given back after a privileged command

- **The operator reported that the terminal goes mute after a command
  that asked for the sudo password in a window**, and pointed at
  [pyinvoke/invoke#303](https://github.com/pyinvoke/invoke/issues/303) —
  the same defect in another project: the process that changed the
  terminal settings died in the middle of the question and never gave
  them back.

  The evidence is in `investigate/privilege-terminal-echo/` — the report,
  the proposal and the probe that measures it.

- **The question in a window does not damage the terminal.**  It was
  measured, in a pty of the probe's own: the echo is still on after a
  command that was escalated through `pkexec` and polkit.

- **The paths that ask on the terminal do.**  The `sudo` fallback (when
  there is no polkit agent to ask), the textual agent of `pkexec` (at a
  console, when no window answers), and the whiptail dialog of the APT
  toolkit all switch the **echo off** to read the password.  The agent
  killed the child when the timeout fired — with **SIGKILL**, which
  cannot be caught — and it killed only the shell, not the `sudo`
  behind it.  The terminal kept the echo-off state, and the operator was
  left typing into a terminal that showed nothing.

- **Four changes, and one rule behind them.**

  | The change | What it does |
  |---|---|
  | the terminal is held around every command | the attributes are read before the command and written back in a `finally` — whatever the command did to it, and whether the timeout killed it |
  | the timeout ends the **whole tree** | a SIGTERM first, so a child that can catch it gives the terminal back itself; a SIGKILL after the grace period, for a child that does not care |
  | the question never lands on the terminal | `--disable-internal-agent` is always passed, and the gate refuses to escalate when no window can be shown |
  | the `sudo` fallback is gone | a command that needs root on a machine without a polkit agent is **refused with the reason**, instead of being run as a `sudo` that asks on a terminal the agent cannot give back |

- **The rule is the one of invoke#303:** whoever changes the state of
  the terminal gives it back — and the give-back runs even when the
  process is interrupted.  The two other places in the project that
  switch the terminal off — the masked password of
  `components/console_input_module.py` and the reader of
  `components/tui/input_reader.py` — already keep it that way.

- **The probe proves it.**
  `investigate/privilege-terminal-echo/probe_privilege_terminal.py`
  runs five measurements against the real code of the repository, in a
  pty of its own, so it never touches the terminal of the operator.

  | | Before | After |
  |---|---|---|
  | the probe | exit **1** — *"the terminal was left mute"* | exit **0** — *"the terminal was given back in every measurement"* |
  | the question on the terminal (`sudo -v`) | the echo is **OFF** | the echo is **on** |
  | the mechanism — a child that only switches the echo off | the echo is **OFF** | the echo is **on** |
  | the child after the timeout | the `sudo` behind the shell is **still alive** | the tree is gone |

- **The tests are in `toolkits/linux-toolkit/tests/`** —
  `test_privilege_timeout.py` (the tree that is ended with the command,
  the child that is given the chance to end by itself, and the refusal
  with the reason), `test_privilege_terminal.py` (the question, the
  input, and the terminal) and `test_privilege.py` (the gate and the
  rewrite).  They are offline and hermetic: no test runs `pkexec`, no
  test opens a window, and every check that needs a terminal runs
  against a pty of its own.

  The new tests were run against the code **before** the change, and
  they fail there — *"the grandchild outlived the timeout of the
  command"* — and they pass after it.

- **What is deliberately not in this change:** the whiptail dialog of
  the APT toolkit has the same defect, and it needs the screen as well
  as the echo — another component, another contract, another change.
  The cbreak mode of the TUI is not a defect: the TUI draws the screen
  itself.  A `kill -9` of the agent cannot be answered by any program,
  and the textual agent of polkit is upstream's code — the toolkit's
  job is to stop it from being used, not to repair it.

#### The terminal of the operator was left mute after a command that needed root

- **The operator reported it on 2026-11-10:**

  > *ok I see the same issue with hidden typing, afetr agnet runs pexdec
  > to ask root password I can notice this issue when the termo=inal does
  > not show typed characters*

  The same hidden typing as the report of 2026-11-09, this time after
  the path of the privileged command.

- **The question of a privilege escalation was asked on the terminal of
  the operator — in one of the two modes.**  `pkexec` falls back to its
  own textual agent when no graphical agent answers, and that agent asks
  the password **on the terminal**, through a helper that reads the
  answer from `/dev/tty` with the **echo off** — the helper changes the
  attributes of the terminal, and `libpolkit-agent-1` carries
  `tcsetattr` and `tcgetattr` for exactly that.  The operator typed a
  password into a terminal that showed nothing of it.

  The flag that stops it, `--disable-internal-agent`, was added **only
  when the terminal belonged to an application that draws the screen** —
  a snapshot of the echo, read when the plan was made.  On an ordinary
  console — the classic REPL, a session over SSH — the echo is on, and
  the flag was left out.

  The flag is now **always** passed.  The gate of the feature already
  refuses to escalate when no window can be shown, so the question is
  asked in the window or not at all.

- **The child of an escalated command inherited the terminal.**  It runs
  as another user, and it could read the keystrokes of the operator —
  the input reader of the TUI competes with it for every one of them —
  and it could ask a question the operator cannot answer.  An escalated
  command gets `stdin=subprocess.DEVNULL` now; an ordinary command keeps
  the terminal, as it always did.

- **The terminal was never given back.**  The state of a terminal
  belongs to the terminal, not to the process: a command that took the
  terminal over and was killed by the timeout of the command
  (`subprocess.run` sends `SIGKILL`) left the echo off, and the operator
  typed into a terminal that showed nothing of it — and that state
  outlived the agent.

  The toolkit snapshots the controlling terminal before it runs a
  command and puts it back afterwards, whatever the command did to it.
  The restore has three guards, because the terminal of the operator is
  not always willing: nothing is written when the terminal was not
  changed, `TCSANOW` is used instead of the `TCSADRAIN` that waits for
  the output of a terminal nobody reads, and the restore runs in a
  thread of its own — a terminal that refuses to give its attributes
  back cannot hold the agent.  The block was measured on the terminal of
  the operator: the same script returned in a thousandth of a second on
  one run, and never returned on the next.

- **The measurements are in `investigate/pkexec-hidden-typing/`.**  The
  probe measures the three things that decide it — the flag, the input
  and the terminal — against a pty of its own:

  | | Before | After |
  |---|---|---|
  | the textual agent may ask | **YES** (on an ordinary console) | no |
  | the standard input of an escalated command | the terminal | nothing |
  | the terminal after the command | **mute** | as it was found |

  The ten new tests are in
  `toolkits/linux-toolkit/tests/test_privilege_terminal.py`.  They are
  offline and hermetic: no test runs `pkexec`, no test opens a window,
  and every check that needs a terminal runs against a pty of its own.

- **What was deliberately not in this change, and what became of it:**
  the timeout of a command and the `sudo` that is left alone when no
  window can be shown were both changes of their own, and both landed
  with the change above — *"The terminal is given back after a
  privileged command"*.  The `TCSADRAIN` of the console input module —
  the other password prompt of the project — carries the same wait, and
  it is a change in another component.

#### The operator could not see what they typed while the agent asked a question

- **The line the operator types on was not on the screen.**  The
  operator reported it on 2026-11-09:

  > *after agent response sometime by typint I do not see what is typed
  > looks like it is hidded even after leaving agent app the typing in
  > terminal is hidden*

  The text was in the application the whole time — it was never drawn.
  The footer of the TUI is a partition of the layout with a fixed
  height of three lines: a border, one line of content, a border.  The
  command bar fits in one line of content.  The HITL panel does not —
  it carries the question of the agent *and* the line the answer is
  typed on — and a panel that is taller than its partition is cropped
  from the bottom.  The answer is the last line of the panel, so the
  answer was the first thing to go.

  ```
  --- the footer of the TUI, with a question waiting ---
     │ 🤖 AGENT QUESTION: Which file should I read?                            │
  ```

  The height the panel needs is measured now, and the partition is
  given that many lines while a question is waiting.  The command bar
  keeps the height it has always had — it is one line of content, and
  the hints beside it are as long as they have been.

  ```
     │ 🤖 AGENT QUESTION: Which file should I read?                                                 │
     │ Answer: rm -rf [a-z] now                                                  [Enter to confirm] │
  ```

- **The typed text was read as markup.**  The HITL panel put the typed
  text into the markup of Rich without escaping it, so Rich read the
  square brackets as tags and swallowed the text between them:

  | Typed | On the screen |
  |---|---|
  | `rm -rf [a-z]` | `Answer: rm -rf` |
  | `a[b]c` | `Answer: ac` |

  The command bar — the same text, one branch up — escaped it
  correctly, and so does the HITL panel now.  A bracket that closed a
  tag Rich never opened also took the panel down with a
  `MarkupError`; it does not any more.

- **The terminal was left mute when the agent did not exit on its
  own.**  The reader of the keyboard puts the terminal into cbreak
  mode, and cbreak switches the echo off — the TUI draws the typed
  text itself.  That state belongs to the **terminal**, not to the
  process, so it outlives the agent: a terminal left in cbreak mode
  shows nothing of what is typed, and it stays that way after the
  agent is gone.

  The ordinary exits give the terminal back, and they always have:
  `\exit`, Ctrl-D, Ctrl-C and `kill` all leave the echo on.  What was
  not covered is an exit that no handler runs — an exception outside
  the loop, an exit that skips the cleanup.  The reader registers its
  own `stop()` with `atexit`, so every exit that runs the atexit
  handlers gives the terminal back.

  A `kill -9` still leaves the terminal mute: SIGKILL cannot be
  caught, and no program can answer for it.  `stty sane` gives the
  terminal back.

- **The evidence is in `investigate/tui-hidden-input/`.**  The probe
  (`probe_hidden_input.py`) renders the TUI the way the app does, and
  it checks the terminal against a pty of its own, so it never touches
  the terminal of the operator.  Before the change: *"the operator sees
  it: NO"*.  After: the typed text is on the screen, and the terminal
  is given back.  The fourteen tests are in
  `tests/test_tui_footer.py`.

#### The frames of the agent were written twice, and at the ERROR level

- **One failed request put two copies of the frames in the log, both at
  the ERROR level.**  `components/event_consumer.py` logged the failure
  with `exc_info=True`, and `components/llm_errors.py` logged the same
  failure with `exc_info=exc`.  The frames say where the failure
  happened *inside the agent* — they are of no use to anybody who did
  not write the agent, and they bury the one line that matters, which is
  what the server said.

  The ERROR record keeps the message — *"The request failed: Internal
  Server Error (ref: …) (status code: 500)"* — and the frames are
  written as a second record, under the DEBUG level:

  ```
  ERROR    components.llm_errors   The request failed: Internal Server Error (ref: bc97453e-…) (status code: 500)
  DEBUG    components.llm_errors   The request failed — the frames of the agent:
  Traceback (most recent call last):
    ...
  ```

  The operator asks for the frames with `--log-level DEBUG`.

- **The wording of the failure would have lost its provider.**  The
  retrying LLM lives in a module of its own, and
  `provider_of_the_llm()` looked at the module of the class of the LLM
  alone — the failure would have been described as *"The model server
  failed"* instead of *"The Ollama server failed"*.  The whole line of
  ancestors of the LLM is looked at now, so a subclass of the LLM of a
  provider is still that provider.

#### The cache broke under a value it could not hold, and under a second agent

- **One value that JSON could not hold broke the cache for the rest of
  the session.**  `save_to_cache` takes any value the tool call hands
  it.  Give it one that JSON cannot carry, and the value stayed in the
  cache in memory — so every later write carried it and failed again:

  ```
  save_to_cache("context.custom", object())
    -> "Error saving to cache: Object of type object is not JSON serializable"

  log_error("boom")  -> TypeError: Object of type object is not JSON serializable
  start_session()    -> TypeError: Object of type object is not JSON serializable
  ```

  `log_error` is called from the `except` handler of the model call in
  `agent-torvalds.py` and `agent-torvalds-mw.py`, so a poisoned cache
  turned an ordinary failure of the model into an unhandled exception
  in the error path of the agent.

  The value is now dropped, and reported.  The cache is serialised as a
  *copy*, the copy is what is written, and the copy — without the value
  — is what the cache holds afterwards.  The caller is told what was
  left out, and the later writes go through.

- **Two agents at once crashed on the same temp file.**  The temp file
  had a fixed name — `agent_cache.tmp` — so every writer, in every
  process, wrote to the same one, and one writer's rename left the
  other with nothing to rename:

  ```
  FileNotFoundError: [Errno 2] No such file or directory:
      '~/.cache/torvalds/agent_cache.tmp' -> '~/.cache/torvalds/agent_cache.json'
  ```

  The temp file now belongs to the writer alone (`tempfile.mkstemp` in
  the folder of the cache), and it is removed when the write fails.  The
  write is serialised by a lock, and an `fsync` before the rename makes
  the rename durable, and not only atomic.

- **A save wiped what another agent had written.**  The whole file was
  rewritten from the writer's own copy in memory, so the second of two
  agents erased the entries of the first one — the errors, the
  sessions, the git repos, the request statistics.

  The file is now read again under the lock, and only what *this*
  writer changed since it loaded the cache is applied to it.  The
  sections that grow — the error log, the sessions, the request
  statistics, the frequent commands — are merged by identity, so the
  entries of both agents survive, and an entry that was written again
  replaces its earlier version instead of being added a second time.

- **A damaged cache file was silent.**  A file that could not be read
  was replaced with an empty cache, and nothing said so.  The file that
  cannot be read is now reported — in the log, and in the status of the
  cache — and it is left as it is.

#### A failure of the model server was shown as a stack trace

- **The chat showed a traceback when the model server failed.**  The
  agent answered a failed request with the exception and the whole
  stack trace:

  ```
  Error: Internal Server Error (ref: 5da53c14-e0ba-41ea-9ae5-3fec8c43ef64) (status code: 500) (status code: 500)
  Traceback (most recent call last):
    File ".../site-packages/ollama/_client.py", line 809, in inner
      raise ResponseError(e.response.text, e.response.status_code) from None
    ...
  ```

  The traceback shows where the failure happened *inside the agent*,
  and it hides the one thing that matters: the **server** failed.  The
  operator was given forty frames of the agent and no hint of what to
  do about it.

  The chat now says what actually went wrong:

  > The Ollama server failed (HTTP 500). The request went to
  > http://localhost:11434. The usual causes are a model that crashed
  > and a model that ran out of memory - `ollama ps` shows whether a
  > model is loaded, and the server log says why it died. Reference:
  > 5da53c14-e0ba-41ea-9ae5-3fec8c43ef64.

  The traceback is not lost - it goes to the log, where it belongs.

  The other failures of the model server are named as well: the model
  that is not pulled (404), the request the server rejected (400), the
  server that cannot be reached at all, and the request that timed out.
  An error nobody knows is still shown as it is - just without the
  frames.

- **The wording named Ollama whatever failed.**  The message was the
  words of one backend, so a failure of another one was described in
  words that were wrong for it: a rejected key would have been
  answered with "the model was not found - pull it with `ollama pull`".

  The wording now follows the backend the failure came from - Ollama,
  the Anthropic API or the OpenAI API - and the backend is found twice:
  from the failure itself, which is the better witness, and from the
  LLM the agent holds, which is the fallback for the failures that say
  nothing.  Ollama turns a refused connection into a plain
  `ConnectionError`, and that failure names nobody.

  Each backend is told what to do about the failure it gave:

  > The Anthropic API refused the request (HTTP 401). The request went
  > to https://api.anthropic.com. Anthropic wants an API key: set
  > `ANTHROPIC_API_KEY`, and check that it belongs to the account that
  > may use the model. Reference: req_abc123.

  A failure that names no backend at all is described in the words of
  any backend, and no backend is named.

  The module depends on no provider package - not even on the one that
  raised the error - so it reads a failure the way every HTTP client
  reports it: a status code, a text and a class name.

- **`components/ollama_config.py` learned to name the endpoint of
  whatever serves the model.**  `get_configured_base_url(default)`
  resolves the endpoint of any backend, and `get_ollama_base_url()` is
  kept, as the name the rest of the agent already uses.

- **The wording reached two entry points of four.**  The agent is run
  in four ways, and each of them answers a failed request: the classic
  console, the panel of the multi-window console, the chat of the
  multi-window console and the llama.cpp console.  The wording was put
  in the first two, and the other two kept the traceback:

  ```
  Error: Internal Server Error (ref: 5da53c14-...)
  Traceback (most recent call last):
    File ".../agent-torvalds-mw.py", line 1055, in prompt_handler
      import traceback
    ...
  ```

  The chat of the multi-window console is the one the operator meets
  most often, and it is the one that kept pasting the frames of the
  agent into the chat.  It says now what the other two say, and the
  llama.cpp console says it too.

  A wording that reaches some of the entry points and not the others is
  a wording that is there by accident, so the tests hold every entry
  point to it: the chat of each of them carries the message, and not
  the frames.  The tests were broken once on purpose, and they failed.

#### The rule about stray test files named a folder that no longer exists

- **The skip list of the rule about stray test files carried the name of
  the retired clone folder.**  The folder is gone, and the rule was a
  name in a list — a list that had to be remembered, and a name that
  pointed at nothing.

  The rule is now a fact about the tree rather than a remembered name:
  a directory that carries its own `.git` is a copy of the repository,
  and a copy of the repository is not part of this repository.  It holds
  a whole copy of the suite, and a rule about the files of this
  repository must not read the files of the copy.  The rule holds
  whatever the copy is called.

  The rule was proved in one direction only — it must ignore a copy —
  and a rule that only ignores things can also ignore too much.  It now
  proves the other side as well: a directory that carries no `.git` is
  not a copy, so it is walked, and a test file in it is a stray like
  any other.  With the rule broken either way, the proof fails.

#### The deployment harness named a folder that no longer exists

- **The skip list of the deployment harness carried the name of the
  retired clone folder.**  The folder is gone, and the rule was a name
  in a list — a list that had to be remembered, and a name that pointed
  at nothing.

  The rule is now a fact about the tree rather than a remembered name:
  a directory that carries its own `.git` is a copy of the repository,
  and a copy of the repository is not part of the contract.  It holds
  its own copy of the script and its own copy of the harness, and
  neither is a breach.  The rule holds whatever the copy is called.

  The proof grew the matching case: the contract must **not** report
  the script that lives inside a copy of the repository.  With the
  rule removed, the copy is reported and the proof fails — a check that
  cannot fail proves nothing.

#### The example `.env` of the deployment folder configured nothing

- **`deploy/deploy-torvalds.sh.example.env` named two variables the
  agent does not read.**  `TORVALDS_CHAT_MODEL` and
  `TORVALDS_OLLAMA_BASE_URL` are the names the script used to write
  before they were corrected; the agent reads `TORVALDS_MODEL` and
  `TORVALDS_OLLAMA_HOST`.

  The example says "copy this file to .env and adjust values as
  needed", so copying it left the chat model and the Ollama endpoint
  unset — the agent fell back to its defaults, silently.

  The invariant **D8** caught exactly this in the `.env` the script
  writes, and never looked at the example.  It covers both files now,
  and the drift proof breaks the example as well: a check that has
  never failed proves nothing.

#### The private folder of the operator is never published

- **The home directory of the operator was published.**  The repository
  is public, and the home of the operator — the name of the account and
  the path that carries it — is private.  It was in the documentation,
  in the reports of the investigations, in the examples of the
  toolkits, in a test fixture and in the body of a pull request.

  It is written the way the documentation of a project writes it now:
  `~/.config/torvalds/config.toml` instead of the absolute path, and
  the name of the account is not written down at all.

- **The paths that have to work on the machine of the operator are
  computed, not written down.**  Three of them were literal paths, and
  they were wrong on every other machine:

  | | |
  |---|---|
  | `test_live_agent_hitl.py` | the directory of the file itself |
  | `investigate/context-window-proof/replay_the_operator_log.py` | `Path.home()` |
  | `agent-torvalds-cpp.py` | `os.path.expanduser`, with `TORVALDS_CPP_MODEL` |

  The model path of the C++ agent was `"${HOME}/..."` — a **shell**
  variable, in a Python file, where it is not expanded and never was.

- **The name of the account is taken from the environment.**  It was
  written down in the reports of the investigations, in the SSH harness
  of the MikroTik prototypes and in the path of the workspace on the
  external drive.

  | | |
  |---|---|
  | the reports | `$USER` |
  | `investigate/MikroTik-RouterOS/_proto_config.py` | `os.environ["USER"]`, with `getpass.getuser()` behind it |
  | `investigate/no-user-query-error/repro_live.py` | `os.environ["USER"]`, and `SOURCE_WORKSPACE` overrides it |

  A literal `$USER` is right in a shell and in a report.  In **Python**
  it is not expanded — it is a path that starts with a dollar sign — so
  the environment is read instead.  That is the same thing `$USER`
  means, and it is the reason the two are not written the same way.

- **The check is in the build.**  `tests/test_no_private_paths.py`
  looks for the **shape** of a home directory in every tracked file,
  and for the home of the machine the test runs on — **computed**,
  never written down.  It was proven against a leak: with a home in a
  tracked file, the check fails and names the file and the line.

  The generic placeholders — `/home/user/...` — are not a home of
  anybody and are left alone.

### Added

#### The configuration file — `~/.config/torvalds/config.toml`

- **The agent has a configuration file.**  It had forty-five environment
  variables and no file, and a shell profile is a poor home for
  forty-five settings: it is loaded into every shell, it is shared with
  every other program, and it cannot hold a comment that explains what a
  value is for.  The operator asked for it on 2026-10-29:

  > *"we do not have a torvalds config file let say i=under ~/.config
  > folder but I would like to introduce such folder with name 'torvalds'
  > and under this folder we can have a config"*

  The location follows the convention of the platform:

  | | |
  |---|---|
  | **Linux and the BSDs** | `~/.config/torvalds/config.toml` |
  | **macOS** | `~/Library/Application Support/torvalds/config.toml` |
  | **Windows** | `%APPDATA%` \ `torvalds` \ `config.toml` |

  `$XDG_CONFIG_HOME` is honoured on **every** platform when it is set — it
  is an explicit choice by the operator — and a **relative** path is
  ignored, the way the XDG standard says: a relative path would make the
  configuration of the agent depend on the directory it was started in.

  **Only the configuration file moves.**  What the agent produced — the
  chat history, the logs, the cache — stays where it is, on every
  system: moving it would break the sessions of everybody who already
  has one.

  The location is the **XDG** one — `$XDG_CONFIG_HOME`, or `~/.config` —
  and it completes the triad the project already keeps:

  | | |
  |---|---|
  | `~/.config/torvalds/config.toml` | the operator's **intent** |
  | `~/.torvalds/chat_manager.db` | what the agent **produced** |
  | `~/.torvalds/logs/` | what the agent **produced** |
  | `~/.cache/torvalds/agent_cache.json` | what the agent **produced** |

  The data does not move.  A database and a rotating log are not
  configuration, and moving the chat history would break the sessions of
  everybody who already has one.

- **The order of things is the one the project already used, with the
  file inserted underneath the environment variables:**

  ```
  flag  >  environment variable  >  config file  >  built-in default
  ```

  The file sits **below** the variables on purpose.  Every operator who
  has been running this agent has variables in their shell profile, and a
  file that outranked them would change the behaviour of every one of
  them the moment they upgraded — a different model, a different host,
  silently.  With the file underneath, an operator with no file sees **no
  change**, an operator with both keeps the variables winning, and the
  file becomes the *"set it once, in one place"* layer.

- **`components/config.py`** — the loader, the registry of the settings,
  the resolution and the provenance.  The format is **TOML**, read by
  `tomllib` from the standard library: no dependency, and a syntax error
  is a hard error with a line number — YAML, by contrast, turns a
  malformed document into `None`.

  | Section | What it holds |
  |---|---|
  | `[llm]` | the model, the host, the context window, the iterations, the timeout |
  | `[agent]` | the retriever, the events, the prompt injection, the context guard |
  | `[hitl]` | the human in the loop |
  | `[stats]` | the statistics |
  | `[logging]` | the level, the file, the rotation, the symlink |

- **Every setting reports where it came from.**  Four layers without
  provenance is a debugging nightmare: "why is my model X?" must have an
  answer.

- **`\config`** — the effective configuration, with the value that won
  and the layer it came from.  It works in the classic REPL (a table) and
  in the multi-window TUI (the document pane).

- **The agent writes the file for itself.**  When it starts and the file
  is not there, it creates the commented template — every setting of it is
  a comment, so **nothing changes about the way the agent runs**.  Only
  the default location is written to: a file the operator named with
  `TORVALDS_CONFIG` is theirs, and the agent does not create it.  An
  existing file is never overwritten, and a home directory that cannot be
  written to is a warning, not a failure.

- **`--write-default-config`** — writes a commented template with every
  setting, its default, the environment variable that overrides it and
  one line of explanation.

  The file is created with the mode `0600` — **at creation**, not chmod'ed
  afterwards, so there is no moment at which it is readable by every
  account on the box.  An **existing file is never overwritten**: the
  settings the operator wrote are worth more than a fresh copy of the
  defaults, so the command says so and stops.  A **symbolic link is never
  written through**.

- **A broken file never stops the agent.**  A missing file is the normal
  state of a fresh installation; a malformed one is a **warning** with
  the line and the column, and the defaults are used.  A typo is
  **reported** — a section the agent does not know, a setting it does
  not know, a value of the wrong type, a value outside the choices of
  the setting.  A setting the agent silently ignores is a setting the
  operator believes in and that does nothing.

- **The MikroTik configuration file falls back to the config directory.**
  `mikrotik_targets.yaml` was found in the **working directory only**,
  which meant it was found when the agent was started from the repository
  root and nowhere else.  The working directory is still the first place
  to look — the developer keeps working as before — and the configuration
  directory is the second.

  The **database toolkit keeps its behaviour**: its own verification
  proves that the library half is behaviour-neutral against the original
  script it was split out of, and a second search path is a difference
  that proof cannot accept.

### Fixed

#### The boolean environment variables did not agree with each other

- **`TORVALDS_HITL_ENABLED=1` disabled the human in the loop.**  The
  HITL flags were read with `== "true"` while every other boolean in the
  project was read with `in ("true", "1", "yes")` — so `1` meant *yes*
  everywhere and *no* in the HITL.  The values are read the same way
  now, and `1`, `yes` and `on` all mean *yes*.

- **A malformed integer environment variable killed the agent.**  The
  settings were read with `int(os.environ.get(...))` at import time, so
  `TORVALDS_MAX_ITERATIONS=abc` ended the run with a traceback.  A
  malformed value is now a **warning**, and the default is used.

#### The logging goes into a file, and it rotates

- **The log can be written into a file, rotated at a predefined size,
  with a symlink to the current log file next to the rotated ones.**  The
  operator asked for it on 2026-10-27:

  > *"I want be able to redirect logging into file, this solution must
  > have a posibility to rotare log when reaching current log file
  > predefined size. Inside directory we must have soft link to current
  > log file the files"*

  | Flag | Environment variable | Default |
  |---|---|---|
  | `--log-file PATH` | `TORVALDS_LOG_FILE` | *off* |
  | `--log-dir DIR` | `TORVALDS_LOG_DIR` | `~/.torvalds/logs` |
  | `--log-max-size SIZE` | `TORVALDS_LOG_MAX_SIZE` | `10MB` |
  | `--log-max-files N` | `TORVALDS_LOG_MAX_FILES` | `5` |
  | `--log-symlink NAME` | `TORVALDS_LOG_SYMLINK` | `<stem>-current.log` |

  The flag wins over the environment variable, and the environment
  variable wins over the default — the order the project already uses for
  `TORVALDS_OLLAMA_HOST`.

- **`components/file_logging.py`** — the handler, the size parser and the
  wiring.  The standard library only: `logging.handlers.RotatingFileHandler`
  does the rotation, and the subclass adds the symlink and the file mode.

  | | The stdlib handler | The subclass |
  |---|---|---|
  | Rotates at `maxBytes` | yes | yes |
  | Keeps `backupCount` generations | yes | yes |
  | The file is `0600` | no — `0666 & ~umask` | yes |
  | A symlink to the live file | no | yes |
  | The symlink heals itself | no | yes |

- **The symlink points at the *path* of the live log file, not at its
  inode.**  `doRollover()` renames `agent.log` to `agent.log.1` and
  reopens `agent.log` — the path does not change, only the file at it
  does.  The pointer is therefore valid at every moment and never has to
  be re-pointed.  It is created atomically (`os.replace`) and re-asserted
  after a rollover, so it heals itself.

- **The size limit is written the way an operator writes it** —
  `--log-max-size 10MB`, with `B`, `KB`, `MB` and `GB`.  An unknown unit
  is a **typo that is reported**: a log that never rotates because the
  size was not understood is the exact failure this feature exists to
  prevent, so the agent stops with a message instead of ignoring it.

- **The file logging is off by default**, and it is a **tee** — the
  stderr handler stays, so the operator still sees the output in the
  terminal while the file carries the history.  That was the operator's
  decision on 2026-10-29: *"no let him write to the stderr we can also
  redirect it into file under torvalds log directory"*.

- **A missing feature degrades, it never takes the agent down.**  A log
  directory that cannot be created, a log file that cannot be opened and
  a symlink that cannot be created each produce a warning, and the agent
  boots.  The two things that stop it are the two typos: a size that
  cannot be parsed, and `--log-max-files 0` — zero generations would mean
  no rotation at all, and the file would grow until the disk is full.

- **The dead `to_file` parameter of `agent-torvalds-mw.py` is gone.**  It
  had been there since the multi-window work, and no caller ever reached
  it.  It wrote to a plain `logging.FileHandler` — a handler that never
  rotates, so the file grew until the disk was full.  Both orchestrators
  now take the resolved configuration of `components/file_logging.py`.

- **`docs/logging.md`** — the rotation, the symlink, the file mode, the
  flags, the environment variables, and what degrades and what does not.

### Fixed

#### A `NameError` in the classic REPL of the multi-window agent

- **The log file announcement read a name that the function did not
  have.**  The multi-window agent has two modes — the classic REPL and
  the TUI — and the announcement of the log file was added to the REPL,
  where the resolved configuration was not a parameter.  The TUI path was
  never taken by a test, so nothing noticed, and the REPL would have
  crashed on its first run.

  `tests/test_no_undefined_globals.py` now reads the source of every
  function of both orchestrators and checks that every global it reads
  exists in its module.  It is a static check, so it covers the paths no
  test enters.

#### The L5 invariant had a hole

- **The check that the symlink cannot stop the logging passed when the
  handler was never installed.**  The check skipped the second half of
  the invariant when the handler was `None`, so a drift that turned the
  degradation of the pointer into the end of the file logging altogether
  was invisible.  The check now fails when the handler is missing, and
  the drift proof caught the drift it let through.

### Tests

- **`tests/test_file_logging.py`** — 52 tests: the size parser, the
  resolution, the handler, the degradation and the tee.
- **`tests/test_logging_cli.py`** — the five flags, their defaults and
  their environment variables, pinned next to `--log-level`.
- **`tests/test_multi_window_parity.py`** — the file-logging flags of the
  two orchestrators must not drift.
- **`tests/test_no_undefined_globals.py`** — a **static** check that every
  global a function reads exists in its module.  It closes the hole that
  let a `NameError` reach the classic REPL of the multi-window agent: the
  name was only read in that one mode, and no test entered it.
- **`investigate/logging-to-file/verify_implementation.py`** — the
  thirteen invariants of the investigation, run against the **shipped
  implementation** and not only against the prototype.
- **`investigate/logging-to-file/verify_implementation_catches_regressions.py`**
  — the proof that the harness catches seven deliberate drifts in the
  implementation.

### Documentation

#### The skills document said what the settings were, and not how to change them

- **`docs/skills.md` listed `skills.enabled`, `skills.dirs`,
  `skills.catalog_in_prompt` and `skills.body_token_limit` as a table of
  names.**  A name is not a command: the operator read them as things to
  run at a shell, and there is no `skills` command to run.  The document
  now says what they are — the **options** of the `[skills]` section of
  `~/.config/torvalds/config.toml` — and how they are changed: the
  environment variable, the file, or the one command that writes the
  file, `\config skills.body_token_limit 4000`.

- **One option, four names — and only the last one is a command.**  The
  document now tells the four apart: the line in the file
  (`body_token_limit`), the dotted name (`skills.body_token_limit`), the
  environment variable (`TORVALDS_SKILLS_BODY_TOKEN_LIMIT`) and the
  command (`\config skills.body_token_limit 4000`).  The recipes show the
  option, the line in the file and the command side by side, so the one
  that is **typed** is never mistaken for the one that is **read**.

- **The three layers and the moment of the change are written down.**
  The environment variable wins over the file, the file wins over the
  default, and the settings of the skills are read when the agent starts
  — so a change applies on the **next start**.  Four recipes are given:
  turn the feature off, look in one folder only, put the catalog in the
  prompt, raise the limit of the body.

- **A section on managing the skills was added.**  A skill is a file, not
  a command: it is added by making a folder with a `SKILL.md` in it,
  changed by editing that file, removed by deleting the folder, and
  overridden by a skill of the project with the same name.  The document
  also says where the agent announces the skills it found, that a broken
  skill is skipped rather than fatal, and how to list the skills of the
  machine from a shell — the same discovery, without a model and without
  a token.

#### How the agent carries a skill — the tools, and the price of the body

- **`docs/skills-in-the-agent.md` is new.**  It says what the agent does
  with a skill once it has one: where the two tools live, what the body of a
  skill costs, and when it is paid.

- **The retriever is asked twice per turn, and the second question is the
  name of the tool.**  `run_agent_step()` asks it with the question of the
  user — that is where the eight tools are picked — but `call_tool()` asks it
  with the **name** of the tool that is being called.  A retriever that
  matches on meaning does not match on a name, so a tool that is only in the
  retriever is not found when it is called.  A skill tool therefore has to be
  in `agent.tools`, which is how both orchestrators already build it.

- **The body of a skill is paid again by every request that follows.**
  `finalize()` writes the whole scratchpad into the memory of the session, so
  the body is carried along: on the request after the activation it was 85%
  of the prompt.  It leaves the prompt when the context guard drops it as the
  oldest turn of a conversation that has grown — round 18, on the synthetic
  growth of the probe.

- **The transient channel is measured, not shipped.**  A body dropped as soon
  as the model has read it pays off only when the run *continues* past the
  body; a run that ends with the body pays the same as without it.

- **`investigate/skills-in-function-agent/INVESTIGATION_REPORT.md`** holds the
  evidence, and
  **`investigate/skills-in-function-agent/probe_skills_in_function_agent.py`**
  the read-only probe that prints it.  The probe measures the transient
  channel in the two cases that differ — a run that ends with the body, and a
  run that continues past it.

#### The terminal after a privileged command

- **The operator reported that the terminal goes mute after a command
  that asked for the sudo password in a window**, and pointed at
  [pyinvoke/invoke#303](https://github.com/pyinvoke/invoke/issues/303) —
  the same defect in another project: the process that changed the
  terminal settings died in the middle of the question and never gave
  them back.

- **The question in a window does not damage the terminal.**  It was
  measured, in a pty of the probe's own: the echo is still on after a
  command that was escalated through `pkexec` and polkit.

- **The paths that ask on the terminal do.**  The `sudo` fallback (when
  there is no polkit agent to ask), the textual agent of `pkexec` (at a
  console, when no window answers), and the whiptail dialog of the APT
  toolkit all switch the **echo off** to read the password.  The agent
  kills the child when the timeout fires — with **SIGKILL**, which
  cannot be caught — and it kills only the shell, not the `sudo` behind
  it.  The terminal keeps the echo-off state, and the operator is left
  typing into a terminal that shows nothing.

  | Measurement | The echo afterwards |
  |---|---|
  | the question in a window (`pkexec` + polkit) | **on** |
  | the question on the terminal (`sudo -v`) | **OFF** |
  | the mechanism — a child that only switches the echo off | **OFF** |

- **The agent is the one that has to give the terminal back.**  The
  other two places in the repository that switch the terminal off — the
  masked password of `components/console_input_module.py` and the reader
  of `components/tui/input_reader.py` — give it back in a `finally`,
  with an `atexit` hook behind it.  The privilege path has neither: the
  agent never takes the terminal, so it cannot give it back.  This is
  the rule of invoke#303, whose fix upstream (0.12.2) was to tie the IO
  threads off *before* the exception is re-raised.

- **A mute terminal is baked into the baseline of the next run.**  The
  reader of the TUI captures the state of the terminal when it starts
  and restores *that* state when it stops — so a terminal that was
  already mute stays mute, and the state outlives the agent.

- **The evidence is in `investigate/privilege-terminal-echo/`.**  The
  probe (`probe_privilege_terminal.py`) runs five measurements against
  the real code of the repository, in a pty of its own, so it never
  touches the terminal of the operator.  Before the fix it exits **1** —
  *"the terminal was left mute"*.  The fix is proposed in
  `investigate/privilege-terminal-echo/PROPOSAL.md`, and it is in
  *"The terminal is given back after a privileged command"* above: the
  probe exits **0** now — *"the terminal was given back in every
  measurement"*.

- **After the fix:** `stty sane` is not needed any more.  It is still
  the answer for a terminal that was left mute by a `kill -9` of the
  agent — SIGKILL cannot be caught, and no program can answer for it.

#### The status lines of two reports were older than the merge

- **The reports of the TUI work still said that the work was not
  committed.**  Both of them — the terminal size and the session
  selection — carried *"not committed (Rule 2: awaiting the operator's
  approval)"*, and so did the README of the first.  The work was
  merged: PR #95 and PR #96 are in `master`.

  A status line is read by the next person who opens the report, and
  this one answered *"is this committed?"* with *"no, it waits for an
  approval that has already been given"*.  The line now says what is
  true: the operator approved the commit, and the fix is in `master`.

  | | |
  |---|---|
  | `investigate/tui-selection-and-flicker/IMPLEMENTATION_REPORT.md` | PR #95, `1f8c52e` |
  | `investigate/tui-selection-and-flicker/README.md` | PR #95, `1f8c52e` |
  | `investigate/tui-session-selection/IMPLEMENTATION_REPORT.md` | PR #96, `e031ebf` |

## [1.0.0] - 2026-10-29

### Added

#### The unified project loading API

- **NEW: `load_project()` unified project loading API** — transparently handles both existing workspaces (loads from `.agentworkspace.json`) and new project discovery (creates workspace, scans, detects, and registers)
- **Unified Entry Point**: Single method to load projects regardless of whether a workspace already exists
- **Two Loading Modes**:
  - `existing_workspace`: Loads project from existing `.agentworkspace.json` config
  - `new_workspace`: Creates workspace, scans directory, auto-detects type, and registers project
- **Smart Project Resolution**: Supports lookup by `project_name` or automatic path matching
- **Standardized Results**: Returns consistent dictionary structure with `status`, `method`, `workspace_path`, and full `project` metadata
- **Fallback Handling**: Gracefully falls back to first project when no exact path match is found in existing workspaces
- **Force Mode**: Supports `force=True` to register projects even when type detection is ambiguous

#### The deployment scripts have a home of their own

- **`deploy/`** — the dedicated folder for the deployment scripts.  The
  script used to live in `investigate/deployment-script/`, next to the
  report that described it, which is the wrong home for it:
  `investigate/` holds the *record* of a piece of work, and the
  implementations that came out of it live in their own place — the
  toolkits under `toolkits/`, the chat manager under `chat_manager/`, the
  deployment scripts here.  The investigation documents stayed where
  they were.

  | Path | What it is |
  |---|---|
  | `deploy/deploy-torvalds.sh` | The deployment script, moved |
  | `deploy/deploy-torvalds.sh.example.env` | The example environment file, moved |
  | `deploy/README.md` | What the folder holds, and how to use it |
  | `deploy/tests/` | The folder's contract harness, and the proof that it catches deliberate breakage |

- **`deploy/tests/verify_deploy_layout.py`** — eleven invariants that
  hold the folder and the script to their contract, and
  **`deploy/tests/verify_harness_catches_regressions.py`** — the proof
  that the harness catches eleven deliberate drifts, one per invariant.
  Both run under pytest as well.

#### The prompt in the debug log is readable

- **The context window is logged at the `INFO` level.**  The size of
  the model's context window is written to the log when the agent
  starts, together with the place the number came from:

  ```console
  2026-10-27 21:24:03,517 [INFO] components.ollama_config: Context window: 8192 tokens — the running model (/api/ps)
  ```

  The number is the window the **server** uses — not the maximum the
  model advertises.  The two are often very different: the agent's
  model advertises 262144 tokens, and the server runs it with 8192.  A
  prompt that exceeds the real window is truncated from the front by
  the server, which drops the user request and makes the model
  template fail with "No user query found in messages.".

  The source is named in the log line, because a number on its own
  does not say whether it is the window the server really uses.  The
  sources are tried in this order: `TORVALDS_CONTEXT_LENGTH`, the
  running model (`/api/ps`), `PARAMETER num_ctx` in the Modelfile,
  and finally the maximum the model advertises.

- **The context guard logs the budget it works with.**  With
  `--context-guard-on` the agent writes the window and the part of it
  the prompt may take:

  ```console
  2026-10-27 21:24:03,601 [INFO] components.hitl_agent: Context guard: the context window is 8192 tokens — the prompt may use 6554 of them.
  ```

- **`investigate/context-window-proof/`** — the proof that the reported
  window is the server's and not the model's advertisement: four
  invariants, and a second script that proves the harness catches four
  deliberate drifts.

#### The prompt in the debug log is readable

- **`components/chat_message.py`** - the rendering: `to_string()` for
  one message, `to_strings()` for a whole prompt.  `ChatMessage` is a
  class of the LlamaIndex framework, so the rendering is a function of
  this project rather than a method of the framework's class.
- **`tests/test_chat_message.py`** - 26 tests.
- **`investigate/chat-message-debug/verify_chat_message.py`** - the
  verification harness: four invariants, written against the public
  behaviour (the log records and the state).  The second script in that
  folder proves the harness catches four deliberate drifts.

#### The context guard is optional

- **`--context-guard-on`** — the command line switch, in `agent-torvalds.py`
  and in `agent-torvalds-mw.py`.  The startup banner reports the effective
  state ("Context guard: enabled" / "disabled").

- **`TORVALDS_CONTEXT_GUARD`** — the environment variable, for the runs
  that are started by something else (a service, a script).  It accepts
  `true`, `1` and `yes`, like the other feature flags.

- **`tests/test_context_guard_toggle.py`** — the tests that pin the switch:
  the guard stands down by default, the prompt grows past the context
  window when it does, the prompt is trimmed and keeps the user request
  when the guard is on, and the flag and the environment variable turn it
  on.

#### The data analysis toolkit is a module

- **`toolkits/data-analysis-toolkit/`** — the package, with a `README.md`, a
  `py.typed` marker and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/data-analysis-toolkit`).  The distribution depends
  on `pandas` and `numpy`; the adapter is an extra
  (`data-analysis-toolkit[agent]`).

- **`toolkits/data-analysis-toolkit/tests/`** — the test suite, 94 tests.  The
  suite that used to live at `tests/test_data_analysis_toolkit.py` moved with
  the toolkit and was extended: the error contract of all thirteen operations,
  the tool surface and its order are now pinned.

- **`toolkits/data-analysis-toolkit/tests/test_package_layout.py`** — the layout
  contract, 33 checks: the flat layout, the relative imports, the alias, the
  LlamaIndex boundary, the dependency profile of the library half, the
  thirteen-tool surface and the fact that no call site imports the old module
  name any more.

- **`toolkits/data-analysis-toolkit/tests/test_split_verification.py`** — the
  test of the mechanical check, driven with fourteen deliberate drifts: a
  reworded tool description, a dropped docstring, a changed body, a changed
  parameter default, two operations swapped, a LlamaIndex import in the
  library half, a tool that went missing, an operation that went missing, a
  lost module-level logger, a lost dependency, an unexpected one, a lost
  numpy import, the tool registry in the wrong half and a dependency the
  original did not have.

- **`investigate/data-analysis-toolkit-module/verify_split.py`** — the mechanical
  check: it compares the *committed* original with the new files, by AST, and
  fails on a changed signature, a changed docstring, a changed body, a changed
  order, a changed tool description, a lost module-level logger, a changed
  dependency profile, a lost pandas or numpy import or a LlamaIndex import in
  the wrong half.  The original is **found, not assumed**: a named ref that
  still carries the file, and otherwise the parent of the commit that deleted
  it, so the check also works in a CI checkout with a detached HEAD.

- **`investigate/data-analysis-toolkit-module/verify_optional_dependency.py`** —
  the measurement of what a missing `pandas` does: with `pandas` blocked at
  the import machinery, the agent still boots.

- **`investigate/data-analysis-toolkit-module/dump_tool_menu.py`** — the tool
  menu dump, so the menu of this tree and the menu of `master` can be
  compared byte for byte.

- **`investigate/data-analysis-toolkit-module/REPORT_data_analysis_toolkit_module.md`**
  — the report: what was implemented, and why.

#### The Excel toolkit is a module

- **`toolkits/xlsx-toolkit/`** — the package, with a `README.md`, a `py.typed`
  marker and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/xlsx-toolkit`).  The distribution depends on
  `openpyxl`; the adapter is an extra (`xlsx-toolkit[agent]`).

- **`toolkits/xlsx-toolkit/tests/`** — the test suite, 95 tests.  The suite
  that used to live at `tests/test_xlsx_toolkit.py` moved with the toolkit and
  was extended: the error contract of all nine operations, the tool surface and
  its order are now pinned.

- **`toolkits/xlsx-toolkit/tests/test_package_layout.py`** — the layout contract,
  33 checks: the flat layout, the relative imports, the alias, the LlamaIndex
  boundary, the dependency profile of the library half, the nine-tool surface
  and the fact that no call site imports the old module name any more.

- **`toolkits/xlsx-toolkit/tests/test_split_verification.py`** — the test of the
  mechanical check, driven with twelve deliberate drifts: a reworded tool
  description, a dropped docstring, a changed body, a changed parameter
  default, two operations swapped, a LlamaIndex import in the library half, a
  tool that went missing, an operation that went missing, a lost module-level
  logger, a lost dependency, an unexpected one and a lost openpyxl import.

- **`investigate/xlsx-toolkit-module/verify_split.py`** — the mechanical check: it
  compares the *committed* original with the new files, by AST, and fails on a
  changed signature, a changed docstring, a changed body, a changed order, a
  changed tool description, a lost module-level logger, a changed dependency
  profile, a lost openpyxl import or a LlamaIndex import in the wrong half.
  The original is **found, not assumed**: a named ref that still carries the
  file, and otherwise the parent of the commit that deleted it, so the check
  also works in a CI checkout with a detached HEAD.

- **`investigate/xlsx-toolkit-module/REPORT_xlsx_toolkit_module.md`** — the report:
  what was implemented, and why.

#### The database toolkit is a module

- **`toolkits/db-toolkit/`** — the package, with a `README.md`, a `py.typed`
  marker and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/db-toolkit`).  The distribution depends on the two
  drivers and on `PyYAML`; the adapter is an extra (`db-toolkit[agent]`).

- **`toolkits/db-toolkit/tests/`** — the test suite, 85 tests.  The toolkit had
  **no** test suite before this change; the one that came with it is
  **offline** — it drives the operations through a stubbed `psycopg2` and a
  stubbed `mysql.connector`, so it needs no database server.

- **`toolkits/db-toolkit/tests/test_package_layout.py`** — the layout contract,
  34 checks: the flat layout, the relative imports, the alias, the LlamaIndex
  boundary, the dependency profile of the library half, the two-tool surface,
  the import-time configuration load, and the fact that no call site imports
  the old module name any more.

- **`toolkits/db-toolkit/tests/test_split_verification.py`** — the test of the
  mechanical check, driven with eleven deliberate drifts: a reworded tool
  description, a dropped docstring, a changed body, two operations swapped, a
  LlamaIndex import in the library half, a tool that went missing, an
  operation that went missing, a lost module-level logger, a lost import-time
  configuration load, a lost dependency and an unexpected one.

- **`investigate/db-toolkit-module/verify_split.py`** — the mechanical check: it
  compares the *committed* original with the new files, by AST, and fails on a
  changed signature, a changed docstring, a changed body, a changed order, a
  changed tool description, a lost module-level logger, a lost import-time
  configuration load, a changed dependency profile or a LlamaIndex import in
  the wrong half.  The original is **found, not assumed**: a named ref that
  still carries the file, and otherwise the parent of the commit that deleted
  it, so the check also works in a CI checkout with a detached HEAD.

- **`investigate/db-toolkit-module/REPORT_db_toolkit_module.md`** — the report:
  what was implemented, and why.

- **`conftest.py`** — the session-wide test preparation.  The toolkit reads its
  configuration file at import time, so the file has to be in the working
  directory before anything imports it; the conftest puts it there when it is
  missing and removes it again when the session ends.

#### The Windows toolkit is a module

- **`toolkits/windows-toolkit/`** — the package, with a `README.md`, a `py.typed` marker
  and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/windows-toolkit`).  The distribution has no
  dependency; the adapter is an extra (`windows-toolkit[agent]`).

- **`toolkits/windows-toolkit/tests/`** — the test suite, 87 tests.  The toolkit
  had **no** test suite before this change; the one that came with it is
  platform-independent — it drives the operations through a stubbed
  `subprocess.run`, so it needs neither Windows nor a PowerShell installation.

- **`toolkits/windows-toolkit/tests/test_package_layout.py`** — the layout contract,
  30 checks: the flat layout, the relative imports, the alias, the LlamaIndex
  boundary, the dependency profile of the library half, the six-tool surface, and
  the fact that no call site imports the old module name any more.

- **`toolkits/windows-toolkit/tests/test_split_verification.py`** — the test of the
  mechanical check, driven with nine deliberate drifts: a reworded tool
  description, a changed parameter default, a dropped docstring, a changed body,
  two operations swapped, a LlamaIndex import in the library half, a tool that
  went missing, an operation that went missing, and a lost module-level logger.

- **`investigate/windows-toolkit-module/verify_split.py`** — the mechanical check: it
  compares the *committed* original with the new files, by AST, and fails on a
  changed signature, a changed docstring, a changed body, a changed order, a
  changed tool description, a lost module-level logger or a LlamaIndex import in
  the wrong half.  The original is **found, not assumed**: a named ref that still
  carries the file, and otherwise the parent of the commit that deleted it, so the
  check also works in a CI checkout with a detached HEAD.

- **`investigate/windows-toolkit-module/REPORT_windows_toolkit_module.md`** — the
  report: what was implemented, and why.

#### The APT toolkit is a module

- **`toolkits/apt-toolkit/`** — the package, with a `README.md`, a `py.typed` marker
  and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/apt-toolkit`).  The distribution depends on `rich`; the
  adapter is an extra (`apt-toolkit[agent]`).

- **`toolkits/apt-toolkit/tests/`** — the test suite, 101 tests.  The 48 tests the
  toolkit already had moved with it, and two new files were added: the layout
  contract (37 checks) and the test of the split-verification script (16 tests).

- **`toolkits/apt-toolkit/tests/test_package_layout.py`** — the layout contract, 37
  checks: the flat layout, the relative imports, the alias, the LlamaIndex
  boundary, the dependency profile of the library half, the ten-tool surface, the
  command-line interface, and the fact that no call site imports the old module
  name any more.

- **`toolkits/apt-toolkit/tests/test_split_verification.py`** — the test of the
  mechanical check, driven with twelve deliberate drifts: a reworded tool
  description, a changed parameter default, a dropped docstring, a changed body,
  two operations swapped, a LlamaIndex import in the library half, a tool that
  went missing, an operation that went missing, a reworded command-line option,
  narrowed command-line choices, a reworded command-line message and a dropped
  command-line option.

- **`investigate/apt-toolkit-module/verify_split.py`** — the mechanical check: it
  compares the *committed* original with the new files, by AST, and fails on a
  changed signature, a changed docstring, a changed body, a changed order, a
  changed tool description, a changed command-line interface or a LlamaIndex
  import in the wrong half.  The original is **found, not assumed**: a named ref
  that still carries the file, and otherwise the parent of the commit that deleted
  it, so the check also works in a CI checkout with a detached HEAD.  It compares
  the **section headers** of the module as well — they are the reader's map of
  the file, and the first cut of the split lost every one of them.

- **`investigate/apt-toolkit-module/REPORT_apt_toolkit_module.md`** — the report:
  what was implemented, and why.

#### The Linux toolkit is a module

- **`toolkits/linux-toolkit/`** — the package, with a `README.md`, a `py.typed` marker
  and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/linux-toolkit`).  The distribution depends on the standard
  library and on nothing else; the adapter is an extra (`linux-toolkit[agent]`).

- **`toolkits/linux-toolkit/tests/`** — the test suite, 78 tests.  The eleven tests
  the toolkit already had moved with it, and the suite was extended to cover the
  error contract of every operation: a failure is *reported*, never raised.  Three
  of the new tests pin behaviour that is easy to get wrong: `shell=False` treats the
  command as a *path*, a command that writes to `stderr` may still have succeeded,
  and `run_command_with_env` has a hard-coded 30 second timeout.

- **`toolkits/linux-toolkit/tests/test_package_layout.py`** — the layout contract, 31
  checks: the flat layout, the relative imports, the alias, the LlamaIndex
  boundary, the dependency profile of the library half, the six-tool surface, and
  the fact that no call site imports the old module name any more.

- **`toolkits/linux-toolkit/tests/test_split_verification.py`** — the test of the
  mechanical check, driven with seven deliberate drifts: a reworded tool
  description, a changed parameter default, a dropped docstring, a changed body,
  two operations swapped, a LlamaIndex import in the library half, and a tool that
  went missing.  A check that has never failed proves nothing.

- **`investigate/linux-toolkit-module/verify_split.py`** — the mechanical check that
  the split moved everything verbatim: the operation names, their order, their
  signatures, their docstrings, their bodies, and the tool names, their order and
  their descriptions, compared against the committed original by AST.

#### The OS toolkit is a module

- **`toolkits/os-toolkit/`** — the package, with a `README.md`, a `py.typed` marker
  and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/os-toolkit`).  The distribution depends on the standard
  library and on nothing else; the adapter is an extra (`os-toolkit[agent]`).

- **`toolkits/os-toolkit/tests/`** — the test suite, 69 tests.  The seventeen tests
  the toolkit already had moved with it, and the suite was extended to cover the
  error contract of every operation: a failure is *reported*, never raised.

- **`toolkits/os-toolkit/tests/test_package_layout.py`** — the layout contract, 28
  checks: the flat layout, the relative imports, the alias, the LlamaIndex
  boundary, the dependency profile of the library half and the eleven-tool surface.

- **`investigate/os-toolkit-module/verify_split.py`** — the mechanical check that
  the split moved everything verbatim: the operation names, their order, their
  signatures, their docstrings, their bodies, and the tool names, their order and
  their descriptions, compared against the committed original by AST.

#### The GitHub toolkit is a module

- **`toolkits/github-toolkit/`** — the package, with a `README.md`, a `py.typed` marker
  and a `pyproject.toml` for a standalone install
  (`pip install ./toolkits/github-toolkit`).  The distribution depends on `requests`
  and on nothing else; the adapter is an extra (`github-toolkit[agent]`).

- **A test suite for the GitHub toolkit.**  It is the first toolkit of the
  "every toolkit is a module" refactoring that arrived **without** tests, so moving
  it would have been an entirely unverified refactoring.  The suite — 95 tests —
  pins the behaviour of every operation: the token resolution, the headers, the
  status-code mapping, the error contract and the payload of all thirteen tools.  It
  is **offline**: `requests` is stubbed at the transport boundary and the GitHub CLI
  is stubbed too, so no test reaches `api.github.com` and no test needs a token.

- **`toolkits/github-toolkit/tests/test_package_layout.py`** — the layout contract,
  25 checks: the flat layout, the relative imports, the alias, the LlamaIndex
  boundary, the dependency profile of the library half and the thirteen-tool surface.

- **The adapter re-exports the 13 GitHub functions**, so a star import keeps working
  the way it did when the toolkit was a single module.

#### The Git toolkit is a module

- **`toolkits/git-toolkit/`** — the package, with a `README.md`, a `py.typed` marker and a
  `pyproject.toml` for a standalone install (`pip install ./toolkits/git-toolkit`).  The
  distribution depends on `pygit2` and on nothing else; the adapter is an extra
  (`git-toolkit[agent]`).

- **A layout contract for the toolkit.**  `toolkits/git-toolkit/tests/test_package_layout.py`
  is new — 24 checks that pin the layout, the relative imports, the import alias, the
  LlamaIndex boundary and the dependency profile of the library half, so the package
  cannot drift back to a loose module at the root.

- **`toolkits/git-toolkit/tests/test_operations.py`** — the test suite, moved out of
  `tests/test_git_toolkit.py` and switched to relative imports.

- **The Git toolkit joined the alias contract.**  `tests/test_toolkit_alias_contract.py`
  now covers it, so the alias is a literal, the submodules resolve to one object, and
  `import toolkits` still does not import LlamaIndex.

#### The math toolkit is a module

- **`toolkits/math-toolkit/`** — the package, with a `README.md`, a `py.typed` marker and a
  `pyproject.toml` for a standalone install (`pip install ./toolkits/math-toolkit`).  The
  distribution has **no** third-party dependency: the library half is pure standard library,
  and the adapter is an extra (`math-toolkit[agent]`).

- **A layout contract for the toolkit.**  `toolkits/math-toolkit/tests/test_package_layout.py`
  is new — 18 checks that pin the layout, the relative imports, the import alias and the
  LlamaIndex boundary, so the package cannot drift back to a loose module at the root.

- **`toolkits/math-toolkit/tests/test_operations.py`** — the test suite, moved out of
  `tests/test_math_toolkit.py` and switched to relative imports.

- **The math toolkit joined the alias contract.**  `tests/test_toolkit_alias_contract.py`
  now covers it, so the alias is a literal, the submodules resolve to one object, and
  `import toolkits` still does not import LlamaIndex.

#### The legacy chat memory is gone

- **`chat_manager.startup.get_memory_buffer()`.**  Returns the memory buffer for the active
  session, and falls back to an in-memory buffer when the manager is not up — so the
  orchestrators can call it unguarded and always have a usable memory.

  `chat_manager.startup.get_in_memory_buffer()` is the in-memory buffer on its own.  Both are
  cached process-wide, so every caller sees the same conversation.

- **A regression test for the outage path.**  `chat_manager/tests/test_startup_memory.py` pins
  the behaviour the removal rests on: with the primary database unreachable the manager still
  comes up completely — user, sessions, active session — and the buffer is bound to that
  active session.

#### The chat history survives a database outage

- **The metadata layer now has a local fallback.**  When the primary
  database cannot be reached, `CustomDBConnector` retries against a local
  SQLite file (`~/.torvalds/chat_manager.db` by default) and records the
  degradation.  This is the same shape of degradation the message backend
  already had, and it removes the last reason the legacy single-key chat
  memory had to stay in the code: the manager now covers both "PostgreSQL
  up" (full features) and "PostgreSQL down" (degraded but complete).

  Everything the manager does keeps working on the fallback — user
  identification and provisioning, the session lifecycle, the active
  session and the user's settings.  The only thing it loses is *sharing*:
  the history lives in one local file instead of the shared database.

  | Variable | Default | Description |
  |----------|---------|-------------|
  | `TORVALDS_STORAGE_FALLBACK_URI` | `sqlite:///~/.torvalds/chat_manager.db` | The local database used when the primary one cannot be reached. |
  | `TORVALDS_STORAGE_FALLBACK` | *(enabled)* | Set to `off` / `none` / `no` / `0` / `false` to switch the fallback off. |

  The directory is created automatically.  The URI can also be passed
  directly: `CustomDBConnector(connection_uri=…, fallback_uri=…)` and
  `ChatHistoryManager(…, fallback_uri=…)` — an empty string switches the
  fallback off.

- **The degradation is reported, not hidden.**  `connector.is_degraded`,
  `connector.active_uri` and `connector.degradation_reason` describe what
  is going on; `manager.is_degraded` and `manager.storage_mode`
  (`primary` / `fallback` / `unavailable`) do the same one level up.  Both
  orchestrators print a yellow notice at startup, and `\chat-info` shows
  a `Storage:` line.

#### The user can finally change their own settings

- **A user-settings API in the `chat_manager` module.**
  `ChatHistoryManager.get_user_settings()` returns an immutable
  `UserSettings` snapshot of the current user's preferences, and
  `ChatHistoryManager.update_user_settings(**changes)` validates,
  persists and applies a change.  The values are validated **before**
  anything is written, so a bad value never leaves the settings
  half-updated.  A convenience wrapper,
  `ChatHistoryManager.set_chat_token_limit(limit)`, covers the one
  setting that changes most often.  The new `chat_manager/settings.py`
  module is the single source of truth for the settings, their ranges
  and their validation; `UserSettings`, `SettingSpec`, `SettingError`
  and the `DEFAULT_/MIN_/MAX_CHAT_TOKEN_LIMIT` constants are exported
  from the package root.
- **A `\chat-user` command over the user's own configuration.** It is
  dispatched by the same `\chat-*` layer as every other chat command —
  before the LLM is invoked, so it costs no tokens and the model cannot
  trigger it — and it is declared in `components/command_registry.py`,
  so `\help` lists it in both orchestrators.

  | Command | Description |
  |---------|-------------|
  | `\chat-user` | Show every setting and its value. |
  | `\chat-user get <key>` | Show one setting. |
  | `\chat-user set <key> <value>` | Change one setting. |
  | `\chat-user help` | List the settings, their ranges and their usage. |

  The multi-window agent renders the settings as a Markdown table
  (`components/tui/chat_history_view.py`), so the TUI and the classic
  REPL show the same thing.

#### The toolkits own their adapters

- **Seven new contract tests** — the adapter is reachable through the alias
  and resolves to one module object; `import toolkits` does not drag
  LlamaIndex into the process; the library half of the package keeps its
  LlamaIndex-free rule, with the adapter as the single named exception.
- **Three new rows in `verify_layout_contract.py`** (R1b, R1c, R4) and
  **four new tests** in the package-local layout suite.
- **New report**: `investigate/toolkit-adapter-location/REPORT_toolkit_adapter_location.md`.

#### A timeout the model can see

- **New regression tests**: `tests/test_hitl_timeout_policy.py` — six tests
  against the real agent, the real consumer and the real input module; only
  the human is a double. Two of them fail without the fix.
- **New harness**: `investigate/hitl-timeout-policy/verify_timeout_policy.py`
  — 11 checks of the operator's rule; 9/11 before the fix, 11/11 after.
- **New report**: `investigate/hitl-timeout-policy/REPORT_timeout_policy.md`.
- **The timeout rule** in `DEVELOPMENT_RULES.md`: how the agent waits for
  the operator, and what it may do when the wait ends.

#### Continuous integration

- **A CI workflow that runs the test suite** — `.github/workflows/tests.yml`
  runs on every push to `master` and on every pull request, on
  `ubuntu-latest` with Python 3.12. The failure list is uploaded as the
  artifact `pytest-failures` when the build is red.
- **`scripts/ci_test_gate.py` — the CI test gate.** The suite carries 77
  known failures, so a plain `pytest` run is always red and a workflow
  built on it would be noise. The gate compares the failures with a
  committed baseline and fails the build **only when a failure appears
  that is not in it**: a new regression breaks the build, the known
  failures do not. It also reports the failures that have been fixed, so
  the baseline can be tightened.
- **`tests/ci_baseline.txt` — the known-failure baseline.** One node id
  per line, regenerated with
  `python scripts/ci_test_gate.py --write-baseline`.
- **`requirements-ci.lock` — the pinned environment for CI.**
  `requirements.txt` states the minimum versions the agent supports; the
  lock pins the versions the baseline was recorded with, so the baseline
  means the same thing on every runner. `llama-index-llms-llama-cpp` is
  deliberately absent — it pulls `llama-cpp-python`, which has no
  prebuilt wheel, and the test suite does not need it.
- **`docs/ci.md`** — how the gate works, what the known failures are, and
  how to tighten the baseline.

#### HITL question presentation

- **`components/hitl_question.py`** — the single source of truth for what a
  question is: `split_question()`, `detect_input_type()`,
  `normalise_question()` and `is_question()`. Every function is pure, so
  the whole thing is unit-testable without a workflow, an LLM or a console.
  The two copies of the detection patterns (in `hitl_agent` and
  `human_loop_handler`) and the two copies of the input-type heuristic have
  been removed — they had already drifted apart.
- **A question written as a list of choices is a menu** — "Would you like
  me to: 1. Set up sqitch? 2. Write the docs?" cannot be answered with a
  yes or a no, so the question is now typed `menu` and the operator picks
  one of the options. The input modules gained `menu_with_status()`, which
  does **not** print the options — the consumer renders them with the
  question, so they cannot appear twice. The TUI command bar shows the
  number range and takes the number; the whiptail dialog shows its own
  menu.
- **The TUI footer follows the question** — the command bar now labels the
  prompt by the kind of answer the question wants ("Answer", "Yes/No",
  "Option", "Password") instead of always saying "Answer".
- **`tests/test_hitl_question_presentation.py`** — 44 tests: the splitting,
  the input type, the normalisation, the menu, the status-aware input API
  and the wiring (the question is rendered once, the context is rendered,
  the input module never receives the question, the empty answer is a
  timeout, the answer still reaches the agent).

#### Shodan Toolkit

- **Shodan toolkit** — the agent can now query the Shodan internet-exposure
  database. Sixteen tools are exposed: `shodan_search`, `shodan_count`,
  `shodan_host`, `shodan_stats`, `shodan_trends`, `shodan_domain_info`,
  `shodan_honeyscore`, `shodan_myip`, `shodan_account_info`,
  `shodan_list_alerts`, `shodan_list_scans`, `shodan_raw`, and the four
  write-capable tools `shodan_create_alert`, `shodan_delete_alert`,
  `shodan_submit_scan` and `shodan_download`.
- **The project was moved into this repository** — the toolkit was developed
  standalone and now lives in `toolkits/shodan-toolkit/`. The move used
  `git subtree`, so the **original commits are preserved** in the history of
  the `feature/shodan-toolkit` branch, grafted under the
  `toolkits/shodan-toolkit/` prefix. The content is byte-identical to the
  upstream project (every file has the same blob hash), so the upstream
  repository stays the source of truth and `git subtree pull` can bring in
  later upstream work.
- **Reusable core package** — the library half keeps its upstream `src/`
  layout and imports **no** LlamaIndex at import time, so it stays
  independently testable and can be used as a plain library. The directory
  name contains a hyphen, so consumers import it through the alias
  `toolkits.shodan_toolkit`, which `toolkits/__init__.py` registers.
- **`agent_shodan_toolkit.py`** — the LlamaIndex adapter. It does not
  re-implement the tools: it re-uses the upstream functions verbatim and
  only rewrites the descriptions so that every tool carries the
  `Category: Security` tag the startup selection menu needs.
- **The Security category** — the Shodan tools form their own category in
  the startup tool selection menu (`--select`, and `\tools` /
  `\tool-select` in the TUI), so they can be loaded on their own.
- **`docs/shodan-toolkit.md`** — the end-user reference: installation,
  configuration, the tools, the read-only / write split, the limitations,
  the security model and the troubleshooting table.
- **`toolkits/shodan-toolkit/tests/test_agent_adapter.py`** — 19 tests for
  the adapter: the tool registration, the degradation contract, the
  error-payload convention, the raw-command guard and the load-path parity.
- **The Security category is locked down by a regression suite** —
  `tests/test_tool_selection_menu.py` now covers the Shodan tools the same
  way it covered the MikroTik ones: the category must exist, hold exactly
  the twelve read-only tools, be selectable through
  `select_tools_by_category()` and the interactive prompt, and be rendered
  in the menu. The write-capable tools must stay out of the menu unless
  `TORVALDS_SHODAN_ALLOW_MUTATING=1` is set, and the Shodan tools must be
  reachable through every load path (menu, retriever, both orchestrators).

#### Local LLM setup (Ollama)

- **`components/ollama_config.py`** - the single source of truth for the
  Ollama endpoint. `get_ollama_base_url()` resolves
  `TORVALDS_OLLAMA_HOST`, then `OLLAMA_HOST`, then
  `http://localhost:11434`, and normalises a bare `host:port` into a full
  URL with the `http://` scheme.
- **`TORVALDS_OLLAMA_HOST`** - points the agent at an Ollama server that does
  not listen on the default endpoint (another host, a container, a
  non-default port). It is used for the chat model in both orchestrators
  and for the embedding model in the tool retriever.

#### HITL: no timeout by default

- **`components/hitl_timeout.py`** — the single source of truth for the
  convention. It provides `NO_TIMEOUT` (`-1`), `normalize_timeout()` (the
  translation into the `None` that `asyncio.wait_for` and
  `Context.wait_for_event` expect), `is_no_timeout()`, `validate_timeout()`
  and `describe_timeout()` (which renders `-1` as `none` in the status
  output).

#### MikroTik RouterOS Toolkit

- **MikroTik RouterOS toolkit** — the agent can now inspect and configure
  MikroTik routers over SSH. Eight tools are exposed: list the configured
  routers, test the connection, run a single RouterOS CLI command, read a
  configuration section, export the configuration, read the device identity,
  list the interfaces, and read the health (CPU, memory, disk, recent
  errors).
- **Reusable core package** — the library half lives in
  `toolkits/MikroTik-RouterOS/` and imports **no** LlamaIndex, so it stays
  independently testable and can be used as a plain library. The directory
  name contains a hyphen, so consumers import it through the alias
  `toolkits.mikrotik_routeros`, which `toolkits/__init__.py` registers.
- **Risk-classified write path** — every command is classified before it
  runs. Reads and cosmetic changes execute directly, a configuration change
  needs `confirm=True`, and a HIGH or CRITICAL change additionally needs an
  explicit human approval through the existing console prompt. A
  `confirm=True` flag is *not* a substitute for that approval, and a
  timeout is a refusal rather than an approval.
- **Management-path escalation** — a command that would disable, remove or
  rename the interface carrying the current session is escalated to
  `CRITICAL`, because it would cut the agent off from the router mid-change.
- **Multi-line guard** — a command containing a newline, `;`, `&&`, `||`, a
  pipe or a script block is refused with `MULTILINE_UNSUPPORTED` before it
  reaches the router. MikroTik's SSH server provides no pseudo-terminal, so
  such a command cannot be delivered — and it is a common prompt-injection
  vector.
- **Two SSH transports** — a stateless `exec` channel for reads (the
  router's error text arrives cleanly separated on stderr) and a stateful
  `session` channel for changes and for verbatim captures such as
  `/export`. `mode="auto"` picks between them.
- **Structured errors** — every tool returns a dictionary with `ok=False` and
  a machine-readable code (`AUTH_FAILED`, `HOST_KEY_MISMATCH`, `UNREACHABLE`,
  `TIMEOUT`, `COMMAND_REJECTED`, `MULTILINE_UNSUPPORTED`,
  `INTERACTIVE_INPUT_REQUIRED`, `SAFE_MODE_ACTIVE`, `PAGING_DETECTED`,
  `NOT_AUTHORIZED`, `PROMPT_NOT_DETECTED`, `UNKNOWN_TARGET`). A tool never
  raises.
- **Secret redaction** — the password and the key passphrase are held as
  `SecretStr` and are scrubbed from every tool result, every log line and
  every exception message.
- **Host-key verification** — the router's host key is checked against
  `known_hosts`; a changed key is a hard stop (`HOST_KEY_MISMATCH`), never
  an automatic retry.
- **Four interactive commands** — `\routers`, `\router-health <target>`,
  `\router-interfaces <target>` and `\router-backup <target>` work in the
  classic REPL and in the multi-window TUI, and are listed by `\help` under
  **Network Devices (MikroTik RouterOS)**.
- **Target configuration** — the routers are described in
  `mikrotik_targets.yaml`, with an annotated
  `mikrotik_targets.yaml.example`. The real file is in `.gitignore`, so
  credentials never reach the repository. `MIKROTIK_TARGETS`,
  `MIKROTIK_PASSWORD` and `MIKROTIK_KEY` provide the fallbacks.
- **Graceful degradation** — `asyncssh` and `pydantic` are optional. The
  agent boots without them, and the toolkit reports that it is unavailable
  instead of breaking the boot.

#### Interactive Help Command

- **`\help` command** — typing `\help` in any interactive session now lists
  every available command together with a short description, grouped by
  category (General, Statistics, HITL, Tools, Projects, Chat). It works in the
  multi-window TUI (rendered as Markdown in the document pane) and in the
  classic linear REPL of both `agent-torvalds.py` and `agent-torvalds-mw.py`.
- **Central command registry** — the new `components/command_registry.py`
  declares every interactive command exactly once, with its description,
  usage, category, aliases and the feature flag that gates it. Both
  orchestrators render their help screen from this registry, so the help
  output can no longer drift away from the real behaviour. The help screen is
  filtered by the features that are actually enabled in the current session
  (HITL runtime toggle, Chat History Manager, Project Manager, TUI-only
  commands), so it never advertises a command that would fail.
- **TUI keyboard cheat sheet** — the TUI help screen also lists the keyboard
  navigation shortcuts (Enter, PgUp/PgDn, Up/Down, Left/Right, Home/End,
  Ctrl+C).

#### Multi-Window Agent Parity

- **Multi-Window agent feature parity** — `agent-torvalds-mw.py` now matches the
  capabilities of the classic `agent-torvalds.py` orchestrator:
  - **Startup tool selection** — new `--select` flag with an interactive category
    picker; the agent now loads only the toolkits the user chose.
  - **Project Manager** — new `--auto-scan`, `--project-type` and `--project-path`
    flags, project context injection into agent memory, and the Project Manager
    toolkits included in the full tool collection.
  - **Chat History Manager** — the multi-user, multi-session chat history is now
    initialized at startup, with the `\chat-*` runtime commands available in both
    the TUI and the classic REPL.
  - **Runtime Prompt Injection** — the system prompt is now generated dynamically
    from the active project via `PromptTemplateEngine`, with `--no-prompt-injection`,
    `--prompt-template`, `--no-tool-recommendations` and `--force-project` flags.
  - **Callback manager propagation** — the callback manager is now passed to the LLM
    at creation time so LLM-level events reach the stats and HITL handlers.
- **Full tool parity** — `--full` mode now loads every toolkit (previously only
  OS and GitHub), matching the classic orchestrator exactly.

#### Multi-Window Agent Parity

- `components/tui/tool_selection_view.py` — TUI-friendly tool discovery, category
  rendering and interactive selection.
- `components/tui/project_manager_view.py` — Markdown renderers for the project
  list, project details, git status and workspace summary.
- `components/tui/chat_history_view.py` — Markdown renderers for the chat session
  list and active session details.
#### Graceful shutdown on a signal

- **The agent stops gracefully when it is told to.**  `components/signal_handler.py`
  — the `SignalHandler` class, exported from `components/__init__.py` and wired
  into `agent-torvalds.py`.  It catches **SIGINT** (Ctrl+C), **SIGQUIT**
  (Ctrl+backslash) and **SIGTERM** (`kill <pid>`), and runs an asynchronous
  shutdown sequence when there is an event loop and a synchronous one when
  there is not.  **SIGQUIT** can dump the session state for debugging, and an
  `atexit` handler covers a normal exit.  SIGKILL cannot be caught, so
  `kill -TERM` is the way to stop the agent.

#### Readline for every console prompt

- **Every console prompt gets line editing and a history.**  The
  `components/console_input_module.py` initialises Python's `readline` once at
  import time, so every `input()` in the application gets cursor movement with
  the arrow keys, multi-line editing, and the command history — and the
  history is written to a file in the user's home directory, so it survives
  between the sessions.

#### The persistent agent cache

- **A cache for the context that is not chat.**  `agent_cache_system.py` — a
  JSON-backed cache at `~/.cache/torvalds/agent_cache.json`, configurable
  through `TORVALDS_CACHE_PATH`.  It holds the operational and technical
  context that does not belong in the conversation: the state that has to
  survive between the sessions.

#### The on-demand tool retriever

- **The tools are loaded on demand.**  `agent_tool_retriever.py` — the tools
  are indexed in a LlamaIndex `ObjectIndex` and retrieved semantically from
  the user's query, instead of every one of them being loaded into the
  context window on every turn.

### Changed

#### The deployment scripts have a home of their own

- **The generated `.env` names the variables the agent actually reads.**
  The script wrote `TORVALDS_CHAT_MODEL` and `TORVALDS_OLLAMA_BASE_URL`;
  the agent reads `TORVALDS_MODEL` and `TORVALDS_OLLAMA_HOST`, so the
  `.env` it produced configured nothing.  `TORVALDS_EMBEDDING_MODEL` is
  still written, but only for reference — the retriever hard-codes
  `nomic-embed-text`.

- **`sudo env VAR=value cmd`, never `sudo VAR=value cmd`.**  sudo only
  honours a variable set on the command line when the `setenv` option is
  set in sudoers, or when the variable survives `env_reset`.  Neither is
  guaranteed, and when the variable is refused sudo aborts the whole
  command.  `sudo env VAR=value cmd` always works, because `env` runs
  *as root*, after sudo has already reset the environment.

- **`dpkg-query` instead of `dpkg -l`.**  `dpkg -l <name>` exits **0**
  for a package that dpkg knows about but that is not installed, so it
  could not be used to test for installation.

- **The virtual environment is repaired when it is incomplete.**  When
  `ensurepip` fails, `venv` leaves a half-built tree behind — a working
  `bin/python`, but no `bin/activate` and no `pip` — and that tree was
  never repaired.  The script now recreates it.

- **A single bad requirement cannot take the deployment down.**  pip
  builds every wheel before it installs anything, so one package that
  cannot be built left the environment completely empty.  The bulk
  install now falls back to installing the requirements one by one.

- **The log file is made writable before anything is redirected to it.**
  The default is `/var/log/torvalds-deploy.log`, which only root may
  create — and every `2>>"$LOG_FILE"` in the script is a redirection,
  and a redirection that cannot be opened means the command does not
  run at all.  An ordinary user would have silently skipped every pip
  and apt call.  The log now falls back to `~/.torvalds/logs/`, and the
  script says so.

- **`--help` and `--version` are queries.**  They write to **stdout**
  now, so `--help | less` shows something, and they no longer report a
  deployment summary.  The deployment itself keeps logging to stderr.

- **The script needs no Python of its own.**  A missing or too-old
  interpreter was a fatal error, and the script died before the phase
  that installs one — on exactly the machine it exists to fix.  It is a
  warning now, and the hard check runs after the packages are in.

#### The prompt in the debug log is readable

- **The empty lines are gone from the log.**  A system prompt that
  ends with a few newlines, or a document that separates its
  paragraphs with a run of blank lines, filled the log with empty
  records.  One empty line is kept — it is a paragraph break and it
  carries meaning — and a run of them is reduced to one.  A message
  that carries nothing but whitespace reads as `(empty)`.

- **The prompt in the debug log is readable, not a repr.**  The event
  consumer used to log the whole conversation as a Python repr - one
  enormous record of escaped object syntax, spread over dozens of
  lines.  It now logs the messages the way a person reads them: the
  role, and what the message carries.

  ```console
  EventConsumer._on_agent_input: prompt: 5 messages
  EventConsumer._on_agent_input:   [0] system: You are Torvalds, a technical AI assistant that interacts with the operating system.
  EventConsumer._on_agent_input:   [1] user: I want to improve debug message for context window
  EventConsumer._on_agent_input:   [3] assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)
  EventConsumer._on_agent_input:   [4] tool: output: ~
  ```

  A message shows its **text**, its **thinking** and the **tool calls**
  it requests.  A tool call carried in the OpenAI shape
  (`additional_kwargs["tool_calls"]`) is shown as well, so the log
  shows the same tools the model is shown.

- **The state handler holds the readable text.**  It used to hold
  `str(input)` - the repr of the whole conversation, megabytes of
  escaped object syntax for a long run.  It now holds the rendered
  messages.

#### The context guard is optional

- **The context guard is now opt-in.**  It used to be always on: every
  request was trimmed to the model's context window, and the user request
  was restored when the chat memory had trimmed it away.  The guard is
  **off by default** now, and the operator turns it on with
  `--context-guard-on` (or `TORVALDS_CONTEXT_GUARD=true`).

  The guard changes what the model is shown — it drops the oldest turns and
  shortens the ones that do not fit — so the decision belongs to the
  operator, not to the agent.

  | | Before | Now |
  |---|---|---|
  | The prompt | always trimmed to the context window | trimmed only with `--context-guard-on` |
  | `TORVALDS_CONTEXT_GUARD` | — | `true` turns the guard on, `false` (the default) leaves it off |
  | `HITLFunctionAgent.context_guard_enabled` | — | `False` (the default) |

  The guard itself did not change: `components/context_guard.py` is the same
  code, and so is the trimming in `components/hitl_agent.py`.  What changed
  is the switch around it — `take_step()` returns to the base implementation
  untouched when the guard stands down.

  **The trade-off is the price of the switch.**  With the guard off, a long
  tool-using run grows the prompt without bound; the Ollama server then
  truncates it from the front, which drops the user request, and the model
  template refuses to render a conversation without one ("No user query
  found in messages.").  The guard exists to prevent exactly that, so a
  run that reads a large file should be started with `--context-guard-on`.

#### The data analysis toolkit is a module

- **The data analysis toolkit is now a module under `toolkits/`.**  It was the
  **last** loose module at the project root, `agent_data_analysis_toolkit.py`,
  next to the other `agent_*.py` files, while every other toolkit already
  lived in a folder under `toolkits/`.  A toolkit is now one folder, like the
  MikroTik, the Shodan, the math, the Git, the GitHub, the OS, the Linux, the
  APT, the Windows, the database and the Excel one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_data_analysis_toolkit.py` | the whole toolkit — the operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/data-analysis-toolkit/operations.py` | — | the thirteen analysis operations, the **library half** |
  | `toolkits/data-analysis-toolkit/agent_data_analysis_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/data-analysis-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/data-analysis-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The operations carry **no** LlamaIndex import, so
  they stay usable — and testable — as a plain Python library; the adapter is
  the one module that knows about the agent framework, and it is imported on
  demand.  Importing the toolkit therefore never pulls LlamaIndex into the
  process.

  The library half is built on `pandas` — the DataFrame is the data model —
  and on `numpy`, which the pivot table uses to infer the numeric columns, and
  on the standard library, and on nothing else.  The layout contract pins that
  exact set, so a new dependency cannot slip in unnoticed.

- **The import path moved.**  The package lives in a hyphenated directory, so it
  is reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.data_analysis_toolkit import read_excel_to_df  # the library
  from toolkits.data_analysis_toolkit.agent_data_analysis_toolkit import get_all_tools  # the adapter
  ```

  The **two** call sites — `agent_tool_retriever.py` and
  `agent_tool_selection.py` — were updated.  As with the other toolkits under
  `toolkits/`, the adapter is now imported **behind a guard**, so a missing or
  broken toolkit degrades to "no tools" instead of a failed boot.  The data
  analysis toolkit was **mandatory** before this change; it is optional now.

  That is not a formality.  Before this change a missing `pandas` took the
  whole agent down with an unhandled `ModuleNotFoundError`; now the agent
  boots with 142 tools instead of 155.  The behaviour of the *tools* did not
  change — the operations still report a failure as a message string and never
  raise.

- **The logger's name moved.**  It was `agent_data_analysis_toolkit`, and it is
  now `toolkits.data-analysis-toolkit.operations` — that is what
  `logging.getLogger(__name__)` does when the module moves.  The adapter
  re-exports it, so the toolkit still logs through one logger.

#### The Excel toolkit is a module

- **The Excel toolkit is now a module under `toolkits/`.**  It used to be a
  single loose module at the project root, `agent_xlsx_toolkit.py`, next to the
  other `agent_*.py` files, while the features that were already modules lived
  in folders under `toolkits/`.  A toolkit is now one folder, like the
  MikroTik, the Shodan, the math, the Git, the GitHub, the OS, the Linux, the
  APT, the Windows and the database one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_xlsx_toolkit.py` | the whole toolkit — the operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/xlsx-toolkit/operations.py` | — | the nine Excel operations, the **library half** |
  | `toolkits/xlsx-toolkit/agent_xlsx_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/xlsx-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/xlsx-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The operations carry **no** LlamaIndex import, so
  they stay usable — and testable — as a plain Python library; the adapter is
  the one module that knows about the agent framework, and it is imported on
  demand.  Importing the toolkit therefore never pulls LlamaIndex into the
  process.

  The library half is built on `openpyxl` — the Excel file format is the file
  format, so an Excel operation is an Excel operation whether or not an agent
  framework is installed — and on the standard library, and on nothing else.
  The layout contract pins that exact set, so a new dependency cannot slip in
  unnoticed.

- **The import path moved.**  The package lives in a hyphenated directory, so it
  is reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.xlsx_toolkit import read_xlsx_file  # the library
  from toolkits.xlsx_toolkit.agent_xlsx_toolkit import get_all_tools  # the adapter
  ```

  The **two** call sites — `agent_tool_retriever.py` and
  `agent_tool_selection.py` — were updated.  As with the other toolkits under
  `toolkits/`, the adapter is now imported **behind a guard**, so a missing or
  broken toolkit degrades to "no tools" instead of a failed boot.  The Excel
  toolkit was **mandatory** before this change; it is optional now.

  That is not a formality.  Before this change a missing `openpyxl` took the
  whole agent down with an unhandled `ModuleNotFoundError`; now the agent
  boots with 146 tools instead of 155.  The behaviour of the *tools* did not
  change — the operations still report a failure as a message string and never
  raise.

- **The logger's name moved.**  It was `agent_xlsx_toolkit`, and it is now
  `toolkits.xlsx-toolkit.operations` — that is what `logging.getLogger(__name__)`
  does when the module moves.  The adapter re-exports it, so the toolkit still
  logs through one logger.

#### The database toolkit is a module

- **The database toolkit is now a module under `toolkits/`.**  It used to be a
  single loose module at the project root, `agent_db_toolkit.py`, next to the
  other `agent_*.py` files, while the features that were already modules lived
  in folders under `toolkits/`.  A toolkit is now one folder, like the
  MikroTik, the Shodan, the math, the Git, the GitHub, the OS, the Linux, the
  APT and the Windows one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_db_toolkit.py` | the whole toolkit — the operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/db-toolkit/operations.py` | — | the two SQL operations and the config loader, the **library half** |
  | `toolkits/db-toolkit/agent_db_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/db-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/db-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The operations carry **no** LlamaIndex import, so
  they stay usable — and testable — as a plain Python library; the adapter is
  the one module that knows about the agent framework, and it is imported on
  demand.  Importing the toolkit therefore never pulls LlamaIndex into the
  process.

  Unlike the OS, the Linux and the Windows toolkit, this toolkit's library
  half is **not** dependency-free.  It needs `psycopg2` and
  `mysql-connector-python` — the two drivers — and `PyYAML`, which reads the
  configuration file.  The layout contract pins that exact set, so a new
  dependency cannot slip in unnoticed.

- **The import path moved.**  The package lives in a hyphenated directory, so it
  is reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.db_toolkit import run_postgres_query  # the library
  from toolkits.db_toolkit.agent_db_toolkit import get_all_tools  # the adapter
  ```

  The **five** call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`,
  `agent_tool_retriever.py`, `agent_tool_selection.py` and
  `agent-torvalds-cpp.py` — were updated.  As with the other toolkits under
  `toolkits/`, the adapter is now imported **behind a guard**, so a missing or
  broken toolkit degrades to "no tools" instead of a failed boot.  The database
  toolkit was **mandatory** before this change; it is optional now.

  The guard is wider than `except ImportError` for this one toolkit, and it
  has to be: the toolkit reads `db_toolkit_config.yaml` **at import time**, so
  a missing or malformed configuration file raises as well.  The behaviour of
  the *tools* did not change — the operations still report a failure as a
  message string and never raise.

- **The logger's name moved.**  It was `agent_db_toolkit`, and it is now
  `toolkits.db-toolkit.operations` — that is what `logging.getLogger(__name__)`
  does when the module moves.  The adapter re-exports it, so the toolkit still
  logs through one logger.

#### The Windows toolkit is a module

- **The Windows PowerShell toolkit is now a module under `toolkits/`.**  It used to
  be a single loose module at the project root, `agent_windows_toolkit.py`, next
  to the other `agent_*.py` files, while the features that were already modules
  lived in folders under `toolkits/`.  A toolkit is now one folder, like the
  MikroTik, the Shodan, the math, the Git, the GitHub, the OS, the Linux and the
  APT one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_windows_toolkit.py` | the whole toolkit — the operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/windows-toolkit/operations.py` | — | the six PowerShell and system operations, the **library half** |
  | `toolkits/windows-toolkit/agent_windows_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/windows-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/windows-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The operations carry **no** LlamaIndex import, so they
  stay usable — and testable — as a plain Python library; the adapter is the one
  module that knows about the agent framework, and it is imported on demand.
  Importing the toolkit therefore never pulls LlamaIndex into the process.

  Like the OS and the Linux toolkit, this toolkit's library half is built on the
  **standard library alone** — `subprocess`, `logging` and `typing`.  The one
  thing that did not move verbatim is the module header: the `os` import of the
  original was never used by any of the operations, so it was dropped rather than
  carried along.

- **The import path moved.**  The package lives in a hyphenated directory, so it is
  reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.windows_toolkit import execute_shell_command  # the library
  from toolkits.windows_toolkit.agent_windows_toolkit import get_all_tools  # the adapter
  ```

  The four call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`,
  `agent_tool_retriever.py` and `agent_tool_selection.py` — were updated.  As with
  the other toolkits under `toolkits/`, the adapter is now imported **behind a
  guard**, so a missing or broken toolkit degrades to "no tools" instead of a failed
  boot.  The Windows toolkit was **mandatory** before this change; it is optional
  now.

- **The logger's name moved.**  It was `agent_windows_toolkit`, and it is now
  `toolkits.windows-toolkit.operations` — that is what `logging.getLogger(__name__)`
  does when the module moves.  The adapter re-exports it, so the toolkit still logs
  through one logger.

#### The APT toolkit is a module

- **The APT toolkit is now a module under `toolkits/`.**  It used to be a single
  loose module at the project root, `agent_apt_toolkit.py`, next to the other
  `agent_*.py` files, while the features that were already modules lived in folders
  under `toolkits/`.  A toolkit is now one folder, like the MikroTik, the Shodan,
  the math, the Git, the GitHub, the OS and the Linux one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_apt_toolkit.py` | the whole toolkit — the operations *and* the LlamaIndex adapter *and* the command-line interface | split in three |
  | `toolkits/apt-toolkit/operations.py` | — | the thirteen package, sudo and install operations, the **library half** |
  | `toolkits/apt-toolkit/agent_apt_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/apt-toolkit/cli.py` | — | the command-line interface, which used to be a `__main__` block |
  | `toolkits/apt-toolkit/__main__.py` | — | the `python -m toolkits.apt_toolkit` entry point |
  | `toolkits/apt-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/apt-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The operations carry **no** LlamaIndex import, so they
  stay usable — and testable — as a plain Python library; the adapter is the one
  module that knows about the agent framework, and it is imported on demand.
  Importing the toolkit therefore never pulls LlamaIndex into the process.

  Unlike the OS and the Linux toolkit, this toolkit's library half is **not**
  dependency-free.  It needs `rich` for the *console* password prompt, which is
  the default prompt method, and the repository's own
  `components.whiptail_password` for the *whiptail* one.  Both imports are
  deferred to the call and both degrade gracefully — a missing `rich` turns the
  console prompt into an error message, and a missing `components` falls back to
  the console prompt, which is the documented behaviour.

- **The import path moved.**  The package lives in a hyphenated directory, so it is
  reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.apt_toolkit import install_package          # the library
  from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools  # the adapter
  ```

  The four call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`,
  `agent_tool_retriever.py` and `agent_tool_selection.py` — were updated.  As with
  the other toolkits under `toolkits/`, the adapter is now imported **behind a
  guard**, so a missing or broken toolkit degrades to "no tools" instead of a failed
  boot.  The APT toolkit was **mandatory** before this change; it is optional now.

- **The command-line interface moved.**  It used to be an
  `if __name__ == "__main__":` block at the bottom of the module; it is
  `toolkits/apt-toolkit/cli.py` now, with the package as its entry point:

  ```bash
  python -m toolkits.apt_toolkit --show-method
  python -m toolkits.apt_toolkit --prompt-method whiptail
  ```

  The options, the output and the exit codes are unchanged.  The one line that
  had to change is the example in the help text, which named the file the
  interface used to live in.

- **The logger's name moved.**  It was `agent_apt_toolkit`, and it is now
  `toolkits.apt-toolkit.operations` — that is what `logging.getLogger(__name__)`
  does when the module moves.  The adapter re-exports it, so the toolkit still logs
  through one logger.

#### The Linux toolkit is a module

- **The Linux toolkit is now a module under `toolkits/`.**  It used to be a single
  loose module at the project root, `agent_linux_toolkit.py`, next to the other
  `agent_*.py` files, while the features that were already modules lived in folders
  under `toolkits/`.  A toolkit is now one folder, like the MikroTik, the Shodan,
  the math, the Git, the GitHub and the OS one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_linux_toolkit.py` | the whole toolkit — the shell operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/linux-toolkit/operations.py` | — | the six shell and system operations, the **library half** |
  | `toolkits/linux-toolkit/agent_linux_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/linux-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/linux-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The shell operations carry **no** LlamaIndex import, so
  they stay usable — and testable — as a plain Python library; the adapter is the
  one module that knows about the agent framework, and it is imported on demand.
  Importing the toolkit therefore never pulls LlamaIndex into the process.

  Like the OS toolkit, this toolkit's library half depends on the **standard
  library only** — `subprocess`, `os`, `logging` and `typing`.  There is no
  third-party dependency at all, so the shell operations work in any Python that
  exists.

- **The import path moved.**  The package lives in a hyphenated directory, so it is
  reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.linux_toolkit import execute_shell_command   # the library
  from toolkits.linux_toolkit.agent_linux_toolkit import get_all_tools  # the adapter
  ```

  The four call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`,
  `agent_tool_retriever.py` and `agent_tool_selection.py` — were updated.  As with
  the other toolkits under `toolkits/`, the adapter is now imported **behind a
  guard**, so a missing or broken toolkit degrades to "no tools" instead of a failed
  boot.  The Linux toolkit was **mandatory** before this change; it is optional now.

- **The logger's name moved.**  It was `agent_linux_toolkit`, and it is now
  `toolkits.linux-toolkit.operations` — that is what `logging.getLogger(__name__)`
  does when the module moves.  The adapter re-exports it, so the toolkit still logs
  through one logger.

#### The OS toolkit is a module

- **The OS toolkit is now a module under `toolkits/`.**  It used to be a single
  loose module at the project root, `agent_os_toolkit.py`, next to the other
  `agent_*.py` files, while the features that were already modules lived in folders
  under `toolkits/`.  A toolkit is now one folder, like the MikroTik, the Shodan,
  the math, the Git and the GitHub one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_os_toolkit.py` | the whole toolkit — the file-system operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/os-toolkit/operations.py` | — | the file-system operations, the **library half** |
  | `toolkits/os-toolkit/agent_os_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/os-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/os-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The file-system operations carry **no** LlamaIndex import,
  so they stay usable — and testable — as a plain Python library; the adapter is the
  one module that knows about the agent framework, and it is imported on demand.
  Importing the toolkit therefore never pulls LlamaIndex into the process.

  This toolkit is the odd one out in the series in a good way: its library half
  depends on the **standard library only** — `os`, `shutil`, `pathlib` and
  `platform`.  There is no third-party dependency at all, so the file-system
  operations work in any Python that exists.  It is the first toolkit of the series
  whose reusable half is dependency-free.

- **The import path moved.**  The package lives in a hyphenated directory, so it is
  reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.os_toolkit import pwd, ls, mkdir          # the library
  from toolkits.os_toolkit.agent_os_toolkit import get_all_tools  # the adapter
  ```

  The six call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`,
  `agent_tool_retriever.py`, `agent_tool_selection.py`,
  `agent-torvalds-cpp.py` and `test_callback_events_debug.py` — were updated.  As
  with the other toolkits under `toolkits/`, the adapter is now imported **behind a
  guard**, so a missing or broken toolkit degrades to "no tools" instead of a failed
  boot.  The OS toolkit was the last toolkit that was still *mandatory*.

- **The star import keeps working.**  `agent-torvalds-cpp.py` reaches the toolkit
  with `from toolkits.os_toolkit.agent_os_toolkit import *`, and the adapter
  re-exports the eleven operations, so the file reads the same as before.

#### The GitHub toolkit is a module

- **The GitHub toolkit is now a module under `toolkits/`.**  It used to be a single
  loose module at the project root, `agent_github_toolkit.py`, next to 18 other
  `agent_*.py` files, while the features that were already modules lived in folders
  under `toolkits/`.  A toolkit is now one folder, like the MikroTik, the Shodan, the
  math and the Git one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_github_toolkit.py` | the whole toolkit — the GitHub operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/github-toolkit/operations.py` | — | the GitHub operations, the **library half** |
  | `toolkits/github-toolkit/agent_github_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/github-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/github-toolkit/tests/` | — | the module-local tests |

  The split is the point.  The GitHub operations carry **no** LlamaIndex import, so
  they stay usable — and testable — as a plain Python library; the adapter is the one
  module that knows about the agent framework, and it is imported on demand.
  Importing the toolkit therefore never pulls LlamaIndex into the process.

  The library half keeps exactly one third-party dependency: `requests`, the HTTP
  client the GitHub REST API is called through.  LlamaIndex is *not* on that list —
  that is the whole point of the split.

- **The import path moved.**  The package lives in a hyphenated directory, so it is
  reached through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.github_toolkit import github_create_pull_request   # the library
  from toolkits.github_toolkit.agent_github_toolkit import get_all_tools  # the adapter
  ```

  The four call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`,
  `agent_tool_retriever.py` and `agent_tool_selection.py` — were updated.  As with
  the other toolkits under `toolkits/`, the adapter is now imported **behind a
  guard**, so a missing or broken toolkit degrades to "no tools" instead of a failed
  boot.

#### The Git toolkit is a module

- **The Git toolkit is now a module under `toolkits/`.**  It used to be a single loose
  module at the project root, `agent_git_toolkit.py`, next to 19 other `agent_*.py` files,
  while the features that were already modules lived in folders under `toolkits/`.  A toolkit
  is now one folder, like the MikroTik, the Shodan and the math one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_git_toolkit.py` | the whole toolkit — the Git operations *and* the LlamaIndex adapter | split in two |
  | `toolkits/git-toolkit/operations.py` | — | the Git operations, the **library half** |
  | `toolkits/git-toolkit/agent_git_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/git-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/git-toolkit/tests/` | `tests/test_git_toolkit.py` | the module-local tests |

  The split is the point.  The Git operations carry **no** LlamaIndex import, so they stay
  usable — and testable — as a plain Python library; the adapter is the one module that
  knows about the agent framework, and it is imported on demand.  Importing the toolkit
  therefore never pulls LlamaIndex into the process.

  The library half keeps exactly one third-party dependency: `pygit2`, the binding to
  `libgit2` the toolkit is built on.  LlamaIndex is *not* on that list — that is the
  whole point of the split.

- **The import path moved.**  The package lives in a hyphenated directory, so it is reached
  through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.git_toolkit import git_get_status, git_commit        # the library
  from toolkits.git_toolkit.agent_git_toolkit import get_all_tools    # the adapter
  ```

  The six call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`, `agent-torvalds-cpp.py`,
  `agent_tool_retriever.py`, `agent_tool_selection.py` and
  `test_callback_events_debug.py` — were updated.  As with the other toolkits under
  `toolkits/`, the adapter is now imported **behind a guard**, so a missing or broken
  toolkit degrades to "no tools" instead of a failed boot.

  The C++ orchestrator uses a star import of the adapter, so the adapter re-exports the
  27 Git functions; `from toolkits.git_toolkit.agent_git_toolkit import *` still brings in
  `git_get_latest_commit`, `git_init_repo` and the rest.

#### The math toolkit is a module

- **The math toolkit is now a module under `toolkits/`.**  It used to be a single loose
  module at the project root, `agent_math_toolkit.py`, next to 20 other `agent_*.py` files,
  while the features that were already modules lived in folders under `toolkits/`.  A toolkit
  is now one folder, like the MikroTik and the Shodan one.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_math_toolkit.py` | the whole toolkit — the mathematics *and* the LlamaIndex adapter | split in two |
  | `toolkits/math-toolkit/operations.py` | — | the mathematics, the **library half** |
  | `toolkits/math-toolkit/agent_math_toolkit.py` | — | the **adapter**, the only LlamaIndex-dependent module |
  | `toolkits/math-toolkit/__init__.py` | — | the public API surface |
  | `toolkits/math-toolkit/tests/` | `tests/test_math_toolkit.py` | the module-local tests |

  The split is the point.  The mathematics carries **no** LlamaIndex import, so it stays
  usable — and testable — as a plain Python library; the adapter is the one module that
  knows about the agent framework, and it is imported on demand.  Importing the toolkit
  therefore never pulls LlamaIndex into the process.

- **The import path moved.**  The package lives in a hyphenated directory, so it is reached
  through the alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.math_toolkit import add, multiply, evaluate_rpn            # the library
  from toolkits.math_toolkit.agent_math_toolkit import get_all_tools       # the adapter
  ```

  The six call sites — `agent-torvalds.py`, `agent-torvalds-mw.py`, `agent-torvalds-cpp.py`,
  `agent_tool_retriever.py`, `agent_tool_selection.py` and
  `test_callback_events_debug.py` — were updated.  As with the other toolkits under
  `toolkits/`, the adapter is now imported **behind a guard**, so a missing or broken
  toolkit degrades to "no tools" instead of a failed boot.

#### The legacy chat memory is gone

- **`--no-chat-history` means something different now.**  It used to select the legacy
  single-session memory.  It now means *persist nothing*: the chat history manager is not
  started and the conversation runs in an in-memory store.  The flag stays — a user-facing flag
  must not disappear — and it prints a deprecation warning.

- **`TORVALDS_TOKEN_LIMIT` now sizes the in-memory buffer.**  It was the legacy buffer's
  limit.  The manager still uses the user's own `chat_token_limit` setting; the variable is
  the limit for the in-memory fallback, and its default is still `5000`.

- **`TORVALDS_CHAT_KEY` still works, for one more release.**  The migration hook in the
  manager is unchanged: when the variable is set, the General session points at the old flat
  history so pre-existing messages stay reachable.

#### The chat history survives a database outage

- **The message bodies are still the weaker half of the degradation.**  The
  message backend falls back to an *in-memory* store, so the metadata
  survives a restart while the database is down but the messages
  themselves do not.  That is unchanged — the metadata layer was the
  half that had no fallback at all, and it is the half that had to be
  fixed before the legacy path could be removed.

#### The user can finally change their own settings

- **`token_limit` is now `chat_token_limit` — the setting says whose
  tokens it limits.**  The name said the unit but not the scope, and
  the scope is the interesting part: the codebase used `token_limit`
  for at least three other things (the model's `context_window`, the
  legacy `TORVALDS_TOKEN_LIMIT`, and the dead `TOKEN_LIMITS` constant
  in both orchestrators).  The setting governs the number of
  *chat-history* tokens the agent keeps in the memory buffer of the
  active session, and it now says so.  The rename is backwards
  compatible in three places:

  - **The database.**  `CustomDBConnector.connect()` renames the column
    in place (`ALTER TABLE users RENAME COLUMN token_limit TO
    chat_token_limit`), so an existing database keeps its values and
    needs no manual migration step.  The migration is idempotent and
    never fatal — a failure is logged as a warning, because a chat
    history that cannot be migrated is a smaller problem than a chat
    history that cannot be reached.
  - **The Python API.**  `User.token_limit` survives as a deprecated
    property (getter *and* setter), `User(token_limit=…)` still works as
    a constructor keyword, `User.to_dict()` carries both keys, and
    `User.from_dict()` accepts either.
  - **The command.**  `\chat-user set token_limit 12000` still works;
    `token_limit` is a registered alias of the canonical key, and the
    reply always names the canonical key.

  The proposal, with the alternatives that were considered and why
  they were rejected, is in
  `investigate/chat-manager-user-settings/PROPOSAL_chat_token_limit.md`.
  `TORVALDS_TOKEN_LIMIT` was **not** renamed: it configures the legacy
  compatibility buffer, whose removal is a separate phase.

#### The toolkits own their adapters

- **The Shodan toolkit dropped its `src/` level — and its nested package
  directory.** The importable package moved from
  `toolkits/shodan-toolkit/src/shodan_toolkit/` to
  `toolkits/shodan-toolkit/`: the toolkit directory *is* the package now,
  so the toolkit folder has the same shape as the MikroTik one — the
  package, the tests and the examples side by side instead of the package
  being buried one or two levels down. The import name is unchanged —
  `shodan_toolkit` for a standalone install, `toolkits.shodan_toolkit`
  through the alias — and the toolkit's own `pyproject.toml` now maps the
  package explicitly, because the directory name contains a hyphen.
- **The agent adapters now live inside their toolkit.** `agent_mikrotik_toolkit.py`
  moved from the project root to `toolkits/MikroTik-RouterOS/`, and
  `agent_shodan_toolkit.py` to
  `toolkits/shodan-toolkit/`. A toolkit is now one
  folder: the library half, the adapter that exposes it to the agent, and
  the tests — with nothing about the feature left behind at the project
  root, which carried 22 loose `agent_*.py` modules.
- **The adapters are submodules of their toolkit package**, so they are
  reached through the alias the toolkit already had:
  `from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import get_all_tools`
  and `from toolkits.shodan_toolkit.agent_shodan_toolkit import get_all_tools`.
  The package directory names contain a hyphen, so this is the only spelling
  a plain `import` statement can use.
- **The adapters pull the core package in with a relative import**
  (`from . import ...`). The adapter is now part of the package it adapts,
  so it always works with the very same module objects the package exports —
  and the Shodan adapter keeps working when the toolkit is installed as a
  standalone distribution, where no `toolkits` package exists at all.
- **`import toolkits` still does not import LlamaIndex.** The adapters are
  the only LlamaIndex-dependent modules of a toolkit, so the alias shim no
  longer publishes them eagerly; they are imported on demand, by whoever
  needs them. The rule "the library half has no LlamaIndex dependency" is
  unchanged — it is now checked behaviourally as well as statically.

#### The HITL question is asked as the question it is

- **The question bank grows from 17 to 23 cases** — five of them catch the
  defect above, one of them guards the fix against being too broad (a
  relative clause must stay a yes/no question).
- **The presentation harness reports 9 invariants** instead of 8; the new
  one checks that a decorated question is asked as the open question it is.
- **New diagnostic**: `investigate/hitl-questions-issue/diag_decorated_question.py`
  — 8 mis-classifications before the fix, 0 after.

#### Shodan Toolkit

- `toolkits/__init__.py` now registers a second alias,
  `toolkits.shodan_toolkit`, next to the existing
  `toolkits.mikrotik_routeros`. Both are registered only if the package is
  importable, so `import toolkits` never fails when an optional toolkit is
  absent.
- `agent_tool_retriever.py` gained an `include_shodan_tools` flag (on by
  default), `agent_tool_selection.py` discovers the Shodan tools for the
  startup menu, and both orchestrators (`agent-torvalds.py`,
  `agent-torvalds-mw.py`) load them in the full-inventory mode.
- `docs/shodan-toolkit.md` gained a **Selecting the tools** section: what
  the Security entry in the menu looks like, how to pick it, and how the
  four write-capable tools join it after the opt-in.
- `pytest.ini` puts `toolkits/shodan-toolkit/src` on the path and adds the
  toolkit's own test suite to `testpaths`, so the 133 upstream tests run
  against the in-repository copy - the same code the adapter loads.
- **Every Shodan test now lives under `toolkits/shodan-toolkit/tests/`.**
  The adapter suite moved there from `tests/test_shodan_toolkit.py` and is
  now `tests/test_agent_adapter.py`, so the whole feature - the library and
  its agent integration - is tested from one directory. The moved file
  skips itself when the toolkit is used as a standalone library, because
  the agent-side modules it needs do not exist there.
- **`toolkits/shodan-toolkit/conftest.py`** — puts the toolkit's `src/`
  directory on `sys.path`. pytest picks the nearest configuration file when
  it is pointed at a path inside the toolkit, and `pyproject.toml` is the
  one it finds; without this the suite could only be run from the
  repository root. The upstream files themselves are untouched, so
  `git subtree pull` keeps working.

#### Local LLM setup (Ollama)

- The chat model (`agent-torvalds.py`, `agent-torvalds-mw.py`) and the
  embedding model (`agent_tool_retriever.py`) now use the resolved Ollama
  endpoint instead of the hard-coded `http://localhost:11434`. The default
  behaviour is unchanged.

#### HITL: no timeout by default

- Every HITL default is now `-1` instead of `30`: the orchestrators
  (`agent-torvalds.py`, `agent-torvalds-mw.py`), the timeout manager, the
  console and whiptail input modules, the HITL event classes, the agent
  step, the event consumer, the TUI state bridge, the MikroTik approval
  prompt and the project-manager disambiguation prompt.
- The HITL status output shows `Timeout: none` instead of `Timeout: 30s`.

#### Agent Cache Zero Stats Fix

- **Token usage extraction** — the new `components.stats_handler._extract_usage()`
  helper probes several provider response shapes (`raw["usage"]`,
  `raw["usage_metadata"]`, the raw Ollama `prompt_eval_count`/`eval_count` format,
  `additional_kwargs["usage"]` and the `usage`/`usage_metadata` attributes) instead
  of only reading `raw["usage"]`.
#### The commit history carries no Claude co-author trailer

- **The commit history carries no Claude co-author trailer.**  The Claude
  co-author attribution was found, and the history was rewritten to remove it.
  No commit in `master` names Claude as a co-author; the two
  `Co-authored-by` trailers that remain name the project's own authors.  The
  commit SHAs that the rewrite made stale were refreshed in the documentation
  that quoted them.
#### The wiki is a submodule of this repository

- **The wiki is a submodule of this repository.**  The nine wiki pages live in
  `agent-torvalds.wiki.git` and are now carried at `wiki/`, so a clone of this
  repository can bring the documentation with it: `git clone
  --recurse-submodules` fetches the pages, and a plain clone leaves the
  directory empty.  The pages are still published from the wiki repository
  itself, and the pages link to each other by their wiki names, which resolve
  on the wiki site and inside the submodule.

### Fixed

#### The deployment scripts have a home of their own

- **An unknown option exits 2, not 0.**  The script logged the error,
  printed the help and exited **0** — a deployment that was given a bad
  flag and reported success.

- **A non-interactive run can obtain sudo by itself.**  sudo keys its
  cached timestamp on the terminal, so a cache created by the calling
  shell is not visible to a script, and the script could never bootstrap
  itself.  It now establishes its own timestamp, from `SUDO_PASSWORD` or
  `SUDO_PASSWORD_FILE`.

- **`python3.-venv` is no longer requested.**  The version-specific
  venv module was added to the apt list unconditionally, and with an
  empty `PYTHON_MINOR` — which is what a machine without Python has —
  apt-get failed on the whole batch.

#### The APT toolkit is a module

- **`python -m <toolkit>` works again.**  The alias shim published *every*
  submodule of a toolkit under the toolkit's alias — including the `__main__`
  modules.  A `__main__` module is meant to be executed, not imported: publishing
  it puts it in `sys.modules`, and `runpy` then refuses to execute it.

  ```
  RuntimeWarning: 'toolkits.shodan_toolkit.__main__' found in sys.modules
  after import of package 'toolkits.shodan_toolkit', but prior to execution
  of 'toolkits.shodan_toolkit.__main__'
  ```

  The shim skips the `__main__` modules now, the way it already skipped the agent
  adapters.  This had broken the **Shodan** toolkit's `python -m
  toolkits.shodan_toolkit` long before the APT toolkit had an entry point at
  all.

- **The dead `collect_ignore` option in `pytest.ini` is gone.**  It named
  `agent_apt_toolkit.py`, and it was meant to keep pytest from collecting the
  toolkit's `test_sudo_password` operation as a test.  `collect_ignore` is **not**
  a pytest ini option — it belongs in a `conftest.py` — so pytest warned
  "Unknown config option: collect_ignore" on every run and ignored it.  The
  source module is not collected because it is not in `testpaths`, which is the
  protection every other toolkit relies on.

#### The Linux toolkit is a module

- **The split-verification check no longer depends on a branch called
  `master`.**  It asked git for the committed original by name
  (`git show master:agent_linux_toolkit.py`), and the test that drove it
  hard-coded the same name.  That works in a clone and it fails in CI: a
  CI checkout is a detached HEAD of the merge commit with a shallow
  history, so there is no `master` branch to ask, and the build went red
  with ten new failures — all of them in the check, none in the toolkit.

  The check now **finds** the original instead of assuming where it is: a
  named ref that still carries the file (`master`, `origin/master`,
  `main`, `origin/main`), and otherwise the **parent of the commit that
  deleted it** — which is exactly the state the file was in when it was
  removed.  The second step is what makes the check work in CI, and it is
  the more precise definition anyway.  The workflow now checks the
  repository out with `fetch-depth: 0`, because a shallow history cannot
  answer the question at all.

  A check that only runs where its author sits is not a check: it ran
  green on the developer's machine for the whole of the change, and the
  build found it in two minutes.

#### The Git toolkit is a module

- **The Git toolkit's own behaviour did not change.**  All 27 functions, every docstring and
  the error contract — a failure is reported as `False`, as `{"success": False, "error": ...}`
  or as an `"Error: ..."` string, never raised — moved verbatim.  The toolkit's 56 tests
  pass before and after, and the CI gate reports no new failure.

#### The user can finally change their own settings

- **A changed chat-token limit now reaches the live memory buffer.**
  The buffer caches the limit it was built with, and the cache was
  dropped only by `switch_session()` and `clear_messages()` — so a
  changed limit was inert until the operator switched sessions.  The
  settings API drops the cache itself, and a new limit is live on the
  next turn.
- **`get_memory_buffer()` no longer silently drops its override.**  The
  early return happened *before* the argument was read, so every call
  after the first one was ignored.  The buffer is now rebuilt when the
  effective limit differs from the one it was built with.

#### The toolkits own their adapters

- **A broken toolkit can no longer break the agent boot.** The adapters
  moved behind the toolkit package, so a package that fails to import
  takes the adapter with it. The two orchestrators now import them behind
  a guard and degrade to "no tools", the way the retriever and the
  `--select` menu already did.

#### A timeout the model can see

- **A timeout is no longer reported to the model as if the human had
  answered.** The operator's rule: *"-1 means stop and wait; a finite
  timeout means wait, and when it expires act on your own judgement."* The
  machinery already honoured it — the step waits forever with `-1` and
  continues when a finite timeout expires — but the model was fed the
  fallback answer as if the human had said it. With the shipped default (no
  fallback answer) it was fed an **empty turn**, which for a yes/no question
  is indistinguishable from a "no": the agent refused to act, the exact
  opposite of the rule. The model now reads *"No human response — the 1s wait
  ended without an answer. The question was not answered; act on your own
  judgement."* The fallback answer stays in the timeout log, for the audit
  trail.

#### The HITL question is asked as the question it is

- **A quoted, emphasised or labelled question is no longer prompted as a
  yes/no question.** The operator reported that a question with three choices
  was answered with `[y/N]`: the agent had written the question as
  `question: 'Which one should I use?'`, and the quotes and the label kept
  the "which" out of the head of the question — so the "should I" *inside* it
  turned the question into a confirmation. The question is now read through
  its **core** — without the quotes, the Markdown emphasis and the label —
  and the operator reads it without them too.
- **A question whose question word heads a clause is not a yes/no question.**
  "I found three options, so which one should I use?" asks for a choice: the
  "should I" sits in a subordinate clause. A wh-word in front of the offer
  now means the offer is not what the question asks. The rule stays narrow:
  a wh-word *after* the offer is a relative clause, not a question word, so
  "Should I use the tool which deletes the branch?" is still a confirmation.
- **The HITL history records the type the operator was asked for.** A menu
  question was recorded as a yes/no question, because the options were not
  passed to the type detection.

#### Git toolkit against pygit2 1.20

- **The git toolkit works again with the installed pygit2.** Every one of
  its 37 tests failed against pygit2 1.20, because the toolkit was written
  against an older API. Ten API changes were adapted:
  `Index.add()` takes one path per call (`Index.add_all()` stages
  everything); `Config.has_key()` and `Config.get()` are gone (the mapping
  interface — `key in config` and `config[key]` — replaces them);
  `Config.set_multivar()` needs a regex, so a single value is set through
  `config[key] = value`; `Repository.create_remote()` moved to
  `repo.remotes.create()`; the diff moved from the index to the repository
  (`repo.diff(target, cached=True)` compares the index with a target,
  `repo.diff()` compares the working tree with the index);
  `Diff.diffstring` is gone (the diff is iterable and yields one `Patch`
  per file, each with its own `text`); `Oid.hex` is gone (`str(oid)`);
  `Commit.short_id` is a string now, not an `Oid`; iterating the branch
  collections yields the names, not objects; `Repository.graph_ahead_behind()`
  is now `Repository.ahead_behind()`.
- **The second commit in a repository was silently refused.** The guard
  that checks whether there is anything to commit was inverted — it
  reported "no staged changes" exactly when there were staged changes, so
  `git_commit()` returned `False` for every commit after the first one in a
  repository. The guard now asks the right question.
- **`git_log_compare()` no longer reports the whole history.** The
  ahead/behind lists were supposed to stop at the shared history, but the
  filter was never applied — the exception that was meant to skip the
  shared commits was swallowed, so both branches reported every commit they
  had. The walk now stops at the first commit the other branch also
  contains.
- **`git_pull()` no longer reports success for a pull that never
  happened.** A missing remote was skipped silently and the tool answered
  "Fetch completed". It now fails with "Remote 'origin' does not exist".
- **`git_branch_rename()` works again.** pygit2 1.20 removed
  `Branches.rename()`; the reference itself is renamed now — the new one is
  created, HEAD is pointed at it, and the old one is dropped.

#### HITL question presentation

- **The question is a question, not the whole answer** — the Human-in-the-Loop
  used the **entire assistant message** as the question. A 3 180-character
  investigation report became a 3 180-character question, and the operator
  was asked to answer a report. The question is now split out of the
  message (`components/hitl_question.py`), and the report around it travels
  in the `AgentQuestionEvent.context` field, which the consumer renders
  above the question.
- **The input type follows the question, not the answer** — the type was
  guessed from the whole message with a substring match, so a report that
  merely mentioned *"secret redaction"* turned the question into a masked
  `Enter password: ` prompt and the operator never saw the question at all.
  The type is now derived from the extracted question, on word boundaries:
  a question that *asks for* a secret is a password question, a question
  that *mentions* one is not.
- **The question is rendered exactly once** — the consumer printed the
  question and then handed the same text to the input module, which printed
  it again. The consumer now owns the rendering and the input module only
  ever receives a short prompt (`[Y/n]`, `Your response: `,
  `Enter password: `, `Select option [1]: `).
- **An empty answer is a timeout, not a "no"** — pressing Enter was recorded
  as an explicit "no", so the operator could not tell the two apart. The
  input modules gained `confirm_with_status()` / `prompt_with_status()`,
  and the empty answer is now reported as `timeout=True`.
- **A rephrased question is not asked twice** — the re-ask guard compared
  the question text exactly, so "Shall I create the branch X?" followed by
  "Should I create the branch X?" asked the same thing again. The guard now
  compares the *normalised* question (case, Markdown, punctuation and the
  interrogative frame are dropped).
- **A question that ends with a code span is detected** — the question-mark
  pattern could not match `Shall I create the branch `feature/sqitch`?`, so
  the agent never asked it.
- **A question is detected once, not once per workflow replay** — the
  workflow replays the suspended step when the answer arrives, so the
  "HITL question detected" line was logged twice for one question. The
  question identity now reports whether the question is new.

#### Shodan Toolkit

- **The Security summary no longer contains a raw verb** — the menu
  describes a category with the canonical actions of its tools
  (`Actions: discover, inspect, diagnose, execute`). `shodan_myip` ("Get the
  public IP address Shodan sees for this machine") did not match any
  action pattern and fell through to the raw first word, so the summary
  read `Actions: discover, inspect, diagnose, get, execute`. The pattern
  now maps it to `inspect`, like the other lookups.
- **The Shodan tests no longer depend on the operator's environment** —
  `TORVALDS_SHODAN_ALLOW_MUTATING=1` enables the write-capable tools in
  every load path, so a developer who had it exported saw three adapter
  tests fail. The variable is now removed for the duration of the suite,
  and the tests that exercise the opt-in set it themselves.

#### HITL: no timeout by default

- **The agent no longer gives up on the user** — the Human-in-the-Loop
  timeout now defaults to **`-1`, which means "no timeout"**. The agent
  waits for the answer constantly, for as long as the human needs, instead
  of falling back to the default answer after 30 seconds. The value can be
  set to a positive number (`--hitl-timeout 60` or
  `TORVALDS_HITL_TIMEOUT=60`) to restore a deadline.
- **`-1` is no longer mangled on the way to the prompt** — the value used
  to be corrupted at four different places, each of which would have
  turned "wait forever" into a short wait:
  - `asyncio.wait_for()` treats every value `<= 0` as *expire
    immediately*, so the raw `-1` was passed straight through by the
    timeout manager and both input modules. They now translate it into
    the `None` that asyncio understands as "wait indefinitely".
  - `HumanLoopHandler` clamped the value with `max(1, default_timeout)`,
    which turned `-1` into 1 second.
  - The agent step padded the timeout with a 5 second grace period
    (`timeout=timeout + 5`), which would have turned `-1` into a 4 second
    deadline. The grace period now only applies to a *finite* timeout.
  - The TUI counted down from a negative value and displayed `0s`; it now
    shows no countdown at all.
- **`-1` is accepted as a valid timeout** by `AgentQuestionEvent` and
  `TimeoutManager` instead of being rejected as "negative". Values below
  `-1` are still rejected as typos.

#### MikroTik RouterOS Toolkit

- **The MikroTik tools were missing from the startup tool selection menu.**
  `agent_tool_selection._discover_tools()` — the single function that
  builds the `--select` menu — never imported the MikroTik adapter, so the
  eight tools (category **Network**) were absent from the menu even though
  the toolkit was fully wired into the retriever and into both
  orchestrators. The operator could not see or select the capability.
  The adapter is now imported by the discovery function, and the **Network**
  category appears in the menu of the classic REPL (`--select`) and of the
  multi-window TUI (`\tools`, `\tool-select`).
- **The menu's action summary misread the RouterOS paths.** The summary is
  built by matching the leading verb of a tool description, and the
  fallback (the lowercased first word) produced the useless labels
  `list, check, run, filter, export, get`. In addition, the RouterOS path
  `/ip/firewall/filter` in the config tool's description was matched by
  the data-analysis `filter` pattern, which reported the category as
  doing data filtering. Dedicated **Network** patterns now map the eight
  tools onto `discover, diagnose, execute, inspect, backup`.

#### Interactive Help Command

- **Classic REPL project commands** — `agent-torvalds.py` never dispatched the
  `\projects` / `\project-info` / `\project-status` / `\project-summary`
  commands, even though the multi-window agent did. The classic orchestrator
  now handles them, which keeps both agents behaviourally identical.
- **Unbound `hitl_response` in the classic REPL** — in `agent-torvalds.py` the
  variable was read outside the `if runtime_toggle_enabled:` block that
  assigns it, raising `UnboundLocalError` whenever the runtime toggle was
  disabled (`--hitl-no-runtime-toggle` or `TORVALDS_HITL_RUNTIME_TOGGLE=false`).
- **Missing HITL commands in the TUI** — the multi-window TUI only handled
  `\toggle-hitl` and `\hitl-status`. It now routes every HITL command
  (`\hitl-on`, `\hitl-off`, `\hitl-help`) through the runtime toggle.

#### Agent Cache Zero Stats Fix

- **Zero request statistics** — the persisted `request_stats` entries in the agent
  cache always recorded `llm_calls`, `total_tokens`, `prompt_tokens`,
  `completion_tokens` and `tool_call_count` as `0`, while only `duration_ms` was
  correct. Three independent root causes were fixed:
  - **Callback manager wiring** — `llama_index.core.llms.callbacks.llm_chat_callback`
    resolves the callback manager from the **LLM instance**, not from the agent.
    `FunctionAgent` is a Pydantic model with no `callback_manager` field, so
    `FunctionAgent(callback_manager=...)` and `agent.run(callback_manager=...)` are
    silently discarded and the stats handler never received a single event. The new
    `components.stats_handler.bind_callback_manager()` installs the manager on the
    LLM, where the events are actually delivered.
  - **Tool call accounting** — `CBEventType.FUNCTION_CALL` is never emitted by
    llama-index 0.14.x, so tool calls are now sourced from the workflow event
    stream. `EventConsumer` feeds them into the handler via the new
    `begin_tool_call()` / `end_tool_call()` API, keyed by `tool_id` so concurrent
    calls to the same tool stay correctly paired.
  - **Numeric normalisation** — `save_request_stats()` wrote `None` for missing
    numeric fields, which made `get_stats_summary()` raise `TypeError` during
    aggregation and degrade the summary to `{"error": ...}`. All numeric fields are
    now normalised through `agent_cache_system._as_number()`.

#### Multi-Window Agent Parity

- **TUI input reader** — keystrokes typed in a burst were truncated to the first
  character because `sys.stdin.read(1)` blocks until a full line arrives. The
  reader now consumes the raw terminal file descriptor and buffers the remainder,
  so slash commands such as `\projects` are received in full.

### Removed

#### The legacy chat memory is gone

- **`agent_chat_memory.py` is deleted.**  The module was the compatibility layer over the
  `chat_manager` package: it kept the historical `get_chat_store()` / `get_chat_memory()` /
  `chat_memory` API alive and fell back to a legacy single-key buffer when the manager was
  unavailable.  The manager is now the only source of a chat memory buffer, and the in-memory
  buffer is the last resort rather than a parallel implementation.

  The legacy path had exactly one job left — keeping the agent's memory alive when the
  database was down — and the local SQLite fallback does that job properly now, with the
  sessions intact instead of as one flat key.

  | Path | Was | Now |
  |------|-----|-----|
  | `agent_chat_memory.py` | the whole module (273 lines) | deleted |
  | `agent-torvalds.py`, `agent-torvalds-mw.py` | `import agent_chat_memory` · `agent_chat_memory.get_chat_memory()` | `from chat_manager.startup import get_memory_buffer` · `get_memory_buffer()` |
  | `agent-torvalds-cpp.py` | `agent_chat_memory.chat_memory` | `get_memory_buffer()` |
  | both orchestrators | `TOKEN_LIMITS` | deleted — it was defined and never read |

### Security

#### Shodan Toolkit

- **Read-only by default** — the four tools that change account state or
  consume credits (alerts, scans, downloads) are **not** exposed. The
  opt-in is a single environment variable, `TORVALDS_SHODAN_ALLOW_MUTATING=1`,
  which the adapter reads itself, so every load path (the retriever, the
  `--select` menu and both orchestrators) behaves identically.
- **The raw-command guard** — `shodan_raw` can run any CLI subcommand, so
  the toolkit screens the subcommand and refuses the ones that change
  state, consume credits or write files. It therefore cannot be used to
  bypass the read-only split.
- **No shell** — the `shodan` CLI is executed as an argument vector, never
  through a shell, so a query string cannot become a shell command. The API
  key is never passed on the command line either, so it cannot leak into a
  log line or an error message.

### Documentation

#### Local LLM setup (Ollama)

- **README.md - "Local LLM Setup (Ollama)"** - a step-by-step guide to
  running the agent against a local Ollama instance: installing Ollama on
  Linux, macOS, Windows and Docker, verifying the server, pulling the chat
  and embedding models, pointing the agent at the model and starting the
  agent. It also carries a hardware-sizing table and a troubleshooting
  matrix.
- **`docs/ollama-setup.md`** - the long form of the same guide, with the
  agent/Ollama architecture, the complete environment-variable reference,
  the model catalogue, a three-step verification of the whole chain
  (`/api/generate`, `/api/embeddings` and the agent's own client) and the
  housekeeping commands (`ollama ps` / `stop` / `rm`).
- The installation steps in the README now include the Ollama install and
  the two `ollama pull` commands, and Ollama moved from "optional" to
  **required** in the prerequisites - the agent has no cloud fallback.

#### MikroTik RouterOS Toolkit

- **Module README** — `toolkits/MikroTik-RouterOS/README.md` documents the
  reusable core package: the layout, the import contract (and why the hyphen
  forces the `toolkits.mikrotik_routeros` alias), the public API, the risk
  classifier and its rule order, the safety model, the two transports, the
  uniform result shape, the error taxonomy, the configuration reference, the
  library-only usage, the security notes and the limitations.
- **Root README** — the module README is linked from the new *Module
  documentation* index, from the MikroTik section and from the configuration
  section. The *Project Structure* tree now lists the `toolkits/` package,
  the `agent_mikrotik_toolkit.py` adapter and
  `mikrotik_targets.yaml.example`, all of which were missing.
#### The design proposals the work was built from

- **`docs/proposals/` holds the design documents the work was built from** —
  the agent cache system, the extended logging and statistics, the
  interactive APT package installation, the LlamaIndex memory implementation,
  the on-demand tool loading, and the pull-request tooling.
#### The documentation was audited

- **The documentation was audited.**  The root `README.md` described five of
  its toolkits twice — once in sections 1–5 and again in sections 20–24, with
  the short versions deferring to the long ones — and the duplication is gone,
  with the numbering unchanged, so no anchor moved.  A cross-reference that
  pointed at the Shodan toolkit instead of the Chat History Manager was
  corrected, the "Recent Updates" section was brought up to date, and the
  project-structure tree now names every folder and document the repository
  actually holds.  The `tools_menu_update.md` described a six-category menu
  that does not exist; it is now generated from the live twelve-category menu.

### Tests

#### Local LLM setup (Ollama)

- **`tests/test_ollama_config.py`** - 12 new tests covering the endpoint
  resolution: the default, the `TORVALDS_OLLAMA_HOST` override, the
  `OLLAMA_HOST` fallback, the precedence between the two, the
  `host:port` -> `http://host:port` normalisation, and the integration with
  the two orchestrators and the tool retriever.

#### Local LLM setup (Ollama)

- The chain was checked end to end against a live local Ollama 0.33.2
  server: the default chat model
  (`richardyoung/qwen3.6-27b-abliterated:Q4_K_M`) answers, and
  `nomic-embed-text` returns a 768-dimension embedding.
- The full test suite shows no new failures: the failure set is
  byte-identical to the baseline (77 pre-existing failures, unchanged).

#### HITL: no timeout by default

- **`tests/test_hitl_no_timeout.py`** — 28 new tests covering the helper
  module, the timeout manager, the console input module, every component
  default, the agent step (in particular that `-1` reaches
  `wait_for_event()` as `None` and not as a small number) and both
  orchestrators.

#### MikroTik RouterOS Toolkit

- `tests/test_tool_selection_menu.py` — locks the selection menu against
  the defect above: the MikroTik tools must be discoverable and must form
  the **Network** category, the category must hold nothing else, the menu
  must offer the same inventory as the retriever, and the MikroTik tools
  must be present in every load path (menu, retriever, classic
  orchestrator, multi-window orchestrator). The two pre-existing
  inventory differences are pinned explicitly, so a *new* one still fails
  the test.
- `tests/test_mikrotik_toolkit.py` — the tool layer with a mocked transport:
  the uniform result shape, the safety gate, the confirmation and approval
  policy, the multi-line guard, the error-code mapping, the redaction and
  the tool registration.
- `tests/test_mikrotik_session.py` — every error of the taxonomy mapped to
  its code, the timeout plumbing and the safe-mode and prompt-not-detected
  results.
- `tests/test_mikrotik_safety.py` — the classifier table, the injection
  patterns, the management-path escalation and the confirmation policy.
- `tests/test_mikrotik_parser.py` — the `print`, `detail`, identity and
  property parsing fixtures.
- `tests/test_mikrotik_config.py` — the tolerant YAML loader, the
  environment fallbacks, the validation and the redaction.
- `tests/test_mikrotik_integration.py` — the opt-in suite against a real
  router, skipped unless `MIKROTIK_TEST_HOST` is set.

#### Interactive Help Command

- `tests/test_help_command.py` — 32 tests covering the command registry
  (uniqueness, descriptions, alias handling, feature filtering, rendering),
  the `\help` command in the TUI and in both classic REPLs, and consistency
  between the registry and the real dispatchers (HITL toggle, chat manager,
  project view, tool selection view).

#### Agent Cache Zero Stats Fix

- `tests/test_stats_wiring.py` — 27 tests covering the callback manager binding,
  the tool-call accounting path and the numeric normalisation, using
  `MockFunctionCallingLLM` so no network access is required.
- `tests/test_stats_mock.py` — fixed the `EventPayload.TOOL_NAME` payload key,
  which does not exist in llama-index 0.14.x and made `test_token_extraction` fail.

#### Multi-Window Agent Parity

- `tests/test_multi_window_parity.py` — 56 tests covering CLI parity, tool
  collection parity, tool selection, project manager, chat history, TUI state and
  command dispatch.
- `tests/test_tui_input_reader.py` — 6 tests covering the buffered input reader.

### Investigation

#### Agent Cache Zero Stats Fix

- `investigate/agent-cache-zero-stats/` — root-cause analysis, reproduction and
  verification scripts for the zero-statistics bug.

### Notes

#### The Linux toolkit is a module

- **The behaviour did not change.**  The tool menu is identical to the one on
  `master` — the same tools, in the same order, with the same descriptions.  The
  CI gate reports the same 40 known failures, 0 new and 0 fixed.

- **`get_system_info` is defined twice.**  The Linux toolkit and the OS toolkit
  each have one, and both are loaded into the same process on Linux, so the tool
  menu carries the name twice.  That duplicate is **pre-existing** — it is on
  `master` too — and the move neither created nor changed it.  The two functions
  are different: the Linux one shells out to `uname`/`lscpu`/`free`/`df` and
  returns their output, the OS one reads `platform` directly and returns a
  dictionary of structured fields.

- **A pre-existing `SyntaxWarning` in `agent-torvalds.py`.**  Line 759 holds
  `help="Disable runtime HITL toggle commands (\toggle-hitl, \hitl-status, etc.)"`,
  and `\t` and `\h` are not valid escape sequences in a non-raw string.  The
  layout contract parses that file to check its imports, and the warning showed
  up there; the test now suppresses it.  **The bug is left alone on purpose** —
  this is a behaviour-neutral refactoring, and the fix belongs in its own change.

### Unchanged

#### The GitHub toolkit is a module

- **The behaviour.**  Every function, every docstring, the tool descriptions and the
  error contract (a failure is reported as `False` or as
  `{"success": False, "error": ...}`, never raised) were moved verbatim.  The CI gate
  reports the same 40 known failures, **0 new and 0 fixed** — and `tests/ci_baseline.txt`
  did not change at all, because the toolkit had no known failures of its own.

## 2026-09-10

- [feature] add Linux shell command toolkit and enable chat memory (2026-09-10)

## [0.1.0] - 2026-09-09

### Features

- Integrated comprehensive Git and OS toolkits into Torvald agent, enabling full interaction with Git repositories and system operations
- Added database toolkit capabilities for executing SQL queries on PostgreSQL and MySQL databases
- Enhanced mathematical toolkit with addition, multiplication, and division operations
- Implemented system operations toolkit with full OS functionality access including file management and process control

### Fixes

- Updated agent-torvalds.py with recent changes

## [0.0.1] - 2026-09-08

### Features

- Initial commit: Torvalds Functional Agent
- Initial commit

[Unreleased]: https://github.com/KostiantynBushko/agent-torvalds/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/KostiantynBushko/agent-torvalds/releases/tag/v1.0.0
