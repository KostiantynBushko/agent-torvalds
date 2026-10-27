# Implementation report — the removal of the legacy chat memory

**Date:** 2026-10-25
**Branch:** `feature/chat-manager-remove-legacy-memory` (off
`feature/chat-manager-sqlite-fallback`, `e78fe68`)
**Scope:** Phase C of the chat-manager investigation
(`investigate/chat-manager-user-settings/INVESTIGATION_REPORT.md` §5.2 and §5.3).
**Status:** implemented, verified.

---

## 0. What this closes

Phase B gave the metadata layer the local fallback it never had. With it, the manager
covers both "PostgreSQL up" (full features) and "PostgreSQL down" (degraded but
complete) — which is what §5.3 called the precondition for this phase.

The legacy implementation existed for one reason after that: it was the thing that kept
the agent's memory alive when the database was down. The local fallback does that job
properly now — with the sessions intact, instead of as one flat key. So the legacy path
has no remaining job, and this phase removes it.

This closes defect **C5** (the legacy single-key implementation is still present and
reachable) and, with it, **C6** and **C9**.

---

## 1. What was removed

| Path | Was | Now |
|------|-----|-----|
| `agent_chat_memory.py` | the whole module (273 lines) | deleted |
| `agent-torvalds.py` | `import agent_chat_memory` · `agent_chat_memory.get_chat_memory()` (×2) | `from chat_manager.startup import get_memory_buffer` · `get_memory_buffer()` |
| `agent-torvalds-mw.py` | the same (×3) | the same |
| `agent-torvalds-cpp.py` | `agent_chat_memory.chat_memory` (×2) | `get_memory_buffer()` |
| both orchestrators | `TOKEN_LIMITS` | deleted — it was defined and never read |
| `tests/test_logging_cli.py` | imported `agent_chat_memory`'s logger | imports `chat_manager.startup`'s logger |

The module's own `get_all_tools()` was dead: `agent_chat_memory` was never in the
tool collection, so removing it takes no tool away.

---

## 2. The replacement

`chat_manager.startup` gained two functions.

```python
def get_memory_buffer(chat_token_limit=None):
    """The memory buffer for the active session.

    Falls back to an in-memory buffer when the manager is not up.
    """
```

```python
def get_in_memory_buffer(chat_token_limit=None):
    """A process-wide buffer that persists nothing."""
```

`get_memory_buffer()` is the one the orchestrators call. It returns the manager's buffer
— bound to the active session's `chat_key` — when the manager is up, and the in-memory
buffer when it is not. The orchestrators call it unguarded: it does not raise, so the
agent always has a usable memory.

Both buffers are cached process-wide. The legacy module cached its own singleton for the
same reason: every caller has to see the same conversation, and a fresh buffer per call
would silently split the history in half.

The in-memory buffer's limit comes from `TORVALDS_TOKEN_LIMIT` (default `5000`, the same
default the legacy buffer used). A value that is not an integer is logged and ignored
rather than taken as a crash.

---

## 3. `--no-chat-history`

The flag is kept — a user-facing flag must not disappear — but it means something
different now.

| | Before | After |
|---|--------|-------|
| Meaning | Disable the manager, use the legacy single-session memory | Persist nothing: no manager, an in-memory store only |
| Warning | none | a yellow deprecation notice at startup |
| Help text | "use the legacy single-session chat memory" | "run with an in-memory store only (deprecated)" |

---

## 4. What was deliberately *not* changed

| Not changed | Why |
|-------------|-----|
| `TORVALDS_CHAT_KEY` migration hook in `chat_manager/manager.py` | Keep it for one release, then remove it. It still points the General session at the old flat history, so pre-existing messages stay reachable after the upgrade. |
| The `chat_manager` package itself | The removal is a change in the *callers*, not in the package. The manager's API is untouched. |
| The `--no-session-select` flag | Unrelated to the legacy memory. |

---

## 5. The regression test

`chat_manager/tests/test_startup_memory.py` (9 tests) pins the behaviour the removal
rests on:

* **The buffer is always available.** Without a manager it is an in-memory buffer; with a
  manager it is the manager's; a manager that raises is survived; a manager that is not
  initialised is not treated as a manager. The in-memory buffer is a singleton, and it
  honours `TORVALDS_TOKEN_LIMIT` — and survives a broken one.
* **The outage path still works.** With the primary database unreachable the manager
  comes up completely — user, sessions, active session — and the buffer is bound to that
  active session.

`chat_manager/tests/test_fallback.py` already covered the manager and the connector
level; the new file covers the *startup* level, which is the surface this phase
introduced.

---

## 6. Verification

| Check | Result |
|-------|--------|
| The chat manager suite | **207 passed** (198 before, 9 new) |
| The full suite | **40 known failures, 0 new** — the failure set is identical to the baseline on `feature/chat-manager-sqlite-fallback` (the one difference in the captured output is the iteration order of a `frozenset` inside one assertion message) |
| The orchestrators import | `agent-torvalds.py` and `agent-torvalds-mw.py` both import cleanly |
| The end-to-end outage run | The manager came up on the fallback: user `kbush`, sessions `['Project Chat', 'General Chat']`, active session `General Chat`, `storage_mode` `fallback`, and the buffer bound to the active session's key |
| `git grep agent_chat_memory` | No references left outside the historical reports and the documentation that says the module is gone |

---

## 7. The next step

Merge the stack, bottom-up:

| # | Branch | Base | Merge commit |
|---|--------|------|--------------|
| #35 | `feature/chat-user-settings` | `master` | `05fb22b` (already on `origin`) |
| #36 | `feature/chat-manager-sqlite-fallback` | `feature/chat-user-settings` | `e78fe68` (already pushed) |
| #37 | `feature/chat-manager-remove-legacy-memory` | `feature/chat-manager-sqlite-fallback` | this branch |

**Bottom-up: 35, then 36, then 37.** Each base is retargeted to `master` *after* the PR
below it has been merged, and each is merged with a merge commit, never a squash.
