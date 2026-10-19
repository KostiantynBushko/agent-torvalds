# ChatHistoryManager — Storage Layout Proposal

## 1. Overview

The ChatHistoryManager uses a **SQL-based database** for all persistent state.  
**No local config files or cache files are used.** Everything — user identities, session metadata, active session state, and user preferences — lives in the database.

The storage layer is **backend-agnostic** and supports any SQL-compatible database:
- PostgreSQL
- MySQL / MariaDB
- SQLite
- Any other SQL-like database

| Data Type | Storage | Characteristics |
|---|---|---|
| **User Identities** | `users` table | Multi-user support, per-user preferences |
| **Session Metadata** | `chat_sessions` table | Scoped per user, active state tracked in DB |
| **Active Session** | `chat_sessions.is_active` | One active session per user, stored in DB |
| **User Preferences** | `users` table | Backend type, token limit per user |

---

## 2. Database Schema

### 2.1 Users Table

Stores user identity and per-user preferences.

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    backend_type  TEXT NOT NULL DEFAULT 'postgres',
    token_limit   INTEGER NOT NULL DEFAULT 5000,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**
| Field | Type | Default | Description |
|---|---|---|---|
| `user_id` | TEXT (UUID) | — | Primary key |
| `username` | TEXT | — | OS username, unique constraint |
| `backend_type` | TEXT | `'postgres'` | Preferred storage backend |
| `token_limit` | INTEGER | `5000` | Max tokens in memory buffer |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | User creation time |
| `updated_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | Last update time |

**User Identification:**
- On first run: `os.getlogin()` → look up in `users` table
- If not found: auto-create user with default preferences
- Future: explicit login mechanism

---

### 2.2 Chat Sessions Table

Stores session metadata scoped per user.

```sql
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
```

**Fields:**
| Field | Type | Default | Description |
|---|---|---|---|
| `session_id` | TEXT (UUID) | — | Primary key |
| `user_id` | TEXT | — | FK → `users.user_id`, CASCADE delete |
| `session_name` | TEXT | — | Human-readable name |
| `session_type` | TEXT | — | `general`, `project`, or `custom` |
| `chat_key` | TEXT | — | Maps to LlamaIndex Table A, unique |
| `metadata` | TEXT | `'{}'` | Optional JSON metadata |
| `created_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | Session creation time |
| `updated_at` | TIMESTAMP | `CURRENT_TIMESTAMP` | Last update time |
| `is_active` | BOOLEAN | `FALSE` | Active session flag (one TRUE per user) |

**Indexes:**
```sql
CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_type ON chat_sessions(session_type);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON chat_sessions(user_id, is_active);
```

---

### 2.3 Pre-seeded Sessions

On first run for a new user, two default sessions are created:

| session_id | user_id | session_name | session_type | chat_key | is_active |
|---|---|---|---|---|---|
| `<uuid>` | `<user_id>` | General Chat | `general` | `chat-general-<user_id>` | `TRUE` |
| `<uuid>` | `<user_id>` | Project Chat | `project` | `chat-project-<user_id>` | `FALSE` |

The `general` session is activated by default.

---

## 3. Active Session Tracking

### How It Works

1. **On startup:**
   ```sql
   SELECT * FROM chat_sessions 
   WHERE user_id = ? AND is_active = TRUE;
   ```
   - If result exists → restore that session
   - If no result → activate the `general` session

2. **On session switch:**
   ```sql
   -- Deactivate all sessions for this user
   UPDATE chat_sessions SET is_active = FALSE WHERE user_id = ?;
   
   -- Activate new session
   UPDATE chat_sessions SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP 
   WHERE session_id = ?;
   ```

3. **On session creation:**
   - New session is created with `is_active = FALSE`
   - User must explicitly select it via `\chat-select`

### Multi-User Isolation

Each user has their own set of sessions:
```sql
-- List sessions for current user only
SELECT * FROM chat_sessions WHERE user_id = ?;

-- Each user can have their own "General Chat" and "Project Chat"
-- Sessions are fully isolated by user_id
```

