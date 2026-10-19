# ChatHistoryManager — Implementation Plan

## Module Location
The **ChatHistoryManager** will be implemented as a separate, self-contained module at:

```
chat-manager/
```

located in the **project root folder**.

---

## 1. Module Structure

```
chat-manager/
├── __init__.py                  # Package init, public API exports
├── manager.py                   # ChatHistoryManager core class
├── session.py                   # Session data model
├── backend/
│   ├── __init__.py              # Backend interface exports
│   ├── base.py                  # ChatStoreBackend ABC
│   ├── postgres.py              # PostgresChatStoreBackend implementation
│   └── simple.py                # SimpleChatStoreBackend (in-memory fallback)
├── storage/
│   ├── __init__.py              # Storage exports
│   ├── session_store.py         # Session metadata persistence (SQLite/JSON)
│   └── config_store.py          # Active session config persistence
├── commands/
│   ├── __init__.py              # Command handlers exports
│   └── chat_commands.py         # \chat-* command implementations
├── startup/
│   ├── __init__.py              # Startup flow exports
│   └── session_selector.py      # Startup chat selection UI
└── tests/
    ├── __init__.py
    ├── test_manager.py
    ├── test_backend.py
    └── test_session_store.py
```

---

## 2. Step-by-Step Implementation Plan

### Step 1: Create Module Skeleton & Data Models
**Files:** `chat-manager/__init__.py`, `chat-manager/session.py`

- Create the `chat-manager/` directory structure
- Define `Session` dataclass/model with fields:
  - `session_id: UUID`
  - `session_name: str`
  - `session_type: SessionType` (enum: `general`, `project`, `custom`)
  - `chat_key: str` (maps to LlamaIndex Table A)
  - `metadata: dict` (optional JSON)
  - `created_at: datetime`
  - `updated_at: datetime`
  - `is_active: bool`
- Define `SessionType` enum

**Deliverable:** Module skeleton with data models, importable without errors.

---

### Step 2: Backend Adapter Interface
**Files:** `chat-manager/backend/base.py`, `chat-manager/backend/__init__.py`

- Define `ChatStoreBackend` ABC with methods:
  - `put_messages(chat_key: str, messages: list) -> None`
  - `get_messages(chat_key: str) -> list`
  - `delete_messages(chat_key: str) -> None`
  - `list_keys() -> list[str]`
  - `close() -> None`
- Define `BackendConfig` dataclass for connection parameters

**Deliverable:** Abstract backend interface ready for implementations.

---

### Step 3: Backend Implementations
**Files:** `chat-manager/backend/postgres.py`, `chat-manager/backend/simple.py`

- Implement `PostgresChatStoreBackend` wrapping existing `PostgresChatStore`
  - Reuses current PostgreSQL connection from env vars
  - Delegates to LlamaIndex's `PostgresChatStore` methods
- Implement `SimpleChatStoreBackend` as in-memory fallback
  - Uses LlamaIndex's `SimpleChatStore`
  - Activates when PostgreSQL is unavailable

**Deliverable:** Two working backend implementations, tested independently.

---

### Step 4: Session Metadata Storage
**Files:** `chat-manager/storage/session_store.py`, `chat-manager/storage/config_store.py`

- Implement `SessionStore` for persisting session metadata (Table B)
  - Primary: SQLite database with schema:
    ```sql
    CREATE TABLE chat_sessions (
        session_id    TEXT PRIMARY KEY,
        session_name  TEXT NOT NULL,
        session_type  TEXT NOT NULL,
        chat_key      TEXT NOT NULL UNIQUE,
        metadata      TEXT,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active     BOOLEAN DEFAULT FALSE
    );
    ```
  - Fallback: JSON file storage if SQLite unavailable
- Implement `ConfigStore` for persisting active session ID
  - Stores in `~/.torvalds/chat_config.json`
  - Fields: `last_active_session_id`, `token_limit`, `backend_type`

**Deliverable:** Session metadata persistence with SQLite + JSON fallback.

---

### Step 5: ChatHistoryManager Core
**Files:** `chat-manager/manager.py`

