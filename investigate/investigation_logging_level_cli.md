# Investigation: Dynamic Logging Level via CLI Argument

**Date**: 2025-01-15  
**Branch**: `feature/logging-level-cli-argument`  
**Status**: Investigation complete — ready for implementation  

---

## 1. Objective

Enable users to control the logging verbosity at runtime via a `--log-level` CLI argument without modifying source code or environment variables.

---

## 2. Current State Analysis

### 2.1 Logging Configuration Points

The codebase currently has **fragmented logging configuration** spread across multiple modules:

| File | Line | Pattern | Issue |
|------|------|---------|-------|
| `agent-torvalds.py` | 124 | `logging.basicConfig(level=logging.INFO)` | Hardcoded default |
| `agent_linux_toolkit.py` | 21 | `logging.basicConfig(level=logging.INFO)` | Duplicate `basicConfig` call |
| `agent_windows_toolkit.py` | 22 | `logging.basicConfig(level=logging.INFO)` | Duplicate `basicConfig` call |
| `agent_git_toolkit.py` | 18-19 | `logger = logging.getLogger(__name__)` then `logger.setLevel(logging.DEBUG)` | Hardcoded DEBUG override — ignores root config |

**Problem**: `logging.basicConfig()` is only effective the **first time** it's called. Subsequent calls are silently ignored. The current code calls it 3 times across different modules, but only the first import wins. This creates unpredictable logging behavior depending on import order.

### 2.2 Logger Usage Patterns

Most modules correctly use the module-level logger pattern:
```python
import logging
logger = logging.getLogger(__name__)
```

Modules using this pattern:
- `agent_apt_toolkit.py` — uses `logger.info()`, `logger.debug()`, `logger.warning()`, `logger.error()`
- `agent_chat_memory.py` — uses `logger.debug()`, `logger.info()`, `logger.warning()`
- `agent_db_toolkit.py` — uses `logger.info()`
- `agent_git_toolkit.py` — uses `logger.info()` (but overrides with `setLevel(DEBUG)`)
- `agent_github_toolkit.py` — logger defined but minimal usage
- `agent_linux_toolkit.py` — logger defined
- `agent_math_toolkit.py` — logger defined
- `agent_os_toolkit.py` — logger defined
- `agent_windows_toolkit.py` — logger defined
- `components/whiptail_password.py` — logger defined

### 2.3 CLI Argument Parsing

Current `parse_args()` in `agent-torvalds.py` (lines 206-233):

```python
def parse_args():
    parser = argparse.ArgumentParser(description="Torvalds AI Agent")
    parser.add_argument("--full", action="store_true", ...)
    parser.add_argument("--top-k", type=int, default=SIMILARITY_TOP_K, ...)
    parser.add_argument("--no-stats", action="store_true", ...)
    parser.add_argument("--no-events", action="store_true", ...)
    parser.add_argument("--verbose-events", action="store_true", ...)
    return parser.parse_args()
```

**No `--log-level` argument exists yet.**

### 2.4 Existing Test Coverage

- No tests for logging configuration
- No tests for CLI argument parsing
- Existing tests focus on toolkit functionality (git, apt, math, OS, cache, stats)

---

## 3. Issues Identified

### 3.1 Critical Issues

1. **Duplicate `basicConfig` calls** — `agent_linux_toolkit.py` and `agent_windows_toolkit.py` call `logging.basicConfig()` redundantly. These calls are no-ops after the first one.

2. **Hardcoded level override in git toolkit** — `agent_git_toolkit.py` line 19:
   ```python
   logger.setLevel(logging.DEBUG)
   ```
   This forces DEBUG output for git operations regardless of user preference.

### 3.2 Design Issues

3. **No centralized logging configuration** — Logging setup is scattered across modules. There's no single place to configure formatters, handlers, or levels.

4. **No validation of log levels** — If we add `--log-level`, invalid input would cause a runtime error.

---

## 4. Proposed Implementation Plan