---

## 4. Backend Abstraction

The storage layer exposes a **backend-agnostic interface** so the database engine can be swapped without changing application code.

### Storage Backend Interface

```python
class StorageBackend(ABC):
    """Abstract interface for SQL-based session storage."""

    @abstractmethod
    def connect(self, connection_string: str) -> None: ...

    @abstractmethod
    def execute(self, query: str, params: tuple = ()) -> Any: ...

    @abstractmethod
    def execute_many(self, query: str, params_list: list) -> None: ...

    @abstractmethod
    def create_schema(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...
```

### Supported Backends

| Backend | Driver | Connection String Format |
|---|---|---|
| **PostgreSQL** | `asyncpg` / `psycopg2` | `postgresql://user:pass@host:5432/dbname` |
| **MySQL** | `mysql-connector-python` | `mysql://user:pass@host:3306/dbname` |
| **SQLite** | `sqlite3` (stdlib) | `sqlite:///path/to/chat_manager.db` |

### Configuration

Database connection is configured via environment variables:

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_STORAGE_URI` | `sqlite:////tmp/torvalds_chat.db` | Database connection URI |
| `TORVALDS_STORAGE_BACKEND` | `auto` | Backend type: `postgres`, `mysql`, `sqlite`, or `auto` |

When set to `auto`, the system detects the backend from the URI scheme.

---

## 5. Migration from Current Setup

**Current:**
- `TORVALDS_CHAT_KEY` env var → single hardcoded key
- No session persistence
- No user identification

**Migration Path:**
1. On first run with new system, detect if `TORVALDS_CHAT_KEY` is set
2. Create user from `os.getlogin()`
3. If old key exists, create a `general` session using that key
4. Migrate existing messages from old key to new session (if any)
5. Pre-seed `project` session
6. Set `general` session as active
7. Subsequent runs use new system exclusively

---

## 6. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `asyncpg` | 0.30.0 (installed) | PostgreSQL async driver |
| `psycopg2-binary` | 2.9.12 (installed) | PostgreSQL sync driver |
| `mysql-connector-python` | 26.7.0 (installed) | MySQL driver |
| `sqlite3` | stdlib | SQLite driver |
| `uuid` | stdlib | ID generation |
| `os` | stdlib | User identification |

**No new dependencies required.**

---

## 7. Security & Permissions

- No sensitive data stored (no passwords, no tokens)
- Foreign key constraints ensure referential integrity
- `ON DELETE CASCADE` ensures sessions are cleaned up when user is deleted
- Connection strings configured via environment variables

---

## 8. Database Operations Reference

### Common Queries

```sql
-- Get current user
SELECT * FROM users WHERE username = ?;

-- List all sessions for current user
SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC;

-- Get active session for current user
SELECT * FROM chat_sessions WHERE user_id = ? AND is_active = TRUE;

-- Switch active session
UPDATE chat_sessions SET is_active = FALSE WHERE user_id = ?;
UPDATE chat_sessions SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP 
WHERE session_id = ?;

-- Create new session
INSERT INTO chat_sessions (session_id, user_id, session_name, session_type, chat_key)
VALUES (?, ?, ?, ?, ?);

-- Delete session
DELETE FROM chat_sessions WHERE session_id = ?;
```

---

## 9. Summary

| Concern | Solution |
|---|---|
| Backend agnostic | SQL interface supporting PostgreSQL, MySQL, SQLite |
| User identification | `users` table, auto-provisioned from OS username |
| Multi-user support | Sessions scoped by `user_id` FK |
| Active session tracking | `is_active` flag in `chat_sessions` table |
| User preferences | `backend_type`, `token_limit` in `users` table |
| No config/cache files | **All state in SQL database** |
| Migration | Auto-detect old env var, create initial user & sessions |
| Dependencies | None new — all drivers already installed |
