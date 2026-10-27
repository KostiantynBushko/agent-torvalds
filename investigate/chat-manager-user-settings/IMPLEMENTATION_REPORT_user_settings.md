# Implementation report — the user-settings API and the `\chat-user` command

**Date:** 2026-10-25
**Branch:** `feature/chat-user-settings` (off `master`, `5468e3b`)
**Scope:** Phase A of the investigation's proposed order of work
(`INVESTIGATION_REPORT.md` §5.3).
**Status:** implemented, verified.

---

## 0. What was asked for, and what was done

| Ask | Answer |
|-----|--------|
| Open the branch and start the implementation | `feature/chat-user-settings`, off `master` (`5468e3b`). |
| The name `token_limit` is wrong — it is applied to *chat* tokens. Propose a better name. | **`chat_token_limit`** — the proposal is in `PROPOSAL_chat_token_limit.md`, with six candidates weighed and the rejected ones explained. Implemented, with the old name kept as a working alias. |
| A command to manipulate the user configuration. The API must be exposed by the `chat_manager` module and integrated into the agent through the defined interface, like every other command. | `chat_manager.settings` (the API) + `ChatHistoryManager.get_user_settings()` / `update_user_settings()`, and the `\chat-user` command — registered in `components/command_registry.py`, dispatched by `chat_manager.commands.handler`, rendered by the TUI, and advertised by both orchestrators. |

---

## 1. The naming decision

**`token_limit` → `chat_token_limit`.**

The name said the unit but not the scope. The scope is the interesting part: the setting
governs how many tokens of **chat history** the agent keeps in the memory buffer of the active
session, and the codebase uses `token_limit` for at least three other things — the model's
`context_window` (`components/ollama_config.py`), the legacy `TORVALDS_TOKEN_LIMIT`
(`agent_chat_memory.py`), and the dead `TOKEN_LIMITS` constant in both orchestrators.

The full proposal, including the six candidates that were weighed and the three compatibility
seams, is in **`PROPOSAL_chat_token_limit.md`**. In short:

| Candidate | Verdict |
|-----------|---------|
| `token_limit` | Ambiguous — four meanings, one name. |
| **`chat_token_limit`** | **Adopted.** Says whose tokens. No collision in the tree. |
| `memory_token_limit` | Binds the setting to a LlamaIndex class name, not to the domain concept. |
| `context_token_limit` | Collides with the model's `context_window`. |
| `history_token_limit` | Too narrow — the buffer holds the live context, not a log. |
| `max_chat_tokens` | Reads like a constant, not a persisted setting. |
| `chat_context_limit` | The same `context` collision, less precise about the unit. |

**Three compatibility seams, so the rename breaks nothing:**

| Where | How |
|-------|-----|
| The database | `ALTER TABLE users RENAME COLUMN token_limit TO chat_token_limit`, run idempotently on connect. The values are kept; no manual step. |
| The Python API | `User.token_limit` is a deprecated property (getter *and* setter); `User(token_limit=…)` still works; `to_dict()` carries both keys; `from_dict()` accepts either. |
| The command | `token_limit` is a registered alias — `\chat-user set token_limit 12000` works, and the reply names the canonical key. |

`TORVALDS_TOKEN_LIMIT` was deliberately **not** renamed: it configures the *legacy*
compatibility buffer, and the legacy removal is Phase C, which is blocked on Phase B.

---

## 2. The API

### 2.1 `chat_manager/settings.py` (new)

The single source of truth for the settings, their ranges and their validation.

| Symbol | Purpose |
|--------|---------|
| `UserSettings` | Immutable snapshot of the current user's preferences. |
| `SettingSpec` | One setting: key, description, unit, default, range, writability. |
| `SettingError` | Raised for an unknown key, a read-only key, or a bad value. |
| `DEFAULT_CHAT_TOKEN_LIMIT` | `5000`. |
| `MIN_CHAT_TOKEN_LIMIT` / `MAX_CHAT_TOKEN_LIMIT` | `256` / `1_000_000`. |
| `normalize_setting_key(key)` | Typed key → canonical key (accepts `token_limit`). |
| `validate_setting_value(key, value)` | Validated value, ready to persist. |
| `validate_chat_token_limit(value)` | The chat-token limit's own validator. |

The two settings:

| Key | Writable | Range | Meaning |
|-----|----------|-------|---------|
| `chat_token_limit` | yes | 256 – 1 000 000 | Chat-history token budget of the memory buffer. |
| `backend_type` | **no** | — | The storage backend provisioned for the user. Assigned on first login; shown for reference only. |

`backend_type` is read-only on purpose: it is written when the user is provisioned and is
never consulted at runtime, so letting the operator change it would be a lie.

### 2.2 The manager

```python
manager.get_user_settings()            # -> UserSettings
manager.update_user_settings(chat_token_limit=12000)   # -> UserSettings
manager.set_chat_token_limit(8000)     # the same, shorter
```

`update_user_settings()`:

1. resolves every key (`token_limit` → `chat_token_limit`),
2. validates every value **before** writing anything — a bad value never leaves the settings
   half-updated,
3. persists through `CustomDBConnector.update_user()`,
4. **drops the cached memory buffer**, so a changed limit is live on the next turn.

Step 4 closes defect **C2** (a changed limit was inert until the operator switched sessions).

---

## 3. The command

`\chat-user` joins the `\chat-*` layer, so it is dispatched by the agent's main loop **before**
the LLM is invoked — it costs no tokens and the model cannot trigger it.

| Command | Description |
|---------|-------------|
| `\chat-user` | Show every setting and its value. |
| `\chat-user get <key>` | Show one setting. |
| `\chat-user set <key> <value>` | Change one setting. |
| `\chat-user help` | List the settings, their ranges and their usage. |

The implementation follows the layer's existing shape exactly:

| Layer | File | What was added |
|-------|------|----------------|
| Command functions | `chat_manager/commands/cli.py` | `cmd_chat_user`, `cmd_chat_user_get`, `cmd_chat_user_set`, `cmd_chat_user_help` — one function per command, each returning a human-readable string and never raising for an expected error. |
| Dispatcher | `chat_manager/commands/handler.py` | `\chat-user` in `CHAT_COMMANDS`; the sub-command branch in `handle_chat_command()`. |
| Package exports | `chat_manager/commands/__init__.py` | The four new functions. |
| Module exports | `chat_manager/__init__.py` | `UserSettings`, `SettingSpec`, `SettingError`, `SETTING_SPECS`, the three constants, the three validators. |
| The registry | `components/command_registry.py` | A `CommandSpec` in the **Chat** category with `FEATURE_CHAT_HISTORY` — so `\help` lists it in both orchestrators. |
| The TUI | `components/tui/chat_history_view.py` | `render_chat_user_markdown()` — a Markdown table of the settings; `\chat-user` routes to it. |
| The orchestrators | `agent-torvalds.py`, `agent-torvalds-mw.py` | A startup hint line, and the command list in the multi-window header. |

### 3.1 The registry is the contract

`tests/test_help_command.py::test_chat_commands_match_the_chat_handler` already asserts that
every command the chat handler knows is declared in the registry. The new command is therefore
covered by an existing guard — and the reverse direction (every registered chat command is
handled) is now guarded too, by
`tests/test_user_settings_command.py::TestChatUserInTheRegistry`.

### 3.2 A sample session

```
>>> \chat-user
Settings for user 'kbush':
  chat_token_limit  5000 tokens
  backend_type      postgres string

Change a setting with: \chat-user set <key> <value>
Show one setting with: \chat-user get <key>

>>> \chat-user set chat_token_limit 12000
Set chat_token_limit = 12000 tokens. The memory buffer was rebuilt, so the new limit applies from the next message on.

>>> \chat-user get chat_token_limit
chat_token_limit = 12000 tokens

>>> \chat-user set chat_token_limit 5
The chat token limit must be at least 256 (got 5).

>>> \chat-user set token_limit 8000
Set chat_token_limit = 8000 tokens. The memory buffer was rebuilt, so the new limit applies from the next message on.
```

---

## 4. The defects this closes

