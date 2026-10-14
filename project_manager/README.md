# Project Manager Module

> **Project-aware workspace orchestration for the Torvalds AI Agent.**

The `project_manager` module provides automatic project type detection, workspace configuration management, action execution, tool recommendation, and dynamic prompt generation — all integrated as LlamaIndex FunctionTools for seamless agent interaction.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Components](#components)
- [Supported Project Types](#supported-project-types)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Integration with Agent](#integration-with-agent)
- [Human-in-the-Loop](#human-in-the-loop)
- [Runtime Prompt Injection](#runtime-prompt-injection)
- [Usage Examples](#usage-examples)
- [CLI Options](#cli-options)
- [Environment Variables](#environment-variables)

---

## Overview

The Project Manager module enables the Torvalds AI Agent to:

1. **Auto-detect project types** by scanning directories for indicator files (e.g., `pyproject.toml` → Python, `package.json` → Node.js, `Cargo.toml` → Rust).
2. **Persist workspace state** in `.agentworkspace.json` with project metadata, build commands, and Git status.
3. **Execute project actions** (build, test, run, clean) with timeout support and output capture.
4. **Recommend relevant tools** based on detected project type.
5. **Resolve ambiguities** via Human-in-the-Loop (HITL) when multiple project types are detected with similar confidence.
6. **Generate dynamic system prompts** based on active project context and tool recommendations.

### Key Benefits

| Benefit | Description |
|---------|-------------|
| **Unified handling** | Diverse project types (Python, Node.js, ESP32, Yocto, FPGA, etc.) managed through a single interface |
| **Automatic Git** | Every project is placed under Git version control; repos are auto-initialized if missing |
| **Workspace awareness** | Multiple projects tracked separately in a single workspace |
| **Extensible** | New project types and tools can be added via the indicator database and recommender |
| **HITL fallback** | Ambiguous detections are resolved interactively with timeout handling |
| **Dynamic Prompts** | System prompt adapts at runtime based on active project and tool recommendations |

---

## Architecture

```
project_manager/
├── __init__.py                      # Package entry point & public API
├── types.py                         # Shared types, constants, indicator database
├── scanner.py                       # ProjectScanner — type detection engine
├── config.py                        # WorkspaceConfig — persistence layer
├── manager.py                       # ProjectManager — orchestration layer
├── executor.py                      # ActionExecutor — safe command execution
├── recommender.py                   # ToolRecommender — project-aware tool suggestions
├── prompt_engine.py                 # PromptTemplateEngine — dynamic prompt generation
└── agent_project_manager_toolkit.py # LlamaIndex FunctionTools integration
```

### Data Flow

```
Directory Scan → ProjectScanner → Confidence Scores
                                      │
                              ┌───────┴───────┐
                              │  Ambiguous?   │
                              └───────┬───────┘
                            Yes       │       No
                              ┌───────┴───────┐
                              │  HITL Prompt  │
                              └───────┬───────┘
                                      │
                              ProjectManager
                                      │
                              WorkspaceConfig (.agentworkspace.json)
                                      │
                              ToolRecommender → Recommended Tools
                              ActionExecutor  → Build/Test/Run
                              PromptTemplateEngine → Dynamic System Prompt
```

---

## Components

### 1. `ProjectScanner` — Type Detection Engine

Scans directories and identifies project types based on file indicators using a confidence scoring algorithm.

| Method | Description |
|--------|-------------|
| `scan_directory(path)` | Returns `{project_type: confidence_score}` dict |
| `detect_project_type(path)` | Returns detected type or `None` if ambiguous |
| `get_candidates(path)` | Returns all candidate types sorted by confidence |
| `get_project_indicators(type)` | Returns indicator files for a given project type |
| `get_supported_types()` | Returns list of all supported project types |

**Confidence Scoring:**
- Each indicator file found adds weighted points to the corresponding project type
- Primary indicators (e.g., `pyproject.toml`) score higher than secondary ones
- Scores are normalized to 0.0–1.0 range
- Configurable `confidence_threshold` (default: 0.6) for auto-detection

### 2. `WorkspaceConfig` — Persistence Layer

Manages `.agentworkspace.json` files for storing project metadata, build commands, and Git status.

| Method | Description |
|--------|-------------|
| `add_project(name, path, type, ...)` | Add a new project entry |
| `get_project(name)` | Get project by name |
| `get_all_projects()` | Return all projects in workspace |
| `get_project_types()` | Return projects grouped by type |
| `update_project(name, **kwargs)` | Update an existing project |
| `remove_project(name)` | Remove a project entry |
| `rename_project(old, new)` | Rename a project |
| `set_actions(name, actions)` | Set build/run/test actions |
| `save()` | Persist config to disk |
| `get_config()` | Return full config dict |
| `to_json()` | Return config as JSON string |
| `clear_projects()` | Remove all projects |

**Config Schema (`.agentworkspace.json`):**
```json
{
  "version": "1.0",
  "workspace_path": "/absolute/path",
  "created_at": "2025-10-11T12:00:00",
  "updated_at": "2025-10-11T12:05:00",
  "projects": [
    {
      "name": "backend",
      "path": "api/",
      "type": "Python",
      "git_repo": true,
      "git_branch": "main",
      "indicators_found": ["pyproject.toml", "requirements.txt"],
      "confidence": 0.95,
      "actions": {
        "build": "python -m build",
        "test": "pytest",
        "run": "uvicorn main:app"
      },
      "metadata": {
        "description": "FastAPI backend service",
        "framework": "FastAPI",
        "language_version": "3.11"
      }
    }
  ]
}
```

### 3. `ProjectManager` — Orchestration Layer

Coordinates project scanning, type detection, workspace registration, and action management.

| Method | Description |
|--------|-------------|
| `scan(path)` | Scan directory and return confidence scores |
| `detect(path)` | Detect project type for a path |
| `get_candidates(path)` | Get all candidate types with scores |
| `discover_and_register(path, ...)` | Main orchestration: scan + register |
| `get_project(name)` | Get project details |
| `get_all_projects()` | Get all registered projects |
| `update_project(name, **kwargs)` | Update project metadata |
| `remove_project(name)` | Remove a project |
| `rename_project(old, new)` | Rename a project |
| `set_actions(name, actions)` | Set project actions |
| `get_actions(name)` | Get project actions |
| `get_workspace_summary()` | Get workspace summary dict |
| `print_summary()` | Print workspace summary to console |

### 4. `ActionExecutor` — Safe Command Execution

Executes configured project actions with timeout support, output capture, and error handling.

| Method | Description |
|--------|-------------|
| `execute(project, action, command, ...)` | Execute an action with timeout |
| `dry_run(project, action, command, ...)` | Dry-run an action without execution |

Returns `ActionResult` dataclass with: `action_name`, `project_name`, `command`, `success`, `return_code`, `stdout`, `stderr`, `duration_ms`, `timed_out`.

### 5. `ToolRecommender` — Project-Aware Tool Suggestions

Analyzes detected project type and recommends the most relevant tools from the available toolkit.

| Method | Description |
|--------|-------------|
| `recommend_for_type(type)` | Get recommendations for a project type |
| `recommend_for_project(project)` | Get recommendations for a specific project |
| `build_context_string(project)` | Build context string for system prompt |
| `has_recommendations(type)` | Check if type has recommendations |
| `get_supported_types()` | Get list of types with recommendations |

### 6. `PromptTemplateEngine` — Dynamic Prompt Generation

Generates customized system prompts at runtime based on active project context, tool recommendations, and custom instructions.

| Method | Description |
|--------|-------------|
| `generate_prompt(user_input, ...)` | Generate full system prompt with context injection |
| `detect_active_project(user_input)` | Detect active project from user input |
| `get_tool_recommendations(project_type)` | Get tool recommendations for project type |
| `load_custom_template(path)` | Load custom prompt template from file |

**Features:**
- **Dynamic Context**: Injects active project details (type, path, framework, etc.)
- **Tool Recommendations**: Includes relevant tool suggestions based on project type
- **Custom Templates**: Supports custom prompt templates via CLI or environment variable
- **Non-Breaking**: Falls back to static prompt if injection is disabled

---

## Supported Project Types

### Software Development

| Type | Primary Indicators | Tools |
|------|-------------------|-------|
| **Python** | `pyproject.toml`, `setup.py`, `requirements.txt` | pip, pytest, uvicorn, black, mypy |
| **Node.js** | `package.json`, `yarn.lock`, `pnpm-lock.yaml` | npm, yarn, pnpm |
| **Java** | `pom.xml`, `build.gradle` | Maven, Gradle |
| **C/C++** | `CMakeLists.txt`, `Makefile` | gcc, clang, cmake, make |
| **Rust** | `Cargo.toml`, `Cargo.lock` | cargo |
| **Go** | `go.mod`, `go.sum` | go build, go test |

### Embedded & Hardware

| Type | Primary Indicators | Tools |
|------|-------------------|-------|
| **ESP32/FreeRTOS** | `sdkconfig`, `main.c`, `CMakeLists.txt` | idf.py, esptool.py |
| **PX4/UAV** | `ROMFS/px4fmu_common`, `CMakeLists.txt` | make px4_sitl, mavlink |
| **Motorola TRBO** | `.rdt`, `config.json`, firmware `.bin` | TRBO config tool, keygen, flash |
| **FPGA** | `.vhd`, `.sv`, `.xdc` | Vivado, Quartus |
| **Yocto** | `conf/local.conf`, `conf/bblayers.conf` | bitbake, devtool |
| **System Software** | `Makefile`, `Kconfig`, `arch/` | make, gcc, cross-compiler |

### Configuration / Non-Code

| Type | Primary Indicators | Tools |
|------|-------------------|-------|
| **Documentation** | `.md`, `.rst`, `mkdocs.yml` | MkDocs, Sphinx |
| **Configuration** | `.json`, `.yaml`, `.ini` | Custom CLI tools |
| **Data Science** | `.ipynb`, `requirements.txt` | Jupyter, pandas, scikit-learn |

---

## Configuration

### Workspace Config File

The workspace configuration is stored in `.agentworkspace.json` at the workspace root. This file is:
- **Auto-created** on first project registration
- **UTF-8 encoded** with pretty-printed JSON
- **Versioned** for future schema migrations
- **Validated** on load with schema checks

### Workspace Path Resolution

When registering a project, the workspace path determines where `.agentworkspace.json` is created:

| Scenario | Workspace Path | `.agentworkspace.json` Location |
|----------|---------------|--------------------------------|
| Single project (default) | Project path itself | Inside the project directory |
| Explicit `workspace_path` | User-specified path | At the specified path |
| Multiple projects | Shared parent directory | At the shared workspace root |

**Default Behavior:**
- When `workspace_path` is **not provided**, it defaults to the **project path itself**
- This ensures the workspace config is created in the correct location for single-project scenarios
- For multi-project workspaces, explicitly specify `workspace_path` to share a common config

**Example:**
```python
# Single project - workspace created in the project directory
register_project("/home/user/my-project")
# → .agentworkspace.json created at /home/user/my-project/.agentworkspace.json

# Multi-project - explicit workspace path
register_project("/home/user/project-a", workspace_path="/home/user")
register_project("/home/user/project-b", workspace_path="/home/user")
# → .agentworkspace.json created at /home/user/.agentworkspace.json
```

### Schema Validation & Migration

The `WorkspaceConfig` class validates the config structure on load and supports migration from older versions:

```python
from project_manager.config import validate_config, migrate_config

# Validate
validate_config(config_dict)  # Raises ValueError if invalid

# Migrate
migrate_config(config_dict)   # Migrates to latest schema
```

---

## API Reference

### Toolkit Functions (LlamaIndex FunctionTools)

All functions are exposed as LlamaIndex `FunctionTool` objects via `get_all_tools()`.

#### Project Detection

| Function | Description |
|----------|-------------|
| `scan_directory(path)` | Scan directory to detect project types with confidence scores |
| `get_project_indicators(type)` | Get indicator files used to detect a specific project type |
| `resolve_project_type_ambiguity(path)` | Prompt user to resolve ambiguous detection (HITL) |

#### Workspace Management

| Function | Description |
|----------|-------------|
| `get_workspace_config(path)` | Load and return workspace configuration |
| `get_workspace_summary(path)` | Get summary of workspace state |
| `list_projects(path)` | List all registered projects |
| `get_project_types_summary(path)` | Get projects grouped by type |
| `clear_all_projects(path)` | Remove all projects (destructive) |

#### Project Lifecycle

| Function | Description |
|----------|-------------|
| `register_project(path, name, force, ...)` | Register a project in the workspace |
| `get_project_details(name, path)` | Get detailed project information |
| `update_project(name, **kwargs)` | Update project metadata |
| `remove_project(name, path)` | Remove a project |
| `rename_project(old, new, path)` | Rename a project |

#### Actions

| Function | Description |
|----------|-------------|
| `set_project_actions(name, actions, path)` | Set build/run/test actions for a project |
| `set_single_action(name, action, command, path)` | Set a single action command |
| `get_project_actions(name, path)` | Get configured actions for a project |

#### Helpers

| Function | Description |
|----------|-------------|
| `build_project_context(path)` | Build project context string for system prompt injection |
| `initialize_project_management(auto_scan, ...)` | Initialize with optional auto-scan |
| `get_all_tools()` | Return all tools as FunctionTool list |

---

## Integration with Agent

### Tool Registration

Project manager tools are registered with the agent's tool retriever:

```python
from project_manager.agent_project_manager_toolkit import get_all_tools

tools = get_all_tools()  # Returns List[FunctionTool]
```

### System Prompt Injection

Project context is injected into the system prompt and agent memory:

```python
from project_manager.agent_project_manager_toolkit import build_project_context

context = build_project_context()
# Returns: "### Registered Projects\n- backend (Python): api/\n- frontend (Node.js): web/"
```

### Auto-Scan on Startup

```python
from project_manager.agent_project_manager_toolkit import initialize_project_management

result = initialize_project_management(auto_scan=True)
# Returns: "Auto-registered project: my-project (Python)"
```

---

## Human-in-the-Loop

When the scanner detects multiple project types with similar confidence scores, the agent prompts the user to resolve the ambiguity:

```
Multiple project types detected in '/home/user/project':

1. Python (confidence: 0.72)
2. Data Science (confidence: 0.68)

Enter the number of the correct project type (or 0 for Unknown):
```

**Resolution Methods:**
- **Console** — Standard terminal input (default)
- **Whiptail** — Dialog-based input (Linux)

**Timeout Handling:**
- Configurable timeout (default: 30 seconds)
- Falls back to best guess on timeout
- Default answer configurable via environment variable

---

## Runtime Prompt Injection

The `PromptTemplateEngine` provides dynamic system prompt generation based on the active project context. Instead of a static system prompt, the agent generates a tailored prompt at runtime that includes:

- **Active Project Context**: Details about the currently active project (type, path, framework, etc.)
- **Tool Recommendations**: Suggested tools and actions based on the project type
- **Custom Instructions**: User-defined instructions or overrides

### Features

| Feature | Description |
|---------|-------------|
| **Dynamic Generation** | System prompt is rebuilt at runtime based on detected project |
| **Project Detection** | Automatically detects active project from user input or current directory |
| **Custom Templates** | Supports custom prompt templates via `--prompt-template` or `TORVALDS_PROMPT_TEMPLATE` |
| **Tool Recommendations** | Includes relevant tool suggestions based on project type |
| **Non-Breaking** | Falls back to static prompt if injection is disabled |

### Usage

```bash
# Enable prompt injection (default)
python agent-torvalds.py

# Disable prompt injection
python agent-torvalds.py --no-prompt-injection

# Use custom template
python agent-torvalds.py --prompt-template /path/to/template.txt

# Force specific project context
python agent-torvalds.py --force-project backend
```

---

## Usage Examples

### Direct API Usage

```python
from project_manager import ProjectManager, ProjectScanner, WorkspaceConfig

# Scan a directory
scanner = ProjectScanner()
scores = scanner.scan_directory("/path/to/project")
# {'Python': 0.92, 'Data Science': 0.45}

# Detect project type
project_type = scanner.detect_project_type("/path/to/project")
# 'Python'

# Manage workspace
manager = ProjectManager("/path/to/workspace")
result = manager.discover_and_register("/path/to/project")

# Get workspace summary
summary = manager.get_workspace_summary()
```

### As LlamaIndex Tools

```python
from project_manager.agent_project_manager_toolkit import get_all_tools

tools = get_all_tools()
# Use with LlamaIndex agent or retriever
```

### Action Execution

```python
from project_manager.executor import ActionExecutor

executor = ActionExecutor()
result = executor.execute(
    project_name="backend",
    action_name="test",
    command="pytest",
    cwd="/path/to/project",
    timeout=60,
)
print(result.success)   # True/False
print(result.stdout)    # Captured output
print(result.duration_ms)  # Execution time
```

### Tool Recommendation

```python
from project_manager.recommender import ToolRecommender

recommender = ToolRecommender()
recs = recommender.recommend_for_type("Python")
print(recs["priority_tools"])  # ['execute_shell_command', 'read_file', ...]
print(recs["recommended_actions"])  # {'build': 'python -m build', 'test': 'pytest', ...}
```

---

## CLI Options

| Option | Description |
|--------|-------------|
| `--auto-scan` | Auto-scan and configure projects on startup |
| `--project-type TYPE` | Override auto-detected project type |
| `--no-prompt-injection` | Disable dynamic prompt injection (use static system prompt) |
| `--prompt-template PATH` | Path to custom prompt template file |
| `--no-tool-recommendations` | Disable tool recommendations in dynamic prompts |
| `--force-project NAME` | Force a specific project name for prompt context |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TORVALDS_HITL_ENABLED` | `true` | Enable/disable HITL for project detection |
| `TORVALDS_HITL_METHOD` | `console` | Input method: `console` or `whiptail` |
| `TORVALDS_HITL_TIMEOUT` | `30` | Timeout in seconds for HITL prompts |
| `TORVALDS_HITL_DEFAULT_ANSWER` | `""` | Default fallback answer on timeout |
| `TORVALDS_PROMPT_INJECTION` | `true` | Enable/disable runtime prompt injection |
| `TORVALDS_PROMPT_TEMPLATE` | `""` | Path to custom prompt template file |
| `TORVALDS_INCLUDE_RECOMMENDATIONS` | `true` | Include tool recommendations in prompt |

---

## Implementation History

The module was developed through a 7-step implementation plan:

| Step | Status | Description |
|------|--------|-------------|
| 01 | ✅ Done | Project Scanner Module — Core type detection engine |
| 02 | ✅ Done | Workspace Config Module — Configuration persistence layer |
| 03 | ✅ Done | Project Manager Toolkit — LlamaIndex FunctionTools integration |
| 04 | ✅ Done | HITL Integration — Human-in-the-Loop for ambiguous detection |
| 05 | ✅ Done | Agent Integration — Integration with main agent |
| 06 | ✅ Done | Runtime Prompt Injection — Dynamic system prompt generation |
| 07 | 🔄 WIP | Testing & Validation — Unit and integration tests |

---

## License

This module is part of the Torvalds AI Agent Toolkit, licensed under the **MIT License**.
