# Torvalds' AI Agent Toolkit

A comprehensive, general-purpose AI agent toolkit designed for engineering scientists, mathematicians, database administrators, and technical professionals. This project provides specialized capabilities for mathematical calculations, system operations, database queries, Git/GitHub repository management, APT package management, and technical problem-solving with full access to underlying OS functionality.

---

## Overview

**Torvalds** is an AI assistant that can directly interact with the host operating system and a wide range of technical tools. The toolkit is designed to support engineering scientists, mathematicians, DevOps engineers, and other technical professionals with comprehensive computational and operational capabilities.

> **Key Philosophy**: Tool-first approach - always use provided tools for calculations, file operations, SQL, etc. Never simulate results.

---

## Toolkits Included

> **Note**: The files ending in `*_toolkit.py` are **not agents** themselves - they are **toolkits** that provide tools/functions the agent can call and perform.

### 1. Math Toolkit (`agent_math_toolkit.py`)
- Provides mathematical operations: addition, multiplication, division
- Enables precise numerical calculations
- Supports statistical and engineering computations

### 2. OS Toolkit (`agent_os_toolkit.py`)
- Browse file systems (`ls`, `pwd`)
- Create, read, write, move, and delete files and directories
- Check file/directory existence and permissions
- Full access to underlying OS functionality

### 3. Linux Toolkit (`agent_linux_toolkit.py`)
- Execute shell commands with timeout and error handling
- Run multiple commands sequentially
- Parse command output into structured format
- Get system information (OS, CPU, memory, disk)
- Execute commands with custom environment variables
- Check file permissions

### 4. Windows PowerShell Toolkit (`agent_windows_toolkit.py`)
- Execute PowerShell commands on Windows systems
- Run multiple commands sequentially with batch operation support
- Parse command output into structured format
- Get system information via PowerShell cmdlets
- Check file permissions and access rules
- Execute commands with custom environment variables
- Full Windows system integration

### 5. Git Repository Toolkit (`agent_git_toolkit.py`)
- Initialize and manage Git repositories
- Stage, commit, and push changes
- Retrieve commit history and repository status
- Generate and update changelogs
- Manage remote repositories and upstream tracking
- Get latest commit and recent changes

### 6. GitHub Toolkit (`agent_github_toolkit.py`)
- GitHub API integration for Pull Request management
- Create, list, update, close, and merge Pull Requests
- Add comments and review file changes
- Check authentication status and user information
- Configure Git credentials
- Full PR workflow support

### 7. APT Package Management Toolkit (`agent_apt_toolkit.py`)
- Interactive Debian/Ubuntu package installation
- Command resolution to APT packages
- Multiple password prompting methods (console, whiptail, env_var, parameter)
- Sudo password caching and validation
- Batch package installation
- Automatic dependency resolution workflow

### 8. Database Toolkit (`agent_db_toolkit.py`)
- Execute SQL queries on **PostgreSQL** databases
- Execute SQL queries on **MySQL** databases
- Return query results as structured dictionaries
- Configurable connection parameters via `db_toolkit_config.yaml`

### 9. Chat Memory Module (`agent_chat_memory.py`)
- Persistent chat memory backed by PostgreSQL
- Token-limited memory buffers for conversation context
- Integration with LlamaIndex for AI-powered memory management

### 10. Persistent Cache System (`agent_cache_system.py`)
- JSON-based persistent cache for operational context between sessions
- Stores session info, current directory, active databases, Git repos, error logs
- Configurable cache location via `TORVALDS_CACHE_PATH` environment variable
- Auto-load on startup, incremental updates, configurable retention

### 11. Stats Handler (`agent_stats_handler.py`)
- Per-request statistics collection using Llama Index callbacks
- Tracks token usage (prompt/completion), LLM call count, tool invocations, timing, and errors
- Rich console rendering of statistics after each agent response
- Persistent stats history in cache (configurable max entries)
- Configurable via environment variables (TORVALDS_STATS_ENABLED, TORVALDS_STATS_VERBOSE, etc.)

