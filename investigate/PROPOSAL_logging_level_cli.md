# Proposal: Dynamic Logging Level via Command Line Argument

## Overview

This proposal outlines the implementation of a command-line argument to dynamically control the logging level of the agent-torvalds system. This will allow users to adjust verbosity at runtime without modifying code or configuration files.

## Problem Statement

Currently, the logging level is hardcoded or configured statically in the application. Users who want to:
- Debug issues with verbose output
- Run the system quietly in production
- Tune logging verbosity per session

must either modify source code or restart with different environment variables.

## Proposed Solution

Add a `--log-level` (or `-l`) command-line argument to `agent-torvalds.py` that accepts standard Python logging levels:
- `DEBUG` - Verbose debugging information
- `INFO` - General informational messages (default)
- `WARNING` - Warning messages only
- `ERROR` - Errors only
- `CRITICAL` - Critical errors only

### Usage Example

```bash
# Default INFO level
python agent-torvalds.py

# Debug mode for troubleshooting
python agent-torvalds.py --log-level DEBUG

# Quiet mode for production
python agent-torvalds.py --log-level ERROR
```

## Implementation Plan

### 1. Argument Parsing
- Add `--log-level` argument to the argument parser in `agent-torvalds.py`
- Validate input against allowed logging levels
- Set default to `INFO`

### 2. Logging Configuration
- Apply the selected level to all loggers in the application
- Ensure consistency across all modules and components

### 3. Testing
- Unit tests for argument parsing
- Integration tests verifying log output at different levels
- Edge case handling (invalid levels, missing arguments)

## Technical Details

### Files to Modify
- `agent-torvalds.py` - Main entry point, argument parsing
- Potentially a new logging configuration module if refactoring is needed

### Dependencies
- Uses Python's built-in `logging` module
- No external dependencies required

## Benefits
- **User-friendly**: Easy verbosity control without code changes
- **Debugging**: Quick switch to DEBUG mode for troubleshooting
- **Production-ready**: Reduce noise in production environments
- **Flexible**: Per-session control rather than global config

## Risks & Mitigation
- **Risk**: Invalid log level input
  - **Mitigation**: Input validation with helpful error messages
- **Risk**: Inconsistent logging across modules
  - **Mitigation**: Centralized logging configuration

## Timeline
- Proposal & Design: 1 day
- Implementation: 2-3 days
- Testing: 1 day
- Documentation: 1 day

## Next Steps
1. Review and approve this proposal
2. Begin implementation in `feature/logging-level-cli-argument` branch
3. Create pull request for review
