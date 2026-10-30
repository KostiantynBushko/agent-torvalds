# Investigation: How Agent Torvalds Can Learn from Interaction

**Date:** 2026-10-29
**Status:** Investigation — no source files modified
**Branch:** N/A (investigation only)

---

## Executive Summary

Agent Torvalds has **three independent persistence layers** that collect data from operator interactions, but **none of them feed back into the agent's behaviour**. The agent is effectively amnesiac: it records what happened, but nothing it records changes how it acts next time.

This investigation maps the current state, identifies the gaps, and proposes a learning architecture that turns the collected data into something the agent actually uses.

---

## 1. Current Persistence Architecture

### 1.1 The Three Layers

| Layer | Storage | Location | What it holds | Who reads it |
|-------|---------|----------|---------------|--------------|
| **Chat History** | PostgreSQL (SQLite fallback) | `~/.torvalds/chat_manager.db` / remote PG | Conversational messages per session | LlamaIndex `ChatMemoryBuffer` — fed into the prompt on every turn |
| **Agent Cache** | JSON file | `~/.cache/torvalds/agent_cache.json` | Sessions, context, learnings, state, error log, request stats | Only the cache's own tools (`save_to_cache`, `load_from_cache`) |
| **State Handler** | In-memory | Process memory | Tool call history, errors, workflow state | EventConsumer during the current run only |

### 1.2 Chat History (`chat_manager/`)

**What it does:**
- Multi-user, multi-session conversation storage
- PostgreSQL primary with SQLite local fallback (degradation)
- LlamaIndex `ChatMemoryBuffer` backed by `PostgresChatStoreBackend`
- Token-limited: `chat_token_limit` (default 5000) controls how many tokens of history are kept
- Sessions are isolated: "General Chat", "Project Chat", custom sessions

**What it does NOT do:**
- Cross-session learning: each session starts with its own isolated history
- Summarisation: when the token limit is reached, old messages are dropped (not summarised)
- Pattern extraction: no analysis of what the operator asked, what tools were used, what succeeded
- Preference inference: the agent never learns "this operator prefers X over Y"

**Key finding:** The chat history is a **conversation log**, not a learning mechanism. It preserves *what was said*, not *what was learned*.

### 1.3 Agent Cache (`agent_cache_system.py`)

**Structure:**
```json
{
  "sessions": [...],           // Session start/end timestamps, command counts
  "context": {                 // Operational context
    "current_directory": "",
    "active_databases": [],
    "running_processes": [],
    "git_repos": {}
  },
  "learnings": {               // The learning section — mostly empty
    "user_preferences": {},
    "frequent_commands": [],
    "common_patterns": {}
  },
  "state": {                   // Ephemeral state
    "file_watches": {},
    "network_connections": {},
    "temp_files": []
  },
  "error_log": [],             // Error history (max 100)
  "request_stats": []          // Per-request stats (max 500)
}
```

**What is actually written:**
| Function | Called from | Frequency |
|----------|-------------|-----------|
| `record_frequent_command()` | Exposed as tool, but **never called by hooks** | Manual only |
| `log_error()` | Exposed as tool, but **never called by hooks** | Manual only |
| `save_request_stats()` | `agent-torvalds.py` stats rendering | Every request |
| `update_context_current_dir()` | Exposed as tool | Manual only |
| `add_git_repo()` | Exposed as tool | Manual only |
| `add_active_database()` | Exposed as tool | Manual only |

**Critical finding:** The `learnings` section exists but is **never populated automatically**. The functions `record_frequent_command()` and `log_error()` are exposed as tools the agent *could* call, but nothing in the agent's architecture triggers them. The agent would have to *decide* to learn, and it has no incentive to do so.

**What is actually accumulated:**
- `request_stats`: Every request's duration, token counts, tool calls, errors — **500 entries**
- `error_log`: Only if the agent manually calls `log_error()` — **effectively empty**
- `sessions`: Start/end timestamps — **grows but unused**

### 1.4 State Handler (`components/state_handler.py`)