### 12. Tool Retriever (`agent_tool_retriever.py`)
- On-demand semantic tool loading using Llama Index ObjectIndex
- Ollama embedding support (nomic-embed-text model)
- Reduces context window pollution by loading only relevant tools per query
- Configurable similarity_top_k for tool retrieval

### 13. Main Orchestrator (`agent-torvalds.py`)
- The actual **agent** that coordinates all toolkits
- Provides unified interface to all capabilities
- Handles request routing and response aggregation
- Integrated stats rendering and caching
- Interactive console with command processing

### 14. Spinner Manager (`spinner_manager.py`)
- Global singleton for console spinner management
- Pause/resume functionality for interactive dialogs
- Context manager support for automatic pause/resume
- Callback hooks for lifecycle events
- Shared across toolkit modules

---

## Key Features

| Category | Capabilities |
|----------|-------------|
| **Mathematical Operations** | Precise numerical calculations, mathematical problem solving |
| **System-Level Access** | Direct interaction with OS resources, file management |
| **Shell Command Execution** | Linux bash and Windows PowerShell support, parse output, handle errors, set environment variables |
| **Database Queries** | PostgreSQL and MySQL support with configurable connections |
| **Git Management** | Full Git workflow: init, commit, push, changelog generation |
| **GitHub Integration** | Full PR lifecycle: create, review, comment, merge, authentication |
| **APT Package Management** | Interactive package installation with sudo handling and multiple password methods |
| **Chat Memory** | Persistent conversation memory with LlamaIndex integration |
| **Persistent Cache** | Operational context storage across sessions (directory, DBs, repos, errors) |
| **Per-Request Statistics** | Token usage, timing, tool invocations, error tracking with Rich rendering |
| **On-Demand Tool Loading** | Semantic tool retrieval to reduce context window pollution |
| **Human-in-the-Loop** | Interactive questioning with timeout handling and runtime toggle |
| **Technical Computing** | Engineering and scientific computation support |

---

## Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd agent-torvalds

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Configure database connections (if using DB toolkit)
# Edit db_toolkit_config.yaml with your database credentials
```

### Prerequisites

- Python 3.8+
- PostgreSQL (optional, for database toolkit)
- MySQL (optional, for database toolkit)
- Git installed on the system
- Ollama (optional, for on-demand tool retrieval with embeddings)
- Debian/Ubuntu system (for APT package management toolkit)

---

## Configuration

### Database Configuration

Edit `db_toolkit_config.yaml` to configure database connections:

```yaml
postgres:
  host: 127.0.0.1
  port: 5432
  user: postgres
  password: your_password
  database: your_database

mysql:
  host: 127.0.0.1
  port: 3306
  user: root
  password: your_password
  database: your_database
```

### Statistics Configuration

Configure per-request statistics via environment variables:

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_STATS_ENABLED` | `true` | Enable/disable stats collection |
| `TORVALDS_STATS_VERBOSE` | `false` | Show detailed per-tool timing |
| `TORVALDS_STATS_PERSIST` | `true` | Save stats to cache for history |
| `TORVALDS_STATS_MAX_HISTORY` | `500` | Max number of requests to retain |
| `TORVALDS_STATS_FORMAT` | `compact` | Output format: `compact`, `detailed`, `json` |

### APT Package Management Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_SUDO_PASSWORD` | - | Pre-set sudo password for APT operations |
| `TORVALDS_DEFAULT_PROMPT_METHOD` | `console` | Default password prompt method: `console`, `whiptail`, `env_var`, `parameter` |

### Cache Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_CACHE_PATH` | `~/.cache/torvalds/agent_cache.json` | Custom cache file location |

### Human-in-the-Loop Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_HITL_ENABLED` | `true` | Enable/disable HITL interactions |
| `TORVALDS_HITL_METHOD` | `console` | Input method: `console` or `whiptail` |
| `TORVALDS_HITL_TIMEOUT` | `30` | Timeout in seconds for HITL prompts |
| `TORVALDS_HITL_DEFAULT_ANSWER` | `""` | Default fallback answer on timeout |
| `TORVALDS_HITL_RUNTIME_TOGGLE` | `true` | Enable/disable runtime toggle commands |

---

## Usage Examples

