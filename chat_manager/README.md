# Chat History Manager (`chat_manager`)

> **Multi-user, multi-session chat history for the Torvalds AI Agent.**

The `chat_manager` package implements the **ChatHistoryManager** — a stable, backend-agnostic
interface for managing chat sessions, user identities, and persistent message storage. It lets the
agent switch between independent conversations (e.g. *General Chat*, *Project Chat*, and any number
of user-created sessions) while keeping each conversation's history fully isolated and durably
stored in PostgreSQL.

The agent never talks to `PostgresChatStore` directly. It talks to the manager, and the manager
talks to the storage layer. That indirection is what makes the backend replaceable without
touching agent logic.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Component Reference](#component-reference)
- [Database Schema](#database-schema)
- [Configuration](#configuration)
- [Installation](#installation)
- [Usage Examples](#usage-examples)
- [CLI Commands](#cli-commands)
- [User settings](#user-settings)
- [Agent Integration](#agent-integration)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Design Documents](#design-documents)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

Before this module, the agent had a single flat conversation: one PostgreSQL chat store key
(`TORVALDS_CHAT_KEY`, default `user1-abliterated`) and one global memory buffer. Switching topics
meant mixing unrelated messages into the same history.

`chat_manager` replaces that with a proper session model:

1. **User identification** — the current OS user is looked up in the `users` table and
   auto-provisioned on first run.
2. **Session lifecycle** — sessions are created, listed, switched, renamed, and deleted, all
   scoped to the owning user.
3. **Persistent active state** — the active session is stored in the database, so it survives
   restarts and is restored automatically on the next launch.
4. **Isolated message history** — every session maps to its own `chat_key` in the LlamaIndex
   message store, so histories never bleed into one another.
5. **Backend fallback** — if PostgreSQL is unreachable, the message layer degrades gracefully to
   an in-memory store instead of crashing the agent.

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **True session isolation** | Each session has its own `chat_key`; the memory buffer is rebuilt on switch, so messages cannot leak between conversations |
| **Multi-user support** | Sessions are scoped per `user_id`; one user can never activate, read, or delete another user's session |
| **Zero local state** | All state lives in the database — no JSON config files, no cache files, no per-machine drift |
| **Backend-agnostic** | The `ChatStoreBackend` interface isolates the agent from the storage engine; PostgreSQL can be swapped without agent changes |
| **Graceful degradation** | PostgreSQL outage → in-memory message backend; the agent stays usable |
| **Interactive UX** | A numbered session menu at startup, plus `\chat-*` commands for runtime management |
| **Database-only source of truth** | The active session is restored from the DB, not from local files |

---

## Key Features

### Multi-user & auto-provisioning

- The current OS user is resolved via `os.getlogin()`, falling back to `getpass.getuser()`, then
  to the literal `"default_user"`.
- If the user does not exist, a record is created automatically with `backend_type='postgres'` and
  `chat_token_limit=5000`.
- Every session belongs to exactly one user; the ownership check is enforced in the manager layer
  *and* in the SQL connector.

### Session lifecycle

- Two sessions are pre-seeded for a brand-new user: **General Chat** (`general`) and
  **Project Chat** (`project`).
- Users can create any number of additional `custom` sessions.
- Exactly one session per user is active at a time; activating a session deactivates all others in
  a single transaction.
- The active session cannot be deleted (a guard prevents accidental loss of the live conversation).

### Isolated message history

- The LlamaIndex `ChatMemoryBuffer` is bound to the active session's `chat_key`.
- Switching sessions invalidates the cached buffer, so the next call rebuilds it against the new
  key — this is what guarantees no cross-session leakage.
- `\chat-clear` wipes the messages of the active session while keeping the session itself.

### Interactive startup selection

At launch (unless disabled) the agent presents a numbered menu of the user's sessions and lets
you pick one, create a new one, or just press Enter to keep the current one. The choice is
persisted as the user's active session.

### Interactive commands

Eight runtime commands (`\chat-sessions`, `\chat-select`, `\chat-create`, `\chat-delete`,
`\chat-rename`, `\chat-info`, `\chat-clear`, `\chat-user`) are dispatched by the agent's main
loop. They are **commands, not agent tools** — the LLM cannot call them, only the human
operator can.

`\chat-user` is the command over the user's *own configuration* — the preferences stored in
the `users` table. See [User settings](#user-settings) below.

---

## Architecture

```
chat_manager/
├── __init__.py                    # Public API exports
├── manager.py                     # ChatHistoryManager — core orchestrator
├── user.py                        # User dataclass (domain model)
├── session.py                     # Session dataclass + SessionType enum (domain model)
├── settings.py                    # User settings — the user's own configuration
├── startup.py                     # Global singleton lifecycle + startup hooks
├── session_selector.py            # Interactive startup session picker
├── backend/                       # Message storage (LlamaIndex chat store)
│   ├── __init__.py
│   ├── base.py                    # ChatStoreBackend ABC (extends BaseChatStore)
│   ├── postgres.py                # PostgresChatStoreBackend
│   └── simple.py                  # SimpleChatStoreBackend (in-memory fallback)
├── storage/                       # User & session metadata (SQLAlchemy)
│   ├── __init__.py
│   ├── models.py                  # ORM models: User, Session
│   └── connector.py               # CustomDBConnector — CRUD + schema DDL
├── commands/                      # Interactive command layer
│   ├── __init__.py
│   ├── handler.py                 # Dispatch: is_chat_command() / handle_chat_command()
│   └── cli.py                     # Per-command implementations
└── tests/                         # 175 unit tests
    ├── conftest.py
    ├── test_backend.py
    ├── test_commands.py
    ├── test_manager.py
    ├── test_migration.py
    ├── test_models.py
    ├── test_session_selector.py
    ├── test_settings.py
    ├── test_startup.py
    ├── test_storage.py
    └── test_user_settings.py
```

### Dual-Connector Architecture

The module deliberately uses **two independent connectors** so that LlamaIndex owns its own
schema and the manager owns its own:

| Connector | Responsibility | Tables | Managed By |
|-----------|----------------|--------|------------|
| **Custom DB Connector** (`storage/connector.py`) | User identities, session metadata, active-session state, per-user token limits | `users`, `chat_sessions` | `ChatHistoryManager` (SQLAlchemy ORM) |
| **LlamaIndex Connector** (`backend/postgres.py`) | Chat message bodies | LlamaIndex internal chat tables | `PostgresChatStore` (LlamaIndex) |

Both may point at the same PostgreSQL instance; they operate on disjoint tables and never
interfere.

### Data Flow

```
Agent startup
      │
      ▼
initialize_chat_manager()
      │
      ├──► CustomDBConnector.connect()  ──► creates `users` + `chat_sessions` tables
      │
      ├──► Backend selection
      │        ├── PostgresChatStoreBackend.connect()  ──► success
      │        └── SimpleChatStoreBackend.connect()     ──► fallback (PG unavailable)
      │
      ├──► _identify_user()   ──► lookup by OS username, auto-provision if missing
      │
      └──► _ensure_user_sessions()
               ├── seed "General Chat" + "Project Chat" for new users
               └── restore active session from DB (fallback: activate General Chat)

User input
      │
      ▼
ChatMemoryBuffer ──► ChatStoreBackend ──► LlamaIndex chat tables
   (bound to active          (dual connector)
    session's chat_key)
```

---

## Component Reference

### 1. `ChatHistoryManager` (`manager.py`)

The orchestrator. Owns the current user, the active session, the storage connector, and the
message backend.

| Method | Description |
|--------|-------------|
| `initialize()` | Connect connectors, identify user, restore active session. Main startup entry point. |
| `shutdown()` | Close all connections and reset state. Safe to call repeatedly. |
| `identify_user()` | Resolve the current OS user, provisioning on demand. Idempotent. |
| `get_active_session()` | Return the currently active `Session` or `None`. |
| `get_active_chat_key()` | Return the active session's LlamaIndex chat key. |
| `list_sessions()` | List all sessions belonging to the current user. |
| `create_session(name, type, metadata)` | Create a new session (not auto-activated). |
| `get_session(session_id)` | Fetch a session by ID — only if owned by the current user. |
| `update_session(session_id, **kwargs)` | Update fields of an owned session. |
| `rename_session(session_id, new_name)` | Rename an owned session. Rejects empty names. |
| `select_session(session_id)` | Activate a session (alias of `switch_session`). |
| `switch_session(session_id)` | Activate a session and invalidate the memory buffer. |
| `delete_session(session_id)` | Delete an owned, non-active session. |
| `get_memory_buffer(chat_token_limit)` | Lazily build/cache the `ChatMemoryBuffer` for the active session. Rebuilds the buffer when the effective limit changed. |
| `get_user_settings()` | Return the current user's settings as a `UserSettings` snapshot. |
| `update_user_settings(**changes)` | Validate, persist and apply a settings change. Drops the cached buffer so a new limit is live immediately. |
| `set_chat_token_limit(limit)` | Convenience wrapper for the one setting that changes most often. |
| `add_message(content, role)` | Append a `ChatMessage` to the active session. |
| `put_message(content, role)` | Alias of `add_message`. |
| `get_messages()` | Return all `ChatMessage` objects for the active session. |
| `clear_messages()` | Delete all messages of the active session (session itself survives). |
| `close()` | Alias of `shutdown`. |

**Properties:** `current_user` → `User | None`; `is_initialized` → `bool`.

### 2. `ChatStoreBackend` (`backend/base.py`)

An abstract base class that **extends LlamaIndex's `BaseChatStore`**, so instances can be handed
straight to `ChatMemoryBuffer.from_defaults(chat_store=...)`.

Subclasses implement five backend-specific primitives — `connect()`, `put_messages()`,
`get_messages()`, `delete_messages()`, `list_keys()`, `close()` — and this base class maps them
onto the seven methods LlamaIndex requires (`set_messages`, `get_messages`, `add_message`,
`delete_messages`, `delete_message`, `delete_last_message`, `get_keys`).

`BackendConfig` carries the `connection_string`, `table_name`, and free-form `extra_params`.

### 3. `PostgresChatStoreBackend` (`backend/postgres.py`)

Wraps LlamaIndex's `PostgresChatStore`. `connect()` **propagates exceptions** so the manager can
detect the failure and fall back to the in-memory backend.

### 4. `SimpleChatStoreBackend` (`backend/simple.py`)

Wraps LlamaIndex's `SimpleChatStore` — a pure in-memory store. Used as the automatic fallback
when PostgreSQL is unavailable, and handy in tests.

### 5. `CustomDBConnector` (`storage/connector.py`)

A SQLAlchemy-backed connector for user and session metadata, isolated from the LlamaIndex message
store.

**Lifecycle:** `connect()` (creates the schema on demand) · `close()` · `is_connected` property.

**User operations:** `get_user_by_username()` · `get_user_by_id()` · `create_user()` ·
`update_user()`.

**Session operations:** `get_session_by_id()` · `get_active_session()` · `list_sessions()` ·
`create_session()` · `activate_session()` · `delete_session()` · `update_session()`.

Activation and deletion both take a `user_id` filter, so cross-user access is rejected at the SQL
level as well as in the manager.

### 6. `Session` / `User` dataclasses

Plain dataclasses with `to_dict()` / `from_dict()` serialisation, UUID defaults, and
`update_timestamp()`. `Session` and `User` define equality by `session_id` / `user_id` and are
therefore hashable.

`SessionType` is a `str`-backed enum with three members:

| Value | Meaning |
|-------|---------|
| `general` | General-purpose conversation (pre-seeded) |
| `project` | Project-scoped conversation (pre-seeded) |
| `custom` | User-created session |

### 7. `startup.py` — Singleton Lifecycle

| Function | Description |
|----------|-------------|
| `initialize_chat_manager(storage_uri, llama_uri)` | Create and initialise the global singleton. Idempotent — returns the existing instance if already initialised. |
| `get_chat_manager()` | Return the singleton, or `None` if not initialised. |
| `shutdown_chat_manager()` | Shut down and clear the singleton. |
| `is_chat_manager_initialized()` | `True` when the manager is ready. |
| `select_startup_session(input_func, output_func)` | Run the interactive startup picker with injectable I/O. |

### 8. `session_selector.py` — Interactive Startup Picker

Terminal-free by design: both the input and the output function are injectable, so the whole
flow is unit-testable headlessly.

| Function | Description |
|----------|-------------|
| `format_session_list(sessions)` | Render the numbered session menu. |
| `select_session_interactively(manager, input_func, output_func)` | Run the selection loop. |

Accepted inputs: a **number** (1..N) selects that session, **`new <name>`** creates a custom
session, **Enter** keeps the current active session, and `Ctrl+C` / `EOF` aborts safely while
keeping the current session.

### 9. `settings.py` — User Settings

The user's own configuration: what the settings are, what their valid ranges are, and how a
raw operator input is validated before it reaches the database.

| Symbol | Description |
|--------|-------------|
| `UserSettings` | Immutable snapshot of the current user's preferences. |
| `SettingSpec` | Description of one setting: key, unit, default, range, writability. |
| `SettingError` | Raised for an unknown key, a read-only key, or a bad value. |
| `DEFAULT_CHAT_TOKEN_LIMIT` | `5000` — the default chat-history token budget. |
| `MIN_CHAT_TOKEN_LIMIT` / `MAX_CHAT_TOKEN_LIMIT` | `256` / `1_000_000` — the accepted range. |
| `normalize_setting_key(key)` | Resolve a typed key to its canonical name (accepts the deprecated `token_limit`). |
| `validate_setting_value(key, value)` | Validate a value for a setting and return it ready to persist. |
| `validate_chat_token_limit(value)` | The chat-token limit's own validator. |

### 10. `commands/` — Interactive Command Layer

`handler.py` provides the dispatcher used by the agent's main loop:

| Function | Description |
|----------|-------------|
| `is_chat_command(cmd)` | `True` when the input is a `\chat-*` command. |
| `handle_chat_command(cmd)` | Execute the command and return the user-facing response string. |

`cli.py` holds one function per command: `cmd_chat_sessions`, `cmd_chat_select`, `cmd_chat_create`,
`cmd_chat_delete`, `cmd_chat_rename`, `cmd_chat_info`, `cmd_chat_clear`, `cmd_chat_user`,
`cmd_chat_user_get`, `cmd_chat_user_set`, `cmd_chat_user_help`. Each returns a human-readable
string and never raises for expected error conditions.

---

## Database Schema

The metadata layer uses two tables, created idempotently on first connect. The equivalent DDL lives
in the `SCHEMA_SQL` constant of `chat_manager/storage/connector.py`.

### `users`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | TEXT | PRIMARY KEY | UUID of the user |
| `username` | TEXT | NOT NULL, UNIQUE | OS login name |
| `backend_type` | TEXT | NOT NULL, DEFAULT `'postgres'` | Preferred storage backend |
| `chat_token_limit` | INTEGER | NOT NULL, DEFAULT `5000` | Chat-history token budget of the memory buffer |
| `created_at` | TIMESTAMP | DEFAULT `CURRENT_TIMESTAMP` | Creation time |
| `updated_at` | TIMESTAMP | DEFAULT `CURRENT_TIMESTAMP` | Last update time |

### `chat_sessions`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `session_id` | TEXT | PRIMARY KEY | UUID of the session |
| `user_id` | TEXT | NOT NULL, FK → `users(user_id)` `ON DELETE CASCADE` | Owning user |
| `session_name` | TEXT | NOT NULL | Human-readable name |
| `session_type` | TEXT | NOT NULL, CHECK `IN ('general','project','custom')` | Session category |
| `chat_key` | TEXT | NOT NULL, UNIQUE | Key into the LlamaIndex message store |
| `metadata` | TEXT | DEFAULT `'{}'` | JSON blob (tags, project id, …) |
| `created_at` | TIMESTAMP | DEFAULT `CURRENT_TIMESTAMP` | Creation time |
| `updated_at` | TIMESTAMP | DEFAULT `CURRENT_TIMESTAMP` | Last update time |
| `is_active` | BOOLEAN | DEFAULT `FALSE` | Whether this is the user's active session |

Indexes: `idx_sessions_user (user_id)`, `idx_sessions_type (session_type)`,
`idx_sessions_active (user_id, is_active)`.

The schema is created idempotently by `CustomDBConnector.connect()` via
`Base.metadata.create_all(engine)` — no manual migration step is required on a fresh database.

### The `token_limit` → `chat_token_limit` migration

The column was renamed so that it says *whose* tokens it limits (see
`investigate/chat-manager-user-settings/PROPOSAL_chat_token_limit.md`). An existing database
still has the old column name, so `CustomDBConnector.connect()` renames it in place:

```sql
ALTER TABLE users RENAME COLUMN token_limit TO chat_token_limit
```

The migration is idempotent (it is skipped when the canonical column is already there) and
never fatal — a failure is logged as a warning, because a chat history that cannot be migrated
is a smaller problem than a chat history that cannot be reached. The values are kept, and no
manual step is needed.

---

## Configuration

All configuration is environment-driven; nothing is hard-coded in the agent.

| Variable | Default | Description |
|----------|---------|-------------|
| `TORVALDS_STORAGE_URI` | derived from `TORVALDS_PG_*` | SQLAlchemy URI for the `users` / `chat_sessions` tables (e.g. `postgresql://user:pass@host:5432/llama_index_db`) |
| `TORVALDS_LLAMA_URI` | `postgres+asyncpg://…/llama_index_db` | LlamaIndex chat-store URI for message bodies |
| `TORVALDS_PG_HOST` | `127.0.0.1` | PostgreSQL host |
| `TORVALDS_PG_PORT` | `5432` | PostgreSQL port |
| `TORVALDS_PG_USER` | `postgres` | PostgreSQL user |
| `TORVALDS_PG_PASSWORD` | `postgres` | PostgreSQL password |
| `TORVALDS_PG_DATABASE` | `llama_index_db` | PostgreSQL database name |
| `TORVALDS_CHAT_KEY` | — | Legacy single-key chat store name. If set, it is reused as the `chat_key` of the pre-seeded **General Chat** session, which keeps existing message history reachable after the upgrade. |
| `TORVALDS_TOKEN_LIMIT` | `5000` | Token limit for the **legacy** compatibility buffer. The manager uses `users.chat_token_limit` instead — see [User settings](#user-settings). |

**URI precedence.** `TORVALDS_STORAGE_URI` and `TORVALDS_LLAMA_URI` take priority. When they are
absent, both connectors are derived from the `TORVALDS_PG_*` variables — the metadata connector
uses the synchronous `postgresql://` driver, the message connector uses the async
`postgres+asyncpg://` driver required by LlamaIndex.

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--no-chat-history` | off | Disable the ChatHistoryManager entirely and fall back to the legacy single-session chat memory. |
| `--no-session-select` | off | Skip the interactive startup session selection menu. |

---

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL (recommended; the agent degrades to in-memory messages without it, but sessions are
  then not persisted)
- The following Python packages:

```bash
pip install "llama-index>=0.14.24" \
            "llama-index-storage-chat-store-postgres>=0.5.0" \
            "SQLAlchemy>=2.0" \
            "psycopg2-binary>=2.9.12" \
            "asyncpg>=0.30.0"
```

> **Note:** `SQLAlchemy` is imported by `chat_manager/storage/` but is **not** yet listed in
> `requirements.txt`. Add `SQLAlchemy>=2.0` to that file when integrating this branch.

### Database setup

The role and database used by the chat memory module are created with the
`setup_postgres_db.sql` script at the **project root**:

```bash
# Run from the project root
psql -U postgres -f setup_postgres_db.sql
```

```sql
-- setup_postgres_db.sql (project root)
CREATE USER llama WITH PASSWORD 'llama';
CREATE DATABASE llama_index_db OWNER llama;
GRANT ALL PRIVILEGES ON DATABASE llama_index_db TO llama;
```

> **Note:** this script lives in the repository root. If it is missing on your branch, the
> equivalent statements are shown above and can be executed directly.

The `users` and `chat_sessions` tables are then created automatically on first run. The LlamaIndex
message tables are created by `PostgresChatStore` itself.

### Placing the module

The package lives at the **project root** as `chat_manager/` and is imported by the absolute
package name:

```python
from chat_manager import ChatHistoryManager
```

It must be importable from the working directory (i.e. run the agent from the repository root, or
add the root to `PYTHONPATH`).

---

## Usage Examples

### 1. Standalone usage

```python
from chat_manager import ChatHistoryManager

manager = ChatHistoryManager()
manager.initialize()

print(f"User: {manager.current_user.username}")
print(f"Active session: {manager.get_active_session().session_name}")

# List everything the user owns
for session in manager.list_sessions():
    marker = "*" if session.is_active else " "
    print(f" {marker} {session.session_name} [{session.session_type.value}]")

manager.shutdown()
```

### 2. Creating and switching sessions

```python
from chat_manager import ChatHistoryManager, SessionType

manager = ChatHistoryManager()
manager.initialize()

# Create a session (creation does not activate it)
session = manager.create_session(
    name="Postgres migration",
    session_type=SessionType.CUSTOM,
    metadata={"project": "torvalds", "tag": "important"},
)
print(f"Created {session.session_id}")

# Switch to it — the memory buffer is rebuilt against the new chat_key
manager.switch_session(session.session_id)
print(manager.get_active_chat_key())

manager.shutdown()
```

### 3. Writing and reading messages

```python
from chat_manager import ChatHistoryManager

manager = ChatHistoryManager()
manager.initialize()

manager.add_message("How do I set up PostgreSQL?", role="user")
manager.add_message("Run setup_postgres_db.sql, then start the agent.", role="assistant")

for message in manager.get_messages():
    print(f"[{message.role}] {message.content}")

# Wipe the history but keep the session
manager.clear_messages()

manager.shutdown()
```

### 4. Per-session isolation in action

```python
from chat_manager import ChatHistoryManager

manager = ChatHistoryManager()
manager.initialize()

# Session A
a = manager.create_session(name="Session A")
manager.switch_session(a.session_id)
manager.add_message("This belongs to A", role="user")

# Session B
b = manager.create_session(name="Session B")
manager.switch_session(b.session_id)
manager.add_message("This belongs to B", role="user")

print("B sees:", [m.content for m in manager.get_messages()])
# B sees: ['This belongs to B']   ← no leakage from A

# Back to A
manager.switch_session(a.session_id)
print("A sees:", [m.content for m in manager.get_messages()])
# A sees: ['This belongs to A']

manager.shutdown()
```

### 5. Startup singleton + interactive selection

```python
from chat_manager.startup import (
    initialize_chat_manager,
    get_chat_manager,
    select_startup_session,
    shutdown_chat_manager,
)

manager = initialize_chat_manager()

# Interactive menu — injectable I/O makes it testable
select_startup_session(
    input_func=lambda prompt="": input(prompt),
    output_func=lambda text: print(text),
)

print(get_chat_manager().get_active_session().session_name)

shutdown_chat_manager()
```

### 6. Startup selection, headless (scripted)

```python
from chat_manager.startup import initialize_chat_manager, select_startup_session

manager = initialize_chat_manager()

# Answer "2" to the menu without touching stdin
session = select_startup_session(
    input_func=lambda prompt="": "2",
    output_func=lambda text: None,
)
print(session.session_name)
```

### 7. Using the backends directly

```python
from chat_manager.backend import (
    BackendConfig,
    PostgresChatStoreBackend,
    SimpleChatStoreBackend,
)
from llama_index.core.base.llms.types import ChatMessage

config = BackendConfig(connection_string="postgres+asyncpg://postgres:postgres@127.0.0.1:5432/llama_index_db")

backend = PostgresChatStoreBackend()
backend.connect(config)
backend.put_messages("my-key", [ChatMessage(role="user", content="Hello")])
print(backend.get_messages("my-key"))
print(backend.list_keys())
backend.close()
```

### 8. Using the storage connector directly

```python
from chat_manager.storage import CustomDBConnector
from chat_manager.user import User

connector = CustomDBConnector()
connector.connect()

user = connector.get_user_by_username("alice")
if user is None:
    user = connector.create_user(User(username="alice", chat_token_limit=8000))

for session in connector.list_sessions(user.user_id):
    print(session.session_name, session.is_active)

connector.close()
```

### 9. Reading and changing the user's settings

```python
from chat_manager import ChatHistoryManager

manager = ChatHistoryManager()
manager.initialize()

# What is set right now?
print(manager.get_user_settings().chat_token_limit)      # 5000

# Give the agent a longer memory.
manager.update_user_settings(chat_token_limit=12000)
print(manager.get_user_settings().chat_token_limit)      # 12000

# The live buffer picked the new limit up — no session switch needed.
print(manager.get_memory_buffer().token_limit)            # 12000
```

### 10. Handling chat commands programmatically

```python
from chat_manager.commands.handler import is_chat_command, handle_chat_command

if is_chat_command("\\chat-sessions"):
    print(handle_chat_command("\\chat-sessions"))

print(handle_chat_command("\\chat-create Refactor custom"))
print(handle_chat_command("\\chat-info"))
```

---

## CLI Commands

All commands are entered at the agent's interactive prompt and are prefixed with a backslash.
They are handled by the agent's main loop **before** the LLM is invoked, so they cost no tokens
and cannot be triggered by the model.

> **Naming tip:** `\chat-create` and `\chat-rename` split their arguments on whitespace, so a
> **single-word** name is required (e.g. `\chat-create Refactor custom`). The startup menu's
> `new <name>` form keeps the whole remainder of the line, so multi-word names such as
> `new Postgres migration` work there. The Python API (`manager.create_session(name=...)`) has no
> such restriction.

| Command | Alias | Description |
|---------|-------|-------------|
| `\chat-sessions` | `\chat-list` | List all sessions with ID, name, type, active marker, and creation time. |
| `\chat-select <session_id>` | — | Switch the active session. |
| `\chat-create <name> [type]` | — | Create a session. Type is `general`, `project`, or `custom` (default `custom`). **The name must be a single word** — the parser splits on whitespace, so a multi-word name is truncated. Use the startup menu's `new <name>` form (which keeps the full name) or the Python API for multi-word names. |
| `\chat-delete <session_id>` | — | Delete a session. Refuses to delete the active one. |
| `\chat-rename <session_id> <new name>` | — | Rename a session. |
| `\chat-info` | — | Show details of the active session (ID, name, type, chat key, timestamps). |
| `\chat-clear` | — | Delete all messages in the active session, keeping the session. |
| `\chat-user` | — | Show the current user's settings. |
| `\chat-user get <key>` | — | Show one setting. |
| `\chat-user set <key> <value>` | — | Change one setting. The change is validated, persisted, and applied to the live memory buffer. |
| `\chat-user help` | — | List the settings, their ranges and their usage. |

### Sample session

```
>>> \chat-sessions
Sessions for user 'kbush':
ID                                     Name                 Type       Active   Created
----------------------------------------------------------------------------------------------------
7f2c1a44-6f0e-4a1c-9a3e-2b8d5c1e0f11   Postgres migration   custom              2026-10-20 10:02
3d9b8e12-4c7a-4d8b-a1f2-9e3c6b0d5a44   Project Chat         project             2026-10-20 09:14
32f317d6-727d-4225-9ec7-7fb70f155356   General Chat         general    ✓        2026-10-20 09:14

>>> \chat-select 7f2c1a44-6f0e-4a1c-9a3e-2b8d5c1e0f11
Switched to session: 'Postgres migration' (custom)

>>> \chat-info
Active session for user 'kbush':
  ID:       7f2c1a44-6f0e-4a1c-9a3e-2b8d5c1e0f11
  Name:     Postgres migration
  Type:     custom
  Chat key: chat-custom-7f2c1a44-6f0e-4a1c-9a3e-2b8d5c1e0f11-3f2a1b9c
  Created:  2026-10-20 10:02
  Updated:  2026-10-20 10:05

>>> \chat-clear
Cleared message history for session 'Postgres migration'.
```

### Startup menu

```
Active session: 'General Chat'
Available sessions:
  * 1. General Chat [general] (created 2026-10-20 09:14)
    2. Project Chat [project] (created 2026-10-20 09:14)
    3. Postgres migration [custom] (created 2026-10-20 10:02)
  * = currently active
Select a session [1-3], 'new <name>' to create one, or Enter to keep the current one:
```

---

## User settings

The `users` table is the home of the user's *preferences*. The settings API reads and writes
them; the `\chat-user` command is the operator's view onto the same values.

### The settings

| Key | Type | Default | Range | Writable | Meaning |
|-----|------|---------|-------|----------|---------|
| `chat_token_limit` | int | `5000` | `256` – `1 000_000` | yes | Maximum number of **chat-history** tokens kept in the memory buffer of the active session. Older messages are dropped when the budget is exceeded. |
| `backend_type` | string | `postgres` | — | no | The storage backend provisioned for this user. Assigned on first login; shown for reference. |

### The naming

The setting was called `token_limit` until the rename documented in
`investigate/chat-manager-user-settings/PROPOSAL_chat_token_limit.md`. The old name says the
unit but not the scope, and the scope is the interesting part: *whose* tokens? The codebase
uses `token_limit` for at least three other things — the model's `context_window`, the legacy
`TORVALDS_TOKEN_LIMIT`, and the dead `TOKEN_LIMITS` constant in both orchestrators.

`chat_token_limit` is the canonical name. The old name keeps working in three places:

| Where | How |
|-------|-----|
| The database | The column is renamed in place on connect — the values are kept. |
| The Python API | `User.token_limit` is a deprecated property; `User(token_limit=…)` still works; `to_dict()` carries both keys; `from_dict()` accepts either. |
| The command | `\chat-user set token_limit 12000` still works — `token_limit` is a registered alias. The reply always names the canonical key. |

### The API

```python
from chat_manager import ChatHistoryManager

manager = ChatHistoryManager()
manager.initialize()

# Read
settings = manager.get_user_settings()
print(settings.chat_token_limit)      # 5000
print(settings.get("token_limit"))    # 5000  — the alias resolves too

# Write
manager.update_user_settings(chat_token_limit=12000)
manager.set_chat_token_limit(8000)    # the same thing, shorter
```

`update_user_settings()` validates every value **before** writing anything, so a bad value
never leaves the settings half-updated, and it drops the cached memory buffer — a changed
limit is live on the next turn, not after the next session switch.

Invalid input raises `SettingError`:

```python
from chat_manager import SettingError

try:
    manager.update_user_settings(chat_token_limit=5)
except SettingError as exc:
    print(exc)   # The chat token limit must be at least 256 (got 5).
```

### The command

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

>>> \chat-user help
User settings:

  chat_token_limit  (read-write)
      Maximum number of chat-history tokens kept in the memory buffer of the active session. …
      Accepted range: 256 - 1000000

  backend_type  (read-only)
      Storage backend provisioned for this user. …
      Default: postgres
```

---

## Agent Integration

The integration lives in `agent-torvalds.py` and `agent_chat_memory.py`.

### Wiring

```python
# agent-torvalds.py — startup
from chat_manager.startup import (
    initialize_chat_manager,
    get_chat_manager,
    shutdown_chat_manager,
)
from chat_manager.commands.handler import is_chat_command, handle_chat_command

if chat_history_enabled:
    manager = initialize_chat_manager()
    if not args.no_session_select:
        select_startup_session(
            input_func=lambda prompt="": console.input(prompt),
            output_func=lambda text: console.print(text),
        )
```

```python
# agent-torvalds.py — main loop
if chat_history_enabled and is_chat_command(cmd):
    chat_response = handle_chat_command(cmd)
    if chat_response:
        console.print(chat_response)
    continue
```

### Compatibility layer

`agent_chat_memory.py` keeps its historical public API (`get_chat_store()`, `get_chat_memory()`,
`chat_memory` proxy, `get_all_tools()`) but now **delegates to the ChatHistoryManager first**:

```python
manager_buffer = _get_manager_memory_buffer()   # ChatHistoryManager path
if manager_buffer is not None:
    return manager_buffer
# ... otherwise the legacy single-key path
```

If the manager is unavailable — the package is not importable, the database is down, or the user
passed `--no-chat-history` — the legacy single-key behaviour is used, so the agent always has a
working memory buffer. `get_active_chat_key()` was added to expose the active session's chat key
to the rest of the agent.

### Shutdown

`_shutdown_chat_manager()` is called on every exit path — `EOFError`, `KeyboardInterrupt`, and
`\exit` / `\quit` — so connections are always released cleanly.

---

## API Reference

### `chat_manager` (package root)

```python
from chat_manager import (
    ChatHistoryManager, User, Session, SessionType,
    UserSettings, SettingSpec, SettingError, SETTING_SPECS,
    DEFAULT_CHAT_TOKEN_LIMIT, MIN_CHAT_TOKEN_LIMIT, MAX_CHAT_TOKEN_LIMIT,
    normalize_setting_key, validate_chat_token_limit, validate_setting_value,
)
```

### `chat_manager.manager.ChatHistoryManager`

```python
ChatHistoryManager(storage_uri: str | None = None, llama_uri: str | None = None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `storage_uri` | `Optional[str]` | SQLAlchemy URI for the metadata tables. Falls back to `TORVALDS_STORAGE_URI`, then to the `TORVALDS_PG_*` defaults. |
| `llama_uri` | `Optional[str]` | LlamaIndex message-store URI. Falls back to `TORVALDS_LLAMA_URI`, then to the `TORVALDS_PG_*` defaults. |

### `chat_manager.backend`

```python
from chat_manager.backend import (
    BackendConfig,          # connection_string, table_name, extra_params
    ChatStoreBackend,       # abstract base (extends BaseChatStore)
    PostgresChatStoreBackend,
    SimpleChatStoreBackend,
)
```

### `chat_manager.storage`

```python
from chat_manager.storage import Base, User, Session, CustomDBConnector
```

### `chat_manager.commands`

```python
from chat_manager.commands import (
    cmd_chat_sessions, cmd_chat_select, cmd_chat_create,
    cmd_chat_delete, cmd_chat_rename, cmd_chat_info, cmd_chat_clear,
    cmd_chat_user, cmd_chat_user_get, cmd_chat_user_set, cmd_chat_user_help,
)
```

### `chat_manager.settings`

```python
from chat_manager.settings import (
    UserSettings, SettingSpec, SettingError, SETTING_SPECS, SETTINGS_BY_KEY,
    DEFAULT_CHAT_TOKEN_LIMIT, MIN_CHAT_TOKEN_LIMIT, MAX_CHAT_TOKEN_LIMIT,
    normalize_setting_key, validate_chat_token_limit, validate_setting_value,
)
```

### `chat_manager.startup`

```python
from chat_manager.startup import (
    initialize_chat_manager, get_chat_manager,
    shutdown_chat_manager, is_chat_manager_initialized,
    select_startup_session,
)
```

### `chat_manager.session_selector`

```python
from chat_manager.session_selector import (
    format_session_list, select_session_interactively,
)
```

---

## Testing

The package ships **175 unit tests** across ten modules, all hermetic — no live database is
required.

| Test module | Tests | Covers |
|-------------|-------|---------|
| `test_user_settings.py` | 38 | The settings API, the `\chat-user` command, the renamed field and its compatibility seams |
| `test_manager.py` | 28 | Initialisation, session CRUD, message buffer, plan-mandated API surface |
| `test_commands.py` | 22 | Every `\chat-*` command and the dispatcher |
| `test_settings.py` | 20 | The settings module — validation, aliases, the `UserSettings` snapshot |
| `test_backend.py` | 14 | Backend contract and error handling |
| `test_storage.py` | 12 | Connector lifecycle, user and session CRUD |
| `test_migration.py` | 10 | The `token_limit` → `chat_token_limit` column migration |
| `test_models.py` | 11 | `User` / `Session` dataclasses, `SessionType` |
| `test_session_selector.py` | 10 | Menu formatting and the interactive selection loop |
| `test_startup.py` | 7 | Singleton lifecycle and startup hooks |

### Running the tests

```bash
# From the repository root
python -m pytest chat_manager/tests -v

# The whole suite (pytest.ini already includes chat_manager/tests in testpaths)
python -m pytest -v
```

`pytest.ini` is configured with `testpaths = tests chat_manager/tests`, so the chat manager suite is
collected by a default run. `chat_manager/tests/conftest.py` clears the `TORVALDS_STORAGE_URI`,
`TORVALDS_LLAMA_URI`, and `TORVALDS_CHAT_KEY` environment variables around every test, so a
developer's local configuration cannot influence the results.

---

## Design Documents

The module was developed against a written design. The source documents live in
`investigate/ChatHistoryManager/`:

| Document | Contents |
|----------|----------|
| `ChatHistoryManager.md` | Original task definition: requirements for backend-agnostic design, multi-session and multi-user support, database-only persistence. |
| `storage-proposal.md` | Storage layout, dual-connector architecture, SQL schema, and the rationale for keeping LlamaIndex's schema separate. |
| `implementation-plan.md` | The 11-step implementation plan (skeleton → models → backends → storage → manager → commands → startup → agent integration → tests). |
| `STEP_AUDIT.md` | Audit that found nine defects in the initial implementation (broken session isolation, dead fallback path, a dispatcher crash, and multi-user isolation gaps) together with the twelve-step remediation plan. |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ChatHistoryManager not initialized.` | A `\chat-*` command was issued before startup, or `--no-chat-history` was passed. | Remove the flag; ensure `initialize_chat_manager()` runs at startup. |
| `Chat history manager unavailable: …` at startup | The metadata database is unreachable. | Check `TORVALDS_STORAGE_URI` / `TORVALDS_PG_*` and that the database exists. |
| `Using in-memory message backend (fallback)` in the log | PostgreSQL chat store is unavailable. | Check `TORVALDS_LLAMA_URI` and the `llama_index_db` database. Sessions still work; only message persistence is lost. |
| `ModuleNotFoundError: No module named 'chat_manager'` | The agent is not running from the repository root. | `cd` to the root, or add it to `PYTHONPATH`. |
| `ModuleNotFoundError: No module named 'sqlalchemy'` | `SQLAlchemy` is not installed and is not yet in `requirements.txt`. | `pip install "SQLAlchemy>=2.0"` and add it to `requirements.txt`. |
| `Session '<id>' not found.` | The ID is wrong, or the session belongs to a different OS user. | Run `\chat-sessions` to list the IDs you actually own. |
| `Cannot delete the active session.` | Guard rail — the live session cannot be deleted. | Switch to another session first, then delete. |
| Messages from a previous topic still appear | The legacy `TORVALDS_CHAT_KEY` is in use, so the General session points at the old flat history. | Unset `TORVALDS_CHAT_KEY` to start with a clean per-session history. |
| `No sessions found.` at startup | The metadata database is empty and creation failed. | Check the database permissions and the startup log output. |
| `Unknown setting '…'` | The setting name is not one of the known settings. | Run `\chat-user help` for the list. |
| `The chat token limit must be at least 256` | The value is below `MIN_CHAT_TOKEN_LIMIT`. | Pick a value between 256 and 1 000 000. |
| `The setting 'backend_type' is read-only` | The setting is assigned when the user is provisioned. | It cannot be changed at runtime. |
| A changed limit seems to have no effect | The memory buffer caches the limit it was built with. | `update_user_settings()` drops the cache, so the new limit is live immediately. If you changed the value in the database directly, switch sessions or run `\chat-clear` to rebuild the buffer. |

---

## License

This module is part of the Torvalds AI Agent Toolkit, licensed under the **MIT License**.
