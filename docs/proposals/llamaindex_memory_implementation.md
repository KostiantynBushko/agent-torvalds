# LlamaIndex Memory Implementation Proposal

## Overview

This proposal outlines how to integrate LlamaIndex's new `Memory` architecture (v0.14.24+) into the Torvalds agent system. The goal is to replace the current basic `ChatMemoryBuffer` with a more sophisticated, multi-block memory system that provides:

- **Long-term context retention** via summarization and vector storage
- **Fact extraction** for persistent knowledge about the user/environment
- **Static context injection** for system prompts and instructions
- **Composable memory blocks** for modular, extensible memory architecture

> **Source Reference:** https://developers.llamaindex.ai/python/examples/memory/memory/

---

## Current State

### Existing Implementation

The current `agent_chat_memory.py` module uses:

- `ChatMemoryBuffer` (deprecated in v0.14.24)
- `PostgresChatStore` for persistence
- Simple token-limited buffer (default 3000 tokens)
- Single conversation key per user

### Limitations

| Issue | Impact |
|-------|--------|
| Flat token buffer | Loses context when token limit is exceeded |
| No summarization | Cannot retain key information from older messages |
| No fact extraction | Cannot persist learned facts about user/environment |
| No vector retrieval | Cannot search historical conversations semantically |
| Single memory type | No composability or layered memory architecture |

---

## LlamaIndex Memory Architecture (v0.14.24+)

### Core Class: `Memory`

The new `Memory` class orchestrates memory through a **waterfall architecture**:

```
┌─────────────────────────────────────────────────┐
│              Memory (Orchestrator)               │
│  ┌───────────────────────────────────────────┐  │
│  │           FIFO Message Queue              │  │
│  │  (token_limit, pressure_size params)      │  │
│  └───────────────────┬───────────────────────┘  │
│                      │ eject on overflow         │
│  ┌───────────────────▼───────────────────────┐  │
│  │          Memory Blocks (List)             │  │
│  │  ┌─────────────┐ ┌─────────────┐         │  │
│  │  │ Block 1     │ │ Block 2     │ ...      │  │
│  │  │ (Static)    │ │ (Summary)   │           │  │
│  │  └─────────────┘ └─────────────┘           │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Workflow

1. Messages are added to a FIFO queue via `put()` / `put_messages()`
2. When the queue reaches `token_limit`, oldest messages within `pressure_size` are ejected
3. Ejected messages are processed by each memory block in order
4. When pulling messages via `get()`, memory blocks are processed and messages injected into the system message or latest user message

### Available Memory Block Types

| Block Type | Purpose | Key Features |
|------------|---------|--------------|
| `StaticMemoryBlock` | Constant context injection | System prompts, instructions, fixed information |
| `ChatSummaryMemoryBuffer` (via block) | Summarize old messages | Iterative LLM summarization, preserves key info |
| `FactExtractionMemoryBlock` | Extract discrete facts | XML-structured facts from conversation |
| `VectorMemoryBlock` | Semantic retrieval | Vector store-backed historical search |

### Key Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `token_limit` | int | Max tokens in FIFO queue before ejection |
| `pressure_size` | int | Number of oldest messages to eject when limit reached |
| `memory_blocks` | list[MemoryBlock] | Ordered list of memory blocks |
| `chat_store` | ChatStore (optional) | Persistent storage backend |
| `chat_store_key` | str | Unique conversation identifier |

---

## Proposed Implementation for Torvalds

### Phase 1: Basic Migration

**Goal:** Replace deprecated `ChatMemoryBuffer` with new `Memory` class.

```python
from llama_index.core.memory import Memory, StaticMemoryBlock

def get_chat_memory() -> Memory:
    memory = Memory.from_defaults(
        token_limit=4000,
        pressure_size=10,
        memory_blocks=[
            StaticMemoryBlock(text="You are Torvalds, an AI assistant..."),
        ],
        chat_store=get_chat_store(),
        chat_store_key=_get_chat_store_key(),
    )
    return memory