### Math Operations
```python
from agent_math_toolkit import add, multiply, divide

result = add(10, 20)        # 30
result = multiply(5, 6)     # 30
result = divide(100, 4)     # 25.0
```

### System Operations
```python
from agent_os_toolkit import ls, pwd, mkdir, read_file

current_dir = pwd()
files = ls('.')
mkdir('/path/to/new/dir')
content = read_file('/path/to/file.txt')
```

### Linux Shell Commands
```python
from agent_linux_toolkit import execute_shell_command, get_system_info

result = execute_shell_command('ls -la')
sys_info = get_system_info()
```

### Windows PowerShell Commands
```python
from agent_windows_toolkit import execute_shell_command, get_system_info

result = execute_shell_command('Get-Process | Select-Object -First 5')
sys_info = get_system_info()
```

### Git Operations
```python
from agent_git_toolkit import git_init_repo, git_commit, git_get_status

git_init_repo('/path/to/repo')
git_commit('/path/to/repo', 'Initial commit')
status = git_get_status('/path/to/repo')
```

### GitHub PR Operations
```python
from agent_github_toolkit import github_create_pull_request, github_list_pull_requests

# Create a PR
result = github_create_pull_request(
    owner="username",
    repo="repo-name",
    title="Add new feature",
    body="Description...",
    head="feature-branch",
    base="main"
)

# List open PRs
prs = github_list_pull_requests("username", "repo-name", state="open")
```

### APT Package Management
```python
from agent_apt_toolkit import install_package, interactive_install_missing_command

# Install a package
result = install_package("ffmpeg", update_first=True)

# Auto-resolve and install missing command
result = interactive_install_missing_command("ffmpeg")
```

### Database Queries
```python
from agent_db_toolkit import run_postgres_query, run_mysql_query

# PostgreSQL
results = run_postgres_query("SELECT * FROM users LIMIT 10")

# MySQL
results = run_mysql_query("SELECT COUNT(*) as total FROM orders")
```

### Cache System
```python
from agent_cache_system import save_to_cache, load_from_cache, get_cache_status

# Save operational context
save_to_cache("context.current_directory", "/home/user/project")

# Retrieve cached value
cached_dir = load_from_cache("context.current_directory")

# View cache status
status = get_cache_status()
```

### Statistics
```python
from agent_stats_handler import RequestStatsHandler, StatsRenderer

# Stats are automatically collected and rendered after each request
# Use --no-stats CLI flag to disable
# Use \stats command to view historical statistics summary
```

### Human-in-the-Loop
```bash
# Start agent with HITL enabled (default)
python agent-torvalds.py --hitl-enabled --hitl-method console --hitl-timeout 60

# Start agent with HITL disabled
python agent-torvalds.py --hitl-disabled

# Runtime commands during execution:
# \hitl-status   - Show current HITL status
# \toggle-hitl   - Toggle HITL on/off
# \hitl-on       - Enable HITL
# \hitl-off      - Disable HITL
```

---

## Project Structure

