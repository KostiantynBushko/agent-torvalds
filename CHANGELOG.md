# Changelog

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
