# Current Architecture Analysis for Project Manager Feature

## Date: 2025-01-25
## Author: Torvalds AI Agent

---

## 1. Current Project Structure Overview

### Main Agent Entry Point
- **File:** `agent-torvalds.py`
- **Role:** Central orchestrator using LlamaIndex's `FunctionAgent` workflow
- **Key Features:**
  - Supports both full tool loading and on-demand semantic retrieval via `ObjectIndex`
  - Real-time event streaming with spinner pause/resume during interactive operations
  - Human-in-the-Loop (HITL) with runtime toggle support
  - State tracking, stats handlers, and graceful signal handling

### Toolkit Architecture
Each toolkit is a standalone Python module exporting `get_all_tools()`:

| Toolkit | File | Category | Purpose |
|---------|------|----------|---------|
| OS Toolkit | `agent_os_toolkit.py` | File/OS | pwd, ls, mkdir, rm, cp, mv, read/write files |
| Git Toolkit | `agent_git_toolkit.py` | Version Control | Git operations, GitHub API integration |
| Linux Toolkit | `agent_linux_toolkit.py` | System | Linux-specific system commands |
| Windows Toolkit | `agent_windows_toolkit.py` | System | Windows/PowerShell commands |
| DB Toolkit | `agent_db_toolkit.py` | Database | SQL queries across multiple DB engines |
| Math Toolkit | `agent_math_toolkit.py` | Computation | Math/stats calculations |
| GitHub Toolkit | `agent_github_toolkit.py` | Version Control | GitHub REST API operations |
| APT Toolkit | `agent_apt_toolkit.py` | Package Mgmt | Linux package installation |
| Cache System | `agent_cache_system.py` | Infrastructure | Session caching and stats |
| XLSX Toolkit | `agent_xlsx_toolkit.py` | Data | Excel file operations |
| Data Analysis | `agent_data_analysis_toolkit.py` | Data | Pandas/NumPy analysis |

### Tool Retriever System
- **File:** `agent_tool_retriever.py`
- **Mechanism:** Uses `ObjectIndex.from_objects()` with `VectorStoreIndex` for semantic retrieval
- **Embedding Model:** Ollama `nomic-embed-text`
- **Retrieval:** `similarity_top_k` controls how many tools are returned per query

### Components (Reusable Infrastructure)
Located in `components/`:
- `spinner_controller.py` - Console spinner management
- `state_handler.py` - Agent state tracking
- `event_consumer.py` - Real-time event streaming
- `human_loop_handler.py` - HITL orchestration
- `timeout_manager.py` - Timeout handling for prompts
- `hitl_runtime_toggle.py` - Runtime enable/disable HITL
- `console_input_module.py` - Console-based user input
- `whiptail_input_module.py` - Whiptail dialog input (Linux)

---

## 2. What Needs to Be Built: Project Manager Feature

### Gap Analysis

| Requirement | Current State | Gap |
|-------------|---------------|-----|
| Project type detection | NOT IMPLEMENTED | Need scanner for project indicators |
| `.agentworkspace.json` persistence | NOT IMPLEMENTED | Need config file reader/writer |
| Auto Git initialization | NOT IMPLEMENTED | Need git init workflow |
| Tool injection per project type | NOT IMPLEMENTED | Need dynamic tool mapping |
| Human-in-the-Loop for ambiguity | EXISTS | Need integration with project detection |
| Workspace multi-project support | NOT IMPLEMENTED | Need workspace scanning logic |

### Proposed New Modules

1. **`agent_project_manager.py`** - Core project manager toolkit
   - `scan_project_type(path)` - Detect project type from indicators
   - `detect_workspace(path)` - Scan for multiple projects
   - `get_project_config(path)` - Load/save `.agentworkspace.json`
   - `init_git_if_needed(path)` - Auto-initialize Git repos
   - `resolve_ambiguity(path, candidates)` - HITL for ambiguous detection
   - `get_tools_for_project(project_type)` - Map project type to tools

2. **`project_scanner.py`** - Project type detection engine
   - File signature database (indicators per project type)
   - Scoring algorithm for confidence
   - Confidence thresholds and fallback logic

3. **`workspace_config.py`** - Configuration persistence
   - `.agentworkspace.json` reader/writer
   - Schema validation
   - Migration support for config format changes

---

## 3. Integration Points

### With Existing Agent
```
agent-torvalds.py
  | agent_tool_retriever.py
  |   | [existing toolkits]
  |   | agent_project_manager.py  <-- NEW
  | components/
  |   | human_loop_handler.py     <-- reuse for ambiguity
  |   | console_input_module.py   <-- reuse for prompts
  | SYSTEM_PROMPT                 <-- extend with project awareness
```

### With HITL System
The existing HITL infrastructure can be reused for ambiguity resolution:
- `HumanLoopHandler` for prompting user
- `TimeoutManager` for timeout handling
- `ConsoleInputModule` / `WhiptailInputModule` for input method

### With Git Toolkit
The existing `agent_git_toolkit.py` provides git operations. The project manager needs to:
- Check if `.git/` exists via `check_path_exists()`
- Call git init/commit via `execute_shell_command()` or existing git toolkit

---

## 4. Implementation Strategy

### Phase 1: Core Detection Engine
- Build `project_scanner.py` with indicator database
- Implement confidence scoring
- Handle ambiguous cases

### Phase 2: Configuration Persistence
- Build `workspace_config.py`
- Implement `.agentworkspace.json` schema
- Add read/write/update operations

### Phase 3: Project Manager Toolkit
- Build `agent_project_manager.py`
- Integrate scanner and config
- Add Git auto-initialization

### Phase 4: Agent Integration
- Register project manager tools with retriever
- Extend system prompt with project awareness
- Integrate HITL for ambiguity

### Phase 5: Testing & Validation
- Unit tests for scanner
- Integration tests with real projects
- End-to-end workflow tests

---

## 5. Dependencies & Risks

### Dependencies
- No new external packages required
- Reuses existing LlamaIndex infrastructure
- Reuses existing HITL components

### Risks
- **False positives in detection:** Mitigated by confidence thresholds and HITL fallback
- **Performance impact:** Scanning large directories could be slow; need depth limits
- **Multi-project complexity:** Workspace detection needs careful boundary analysis

---

## 6. Success Criteria

1. Agent can detect project type with >90% accuracy on standard projects
2. `.agentworkspace.json` is created/updated automatically
3. Git repos are initialized when missing
4. Ambiguous cases trigger HITL prompt
5. System prompt includes project context for LLM awareness