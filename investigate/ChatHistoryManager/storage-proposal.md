# ChatHistoryManager — Storage Layout Proposal

## 1. Overview

The ChatHistoryManager uses a **single SQLite database** for all persistent state.  
**No local config files or cache files are used.** Everything — user identities, session metadata, active session state, and user preferences — lives in the database.

| Data Type | Storage | Characteristics |
|---|---|---|
| **User Identities** | `users` table | Multi-user support, per-user preferences |
| **Session Metadata** | `chat_sessions` table | Scoped per user, active state tracked in DB |
| **Active Session** | `chat_sessions.is_active` | One active session per user, stored in DB |
| **User Preferences** | `users` table | Backend type, token limit per user |

---

## 2. Database Location

The SQLite database is stored in the platform-native data directory using `platformdirs`:

### Linux
```
~/.local/share/torvalds/chat_manager.db
```

### Windows
```
%APPDATA%\torvalds\chat_manager.db
```

### macOS
```
~/Library/Application Support/torvalds/chat_manager.db
```

---

## 3. Database Schema

### 3.1 Users Table

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

### 3.2 Chat Sessions Table

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

### 3.3 Pre-seeded Sessions

On first run for a new user, two default sessions are created:

| session_id | user_id | session_name | session_type | chat_key | is_active |
|---|---|---|---|---|---|
| `<uuid>` | `<user_id>` | General Chat | `general` | `chat-general-<user_id>` | `TRUE` |
| `<uuid>` | `<user_id>` | Project Chat | `project` | `chat-project-<user_id>` | `FALSE` |

The `general` session is activated by default.

---

## 4. Active Session Tracking

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

## 5. Directory Creation Strategy

```python
import platformdirs
import os

pd = platformdirs.PlatformDirs('torvalds', 'agent-torvalds')

def ensure_directories():
    """Create data directory if it doesn't exist."""
    os.makedirs(pd.user_data_dir, exist_ok=True)
```

Only the data directory is created. No config or cache directories are needed.

---

## 6. Platform Compatibility Matrix

| Feature | Linux | Windows | macOS |
|---|---|---|---|
| Data dir | `~/.local/share/torvalds/` | `%APPDATA%\torvalds\` | `~/Library/Application Support/torvalds/` |
| Database | `chat_manager.db` | `chat_manager.db` | `chat_manager.db` |
| Config file | **None** | **None** | **None** |
| Cache file | **None** | **None** | **None** |

---

## 7. Migration from Current Setup

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

## 8. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `platformdirs` | 4.13.0 (installed) | Platform-aware directory resolution |
| `sqlite3` | stdlib | User & session metadata storage |
| `uuid` | stdlib | ID generation |
| `os` | stdlib | User identification |

**No new dependencies required.**

---

## 9. Security & Permissions

- SQLite DB: `0644` (readable/writable by user only)
- No sensitive data stored (no passwords, no tokens)
- All paths under user home directory
- Foreign key constraints ensure referential integrity
- `ON DELETE CASCADE` ensures sessions are cleaned up when user is deleted

---

## 10. Database Operations Reference

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

## 11. Summary

| Concern | Solution |
|---|---|
| Platform compatibility | `platformdirs` library |
| User identification | `users` table, auto-provisioned from OS username |
| Multi-user support | Sessions scoped by `user_id` FK |
| Active session tracking | `is_active` flag in `chat_sessions` table |
| User preferences | `backend_type`, `token_limit` in `users` table |
| No config/cache files | **All state in SQLite database** |
| Migration | Auto-detect old env var, create initial user & sessions |
| Dependencies | None new — all stdlib or already installed |
