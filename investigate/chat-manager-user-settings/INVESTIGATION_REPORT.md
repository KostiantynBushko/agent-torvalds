# Investigation — `chat_manager`: user settings, `token_limit`, and the legacy implementation

**Date:** 2026-10-25
**Scope:** `self-development/chat_manager/`, `agent_chat_memory.py`, the two orchestrators, the
command registry.
**Method:** static reading + an executable probe
(`investigate/chat-manager-user-settings/probe_user_settings.py`).
**Status:** investigation only — no source file of the agent was modified.

> **This report describes the state _before_ the work it led to.** Phase A of §5.3 has since
> been implemented on the branch `feature/chat-user-settings`: the user-settings API
> (defect **C1**), the live-buffer invalidation (**C2**), the dropped override (**C3**), the
> missing command (**C4**) and the `token_limit` → `chat_token_limit` rename (**C7**) are
> closed. The `file:line` references below are the ones the investigation was made against —
> they have moved since. See
> `IMPLEMENTATION_REPORT_user_settings.md` for what changed, and
> `PROPOSAL_chat_token_limit.md` for the naming decision.
>
> Phases **B** (the SQLite fallback in `CustomDBConnector`) and **C** (the removal of the
> legacy implementation) are **not started** — the legacy path is still load-bearing, exactly
> as §5.1 describes.

---

## 0. Answers up front

| # | Question | Answer |
|---|----------|--------|
| 1 | How do we change `user.token_limit`? | **We cannot, through any supported path.** The column exists and is written by the connector, but the manager exposes no API for it, and the live buffer ignores a changed value anyway. |
| 2 | Do we need a command to manage user settings? | **Yes.** The `users` table is the documented home of the user's *preferences*, yet no command can read or write them, and the operator cannot even see the current value. |
| 3 | Is the old chat-history implementation still there? | **Yes — in four layers**, and one of them is load-bearing: the legacy path is the only thing that keeps the agent usable when the metadata database is down. |

The single most important finding: **the legacy implementation cannot simply be deleted
yet**, because the metadata layer has no fallback of its own. Fix that first, and the removal
becomes safe. Section 5 lays out that order.

---

## 1. The code under investigation

```
chat_manager/
├── manager.py                  ChatHistoryManager — the public surface
├── user.py                     User dataclass (carries token_limit)
├── session.py                  Session dataclass + SessionType
├── startup.py                  Global singleton lifecycle
├── session_selector.py         Interactive startup picker
├── backend/                    Message storage (LlamaIndex chat store)
│   ├── base.py                 ChatStoreBackend ABC
│   ├── postgres.py             PostgresChatStoreBackend
│   └── simple.py               SimpleChatStoreBackend  ← in-memory fallback
├── storage/                    User & session metadata (SQLAlchemy)
│   ├── models.py               ORM: User.token_limit
│   └── connector.py            CustomDBConnector — CRUD + DDL
└── commands/
    ├── handler.py              Dispatch: CHAT_COMMANDS + handle_chat_command()
    └── cli.py                  One function per command
```

`token_limit` travels through four layers:

| Layer | Where | Note |
|-------|-------|------|
| Column | `chat_manager/storage/connector.py:34` — `token_limit INTEGER NOT NULL DEFAULT 5000` | DDL, created idempotently |
| ORM | `chat_manager/storage/models.py:35` — `token_limit = Column(Integer, nullable=False, default=5000)` | |
| Dataclass | `chat_manager/user.py:27` — `token_limit: int = 5000` | |
| **Consumption** | `chat_manager/manager.py:483-491` — read **once**, when the memory buffer is built | **the only read** |

The write path exists in exactly one place: `CustomDBConnector.update_user()`
(`chat_manager/storage/connector.py:274`) writes `existing.token_limit = user.token_limit`.
It has **zero production callers** — only `chat_manager/tests/test_storage.py:76` and the
probe.

---

## 2. Q1 — How to change `user.token_limit`?

### 2.1 There is no public API

`ChatHistoryManager` is the public surface of the package (`chat_manager/__init__.py` exports
`ChatHistoryManager`, `User`, `Session`, `SessionType`). Its public methods are:

```
identify_user · get_active_session · list_sessions · create_session · get_session
update_session · rename_session · select_session · switch_session · delete_session
get_memory_buffer · add_message · put_message · get_messages · clear_messages · close
current_user (property) · is_initialized (property)
```

Every one of them manages **sessions**. None manages the **user**.

> Probe output:
> ```
> Manager public members matching update/user/setting: ['current_user', 'identify_user', 'update_session']
> Manager exposes a user-update method: False
> Connector (private, manager._db) user methods: ['create_user', 'get_user_by_id', 'get_user_by_username', 'update_user']
> ```

The only way to change the limit today is to reach into the **private** `manager._db`:

```python
user = manager.current_user
user.token_limit = 12000
manager._db.update_user(user)     # ← private attribute, not an API
```

### 2.2 Even that does not change the running agent

`get_memory_buffer()` reads the limit once, at build time (`chat_manager/manager.py:483`):

```python
limit = token_limit or (self._current_user.token_limit if self._current_user else 5000)
self._memory_buffer = ChatMemoryBuffer.from_defaults(token_limit=limit, ...)
```

The buffer is then **cached** in `self._memory_buffer` and handed back unchanged on every
subsequent call. It is invalidated in exactly two places: `switch_session()`
(`chat_manager/manager.py:424`) and `clear_messages()` (`chat_manager/manager.py:551`).

> Probe output:
> ```
> Buffer token limit on first build: 5000
> users.token_limit in the database now: 99999
> Buffer token limit on second call: 5000      ← the write had no effect
> Same buffer object returned: True
> Buffer token limit after invalidation: 99999 ← only now it took effect
> ```

So a token-limit change is **inert until the operator switches sessions or clears the
history**. The two ways to change the limit and the one way to make it effective are three
unrelated places in the code.

### 2.3 The `token_limit` argument of `get_memory_buffer()` is ignored after the first call

This is a latent bug in the same function. The early return happens **before** the argument is
read (`chat_manager/manager.py:477-478`):

```python
def get_memory_buffer(self, token_limit: int | None = None) -> Any:
    if self._memory_buffer is not None:
        return self._memory_buffer          # ← token_limit never consulted
    ...
    limit = token_limit or (...)
```

> Probe output:
> ```
> First call with token_limit=111 -> buffer limit 111
> Second call with token_limit=222 -> buffer limit 111
> ```

The override is silently dropped. Any caller that believed it was tuning the buffer after the
first call was not.

### 2.4 The operator cannot even see the value

`cmd_chat_info()` (`chat_manager/commands/cli.py:152`) prints the session's ID, name, type, chat key and
timestamps. `token_limit` appears in **no** command output — verified by grep over
`chat_manager/commands/cli.py`.

### 2.5 The environment variable is a red herring

`TORVALDS_TOKEN_LIMIT` feeds the **legacy** path only (`agent_chat_memory._get_token_limit()`).
When the manager is active, the effective limit is `users.token_limit` (5000).

The variable is also read into a **dead** constant in both orchestrators:

| File | Line | Value | Used? |
|------|------|-------|-------|
| `agent-torvalds.py` | 196 | `TOKEN_LIMITS = int(os.environ.get("TORVALDS_TOKEN_LIMIT", "400"))` | **never** |
| `agent-torvalds-mw.py` | 216 | `TOKEN_LIMITS = int(os.environ.get("TORVALDS_TOKEN_LIMIT", "10000"))` | **never** |

> Probe output: `TOKEN_LIMITS defined=[(196, ...)] used=[]`

So the same concept has **four** different defaults in the codebase — 400, 10000, 5000 (legacy
helper) and 5000 (`users.token_limit`) — and the one the operator is most likely to look at
(the 400 in the classic REPL) is the one that does nothing.

---

## 3. Q2 — Do we need a command to manage user settings?

**Yes.** The evidence is in the original design documents, which the implementation followed
faithfully up to the point where the settings became unwritable:

| Document | Statement |
|----------|-----------|
| `investigate/ChatHistoryManager/ChatHistoryManager.md:76` | "Token limits \| `users.token_limit` column" |
| `investigate/ChatHistoryManager/ChatHistoryManager.md:96-100` | "Stores user identity and **preferences**: … `token_limit` (per-user token limit)" |
| `investigate/ChatHistoryManager/storage-proposal.md:291` | "User preferences \| `backend_type`, `token_limit` in `users` table" |
| `investigate/ChatHistoryManager/storage-proposal.md:6` | "Everything — user identities, session metadata, active session state, and **user preferences** — lives in the database." |

The design called the `users` table the home of the preferences. The implementation built the
table, the column, the ORM mapping, the dataclass field and the connector write — and then
stopped. The read path is a single expression inside a buffer factory. The write path has no
caller. The preference is therefore **write-only from the application's point of view**: the
value in the database is whatever the auto-provisioning put there.

A command layer is the right answer for three reasons:

1. **The operator is the only actor who can want a different limit.** A larger limit is a
   response to "the agent keeps forgetting the conversation"; a smaller one to "the context
   window is too full". Neither is a deployment-wide setting — they are per-user, per-machine
   preferences, which is exactly what the `users` table is for.
2. **The existing command layer is already the right shape.** `\chat-*` commands are dispatched
   by the agent's main loop *before* the LLM is invoked, so they cost no tokens and the model
   cannot trigger them. That is the correct place for a settings command.
3. **There is no other surface.** The TUI has no settings panel, and the startup banner prints
   only the session name.

### 3.1 What a settings command would have to touch

The command layer is deliberately centralised; a new command is not a one-file change:

| Path | Change |
|------|--------|
| `chat_manager/manager.py` | `get_user_settings()` / `update_user_settings(...)` — the missing API of §2.1, including buffer invalidation |
| `chat_manager/commands/cli.py` | `cmd_chat_user(manager)`, `cmd_chat_user_set(manager, key, value)` |
| `chat_manager/commands/handler.py` | `CHAT_COMMANDS` entry + dispatch branch |
| `chat_manager/commands/__init__.py` | export the new functions |
| `components/command_registry.py` | `CommandSpec` entry, so `\help` lists it (`FEATURE_CHAT_HISTORY`) |
| `components/tui/chat_history_view.py` | Markdown rendering, so the multi-window agent shows the same thing |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | startup hint lines (the classic REPL prints `\chat-*` hints in the banner) |
| `chat_manager/README.md` | the command table, the API reference, the configuration table |
| `tests/` | the new command, the new API, the buffer-invalidation behaviour |

---

## 4. Q3 — Is the old chat-history implementation still there?

**Yes, in four layers.**

### Layer 1 — `agent_chat_memory.py` (root, 273 lines)

The pre-`chat_manager` implementation, kept as a "compatibility layer". It still carries the
complete legacy machinery:

| Symbol | Legacy behaviour | Status |
|--------|------------------|--------|
| `_build_pg_uri()` | builds a `postgres+asyncpg://` URI from `TORVALDS_PG_*` | **live** — duplicates the manager's own resolution |
| `_get_chat_store_key()` | `TORVALDS_CHAT_KEY`, default `user1-abliterated` | **live** in the legacy branch |
| `_get_token_limit()` | `TORVALDS_TOKEN_LIMIT`, default 5000 | **live** in the legacy branch |
| `get_chat_store()` (`agent_chat_memory.py:114`) | creates a **raw `PostgresChatStore`** | **live** — bypasses the `ChatStoreBackend` abstraction the README says the agent "never" does |
| `get_chat_memory()` (`agent_chat_memory.py:145`) | prefers the manager, falls back to the legacy single-key buffer | **live** — the fallback branch is still there |
| `get_all_tools()` | exports `get_chat_store` and `get_chat_memory` as LLM `FunctionTool`s | **not registered** in `agent_tool_retriever.py`, so the LLM cannot reach them — but the function is public |

> Probe output:
> ```
> _get_chat_store_key() -> 'user1-abliterated'
> get_chat_memory() still contains the legacy fallback branch: True
> ```

The `get_chat_store()` raw-`PostgresChatStore` path deserves a specific note: it opens a
**second, independent** connection to the same message tables, outside the backend abstraction.
It is currently unreachable from the agent (the tools are not registered), but it is public and
importable.

### Layer 2 — the `--no-chat-history` flag

Present in **both** orchestrators:

| File | Line | Flag |
|------|------|------|
| `agent-torvalds.py` | 765 | `"--no-chat-history"` — "Disable the ChatHistoryManager (use the legacy single-session chat memory)" |
| `agent-torvalds-mw.py` | 756 | `"--no-chat-history"` — same |

And the startup error path in both orchestrators prints
*"Falling back to the legacy single-session chat memory."* — so the legacy path is not only
flag-selectable, it is also the **automatic** behaviour when the manager fails to initialise.

### Layer 3 — the `TORVALDS_CHAT_KEY` migration hook

`manager._create_default_sessions()` (`chat_manager/manager.py:242-245`) still reads the legacy
single-key variable and reuses it as the `chat_key` of the pre-seeded **General Chat** session:

```python
legacy_key = os.environ.get("TORVALDS_CHAT_KEY", "")
general_key = legacy_key if legacy_key else f"chat-general-{uid}"
```

This is a **deliberate** migration aid, and the README documents it. It is also the reason
"messages from a previous topic still appear" is a known symptom (the Troubleshooting table).

### Layer 4 — dead configuration

`TOKEN_LIMITS` in both orchestrators (§2.5) — defined, never used, with four competing
defaults for one concept.

---

## 5. Can the legacy implementation be removed?

**Not safely, today.** One thing still depends on it.

### 5.1 The blocker

The **message** layer degrades on its own:

> ```
> message backend in use: SimpleChatStoreBackend
> metadata connector connected: True
> ```

The **metadata** layer does not:

> ```
> initialize() raised: RuntimeError: CustomDBConnector is not connected
> manager.is_initialized: False
> ```

`CustomDBConnector.connect()` (`chat_manager/storage/connector.py:178`) catches the connection error and
sets `_connected = False`; the next call — `get_user_by_username()` from `_identify_user()` —
raises `RuntimeError("CustomDBConnector is not connected")`, which propagates out of
`initialize()`. The orchestrators catch it, print *"Falling back to the legacy single-session
chat memory."*, and continue with the legacy buffer.

So the legacy path is **load-bearing** in exactly one scenario: *the metadata database is
unreachable*. Remove it without a replacement and the agent loses chat memory entirely in that
scenario, instead of degrading to a flat single-key history.

### 5.2 The fix that unblocks the removal

The manager already knows how to run on SQLite — the whole test suite uses
`sqlite:///:memory:`. The connector is a plain SQLAlchemy engine; it is the **URI resolution**
that only ever produces a PostgreSQL URI.

Give `CustomDBConnector` the same shape of fallback the message backend already has:

* on connection failure, retry against a local SQLite file (e.g. `~/.torvalds/chat_manager.db`)
  and log the degradation;
* the manager then works **fully** — users, sessions, active-session state, per-user token
  limits — just without cross-machine sharing.

With that in place the legacy single-key path has no remaining job: the manager covers both
"PostgreSQL up" (full features) and "PostgreSQL down" (degraded but complete).

### 5.3 Proposed order of work

| Phase | Scope | Why first |
|-------|-------|-----------|
| **A** | Add the user-settings API + command (§3.1) | Fills the gap the design intended; independent of the legacy removal |
| **B** | Add the SQLite fallback to `CustomDBConnector` (§5.2) | Makes the legacy path redundant |
| **C** | Remove the legacy implementation (§6) | Only safe after B |

Doing C before B would remove the only thing that keeps the agent usable when the database is
down.

---

## 6. What the removal would touch

