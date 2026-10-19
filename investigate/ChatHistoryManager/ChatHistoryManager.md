# 1. Task Description: Multi‑Chat History Wrapper for LlamaIndex Agent

## 2. Goal
Implement a **chat history management wrapper** that enables a LlamaIndex Agent to switch between multiple conversation sessions (e.g., *general*, *project*, and user‑created chats).  
The wrapper must abstract away the underlying storage backend so that the system can replace `PostgresChatStore(BaseChatStore)` in the future without modifying agent logic.

This system will rely on:
- **Table A:** the existing LlamaIndex chat message table (managed internally by `PostgresChatStore`)
- **Table B:** a new custom chat session table (managed by the wrapper)

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
- a human‑readable name (for project the name is project name, for general conversation the name must reflect a conversation topik in 2-3 words) 
- optional metadata (type, tags, project ID)  
- its own message history (via mapping to a chat_key)
- All operation related to chat history, like chat selection must be done using commands not agent tools.
---

### 3.3 Dual‑table storage model and config

#### Table A — LlamaIndex message table (existing)
- Created and managed internally by `PostgresChatStore(BaseChatStore)`
- Stores messages only
- Uses `chat_key` to identify a conversation
- Must remain unchanged for compatibility

#### Table B — Custom chat session table (new)
- Managed by the wrapper
- Stores session metadata:
  - session_id  
  - session_name  
  - session_type  
  - created_at  
  - metadata (optional JSON)

#### Local Config:
- Store current chat in agent config: 
    - The agent propose last chat as a default during agent sturt-up 
    - Ability to switch to the chat from list if user skip load default for last session.

The wrapper maps:
    session_id → chat_key


This enables multi‑chat support while keeping LlamaIndex storage untouched.

---

### 3.4 Startup chat selection
On application startup:
1. Load all available chat sessions from the custom session table.  
2. Present them to the user as a selectable list.  
3. Allow the user to choose an existing session or create a new one.  
4. Store the selected session ID (e.g., agent config).  
5. Initialize the agent with this session as the active conversation by mapping it to the correct `chat_key`.

---

### 3.5 Message routing
All messages sent or received by the agent must be stored under the **currently active session**.

Switching sessions:
- changes the active `session_id`
- updates the mapped `chat_key`
- loads the correct message history
- ensures clean separation between conversations

---

### 3.6 Future‑proofing
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

### 3.7 Module Location
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
- the storage backend can be replaced at any time  
- the agent always interacts through a stable wrapper API  
- LlamaIndex's existing message table remains fully compatible  

This design ensures long‑term evolution of the chat history subsystem while keeping the agent architecture stable.