```
agent-torvalds/
| agent_math_toolkit.py          # Mathematical operations toolkit
| agent_os_toolkit.py            # System-level operations toolkit
| agent_linux_toolkit.py         # Linux shell command execution toolkit
| agent_windows_toolkit.py       # Windows PowerShell execution toolkit
| agent_git_toolkit.py           # Git repository management toolkit
| agent_github_toolkit.py        # GitHub API and PR management toolkit
| agent_apt_toolkit.py           # APT package management toolkit
| agent_db_toolkit.py            # Database query toolkit (PostgreSQL and MySQL)
| agent_chat_memory.py           # Chat memory module with LlamaIndex
| agent_cache_system.py          # Persistent cache for operational context
| agent_stats_handler.py         # Per-request statistics collection and rendering
| agent_tool_retriever.py        # On-demand semantic tool loading
| agent-torvalds.py              # Main orchestrator (the actual agent)
| agent-torvalds-cpp.py          # C++ toolkit integration
| spinner_manager.py             # Global console spinner management
| db_toolkit_config.yaml         # Database configuration
| requirements.txt               # Project dependencies
| LICENSE                        # MIT License
| CHANGELOG.md                   # Version history
| README.md                      # This file
| __pycache__/                  # Python cache
| .venv/                        # Virtual environment
| .git/                         # Git repository
| .gitignore                    # Git ignore rules
| .idea/                        # IDE configuration
| docs/                         # Documentation and proposals
| +-- proposals/                # Design proposals
| +-- agent_cache_system.md
| +-- extended_logging_statistics.md
| +-- on_demand_tool_loading.md
| components/                   # Helper modules and utilities
| +-- README.md                 # Components documentation
| +-- __init__.py
| +-- whiptail_password.py      # Whiptail password prompter
| +-- spinner_controller.py     # Spinner controller
| +-- state_handler.py          # State management handler
| +-- stats_handler.py          # Stats handler component
| +-- event_consumer.py         # Event consumer
| +-- hitl_events.py            # HITL event definitions
| +-- console_input_module.py   # Console input module for HITL
| +-- whiptail_input_module.py  # Whiptail input module for HITL
| +-- human_loop_handler.py     # HITL callback handler
| +-- timeout_manager.py        # Timeout management for HITL
| +-- hitl_runtime_toggle.py    # Runtime toggle for HITL
| investigate/                  # Investigation artifacts and proposals
| +-- human-in-the-loop/        # HITL solution documentation
| +-- +-- README.md             # HITL solution overview
| +-- +-- INVESTIGATION_REPORT.md
| +-- +-- PROPOSAL_step_by_step.md
| +-- +-- implementation-plan/  # Step-by-step implementation docs
| +-- llama-index-workflow/     # LlamaIndex workflow investigation
| +-- whiptail/                 # Whiptail investigation
| tests/                        # Test suite
| +-- __init__.py
| +-- test_cache_system.py
| +-- test_git_toolkit.py
| +-- test_linux_toolkit.py
| +-- test_windows_toolkit.py
| +-- test_apt_toolkit.py
| +-- test_math_toolkit.py
| +-- test_os_toolkit.py
| +-- test_stats.py
| +-- test_stats_mock.py
| +-- test_logging_cli.py
```

---

## Recent Updates (September 2026)

### Latest Features Added
- **Human-in-the-Loop (HITL)**: Interactive questioning with timeout handling and runtime toggle
- **APT Package Management Toolkit**: Full Debian/Ubuntu package installation with multiple password methods
- **Windows PowerShell Toolkit**: Native Windows PowerShell support for command execution
- **GitHub Toolkit**: Complete PR lifecycle management including creation, review, commenting, and merging
- **Spinner Manager**: Global console spinner with pause/resume for interactive operations
- **Real-time Event Streaming**: State management and thread-safe spinner with event consumer
- **Enhanced Logging**: CLI argument for logging level configuration

### Key Refactors
- Moved stats handler to components directory for better organization
- Added comprehensive debug logging throughout the codebase
- Fixed cmd.lower() bug for console command processing
- Improved git_add_files with input validation and richer response

### Pull Request History
- **PR #6**: Merge feature/logging-level-cli-argument into master
- **PR #5**: Fix cmd.lower() bug and refactor stats_handler
- **PR #4**: Merge investigation/llama-index-workflow
- **PR #3**: Add Windows PowerShell toolkit support
- **PR #2**: Add APT package management toolkit with enhanced git utilities
- **PR #1**: Merge cognitive_overhead branch with major features

---

## Safety Guidelines

- **Tool-first**: Always use provided tools for calculations, file ops, SQL, etc.
- **Safety first**: Before any destructive action (delete, drop, modify production data), explicit confirmation is required
- **Clarity and transparency**: All actions are logged with clear messages
- **Context awareness**: Current directory, active databases, and running processes are tracked

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Follow the existing code style and conventions
2. Add appropriate tests for new features
3. Update documentation for any new functionality
4. Ensure backward compatibility where possible
5. Submit pull requests with clear descriptions

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## Version History

See [CHANGELOG.md](CHANGELOG.md) for a detailed list of changes.

---

## Support

For issues, questions, or feature requests, please open an issue in the repository.