| Path | Legacy artefact | Action |
|------|-----------------|--------|
| `agent_chat_memory.py` | the whole module (273 lines) | delete; the orchestrators call `manager.get_memory_buffer()` directly |
| `agent-torvalds.py:114` | `import agent_chat_memory` | replace with `get_chat_manager().get_memory_buffer()` |
| `agent-torvalds.py:576, 852` | `agent_chat_memory.get_chat_memory()` | same |
| `agent-torvalds-mw.py:127, 568, 843, 1411` | same | same |
| `agent-torvalds-cpp.py:5, 35, 61` | `agent_chat_memory.chat_memory` | same — note this file is not wired into the CI test paths but is listed in the README |
| `agent-torvalds.py:765`, `agent-torvalds-mw.py:756` | `--no-chat-history` | deprecate with a warning, or re-define it as "no persistence" once the SQLite fallback exists |
| `agent-torvalds.py:196`, `agent-torvalds-mw.py:216` | `TOKEN_LIMITS` | delete (dead) |
| `chat_manager/manager.py:242-245` | the `TORVALDS_CHAT_KEY` migration hook | keep for one release, then remove |
| `tests/test_logging_cli.py:34, 228` | imports `agent_chat_memory`'s logger | update |
| `chat_manager/README.md` | the "Compatibility layer" section, the `TORVALDS_CHAT_KEY` / `TORVALDS_TOKEN_LIMIT` configuration rows | update |
| `README.md`, `CHANGELOG.md` | the same | update |

### 6.1 A note on `--no-chat-history`

It is a **user-facing CLI flag**. Removing it outright would break anyone's scripts. The
friendly option is to keep the flag, print a deprecation warning, and — once the SQLite
fallback of §5.2 exists — re-define it as *"do not persist anything; use an in-memory
store only"*. The flag then keeps a real meaning instead of selecting a dead code path.

---

## 7. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing the legacy path before the SQLite fallback exists | **high** — the agent loses chat memory when PostgreSQL is down | Phase order: B before C |
| A user-settings command writes a limit that the running buffer ignores | medium | `update_user_settings()` invalidates the buffer; a regression test asserts the new limit is live |
| `token_limit` accepted from the operator without validation | medium | bound it (e.g. 256 ≤ limit ≤ 1_000_000); reject non-numeric input with a clear message |
| The `\help` screen drifting from the real behaviour | low | declare the command in `components/command_registry.py`, which both orchestrators render from |
| The TUI and the classic REPL behaving differently | low | implement in `chat_manager/commands/cli.py` (shared) and render in `components/tui/chat_history_view.py` |
| The four conflicting token-limit defaults | low | collapse to one source of truth — `users.token_limit` — and delete the dead `TOKEN_LIMITS` |
| SQLite fallback silently diverging from PostgreSQL semantics | low | the connector already speaks plain SQLAlchemy; the test suite already runs the whole manager on SQLite |

---

## 8. Summary of the defects found

| ID | Defect | Location |
|----|--------|----------|
| **C1** | No public API to change `user.token_limit`; the only write path is the private `manager._db.update_user()` | `chat_manager/manager.py` |
| **C2** | A changed `token_limit` does not reach the live buffer — the buffer caches the limit and is only invalidated by `switch_session()` / `clear_messages()` | `chat_manager/manager.py:464-499` |
| **C3** | The `token_limit` argument of `get_memory_buffer()` is ignored on every call after the first | `chat_manager/manager.py:477-478` |
| **C4** | No command reads or writes the user's settings; the current limit is not even displayed | `chat_manager/commands/` |
| **C5** | The legacy single-key implementation is still present and reachable | `agent_chat_memory.py` |
| **C6** | `--no-chat-history` selects the legacy path; the startup error path selects it automatically | both orchestrators |
| **C7** | `TOKEN_LIMITS` is dead in both orchestrators, with a fourth default (400 / 10000 / 5000 / 5000) for one concept | `agent-torvalds.py:196`, `agent-torvalds-mw.py:216` |
| **C8** | The metadata layer has no fallback, so the legacy path is the *only* thing that survives a database outage | `chat_manager/storage/connector.py:178` |
| **C9** | `get_chat_store()` opens a raw `PostgresChatStore` outside the backend abstraction | `agent_chat_memory.py:114` |

**C8 is the one that decides the order of the work.** C1–C4 and C7 can be fixed at any time.
C5, C6 and C9 must wait for the SQLite fallback.

---

## 9. How to reproduce

```bash
cd self-development
.venv/bin/python investigate/chat-manager-user-settings/probe_user_settings.py
```

The probe answers all six questions with printed evidence and needs no database server
(it uses `sqlite:///:memory:` and an unreachable PostgreSQL URI to simulate an outage).

The existing suite is green and is the regression baseline for any change:

```bash
cd self-development
.venv/bin/python -m pytest chat_manager/tests -q     # 104 passed
```
