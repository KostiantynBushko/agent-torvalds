# Torvalds' AI Agent Toolkit

A comprehensive, general-purpose AI agent toolkit designed for engineering scientists, mathematicians, database administrators, and technical professionals. This project provides specialized capabilities for mathematical calculations, system operations, database queries, Git/GitHub repository management, APT package management, and technical problem-solving with full access to underlying OS functionality.

---

## Overview

**Torvalds** is an AI assistant that can directly interact with the host operating system and a wide range of technical tools. The toolkit is designed to support engineering scientists, mathematicians, DevOps engineers, and other technical professionals with comprehensive computational and operational capabilities.

> **Key Philosophy**: Tool-first approach - always use provided tools for calculations, file operations, SQL, etc. Never simulate results.

> **The long-form documentation is the [wiki](wiki/)** — installation,
> configuration, the toolkits, the architecture, the database and the
> contribution workflow.  It is a submodule of this repository, so the
> pages travel with the code.

---

## Toolkits Included

> **Note**: The files ending in `*_toolkit.py` are **not agents** themselves - they are **toolkits** that provide tools/functions the agent can call and perform.

### Module documentation

Each module has its own README with the full reference:

| Module | README |
|---|---|
| Project Manager | [project_manager/README.md](project_manager/README.md) |
| Chat History Manager | [chat_manager/README.md](chat_manager/README.md) |
| Components | [components/README.md](components/README.md) |
| MikroTik RouterOS Toolkit | [toolkits/MikroTik-RouterOS/README.md](toolkits/MikroTik-RouterOS/README.md) |
| Shodan Toolkit | [toolkits/shodan-toolkit/README.md](toolkits/shodan-toolkit/README.md) |
| Math Toolkit | [toolkits/math-toolkit/README.md](toolkits/math-toolkit/README.md) |
| Git Toolkit | [toolkits/git-toolkit/README.md](toolkits/git-toolkit/README.md) |
| GitHub Toolkit | [toolkits/github-toolkit/README.md](toolkits/github-toolkit/README.md) |
| OS Toolkit | [toolkits/os-toolkit/README.md](toolkits/os-toolkit/README.md) |
| Linux Toolkit | [toolkits/linux-toolkit/README.md](toolkits/linux-toolkit/README.md) |
| APT Toolkit | [toolkits/apt-toolkit/README.md](toolkits/apt-toolkit/README.md) |
| Windows Toolkit | [toolkits/windows-toolkit/README.md](toolkits/windows-toolkit/README.md) |
| Database Toolkit | [toolkits/db-toolkit/README.md](toolkits/db-toolkit/README.md) |
| Excel Toolkit | [toolkits/xlsx-toolkit/README.md](toolkits/xlsx-toolkit/README.md) |
| Data Analysis Toolkit | [toolkits/data-analysis-toolkit/README.md](toolkits/data-analysis-toolkit/README.md) |

The project documentation:

| Topic | Document |
|---|---|
| **The wiki** — the long-form documentation, carried in this repository as a submodule | [wiki/](wiki/) |
| Deployment — install the agent, configure it, and run the deployment script | [DEPLOYMENT.md](DEPLOYMENT.md) |
| The deployment script — what the `deploy/` folder holds, and its contract | [deploy/README.md](deploy/README.md) |
| Continuous integration — the CI test gate and the known-failure baseline | [docs/ci.md](docs/ci.md) |
| Local LLM setup — install Ollama, pull the models, run the agent | [docs/ollama-setup.md](docs/ollama-setup.md) |
| MikroTik RouterOS Toolkit — the end-user reference | [docs/mikrotik-toolkit.md](docs/mikrotik-toolkit.md) |
| Shodan Toolkit — the end-user reference | [docs/shodan-toolkit.md](docs/shodan-toolkit.md) |
| The design proposals — the documents the features were designed in | [docs/proposals/](docs/proposals/) |
| The self-development rules — how the agent modifies its own code | [SELF_DEVELOPMENT_RULES.md](SELF_DEVELOPMENT_RULES.md) |
| The CI test gate — the script the build runs | [scripts/ci_test_gate.py](scripts/ci_test_gate.py) |
| The change log — every change, newest first | [CHANGELOG.md](CHANGELOG.md) |

The **wiki** is the long-form documentation: installation, configuration,
the toolkits, the architecture, the database and the contribution workflow.
It lives in its own repository — `agent-torvalds.wiki.git` — and is carried
here as a **submodule**, so the pages are versioned next to the code they
describe.  A plain `git clone` leaves the directory empty;
`git clone --recurse-submodules` brings the pages with it.

| Wiki page | What it covers |
|---|---|
| [wiki/Home.md](wiki/Home.md) | The overview and the quick start |
| [wiki/Installation.md](wiki/Installation.md) | Clone, virtualenv, dependencies, Ollama, the models |
| [wiki/Deployment.md](wiki/Deployment.md) | The one-command install: the script, its phases, its `.env` |
| [wiki/Configuration.md](wiki/Configuration.md) | LLM, database, cache, statistics, HITL, the context guard |
| [wiki/Toolkits.md](wiki/Toolkits.md) | Every toolkit and what it can do |
| [wiki/Usage.md](wiki/Usage.md) | The runtime commands, chat sessions, router and Shodan commands |
| [wiki/Architecture.md](wiki/Architecture.md) | The orchestrators, the components, the event flow, the project layout |
| [wiki/Database.md](wiki/Database.md) | PostgreSQL setup, the schema, and the Sqitch migrations |
| [wiki/Contributing.md](wiki/Contributing.md) | Branching, commit style, the self-development workflow |

### 1. OS Toolkit (`toolkits/os-toolkit/`)
- The current working directory, directory listings, and path checks
- Creating, reading, writing, copying, moving and removing files and
  directories
- Comprehensive system information: OS, hardware, and user details
- Built on the **standard library only** — `os`, `shutil`, `pathlib` and
  `platform`. The reusable core package in `toolkits/os-toolkit/` has
  **no** LlamaIndex imports and **no** third-party dependency at all, so
  it works in any Python that exists
- The LlamaIndex adapter is the one module that knows about the agent
  framework, and it is imported on demand
- No tool raises: a failure is reported as a message string (or as
  `{"error": ...}`), so the model gets a message it can reason about
- `rm` is destructive and irreversible; the tool description and the
  docstring both say so, so the model sees the warning before it calls
  the tool
- The eleven tools join the **Operating System** category of the startup
  tool selection menu (`--select`, and `\tools` / `\tool-select` in the
  TUI), so the whole category can be loaded on its own
- See the [OS Toolkit README](toolkits/os-toolkit/README.md) for the
  module reference

### 2. Linux Toolkit (`toolkits/linux-toolkit/`)
- Running shell commands, with a timeout, a working directory and an
  option to skip the shell
- Running a series of commands one after another
- Splitting command output into lines and metadata
- System information — OS, CPU, memory and disk — gathered through the
  shell
- File permissions, owner and group
- Running a command with extra environment variables
- Built on the **standard library only** — `subprocess`, `os`, `logging`
  and `typing`. The reusable core package in `toolkits/linux-toolkit/`
  has **no** LlamaIndex imports and **no** third-party dependency at
  all, so it works in any Python that exists
- The LlamaIndex adapter is the one module that knows about the agent
  framework, and it is imported on demand
- No tool raises: a failure is reported — a non-zero exit code, or
  `returncode: -1` and the error text in `stderr` — so the model gets a
  message it can reason about
