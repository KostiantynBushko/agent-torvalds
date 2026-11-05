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
import copy
import contextlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from llama_index.core.tools import FunctionTool

try:  # pragma: no cover - Windows has no fcntl
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - the write is not serialised there
    _fcntl = None

logger = logging.getLogger(__name__)

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
_MAX_REQUEST_STATS = int(os.environ.get("TORVALDS_STATS_MAX_HISTORY", "500"))

# ---------------------------------------------------------------------------
# Merge rules
# ---------------------------------------------------------------------------

#: The sections that grow, and the keys that give an entry its identity.
#:
#: Two agents can write to the cache at the same time.  The sections that
#: grow - the error log, the sessions, the request statistics, the frequent
#: commands - are merged by that identity, so that the entries of both
#: agents survive.  The identity is what tells "the same entry, written
#: again" from "another entry".
_UNION_SECTIONS = {
    ("error_log",): ("message", "timestamp"),
    ("sessions",): ("started_at",),
    ("request_stats",): ("timestamp", "request_id"),
    ("learnings", "frequent_commands"): ("command",),
}

#: How many entries each of the growing sections keeps.
_SECTION_MAX = {
    ("error_log",): _MAX_ERROR_LOG,
    ("sessions",): _MAX_SESSIONS,
    ("request_stats",): _MAX_REQUEST_STATS,
    ("learnings", "frequent_commands"): _MAX_FREQUENT_COMMANDS,
}

#: The marker that says "this value could not be held by JSON".
_DROPPED = object()

#: The marker that says "this key was taken out of the cache".
_REMOVED = object()


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
        "request_stats": [],
    }


# ---------------------------------------------------------------------------
# Reading and writing the file
# ---------------------------------------------------------------------------

def _read_cache_file(cache_path: Path) -> tuple:
    """
    Read the cache file from disk.

    A file that cannot be read is **reported**, not silently replaced with
    an empty cache: the file may have been damaged by a crash between the
    write and the rename, and the operator has to know about it.

    Args:
        cache_path: The file to read.

    Returns:
        tuple: (state, warning).  The state is the cache that was read, or
        a fresh default when the file does not exist.  The warning names
        the file that could not be read, when there was one.
    """
    if not cache_path.exists():
        return _get_default_cache(), None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        warning = (
            f"The cache file {cache_path} cannot be read ({exc}). "
            "A fresh cache is used; the file is left as it is."
        )
        return _get_default_cache(), warning

    if not isinstance(data, dict):
        warning = (
            f"The cache file {cache_path} does not hold a cache - it is not "
            "an object. A fresh cache is used; the file is left as it is."
        )
        return _get_default_cache(), warning

    # Validate structure - migrate if needed
    defaults = _get_default_cache()
    for key in ("sessions", "context", "learnings", "state", "error_log", "request_stats"):
        if key not in data:
            data[key] = defaults[key]
    return data, None


def _record_warning(warning: str) -> None:
    """
    Record a warning about the cache file, once.

    The file is read again on every write, so a damaged file would be
    reported over and over.  It is reported once, and it stays in the
    status of the cache.
    """
    global _load_warnings
    if warning in _load_warnings:
        return
    _load_warnings.append(warning)
    logger.warning(warning)


def _load_cache() -> dict:
    """Load cache from disk, or create a new one if it doesn't exist."""
    state, warning = _read_cache_file(_get_cache_path())
    if warning:
        _record_warning(warning)
    return state