### 4.1 Phase 1: Add CLI Argument (Low Risk)

**File**: `agent-torvalds.py`

```python
# Add to parse_args():
parser.add_argument(
    "--log-level",
    type=str,
    choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    default="INFO",
    help="Set logging level (default: INFO)",
)
```

Then in `main()`, before any toolkit imports are used:
```python
args = parse_args()
logging.basicConfig(level=getattr(logging, args.log_level))
```

### 4.2 Phase 2: Clean Up Duplicate Configs (Medium Risk)

Remove redundant `logging.basicConfig()` calls from:
- `agent_linux_toolkit.py` line 21
- `agent_windows_toolkit.py` line 22

Remove hardcoded level override from:
- `agent_git_toolkit.py` line 19 (`logger.setLevel(logging.DEBUG)`)

### 4.3 Phase 3: Centralized Logging Config (Optional Enhancement)

Create a `configure_logging()` helper function in `agent-torvalds.py`:

```python
def configure_logging(level_name: str = "INFO"):
    """Centralized logging configuration."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
```

This provides:
- Timestamps in log output
- Module name identification
- Consistent formatting across all modules
- Output to stderr (best practice — keeps logs separate from stdout)

### 4.4 Phase 4: Testing

Create `tests/test_logging_cli.py`:

| Test | Description |
|------|-------------|
| `test_log_level_default` | Default level is INFO |
| `test_log_level_debug` | `--log-level DEBUG` sets DEBUG |
| `test_log_level_invalid` | Invalid level raises SystemExit |
| `test_log_level_applied` | Verifying actual logger level after config |
| `test_all_modules_respect_level` | Confirm no module overrides the level |

---

## 5. Files to Modify

| File | Change | Risk |
|------|--------|------|
| `agent-torvalds.py` | Add `--log-level` arg, call `configure_logging()` before toolkit use | Low |
| `agent_linux_toolkit.py` | Remove `logging.basicConfig()` call | Low |
| `agent_windows_toolkit.py` | Remove `logging.basicConfig()` call | Low |
| `agent_git_toolkit.py` | Remove `logger.setLevel(logging.DEBUG)` | Low |
| `tests/test_logging_cli.py` | New test file | N/A |

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Removing `basicConfig` from toolkits breaks something | Low — `basicConfig` is already a no-op after first call | Test in both Linux and Windows environments |
| Removing `setLevel(DEBUG)` from git toolkit hides debug info | Medium — users relied on verbose git logging | Users can now use `--log-level DEBUG` explicitly |
| New argument conflicts with existing args | None — `--log-level` is a new, unique flag | Verified no collision |
| Logging format change breaks parsing | Low — no code currently parses log output | Keep format configurable |

---

## 7. Verification Checklist

- [ ] `--log-level` argument parses correctly for all 5 levels
- [ ] Default is INFO when argument is omitted
- [ ] Invalid log level produces a helpful error message
- [ ] All toolkit loggers respect the configured level
- [ ] No duplicate `basicConfig` calls remain
- [ ] No hardcoded `setLevel` overrides remain
- [ ] Tests pass on both Linux and Windows
- [ ] Existing functionality unchanged (smoke test)

---

## 8. Recommended Implementation Order

1. **Add `--log-level` argument** to `parse_args()`
2. **Create `configure_logging()` helper** in `agent-torvalds.py`
3. **Call `configure_logging(args.log_level)`** at the start of `main()`
4. **Remove redundant `basicConfig`** from toolkits
5. **Remove hardcoded `setLevel`** from git toolkit
6. **Write tests** for the new CLI argument
7. **Smoke test** the full agent workflow at each log level

---

## 9. Estimated Effort

| Task | Estimated Time |
|------|---------------|
| CLI argument + logging config | 30 min |
| Clean up duplicate configs | 15 min |
| Write tests | 45 min |
| Smoke testing | 15 min |
| **Total** | **~2 hours** |

---

*Investigation complete. Ready to proceed with implementation.*
