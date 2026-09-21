# Proposal: Interactive OS Package Installation for Debian/Ubuntu (APT)

## 1. Problem Statement

The Torvalds agent currently has shell execution capabilities via `agent_linux_toolkit.py`, but lacks a **structured, interactive workflow** for installing system packages when a required tool/application is missing.

**Current gaps:**
*   **No automated dependency detection:** When a command like `ffmpeg`, `node`, or `python3-pip` is not found, the agent must manually guess the package name or rely on the LLM's training data.
*   **No sudo password handling:** Installing packages requires `sudo`, which needs a password. There's no mechanism to prompt the user for credentials interactively.
*   **No feedback loop:** If a package installation fails or a command is still missing after installation, the agent has no structured way to retry or explore alternatives.
*   **No package manager abstraction:** Currently, any package management is ad-hoc shell commands. A dedicated toolkit would provide safety, validation, and logging.

**Goal:** Implement a new `agent_apt_toolkit.py` module that provides:
1.  **Package search & resolution** — Find the correct APT package for a given command/binary.
2.  **Interactive sudo password prompting** — Use console input with multiple fallback strategies for secure credential entry.
3.  **Installation workflow** — Safe, idempotent package installation with pre/post validation.
4.  **Error recovery** — Handle broken packages, missing repos, and permission issues gracefully.

---

## 2. Proposed Architecture

### 2.1. Core Components

```
┌────────────────────────────────────────────────────┐
│            Torvalds Agent (APT Toolkit)            │
│                                                    │
│  ┌──────────────┐   ┌──────────────────────────┐   │
│  │ Command      │──▶│ Package Resolver         │   │
│  │ Detection    │   │ (apt-file / dpkg)        │   │
│  └──────────────┘   └──────────┬───────────────┘   │
│                                │                   │
│              ┌─────────────────▼───────────┐       │
│              │  Installation Manager       │       │
│              │  (apt-get install -y)       │       │
│              └──────────┬──────────────────┘       │
│                         │                          │
│        ┌────────────────┼────────────────┐         │
│        ▼                ▼                ▼         │
│  ┌──────────┐   ┌──────────────┐  ┌──────────┐     │
│  │ Sudo     │   │ Validation   │  │ Logging  │     │
│  │ Handler  │   │ (which cmd)  │  │ Cache    │     │
│  └──────────┘   └──────────────┘  └──────────┘     │
└────────────────────────────────────────────────────┘
```

### 2.2. Component Details

#### 2.2.1. Package Resolver
*   **Primary method:** `apt-file search <binary_name>` to find which package provides a missing command.
*   **Fallback:** `dpkg -S /usr/bin/<binary>` for locally installed packages.
*   **Secondary fallback:** `apt-cache search <keyword>` for keyword-based package discovery.
*   **Error handling:** All methods wrapped in try/except for graceful degradation.

#### 2.2.2. Sudo Password Handler
*   **Multiple fallback strategies:** The implementation uses a 4-tier resolution order:
    1.  **Parameter:** Password provided directly as function argument
    2.  **Environment variable:** `TORVALDS_SUDO_PASSWORD` for headless/non-interactive use
    3.  **Session cache:** Previously validated password (re-validated on use)
    4.  **Console input:** Rich console-based prompting (works in agent context)
*   **Safety:** Password is never logged; session cache can be cleared explicitly.
*   **Validation:** All passwords are tested via `sudo -S -k true` before use.

#### 2.2.3. Installation Manager
*   **Idempotent:** Check if package is already installed before attempting install.
*   **Silent mode:** Use `DEBIAN_FRONTEND=noninteractive` to avoid interactive prompts.
*   **Pre-install update:** Optionally run `apt-get update` before install (configurable).
*   **Post-install validation:** Verify the binary is now available via `which`.

#### 2.2.4. Logging & Cache Integration
*   Module-level logging via Python's `logging` module.
*   Session-scoped sudo password cache for convenience.
*   Structured result dictionaries for all operations.

---

## 3. Implementation Details

### 3.1. New Module: `agent_apt_toolkit.py`

The module provides the following functions:

#### Package Resolution
| Function | Description |
|---|---|
| `find_package_for_command(command)` | Find which APT package provides a given command/binary using apt-file → dpkg → apt-cache fallback chain |
| `check_command_exists(command)` | Check if a command/binary is available in the system PATH |

