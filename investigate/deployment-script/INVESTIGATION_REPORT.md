# Agent Torvalds Deployment Script — Investigation Report

**Date**: 2025-01-13  
**Status**: Investigation Phase 1 — Requirements Analysis  
**Location**: `self-development/investigate/deployment-script/`

---

## 1. Objective

Create a Linux shell script (`deploy-torvalds.sh`) that automates the complete
environment preparation for running **Agent Torvalds** on a fresh Linux system.
The script must:

- Install system-level dependencies (Python, Git, Ollama, PostgreSQL, etc.)
- Initialise the PostgreSQL database schema (roles, databases, extensions, grants)
- Bootstrap the Python virtual environment and install all Python packages
- Configure Ollama and pull the required LLM models
- Produce a ready-to-run environment with zero manual intervention (beyond
  answering interactive prompts where human input is unavoidable)

---

## 2. Codebase Analysis

### 2.1 Entry Points

| File | Description |
|---|---|
| `agent-torvalds.py` | Classic linear REPL orchestrator |
| `agent-torvalds-mw.py` | Multi-window TUI orchestrator (full feature parity) |

Both entry points share the same dependency surface and configuration model.

### 2.2 Dependency Surface

#### System-Level Dependencies

| Dependency | Purpose | Mandatory? |
|---|---|---|
| **Python 3.8+** | Runtime for the agent | Yes |
| **Git** | VCS operations, repo cloning | Yes |
| **Ollama** | Local LLM inference server | Yes |
| **PostgreSQL 14+** | Chat memory, chat history, vector store | Optional (graceful fallback to in-memory) |
| **MySQL** | Database toolkit queries | Optional |
| **C/C++ toolchain** (gcc, cmake) | Compile `llama-cpp-python` from source | Conditional (if `llama-index-llms-llama-cpp` is installed) |
| **libpq-dev** | PostgreSQL C libraries for psycopg | Conditional (if PostgreSQL is used) |
| **libgit2** | System library for `pygit2` | Conditional (pip wheel may suffice) |
| **whiptail / dialog** | Interactive password prompts | Optional (console fallback exists) |

#### Python Dependencies

All listed in `requirements.txt`. Key categories:

| Category | Packages |
|---|---|
| Core LLM | `llama-index`, `llama-index-core`, `llama-index-llms-ollama` |
| Embeddings | `llama-index-embeddings-ollama`, `llama-index-embeddings-openai` |
| LLM backends | `llama-index-llms-llama-cpp` |
| Storage | `llama-index-storage-chat-store-postgres`, `llama-index-vector-stores-postgres` |
| DB drivers | `psycopg2-binary`, `psycopg[binary]`, `asyncpg`, `mysql-connector-python` |
| ORM | `SQLAlchemy>=2.0.54,<2.1` |
| Vector | `pgvector>=0.5.1` |
| Utilities | `PyYAML`, `rich`, `numpy`, `requests`, `pandas`, `openpyxl` |
| Git | `pygit2>=1.14.0` |
| Testing | `pytest`, `pytest-asyncio` |
| Optional | `asyncssh`, `pydantic`, `routeros_api`, `whiptail` |

#### Ollama Models

