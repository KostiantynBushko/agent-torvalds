# 1. Task Description: Multi‑Chat History Wrapper for LlamaIndex Agent

## 2. Goal
Implement a **chat history management wrapper** that enables a LlamaIndex Agent to switch between multiple conversation sessions (e.g., *general*, *project*, and user‑created chats).  
The wrapper must abstract away the underlying storage backend so that the system can replace `PostgresChatStore(BaseChatStore)` in the future without modifying agent logic.

This system will rely on:
- **Table A:** the existing LlamaIndex chat message table (managed internally by `PostgresChatStore`)
- **Table B:** a new custom **users** table (user identity, multi-user support)
- **Table C:** a new custom **chat_sessions** table (session metadata, active state)

**All state** — including the current active session — is stored **exclusively in the custom database**. No local config files or cache files are used for session state.

---

## 3. Requirements

### 3.1 Backend‑agnostic design
Create a **ChatHistoryManager** that acts as a stable interface for all chat history operations.  
The agent interacts **only** with this manager, never directly with `PostgresChatStore`.

The manager must support:
- listing available chat sessions  
- creating new chat sessions  
- selecting an active session  
- loading history for the active session  
- storing new messages  

The underlying backend Llama Index (PostgresChatStore) can be replaceable without modifying the agent.
The **ChatHistoryManager** provides an interface to the underlying memory storage.

---

### 3.2 Multi‑session chat architecture
Introduce a session layer so the system can maintain multiple independent conversations.

Two predefined sessions:
- **general**  
- **project**

Users must also be able to create additional custom sessions.

Each session has:
- a unique session ID  
- a human‑readable name (for project the name is project name, for general conversation the name must reflect a conversation topic in 2-3 words) 
- optional metadata (type, tags, project ID)  
- its own message history (via mapping to a chat_key)
- All operations related to chat history, like chat selection must be done using commands not agent tools.

---

### 3.3 Multi‑User Support
The system must support **multiple users** sharing the same database instance.

- Each user has a **unique identity** stored in the `users` table
- Sessions are **scoped per user** — each user has their own set of sessions
- The **active session** is tracked per user in the database
- On startup, the manager identifies the current user (by OS username or explicit login) and loads their sessions

**User identification:**
- Default: OS username (`os.getlogin()`)
- Future: explicit login mechanism

---

### 3.4 Database-Only Persistence

**No local config files or cache files are used.** All state is stored in the custom SQLite database:

| What | Where |
|---|---|
| User identities | `users` table |
| Session metadata | `chat_sessions` table |
| Active session per user | `chat_sessions.is_active` + `user_id` FK |
| Backend configuration | `users.backend_type` column |
| Token limits | `users.token_limit` column |

This eliminates:
- `~/.config/torvalds/chat_config.json`
- `~/.cache/torvalds/agent_cache.json`

Everything is in the database.

---

### 3.5 Dual‑Table Storage Model (LlamaIndex + Custom DB)

#### Table A — LlamaIndex message table (existing)
- Created and managed internally by `PostgresChatStore(BaseChatStore)`
- Stores messages only
- Uses `chat_key` to identify a conversation
- Must remain unchanged for compatibility

#### Table B — Custom users table (new)
- Managed by the wrapper
- Stores user identity and preferences:
  - `user_id` (primary key)
  - `username` (unique, derived from OS login)
  - `backend_type` (preferred storage backend)
  - `token_limit` (per-user token limit)
  - `created_at`
  - `is_active` (current session flag)

#### Table C — Custom chat_sessions table (new)
- Managed by the wrapper
- Stores session metadata:
  - `session_id` (primary key)
  - `user_id` (foreign key → users)
  - `session_name`
  - `session_type`
  - `chat_key` (maps to Table A)
  - `metadata` (optional JSON)
  - `created_at`
  - `updated_at`
  - `is_active` (one active session per user)

The wrapper maps:
```
user_id + session_id → chat_key
```

This enables multi‑chat, multi‑user support while keeping LlamaIndex storage untouched.

---

### 3.6 Startup chat selection
On application startup:
1. Identify current user (OS username)
2. Look up user in `users` table (create if not exists)
3. Load all sessions for this user from `chat_sessions` table
4. Check if user has an active session (`is_active = TRUE`)
5. If active session exists → propose it as default
6. Present sessions to user as a selectable list
7. Allow user to choose an existing session or create a new one
8. Update `is_active` flag in DB for selected session
9. Initialize the agent with this session as the active conversation

---

### 3.7 Message routing
All messages sent or received by the agent must be stored under the **currently active session**.

Switching sessions:
- updates `is_active` flag in `chat_sessions` table for the new session
- sets `is_active = FALSE` for the previous session
- updates the mapped `chat_key`
- loads the correct message history
- ensures clean separation between conversations

---

### 3.8 Future‑proofing
The wrapper must allow replacing the backend with:
- Redis  
- SQLite  
- MongoDB  
- Local JSON files  
- Cloud storage  

without changing:
- agent initialization  
- agent logic  
- session switching behavior  
- message routing logic  

The wrapper becomes the **stable API**, and the backend becomes a **pluggable driver**.

---

### 3.9 Module Location
The **ChatHistoryManager** must be implemented as a **separate module** under the following path:

```
chat-manager/
```

located in the **project root folder**. This module will be fully self-contained and importable by the agent without coupling to other internal modules.

---

## 4. Outcome
A flexible, backend‑agnostic multi‑chat system where:
- conversations are separated into sessions  
- users can switch between chats  
- history persists across runs  
- multiple users can share the same database  
- the storage backend can be replaced at any time  
- the agent always interacts through a stable wrapper API  
- LlamaIndex's existing message table remains fully compatible  
- **all state is stored in the database — no local config or cache files**  

This design ensures long‑term evolution of the chat history subsystem while keeping the agent architecture stable.
