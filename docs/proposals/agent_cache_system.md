# Agent Cache System Proposal

## Overview
A persistent cache file to store operational and technical context during the agent's lifetime. This complements the existing PostgreSQL-backed conversational memory by storing stateful information that doesn't belong in chat history.

---

## 1. Cache Location
```
~/.cache/torvalds/agent_cache.json
```
- Uses standard XDG cache directory convention
- Hidden from normal file listings
- Persisted across sessions
- Configurable via environment variable `TORVALDS_CACHE_PATH`

---

## 2. Cache Structure (JSON)

```json
{
  "version": "1.0",
  "created_at": "2026-09-11T10:46:54",
  "last_updated": "2026-09-11T10:46:54",
  "sessions": [],
  "context": {
    "current_directory": "/home/kbush/...",
    "active_databases": [],
    "running_processes": [],
    "git_repos": {}
  },
  "learnings": {
    "user_preferences": {},
    "frequent_commands": [],
    "common_patterns": {}
  },
  "state": {
    "file_watches": {},
    "network_connections": {},
    "temp_files": []
  }
}
```

---

## 3. What Gets Cached

| Category | Examples | Purpose |
|----------|----------|---------|
| **Session Info** | Timestamp, duration, commands run | Audit trail |
| **Context** | Current dir, active DBs, git repos, running processes | Restore working state |
| **Learnings** | User preferences, frequent commands, patterns | Personalization |
| **State** | File watches, temp files, network connections | Operational continuity |
| **Error Log** | Recent errors for debugging | Troubleshooting |

---

## 4. Implementation Flow

```
Startup → Check/Create Cache Dir → Load Cache → Agent Runtime
                                                              ↓
Exit ← Save Cache ← Update Cache (on key events)
```

---

## 5. Key Features

- **Auto-load on startup**: Restores previous context
- **Incremental updates**: Only changes are written to disk
- **Configurable retention**: Limit history size to prevent bloat
- **Privacy mode**: Option to disable caching via flag/env var
- **Auto-cleanup**: Remove stale temp files/entries older than N days

---

## 6. Integration Points

### New Tools
- `save_to_cache(key, value)` – Store a value in cache
- `load_from_cache(key)` – Retrieve a value from cache
- `clear_cache()` – Wipe all cached data
- `get_cache_status()` – View cache size, age, contents summary

### System Prompt Addition
> *"You have access to a persistent cache file for retaining operational context between sessions. Use it to remember current directory, active databases, git repositories, and other technical state."*

### Auto-Update Hooks
- On `pwd()` call → update `context.current_directory`
- On DB connection → add to `context.active_databases`
- On git operation → update `context.git_repos`
- On process start/stop → update `context.running_processes`
- On error → append to `error_log`

---

## 7. Differences from PostgreSQL Memory

| Feature | Cache File | PostgreSQL Memory |
|---------|------------|-------------------|
| **Purpose** | Operational/technical state | Conversational history |
| **Content** | Dir, DBs, repos, processes, prefs | User prompts & agent responses |
| **Access Speed** | Fast (local file) | Slower (DB query) |
| **Persistence** | Across restarts | Across restarts |
| **Token Limit** | None (configurable size) | 3000 tokens |
| **Per-User** | Single cache per agent | Per conversation key |

---

## 8. Security & Privacy Considerations

- Cache file should not store sensitive data (passwords, tokens)
- Option to encrypt cache with a key
- Clear cache on explicit command
- Log file size to prevent disk exhaustion

---

## 9. Future Enhancements

- [ ] Cache compression for large datasets
- [ ] Sync cache across multiple agent instances
- [ ] Machine learning on frequent commands for auto-suggestions
- [ ] Visual cache browser tool
- [ ] Cache versioning/rollback

---

## Status: **Proposed**
**Author:** Torvalds Agent  
**Date:** 2026-09-11