- The six tools join the **System** category of the startup tool
  selection menu (`--select`, and `\tools` / `\tool-select` in the TUI),
  so the whole category can be loaded on its own
- See the [Linux Toolkit README](toolkits/linux-toolkit/README.md) for the
  module reference

### 3. Windows PowerShell Toolkit (`toolkits/windows-toolkit/`)
- Running PowerShell commands, with a timeout, a working directory and an
  option to skip the shell
- Running a series of commands one after another
- Splitting command output into lines and metadata
- System information — OS, CPU, memory and disk — gathered through the
  PowerShell cmdlets
- File ownership and access rules
- Running a command with extra environment variables
- The PowerShell executable is picked automatically: `pwsh` (PowerShell
  Core 7+) is preferred, `powershell.exe` (Windows PowerShell 5.1+) is
  the fallback
- Built on the **standard library only** — `subprocess`, `logging` and
  `typing`. The reusable core package in `toolkits/windows-toolkit/` has
  **no** LlamaIndex imports and **no** third-party dependency at all, so
  it works in any Python that exists
- The LlamaIndex adapter is the one module that knows about the agent
  framework, and it is imported on demand
- No tool raises: a failure is reported — a non-zero exit code, or
  `returncode: -1` and the error text in `stderr` — so the model gets a
  message it can reason about
- The six tools join the **System** category of the startup tool
  selection menu (`--select`, and `\tools` / `\tool-select` in the TUI),
  so the whole category can be loaded on its own
- The toolkit is loaded **only on Windows**, so exactly one of the
  Windows, Linux and OS toolkits is ever in the menu
- See the [Windows Toolkit README](toolkits/windows-toolkit/README.md) for
  the module reference

---

### 4. GitHub Toolkit (`toolkits/github-toolkit/`)
- Full Pull Request lifecycle: create, list, inspect, update, close, merge
- Comments, file-change reviews, and review submissions
- Authentication status and the authenticated user profile
- Git credential configuration for commits
- Built on `requests` — the reusable core package in
  `toolkits/github-toolkit/` has **no** LlamaIndex imports, so it also
  works as a plain library
- The LlamaIndex adapter is the one module that knows about the agent
  framework, and it is imported on demand
- No tool raises: a failure is reported as `False` or as
  `{"success": False, "error": ...}`, so the model gets a message it can
  reason about
- The thirteen tools join the **Version Control** category of the startup
  tool selection menu (`--select`, and `\tools` / `\tool-select` in the
  TUI), so the whole category can be loaded on its own
- See the [GitHub Toolkit README](toolkits/github-toolkit/README.md) for
  the module reference

### 5. APT Package Management Toolkit (`toolkits/apt-toolkit/`)
- Resolving a missing command to the APT package that provides it —
  through `apt-file`, `dpkg` or `apt-cache`, in that order
- Checking whether a command is on the `PATH`
- Installing one package, or several in sequence
- The end-to-end workflow: detect the missing command, resolve it,
  install it, and verify that it is there afterwards
- Obtaining the sudo password from a parameter, the
  `TORVALDS_SUDO_PASSWORD` environment variable, the session cache,
  or the console — with an automatic fallback between the console
  and the whiptail dialog
- Validating a sudo password, and clearing the cached one
- Choosing the default password prompt method for the session
- The reusable core package in `toolkits/apt-toolkit/` has **no**
  LlamaIndex imports, so the operations also work as a plain
  library. It needs `rich` for the console password prompt, and
  the repository's own `components.whiptail_password` for the
  whiptail one — both imports are deferred, and both degrade
  gracefully when they are missing
- The LlamaIndex adapter is the one module that knows about the
  agent framework, and it is imported on demand
- No tool raises: a failure is reported — `success: False` and
  the reason in `error` — so the model gets a message it can
  reason about
- The ten tools join the **System / Package Management** category
  of the startup tool selection menu (`--select`, and `\tools` /
  `\tool-select` in the TUI)
- The command-line interface moved with the toolkit:
  `python -m toolkits.apt_toolkit --show-method`
- See the [APT Toolkit README](toolkits/apt-toolkit/README.md) for the
  module reference

### 6. Database Toolkit (`toolkits/db-toolkit/`)
- Execute SQL queries on **PostgreSQL** databases
- Execute SQL queries on **MySQL** databases
- Return query results as structured dictionaries
- Configurable connection parameters via `db_toolkit_config.yaml`
- The reusable core package in `toolkits/db-toolkit/` has **no**
  LlamaIndex imports, so it also works as a plain library
- See the
  [Database Toolkit README](toolkits/db-toolkit/README.md)

### 6a. Excel Toolkit (`toolkits/xlsx-toolkit/`)
- Read an `.xlsx` file as a list of dictionaries, keyed by the header row
- Write a list of dictionaries to a new workbook
- List the sheets of a workbook, copy one sheet into a new file, and read
  the used range of a sheet
- Read and write a single cell, by its reference (`A1`)
- Apply bold, colour, alignment, border and fill over a range of cells
- Create an empty workbook, optionally with named sheets
- The reusable core package in `toolkits/xlsx-toolkit/` has **no**
  LlamaIndex imports, so it also works as a plain library
- See the
  [Excel Toolkit README](toolkits/xlsx-toolkit/README.md)

### 6b. Data Analysis Toolkit (`toolkits/data-analysis-toolkit/`)
- Read an `.xlsx` or a `.csv` file as a list of dictionaries
- Summarise the data: descriptive statistics, the DataFrame's shape,
  columns and dtypes, and the statistics of a single column
- Select and reshape it: filter by a condition, sort by a column, and
  list the distinct values of a column
- Aggregate it: group and aggregate, pivot into a cross-tab, compute the
  correlation matrix, and detect the missing values
- Export a list of dictionaries to a new `.xlsx` or `.csv` file
- The reusable core package in `toolkits/data-analysis-toolkit/` has
  **no** LlamaIndex imports, so it also works as a plain library
- See the
  [Data Analysis Toolkit README](toolkits/data-analysis-toolkit/README.md)

### 7. Chat Memory (`chat_manager/`)
- The chat memory is provided by the **Chat History Manager** — see § 15
- The legacy `agent_chat_memory.py` module has been removed; the manager is the only
  source of a memory buffer, and an in-memory buffer is the last resort
- Token-limited memory buffers for conversation context, one per session
- Integration with LlamaIndex for AI-powered memory management

### 8. Persistent Cache System (`agent_cache_system.py`)
- JSON-based persistent cache for operational context between sessions
- Stores session info, current directory, active databases, Git repos, error logs
- Configurable cache location via `TORVALDS_CACHE_PATH` environment variable
- Auto-load on startup, incremental updates, configurable retention

### 9. Stats Handler (`agent_stats_handler.py`)
- Per-request statistics collection using Llama Index callbacks
- Tracks token usage (prompt/completion), LLM call count, tool invocations, timing, and errors
- Rich console rendering of statistics after each agent response
- Persistent stats history in cache (configurable max entries)
- Configurable via environment variables (TORVALDS_STATS_ENABLED, TORVALDS_STATS_VERBOSE, etc.)

### 10. Tool Retriever (`agent_tool_retriever.py`)
- On-demand semantic tool loading using Llama Index ObjectIndex
- Ollama embedding support (nomic-embed-text model)
- Reduces context window pollution by loading only relevant tools per query
- Configurable similarity_top_k for tool retrieval