```

**Changes:**
- [ ] Update `agent_chat_memory.py` to use `Memory` instead of `ChatMemoryBuffer`
- [ ] Add `StaticMemoryBlock` for system prompt injection
- [ ] Test PostgreSQL persistence compatibility

### Phase 2: Summarization Memory

**Goal:** Add iterative summarization to retain context from long conversations.

```python
from llama_index.core.memory import Memory, StaticMemoryBlock, ChatSummaryMemoryBuffer

memory = Memory.from_defaults(
    token_limit=4000,
    pressure_size=10,
    memory_blocks=[
        StaticMemoryBlock(text="System prompt..."),
        # Summarize ejected messages using LLM
        ChatSummaryMemoryBuffer.from_defaults(
            llm=llm,
            token_limit=2000,
            summary_token_limit=500,
        ),
    ],
    chat_store=get_chat_store(),
    chat_store_key=_get_chat_store_key(),
)
```

**Changes:**
- [ ] Integrate LLM instance (Ollama/OpenAI) for summarization
- [ ] Configure `summary_token_limit` for compact summaries
- [ ] Test summarization quality and performance impact

### Phase 3: Fact Extraction

**Goal:** Extract and persist key facts about the user, environment, and preferences.

```python
from llama_index.core.memory import Memory, StaticMemoryBlock, FactExtractionMemoryBlock

memory = Memory.from_defaults(
    token_limit=4000,
    pressure_size=10,
    memory_blocks=[
        StaticMemoryBlock(text="System prompt..."),
        ChatSummaryMemoryBuffer.from_defaults(llm=llm, ...),
        # Extract facts like "User prefers Python", "Project uses PostgreSQL"
        FactExtractionMemoryBlock.from_defaults(
            llm=llm,
            max_facts=100,
        ),
    ],
    chat_store=get_chat_store(),
    chat_store_key=_get_chat_store_key(),
)
```

**Changes:**
- [ ] Add `FactExtractionMemoryBlock` to memory pipeline
- [ ] Configure `max_facts` limit
- [ ] Test fact extraction accuracy and persistence

### Phase 4: Vector Memory

**Goal:** Enable semantic search over conversation history.

```python
from llama_index.core.memory import Memory, StaticMemoryBlock, VectorMemoryBlock
from llama_index.core.vector_stores import SimpleVectorStore

memory = Memory.from_defaults(
    token_limit=4000,
    pressure_size=10,
    memory_blocks=[
        StaticMemoryBlock(text="System prompt..."),
        ChatSummaryMemoryBuffer.from_defaults(llm=llm, ...),
        FactExtractionMemoryBlock.from_defaults(llm=llm, ...),
        # Vector-backed retrieval of relevant historical messages
        VectorMemoryBlock.from_defaults(
            embed_model=embed_model,
            vector_store=SimpleVectorStore(),
            retriever_kwargs={"similarity_top_k": 5},
        ),
    ],
    chat_store=get_chat_store(),
    chat_store_key=_get_chat_store_key(),
)
```

**Changes:**
- [ ] Integrate embedding model (Ollama/OpenAI)
- [ ] Configure vector store (PostgreSQL pgvector or SimpleVectorStore)
- [ ] Test semantic retrieval relevance and performance

### Phase 5: PostgreSQL Vector Integration

**Goal:** Replace in-memory vector store with PostgreSQL pgvector for persistence.

```python
from llama_index.vector_stores.postgres import PGVectorStore

vector_store = PGVectorStore.from_params(
    database=_get_pg_uri(),
    table_name="memory_vectors",
    embed_dim=768,  # Ollama nomic-embed-text
)

