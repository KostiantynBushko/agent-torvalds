# Proposal — renaming `token_limit` to `chat_token_limit`

**Date:** 2026-10-25
**Scope:** `chat_manager/` (the `users` table, the `User` dataclass, the manager API), the
`\chat-user` command, the database column.
**Status:** proposal — the implementation on `feature/chat-user-settings` follows
**Recommendation 1** below.

---

## 1. The problem

The setting currently called `token_limit` decides how many tokens of **chat history** the
agent keeps in the `ChatMemoryBuffer` of the active session. The name says *token limit* and
nothing else, but "token limit" is used for at least four different things in this codebase and
its neighbourhood:

| # | Concept | Where it lives | Value |
|---|---------|----------------|-------|
| 1 | The **chat history** budget of the user's active session | `users.token_limit` → `ChatMemoryBuffer.from_defaults(token_limit=…)` | 5000 |
| 2 | The **model's** context window | `components/ollama_config.py` → `llm.context_window` | per model |
| 3 | The **legacy** single-key buffer budget | `TORVALDS_TOKEN_LIMIT` → `agent_chat_memory._get_token_limit()` | 5000 |
| 4 | The **dead** orchestrator constant | `TOKEN_LIMITS` in `agent-torvalds.py:196` / `agent-torvalds-mw.py:216` | 400 / 10000 |

The names collide, the defaults disagree, and — as the investigation report
(`INVESTIGATION_REPORT.md`, defect **C7**) shows — the number an operator is most likely to
look at (the 400 in the classic REPL) is the one that does nothing.

The operator's own words: *"the name `token_limit` is incorrect, this is applied to chat token."*
That is exactly the distinction the name is missing: **whose** tokens.

---

## 2. What the setting actually does

Traced end to end:

```
users.chat_token_limit  (int)
   │
   ├─► chat_manager.storage.models.User.chat_token_limit     (ORM column)
   ├─► chat_manager.user.User.chat_token_limit                (dataclass field)
   │      │
   │      └─► ChatHistoryManager.get_memory_buffer()
   │             limit = chat_token_limit  (or the caller's override)
   │             ChatMemoryBuffer.from_defaults(token_limit=limit)
   │                  │
   │                  └─► the buffer keeps the newest messages while the
   │                      summed token count stays under the limit, and
   │                      drops the oldest ones when it is exceeded.
   │
   └─► nothing else.  It is not a model limit, not a rate limit, not a
      per-message limit and not a session limit.
```

So the precise meaning is: **the maximum number of tokens of conversation history that the
agent keeps in memory for the active chat session.** The chat store itself keeps every message
on disk; the limit only governs what is held in the buffer that is replayed to the model.

---

## 3. Candidates

