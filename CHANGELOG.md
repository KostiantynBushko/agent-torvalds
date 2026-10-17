# Changelog

## 2026-09-10

- [feature] add Linux shell command toolkit and enable chat memory (2026-09-10)

All notable changes to this project will be documented in this file.

## [Unreleased]

### Features
- Added comprehensive Git toolkit capabilities for repository management
- Implemented system operations toolkit with full OS functionality access
- Integrated database toolkit for PostgreSQL and MySQL query execution
- Enhanced mathematical toolkit with basic arithmetic operations (add, multiply, divide)
- **NEW: `load_project()` unified project loading API** — transparently handles both existing workspaces (loads from `.agentworkspace.json`) and new project discovery (creates workspace, scans, detects, and registers)

### Details: `load_project()` Feature
- **Unified Entry Point**: Single method to load projects regardless of whether a workspace already exists
- **Two Loading Modes**:
  - `existing_workspace`: Loads project from existing `.agentworkspace.json` config
  - `new_workspace`: Creates workspace, scans directory, auto-detects type, and registers project
- **Smart Project Resolution**: Supports lookup by `project_name` or automatic path matching
- **Standardized Results**: Returns consistent dictionary structure with `status`, `method`, `workspace_path`, and full `project` metadata
- **Fallback Handling**: Gracefully falls back to first project when no exact path match is found in existing workspaces
- **Force Mode**: Supports `force=True` to register projects even when type detection is ambiguous

## [0.1.0] - 2026-09-09

### Features
- Integrated comprehensive Git and OS toolkits into Torvald agent, enabling full interaction with Git repositories and system operations
- Added database toolkit capabilities for executing SQL queries on PostgreSQL and MySQL databases
- Enhanced mathematical toolkit with addition, multiplication, and division operations
- Implemented system operations toolkit with full OS functionality access including file management and process control

### Fixes
- Updated agent-torvalds.py with recent changes

## [0.0.1] - 2026-09-08

### Features
- Initial commit: Torvalds Functional Agent
- Initial commit
