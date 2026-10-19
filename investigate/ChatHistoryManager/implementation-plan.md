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
├── user.py                      # User data model
├── backend/
│   ├── __init__.py              # Backend interface exports
│   ├── base.py                  # ChatStoreBackend ABC
│   ├── postgres.py              # PostgresChatStoreBackend implementation
│   └── simple.py                # SimpleChatStoreBackend (in-memory fallback)
├── storage/
│   ├── __init__.py              # Storage exports
│   ├── database.py              # SQLite database connection & schema
│   ├── user_store.py            # User CRUD operations
│   └── session_store.py         # Session CRUD operations
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
    ├── test_user_store.py
    └── test_session_store.py
```

---

## 2. Step-by-Step Implementation Plan

### Step 1: Create Module Skeleton & Data Models
**Files:** `chat-manager/__init__.py`, `chat-manager/session.py`, `chat-manager/user.py`

- Create the `chat-manager/` directory structure
- Define `User` dataclass/model with fields:
  - `user_id: UUID`
  - `username: str` (unique, from OS login)
  - `backend_type: str` (default: `"postgres"`)
  - `token_limit: int` (default: `5000`)
  - `created_at: datetime`
  - `updated_at: datetime`
- Define `Session` dataclass/model with fields:
  - `session_id: UUID`
  - `user_id: UUID` (FK → users)
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

### Step 4: SQLite Database & Schema
**Files:** `chat-manager/storage/database.py`

- Implement `ChatDatabase` class:
  - Manages SQLite connection to `~/.local/share/torvalds/chat_manager.db`
  - Creates schema on first run
  - Provides connection pool / context manager
- **Schema:**

```sql
-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    backend_type  TEXT NOT NULL DEFAULT 'postgres',
    token_limit   INTEGER NOT NULL DEFAULT 5000,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    session_name  TEXT NOT NULL,
    session_type  TEXT NOT NULL CHECK(session_type IN ('general', 'project', 'custom')),
    chat_key      TEXT NOT NULL UNIQUE,
    metadata      TEXT DEFAULT '{}',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active     BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_type ON chat_sessions(session_type);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON chat_sessions(user_id, is_active);
```

**Deliverable:** Database layer with schema creation and connection management.

---

### Step 5: User Store
**Files:** `chat-manager/storage/user_store.py`

- Implement `UserStore` class:
  - `get_or_create_user(username: str) -> User`
    - Looks up by username, creates if not exists
    - Auto-detects backend type from env vars
  - `get_user(user_id: str) -> User`
  - `update_user(user_id: str, **kwargs) -> User`
  - `list_users() -> list[User]`
- On first run, auto-create user from `os.getlogin()`

**Deliverable:** User persistence layer with auto-provisioning.

---

### Step 6: Session Store
**Files:** `chat-manager/storage/session_store.py`

- Implement `SessionStore` class:
  - `list_sessions(user_id: str) -> list[Session]`
  - `create_session(user_id: str, name: str, session_type: SessionType, metadata: dict = None) -> Session`
  - `get_session(session_id: str) -> Session`
  - `update_session(session_id: str, **kwargs) -> Session`
  - `delete_session(session_id: str) -> bool`
  - `set_active_session(user_id: str, session_id: str) -> Session`
    - Sets `is_active = TRUE` for target, `FALSE` for all others of same user
  - `get_active_session(user_id: str) -> Session | None`
  - `preseed_user_sessions(user_id: str) -> None`
    - Creates `general` and `project` sessions if user has none

**Deliverable:** Session persistence layer with active session tracking in DB.

---

### Step 7: ChatHistoryManager Core
**Files:** `chat-manager/manager.py`

- Implement `ChatHistoryManager` class with:
  - **Initialization:**
    - `initialize() -> None`
      - Open DB connection
    - `identify_user() -> User`
      - Get OS username, call `UserStore.get_or_create()`
  - **Session CRUD (delegates to SessionStore):**
    - `list_sessions() -> list[Session]`
    - `create_session(name: str, session_type: SessionType, metadata: dict = None) -> Session`
    - `get_session(session_id: str) -> Session`
    - `update_session(session_id: str, **kwargs) -> Session`
    - `delete_session(session_id: str) -> bool`
    - `rename_session(session_id: str, new_name: str) -> Session`
  - **Active Session Management:**
    - `select_session(session_id: str) -> Session`
      - Calls `SessionStore.set_active_session()`
    - `get_active_session() -> Session`
      - Calls `SessionStore.get_active_session()`
    - `get_active_chat_key() -> str`
  - **Message Operations:**
    - `put_message(content: str, role: str) -> None`
    - `get_messages() -> list`
    - `clear_messages() -> None`
  - **Shutdown:**
    - `close() -> None`
      - Close DB connection, close backend

**Deliverable:** Fully functional ChatHistoryManager with all core operations.

---

### Step 8: Command Handlers
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

### Step 9: Startup Session Selection
**Files:** `chat-manager/startup/session_selector.py`

- Implement startup flow:
  1. Identify current user via `os.getlogin()`
  2. Call `UserStore.get_or_create(username)`
  3. Check if user has sessions; if not, call `preseed_user_sessions()`
  4. Load all sessions for this user from DB
  5. Check for active session (`is_active = TRUE`)
  6. If active session exists → propose it as default
  7. Present session list with numbered options
  8. Allow user to:
     - Select existing session (by number)
     - Create new session (type name)
     - Skip and use default
  9. Update `is_active` flag in DB for selected session
  10. Return selected session for agent initialization

**Deliverable:** Interactive startup session selector.

---

### Step 10: Integration with Agent
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

### Step 11: Testing & Validation
**Files:** `chat-manager/tests/`

- Unit tests:
  - User CRUD operations
  - Session CRUD operations
  - Backend adapter methods
  - Active session switching (DB state verification)
  - Command handler outputs
- Integration tests:
  - Full startup flow
  - Session switching with message routing
  - Multi-user isolation (sessions don't leak between users)
  - Backend swap without agent changes
- Verify:
  - PostgreSQL backend works
  - In-memory fallback works
  - Session isolation (messages don't leak between sessions)
  - **No local config/cache files are created**

**Deliverable:** Test suite with >80% coverage.

---

## 3. Dependencies

| Dependency | Purpose |
|---|---|
| `llama_index` | Existing dependency, provides `PostgresChatStore`, `SimpleChatStore`, `ChatMemoryBuffer` |
| `sqlite3` | Standard library, user & session metadata storage |
| `uuid` | Standard library, ID generation |
| `os` | Standard library, user identification |

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
- [ ] Last active session is restored on restart (from DB)
- [ ] Backend can be swapped without agent code changes
- [ ] All `\chat-*` commands work correctly
- [ ] Existing agent functionality is preserved
- [ ] Tests pass with both PostgreSQL and in-memory backends
- [ ] **No local config or cache files are used**
- [ ] **Multi-user support works (sessions scoped per user)**
