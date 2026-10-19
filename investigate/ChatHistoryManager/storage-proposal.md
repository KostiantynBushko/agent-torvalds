# ChatHistoryManager — Storage Layout Proposal

## 1. Overview

The ChatHistoryManager requires three types of persistent data:

| Type | Purpose | Characteristics |
|---|---|---|
| **Session Metadata** | Session definitions, names, types, mappings | Structured, queryable, grows over time |
| **Configuration** | User preferences, backend settings, defaults | Small, infrequently changed, critical |
| **Runtime Cache** | Current session ID, transient state | Fast access, can be regenerated |

---

## 2. Platform-Aware Directory Strategy

We use **`platformdirs`** (already installed, v4.13.0) to resolve platform-native directories.

### Linux

| Data Type | Directory | Example Path |
|---|---|---|
| Config | `~/.config/torvalds/` | `/home/kbush/.config/torvalds/` |
| Cache | `~/.cache/torvalds/` | `/home/kbush/.cache/torvalds/` |
| Data | `~/.local/share/torvalds/` | `/home/kbush/.local/share/torvalds/` |

### Windows

| Data Type | Directory | Example Path |
|---|---|---|
| Config | `%APPDATA%\torvalds\` | `C:\Users\<user>\AppData\Roaming\torvalds\` |
| Cache | `%LOCALAPPDATA%\torvalds\` | `C:\Users\<user>\AppData\Local\torvalds\` |
| Data | `%APPDATA%\torvalds\` | `C:\Users\<user>\AppData\Roaming\torvalds\` |

### macOS

| Data Type | Directory | Example Path |
|---|---|---|
| Config | `~/Library/Preferences/torvalds/` | `~/Library/Preferences/torvalds/` |
| Cache | `~/Library/Caches/torvalds/` | `~/Library/Caches/torvalds/` |
| Data | `~/Library/Application Support/torvalds/` | `~/Library/Application Support/torvalds/` |

---

## 3. File Layout

```
~/.config/torvalds/
└── chat_config.json          # Configuration (user preferences)

~/.cache/torvalds/
└── agent_cache.json          # Runtime cache (current session ID)

~/.local/share/torvalds/      # Linux
  (or %APPDATA%\torvalds\)    # Windows
  (or ~/Library/Application Support/torvalds/)  # macOS
└── sessions.db               # SQLite session metadata (Table B)
```

---

## 4. File Specifications

### 4.1 Configuration File
**Path:** `~/.config/torvalds/chat_config.json`

**Purpose:** User preferences and backend configuration. Survives cache clears.

**Schema:**
```json
{
    "backend_type": "postgres",
    "token_limit": 5000,
    "default_session_type": "general",
    "auto_restore_last_session": true,
    "startup_behavior": "prompt",
    "created_at": "2024-01-15T10:30:00Z"
}
```

**Fields:**
| Field | Type | Default | Description |
|---|---|---|---|
| `backend_type` | string | `"postgres"` | Storage backend: `postgres`, `sqlite`, `memory` |
| `token_limit` | int | `5000` | Max tokens in memory buffer |
| `default_session_type` | string | `"general"` | Default type for new sessions |
| `auto_restore_last_session` | bool | `true` | Restore last session on startup |
| `startup_behavior` | string | `"prompt"` | `prompt`, `auto-restore`, `always-new` |
| `created_at` | datetime | — | Config creation timestamp |

---

### 4.2 Runtime Cache File
**Path:** `~/.cache/torvalds/agent_cache.json`

**Purpose:** Fast-access runtime state. Can be safely deleted/regenerated.

**Schema:**
```json
{
    "active_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "last_active_at": "2024-01-15T14:22:00Z",
    "session_count": 3,
    "cache_version": 1
}
```

**Fields:**
| Field | Type | Description |
|---|---|---|
| `active_session_id` | UUID | Currently active session |
| `last_active_at` | datetime | When this session was last selected |
| `session_count` | int | Total number of sessions (for quick display) |
| `cache_version` | int | Cache schema version for migration |

**Lifecycle:**
- Written on every session switch
- Read on startup for fast session restore
- Safe to delete — will be regenerated from `sessions.db`

---

### 4.3 Session Metadata Database
**Path:** `~/.local/share/torvalds/sessions.db` (Linux)

**Purpose:** Persistent session metadata (Table B). Primary source of truth.

**SQLite Schema:**
```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id    TEXT PRIMARY KEY,
    session_name  TEXT NOT NULL,
    session_type  TEXT NOT NULL CHECK(session_type IN ('general', 'project', 'custom')),
    chat_key      TEXT NOT NULL UNIQUE,
    metadata      TEXT DEFAULT '{}',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active     BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_sessions_type ON chat_sessions(session_type);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON chat_sessions(is_active);
```

**Pre-seeded Sessions:**
| session_id | session_name | session_type | chat_key |
|---|---|---|---|
| `gen-000000` | General Chat | `general` | `chat-general-001` |
| `proj-000000` | Project Chat | `project` | `chat-project-001` |

---

## 5. Directory Creation Strategy

```python
import platformdirs
import os

pd = platformdirs.PlatformDirs('torvalds', 'agent-torvalds')

def ensure_directories():
    """Create all required directories if they don't exist."""
    for dir_path in [
        pd.user_config_dir,
        pd.user_cache_dir,
        pd.user_data_dir,
    ]:
        os.makedirs(dir_path, exist_ok=True)
```

---

## 6. Platform Compatibility Matrix

| Feature | Linux | Windows | macOS |
|---|---|---|---|
| Config dir | `~/.config/torvalds/` | `%APPDATA%\torvalds\` | `~/Library/Preferences/torvalds/` |
| Cache dir | `~/.cache/torvalds/` | `%LOCALAPPDATA%\torvalds\` | `~/Library/Caches/torvalds/` |
| Data dir | `~/.local/share/torvalds/` | `%APPDATA%\torvalds\` | `~/Library/Application Support/torvalds/` |
| Session DB | `sessions.db` | `sessions.db` | `sessions.db` |
| Config file | `chat_config.json` | `chat_config.json` | `chat_config.json` |
| Cache file | `agent_cache.json` | `agent_cache.json` | `agent_cache.json` |

---

## 7. Migration from Current Setup

**Current:**
- `TORVALDS_CHAT_KEY` env var → single hardcoded key
- No session persistence
- No config file

**Migration Path:**
1. On first run with new system, detect if `TORVALDS_CHAT_KEY` is set
2. If yes, create a `general` session using that key
3. Migrate existing messages from old key to new session
4. Write initial config and cache files
5. Subsequent runs use new system exclusively

---

## 8. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `platformdirs` | 4.13.0 (installed) | Platform-aware directory resolution |
| `sqlite3` | stdlib | Session metadata storage |
| `json` | stdlib | Config and cache file I/O |
| `uuid` | stdlib | Session ID generation |

**No new dependencies required.**

---

## 9. Security & Permissions

- Config files: `0644` (readable by user, writable by user)
- Cache files: `0644`
- SQLite DB: `0644`
- No sensitive data stored (no passwords, no tokens)
- All paths under user home directory

---

## 10. Summary

| Concern | Solution |
|---|---|
| Platform compatibility | `platformdirs` library |
| Config persistence | `~/.config/torvalds/chat_config.json` |
| Runtime state | `~/.cache/torvalds/agent_cache.json` |
| Session metadata | SQLite DB in platform data dir |
| Migration | Auto-detect old env var, create initial session |
| Dependencies | None new — all stdlib or already installed |
