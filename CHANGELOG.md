# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

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
- **Rule 7** in `SELF_DEVELOPMENT_RULES.md`: how the agent waits for the
  operator, and what it may do when the wait ends.

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
  EventConsumer._on_agent_input:   [4] tool: output: /home/kbush
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