### 11. Main Orchestrator (`agent-torvalds.py`)
- The actual **agent** that coordinates all toolkits
- Provides unified interface to all capabilities
- Handles request routing and response aggregation
- Integrated stats rendering and caching
- Interactive console with command processing
- **Optional context guard** (`--context-guard-on`, or `TORVALDS_CONTEXT_GUARD=true`):
  trims the prompt to the model's context window and keeps the user request,
  so that a long tool-using run cannot overflow the window (the Ollama server
  truncates the prompt from the front, which drops the user request and makes
  the model template fail with "No user query found in messages.").  It is
  **off by default** — the guard changes what the model is shown, so the
  operator asks for it.

### 12. Spinner Manager (`spinner_manager.py`)
- Global singleton for console spinner management
- Pause/resume functionality for interactive dialogs
- Context manager support for automatic pause/resume
- Callback hooks for lifecycle events
- Shared across toolkit modules


### 13. Project Manager (`project_manager/`)
- Automatic project type detection via file indicator scanning
- Workspace configuration persistence in `.agentworkspace.json`
- Project action execution (build, test, run, clean) with timeout support
- Project-aware tool recommendation engine
- Human-in-the-Loop resolution for ambiguous project types
- Full LlamaIndex FunctionTools integration
- `--project-path` CLI flag to load and work on a specific project directory on startup
- See [Project Manager README](project_manager/README.md) for details

### 14. Multi-Window Console Agent (`agent-torvalds-mw.py`)
- The **multi-window** variant of the orchestrator, built on top of `agent-torvalds.py`
- Persistent Multi-Window TUI: Markdown document viewer, background worker/tool progress,
  agent telemetry inspector, and a non-blocking command bar with HITL dialogs
- **Full feature parity** with the classic orchestrator:
  - Startup tool selection (`--select`) with an interactive category picker
  - Project Management: `--auto-scan`, `--project-path`, workspace config, project context injection
  - Chat History Manager: multi-user, multi-session history with `\chat-*` commands
  - Runtime Prompt Injection: dynamic system prompt derived from the active project
  - Callback-manager propagation for LLM-level event tracking
- TUI slash commands: `\help`, `\tools`, `\tool-list`, `\projects`, `\project-info`,
  `\project-status`, `\project-summary`, `\chat-sessions`, `\chat-select`, `\chat-info`,
  `\chat-user`, …
- Seamless fallback to the classic linear REPL via `--no-tui` or in headless/piped environments

### 15. Chat History Manager (`chat_manager/`)
- Multi-user, multi-session chat history with a backend-agnostic storage interface
- Session lifecycle: create, list, select, rename, delete, clear
- Per-session message isolation — each session maps to its own LlamaIndex `chat_key`
- Automatic user identification from the OS login with on-demand provisioning
- Active session persisted in the database and restored on the next startup
- User settings API (`get_user_settings` / `update_user_settings`) and the `\chat-user` command
  over the user's own preferences — the chat token limit among them
- Interactive startup session picker plus eight `\chat-*` runtime commands
- Dual-connector architecture: SQLAlchemy for metadata, LlamaIndex for message bodies
- Graceful fallback to an in-memory message store when PostgreSQL is unavailable
- Graceful fallback to a local SQLite database when the metadata database is unreachable —
  the chat history keeps working, it is just not shared with other machines
- 198 hermetic unit tests
- See [Chat History Manager README](chat_manager/README.md) for details

### 16. MikroTik RouterOS Toolkit (`toolkits/MikroTik-RouterOS/`)
- SSH-based configuration and monitoring of MikroTik routers
- Eight tools: list targets, test connection, run a command, read a config
  section, export the configuration, read the identity, list the interfaces,
  read the health
- Reusable core package in `toolkits/MikroTik-RouterOS/` with **no**
  LlamaIndex imports, so it also works as a plain library
- Rule-based risk classifier in front of every write: reads run directly,
  changes need `confirm=True`, and HIGH / CRITICAL changes additionally need
  a human approval
- A command that would drop the management path is escalated to `CRITICAL`
- Multi-line and chained commands are refused outright — the MikroTik SSH
  server has no pseudo-terminal
- Host-key verification with a hard stop (`HOST_KEY_MISMATCH`) on a change
- Secrets are redacted from every result, log line and exception message
- Four interactive commands: `\routers`, `\router-health <target>`,
  `\router-interfaces <target>`, `\router-backup <target>`
- The eight tools form the **Network** category of the startup tool
  selection menu (`--select`, and `\tools` / `\tool-select` in the TUI),
  so they can be loaded on their own
- Optional dependency (`asyncssh`) — the agent still boots without it
- 150 unit tests plus an opt-in integration suite against a real router
- See the [MikroTik RouterOS Toolkit README](toolkits/MikroTik-RouterOS/README.md)
  for the module reference
- See [MikroTik RouterOS Toolkit docs](docs/mikrotik-toolkit.md) for details

### 17. Shodan Toolkit (`toolkits/shodan-toolkit/`)
- Internet-exposure intelligence from the Shodan database: which hosts are
  reachable, what software they run, which ports are open, which are
  honeypots
- Sixteen tools: search, count, host lookup, statistics, trends, DNS
  records, honeypot score, public IP, account info, list alerts, list
  scans, raw CLI, and the four write-capable tools
- Wraps the official `shodan` CLI instead of reimplementing the API client,
  so it inherits Shodan's own rate limiting and output formats - and
  converts the human-readable tables into stable JSON for the model
- Reusable core package in `toolkits/shodan-toolkit/` with **no**
  LlamaIndex imports, so it also works as a plain library
- **Read-only by default**: the four tools that change account state or
  consume credits (alerts, scans, downloads) are opt-in via
  `TORVALDS_SHODAN_ALLOW_MUTATING=1`
- The `shodan_raw` tool is guarded: subcommands that change state, consume
  credits or write files are refused, so it cannot be used to bypass the
  read-only split
- A tool never raises - a failure is returned as a `{"success": false,
  "error": ...}` payload the model can reason about
- The tools form the **Security** category of the startup tool selection
  menu (`--select`, and `\tools` / `\tool-select` in the TUI), so they can
  be loaded on their own
- Optional dependency (`shodan` CLI) - the agent still boots without it
- 145 upstream tests plus the 19 adapter tests
- See the [Shodan Toolkit README](toolkits/shodan-toolkit/README.md) for the
  module reference
- See [Shodan Toolkit docs](docs/shodan-toolkit.md) for details

### 18. Math Toolkit (`toolkits/math-toolkit/`)
- Provides mathematical operations: addition, subtraction, multiplication,
  division, powers, modulo and square roots
- Trigonometry in radians (`sin`, `cos`, `tan`) and logarithms (`log`,
  `log10`), plus the factorial
- A Reverse Polish Notation evaluator for expressions without parentheses
- Reusable core package in `toolkits/math-toolkit/` with **no** LlamaIndex
  imports, so it also works as a plain library
- Every operation is total: a division by zero, a negative square root or a
  malformed expression is reported as a readable error string instead of
  raising, so the model gets a message it can reason about
- The LlamaIndex adapter is the one module that knows about the agent
  framework, and it is imported on demand
- The fourteen tools form the **Mathematics** category of the startup tool
  selection menu (`--select`, and `\tools` / `\tool-select` in the TUI),
  so they can be loaded on their own
- See the [Math Toolkit README](toolkits/math-toolkit/README.md) for the
  module reference

