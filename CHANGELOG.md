# Changelog

## [Unreleased] - Shodan Toolkit

### Added
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

### Fixed
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

### Security
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

### Changed
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

## [Unreleased] - Local LLM setup (Ollama)

### Documentation
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

### Added
- **`components/ollama_config.py`** - the single source of truth for the
  Ollama endpoint. `get_ollama_base_url()` resolves
  `TORVALDS_OLLAMA_HOST`, then `OLLAMA_HOST`, then
  `http://localhost:11434`, and normalises a bare `host:port` into a full
  URL with the `http://` scheme.
- **`TORVALDS_OLLAMA_HOST`** - points the agent at an Ollama server that does
  not listen on the default endpoint (another host, a container, a
  non-default port). It is used for the chat model in both orchestrators
  and for the embedding model in the tool retriever.

### Changed
- The chat model (`agent-torvalds.py`, `agent-torvalds-mw.py`) and the
  embedding model (`agent_tool_retriever.py`) now use the resolved Ollama
  endpoint instead of the hard-coded `http://localhost:11434`. The default
  behaviour is unchanged.

### Tests
- **`tests/test_ollama_config.py`** - 12 new tests covering the endpoint
  resolution: the default, the `TORVALDS_OLLAMA_HOST` override, the
  `OLLAMA_HOST` fallback, the precedence between the two, the
  `host:port` -> `http://host:port` normalisation, and the integration with
  the two orchestrators and the tool retriever.

### Verified
- The chain was checked end to end against a live local Ollama 0.33.2
  server: the default chat model
  (`richardyoung/qwen3.6-27b-abliterated:Q4_K_M`) answers, and
  `nomic-embed-text` returns a 768-dimension embedding.
- The full test suite shows no new failures: the failure set is
  byte-identical to the baseline (77 pre-existing failures, unchanged).

## [Unreleased] - HITL: no timeout by default

### Fixed
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

### Added
- **`components/hitl_timeout.py`** — the single source of truth for the
  convention. It provides `NO_TIMEOUT` (`-1`), `normalize_timeout()` (the
  translation into the `None` that `asyncio.wait_for` and
  `Context.wait_for_event` expect), `is_no_timeout()`, `validate_timeout()`
  and `describe_timeout()` (which renders `-1` as `none` in the status
  output).

### Changed
- Every HITL default is now `-1` instead of `30`: the orchestrators
  (`agent-torvalds.py`, `agent-torvalds-mw.py`), the timeout manager, the
  console and whiptail input modules, the HITL event classes, the agent
  step, the event consumer, the TUI state bridge, the MikroTik approval
  prompt and the project-manager disambiguation prompt.
- The HITL status output shows `Timeout: none` instead of `Timeout: 30s`.

### Tests
- **`tests/test_hitl_no_timeout.py`** — 28 new tests covering the helper
  module, the timeout manager, the console input module, every component
  default, the agent step (in particular that `-1` reaches
  `wait_for_event()` as `None` and not as a small number) and both
  orchestrators.

## [Unreleased] - MikroTik RouterOS Toolkit

### Features
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

### Fixes
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

### Tests
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

### Documentation
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

## [Unreleased] - Interactive Help Command

### Features
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

### Fixes
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

### Tests
- `tests/test_help_command.py` — 32 tests covering the command registry
  (uniqueness, descriptions, alias handling, feature filtering, rendering),
  the `\help` command in the TUI and in both classic REPLs, and consistency
  between the registry and the real dispatchers (HITL toggle, chat manager,
  project view, tool selection view).

## [Unreleased] - Agent Cache Zero Stats Fix

### Fixes
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

### Improved
- **Token usage extraction** — the new `components.stats_handler._extract_usage()`
  helper probes several provider response shapes (`raw["usage"]`,
  `raw["usage_metadata"]`, the raw Ollama `prompt_eval_count`/`eval_count` format,
  `additional_kwargs["usage"]` and the `usage`/`usage_metadata` attributes) instead
  of only reading `raw["usage"]`.

### Tests
- `tests/test_stats_wiring.py` — 27 tests covering the callback manager binding,
  the tool-call accounting path and the numeric normalisation, using
  `MockFunctionCallingLLM` so no network access is required.
- `tests/test_stats_mock.py` — fixed the `EventPayload.TOOL_NAME` payload key,
  which does not exist in llama-index 0.14.x and made `test_token_extraction` fail.

### Investigation
- `investigate/agent-cache-zero-stats/` — root-cause analysis, reproduction and
  verification scripts for the zero-statistics bug.

## [Unreleased] - Multi-Window Agent Parity

### Features
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

### Fixes
- **TUI input reader** — keystrokes typed in a burst were truncated to the first
  character because `sys.stdin.read(1)` blocks until a full line arrives. The
  reader now consumes the raw terminal file descriptor and buffers the remainder,
  so slash commands such as `\projects` are received in full.

### New modules
- `components/tui/tool_selection_view.py` — TUI-friendly tool discovery, category
  rendering and interactive selection.
- `components/tui/project_manager_view.py` — Markdown renderers for the project
  list, project details, git status and workspace summary.
- `components/tui/chat_history_view.py` — Markdown renderers for the chat session
  list and active session details.

### Tests
- `tests/test_multi_window_parity.py` — 56 tests covering CLI parity, tool
  collection parity, tool selection, project manager, chat history, TUI state and
  command dispatch.
- `tests/test_tui_input_reader.py` — 6 tests covering the buffered input reader.

## 2026-09-10

- [feature] add Linux shell command toolkit and enable chat memory (2026-09-10)

All notable changes to this project will be documented in this file.

## [Unreleased]

### Features
- Added comprehensive Git toolkit capabilities for repository management
- Implemented system operations toolkit with full OS functionality access
- Integrated database toolkit for PostgreSQL and MySQL query execution
- Enhanced mathematical toolkit with basic arithmetic operations (add, multiply, divide)
- **NEW: `load_project()` unified project loading API** — transparently handles both existing workspaces (loads from `.agentworkspace.json`) and new project discovery (creates workspace, scans, detects, and registers)

### Details: `load_project()` Feature
- **Unified Entry Point**: Single method to load projects regardless of whether a workspace already exists
- **Two Loading Modes**:
  - `existing_workspace`: Loads project from existing `.agentworkspace.json` config
  - `new_workspace`: Creates workspace, scans directory, auto-detects type, and registers project
- **Smart Project Resolution**: Supports lookup by `project_name` or automatic path matching
- **Standardized Results**: Returns consistent dictionary structure with `status`, `method`, `workspace_path`, and full `project` metadata
- **Fallback Handling**: Gracefully falls back to first project when no exact path match is found in existing workspaces
- **Force Mode**: Supports `force=True` to register projects even when type detection is ambiguous

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
