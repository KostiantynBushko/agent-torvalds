# Implementation report — the local fallback of the metadata layer

**Date:** 2026-10-25
**Branch:** `feature/chat-manager-sqlite-fallback` (off `master`, `5468e3b`)
**Scope:** Phase B of the chat-manager investigation
(`investigate/chat-manager-user-settings/INVESTIGATION_REPORT.md` §5.2 and §5.3).
**Status:** implemented, verified.

---

## 0. What this closes

The investigation's §5.1 named the blocker for removing the legacy chat-memory
implementation:

> the **metadata** layer does not degrade on its own — when PostgreSQL is
> unreachable, `initialize()` raises `RuntimeError: CustomDBConnector is not
> connected`, the orchestrators catch it, and the agent falls back to the
> legacy single-key buffer.

The message layer already degraded (to an in-memory store). The metadata layer
did not. That asymmetry was the only thing keeping the legacy path alive.

**Phase B gives the metadata layer the same shape of degradation.** With it, the
manager covers both "PostgreSQL up" (full features) and "PostgreSQL down"
(degraded but complete) — which is what §5.3 called the precondition for Phase C,
the removal of the legacy implementation.

Phase B closes defect **C8** and unblocks **C5**, **C6** and **C9**. It does not
perform the removal itself — that is Phase C.

---

## 1. The design

```
   connect()
       │
       ├── primary URI reachable?  ── yes ──▶  storage_mode = "primary"
       │                                        (everything is shared)
       └── no
            │
            ├── local fallback reachable? ── yes ──▶  storage_mode = "fallback"
            │                                        (everything works, nothing is shared)
            └── no ──▶  not connected
                        (the agent falls back to the legacy chat memory)
```

The fallback is a **local SQLite file** — the same technology the whole test
suite already runs the manager on (`sqlite:///:memory:`), so the degradation path
is not a second, less-travelled implementation: it is the same code on a
different URI.

### 1.1 Where it lives

| | |
|---|---|
| Default | `~/.torvalds/chat_manager.db` |
| Override | `TORVALDS_STORAGE_FALLBACK_URI=sqlite:////path/to/chat.db` |
| Switch off | `TORVALDS_STORAGE_FALLBACK=off` (or `none`, `no`, `0`, `false`, `disabled`) |
| In code | `CustomDBConnector(connection_uri=…, fallback_uri=…)` · `ChatHistoryManager(…, fallback_uri=…)` — an empty string switches it off |

The directory is created automatically: SQLite cannot create a file in a
directory that does not exist, and `~/.torvalds/` usually does not.

The default follows the shape of the existing `agent_cache_system.py`
convention (`Path.home() / …`, overridable by an environment variable,
`expanduser()` + `resolve()`), but it lives in `~/.torvalds/` rather than
`~/.cache/torvalds/`: the chat history is **state**, not a cache, and a cache
directory is the wrong place for the only copy of someone's conversation.

### 1.2 What keeps working

Everything the manager does:

- user identification and on-demand provisioning,
- the session lifecycle (create, list, select, rename, delete, clear),
- the active session and its restoration on the next startup,
- the user's settings.

The only thing the fallback loses is **sharing**: the history lives in one local
file instead of the shared database, so another machine does not see it.

### 1.3 What does *not* survive

The **message bodies** are a separate layer, and they degrade to an *in-memory*
store (`SimpleChatStoreBackend`). So during an outage:

| Layer | Where it lands | Survives a restart? |
|---|---|---|
| Metadata (users, sessions, settings) | the local SQLite file | **yes** |
| Message bodies | an in-memory store | no |

That is unchanged by this phase, and it is stated in the README rather than
glossed over: the metadata was the half that had *no* fallback at all, and it is
the half that had to be fixed first.

---

## 2. The degradation is reported, not hidden

A silent fallback is a trap: the operator would believe the agent is sharing
its history across machines when it is not. So the degradation is visible in six
places.

| Where | What |
|-------|------|
| The log | `CustomDBConnector could not reach <uri>; falling back to the local database at <uri>. The chat history is not shared with other machines.` |
| `connector.is_degraded` | `True` when the local database is in use. |
| `connector.active_uri` | The URI actually in use. |
| `connector.degradation_reason` | A sentence explaining the degradation. |
| `manager.is_degraded` / `manager.storage_mode` | The same, one level up: `primary` / `fallback` / `unavailable`. |
| The startup banner | A yellow notice in **both** orchestrators. |
| `\chat-info` | A `Storage:` line — `local fallback (the primary database is unreachable)`. |

The manager also logs the degradation itself at `initialize()`, so it appears in
the log even when the orchestrator's banner is not shown.