### 19. Git Toolkit (`toolkits/git-toolkit/`)
- Initialize and manage Git repositories
- Stage, commit, and push changes
- Retrieve commit history and repository status
- Generate and update changelogs
- Manage remote repositories and upstream tracking
- Get latest commit and recent changes
- Built on `pygit2` (the binding to libgit2) — the reusable core package
  in `toolkits/git-toolkit/` has **no** LlamaIndex imports, so it also
  works as a plain library
- The LlamaIndex adapter is the one module that knows about the agent
  framework, and it is imported on demand
- No tool raises: a failure is reported as `False`, as
  `{"success": False, "error": ...}` or as an `"Error: ..."` string, so the
  model gets a message it can reason about
- The twenty-seven tools join the **Version Control** category of the
  startup tool selection menu (`--select`, and `\tools` / `\tool-select`
  in the TUI), so the whole category can be loaded on its own
- See the [Git Toolkit README](toolkits/git-toolkit/README.md) for the
  module reference

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
| **Multi-Session Chat History** | Isolated per-session conversations, multi-user scoping, and database-persisted active session |
| **Chat Session Commands** | `\chat-sessions`, `\chat-select`, `\chat-create`, `\chat-delete`, `\chat-rename`, `\chat-info`, `\chat-clear` |
| **User Settings Commands** | `\chat-user`, `\chat-user get <key>`, `\chat-user set <key> <value>`, `\chat-user help` |
| **Interactive Help** | `\help` lists every available command with its description, filtered by the features enabled in the current session |
| **Persistent Cache** | Operational context storage across sessions (directory, DBs, repos, errors) |
| **Per-Request Statistics** | Token usage, timing, tool invocations, error tracking with Rich rendering |
| **On-Demand Tool Loading** | Semantic tool retrieval to reduce context window pollution |
| **Optional Context Guard** | `--context-guard-on` trims the prompt to the model's context window, keeping the user request; **off by default** |
| **Local-First LLM** | Chat and embedding models served by a local Ollama instance - no cloud API, nothing leaves the machine |
| **Project Path Loading** | `--project-path` flag to load, scan, and register a specific project on startup |
| **Human-in-the-Loop** | Interactive questioning with runtime toggle; by default there is **no timeout** — the agent waits for the user |
| **Technical Computing** | Engineering and scientific computation support |
| **Network Devices** | MikroTik RouterOS configuration and monitoring over SSH, with a risk-classified write path and human approval for destructive changes |
| **Router Commands** | `\routers`, `\router-health <target>`, `\router-interfaces <target>`, `\router-backup <target>` |
| **Internet Exposure** | Shodan reconnaissance: host search, port and product statistics, DNS records, honeypot detection, trend analysis |

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

# 5. Install Ollama and pull the models (REQUIRED - see below)
# Linux:
curl -fsSL https://ollama.com/install.sh | sh
# macOS:
#   brew install ollama
# Windows: download OllamaSetup.exe from https://ollama.com/download
ollama pull richardyoung/qwen3.6-27b-abliterated:Q4_K_M   # chat model
ollama pull nomic-embed-text                              # embedding model

# 6. Configure database connections (if using DB toolkit)
# Edit db_toolkit_config.yaml with your database credentials

# 7. Run the agent
python agent-torvalds.py
```

Step 5 is mandatory: the agent has no cloud fallback. It talks to a local
Ollama server for both the chat model and the embedding model. The
[Local LLM Setup](#local-llm-setup-ollama) section below walks through it in
detail.

> **Or let the script do it.** `deploy/deploy-torvalds.sh` performs the
> system packages, the virtual environment, Ollama with the models and a
> starter `.env` in one pass — on a machine that does not have Python
> either. See [`deploy/README.md`](deploy/README.md) and section 17 of
> [DEPLOYMENT.md](DEPLOYMENT.md).

### Prerequisites

- Python 3.8+
- **Ollama** running locally, with the chat model and the embedding model
  pulled (see [Local LLM Setup](#local-llm-setup-ollama)) - **required**
- PostgreSQL (optional, for database toolkit)
- MySQL (optional, for database toolkit)
- Git installed on the system
- Debian/Ubuntu system (for APT package management toolkit)

---

## Local LLM Setup (Ollama)

Torvalds runs entirely on your own hardware. The chat model and the embedding
model are served by a local [Ollama](https://ollama.com) instance, so no
prompt, file or command ever leaves the machine.

The agent needs **two** models:

| Purpose | Model | Required for | Download |
|---|---|---|---|
| Chat & tool calling | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (default) | every run | ~16 GB |
| Embeddings | `nomic-embed-text` | the default tool-retrieval mode | ~274 MB |

> The embedding model is only needed in the **default (retriever) mode**.
> With `--full` or `--select` the agent loads the tools directly and never
> builds the vector index, so `nomic-embed-text` can be skipped.

A full walkthrough, including Docker, remote endpoints and the complete
troubleshooting matrix, is in **[docs/ollama-setup.md](docs/ollama-setup.md)**.

### Step 1 — Install Ollama

**Linux** — installs the binary to `/usr/local/bin/ollama` and registers a
`systemd` service that starts on boot:

```bash
curl -fsSL https://ollama.com/install.sh | sh

# The service is usually started automatically; otherwise:
sudo systemctl start ollama
sudo systemctl status ollama
```

**macOS** — via Homebrew, or download `Ollama-darwin.zip` from
<https://ollama.com/download>:

```bash
brew install ollama
ollama serve            # the desktop app starts the server for you
```

**Windows** — download `OllamaSetup.exe` from <https://ollama.com/download>
and run it. The app starts the server automatically.

**Docker** — a containerised server with the models kept in a named volume:

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
```

### Step 2 — Verify that the server is up

```bash
curl http://localhost:11434/api/version
# {"version":"0.33.2"}
```

`ollama list` prints the models that are currently installed. An empty table
means no model has been pulled yet.

### Step 3 — Pull the models

```bash
# Chat model - the default the agent expects (~16 GB)
ollama pull richardyoung/qwen3.6-27b-abliterated:Q4_K_M

# Embedding model - required by the default tool-retrieval mode (~274 MB)
ollama pull nomic-embed-text

# Confirm both are present
ollama list
```

Smaller chat models, if the 16 GB one does not fit your machine:

```bash
ollama pull qwen2.5-coder:7b-instruct-q4_K_M                                # ~4.7 GB
ollama pull richardyoung/qwen3-8b-abliterated:Q4_K_M                         # ~5.0 GB
ollama pull richardyoung/qwen2.5-coder-14b-instruct-abliterated:Q4_K_M      # ~9.0 GB
```

### Step 4 — Point the agent at the model

The default model is the one pulled above, so nothing has to be configured.
Set `TORVALDS_MODEL` only when you choose a different one:

```bash
export TORVALDS_MODEL="qwen2.5-coder:7b-instruct-q4_K_M"
```

If Ollama does not listen on `http://localhost:11434` (another host, a
container, a non-default port), point the agent at it:

```bash
export TORVALDS_OLLAMA_HOST="http://192.168.1.10:11434"
```

A bare `host:port` is accepted as well - the scheme is filled in for you.
`OLLAMA_HOST` is honoured as a fallback, but `TORVALDS_OLLAMA_HOST` wins when
both are set.

### Step 5 — Run the agent

```bash
source .venv/bin/activate
python agent-torvalds.py
```

The multi-window TUI variant:

```bash
python agent-torvalds-mw.py
```

The **first** request is slow: Ollama loads the model into RAM/VRAM on the
first call. Watch the loaded models with `ollama ps` and free the memory
again with `ollama stop <model>`.

### Verify the whole chain without starting the agent

