# Components (Helper Modules)

> **Note:** This folder contains **helper components and utility modules**, NOT the agent's callable tools.
>
> - **Agent Tools** = The MCP functions the agent can invoke (e.g. `read_file`, `run_shell_command`, `git_commit`, `run_postgres_query`, etc.)
> - **Components** = Internal helper modules that support the agent's infrastructure (e.g. password prompters, spinner controllers, cache handlers, UI utilities, etc.)

## Purpose

Reusable helper modules and internal components extracted from investigations and feature work. These are supporting utilities used **by** the agent, not tools called **by** users.

Each component is a self-contained module that can be imported and used independently.

## Available Components

### `whiptail_password.py`
Terminal-based password prompter using whiptail dialogs.

**Purpose:** Provides an alternative to stdin/console password input in terminal environments where whiptail is available.

**Usage:**
```python
from components.whiptail_password import WhiptailPasswordPrompter

prompter = WhiptailPasswordPrompter()
result = prompter.prompt_password(max_attempts=3)
```

**Prerequisites:**
- `/usr/bin/whiptail` installed (newt package on Debian/Ubuntu)
- `whiptail` Python package (`pip install whiptail`)

---

### `spinner_controller.py`
Console spinner controller for progress indication.

**Purpose:** Provides a thread-safe spinner for displaying progress during long-running operations.

**Features:**
- Thread-safe spinner with pause/resume functionality
- Integration with rich console for styled output
- Callback hooks for lifecycle events

---

### `state_handler.py`
State management handler for tracking operational state.

**Purpose:** Manages the state of ongoing operations and provides state tracking capabilities.

**Features:**
- Tracks operational state across tool invocations
- Supports state serialization and restoration
- Thread-safe state updates

---

### `stats_handler.py`
Statistics handler component (refactored from `agent_stats_handler.py`).

**Purpose:** Handles per-request statistics collection, tracking, and rendering using LlamaIndex callbacks.

**Features:**
- Token usage tracking (prompt/completion)
- Tool invocation timing
- Error tracking
- Rich console rendering with configurable formats
- Persistent stats history in cache

**Usage:**
```python
from components.stats_handler import RequestStatsHandler, StatsRenderer

# Stats are automatically collected and rendered after each request
# Use --no-stats CLI flag to disable
# Use \stats command to view historical statistics summary
```

**Note:** This was moved from `agent_stats_handler.py` in the root directory (PR #5) to better organize infrastructure code. Comprehensive debug logging was added throughout.

---

### `event_consumer.py`
Real-time event streaming and consumer.

**Purpose:** Handles real-time event streaming with state management.

**Features:**
- Thread-safe event processing
- State management for streaming operations
- Integration with spinner for progress indication
- Supports event filtering and routing

---

### `__init__.py`
Package initialization file.

**Purpose:** Makes the components directory a proper Python package.

---

## Adding New Components

1. Create a new `.py` file in this directory
2. Add comprehensive docstrings with usage examples
3. Include a `__main__` block for standalone testing
4. Add tests in `tests/` if applicable
5. Update this README.md to document the new component

## Recent Updates

- **PR #5**: Moved `agent_stats_handler.py` to `components/stats_handler.py` for better organization
- **September 2026**: Added comprehensive debug logging throughout all components
- **September 2026**: Extracted SpinnerController components and enhanced with whiptail support