| Model | Purpose | Size | Mandatory? |
|---|---|---|---|
| `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | Default chat model | ~16 GB | Yes (default) |
| `nomic-embed-text` | Embedding model for tool retrieval | ~274 MB | Yes (default mode) |

Smaller alternative chat models are documented in the README for machines with
limited RAM/VRAM.

### 2.3 Database Schema

The PostgreSQL setup is handled by `setup_postgres_db.sql`. It performs:

1. **Role creation** — creates the application role (default: `llama`) with login
   and password
2. **Database creation** — creates the application database (default:
   `llama_index_db`) owned by the app role
3. **Privilege grants** — CONNECT, TEMPORARY, USAGE, CREATE on schema public,
   ALL on tables/sequences/functions, default privileges
4. **Extensions** — `pgvector` (for vector memory), `pg_trgm` (for hybrid
   search); both degrade gracefully if unavailable
5. **Verification** — prints role, database, objects, and extension status

The script is **idempotent** and safe to re-run.

### 2.4 Configuration Model

| Layer | Mechanism | Examples |
|---|---|---|
| Environment variables | `TORVALDS_*`, `OLLAMA_HOST`, `MIKROTIK_*`, `SHODAN_*` | `TORVALDS_MODEL`, `TORVALDS_PG_HOST`, `TORVALDS_HITL_ENABLED` |
| YAML config files | `db_toolkit_config.yaml`, `mikrotik_targets.yaml` | DB credentials, router targets |
| CLI flags | `--full`, `--select`, `--no-chat-history`, `--project-path`, etc. | Startup mode, feature toggles |
| Cache | `~/.cache/torvalds/agent_cache.json` | Persistent operational context |

### 2.5 Graceful Degradation

The agent is designed to boot and function even when optional components are
missing:

- **No PostgreSQL** → in-memory chat store (no persistent history)
- **No Ollama** → agent starts but every request fails (Ollama is mandatory
  for actual operation)
- **No MikroTik toolkit** → toolkit reports unavailable, agent boots fine
- **No Shodan toolkit** → toolkit reports unavailable, agent boots fine
- **No pgvector extension** → vector memory blocks unavailable, rest works

---

## 3. Deployment Script Design Requirements

### 3.1 Script Characteristics

| Property | Requirement |
|---|---|
| **Platform** | Linux (Debian/Ubuntu primary; RHEL/Fedora as stretch goal) |
| **Language** | POSIX-compatible bash (`#!/usr/bin/env bash`) |
| **Idempotency** | Safe to re-run; checks before installing |
| **Interactivity** | Prompts for user input where needed (DB passwords, model selection) |
| **Logging** | Every action logged with timestamps; log file written to disk |
| **Error handling** | `set -euo pipefail`; trap on ERR; rollback on critical failures |
| **Privilege** | Detects if `sudo` is needed; prompts for password once |
| **Configuration** | Accepts parameters via CLI flags and/or a config file |
| **Documentation** | Self-documenting with `--help`; every section commented |

### 3.2 Script Sections (Execution Order)

```
1. Prologue
   ├── Shebang, set -euo pipefail, trap handlers
   ├── Parse CLI arguments (--help, --non-interactive, --skip-ollama, etc.)
   ├── Detect OS/distro (deb vs rpm)
   ├── Create log file
   └── Print banner

2. Prerequisites Check
   ├── Python version (>= 3.8)
   ├── Git installed
   ├── Network connectivity (for pip and ollama pulls)
   └── Disk space estimation

3. System Package Installation
   ├── Python 3 + venv + pip (if not present)
   ├── Git (if not present)
   ├── Build tools (gcc, cmake, make) — for llama-cpp-python
   ├── PostgreSQL client libraries (libpq-dev)
   ├── Optional: whiptail/dialog
   └── Optional: PostgreSQL server (if --with-postgres)

4. PostgreSQL Setup (if --with-postgres)
   ├── Install PostgreSQL server package
   ├── Start and enable systemd service
   ├── Run setup_postgres_db.sql (idempotent)
   └── Verify database connectivity

5. Python Virtual Environment
   ├── Create .venv in project root
   ├── Upgrade pip, setuptools, wheel
   └── pip install -r requirements.txt

6. Ollama Setup
   ├── Download and install Ollama binary
   ├── Start and enable systemd service
   ├── Verify server is responding (curl localhost:11434)
   ├── Pull chat model (configurable via --model)
   ├── Pull embedding model (configurable via --embedding-model)
   └── Verify models are loaded

7. Configuration Bootstrap
   ├── Generate .env file from defaults + user input
   ├── Copy db_toolkit_config.yaml.example → db_toolkit_config.yaml (if needed)
   ├── Copy mikrotik_targets.yaml.example → mikrotik_targets.yaml (if needed)
   └── Set file permissions on sensitive files

8. Verification
   ├── Test Python imports (smoke test)
   ├── Test Ollama connectivity
   ├── Test PostgreSQL connectivity (if configured)
   └── Print deployment summary

9. Epilogue
   ├── Print "how to run" instructions
   └── Exit with appropriate code
```