```bash
# Chat model
curl http://localhost:11434/api/generate -d '{
  "model": "richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
  "prompt": "Reply with exactly: OK",
  "stream": false
}'

# Embedding model
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "hello world"
}'
```

Both endpoints must answer before the agent is started.

### Hardware sizing

| Model | Disk | RAM/VRAM needed (Q4) | Notes |
|---|---|---|---|
| `qwen2.5-coder:7b-instruct-q4_K_M` | 4.7 GB | ~6 GB | fastest, smallest machines |
| `richardyoung/qwen3-8b-abliterated:Q4_K_M` | 5.0 GB | ~7 GB | |
| `richardyoung/qwen2.5-coder-14b-instruct-abliterated:Q4_K_M` | 9.0 GB | ~12 GB | good balance |
| `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | 16 GB | ~20 GB | default, best quality |
| `nomic-embed-text` | 274 MB | ~0.3 GB | embeddings only |

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` / `Could not reach Ollama` | the server is not running | `ollama serve`, or `sudo systemctl start ollama` |
| `model '...' not found` (404) | the model was never pulled, or the tag is wrong | `ollama pull <model>` - the tag must match `ollama list` exactly |
| `nomic-embed-text` not found | the embedding model is missing | `ollama pull nomic-embed-text` |
| `address already in use ... 11434` | an Ollama instance is already listening | it is already running - check `ollama list` |
| The first answer takes minutes | the model is being loaded into memory | expected on the first call; `ollama ps` shows what is resident |
| The process is killed / out of memory | the model does not fit | use a smaller model, or `ollama stop <model>` to unload |
| Answers are slow | running on CPU only | smaller model, or give Ollama GPU acceleration |
| The agent starts but every request fails | wrong endpoint | check `TORVALDS_OLLAMA_HOST` and `curl http://localhost:11434/api/version` |

---

## Configuration

### Ollama / LLM Configuration

The agent is configured through environment variables. All of them can also be
given inline, e.g. `TORVALDS_MODEL=qwen2.5-coder:7b python agent-torvalds.py`.

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_MODEL` | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | Chat model served by Ollama. Must be pulled with `ollama pull` first |
| `TORVALDS_OLLAMA_HOST` | `http://localhost:11434` | Endpoint of the Ollama server. A bare `host:port` is accepted and gets `http://` prepended |
| `OLLAMA_HOST` | - | Fallback for `TORVALDS_OLLAMA_HOST` when the latter is not set |
| `TORVALDS_REQUEST_TIMEOUT` | `99999` | LLM request timeout in seconds |
| `TORVALDS_MAX_ITERATIONS` | `50` | Maximum tool-calling iterations per request |
| `TORVALDS_SIMILARITY_TOP_K` | `8` | Number of tools retrieved per query in retriever mode |

