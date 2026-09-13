"""
Agent Cache System - Persistent operational context storage.

This module provides a JSON-based cache for storing operational and technical
context between agent sessions. This complements the PostgreSQL-backed
conversational memory by storing stateful information that doesn't belong
in chat history.

Cache location: ~/.cache/torvalds/agent_cache.json (configurable via TORVALDS_CACHE_PATH)

Category: Infrastructure
Retriever Keywords: cache, memory, state, persistence, context, session
"""
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from llama_index.core.tools import FunctionTool

# ---------------------------------------------------------------------------
# Cache configuration
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "torvalds"
_DEFAULT_CACHE_FILE = "agent_cache.json"
_CACHE_VERSION = "1.0"

# Maximum sizes (to prevent bloat)
_MAX_ERROR_LOG = 100
_MAX_SESSIONS = 50
_MAX_FREQUENT_COMMANDS = 50


def _get_cache_path() -> Path:
    """Get the cache file path, respecting TORVALDS_CACHE_PATH env var."""
    env_path = os.environ.get("TORVALDS_CACHE_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return _DEFAULT_CACHE_DIR / _DEFAULT_CACHE_FILE


def _get_default_cache() -> dict:
    """Return a fresh default cache structure."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "version": _CACHE_VERSION,
        "created_at": now,
        "last_updated": now,
        "sessions": [],
        "context": {
            "current_directory": "",
            "active_databases": [],
            "running_processes": [],
            "git_repos": {},
        },
        "learnings": {
            "user_preferences": {},
            "frequent_commands": [],
            "common_patterns": {},
        },
        "state": {
            "file_watches": {},
            "network_connections": {},
            "temp_files": [],
        },
        "error_log": [],
    }


def _load_cache() -> dict:
    """Load cache from disk, or create a new one if it doesn't exist."""
    cache_path = _get_cache_path()
    if cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            # Validate structure — migrate if needed
            for key in ("sessions", "context", "learnings", "state", "error_log"):
                if key not in data:
                    data[key] = _get_default_cache()[key]
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return _get_default_cache()


def _save_cache(cache: dict) -> None:
    """Save cache to disk atomically (write to temp, then rename)."""
    cache_path = _get_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache["last_updated"] = datetime.now(timezone.utc).isoformat()

    tmp_path = cache_path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(cache, f, indent=2)
    os.replace(str(tmp_path), str(cache_path))


# ---------------------------------------------------------------------------
# Public API — cache access functions
# ---------------------------------------------------------------------------

_cache = None  # Module-level singleton

def _get_cache() -> dict:
    """Get (and lazily load) the singleton cache."""
    global _cache
    if _cache is None:
        _cache = _load_cache()
    return _cache


def save_to_cache(key: str, value: Any) -> str:
    """
    Store a value in the persistent cache.

    Args:
        key: Dot-separated key path (e.g. 'context.current_directory')
        value: Any JSON-serializable value

    Returns:
        str: Success or error message

    Keywords: cache, store, save, persist, write
    """
    try:
        cache = _get_cache()
        parts = key.split(".")
        obj = cache
        for part in parts[:-1]:
            if part not in obj:
                obj[part] = {}
            obj = obj[part]
        obj[parts[-1]] = value
        _save_cache(cache)
        return f"Saved to cache: {key}"
    except Exception as e:
        return f"Error saving to cache: {e}"


def load_from_cache(key: str) -> Any:
    """
    Retrieve a value from the persistent cache.

    Args:
        key: Dot-separated key path (e.g. 'context.current_directory')

    Returns:
        The cached value, or None if not found

    Keywords: cache, load, retrieve, read, get
    """
    try:
        cache = _get_cache()
        parts = key.split(".")
        obj = cache
        for part in parts:
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                return None
        return obj
    except Exception as e:
        return f"Error loading from cache: {e}"


def clear_cache() -> str:
    """
    Wipe all cached data and start fresh.

    Returns:
        str: Confirmation message

    Keywords: cache, clear, wipe, reset, delete
    """
    global _cache
    try:
        _cache = _get_default_cache()
        _save_cache(_cache)
        return "Cache cleared successfully."
    except Exception as e:
        return f"Error clearing cache: {e}"


def get_cache_status() -> dict:
    """
    View cache size, age, and contents summary.

    Returns:
        dict: Status information including file size, creation time,
              and summary of each section

    Keywords: cache, status, info, size, summary
    """
    try:
        cache = _get_cache()
        cache_path = _get_cache_path()
        file_size = cache_path.stat().st_size if cache_path.exists() else 0

        return {
            "cache_path": str(cache_path),
            "file_size_bytes": file_size,
            "file_size_human": _human_size(file_size),
            "version": cache.get("version"),
            "created_at": cache.get("created_at"),
            "last_updated": cache.get("last_updated"),
            "sections": {
                "sessions": len(cache.get("sessions", [])),
                "context_keys": len(cache.get("context", {})),
                "learnings_keys": len(cache.get("learnings", {})),
                "state_keys": len(cache.get("state", {})),
                "error_log_entries": len(cache.get("error_log", [])),
            },
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Context helpers — called by hooks or directly
# ---------------------------------------------------------------------------

def update_context_current_dir(path: str) -> str:
    """Update the cached current directory context."""
    return save_to_cache("context.current_directory", path)


def add_active_database(name: str, host: str) -> str:
    """Record an active database connection."""
    cache = _get_cache()
    db_entry = {"name": name, "host": host, "connected_at": datetime.now(timezone.utc).isoformat()}
    if "active_databases" not in cache["context"]:
        cache["context"]["active_databases"] = []
    cache["context"]["active_databases"].append(db_entry)
    _save_cache(cache)
    return f"Database {name} added to active connections."


def add_git_repo(path: str, branch: str = "") -> str:
    """Record a Git repository being used."""
    cache = _get_cache()
    if "git_repos" not in cache["context"]:
        cache["context"]["git_repos"] = {}
    cache["context"]["git_repos"][path] = {
        "branch": branch,
        "last_accessed": datetime.now(timezone.utc).isoformat(),
    }
    _save_cache(cache)
    return f"Git repo {path} recorded."


def log_error(message: str) -> str:
    """Append an error to the cache error log."""
    cache = _get_cache()
    if "error_log" not in cache:
        cache["error_log"] = []
    cache["error_log"].append({
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Trim to max size
    cache["error_log"] = cache["error_log"][-_MAX_ERROR_LOG:]
    _save_cache(cache)
    return f"Error logged: {message[:80]}..."


def record_frequent_command(command: str) -> str:
    """Track a frequently used command for personalization."""
    cache = _get_cache()
    freq = cache["learnings"].get("frequent_commands", [])
    # Increment count or add new
    for entry in freq:
        if entry["command"] == command:
            entry["count"] += 1
            entry["last_used"] = datetime.now(timezone.utc).isoformat()
            _save_cache(cache)
            return f"Command '{command}' count updated."
    freq.append({
        "command": command,
        "count": 1,
        "first_used": datetime.now(timezone.utc).isoformat(),
        "last_used": datetime.now(timezone.utc).isoformat(),
    })
    # Trim
    freq = freq[-_MAX_FREQUENT_COMMANDS:]
    cache["learnings"]["frequent_commands"] = freq
    _save_cache(cache)
    return f"Command '{command}' recorded."


def start_session() -> str:
    """Start a new session entry in the cache."""
    cache = _get_cache()
    if "sessions" not in cache:
        cache["sessions"] = []
    cache["sessions"].append({
        "started_at": datetime.now(timezone.utc).isoformat(),
        "commands_run": 0,
    })
    # Trim
    cache["sessions"] = cache["sessions"][-_MAX_SESSIONS:]
    _save_cache(cache)
    return "New session started."


def end_session() -> str:
    """End the current session."""
    cache = _get_cache()
    sessions = cache.get("sessions", [])
    if sessions:
        sessions[-1]["ended_at"] = datetime.now(timezone.utc).isoformat()
        _save_cache(cache)
        return "Session ended."
    return "No active session to end."


def increment_session_commands() -> None:
    """Increment the command counter for the current session."""
    cache = _get_cache()
    sessions = cache.get("sessions", [])
    if sessions:
        sessions[-1]["commands_run"] = sessions[-1].get("commands_run", 0) + 1
        _save_cache(cache)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _human_size(nbytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def get_all_tools() -> list[FunctionTool]:
    """
    Return all cache tools as FunctionTool objects.

    Returns:
        list[FunctionTool]: List of cache FunctionTool objects
    """
    return [
        FunctionTool.from_defaults(
            fn=save_to_cache,
            description="Store a value in the persistent cache. Use for saving operational context between sessions. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=load_from_cache,
            description="Retrieve a value from the persistent cache. Use for restoring operational context. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=clear_cache,
            description="Wipe all cached data. Use for resetting agent state. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=get_cache_status,
            description="View cache status including size, age, and section summary. Use for cache diagnostics. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=update_context_current_dir,
            description="Update cached current directory. Use for tracking working directory. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=add_git_repo,
            description="Record a Git repository being used. Use for tracking repo context. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=log_error,
            description="Log an error to the cache. Use for tracking issues. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=start_session,
            description="Start a new agent session. Use for session tracking. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=end_session,
            description="End the current agent session. Use for session tracking. Category: Infrastructure",
        ),
    ]


# ---------------------------------------------------------------------------
# Auto-load cache on import
# ---------------------------------------------------------------------------
_cache = _load_cache()