### 3.3 CLI Parameters (Proposed)

| Flag | Default | Description |
|---|---|---|
| `--help` | — | Show usage and exit |
| `--non-interactive` | false | No prompts; use all defaults |
| `--with-postgres` | false | Install and configure PostgreSQL |
| `--postgres-host` | `127.0.0.1` | PostgreSQL host |
| `--postgres-port` | `5432` | PostgreSQL port |
| `--postgres-user` | `llama` | Application role name |
| `--postgres-password` | `llama` | Application role password |
| `--postgres-db` | `llama_index_db` | Application database name |
| `--with-mysql` | false | Install MySQL client libraries |
| `--model` | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | Ollama chat model |
| `--embedding-model` | `nomic-embed-text` | Ollama embedding model |
| `--skip-ollama` | false | Skip Ollama installation (already installed) |
| `--skip-pip` | false | Skip pip install (venv already set up) |
| `--venv-path` | `.venv` | Virtual environment path |
| `--project-path` | `.` | Project root directory |
| `--log-file` | `/var/log/torvalds-deploy.log` | Log file path |
| `--verbose` | false | Verbose output |

### 3.4 Configuration File (Proposed)

A `deploy.conf` file could be used as an alternative to CLI flags:

```bash
# deploy.conf — Torvalds deployment configuration
WITH_POSTGRES=true
PG_HOST="127.0.0.1"
PG_PORT="5432"
PG_USER="llama"
PG_PASSWORD="your_secure_password"
PG_DATABASE="llama_index_db"

OLLAMA_MODEL="richardyoung/qwen3.6-27b-abliterated:Q4_K_M"
OLLAMA_EMBEDDING="nomic-embed-text"

SKIP_OLLAMA=false
SKIP_PIP=false
NON_INTERACTIVE=false
```

---

## 4. Risk Analysis

| Risk | Impact | Mitigation |
|---|---|---|
| Ollama model download fails (16 GB) | Deployment incomplete | Retry logic; allow `--skip-ollama` to install separately |
| PostgreSQL already running with conflicting role/db | Script aborts | Idempotent SQL; detect existing state |
| Insufficient disk space | Script fails mid-way | Pre-flight disk space check |
| C/C++ compilation fails for llama-cpp-python | pip install fails | Pre-install build tools; allow removing from requirements |
| sudo password prompt fails | System packages not installed | Prompt once, cache with `sudo -v` |
| Network unavailable | Cannot install anything | Pre-flight connectivity check |

---

## 5. Next Steps

1. **Draft the shell script** — implement section by section
2. **Test on a clean Ubuntu 24.04 VM** — verify end-to-end
3. **Test idempotency** — run the script twice, verify no errors
4. **Test non-interactive mode** — verify zero prompts
5. **Test partial deployments** — `--skip-ollama`, `--skip-pip`, no PostgreSQL
6. **Document the script** — inline comments + `--help` output
7. **Add to repository** — place in project root, add to README

---

## 6. References

- `README.md` — installation instructions, configuration reference
- `requirements.txt` — Python dependency list
- `setup_postgres_db.sql` — PostgreSQL schema initialization
- `db_toolkit_config.yaml` — database configuration template
- `docs/ollama-setup.md` — Ollama installation and troubleshooting
- `agent-torvalds.py` — main orchestrator source
- `agent-torvalds-mw.py` — multi-window TUI orchestrator source