memory = Memory.from_defaults(
    token_limit=4000,
    pressure_size=10,
    memory_blocks=[
        StaticMemoryBlock(text="System prompt..."),
        ChatSummaryMemoryBuffer.from_defaults(llm=llm, ...),
        FactExtractionMemoryBlock.from_defaults(llm=llm, ...),
        VectorMemoryBlock.from_defaults(
            embed_model=embed_model,
            vector_store=vector_store,
            retriever_kwargs={"similarity_top_k": 5},
        ),
    ],
    chat_store=get_chat_store(),
    chat_store_key=_get_chat_store_key(),
)
```

**Changes:**
- [ ] Create PostgreSQL table for vector storage
- [ ] Configure PGVectorStore with proper embedding dimensions
- [ ] Test vector persistence and retrieval

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Torvalds Agent                           │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Memory (Orchestrator)                     │  │
│  │                                                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │           FIFO Message Queue                    │  │  │
│  │  │  token_limit=4000, pressure_size=10             │  │  │
│  │  └──────────────────────┬──────────────────────────┘  │  │
│  │                         │ eject                       │  │
│  │  ┌──────────────────────▼──────────────────────────┐  │  │
│  │  │           Memory Blocks (Ordered)               │  │  │
│  │  │                                                 │  │  │
│  │  │  1. StaticMemoryBlock                           │  │  │
│  │  │     └─ System prompt, Torvalds identity         │  │  │
│  │  │                                                 │  │  │
│  │  │  2. ChatSummaryMemoryBuffer                     │  │  │
│  │  │     └─ LLM summarization of old messages        │  │  │
│  │  │                                                 │  │  │
│  │  │  3. FactExtractionMemoryBlock                   │  │  │
│  │  │     └─ Persistent facts about user/project      │  │  │
│  │  │                                                 │  │  │
│  │  │  4. VectorMemoryBlock                           │  │  │
│  │  │     └─ Semantic search over history             │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                       │  │
│  │  Persistence: PostgreSQL ChatStore + PGVectorStore    │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Backend Services                         │  │
│  │  ┌───────────┐  ┌───────────┐  ┌──────────────────┐  │  │
│  │  │ PostgreSQL│  │   Ollama  │  │  Tool Retriever  │  │  │
│  │  │ (chat +   │  │ (LLM +    │  │  (on-demand      │  │  │
│  │  │  vectors) │  │  embed)   │  │   loading)       │  │  │
│  │  └───────────┘  └───────────┘  └──────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TORVALDS_MEMORY_TOKEN_LIMIT` | 4000 | Max tokens in FIFO queue |
| `TORVALDS_MEMORY_PRESSURE_SIZE` | 10 | Messages to eject on overflow |
| `TORVALDS_MEMORY_SUMMARY_TOKEN_LIMIT` | 500 | Max tokens for summaries |
| `TORVALDS_MEMORY_MAX_FACTS` | 100 | Max extracted facts |
| `TORVALDS_MEMORY_VECTOR_TOP_K` | 5 | Top-k vector retrieval |
| `TORVALDS_MEMORY_EMBED_DIM` | 768 | Embedding vector dimensions |

### Memory Block Ordering

The order of memory blocks matters — they are processed sequentially:

1. **StaticMemoryBlock** — Inject system context first (highest priority)
2. **ChatSummaryMemoryBuffer** — Summarized history for recent context
3. **FactExtractionMemoryBlock** — Learned facts about user/project
4. **VectorMemoryBlock** — Semantic retrieval for relevant historical messages

---

## Benefits

| Benefit | Description |
|---------|-------------|
| **Context Retention** | Summarization preserves key info beyond token limits |
| **Persistent Knowledge** | Facts extracted and stored across sessions |
| **Semantic Search** | Retrieve relevant historical messages by meaning |
| **Modular Architecture** | Easy to add/remove/replace memory blocks |
| **Composable** | Different memory configurations per use case |
| **PostgreSQL Backed** | All memory persisted to database |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM summarization latency | Use fast local LLM (Ollama) or cache summaries |
| Vector store performance | Index PostgreSQL vectors, limit retrieval to top-k |
| Fact extraction accuracy | Limit max facts, review/curate periodically |
| Token budget management | Monitor and tune token_limit/pressure_size |
| Memory block order impact | Test different orderings for optimal context |

---

## Prerequisites

- LlamaIndex >= 0.14.24 (installed: ✅)
- PostgreSQL with pgvector extension (installed: ✅)
- Ollama running with embedding model (installed: ✅)
- Existing `agent_chat_memory.py` module (exists: ✅)

---

## Next Steps

1. **Review** this proposal with stakeholders
2. **Implement Phase 1** — Migrate to `Memory` class
3. **Test** PostgreSQL persistence with new architecture
4. **Iterate** through Phases 2-5 based on testing results
5. **Monitor** performance and context quality metrics

---

*Proposal created: $(date +%Y-%m-%d)*  
*Author: Torvalds Agent*  
*Status: DRAFT — No implementation yet*