See the [Local LLM Setup](#local-llm-setup-ollama) section for the complete
installation and model-pull walkthrough.

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

### Debugging Configuration

The agent logs the prompt it sends to the model in a **readable** form:
one line per message, the way a person reads it.  The log appears at
the `DEBUG` level.

```console
$ python agent-torvalds.py --log-level DEBUG
...
EventConsumer._on_agent_input: prompt: 5 messages
EventConsumer._on_agent_input:   [0] system: You are Torvalds, a technical AI assistant that interacts with the operating system.
EventConsumer._on_agent_input:   [1] user: I want to improve debug message for context window
EventConsumer._on_agent_input:   [3] assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)
EventConsumer._on_agent_input:   [4] tool: output: ~
```

A message is rendered as its **role**, a colon, and what it carries:
its text, its thinking, and the tool calls it requests.  A tool call
that the chat history carries in the OpenAI shape
(`additional_kwargs["tool_calls"]`) is rendered as well, so the log
shows the same tools the model is shown.

The rendering lives in `components/chat_message.py` — `to_string()`
for one message, `to_strings()` for a whole prompt.

The **empty lines are removed**: a system prompt that ends with a few
newlines, or a document that separates its paragraphs with a run of
blank lines, would otherwise fill the log with empty records.  One
empty line is kept — it is a paragraph break and it carries meaning —
and a run of them is reduced to one.

### The Configuration File

The agent reads its settings from the **environment**, from the **command
line**, and from a **configuration file** — `~/.config/torvalds/` on
Linux and the BSDs, `~/Library/Application Support/torvalds/` on macOS,
and `%APPDATA%` \ `torvalds` on Windows:

```toml
# ~/.config/torvalds/config.toml
[llm]
model = "minimax-m3.1-flash:cloud"
host = "http://localhost:11434"

[hitl]
enabled = true
method = "console"
timeout = 300

[logging]
file = "agent.log"
dir  = "~/.torvalds/logs"
max_size = "10MB"
```

The agent **writes the file for itself** when it starts and it is not
there yet — a commented template, every setting explained, and nothing
uncommented, so it changes nothing about the way the agent runs:

```console
$ python agent-torvalds.py
Config file: ~/.config/torvalds/config.toml
The configuration template was created at ~/.config/torvalds/config.toml — every setting in it is commented out, so the defaults are used
```

The same file can be written by hand:

```console
$ python agent-torvalds.py --write-default-config
The configuration template was written to ~/.config/torvalds/config.toml
```

A value can be changed from the menu, and it is written into the file:

```console
>>> \config logging.file agent.output.log
logging.file is now agent.output.log
  written to ~/.config/torvalds/config.toml
```

The file is **edited**, not rewritten: your comments and the order of the
settings stay as they are.

The **order of things** is the one the project already used, with the file
inserted underneath the environment variables:

```
flag  >  environment variable  >  config file  >  built-in default
```

The file sits **below** the variables on purpose: an operator who already
has variables in their shell profile sees **no change** when they upgrade,
and the file becomes the *"set it once, in one place"* layer.

Every setting reports **where it came from** — `\config` prints the
effective configuration with the layer that won:

```
>>> \config
│ llm.model          │ from-the-file:q4 │ config file ~/.config/torvalds/config.toml │
│ llm.max_iterations │ 2000              │ environment variable TORVALDS_MAX_ITERATIONS │
```

A missing file is not an error, and a broken one is a **warning** — the
agent boots with the defaults and says what it could not read.  The full
documentation is in [`docs/configuration.md`](docs/configuration.md).

### Logging to a File

The agent logs to **stderr** by default.  It can also write the log into
a **file**, rotated at a predefined size, with a **symlink to the current
log file** next to the rotated generations:

```
~/.torvalds/logs/
├── agent.log                    the current log file — a real file
├── agent-current.log -> agent.log  the symlink to the current log file
├── agent.log.1                  the previous generation
└── agent.log.2 ...
```

```console
$ python agent-torvalds.py --log-file agent.log
...
Log file: ~/.torvalds/logs/agent.log (rotated at 10485760 bytes, 5 generations kept)
```

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `--log-file PATH` | `TORVALDS_LOG_FILE` | *off* | The log file.  A bare name goes into the log directory. |
| `--log-dir DIR` | `TORVALDS_LOG_DIR` | `~/.torvalds/logs` | The directory that holds the log, the symlink and the rotated files. |
| `--log-max-size SIZE` | `TORVALDS_LOG_MAX_SIZE` | `10MB` | The size at which the log is rotated.  `B`, `KB`, `MB`, `GB`. |
| `--log-max-files N` | `TORVALDS_LOG_MAX_FILES` | `5` | How many generations are kept.  `0` is refused. |
| `--log-symlink NAME` | `TORVALDS_LOG_SYMLINK` | `<stem>-current.log` | The name of the symlink.  The word `none` turns the pointer off. |

The file logging is **off** until it is asked for, and the flag wins over
the environment variable.  The file is a **tee**: the stderr handler
stays, so the output is still seen in the terminal while the run happens.

The log file is `0600` — it carries the prompts, the tool output and the
answers, and the standard library would create it `0664`.  The size limit
is **soft**: the file may exceed it by the record that crossed it, because
a record is never cut in half.

The full documentation — the rotation, the symlink, what degrades and what
does not — is in [`docs/logging.md`](docs/logging.md).

### The Context Window

The agent writes the size of the model's context window to the log at
the `INFO` level, together with the place the number came from:

```console
$ python agent-torvalds.py
...
2026-10-27 21:24:03,517 [INFO] components.ollama_config: Context window: 8192 tokens — the running model (/api/ps)
```

The number is the window the **server** uses, not the maximum the
model advertises — the two are often very different, and a prompt that
exceeds the real window is truncated from the front by the server,
which drops the user request.  The sources are tried in this order:

| Source | What it is |
|---|---|
| `TORVALDS_CONTEXT_LENGTH` | the explicit override |
| `/api/ps` | the context length of the running model |
| `PARAMETER num_ctx` | the Modelfile of the model |
| `llm.metadata.context_window` | the maximum the model advertises |

The name of the source is in the log line, because a number on its own
does not say whether it is the window the server really uses.  With
the context guard on (`--context-guard-on`), the budget it derives
from the window is logged as well:

```console
2026-10-27 21:24:03,601 [INFO] components.hitl_agent: Context guard: the context window is 8192 tokens — the prompt may use 6554 of them.
```

`investigate/context-window-proof/` holds the proof that the number
comes from the server.

### Human-in-the-Loop Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_HITL_ENABLED` | `true` | Enable/disable HITL interactions |
| `TORVALDS_HITL_METHOD` | `console` | Input method: `console` or `whiptail` |
| `TORVALDS_HITL_TIMEOUT` | `-1` | Timeout in seconds for HITL prompts. `-1` = **no timeout**: the agent waits for the user as long as it takes |
| `TORVALDS_HITL_DEFAULT_ANSWER` | `""` | Default fallback answer on timeout |
| `TORVALDS_HITL_RUNTIME_TOGGLE` | `true` | Enable/disable runtime toggle commands |

### Chat History Manager Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_STORAGE_URI` | derived from `TORVALDS_PG_*` | SQLAlchemy URI for the `users` / `chat_sessions` tables |
| `TORVALDS_STORAGE_FALLBACK_URI` | `sqlite:///~/.torvalds/chat_manager.db` | Local database used when the primary one cannot be reached |
| `TORVALDS_STORAGE_FALLBACK` | *(enabled)* | Set to `off` to switch the local fallback off |
| `TORVALDS_LLAMA_URI` | `postgres+asyncpg://…/llama_index_db` | LlamaIndex chat-store URI for message bodies |
| `TORVALDS_PG_HOST` | `127.0.0.1` | PostgreSQL host |
| `TORVALDS_PG_PORT` | `5432` | PostgreSQL port |
| `TORVALDS_PG_USER` | `postgres` | PostgreSQL user |
| `TORVALDS_PG_PASSWORD` | `postgres` | PostgreSQL password |
| `TORVALDS_PG_DATABASE` | `llama_index_db` | PostgreSQL database name |
| `TORVALDS_CHAT_KEY` | - | Legacy single chat key. If set, it is reused as the General session's `chat_key` to keep pre-existing history reachable |

CLI flags:

| Flag | Description |
|---|---|
| `--no-chat-history` | Disable the ChatHistoryManager and fall back to the legacy single-session chat memory |
| `--no-session-select` | Skip the interactive startup session selection menu |

### MikroTik RouterOS Configuration

The routers are described in `mikrotik_targets.yaml` in the repository root.
Copy the annotated example and fill it in:

```bash
cp mikrotik_targets.yaml.example mikrotik_targets.yaml
```

`mikrotik_targets.yaml` is in `.gitignore`, so a real configuration with real
credentials never reaches the repository — only the `.example` file is
tracked.

| Variable | Default | Description |
|---|---|---|
| `MIKROTIK_TARGETS` | `mikrotik_targets.yaml` | Path of the target configuration file |
| `MIKROTIK_PASSWORD` | - | Fallback password for targets that do not carry one |
| `MIKROTIK_KEY` | - | Fallback private-key path for targets that do not carry one |
| `MIKROTIK_SKIP_APPROVAL` | `false` | Skip the human approval for HIGH / CRITICAL commands. **Off by default** |

The SSH transport needs the optional `asyncssh` package. The agent boots
without it, and the toolkit reports that it is unavailable.

See the [MikroTik RouterOS Toolkit README](toolkits/MikroTik-RouterOS/README.md)
for the module reference and the
[MikroTik RouterOS Toolkit docs](docs/mikrotik-toolkit.md) for the
complete end-user reference.

### Shodan Toolkit Configuration

The toolkit drives the official `shodan` CLI and needs a Shodan API key.

```bash
pip install "shodan>=1.31" "setuptools<81"
shodan-toolkit init <your-api-key>     # writes ~/.config/shodan/api_key (mode 0600)
```

| Variable | Default | Description |
|---|---|---|
| `SHODAN_TOOLKIT_API_KEY` | - | API key (also accepts `SHODAN_API_KEY`) |
| `SHODAN_TOOLKIT_EXECUTABLE` | `shodan` | Path to the Shodan CLI |
| `SHODAN_TOOLKIT_TIMEOUT` | `120` | Per-command timeout in seconds |
| `SHODAN_TOOLKIT_MAX_RESULTS` | `100` | Default result cap for searches |
| `SHODAN_TOOLKIT_CONFIG` | `~/.config/shodan-toolkit/config.json` | Toolkit config file |
| `TORVALDS_SHODAN_ALLOW_MUTATING` | unset | Expose the write-capable tools (alerts, scans, downloads). **Off by default** |

The `shodan` CLI is an optional dependency - the agent boots without it, and
the toolkit reports that it is unavailable.

See the [Shodan Toolkit README](toolkits/shodan-toolkit/README.md) for the
module reference and the [Shodan Toolkit docs](docs/shodan-toolkit.md) for
the complete end-user reference.

---

## Usage Examples

### Math Operations
```python
from toolkits.math_toolkit import add, multiply, divide

result = add(10, 20)        # 30
result = multiply(5, 6)     # 30
result = divide(100, 4)     # 25.0
```

### System Operations
```python
from toolkits.os_toolkit import ls, pwd, mkdir, read_file

current_dir = pwd()
files = ls('.')
mkdir('/path/to/new/dir')
content = read_file('/path/to/file.txt')
```

### Linux Shell Commands
```python
from toolkits.linux_toolkit import execute_shell_command, get_system_info

result = execute_shell_command('ls -la')
sys_info = get_system_info()
```

### Windows PowerShell Commands
```python
from toolkits.windows_toolkit import execute_shell_command, get_system_info

result = execute_shell_command('Get-Process | Select-Object -First 5')
sys_info = get_system_info()
```

### Git Operations
```python
from toolkits.git_toolkit import git_init_repo, git_commit, git_get_status

git_init_repo('/path/to/repo')
git_commit('/path/to/repo', 'Initial commit')
status = git_get_status('/path/to/repo')
```

### GitHub PR Operations
```python
from toolkits.github_toolkit import github_create_pull_request, github_list_pull_requests

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
from toolkits.apt_toolkit import install_package, interactive_install_missing_command

# Install a package
result = install_package("ffmpeg", update_first=True)

# Auto-resolve and install missing command
result = interactive_install_missing_command("ffmpeg")
```

### Database Queries
```python
from toolkits.db_toolkit import run_postgres_query, run_mysql_query

# PostgreSQL
results = run_postgres_query("SELECT * FROM users LIMIT 10")

# MySQL
results = run_mysql_query("SELECT COUNT(*) as total FROM orders")
```

### Excel Files
```python
from toolkits.xlsx_toolkit import read_xlsx_file, write_xlsx_file, get_cell_value

# Read a sheet as a list of dicts, keyed by the header row
rows = read_xlsx_file("report.xlsx", sheet_name="Summary")

# Write a list of dicts to a new workbook
write_xlsx_file("output.xlsx", [{"Name": "Alice", "Age": 30}])

# Read a single cell
value = get_cell_value("report.xlsx", "Summary", "A1")
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
# Start agent with HITL enabled (default).
# The default timeout is -1: no timeout — the agent waits for the user.
python agent-torvalds.py --hitl-enabled --hitl-method console

# Give the user 60 seconds to answer instead
python agent-torvalds.py --hitl-enabled --hitl-method console --hitl-timeout 60

# Start agent with HITL disabled
python agent-torvalds.py --hitl-disabled

# Runtime commands during execution:
# \hitl-status   - Show current HITL status
# \toggle-hitl   - Toggle HITL on/off
# \hitl-on       - Enable HITL
# \hitl-off      - Disable HITL
```

#### Timeout semantics

The default timeout is **`-1`**, which means **no timeout**: the agent waits
for the answer for as long as the human needs, and never falls back to the
default answer on a timer.

| Value | Meaning |
|---|---|
| `-1` (default) | **No timeout** — wait for the user indefinitely. |
| `0` | Expire immediately (useful for scripted runs). |
| `n > 0` | Wait at most *n* seconds, then use the default answer. |

The value is configured with `--hitl-timeout` or the `TORVALDS_HITL_TIMEOUT`
environment variable, and it applies uniformly to the agent question, the
console/whiptail prompt and the multi-window TUI.

### Chat History Manager
```python
from chat_manager import ChatHistoryManager, SessionType

manager = ChatHistoryManager()
manager.initialize()

# Inspect the current user and sessions
print(manager.current_user.username)
for session in manager.list_sessions():
    print(session.session_name, session.is_active)

# Create and switch to a dedicated session
session = manager.create_session(
    name="Postgres migration",
    session_type=SessionType.CUSTOM,
    metadata={"tag": "important"},
)
manager.switch_session(session.session_id)

# Messages stay isolated per session
manager.add_message("How do I set up PostgreSQL?", role="user")
print([m.content for m in manager.get_messages()])

manager.shutdown()
```

```bash
# Runtime commands inside the agent:
# \chat-sessions              - List all sessions
# \chat-select <session_id>   - Switch the active session
# \chat-create <name> [type]  - Create a session (single-word name)
# \chat-delete <session_id>   - Delete a session
# \chat-rename <id> <name>    - Rename a session
# \chat-info                  - Show the active session
# \chat-clear                 - Clear the active session's message history
# \chat-user                  - Show your own settings
# \chat-user get <key>        - Show one setting
# \chat-user set <key> <val>  - Change one setting
# \chat-user help             - List the settings and their ranges
#
# Note: \chat-create / \chat-rename split on whitespace, so use a single-word
# name there. The startup menu's "new <name>" form keeps the full name.
```

---

## Project Structure

```
| agent-torvalds/
| agent_cache_system.py          # Persistent cache for operational context
| agent_stats_handler.py         # Per-request statistics collection and rendering
| agent_tool_retriever.py        # On-demand semantic tool loading
| agent_tool_selection.py        # The startup tool menu, and the category selection
| agent-torvalds.py              # Main orchestrator (the actual agent)
| agent-torvalds-mw.py           # Multi-window console agent (the TUI variant)
| agent-torvalds-cpp.py          # C++ toolkit integration
| spinner_manager.py             # Global console spinner management
| conftest.py                    # The repository-root pytest fixtures
| db_toolkit_config.yaml         # Database configuration
| setup_postgres_db.sql          # The database schema
| mikrotik_targets.yaml.example  # MikroTik router target configuration (example)
| requirements.txt               # Project dependencies
| requirements-ci.lock           # The pinned environment the CI baseline was recorded with
| pytest.ini                     # The test paths, and the pytest configuration
| scripts/                       # The CI test gate and the HITL test scripts
| +-- ci_test_gate.py            # The gate the build runs: a NEW failure breaks the build
| +-- hitl_question_bank.py      # The question classifier's case bank
| +-- hitl_interactive_test.py
| +-- hitl_live_llm_test.py
| LICENSE                        # MIT License
| CHANGELOG.md                   # Version history
| DEPLOYMENT.md                  # The deployment guide
| README.md                      # This file
| SELF_DEVELOPMENT_RULES.md      # The rules the agent follows on its own code
| tools_menu_update.md           # The startup tool menu, category by category
| __pycache__/                  # Python cache
| .venv/                        # Virtual environment
| .git/                         # Git repository
| .gitignore                    # Git ignore rules
| .gitmodules                   # The wiki submodule
| .github/                      # The GitHub Actions workflow
| +-- workflows/                # The CI test gate
| .idea/                        # IDE configuration
| docs/                         # Documentation and proposals
| +-- ci.md                     # Continuous integration: the CI test gate and the known-failure baseline
| +-- ollama-setup.md           # Local LLM setup: install Ollama, pull models, run the agent
| +-- mikrotik-toolkit.md       # MikroTik RouterOS Toolkit: the end-user reference
| +-- shodan-toolkit.md         # Shodan Toolkit: the end-user reference
| +-- proposals/                # Design proposals
| +-- agent_cache_system.md
| +-- extended_logging_statistics.md
| +-- interactive_apt_package_installation.md
| +-- llamaindex_memory_implementation.md
| +-- on_demand_tool_loading.md
| +-- pull_request_tooling.md
| deploy/                       # Deployment scripts
| +-- README.md                 # What the folder holds, and how to use it
| +-- deploy-torvalds.sh        # The automated deployment script
| +-- deploy-torvalds.sh.example.env  # Example environment file
| +-- tests/                    # The folder's contract harness, and the proof that it catches drifts
| +-- verify_deploy_layout.py   # Eleven invariants over the folder and the script
| +-- verify_harness_catches_regressions.py  # The proof that the harness catches eleven drifts
| +-- test_deploy_layout.py     # The harness, under pytest
| wiki/                         # The long-form documentation - a submodule of agent-torvalds.wiki.git
| +-- Home.md
| +-- Installation.md
| +-- Configuration.md
| +-- Toolkits.md
| +-- Usage.md
| +-- Architecture.md
| +-- Database.md
| +-- Contributing.md
| project_manager/              # Project detection, workspace config and project-aware actions
| +-- README.md                 # Project Manager documentation
| +-- __init__.py
| +-- manager.py                # The project manager core
| +-- scanner.py                # Project type detection
| +-- executor.py               # Build / test / run / clean
| +-- recommender.py            # Project-aware tool recommendation
| +-- prompt_engine.py          # Project context for the system prompt
| +-- git_status.py
| +-- config.py
| +-- types.py
| components/                   # Helper modules and utilities
| +-- README.md                 # Components documentation
| +-- __init__.py
| +-- ollama_config.py          # Ollama endpoint resolution (TORVALDS_OLLAMA_HOST)
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
| toolkits/                     # Reusable toolkit packages (no LlamaIndex imports)
| +-- __init__.py               # Package root + import alias shim
| +-- MikroTik-RouterOS/        # MikroTik RouterOS toolkit (core library)
| +-- +-- README.md             # MikroTik RouterOS module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- config.py             # Targets, target registry, YAML loader
| +-- +-- models.py             # CommandResult, RouterIdentity, CommandCategory
| +-- +-- exceptions.py         # Typed error hierarchy
| +-- +-- parser.py             # print / detail / identity parsing
| +-- +-- session.py            # RouterOSSession (exec + session transports)
| +-- +-- safety.py             # Risk classifier + confirmation policy
| +-- +-- _compat.py            # Optional-dependency compatibility layer
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- math-toolkit/             # Math toolkit (core library)
| +-- +-- README.md             # Math toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The mathematics - the library half
| +-- +-- agent_math_toolkit.py # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- git-toolkit/              # Git toolkit (core library)
| +-- +-- README.md             # Git toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The Git operations - the library half
| +-- +-- agent_git_toolkit.py  # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- github-toolkit/           # GitHub toolkit (core library)
| +-- +-- README.md             # GitHub toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The GitHub operations - the library half
| +-- +-- agent_github_toolkit.py # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- os-toolkit/               # OS toolkit (core library)
| +-- +-- README.md             # OS toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The file-system operations - the library half
| +-- +-- agent_os_toolkit.py   # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- linux-toolkit/            # Linux toolkit (core library)
| +-- +-- README.md             # Linux toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The shell operations - the library half
| +-- +-- agent_linux_toolkit.py # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- apt-toolkit/              # APT toolkit (core library)
| +-- +-- README.md             # APT toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The package and install operations
| +-- +-- agent_apt_toolkit.py  # The LlamaIndex adapter
| +-- +-- cli.py                # The command-line interface
| +-- +-- __main__.py           # `python -m toolkits.apt_toolkit`
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- windows-toolkit/          # Windows PowerShell toolkit (core library)
| +-- +-- README.md             # Windows toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The PowerShell operations - the library half
| +-- +-- agent_windows_toolkit.py # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- db-toolkit/               # Database toolkit (core library)
| +-- +-- README.md             # Database toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The SQL operations - the library half
| +-- +-- agent_db_toolkit.py   # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| +-- xlsx-toolkit/             # Excel toolkit (core library)
| +-- +-- README.md             # Excel toolkit module documentation
| +-- +-- __init__.py           # Public API surface
| +-- +-- operations.py         # The Excel operations - the library half
| +-- +-- agent_xlsx_toolkit.py # The LlamaIndex adapter
| +-- +-- py.typed              # PEP 561 marker
| +-- +-- tests/                # Module-local tests (no __init__.py)
| chat_manager/                 # Chat History Manager (multi-user, multi-session)
| +-- README.md                 # Chat History Manager documentation
| +-- __init__.py
| +-- manager.py                # ChatHistoryManager core orchestrator
| +-- user.py                   # User data model
| +-- session.py                # Session data model + SessionType enum
| +-- startup.py                # Global singleton lifecycle + startup hooks
| +-- session_selector.py       # Interactive startup session picker
| +-- backend/                  # Message storage backends (LlamaIndex)
| +-- +-- base.py               # ChatStoreBackend ABC (extends BaseChatStore)
| +-- +-- postgres.py           # PostgreSQL chat store backend
| +-- +-- simple.py             # In-memory chat store backend (fallback)
| +-- storage/                  # User & session metadata (SQLAlchemy)
| +-- +-- models.py             # ORM models: User, Session
| +-- +-- connector.py          # CustomDBConnector — CRUD + schema DDL
| +-- commands/                 # Interactive chat command layer
| +-- +-- handler.py            # Command dispatcher
| +-- +-- cli.py                # Per-command implementations
| +-- tests/                    # Chat manager unit tests
| +-- +-- test_backend.py
| +-- +-- test_commands.py
| +-- +-- test_manager.py
| +-- +-- test_models.py
| +-- +-- test_session_selector.py
| +-- +-- test_startup.py
| +-- +-- test_storage.py
| investigate/                  # Investigation artifacts and proposals
| +-- human-in-the-loop/        # HITL solution documentation
| +-- +-- README.md             # HITL solution overview
| +-- +-- INVESTIGATION_REPORT.md
| +-- +-- PROPOSAL_step_by_step.md
| +-- +-- implementation-plan/  # Step-by-step implementation docs
| +-- llama-index-workflow/     # LlamaIndex workflow investigation
| +-- whiptail/                 # Whiptail investigation
| +-- ChatHistoryManager/       # Chat history design docs & implementation plan
| +-- +-- ChatHistoryManager.md
| +-- +-- storage-proposal.md
| +-- +-- implementation-plan.md
| +-- +-- STEP_AUDIT.md
| tests/                        # Test suite
| +-- __init__.py
| +-- test_cache_system.py
| +-- test_windows_toolkit.py
| +-- test_os_toolkit.py
| +-- test_stats.py
| +-- test_stats_mock.py
| +-- test_logging_cli.py
| +-- test_ollama_config.py
```

---

## Recent Updates (October 2026)

### Latest Features Added
- **A dedicated `deploy/` folder**: the deployment scripts have a home of their own, and the script was repaired — a non-interactive run can now obtain sudo by itself, the `.env` it writes names the variables the agent actually reads, and an unknown option fails instead of reporting success
- **Every toolkit is a module**: the ten loose toolkits at the project root moved under `toolkits/`, each split into a dependency-free library half and a LlamaIndex adapter — so a missing or broken toolkit degrades to "no tools" instead of a failed boot
- **The legacy chat memory is gone**: `agent_chat_memory.py` was removed once the SQLite fallback made it unnecessary — the manager is now the only source of a memory buffer
- **The debug log is readable**: the prompt is rendered message by message instead of dumped as a Python `repr`, and the answer — which was never logged at all — is logged now
- **The context window is logged, and proved**: the number in the log is the window the *server* uses, not the maximum the model advertises, and the source of the number is in the log line
- **The context guard is optional**: `--context-guard-on` trims the prompt to the model's real window; it is off by default
- **The wiki**: the long-form documentation, carried in this repository as a submodule

### Key Refactors
- Ten toolkits moved under `toolkits/`, each split into a library half and an adapter, with a layout contract that pins the dependency set
- The chat history gained a SQLite fallback, so an unreachable database no longer costs the agent its sessions
- The deployment script moved out of `investigate/` and into `deploy/`, where a folder named for what it holds can be found again
- The `Co-Authored-By:` contributor was purged from the history, and the tooling that keeps it out was merged

### Pull Request History
- **PR #65**: give the deployment scripts a dedicated folder, and repair the script
- **PR #57**: make the data analysis toolkit a module — the tenth and last of the series
- **PR #37**: remove the legacy chat memory implementation
- **PR #58**: purge the Claude co-author contributor from the history
- **PR #43**: make the GitHub toolkit a module
- **PR #39**: make the math toolkit a module

The full list is in the [CHANGELOG.md](CHANGELOG.md) and in the
[git history](https://github.com/KostiantynBushko/agent-torvalds/commits/master).

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