---

## 3. The files

| Path | Change |
|------|--------|
| `chat_manager/storage/connector.py` | The fallback: `_prepare_sqlite_uri()`, `_resolve_fallback_uri()`, `_connect_to()`, the new `connect()`, and the `is_degraded` / `active_uri` / `degradation_reason` properties. |
| `chat_manager/manager.py` | The `fallback_uri` constructor argument, the `is_degraded` and `storage_mode` properties, and the degradation log line in `initialize()`. |
| `chat_manager/commands/cli.py` | The `Storage:` line in `\chat-info`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The yellow startup notice. |
| `chat_manager/tests/test_fallback.py` | **New.** 23 tests. |
| `chat_manager/tests/conftest.py` | The two new environment variables are cleared around every test. |
| `chat_manager/README.md`, `README.md`, `CHANGELOG.md` | The documentation. |

---

## 4. Verification

```bash
cd self-development

# The chat manager suite — 127 passed
.venv/bin/python -m pytest chat_manager/tests -q

# The whole suite, through the CI gate
.venv/bin/python scripts/ci_test_gate.py
```

| Check | Result |
|-------|--------|
| `chat_manager/tests` | **127 passed** (104 before, 23 new). |
| The full suite | The CI gate reports **40 known failures, 0 new** — the build is green. |
| The end-to-end outage run | The manager came up **fully** on the fallback: the user was provisioned, both default sessions were seeded, the active session was restored, a new session was created, and `\chat-sessions` listed all three. The data was in the local file. |

### The end-to-end run, in full

```
=== The manager came up on the fallback ===
is_initialized : True
is_degraded    : True
storage_mode   : fallback
user           : kbush
sessions       : ['Project Chat', 'General Chat']
active session : General Chat

=== \chat-info shows the storage mode ===
Active session for user 'kbush':
  ID:       fab62e1a-e4d3-47a4-bb80-675b10f5665c
  Name:     General Chat
  Type:     general
  Chat key: chat-general-e89a145c-e81b-4a08-abd9-0d6ab6312097
  Created:  2026-10-25 22:01
  Updated:  2026-10-25 22:01
  Storage:  local fallback (the primary database is unreachable)
```

The primary database in that run was
`postgresql://postgres:postgres@127.0.0.1:59999/llama_index_db` — nothing is
listening on that port.

---

## 5. A note on a database that comes back

The fallback file is a real database, not a scratch space. The records written
while the primary was down are still in the file when the primary comes back —
but the agent switches back to the primary on the next start, and nothing is
merged: the outage-era sessions stay local unless they are copied over.

This is a deliberate trade. Merging the two would mean deciding, per record,
which side wins — and the local file is, by construction, the *newer* one. The
cost of the simpler behaviour is one manual copy in the rare case where the
outage mattered; the benefit is that the fallback never has to reason about
conflicts.

---

## 6. What Phase B does **not** do

| Not done | Why |
|-----------|-----|
| Remove `agent_chat_memory.py`, `--no-chat-history` or the dead `TOKEN_LIMITS` | Phase C — a separate change, on its own branch, so the removal can be reviewed on its own. |
| Fall back for the **message bodies** to a local store | The message backend already degrades to an in-memory store. Persisting messages locally as well is a bigger design question (schema, migration, retention) and was not needed to unblock the legacy removal. |
| Merge the fallback data back into the primary | See §5 — a deliberate simplification. |
| Change the legacy path in any way | The legacy path stays exactly as it is until Phase C. |

---

## 7. The next step

**Phase C — the removal of the legacy implementation.** With the metadata layer
degrading on its own, the legacy single-key path has no remaining job:

| Path | Legacy artefact | Action |
|------|-----------------|--------|
| `agent_chat_memory.py` | the whole module (273 lines) | delete |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | `import agent_chat_memory` · `agent_chat_memory.get_chat_memory()` | replace with `manager.get_memory_buffer()` |
| `agent-torvalds-cpp.py` | `agent_chat_memory.chat_memory` | same |
| both orchestrators | `TOKEN_LIMITS` | delete (dead) |
| both orchestrators | `--no-chat-history` | **keep the flag**, print a deprecation warning, and re-define it as "do not persist anything; use an in-memory store only" — a user-facing flag must not disappear |
| `chat_manager/manager.py` | the `TORVALDS_CHAT_KEY` migration hook | keep for one release, then remove |
| `tests/test_logging_cli.py` | imports `agent_chat_memory`'s logger | update |

Phase C should also add the regression test that pins the behaviour this phase
established: *with the primary database unreachable, the manager still comes up
and still has a user, a session and an active session.*