#### Sudo Password Handling
| Function | Description |
|---|---|
| `prompt_sudo_password(method, password, max_attempts)` | Obtain sudo password using multiple fallback strategies (parameter → env_var → cache → console) |
| `test_sudo_password(password)` | Test if the provided sudo password is valid |
| `clear_sudo_cache()` | Clear the cached sudo password |

#### Package Installation
| Function | Description |
|---|---|
| `install_package(package_name, update_first, sudo_password)` | Install an APT package with optional pre-update and sudo handling |
| `install_multiple_packages(package_names, update_first, sudo_password)` | Install multiple APT packages sequentially |
| `interactive_install_missing_command(command, ...)` | End-to-end workflow: detect missing command, resolve package, install it |

#### Tool Registry
| Function | Description |
|---|---|
| `get_all_tools()` | Return all APT package tools as FunctionTool objects for on-demand loading |

### 3.2. Password Resolution Strategies

The `prompt_sudo_password()` function supports these methods:

| Method | Description |
|---|---|
| `auto` (default) | Try all strategies in order: parameter → env_var → cache → console |
| `parameter` | Use password provided as function argument |
| `env_var` | Read from `TORVALDS_SUDO_PASSWORD` environment variable |
| `cache` | Use session-scoped cached password (re-validated) |
| `console` | Prompt via rich console input (works in agent context) |

### 3.3. Integration with Existing Toolkits

#### Updated `agent-torvalds.py`
```python
from agent_apt_toolkit import get_all_tools as get_apt_tools

# In create_agent() full mode:
all_tools = (
    get_math_tools()
    + get_git_tools()
    + get_os_tools()
    + get_db_tools()
    + get_linux_tools()
    + get_apt_tools()  # <-- APT tools added
    + get_cache_tools()
)
```

#### Updated `agent_tool_retriever.py`
```python
def build_tool_retriever(
    ...
    include_apt_tools: bool = True,  # New parameter
    ...
) -> tuple:
    if include_apt_tools:
        from agent_apt_toolkit import get_all_tools as _get_apt
        all_tools.extend(_get_apt())
```

---

## 4. Interactive Workflow Example

### Scenario: User asks to run `ffmpeg` but it's not installed

```
User: Convert this video to mp3 using ffmpeg

Agent (Internal Process):
1.  Check if ffmpeg exists → check_command_exists("ffmpeg") → False
2.  Resolve package → find_package_for_command("ffmpeg") → {'package_name': 'ffmpeg', ...}
3.  Prompt password → prompt_sudo_password(method="auto") → [Console prompt appears]
4.  Install package → install_package("ffmpeg") → apt-get install -y ffmpeg
5.  Validate → check_command_exists("ffmpeg") → True, path=/usr/bin/ffmpeg
6.  Execute original task → execute_shell_command("ffmpeg -i video.mp4 audio.mp3")

Agent Response:
"Installed ffmpeg via APT. Converting video to mp3..."
[Conversion output]
"Done! Audio saved to audio.mp3"
```

### Console Password Prompt

```
🔑 Enter sudo password (attempt 1/3):
(password will be hidden as you type)
Password: ******
✓ Password accepted!
```

---

## 5. Configuration Options

