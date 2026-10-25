# Investigation — `chat_manager` user settings and the legacy implementation

**Status:** investigation complete — **no source file of the agent was modified.**
**Date:** 2026-10-25

## The three questions that were asked

1. How do we change `user.token_limit`?
2. Do we need a command to manage user settings?
3. Is the old chat-history implementation still there — and if so, can it go?

## The answers

| # | Answer in one line |
|---|---------------------|
| 1 | **We cannot.** There is no public API; the only write path is the private `manager._db.update_user()`, and even that does not reach the live buffer. |
| 2 | **Yes.** The `users` table was designed to hold the user's preferences, but no command can read or write them — the operator cannot even see the current value. |
| 3 | **Yes, in four layers** — and one of them is load-bearing: the legacy path is the only thing that keeps the agent usable when the metadata database is down. |

## The one finding that decides the order of the work

The message layer degrades on its own (`SimpleChatStoreBackend`); the **metadata** layer does
not. When PostgreSQL is unreachable, `ChatHistoryManager.initialize()` raises
`RuntimeError: CustomDBConnector is not connected`, and the orchestrators fall back to the
legacy single-session memory.

So the legacy implementation **cannot be deleted yet**. The removal becomes safe once
`CustomDBConnector` gets the same kind of fallback the message backend already has (a local
SQLite file). The manager already runs on SQLite — the entire test suite does.

| Phase | Scope |
|-------|-------|
| **A** | Add the user-settings API and the `\chat-user` command |
| **B** | Add the SQLite fallback to `CustomDBConnector` |
| **C** | Remove the legacy implementation |

Doing **C** before **B** removes the only thing that keeps the agent working during a
database outage.

## Files

| File | What it is |
|------|------------|
| `INVESTIGATION_REPORT.md` | The report: findings C1–C9, the design evidence, the removal plan, the risks |
| `probe_user_settings.py` | The executable probe — answers all six questions with printed evidence |
| `verify_report_references.py` | Checks that every `file:line` reference in the report resolves to the claimed construct |

## Running them

```bash
cd self-development

# The probe — no database server needed.
.venv/bin/python investigate/chat-manager-user-settings/probe_user_settings.py

# The reference check — must report PASS.
.venv/bin/python investigate/chat-manager-user-settings/verify_report_references.py

# The regression baseline for any change that follows.
.venv/bin/python -m pytest chat_manager/tests -q     # 104 passed
```

The probe uses `sqlite:///:memory:` and an unreachable PostgreSQL URI to simulate an outage,
so it never touches a real database.

## Where the defects are

| ID | Defect | Location |
|----|--------|----------|
| **C1** | No public API to change `user.token_limit` | `chat_manager/manager.py` |
| **C2** | A changed `token_limit` does not reach the live buffer | `chat_manager/manager.py:464-499` |
| **C3** | The `token_limit` argument of `get_memory_buffer()` is ignored after the first call | `chat_manager/manager.py:477-478` |
| **C4** | No command reads or writes the user's settings | `chat_manager/commands/` |
| **C5** | The legacy single-key implementation is still present and reachable | `agent_chat_memory.py` |
| **C6** | `--no-chat-history` selects the legacy path; the startup error path selects it automatically | both orchestrators |
| **C7** | `TOKEN_LIMITS` is dead in both orchestrators — four competing defaults for one concept | `agent-torvalds.py:196`, `agent-torvalds-mw.py:216` |
| **C8** | The metadata layer has no fallback | `chat_manager/storage/connector.py:178` |
| **C9** | `get_chat_store()` opens a raw `PostgresChatStore` outside the backend abstraction | `agent_chat_memory.py:114` |