- Implement `ChatHistoryManager` class with:
  - **Session CRUD:**
    - `list_sessions() -> list[Session]`
    - `create_session(name: str, session_type: SessionType, metadata: dict = None) -> Session`
    - `get_session(session_id: str) -> Session`
    - `update_session(session_id: str, **kwargs) -> Session`
    - `delete_session(session_id: str) -> bool`
    - `rename_session(session_id: str, new_name: str) -> Session`
  - **Active Session Management:**
    - `select_session(session_id: str) -> Session`
    - `get_active_session() -> Session`
    - `get_active_chat_key() -> str`
  - **Message Operations:**
    - `put_message(content: str, role: str) -> None`
    - `get_messages() -> list`
    - `clear_messages() -> None`
  - **Initialization:**
    - `initialize(backend: ChatStoreBackend) -> None`
    - `load_config() -> None`
    - `save_config() -> None`
  - **Pre-seeding:**
    - Auto-create `general` and `project` sessions on first run

**Deliverable:** Fully functional ChatHistoryManager with all core operations.

---

### Step 6: Command Handlers
**Files:** `chat-manager/commands/chat_commands.py`

- Implement command handlers for `\chat-*` commands:
  - `\chat-list` — List all sessions with ID, name, type, created date
  - `\chat-create <name>` — Create new custom session
  - `\chat-select <id>` — Switch to specified session
  - `\chat-delete <id>` — Delete session (with confirmation)
  - `\chat-rename <id> <new_name>` — Rename session
  - `\chat-info` — Show current session details
  - `\chat-clear` — Clear current session messages
- Each command returns formatted output string for console display

**Deliverable:** Command handlers integrated with ChatHistoryManager.

---

### Step 7: Startup Session Selection
**Files:** `chat-manager/startup/session_selector.py`

- Implement startup flow:
  1. Load config → get last active session ID
  2. If valid session exists → propose it as default
  3. Present session list with numbered options
  4. Allow user to:
     - Select existing session (by number)
     - Create new session (type name)
     - Skip and use default
  5. Return selected session for agent initialization

**Deliverable:** Interactive startup session selector.

---

### Step 8: Integration with Agent
**Files:** `agent-torvalds.py`, `agent_chat_memory.py` (compatibility layer)

- Update `agent-torvalds.py`:
  - Import `ChatHistoryManager` from `chat-manager`
  - Replace direct `PostgresChatStore` usage with manager
  - Wire `\chat-*` commands to command handlers
  - Call startup session selector on agent init
- Update `agent_chat_memory.py`:
  - Add compatibility layer that delegates to `ChatHistoryManager`
  - Maintain backward compatibility for existing code

**Deliverable:** Agent fully integrated with ChatHistoryManager.

---

### Step 9: Testing & Validation
**Files:** `chat-manager/tests/`

- Unit tests:
  - Session CRUD operations
  - Backend adapter methods
  - Config persistence
  - Command handler outputs
- Integration tests:
  - Full startup flow
  - Session switching with message routing
  - Backend swap without agent changes
- Verify:
  - PostgreSQL backend works
  - In-memory fallback works
  - Session isolation (messages don't leak between sessions)

**Deliverable:** Test suite with >80% coverage.

---

## 3. Dependencies

| Dependency | Purpose |
|---|---|
| `llama_index` | Existing dependency, provides `PostgresChatStore`, `SimpleChatStore`, `ChatMemoryBuffer` |
| `sqlite3` | Standard library, session metadata storage |
| `uuid` | Standard library, session ID generation |
| `json` | Standard library, config persistence |

No new external dependencies required.

---

## 4. Migration Path

1. **Phase 1:** `chat-manager/` module created alongside existing `agent_chat_memory.py`
2. **Phase 2:** Agent uses `ChatHistoryManager` internally, `agent_chat_memory.py` becomes thin wrapper
3. **Phase 3:** `agent_chat_memory.py` deprecated, fully replaced by `chat-manager`
4. **Phase 4:** Backend swap tested (e.g., PostgreSQL → SQLite)

---

## 5. Success Criteria

- [ ] Multiple sessions can be created and switched between
- [ ] Messages are isolated per session
- [ ] Startup presents session selection UI
- [ ] Last active session is restored on restart
- [ ] Backend can be swapped without agent code changes
- [ ] All `\chat-*` commands work correctly
- [ ] Existing agent functionality is preserved
- [ ] Tests pass with both PostgreSQL and in-memory backends