**What it does:**
- Tracks tool calls, errors, and interactive prompts **during a single workflow run**
- Provides snapshots and summaries

**What it does NOT do:**
- Persist anything across runs
- Feed data back into the system prompt
- Accumulate knowledge

**Finding:** Purely ephemeral. Useful for debugging a single run, useless for learning.

### 1.5 Stats Handler (`components/stats_handler.py`)

**What it does:**
- Per-request token counting, tool timing, error tracking
- Rich console rendering after each response
- Persistence to cache via `save_request_stats()`

**What it does NOT do:**
- Analyse trends (e.g., "the operator uses `execute_shell_command` 80% of the time")
- Adapt behaviour based on patterns
- Feed statistics into the system prompt

**Finding:** Excellent observability, zero feedback.

---

## 2. The Learning Gap

### 2.1 What "Learning" Would Mean

Learning from interaction means the agent changes its behaviour based on past interactions. There are several levels:

| Level | What changes | Example |
|-------|-------------|---------|
| **L0: Memory** | The agent remembers what was said | "Last time you asked about the deploy script" |
| **L1: Preference** | The agent adapts to the operator's style | "You prefer TOML over YAML, so I'll suggest TOML" |
| **L2: Pattern** | The agent recognises recurring situations | "You always check disk space before deploying" |
| **L3: Strategy** | The agent improves its approach | "Last time `apt-get` failed, `apt update` first fixed it" |
| **L4: Meta-learning** | The agent learns what it doesn't know | "I'm bad at parsing MikroTik output, I should ask for clarification" |

### 2.2 Current State: L0 Only, and Partially

The agent has **partial L0**:
- Chat history remembers the conversation within a session
- But sessions are isolated — no cross-session memory
- And the token limit means old messages are dropped, not remembered

**L1–L4 do not exist.** Nothing in the architecture extracts preferences, patterns, strategies, or meta-knowledge from interactions.

### 2.3 The Missing Feedback Loop

```
┌─────────────────────────────────────────────────────┐
│                  CURRENT STATE                       │
│                                                      │
│  Operator ──query──► Agent ──tools──► Result        │
│                     │                              │
│                     ▼                              │
│              Chat History (L0)                      │
│              Cache (raw stats)                      │
│              State (ephemeral)                      │
│                                                      │
│  ◄── NOTHING FLOWS BACK ──►                         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                  DESIRED STATE                       │
│                                                      │
│  Operator ──query──► Agent ──tools──► Result        │
│                     │           │                    │
│                     ▼           ▼                    │
│              Chat History   Learning Engine          │
│              Cache (enriched) ◄──── extract()        │
│                     │           │                    │
│                     ▼           ▼                    │
│              System Prompt ◄── inject learnings      │
│                                                      │
│  ◄── CLOSED LOOP ──►                                │
└─────────────────────────────────────────────────────┘
```

---

## 3. Data Sources Available for Learning

### 3.1 Rich Data Already Collected

The agent already collects more data than most AI assistants:

| Source | Data Available | Volume |
|--------|---------------|--------|
| **Chat History** | Every user query, every agent response, every tool call within the conversation | Bounded by `chat_token_limit` per session |
| **Request Stats** | Duration, token counts, tools used, tool call count, error count, request ID | 500 entries in cache |
| **Error Log** | Error messages with timestamps | Up to 100 entries (but empty in practice) |
| **HITL Questions** | Every question asked, how the operator answered, whether it timed out | In `human_loop_handler` history |
| **Tool Call History** | Every tool invoked, its arguments, its result, whether it errored | In `state_handler` (ephemeral) and stats |
| **Session Metadata** | When sessions start/end, how many commands per session | In cache `sessions` array |

### 3.2 What Can Be Extracted

From this data, the following learnings are computable:

| Learning | Source | Method |
|----------|--------|--------|
| **Frequent commands/tools** | Request stats | Count tool names across requests |
| **Error-prone tools** | Request stats + error log | Correlate tool names with errors |
| **Operator's tool preferences** | Request stats | Which tools the operator asks for most |
| **Recurring query patterns** | Chat history | Semantic similarity of user queries over time |
| **HITL answer patterns** | HITL history | Does the operator say "yes" or "no" to certain types of questions? |
| **Time-of-day patterns** | Request stats timestamps | When does the operator work? What do they do at different times? |
| **Project context** | Chat history + git repos | What repositories are active, what work is being done |
| **Success patterns** | Tool call results | Which tool sequences lead to success vs. error |

---

## 4. Proposed Learning Architecture

### 4.1 Design Principles

1. **Learning is passive.** The operator should not have to configure learning. It happens automatically from the data that is already collected.
2. **Learnings are injected into the system prompt.** The only way the agent "uses" learnings is by reading them at startup. No runtime API calls to a learning service.
3. **Learnings are bounded.** The system prompt has a finite context window. Learnings must be concise — a few lines, not megabytes of raw data.
4. **Learnings are persistent.** They survive across sessions, across restarts, across days.
5. **Learnings are inspectable.** The operator can see what the agent has learned, edit it, or clear it.
6. **No new storage.** Use the existing cache (`~/.cache/torvalds/agent_cache.json`). No new database, no new file.

### 4.2 The Learning Pipeline

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Interaction  │    │   Extract    │    │   Store      │    │   Inject     │
│  (every turn) │───►│  (post-turn) │───►│  (in cache)  │───►│  (at startup)│
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
      │                    │                    │                    │
      ▼                    ▼                    ▼                    ▼
  User query        Analyse:            Update learnings    Read learnings
  Tool calls            what tools        in cache            into system
  Results               succeeded?        (JSON)              prompt
  Errors                what failed?
  HITL answers          what did the
                        operator choose?
```

### 4.3 Component: `components/learning_engine.py`

A new module that sits between the cache and the system prompt:

```python
# Pseudocode — not implementation

class LearningEngine:
    """Extracts learnings from interactions and injects them into the prompt."""

    def __init__(self, cache_path: Path):
        self.cache = load_cache(cache_path)

    # Called after every agent turn
    def record_turn(self, turn: TurnRecord) -> None:
        """Analyse a completed turn and update learnings."""
        self._update_tool_usage(turn.tools_used)
        self._update_error_patterns(turn.errors)
        self._update_query_patterns(turn.user_query)
        self._update_hitl_patterns(turn.hitl_questions)
        self._trim()  # Keep learnings bounded
        self._persist()

    # Called at agent startup
    def get_prompt_injection(self) -> str:
        """Return a concise block of learnings for the system prompt."""
        learnings = self.cache["learnings"]
        lines = []

        # Top tools — what the operator uses most
        top_tools = self._top_tools(learnings["tool_usage"], n=5)
        if top_tools:
            lines.append(f"Most used tools: {', '.join(top_tools)}")

        # Error patterns — what tends to fail
        error_patterns = self._error_summary(learnings["error_patterns"])
        if error_patterns:
            lines.append(f"Known issues: {error_patterns}")

        # Operator preferences — inferred from HITL answers
        preferences = self._preference_summary(learnings["user_preferences"])
        if preferences:
            lines.append(f"Operator preferences: {preferences}")

        # Recurring patterns
        patterns = self._pattern_summary(learnings["common_patterns"])
        if patterns:
            lines.append(f"Recurring patterns: {patterns}")

        return "\n".join(lines) if lines else ""
