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
- Callback hooks for lifecycle events — `on_start`, `on_stop`, `on_pause`, `on_resume`
- The single spinner feature of the project; it absorbed `spinner_manager.py`, which was
  never imported by anything. The investigation is in `investigate/spinner-consolidation/`.

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

### `config.py`
The configuration file — `~/.config/torvalds/config.toml`.

**Purpose:** Gives the agent one place to keep its settings, instead of
forty-five environment variables spread over a shell profile.

**Features:**
- The **XDG** location — `$XDG_CONFIG_HOME`, or `~/.config` — and
  `TORVALDS_CONFIG` for a file that is somewhere else
- The precedence chain: **flag > environment variable > config file >
  default**.  The file sits *below* the variables on purpose, so an
  operator who already has variables sees no change when they upgrade
- **Every setting reports its source**, so "why is my model X?" has an
  answer
- A broken file is a **warning**, never a failed boot; a typo is
  **reported**, never silently ignored
- TOML, read by `tomllib` from the standard library — no dependency, and
  a syntax error is a hard error with a line number

**Usage:**
```python
from components.config import config

MODEL = config.get("llm.model")
config.source("llm.model")   # "environment variable TORVALDS_MODEL"
```

---

### `config_view.py`
The `\config` command — the effective configuration, rendered.

**Purpose:** Shows every setting the agent resolved, the value that won
and the layer it came from.  The multi-window TUI renders it into the
document pane; the classic REPL prints it as a table.

**Usage:**
```python
from components.config_view import render_effective, render_effective_markdown

render_effective(config, console)          # the classic REPL
render_effective_markdown(config)          # the TUI
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

### `context_metrics.py`
The size of the prompt that goes to the model — in tokens and in bytes.

**Purpose:** Measures the prompt that is sent to the model and renders it
the way the operator reads a size.

**What "the context" is:** the prompt is **chat messages** — the chat
memory (the system prompt, the history of the session, the request of the
user) plus the scratchpad of the run (the assistant turns that asked for a
tool, and the tool results that answered them).  The tool schemas travel
with every request too, and they are counted **separately**, because they
are not messages.

**Features:**
- The tokens are counted with the tokenizer the chat memory itself uses,
  so the number is the number the token limit is enforced with
- The bytes are the UTF-8 bytes of the text of the prompt
- The tool schemas are measured on their own, so it is visible where the
  prompt goes
- A tokenizer that cannot be loaded **degrades**: the tokens are then
  estimated and the log line says so — the bytes are always exact

**Usage:**
```python
from components.context_metrics import describe_context, measure_context

size = measure_context(messages, tools=agent.tools)
print(describe_context(size, window=8192))
# 12 messages, 1,200 tokens, 4.5 KB, 14.6% of the 8,192-token window
```

The agent writes the line itself, before every request to the model:

```
Context: 12 messages, 1,200 tokens, 4.5 KB, 14.6% of the 8,192-token window
```

---

### `skills.py`
The procedures the agent loads on demand — the library half.

**Purpose:** Reads the skills of the operator and of the project, and turns
them into the catalog and the body the agent hands to the model.

**Features:**
- A skill is a directory with a `SKILL.md` in it: a frontmatter block
  (`name`, `description`) and the procedure in the body
- Two roots: `~/.config/torvalds/skills` and `<project>/skills` — the skill
  of the project overrides the skill of the operator with the same name
- The catalog is **one line per skill** — the XML shape of the
  specification costs ten tokens per skill in tags alone
- The body is cut to a token limit, and the cut is marked.  The limit
  applies to the **result**: the count of the result is not the sum of the
  counts of its parts, so the body is cut until the whole thing fits
- Nothing here imports LlamaIndex, so the module stays cheap to import

**Usage:**
```python
from components.skills import discover_skills, render_prompt_section

skills = discover_skills(default_skill_roots())
print(render_prompt_section(skills))
# ### Skills
#
# Procedures for tasks that need one are available on this machine. ...
```

---

### `skills_tools.py`
The two tools that load a skill — the agent-facing half.

**Purpose:** Turns the skills into `list_skills` and `activate_skill`, the
tools the model calls.

**Features:**
- The **catalog is a tool result**, not prompt text: it costs the runs
  that ask for it, and the context guard drops it once it grows old
- The name of the skill is a **free string**, not an enum — an enum is paid
  on every request and grows with every skill
- A machine **without skills gets no tools at all**: the feature costs
  nothing when it is not used
- The body that comes back is cut to `skills.body_token_limit` tokens

**Usage:**
```python
from components.skills_tools import build_skills

tools, section, skills = build_skills(dirs="~/.config/torvalds/skills")
```

The cost of the feature is 220 tokens on every request, whatever the number
of skills — see
[`investigate/agent-skills/`](../investigate/agent-skills/INVESTIGATION_REPORT.md).

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

- **2026-11-04**: Added `context_metrics.py` — the size of the prompt (tokens, bytes) that is logged with every request to the model
- **2026-10-29**: Added `config.py` and `config_view.py` — the configuration file and the `\config` command
- **2026-10-29**: Added `file_logging.py` — the rotating log file, the size parser and the symlink
- **PR #5**: Moved `agent_stats_handler.py` to `components/stats_handler.py` for better organization
- **September 2026**: Added comprehensive debug logging throughout all components
- **September 2026**: Extracted SpinnerController components and enhanced with whiptail support
