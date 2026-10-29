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

### `ollama_config.py`
Resolution of the Ollama endpoint used by the chat and the embedding model.

**Purpose:** Provides a single source of truth for the address of the local
Ollama server, so the chat model and the embedding model can never drift
apart.

**Features:**
- Reads `TORVALDS_OLLAMA_HOST`, then `OLLAMA_HOST`, then falls back to
  `http://localhost:11434`
- Normalises a bare `host:port` into a full URL with the `http://` scheme
  (the Ollama *server* accepts `OLLAMA_HOST=0.0.0.0:11434`, the HTTP client
  needs a URL)

**Usage:**
```python
from components.ollama_config import get_ollama_base_url

base_url = get_ollama_base_url()   # e.g. 'http://localhost:11434'
```

---

### `file_logging.py`
The rotating log file and the symlink to the current one.

**Purpose:** Lets the agent write its log into a file, rotated at a
predefined size, with a symlink to the current log file next to the
rotated generations.

**Features:**
- `RotatingFileHandler` from the **standard library** — the subclass adds
  the symlink and the file mode (`0600`); a plain `FileHandler` would
  never rotate, and the file would grow until the disk was full
- The symlink points at the **path** of the live log file, not at its
  inode, so it survives every rotation untouched
- The size is written the way an operator writes it — `10MB`, `512K`,
  `1G` — and an unknown unit is reported rather than ignored
- The file logging is **off by default**, and it is a **tee**: the
  stderr handler stays
- A missing feature **degrades**: a directory that cannot be created, a
  file that cannot be opened and a symlink that cannot be created each
  warn and let the agent boot

**Usage:**
```python
from components.file_logging import (
    add_logging_arguments,   # the five flags of the command line
    build_file_handler,      # the handler, or None when it degrades
    resolve_config,          # the flags and the environment -> a config
)

# in parse_args():
add_logging_arguments(parser)

# in main(), after the arguments are parsed:
config = resolve_config(log_file=args.log_file, log_dir=args.log_dir)
handler = build_file_handler(config, logging.INFO)
```

See [`docs/logging.md`](../docs/logging.md) for the full documentation.

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

- **2026-10-29**: Added `file_logging.py` — the rotating log file, the size parser and the symlink
- **PR #5**: Moved `agent_stats_handler.py` to `components/stats_handler.py` for better organization
- **September 2026**: Added comprehensive debug logging throughout all components
- **September 2026**: Extracted SpinnerController components and enhanced with whiptail support
