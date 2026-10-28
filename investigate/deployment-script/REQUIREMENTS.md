# Agent Torvalds Deployment Script — Requirements Specification

**Date**: 2025-01-13  
**Status**: Draft  
**Based on**: Investigation Report (`INVESTIGATION_REPORT.md`)

---

## 1. Functional Requirements

### FR-1: System Dependency Installation

The script shall detect and install all system-level packages required to run
Agent Torvalds on a Linux system.

| ID | Requirement |
|---|---|
| FR-1.1 | Detect the target distribution (Debian/Ubuntu or RHEL/Fedora) and use the appropriate package manager (`apt` or `dnf`) |
| FR-1.2 | Install Python 3.8+ with `venv` and `pip` modules if not present |
| FR-1.3 | Install Git if not present |
| FR-1.4 | Install C/C++ build tools (`gcc`, `g++`, `cmake`, `make`) for compiling `llama-cpp-python` |
| FR-1.5 | Install `libpq-dev` (Debian) or `libpq-devel` (RHEL) for PostgreSQL Python drivers |
| FR-1.6 | Optionally install `whiptail` or `dialog` for interactive password prompts |
| FR-1.7 | Skip installation of packages that are already present (idempotency) |

### FR-2: PostgreSQL Setup

When `--with-postgres` is specified, the script shall install and configure
PostgreSQL.

| ID | Requirement |
|---|---|
| FR-2.1 | Install the PostgreSQL server package appropriate for the detected version |
| FR-2.2 | Start the PostgreSQL service and enable it at boot (systemd) |
| FR-2.3 | Execute `setup_postgres_db.sql` to create the application role, database, grants, and extensions |
| FR-2.4 | Accept custom role name, password, database name, host, and port via CLI flags |
| FR-2.5 | Verify database connectivity after setup |
| FR-2.6 | Degrade gracefully if PostgreSQL installation fails (log warning, continue) |

### FR-3: Python Virtual Environment

The script shall create and populate a Python virtual environment.

| ID | Requirement |
|---|---|
| FR-3.1 | Create a virtual environment at the configured path (default: `.venv`) |
| FR-3.2 | Upgrade `pip`, `setuptools`, and `wheel` inside the venv |
| FR-3.3 | Install all dependencies from `requirements.txt` |
| FR-3.4 | Handle pip installation failures gracefully (log errors, report at end) |
| FR-3.5 | Skip venv creation if `--skip-pip` is specified |

### FR-4: Ollama Setup

The script shall install and configure Ollama with the required models.

| ID | Requirement |
|---|---|
| FR-4.1 | Download and install the Ollama binary via the official install script |
| FR-4.2 | Start the Ollama systemd service and enable it at boot |
| FR-4.3 | Verify the Ollama server is responding on `http://localhost:11434` |
| FR-4.4 | Pull the configured chat model (default: `richardyoung/qwen3.6-27b-abliterated:Q4_K_M`) |
| FR-4.5 | Pull the configured embedding model (default: `nomic-embed-text`) |
| FR-4.6 | Verify both models are present via `ollama list` |
| FR-4.7 | Skip Ollama setup if `--skip-ollama` is specified |
| FR-4.8 | Allow alternative model selection via `--model` and `--embedding-model` flags |

### FR-5: Configuration Bootstrap

The script shall generate initial configuration files.

| ID | Requirement |
|---|---|
| FR-5.1 | Generate a `.env` file with all `TORVALDS_*` environment variables set to sensible defaults |
| FR-5.2 | Copy `db_toolkit_config.yaml.example` to `db_toolkit_config.yaml` if the latter does not exist |
| FR-5.3 | Copy `mikrotik_targets.yaml.example` to `mikrotik_targets.yaml` if the latter does not exist |
| FR-5.4 | Set restrictive permissions (0600) on files containing credentials |
| FR-5.5 | Prompt the user for PostgreSQL password in interactive mode; use default in non-interactive mode |

### FR-6: Verification

The script shall verify the deployment before completing.

| ID | Requirement |
|---|---|
| FR-6.1 | Run a Python smoke test: import key modules and verify they load |
| FR-6.2 | Test Ollama connectivity with `curl http://localhost:11434/api/version` |
| FR-6.3 | Test PostgreSQL connectivity if configured (run a simple `SELECT 1`) |
| FR-6.4 | Print a deployment summary table showing what was installed and what was skipped |
| FR-6.5 | Exit with code 0 on success, non-zero on critical failures |

### FR-7: Logging

| ID | Requirement |
|---|---|
| FR-7.1 | Log every action with timestamp to both stderr and a log file |
| FR-7.2 | Log file path configurable via `--log-file` (default: `/var/log/torvalds-deploy.log`) |
| FR-7.3 | Log levels: INFO (normal), WARN (non-critical issues), ERROR (failures) |

---

## 2. Non-Functional Requirements

### NFR-1: Idempotency

The script must be safe to run multiple times. Every installation step must
check for existing state before acting.

### NFR-2: Error Handling

- `set -euo pipefail` at the top of the script
- `trap` on ERR to log the failing command and line number
- Critical failures (Python missing, disk full) abort the script
- Non-critical failures (pgvector extension missing) log a warning and continue

### NFR-3: Interactivity

- Interactive mode (default): prompt for passwords, confirm destructive actions
- Non-interactive mode (`--non-interactive`): use all defaults, no prompts
- All prompts must have sensible defaults (press Enter to accept)

### NFR-4: Portability

- Primary target: Debian 12 / Ubuntu 24.04
- Stretch goal: RHEL 9 / Fedora 40 (dnf package manager)
- Use `#!/usr/bin/env bash` for portability
- Avoid GNU-specific extensions where possible

### NFR-5: Documentation

- `--help` flag prints complete usage information
- Every function in the script is documented with a comment block
- The deployment summary at the end explains how to run the agent

### NFR-6: Security

- Credential files are created with mode 0600
- Passwords are not echoed to the log file
- `sudo` password is prompted once and cached

---

## 3. Acceptance Criteria

| # | Criterion |
|---|---|
| AC-1 | Running the script on a fresh Ubuntu 24.04 VM results in a fully functional Agent Torvalds environment |
| AC-2 | Running the script a second time completes without errors and without re-installing anything |
| AC-3 | `--non-interactive` mode completes without any user prompts |
| AC-4 | `--skip-ollama` mode skips Ollama installation but completes everything else |
| AC-5 | `--with-postgres` mode installs PostgreSQL, creates the database, and verifies connectivity |
| AC-6 | Without `--with-postgres`, the agent boots with in-memory chat store (no PostgreSQL) |
| AC-7 | The deployment summary clearly states what was installed and what was skipped |
| AC-8 | All log output is written to the configured log file |
| AC-9 | The script exits with code 0 on success and non-zero on failure |
| AC-10 | `--help` prints usage information and exits with code 0 |

---

## 4. Out of Scope (for now)

- Docker container deployment
- systemd service unit for the agent itself
- Automated Ollama GPU detection and configuration
- Remote Ollama server configuration
- MySQL server installation (client libraries only)
- Shodan toolkit API key setup
- MikroTik target configuration