```

### 4.4 Where It Hooks In

| Hook Point | Location | What Happens |
|------------|----------|--------------|
| **Post-turn extraction** | `agent-torvalds.py` after `consumer.consume_events()` returns | `learning_engine.record_turn(...)` is called with the turn's stats, tool calls, and errors |
| **Startup injection** | `agent-torvalds.py` when building the system prompt | `learning_engine.get_prompt_injection()` is appended to the system prompt |
| **HITL recording** | `EventConsumer._on_agent_answer()` | HITL question/answer pairs are forwarded to the learning engine |
| **Error recording** | `EventConsumer._on_tool_call_result()` when `is_error=True` | Errors are forwarded to the learning engine |

### 4.5 Cache Schema Extension

The existing `learnings` section would be enriched:

```json
{
  "learnings": {
    "user_preferences": {
      "preferred_format": "toml",        // Inferred from choices
      "preferred_editor": "vim",         // Inferred from tool usage
      "hitl_yes_rate": 0.85             // 85% yes on HITL questions
    },
    "tool_usage": {
      "execute_shell_command": {"count": 342, "last_used": "...", "success_rate": 0.97},
      "read_file": {"count": 156, "last_used": "...", "success_rate": 1.0},
      "pwd": {"count": 89, "last_used": "...", "success_rate": 1.0}
    },
    "error_patterns": {
      "install_package": {
        "count": 12,
        "common_fix": "apt update first",
        "first_seen": "...",
        "last_seen": "..."
      }
    },
    "common_patterns": {
      "pre-deploy-checks": {
        "description": "Operator checks disk space and git status before deploying",
        "frequency": 15,
        "tools": ["execute_shell_command", "git_status"]
      }
    },
    "query_patterns": {
      "top_queries": [
        {"pattern": "check disk space", "count": 23, "tools_used": ["execute_shell_command"]},
        {"pattern": "git operations", "count": 18, "tools_used": ["git_status", "git_diff"]}
      ]
    }
  }
}
```

### 4.6 System Prompt Injection

The learnings would be injected as a section at the end of the system prompt:

```
## Operator Context (learned from past interactions)