Add environment variables for tuning:

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_SUDO_PASSWORD` | `` | Sudo password for headless mode |
| `TORVALDS_APT_UPDATE_BEFORE_INSTALL` | `true` | Run `apt-get update` before each install |
| `TORVALDS_APT_TIMEOUT` | `180` | Timeout in seconds for apt operations |
| `TORVALDS_APT_DIALOG_METHOD` | `auto` | Password method: `auto`, `console`, `env_var`, `parameter`, `cache` |
| `TORVALDS_APT_CONFIRM_INSTALL` | `false` | Ask user to confirm before installing |
| `TORVALDS_APT_CACHE_TTL` | `3600` | TTL in seconds for package resolution cache |

---

## 6. Safety Considerations

### 6.1. Package Installation Safety
*   **Non-interactive mode:** Always use `DEBIAN_FRONTEND=noninteractive` to avoid hanging on dialogs.
*   **Quiet mode:** Use `-qq` flag to minimize output.
*   **Error handling:** Catch and log all apt errors with actionable messages.
*   **Timeout protection:** All subprocess calls have configured timeouts.

### 6.2. Sudo Password Safety
*   **No caching in plain text:** Password is never stored in the agent cache or logged.
*   **Session-scoped cache:** Password cached in module-level variable, clearable via `clear_sudo_cache()`.
*   **Validation:** All passwords tested before use via `sudo -S -k true`.
*   **Environment variable:** Only use `TORVALDS_SUDO_PASSWORD` if explicitly set.

### 6.3. System Integrity
*   **Idempotent operations:** Check before installing to avoid redundant operations.
*   **Post-install validation:** Verify command availability after installation.
*   **Structured results:** All operations return detailed status dictionaries.

---

## 7. Implementation Plan

### Phase 1: Core Resolution & Installation ✅
- [x] Create `agent_apt_toolkit.py` with `find_package_for_command`
- [x] Implement `check_command_exists` and `install_package`
- [x] Add basic sudo password handling via environment variable
- [x] Register tools in `agent_tool_retriever.py`

### Phase 2: Interactive Password Handling ✅
- [x] Implement `prompt_sudo_password` with multiple fallback strategies
- [x] Add console input support (works in agent context)
- [x] Session-scoped password caching with validation
- [x] Password cache clearing functionality

### Phase 3: Integration & Workflow ✅
- [x] Wire APT toolkit into `agent-torvalds.py`
- [x] Implement `interactive_install_missing_command` end-to-end workflow
- [x] Add comprehensive test suite

### Phase 4: Safety & Polish (Future)
- [ ] Add dry-run mode and package validation
- [ ] Implement resolution caching with TTL
- [ ] Add configuration via environment variables
- [ ] Add installation logging to agent cache

---

## 8. Risks & Mitigation

| Risk | Mitigation |
|---|---|
| **Broken package dependencies** | Use `apt-get install -f` for auto-fix; log errors for manual review |
| **Network failures during apt** | Configurable timeout; error handling with actionable messages |
| **Wrong package resolved** | Show candidates list; allow user to select from alternatives |
| **Sudo password exposure** | Never log password; session cache clearable; no persistent storage |
| **APT lock conflicts** | Detect `dpkg lock` errors; wait or suggest manual intervention |
| **Insufficient disk space** | Pre-check disk space; warn before large installations |

---

## 9. Future Enhancements

*   **pip/npm/conda support:** Extend to Python, Node.js, and Conda package managers.
*   **Snap/Flatpak support:** Install snap/flatpak packages when APT fails.
*   **Dependency graph visualization:** Show what packages will be installed/removed.
*   **Rollback capability:** Track installed packages per session for easy uninstall.
*   **Package pinning:** Support version pinning for reproducible environments.
*   **Multi-OS support:** Abstract to support `yum` (RHEL), `pacman` (Arch), `brew` (macOS).

---

## 10. Dependencies

### System Dependencies
*   **apt-file:** `sudo apt-get install apt-file` (optional, recommended for best resolution)
*   **whiptail/dialog:** Available on Ubuntu/Debian (not used in current implementation)
*   **sudo:** Required for package installation

### Python Dependencies
*   **rich:** For console-based password prompting (already in requirements.txt)
*   **No new Python dependencies required**

---

## 11. Conclusion

Adding interactive APT package installation is a **high-value capability** that transforms the agent from a passive tool executor to an **autonomous system administrator**. The implementation is:

1.  **Safe:** Non-interactive mode, password protection, validation checks
2.  **Interactive:** Console prompts for credentials with multiple fallback strategies
3.  **Idempotent:** Checks before installing, validates after
4.  **Integrated:** Works seamlessly with existing toolkits and retriever
5.  **Extensible:** Foundation for multi-OS and multi-package-manager support

**Key Benefits:**
1.  **Self-healing:** Agent can automatically resolve missing dependencies
2.  **User-friendly:** Interactive prompts for credentials instead of manual sudo
3.  **Transparent:** Full logging of installation attempts and results
4.  **Zero breaking changes:** Fully additive feature

---

*Document prepared by Torvalds AI Agent*
*Date: 2025-01*
*Repository: git@github.com:KostiantynBushko/agent-torvalds.git*
*Target OS: Debian/Ubuntu (APT package manager)*
