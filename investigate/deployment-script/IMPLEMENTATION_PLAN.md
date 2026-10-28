# Agent Torvalds Deployment Script — Implementation Plan

**Date**: 2025-01-13  
**Status**: Planned  
**Based on**: Investigation Report + Requirements Specification

---

## Phase 1: Script Skeleton

Create the basic shell script structure with:

- Shebang, strict mode (`set -euo pipefail`)
- Trap handlers (ERR, EXIT)
- CLI argument parsing (getopt)
- Logging framework (log_info, log_warn, log_error functions)
- Banner and help text
- Section stubs (empty functions for each deployment phase)

**Deliverable**: `deploy-torvalds.sh` with working `--help` and `--version`

---

## Phase 2: System Detection & Prerequisites

Implement:

- OS/distro detection (parse `/etc/os-release`)
- Package manager selection (`apt` vs `dnf`)
- Python version check (`python3 --version`)
- Git availability check
- Network connectivity check (`curl` or `ping`)
- Disk space estimation (Ollama models can be 16+ GB)

**Deliverable**: Prerequisites check that passes or fails with clear messages

---

## Phase 3: System Package Installation

Implement:

- `install_system_packages()` function
- Debian/Ubuntu package list: `python3-venv`, `python3-pip`, `git`, `build-essential`, `cmake`, `libpq-dev`, `whiptail`
- RHEL/Fedora package list: `python3`, `python3-pip`, `git`, `gcc`, `gcc-c++`, `cmake`, `libpq-devel`, `newt` (for dialog)
- Idempotency: check if package is installed before installing
- `sudo` password caching (`sudo -v`)

**Deliverable**: System packages installed or confirmed present

---

## Phase 4: PostgreSQL Setup

Implement:

- `install_postgres()` function (conditional on `--with-postgres`)
- Install `postgresql` and `postgresql-contrib` packages
- Start and enable `postgresql` systemd service
- Execute `setup_postgres_db.sql` with custom parameters via `psql -v`
- Verify connectivity with `psql -c "SELECT 1"`
- Graceful degradation if PostgreSQL fails

**Deliverable**: PostgreSQL running with application role, database, and extensions

---

## Phase 5: Python Virtual Environment

Implement:

- `setup_python_env()` function
- Create `.venv` with `python3 -m venv`
- Upgrade pip, setuptools, wheel
- Install `requirements.txt` with `pip install`
- Handle compilation failures for `llama-cpp-python`
- Skip if `--skip-pip`

**Deliverable**: Working Python virtual environment with all dependencies

---

## Phase 6: Ollama Setup

Implement:

- `setup_ollama()` function (conditional on `--skip-ollama`)
- Download and run Ollama install script
- Start and enable `ollama` systemd service
- Wait for server to be ready (poll `http://localhost:11434/api/version`)
- Pull chat model and embedding model
- Verify models with `ollama list`
- Handle download failures with retry logic

**Deliverable**: Ollama running with required models loaded

---

## Phase 7: Configuration Bootstrap

Implement:

- `bootstrap_config()` function
- Generate `.env` file with all `TORVALDS_*` variables
- Copy example config files if targets don't exist
- Set file permissions on credential files
- Prompt for passwords in interactive mode

**Deliverable**: Configuration files in place with correct permissions

---

## Phase 8: Verification & Summary

Implement:

- `verify_deployment()` function
- Python smoke test (import key modules)
- Ollama connectivity test
- PostgreSQL connectivity test (if configured)
- Deployment summary table
- Exit code logic

**Deliverable**: Verification report and appropriate exit code

---

## Phase 9: Testing

Test scenarios:

| Test | Description |
|---|---|
| T-1 | Fresh Ubuntu 24.04 VM, full deployment |
| T-2 | Re-run on already deployed system (idempotency) |
| T-3 | `--non-interactive` mode |
| T-4 | `--skip-ollama` mode |
| T-5 | `--skip-pip` mode |
| T-6 | Without `--with-postgres` |
| T-7 | With `--with-postgres` |
| T-8 | Alternative model via `--model` |
| T-9 | `--help` output |
| T-10 | Failure scenarios (no network, no disk space) |

---

## File Structure

```
self-development/investigate/deployment-script/
├── INVESTIGATION_REPORT.md          # This analysis
├── REQUIREMENTS.md                  # Functional & non-functional requirements
├── IMPLEMENTATION_PLAN.md           # This document
├── deploy-torvalds.sh               # The deployment script (to be created)
├── deploy-torvalds.sh.example.env   # Example .env template
└── tests/                           # Test scripts (future)
    └── test-deploy-idempotency.sh
```

---

## Timeline Estimate

| Phase | Estimated Effort |
|---|---|
| Phase 1: Skeleton | 1 hour |
| Phase 2: Prerequisites | 1 hour |
| Phase 3: System packages | 2 hours |
| Phase 4: PostgreSQL | 2 hours |
| Phase 5: Python venv | 1 hour |
| Phase 6: Ollama | 2 hours |
| Phase 7: Configuration | 1 hour |
| Phase 8: Verification | 1 hour |
| Phase 9: Testing | 3 hours |
| **Total** | **~14 hours** |