| Candidate | Reads as | Verdict |
|-----------|----------|---------|
| `token_limit` | "a limit on tokens" — which tokens? | **Rejected.** Ambiguous against the model's `context_window`, the legacy env var and the dead `TOKEN_LIMITS` constant. |
| **`chat_token_limit`** | "the limit on *chat* tokens" | **Recommended.** Says whose tokens. Matches the operator's phrasing. No collision with any other concept in the tree. |
| `memory_token_limit` | "the limit of the memory buffer" | Rejected. Binds the setting to a LlamaIndex class name (`ChatMemoryBuffer`) rather than to the domain concept; "memory" is already overloaded in this agent (the agent's own memory, the buffer, the memory backend). |
| `context_token_limit` | "the limit of the context" | Rejected. `context_window` already means **the model's** context window in `components/ollama_config.py`. A second "context" word would create a new ambiguity instead of removing one. |
| `history_token_limit` | "the limit of the history" | Rejected. Accurate but too narrow: the buffer holds the *live context* of the conversation, not a log. The chat store keeps the history; the buffer keeps the context. |
| `max_chat_tokens` | "the maximum number of chat tokens" | Rejected. Grammatically fine, but reads like a constant rather than a persisted, named setting, and loses the "limit" noun that the rest of the schema uses. |
| `chat_context_limit` | "the limit of the chat context" | Rejected. Same collision with `context_window` as `context_token_limit`, and less precise about the unit. |

---

## 4. Recommendation 1 — `chat_token_limit` (implemented)

**`chat_token_limit` is the canonical name** of the user's chat-history token budget.

Why it is the right name:

1. **It answers the question the operator has to ask.** "Which tokens?" → "The chat ones."
   No other candidate answers that in one word.
2. **It is unambiguous inside this tree.** `grep -rn "context_window"` finds the model's
   window; `grep -rn "chat_token_limit"` will find exactly one concept — the chat history
   budget — and it will be the *only* one.
3. **It keeps the unit visible.** `token` is the unit, `limit` is the operation,
   `chat` is the scope. `chat_token_limit` reads as "the chat-token limit".
4. **It is the shortest name that carries all three parts.** `chat_token_limit` (16 chars)
   versus `chat_history_token_limit` (24) — the latter is precise but noisy for a setting that
   is typed on a command line: `\chat-user set chat_token_limit 12000`.
5. **It matches the command surface.** The command that owns it is `\chat-user`, and the key
   inside it is `chat_token_limit`.

### 4.1 What is renamed

| Layer | Before | After |
|-------|--------|-------|
| DB column | `users.token_limit` | `users.chat_token_limit` |
| ORM attribute | `User.token_limit` | `User.chat_token_limit` (old name kept as a SQLAlchemy `synonym`) |
| Dataclass field | `User.token_limit` | `User.chat_token_limit` |
| Manager API | `get_memory_buffer(token_limit=…)` | `get_memory_buffer(chat_token_limit=…)` |
| Command key | — | `chat_token_limit` (alias: `token_limit`) |
| Environment | `TORVALDS_TOKEN_LIMIT` | **unchanged** — it belongs to the legacy compatibility buffer, which is a different thing (§5.3) |

### 4.2 Backwards compatibility

Renaming a persisted column and a published dataclass field is a breaking change unless it is
handled deliberately. The implementation keeps **three** compatibility seams:

1. **Database.** `CustomDBConnector.connect()` runs an idempotent migration: if the `users`
   table has a `token_limit` column and no `chat_token_limit` column, it renames the column
   in place (`ALTER TABLE users RENAME COLUMN token_limit TO chat_token_limit`). Existing
   databases keep their values and need no manual step. The migration is skipped silently when
   there is nothing to migrate, and it never fails the connect — a migration problem is logged
   as a warning, because losing the chat history is worse than a stale column name.
2. **Python API.** `User.token_limit` remains as a deprecated **property** (getter *and*
   setter) that proxies to `chat_token_limit`, and `User(token_limit=5000)` still works as a
   constructor keyword. `User.to_dict()` emits **both** keys — the canonical
   `chat_token_limit` and the legacy `token_limit` mirror — so an old reader of the dict keeps
   working, and `User.from_dict()` accepts either key.
3. **Command.** `\chat-user set token_limit 12000` keeps working: `token_limit` is a registered
   **alias** of the `chat_token_limit` key. The reply always names the canonical key.

### 4.3 The deprecation path

| Release | State |
|---------|-------|
| This change | `chat_token_limit` is canonical everywhere. `token_limit` still works as an alias/property/mirror and is **not** advertised in `\help`. |
| Next release | The `token_limit` alias, the constructor keyword and the dict mirror are announced as deprecated in `CHANGELOG.md`. |
| After that | Removal is proposed once no deployment is known to run the old column name. The database column keeps its values through the rename — a removal would need a second migration, so it is not worth doing for a name that costs nothing to keep. |

---

## 5. Alternatives that were considered and rejected as a whole

### 5.1 Keep `token_limit` and only document it

Rejected. The defect is not documentation — it is that the same word means four different
things in one repository (§1). A docstring cannot fix that; a distinct name can.

### 5.2 Rename to `context_window` to match the LLM

Rejected. They are **not** the same thing: `context_window` is the size of the model's
window, `chat_token_limit` is the slice of the conversation the agent keeps in the buffer.
The buffer limit must always be *smaller* than the model's window. Using the same name for
both would invite exactly the confusion the rename is meant to remove.

### 5.3 Rename `TORVALDS_TOKEN_LIMIT` as well

Deliberately **not** done here. `TORVALDS_TOKEN_LIMIT` configures the **legacy**
single-key compatibility buffer (`agent_chat_memory._get_token_limit()`), which is a
different code path with a different lifetime. The investigation report puts the removal of
the legacy implementation in **Phase C**, and Phase C is blocked on **Phase B** (the SQLite
fallback in `CustomDBConnector`). Touching the legacy env var now would break the legacy path
while the new path is not yet able to replace it. It is listed in the Phase C checklist
instead.

---

## 6. The naming rule that follows from this

A setting name in this codebase answers **"whose <noun> is this, and what is the unit?"**:

```
<scope>_<unit>_<operation>
   |       |       |
   |       |       +-- limit, max, timeout, count
   |       +---------- token, message, session, byte
   +------------------ chat, model, tool, user
```

Applied to the existing settings:

| Setting | Scope | Unit | Operation | Verdict |
|---------|-------|------|-----------|---------|
| `chat_token_limit` | chat | token | limit | **canonical** |
| `token_limit` | — | token | limit | deprecated alias |
| `TORVALDS_TOKEN_LIMIT` | legacy chat | token | limit | Phase C |

---

## 7. Summary

| Question | Answer |
|----------|--------|
| Is `token_limit` incorrect? | **Yes** — it names the unit but not the scope, and the scope is the only interesting part. |
| What is the better name? | **`chat_token_limit`** — it is the shortest name that states whose tokens are limited, it matches the operator's own wording, and it collides with nothing in the tree. |
| Is the rename backwards compatible? | **Yes** — the column is migrated in place, the Python attribute and constructor keyword survive as deprecated aliases, and the command accepts the old key. |
| What else is renamed with it? | Nothing. `TORVALDS_TOKEN_LIMIT` belongs to the legacy path, whose removal is Phase C and blocked on Phase B. |
