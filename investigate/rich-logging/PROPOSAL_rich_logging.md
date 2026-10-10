# Proposal: Rich Logging Integration with `RichHandler`

## 1. Overview

This proposal outlines the implementation plan to modernize the logging output of the **Torvalds AI Agent** by integrating `rich.logging.RichHandler`. This upgrade provides visual log level badges, automatic highlighting of numbers/strings/file paths, clickable source file links, and formatted exception tracebacks while preserving stream separation to `stderr`.

---

## 2. Problem Statement

1. **Monochrome Output**: The current `logging.StreamHandler(sys.stderr)` produces uncolored plain text that blends into the background, making it hard to spot `WARNING` and `ERROR` events during agent execution.
2. **Dense Exception Dumps**: Unhandled exceptions and error logs output raw Python tracebacks that span dozens of third-party internal frames (such as `llama_index` workflow dispatchers), adding significant cognitive overhead during debugging.
3. **Inconsistent Aesthetics**: Torvalds already uses `rich` for Markdown rendering, tables, and spinners, but internal diagnostic logs look dated and disconnected from the rest of the UI.

---

## 3. Proposed Solution

Adopt `rich.logging.RichHandler` within the centralized `configure_logging()` function in `agent-torvalds.py` with:
- **Dedicated Stderr Console**: Prevents log records from corrupting stdout prompts, Markdown answers, and spinners.
- **Traceback Enhancement & Frame Suppression**: Enable `rich_tracebacks=True` with frame suppression for `llama_index` and `asyncio`.
- **Toggle Flags**: Allow fallback to traditional plain text logging via `--no-rich-log` CLI argument or `TORVALDS_RICH_LOGGING=false` environment variable.

### 3.1 Example Configuration

```python
import sys
import logging
from rich.console import Console
from rich.logging import RichHandler

# Dedicated stderr console ensures logs do not mix with stdout REPL
log_console = Console(stderr=True)

def configure_logging(
    level_name: str = "INFO",
    use_rich: bool = True,
    rich_tracebacks: bool = True,
) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)

    if use_rich:
        suppress_modules = []
        try:
            import llama_index
            suppress_modules.append(llama_index)
        except ImportError:
            pass

        handler = RichHandler(
            console=log_console,
            show_time=True,
            show_level=True,
            show_path=True,
            enable_link_path=True,
            rich_tracebacks=rich_tracebacks,
            tracebacks_suppress=suppress_modules,
            markup=False,
            log_time_format="[%X]",
        )
        log_format = "%(name)s: %(message)s"
    else:
        handler = logging.StreamHandler(sys.stderr)
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[handler],
        force=True,
    )
```

---

## 4. CLI and Environment Interface

### 4.1 CLI Arguments in `agent-torvalds.py`

```python
parser.add_argument(
    "--log-level",
    type=str,
    choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    default="INFO",
    help="Set logging verbosity level",
)
parser.add_argument(
    "--no-rich-log",
    action="store_true",
    help="Disable RichHandler and use plain text StreamHandler for logging",
)
parser.add_argument(
    "--no-rich-tracebacks",
    action="store_true",
    help="Disable rich exception traceback formatting",
)
```

### 4.2 Environment Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `TORVALDS_LOG_LEVEL` | string | `INFO` | Default logging verbosity level |
| `TORVALDS_RICH_LOGGING` | boolean | `true` | Enable/disable RichHandler |
| `TORVALDS_LOG_TRACEBACKS` | boolean | `true` | Enable/disable Rich formatted tracebacks |

---

## 5. Implementation Plan

### Step 1: Update `configure_logging()` in `agent-torvalds.py`
- Import `RichHandler` from `rich.logging`.
- Instantiate `log_console = Console(stderr=True)`.
- Update `configure_logging()` to construct `RichHandler` when `use_rich=True`.
- Add frame suppression for `llama_index` and `asyncio`.

### Step 2: Add CLI Arguments and Wiring
- Add `--no-rich-log` and `--no-rich-tracebacks` flags to `parse_args()`.
- Pass these options to `configure_logging()` inside `main()`.

### Step 3: Update Test Suite in `tests/test_logging_cli.py`
- Update `test_configure_logging_output_to_stderr` to support both `RichHandler` (verifying `h.console.file is sys.stderr`) and `StreamHandler` (`h.stream is sys.stderr`).
- Add tests for `use_rich=True` vs `use_rich=False`.
- Add test verifying that invalid log levels still raise appropriate errors.

### Step 4: Documentation Updates
- Update `README.md` under **Logging Configuration** documenting the new options.
- Update `CHANGELOG.md` under `[Unreleased]`.

---

## 6. Risk Assessment & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Log records collision with spinner** | Low | Rich console manages terminal cursor cleanly; `log_console` targets `stderr` while spinner targets `stdout`. |
| **Square brackets in log strings interpreted as tags** | Medium | Set `markup=False` on `RichHandler` constructor so raw brackets are not parsed as BBCode tags. |
| **CI / Non-TTY environments** | Low | Rich automatically detects non-interactive terminals / pipes and strips ANSI color codes. In addition, `--no-rich-log` flag provides explicit fallback. |
| **Test regressions** | Low | Existing tests in `tests/test_logging_cli.py` will be adapted to recognize `RichHandler`. |

---

## 7. Compatibility Assurance

- **Zero changes to toolkit code**: No edits required in `agent_git_toolkit.py`, `agent_os_toolkit.py`, `agent_apt_toolkit.py`, etc.
- **100% backward compatible**: Existing standard `logging.getLogger(__name__)` calls will work immediately without modification.
- **Opt-out available**: Any automation or workflow expecting plain text can pass `--no-rich-log` or set `TORVALDS_RICH_LOGGING=false`.
