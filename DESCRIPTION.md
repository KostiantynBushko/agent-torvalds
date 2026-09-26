# Self-Development Clone

This is the self-development working clone of the **Torvalds AI Agent Toolkit** repository.

## Purpose

Per the self-development rules:
- All source code updates and development work must be performed in this directory: `${PWD}/self-development`
- The main repository (`agent-torvalds`) must **not** be modified directly for development tasks
- This clone serves as the isolated workspace for experimental features, bug fixes, and enhancements

## Current Branch

`feature/logging-level-cli-argument` — Adding a `--log-level` CLI argument for configurable logging verbosity.

## Investigation Artifacts

- `investigate/investigation_logging_level_cli.md` — Investigation notes on implementing logging level via CLI
- `investigate/PROPOSAL_logging_level_cli.md` — Proposal document for the feature
- `tests/test_logging_cli.py` — Test suite for the new CLI argument

## Modified Files

| File | Change |
|------|--------|
| `agent-torvalds.py` | Added `--log-level` CLI argument parsing |
| `agent_git_toolkit.py` | Logging level integration |
| `agent_linux_toolkit.py` | Logging level integration |
| `agent_stats_handler.py` | Logging level integration |
| `agent_windows_toolkit.py` | Logging level integration |

## Workflow

1. Develop and test changes here in `self-development/`
2. Verify with tests in `tests/`
3. Once validated, cherry-pick or merge into the main repository

---
*Maintained automatically by Torvalds AI Agent*
