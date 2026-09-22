# Components (Helper Modules)

> **Note:** This folder contains **helper components and utility modules**, NOT the agent's callable tools.
>
> - **Agent Tools** = The MCP functions the agent can invoke (e.g. `read_file`, `run_shell_command`, `git_commit`, `run_postgres_query`, etc.)
> - **Components** = Internal helper modules that support the agent's infrastructure (e.g. password prompters, cache handlers, UI utilities, etc.)

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

## Adding New Components

1. Create a new `.py` file in this directory
2. Add comprehensive docstrings with usage examples
3. Include a `__main__` block for standalone testing
4. Add tests in `investigate/<feature>/` if applicable