@contextlib.contextmanager
def _cache_lock(cache_path: Path) -> Iterator[None]:
    """
    Hold an exclusive lock on the cache, so two agents do not write at once.

    The lock is a file of its own: the cache file itself is replaced by a
    rename, so a lock held on it would not outlive the write that took it.

    Args:
        cache_path: The cache file the lock belongs to.
    """
    if _fcntl is None:  # pragma: no cover - Windows
        yield
        return

    lock_path = cache_path.with_name(cache_path.name + ".lock")
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:  # pragma: no cover - a read-only cache folder
        logger.warning(
            "The cache lock %s cannot be opened (%s); the write is not serialised.",
            lock_path,
            exc,
        )
        yield
        return

    try:
        _fcntl.flock(fd, _fcntl.LOCK_EX)
        try:
            yield
        finally:
            _fcntl.flock(fd, _fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _write_atomic(path: Path, payload: str) -> None:
    """
    Write *payload* to *path* atomically.

    The temp file belongs to this writer alone: its name is unique, so two
    writers never share it, and it is removed when the write fails.  The
    rename is atomic, and the fsync before it makes the rename durable and
    not only atomic.

    Args:
        path: The file to write.
        payload: The text to write.
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    # The rename is on the disk now - the directory itself has to be
    # written out as well, or the rename can be lost in a crash.
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:  # pragma: no cover - not every filesystem allows it
        pass


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------

def _json_safe(value: Any, path: tuple = (), dropped: Optional[list] = None) -> Any:
    """
    Return a copy of *value* that JSON can hold.

    A value JSON cannot carry - an object, a set, a function - is dropped,
    and the path it was dropped from is recorded.  The cache keeps working:
    the copy is written, and the caller is told what was left out.

    Args:
        value: The value to make JSON-safe.
        path: The path of *value* inside the cache, for the report.
        dropped: The list the dropped values are recorded in.

    Returns:
        The JSON-safe copy, or the _DROPPED marker when the value itself
        cannot be held.
    """
    if dropped is None:
        dropped = []

    if value is None or isinstance(value, (str, bool, int, float)):
        return value

    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            if not isinstance(key, str):
                dropped.append((path + (repr(key),), type(key).__name__))
                continue
            item_safe = _json_safe(item, path + (key,), dropped)
            if item_safe is _DROPPED:
                continue
            safe[key] = item_safe
        return safe

    if isinstance(value, (list, tuple)):
        safe_list = []
        for index, item in enumerate(value):
            item_safe = _json_safe(item, path + (index,), dropped)
            if item_safe is _DROPPED:
                continue
            safe_list.append(item_safe)
        return safe_list

    dropped.append((path, type(value).__name__))
    return _DROPPED


def _describe_dropped(dropped: list) -> str:
    """A report of the values that JSON could not hold."""
    parts = []
    for path, type_name in dropped:
        key = ".".join(str(part) for part in path)
        parts.append(f"the value at '{key}' is a {type_name}, which JSON cannot hold")
    return "; ".join(parts)


def _drop_unholdable(cache: dict) -> None:
    """
    Remove the values that JSON cannot hold from *cache*, in place.

    A value that cannot be serialised must not stay in the cache in
    memory: every later write would carry it and fail again.  The cache
    that is left is one that can still be written.
    """
    dropped = []
    safe = _json_safe(cache, (), dropped)
    if dropped and isinstance(safe, dict):
        cache.clear()
        cache.update(safe)


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def _changed_paths(base: Any, current: Any, path: tuple = (), out: Optional[dict] = None) -> dict:
    """
    The paths where *current* differs from *base*.

    Two agents hold two copies of the cache.  The copy an agent did not
    touch is stale, and must not overwrite what the other agent wrote.  The
    paths are therefore compared against the copy as it was when it was
    loaded, and only what changed is written.

    Args:
        base: The cache as it was loaded.
        current: The cache as it is now.
        path: The path of *base* inside the cache.
        out: The dict the changed paths are collected in.

    Returns:
        dict: The changed paths, mapped to their new value (_REMOVED when
        the key was taken out).
    """
    if out is None:
        out = {}

    if isinstance(base, dict) and isinstance(current, dict):
        for key, value in current.items():
            if key not in base:
                out[path + (key,)] = value
            else:
                _changed_paths(base[key], value, path + (key,), out)
        for key in base:
            if key not in current:
                out[path + (key,)] = _REMOVED
        return out

    if base != current:
        out[path] = current
    return out


def _find_identity(items: list, item: Any, identity: tuple) -> Optional[int]:
    """The index of the item in *items* that carries the same identity."""
    if isinstance(item, dict) and all(key in item for key in identity):
        for index, other in enumerate(items):
            if isinstance(other, dict) and all(other.get(key) == item.get(key) for key in identity):
                return index
        return None
    try:
        return items.index(item)
    except ValueError:
        return None


def _merge_section(target: dict, path: tuple, writer_items: Any) -> None:
    """
    Merge a growing section: what is on disk first, what the writer adds.

    The entries are matched by their identity, so an entry that was
    written again - a session that got its end time, a command that was
    counted once more - replaces its earlier version instead of being
    added a second time.
    """
    obj = target
    for part in path[:-1]:
        nxt = obj.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            obj[part] = nxt
        obj = nxt

    section = path[-1]
    existing = obj.get(section)
    merged = list(existing) if isinstance(existing, list) else []

    identity = _UNION_SECTIONS[path]
    for item in writer_items if isinstance(writer_items, list) else []:
        index = _find_identity(merged, item, identity)
        if index is None:
            merged.append(item)
        else:
            merged[index] = item

    limit = _SECTION_MAX.get(path)
    if limit:
        merged = merged[-limit:]
    obj[section] = merged


def _set_path(target: dict, path: tuple, value: Any) -> None:
    """Set the value at *path* in *target*, creating the sections on the way."""
    obj = target
    for part in path[:-1]:
        nxt = obj.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            obj[part] = nxt
        obj = nxt
    obj[path[-1]] = value


def _delete_path(target: dict, path: tuple) -> None:
    """Remove the key at *path* from *target*, if it is there."""
    obj = target
    for part in path[:-1]:
        nxt = obj.get(part)
        if not isinstance(nxt, dict):
            return
        obj = nxt
    obj.pop(path[-1], None)


def _apply_changes(target: dict, changes: dict) -> dict:
    """Apply the changed paths to the cache that was read from disk."""
    for path, value in changes.items():
        if path in _UNION_SECTIONS:
            _merge_section(target, path, value)
        elif value is _REMOVED:
            _delete_path(target, path)
        else:
            _set_path(target, path, value)
    return target


# ---------------------------------------------------------------------------
# The singleton
# ---------------------------------------------------------------------------

_cache = None            # Module-level singleton
_cache_snapshot = None   # The singleton as it was loaded or last written
_load_warnings = []      # The cache files that could not be read


def _get_cache() -> dict:
    """Get (and lazily load) the singleton cache."""
    global _cache, _cache_snapshot
    if _cache is None:
        _cache = _load_cache()
        _cache_snapshot = copy.deepcopy(_cache)
    return _cache


def _adopt(state: dict) -> None:
    """
    Adopt the written state into the singleton.

    The dict itself is updated in place: the callers hold a reference to
    it, and they have to see what was written.
    """
    global _cache, _cache_snapshot
    if _cache is None:
        _cache = state
    else:
        _cache.clear()
        _cache.update(state)
    _cache_snapshot = copy.deepcopy(state)


def _save_cache(cache: dict, merge: bool = True) -> list:
    """
    Save cache to disk.

    The write is atomic - a temp file that belongs to this writer alone,
    an fsync, and a rename - and it is merged: the file is read again
    under a lock and only what this writer changed is applied to it, so two
    agents that save at the same time do not erase each other's entries.

    Args:
        cache: The cache to write.
        merge: When True (the default), the changes of the singleton are
        merged into the file that is on disk.  When False, the cache is
        written as it is and the file is replaced.

    Returns:
        list: The values that could not be held by JSON, and were dropped.
    """
    cache_path = _get_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # The snapshot is the base of the comparison only for the singleton:
    # it is the copy that was loaded, so it is the copy that says what
    # this writer changed.
    base = _cache_snapshot if (merge and cache is _cache) else None
    dropped: list = []

    try:
        with _cache_lock(cache_path):
            if base is None:
                # The caller hands over a cache of its own: it is written
                # as it is.
                target = copy.deepcopy(cache)
            else:
                disk, warning = _read_cache_file(cache_path)
                if warning:
                    _record_warning(warning)
                target = _apply_changes(disk, _changed_paths(base, cache))

            dropped = []
            target = _json_safe(target, (), dropped)
            if not isinstance(target, dict):  # pragma: no cover - a dict in, a dict out
                raise TypeError("The cache must be a mapping.")

            target["last_updated"] = datetime.now(timezone.utc).isoformat()
            payload = json.dumps(target, indent=2)
            _write_atomic(cache_path, payload)
    except Exception:
        # A failed write must not leave a value that cannot be held in
        # the cache in memory: every later write would carry it and fail
        # again.
        _drop_unholdable(cache)
        raise

    if cache is _cache:
        _adopt(target)
    return dropped


# ---------------------------------------------------------------------------
# Public API — cache access functions
# ---------------------------------------------------------------------------

def save_to_cache(key: str, value: Any) -> str:
    """
    Store a value in the persistent cache.

    A value JSON cannot hold is reported and dropped: the cache keeps
    working, and the value does not stay in the cache to break every later
    write.

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
        dropped = _save_cache(cache)
        if dropped:
            return (
                f"Error saving to cache: {_describe_dropped(dropped)}. "
                "It was dropped; the cache keeps working."
            )
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
        _save_cache(_cache, merge=False)
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
            "warnings": list(_load_warnings),
            "sections": {
                "sessions": len(cache.get("sessions", [])),
                "context_keys": len(cache.get("context", {})),
                "learnings_keys": len(cache.get("learnings", {})),
                "state_keys": len(cache.get("state", {})),
                "error_log_entries": len(cache.get("error_log", [])),
                "request_stats_entries": len(cache.get("request_stats", [])),
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
# Request statistics persistence
# ---------------------------------------------------------------------------


def _as_number(value, default: float = 0) -> float:
    """
    Coerce a value to a number, falling back to *default* when impossible.

    Statistics entries are persisted as JSON and later aggregated with
    ``sum()``. A ``None`` (or non-numeric) value would raise ``TypeError``
    during aggregation, so every numeric field is normalised on the way in
    and on the way out.

    Args:
        value: The raw value to coerce.
        default: Value returned when *value* is None or not numeric.

    Returns:
        float: The coerced number.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def save_request_stats(stats_dict: dict) -> str:
    """
    Save request statistics to the cache for historical analysis.

    Args:
        stats_dict: Dictionary of request stats (from RequestStats.to_dict())

    Returns:
        str: Confirmation message

    Keywords: stats, statistics, save, persist, history
    """
    try:
        cache = _get_cache()
        if "request_stats" not in cache:
            cache["request_stats"] = []

        # Normalise every numeric field: a missing key must be written as 0,
        # never as None. Otherwise get_stats_summary()'s summation raises
        # TypeError on None and the summary degrades to {"error": ...}.
        cache["request_stats"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": stats_dict.get("request_id"),
            "duration_ms": _as_number(stats_dict.get("total_duration_ms")),
            "llm_calls": _as_number(stats_dict.get("llm_call_count")),
            "total_tokens": _as_number(stats_dict.get("total_tokens")),
            "prompt_tokens": _as_number(stats_dict.get("total_prompt_tokens")),
            "completion_tokens": _as_number(stats_dict.get("total_completion_tokens")),
            "tools_used": stats_dict.get("tools_used") or [],
            "tool_call_count": _as_number(stats_dict.get("tool_call_count")),
            "error_count": _as_number(stats_dict.get("error_count")),
        })

        # Keep last N requests
        cache["request_stats"] = cache["request_stats"][-_MAX_REQUEST_STATS:]
        _save_cache(cache)
        return f"Stats saved for request {stats_dict.get('request_id')}"
    except Exception as e:
        return f"Error saving stats: {e}"


def get_stats_summary() -> dict:
    """
    Get summary statistics across all stored requests.

    Returns:
        dict: Aggregate statistics including totals and averages

    Keywords: stats, statistics, summary, history, analytics
    """
    try:
        cache = _get_cache()
        stats_list = cache.get("request_stats", [])

        if not stats_list:
            return {"message": "No request statistics available yet."}

        # Use _as_number so legacy entries (or hand-edited ones) carrying
        # None cannot break the aggregation.
        total_tokens = sum(_as_number(s.get("total_tokens")) for s in stats_list)
        total_duration = sum(_as_number(s.get("duration_ms")) for s in stats_list)
        total_llm_calls = sum(_as_number(s.get("llm_calls")) for s in stats_list)
        total_errors = sum(_as_number(s.get("error_count")) for s in stats_list)
        total_tool_calls = sum(_as_number(s.get("tool_call_count")) for s in stats_list)

        return {
            "total_requests": len(stats_list),
            "total_tokens": total_tokens,
            "total_llm_calls": total_llm_calls,
            "total_tool_calls": total_tool_calls,
            "avg_tokens_per_request": round(total_tokens / len(stats_list), 1),
            "avg_duration_ms": round(total_duration / len(stats_list), 1),
            "avg_llm_calls_per_request": round(total_llm_calls / len(stats_list), 1),
            "total_errors": total_errors,
        }
    except Exception as e:
        return {"error": str(e)}


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
        FunctionTool.from_defaults(
            fn=save_request_stats,
            description="Save request statistics to the cache for historical analysis. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=get_stats_summary,
            description="Get summary statistics across all stored requests. Category: Infrastructure",
        ),
    ]


# ---------------------------------------------------------------------------
# Auto-load cache on import
# ---------------------------------------------------------------------------
_cache = _load_cache()
_cache_snapshot = copy.deepcopy(_cache)