| ID | Defect | How it is closed |
|----|--------|------------------|
| **C1** | No public API to change a user preference. | `get_user_settings()` / `update_user_settings()`. |
| **C2** | A changed limit did not reach the live buffer. | `update_user_settings()` drops the cached buffer; `get_memory_buffer()` also rebuilds when the effective limit differs. |
| **C3** | The `token_limit` argument of `get_memory_buffer()` was ignored after the first call. | The early return now compares the effective limit with the one the buffer was built with, and rebuilds when they differ. |
| **C4** | No command read or wrote the user's settings; the current limit was not even displayed. | `\chat-user`. |
| **C7** (partly) | Four competing defaults for one concept, one of them dead. | The manager's limit is now `users.chat_token_limit` and the *name* says which one it is. The dead `TOKEN_LIMITS` constants and the legacy `TORVALDS_TOKEN_LIMIT` are Phase C — see §7. |

**C5, C6, C8 and C9 are untouched** — they belong to the legacy implementation, and §5.1 of the
investigation shows that removing it before the SQLite fallback exists would cost the agent its
chat memory whenever the metadata database is down.

---

## 5. The files

| Path | Change |
|------|--------|
| `chat_manager/settings.py` | **New.** The settings, their ranges, their validation, the `UserSettings` snapshot. |
| `chat_manager/user.py` | `token_limit` → `chat_token_limit`; deprecated property and constructor keyword; `to_dict()` carries both keys. |
| `chat_manager/storage/models.py` | The column was renamed; a SQLAlchemy `synonym` keeps the old attribute working. |
| `chat_manager/storage/connector.py` | The DDL, the conversions and `update_user()` use the new name; `_migrate_schema()` renames the column in place. |
| `chat_manager/manager.py` | The settings API, the buffer invalidation, the honoured override, the shared default. |
| `chat_manager/commands/cli.py` | The four command functions. |
| `chat_manager/commands/handler.py` | `\chat-user` in the registry and in the dispatcher. |
| `chat_manager/commands/__init__.py`, `chat_manager/__init__.py` | The exports. |
| `components/command_registry.py` | The `CommandSpec` — the `\help` entry. |
| `components/tui/chat_history_view.py` | `render_chat_user_markdown()`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The startup hints and the command list. |
| `chat_manager/tests/test_settings.py` | **New.** 22 tests. |
| `chat_manager/tests/test_user_settings.py` | **New.** 40 tests. |
| `chat_manager/tests/test_migration.py` | **New.** 9 tests. |
| `tests/test_user_settings_command.py` | **New.** 16 tests — the integration. |
| `chat_manager/README.md`, `README.md`, `CHANGELOG.md` | The documentation. |

---

## 6. Verification

```bash
cd self-development

# The chat manager suite — 175 passed
.venv/bin/python -m pytest chat_manager/tests -q

# The integration suite
.venv/bin/python -m pytest tests/test_user_settings_command.py -q

# The whole suite, through the CI gate
.venv/bin/python scripts/ci_test_gate.py
```

| Check | Result |
|-------|--------|
| `chat_manager/tests` | **175 passed** (104 before, 71 new). |
| `tests/test_user_settings_command.py` | **16 passed.** |
| The full suite | **1615 passed, 39 failed, 1 error** — the CI gate reports **40 known failures, 0 new**, so the build is green. |
| The investigation probe | Still runs; the deprecated aliases keep its questions answerable. |
| The report reference check | **PASS** — 28 references resolve (the line numbers moved with the code; the banner in the report says so). |

---

## 7. What was deliberately **not** done

| Not done | Why |
|-----------|-----|
| Removing `agent_chat_memory.py` and the `--no-chat-history` flag | Phase C. Blocked on Phase B (the SQLite fallback in `CustomDBConnector`) — without it, a database outage costs the agent its chat history entirely. |
| Deleting the dead `TOKEN_LIMITS` constants | They belong to the legacy path. Removing them in Phase A would touch a code path that is still load-bearing. |
| Renaming `TORVALDS_TOKEN_LIMIT` | It configures the legacy buffer, not the manager's setting. Phase C. |
| Making `backend_type` writable | It is written once, at provisioning, and never read at runtime. A writable setting that does nothing is a trap. |
| Dropping the `token_limit` aliases | The deprecation path is three releases long, and the aliases cost nothing. |

---

## 8. The next step

**Phase B — the SQLite fallback in `CustomDBConnector`.** Give the metadata layer the same
shape of degradation the message layer already has: on a connection failure, retry against a
local SQLite file and log the degradation. With that in place the manager covers both
"PostgreSQL up" (full features) and "PostgreSQL down" (degraded but complete), and the legacy
single-key path has no remaining job — which unblocks Phase C, the removal.