Most used tools: execute_shell_command, read_file, pwd, git_status, ls
Known issues: install_package often fails without apt update first
Operator preferences: prefers TOML for config, high yes-rate on HITL (85%)
Recurring patterns: checks disk space and git status before deploying
```

This is **~100-200 tokens** — a small fraction of the context window, but enough to make the agent contextually aware.

---

## 5. What Would NOT Be Built (and Why)

### 5.1 No Vector Database for Learnings

The project already uses Ollama embeddings for tool retrieval. Adding a second vector store for learnings would be over-engineering. The learnings are structured (counts, rates, summaries) and fit in a JSON file.

### 5.2 No Fine-tuning

Fine-tuning the model on the operator's interactions is not feasible:
- It requires GPU resources the project does not assume
- It changes the model, not the prompt — making it non-reproducible
- The operator's interactions are too few and too domain-specific

### 5.3 No Cross-Session Chat History Merging

Merging all sessions into one giant history would:
- Exceed the context window immediately
- Mix unrelated conversations (debugging a script vs. writing documentation)
- Lose the session isolation that the operator explicitly manages

### 5.4 No Real-Time Learning API

The learning engine is not a service. It is a module that reads and writes JSON. No HTTP server, no gRPC, no message queue. The agent is a single process; the learning engine is a function call.

---

## 6. Implementation Plan

### Phase 1: Passive Collection (Low Risk)

**Goal:** Start collecting data that is already available but not being captured.

| Task | File | Risk |
|------|------|------|
| Hook `record_frequent_command()` into tool call results | `event_consumer.py` | Low — just counting |
| Hook `log_error()` into error detection | `event_consumer.py` | Low — just logging |
| Populate `tool_usage` from request stats | `learning_engine.py` (new) | Low — read-only analysis |

**Deliverable:** The cache starts accumulating tool usage counts and error logs automatically. Nothing changes in the agent's behaviour yet.

### Phase 2: Prompt Injection (Medium Risk)

**Goal:** Feed accumulated learnings into the system prompt.

| Task | File | Risk |
|------|------|------|
| Build `get_prompt_injection()` | `learning_engine.py` | Medium — changes what the model sees |
| Wire into system prompt construction | `agent-torvalds.py`, `agent-torvalds-mw.py` | Medium — prompt change |
| Add `\learnings` command for inspection | `components/command_registry.py` | Low — read-only |

**Deliverable:** The agent starts receiving learnings in its system prompt. The operator can inspect them with `\learnings`.

### Phase 3: Pattern Recognition (Higher Risk)

**Goal:** Extract higher-level patterns from accumulated data.

| Task | File | Risk |
|------|------|------|
| Query pattern clustering | `learning_engine.py` | Higher — semantic analysis |
| HITL preference inference | `learning_engine.py` | Higher — behavioural inference |
| Error pattern correlation | `learning_engine.py` | Higher — causal inference |

**Deliverable:** The agent learns preferences, recurring patterns, and error correlations.

### Phase 4: Active Adaptation (Highest Risk)

**Goal:** The agent uses learnings to change its behaviour, not just its knowledge.

| Task | File | Risk |
|------|------|------|
| Tool selection bias based on success rates | `agent_tool_retriever.py` | High — changes retrieval |
| Pre-emptive actions based on patterns | `hitl_agent.py` | High — changes agent logic |
| Self-correction based on error history | `learning_engine.py` | High — autonomous behaviour |

**Deliverable:** The agent proactively adapts based on what it has learned.

---

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Learnings are wrong** | Agent acts on incorrect assumptions | Learnings are inspectable (`\learnings`); operator can edit or clear |
| **Prompt bloat** | Learnings consume context window | Hard cap: learnings section is max 200 tokens; oldest entries are trimmed |
| **Privacy** | Learnings contain operator behaviour data | Learnings stay in `~/.cache/torvalds/` — never transmitted, never committed |
| **Stale learnings** | Old patterns no longer apply | Time-decay weighting: recent interactions count more than old ones |
| **Feedback loops** | Agent reinforces its own mistakes | Error patterns are separate from tool preferences; failures reduce confidence |
| **Performance** | Learning analysis slows down the agent | Extraction is post-turn (after the response); injection is at startup (once) |

---

## 8. Open Questions for the Operator

1. **How much context should learnings take?** 100 tokens? 200? 500? The context window is 8192 tokens; the system prompt is already ~500 tokens. Learnings should not starve the conversation.

2. **Should learnings be per-user or global?** The chat manager supports multiple users. Should each user have their own learnings, or should learnings be shared?

3. **Should the operator be able to seed learnings manually?** A `\learnings add "I prefer TOML"` command would let the operator bootstrap the learning without waiting for inference.

4. **How aggressive should pattern recognition be?** Counting tool usage is safe. Inferring "the operator always does X before Y" is more risky — it could be wrong and lead the agent astray.

5. **Should learnings be versioned?** If the learning format changes, old learnings should be migrated, not lost.

---

## 9. File References

| File | Role | Lines of Interest |
|------|------|-------------------|
| `agent_cache_system.py` | Cache storage, learnings section | `_get_default_cache()` (line 42), `learnings` keys |
| `chat_manager/manager.py` | Chat history, session management | `get_memory_buffer()` — token-limited history |
| `components/state_handler.py` | Ephemeral state tracking | `add_tool_call()`, `add_error()` |
| `components/stats_handler.py` | Per-request statistics | `RequestStats`, `save_request_stats()` |
| `components/event_consumer.py` | Event routing, HITL handling | `_on_tool_call_result()`, `_on_agent_answer()` |
| `components/hitl_agent.py` | HITL question/answer round-trip | `parse_agent_output()` — where answers are fed back |
| `agent_tool_retriever.py` | Semantic tool retrieval | `build_tool_retriever()` — no learning bias |
| `agent-torvalds.py` | Main orchestrator, system prompt | System prompt construction — injection point |

---

## 10. Conclusion

Agent Torvalds collects rich interaction data but does nothing with it. The gap between data collection and learning is architectural, not technical: the data exists, the storage exists, and the injection point (the system prompt) is accessible.

The proposed learning engine is a thin layer between the cache and the prompt. It reads what is already being recorded, extracts patterns, and feeds a concise summary back into the agent's context. No new databases, no new services, no new dependencies.

The risk is low because the learnings are bounded, inspectable, and the operator retains full control. The upside is significant: an agent that knows its operator's preferences, recognises recurring situations, and avoids past mistakes is fundamentally more useful than one that starts from scratch every session.
