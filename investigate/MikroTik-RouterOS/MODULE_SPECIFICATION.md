# MODULE SPECIFICATION: MikroTik RouterOS Toolkit

**Date:** 2026-10-21 (revised for the `toolkits/` layout requirement)
**Repository:** agent-torvalds
**Branch:** `feature/mikrotik-routeros-toolkit` (in the `self-development` clone)
**Status:** **Authoritative** — this document defines the module layout and the
implementation contract. Where it conflicts with `IMPLEMENTATION_PLAN.md` or
`PROPOSAL_mikrotik_toolkit.md`, **this document wins**.
**Related:** [INVESTIGATION_REPORT.md](INVESTIGATION_REPORT.md) ·
[PROPOSAL_mikrotik_toolkit.md](PROPOSAL_mikrotik_toolkit.md) ·
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

**Automated verification of this document:**

```bash
self-development/.venv/bin/python \
    self-development/investigate/MikroTik-RouterOS/verify_layout_contract.py
self-development/.venv/bin/python \
    self-development/investigate/MikroTik-RouterOS/verify_test_contract.py
```

The first script re-proves every row of the §3.2 behaviour matrix and the
§4.2 binding rules. The second script re-proves the §3.4 pytest contract.

- **FAIL** = the repository violates a contract this document states.
  The document is right; the implementation is wrong.
- **PENDING** = a requirement that Phase 1 has not implemented yet (the
  `pytest.ini` changes). Not a violation, but it must not stay pending.

`verify_layout_contract.py` must report **20/20 passed**. For
`verify_test_contract.py`, the target is **12/12 passed** once Phase 1 lands
(10 pass + 2 pending before that).

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Directory Layout](#2-directory-layout)
3. [The Hyphen Problem (and the alias)](#3-the-hyphen-problem-and-the-alias)
4. [Module Contract](#4-module-contract)
5. [Per-Module Specifications](#5-per-module-specifications)
6. [Agent Adapter](#6-agent-adapter)
7. [Integration](#7-integration)
8. [Testing](#8-testing)
9. [Definition of Done](#9-definition-of-done)
10. [Open Questions](#10-open-questions)

---

## 1. Purpose

This document is the **single source of truth** for *how* the MikroTik RouterOS
module must be implemented and *where* it must live.

It exists because the earlier documentation (investigation, proposal, plan) was
written before the required directory layout was decided, and it therefore
referenced a lowercase `toolkits/mikrotik/` package. The requirement is now
fixed:

> **In the root folder create a `toolkits/` directory, and under it a new
> Python module called `MikroTik-RouterOS`. This is the home directory for the
> new toolkit.**

Everything in this document follows from that decision, including the
non-obvious Python packaging consequences documented in §3.

---

## 2. Directory Layout

### 2.1 The required tree

```
agent-torvalds/                        # repository root
│
├── toolkits/                          # ← NEW: toolkit home directory
│   ├── __init__.py                    #    package root + import alias shim (§3)
│   └── MikroTik-RouterOS/             # ← NEW: the MikroTik toolkit home directory
│       ├── __init__.py                #    public API surface
│       ├── config.py                  #    MikroTikTarget, TargetRegistry, load_targets
│       ├── models.py                  #    CommandResult, RouterIdentity, CommandCategory
│       ├── exceptions.py              #    typed error hierarchy
│       ├── parser.py                  #    print / detail / identity parsing
│       ├── session.py                 #    RouterOSSession (exec + session transports)
│       ├── safety.py                  #    risk classifier + confirmation policy
│       ├── py.typed                   #    PEP 561 marker
│       ├── agent_mikrotik_toolkit.py  #    LlamaIndex adapter — a submodule
│       │                              #    of this package, and the only
│       │                              #    module here that knows about it
│       └── tests/                     #    module-local tests (optional)
│           │                          # NOTE: deliberately NO __init__.py (§3.4)
│           ├── test_config.py
│           ├── test_models.py
│           ├── test_parser.py
│           ├── test_session.py
│           ├── test_safety.py
│           └── test_package_layout.py
│
├── tests/                             # project-level integration tests
│   ├── test_mikrotik_toolkit.py       #    tool-level tests with a mocked transport
│   └── test_mikrotik_integration.py   #    opt-in, real router
│
├── mikrotik_targets.yaml.example      # annotated example config (no secrets)
├── requirements.txt                   # + optional asyncssh / pydantic / routeros_api
├── pytest.ini                         # + addopts=--import-mode=importlib
│                                      # + toolkits/MikroTik-RouterOS/tests in testpaths
│                                      # + integration marker
├── docs/mikrotik-toolkit.md           # operator documentation
├── README.md                          # + "Network devices" section
└── CHANGELOG.md                       # + entry
```

### 2.2 Naming rules (binding)

| Rule | Value | Rationale |
|---|---|---|
| Toolkit home directory | `toolkits/MikroTik-RouterOS/` | Fixed by requirement. **Exact case.** |
| Package root | `toolkits/` | Fixed by requirement. |
| Python module files | `snake_case.py` | PEP 8. |
| Adapter | `toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py` | Lives **inside** the toolkit package, next to the code it adapts. The package directory name contains a hyphen, so the adapter is reached through the alias (§3). |
| Import alias | `toolkits.mikrotik_routeros` | Valid identifier for the hyphenated package (§3). |
| Config file | `mikrotik_targets.yaml` | Root-level, next to `db_toolkit_config.yaml`. |

> ⚠️ **Case sensitivity.** `MikroTik-RouterOS` is spelled exactly like this —
> capital `M`, capital `T`, capital `R`, capital `O`, capital `S`. A Linux
> checkout of `MikroTik-routeros` will **not** be importable and the failure
> mode is a confusing `ModuleNotFoundError`. Linux/macOS are case-sensitive by
> default; Windows is not. Always use the exact spelling.

---

## 3. The Hyphen Problem (and the alias)

### 3.1 The constraint

`MikroTik-RouterOS` contains a hyphen. A hyphen is **not** a valid character in
a Python identifier, so the package can never be imported with an `import`
statement:

```python
from toolkits.MikroTik-RouterOS import MikroTikTarget
#                                    ^ SyntaxError: invalid syntax
```

This is not a style preference — it is a hard language rule. The `import`
statement's grammar only accepts dotted *identifiers*.

### 3.2 What actually works (empirically verified)

All rows below were executed against **Python 3.12.3 / pytest 9.1.1**, the
versions used by this project. The check is automated and re-runnable:

```bash
self-development/.venv/bin/python \
    self-development/investigate/MikroTik-RouterOS/verify_layout_contract.py
```

| # | Approach | Result |
|---|---|---|
| 1 | `from toolkits.MikroTik-RouterOS import X` | ❌ `SyntaxError: invalid syntax` |
| 2 | `import toolkits.MikroTik-RouterOS` | ❌ `SyntaxError: invalid syntax` |
| 3 | `importlib.import_module("toolkits.MikroTik-RouterOS")` | ✅ works |
| 4 | `importlib.import_module(...)` + **relative** imports inside the package | ✅ works |
| 5 | `importlib.import_module(...)` + **absolute** imports inside the package | ❌ `SyntaxError` — the hyphen is still in the dotted path |
| 6 | Test file at repo root `tests/`, using the alias | ✅ passes (default pytest mode) |
| 7 | Test file **inside** `toolkits/MikroTik-RouterOS/tests/`, default pytest mode, relative import | ❌ `ImportError` (see §3.4) |
| 8 | Test file **inside** `toolkits/MikroTik-RouterOS/tests/`, `--import-mode=importlib`, relative import | ✅ passes |
| 9 | `toolkits/` **without** `__init__.py` (namespace package) | ✅ works |
| 10 | `toolkits/__init__.py` that registers a `sys.modules` alias | ✅ works, and plain `import` statements work too |
| 11 | The alias object is the *same* object as the real package (`is` holds) | ✅ one instance in memory |
| 12 | `import toolkits` when the package raises on import | ✅ still succeeds (alias simply absent) |

**Row 5 is the trap.** Inside the package you might instinctively write
`from toolkits.MikroTik-RouterOS.config import MikroTikTarget`. That is a
`SyntaxError` too, because the dotted path still contains the hyphen. **Use
relative imports** (`from .config import MikroTikTarget`) — they are the only
form that is always valid.

**Row 7 is the second trap**, but the cause is subtler than "pytest cannot
handle the hyphen". See §3.4 for the exact mechanism and the two-part fix.

### 3.3 The resolution: a `sys.modules` alias

`toolkits/__init__.py` registers a **valid-identifier alias** that points at the
very same package object. This is the sanctioned import path for all consumers:

```python
from toolkits.mikrotik_routeros import MikroTikTarget       # ✅
import toolkits.mikrotik_routeros as mikrotik_routeros       # ✅
```

The shim (already committed in `toolkits/__init__.py`):

```python
import importlib
import sys

_MIKROTIK_PACKAGE = "toolkits.MikroTik-RouterOS"
_MIKROTIK_ALIAS = __name__ + ".mikrotik_routeros"

try:
    _mikrotik = importlib.import_module(_MIKROTIK_PACKAGE)
except Exception:  # noqa: BLE001 - optional toolkit; never break `import toolkits`
    _mikrotik = None
else:
    sys.modules[_MIKROTIK_ALIAS] = _mikrotik
    mikrotik_routeros = _mikrotik
```

Requirements on the shim:

- The `try/except` must catch **`Exception`**, not just `ImportError`. A missing
  optional dependency (`asyncssh`, `pydantic`) can surface as a
  `ModuleNotFoundError` (a subclass of `ImportError`, so that is covered) but
  a broken submodule can raise any exception at import time. The toolkit must
  **never** break `import toolkits`.
- The alias is only registered when the package imports cleanly. If the
  directory is absent, `import toolkits` still succeeds.
- The alias is the *same module object*, not a copy — `is` identity holds, so
  there is exactly one instance of the package in memory.

### 3.4 Where tests must live, and the exact pytest contract

Two supported placements, with different requirements:

| Placement | Requirement |
|---|---|
| `tests/test_mikrotik_*.py` (repo root) | **Preferred.** Import via the alias or via `importlib`. Works with the default pytest import mode. |
| `toolkits/MikroTik-RouterOS/tests/` | **No `__init__.py`**, and the suite must run under `--import-mode=importlib`. |

#### The mechanism (pytest 9.1.1)

pytest derives a test module's dotted name from its path. The relevant code is
`_pytest/pathlib.py::resolve_package_path`:

```python
for parent in itertools.chain((path,), path.parents):
    if parent.is_dir():
        if not (parent / "__init__.py").is_file():
            break
        if not parent.name.isidentifier():
            break
        result = parent
```

The `isidentifier()` guard stops the upward walk at `MikroTik-RouterOS`
(the hyphen makes it a non-identifier). Two consequences follow:

1. **Without `__init__.py` in the test directory** the walk stops immediately
   at the test directory itself, so pytest treats the test file as a
   top-level module. A relative import `from .. import ...` then fails with
   `ImportError: attempted relative import with no known parent package`.
2. **With `__init__.py` in the test directory** the walk *does* find a
   package, but it stops at `toolkits` (the first ancestor whose name is a
   valid identifier), so the module is named `tests.test_session` — the
   **root** `tests/` package. The relative import then resolves against the
   wrong package and fails with
   `ImportError: attempted relative import beyond top-level package`.

The same `__init__.py` also causes a **collection-time abort** when a
package-local test file shares its basename with a root test file
(`import file mismatch`), which takes the whole run down.

#### The binding fix

| Requirement | Reason |
|---|---|
| The package-local test directory **must not** contain `__init__.py`. | Restores the correct package root for relative imports and removes the basename-collision abort. |
| `pytest.ini` **must** set `addopts = --import-mode=importlib`. | Makes the relative import resolve against `toolkits/MikroTik-RouterOS/tests`. There is no `import-mode` ini option in pytest 9.1.1 - see the note in §3.4. |
| `pytest.ini` **must** add the package-local test dir to `testpaths`. | Otherwise a bare `pytest` run never collects the package-local tests. |

The resulting `pytest.ini`:

```ini
[pytest]
testpaths = tests chat_manager/tests toolkits/MikroTik-RouterOS/tests
python_files = test_*.py
python_functions = test_*
python_classes = Test*
addopts = --import-mode=importlib
collect_ignore =
    agent_apt_toolkit.py
```

> ⚠️ **pytest 9.1.1 has no `import-mode` ini option.** The spelling
> `import-mode = importlib` is **silently ignored** - pytest emits
> `PytestConfigWarning: Unknown config option: import-mode` and continues
> in the default `prepend` mode, which then fails to import the
> package-local tests. The working spelling is an **`addopts`** entry:
> `addopts = --import-mode=importlib`. This was verified empirically; see
> `verify_test_contract.py`.

#### Verification

```bash
self-development/.venv/bin/python \
    self-development/investigate/MikroTik-RouterOS/verify_test_contract.py
```

Measured outcome of applying the `pytest.ini` change to this repository
(the 76 pre-existing failures are unrelated to this feature and are present
in the baseline as well):

| Mode | Result |
|---|---|
| default (`prepend`) | 76 failed, 722 passed, 1 error |
| `--import-mode=importlib` | 76 failed, 722 passed, 1 error |
| `--import-mode=importlib` **+ extended `testpaths`** | 76 failed, **902** passed, 1 error |

> The 902 includes the 180 package-local Phase 1 tests. The 76 failures are
> pre-existing in the baseline and are unrelated to this feature.

The switch is behaviour-neutral for the existing suite, and the extended
`testpaths` adds the package-local test to the run.

> 🔀 **Merge conflict note.** The `feature/ssh-toolkit` branch also creates
> `toolkits/__init__.py`. When the two branches are merged, that file must be
> reconciled **manually** — keep the SSH-toolkit docstring *and* the alias
> block from this document. See open question Q1.

---

## 4. Module Contract

### 4.1 Layering

```
agent-torvalds.py
    ▼
agent_tool_retriever.py            (include_mikrotik_tools flag)
    ▼
toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py
                                   (LlamaIndex adapter — the eight tools)
    ▼
toolkits/MikroTik-RouterOS/         (core package — no LlamaIndex imports)
```

### 4.2 Binding rules

| # | Rule | Verification |
|---|---|---|
| R1 | **No LlamaIndex import** under the **library half** of `toolkits/MikroTik-RouterOS/`. The agent adapter (`agent_mikrotik_toolkit.py`) is the single, named exception: it is the only module of the feature that knows about LlamaIndex, and it is imported **on demand**, so `import toolkits` never pulls LlamaIndex into the process. | AST scan of every `*.py` under the package → no `llama_index` import outside the adapter, plus `python -c "import sys, toolkits; assert 'llama_index' not in sys.modules"` |
| R2 | Only **relative imports** inside the package (`from .x import y`). | AST scan of every `*.py` under the package → no `ImportFrom`/`Import` node with a `toolkits` root at `level == 0` (a plain `grep` false-positives on the prose in docstrings) |
| R3 | `asyncssh` / `pydantic` / `routeros_api` imported **lazily** or behind `try/except ImportError`. | agent boots with the deps absent |
| R4 | The package must import cleanly with **zero** optional dependencies installed. | `pip uninstall asyncssh && python -c "import toolkits"` → OK |
| R5 | `toolkits/__init__.py` must never raise. | verified by R4 |
| R6 | Every public tool returns a **dict**; no tool raises out of the adapter. | existing toolkit convention |
| R7 | Secrets never appear in a tool result, a log line or an exception message. | automated assertion in the test suite |
| R8 | The package version is exposed as `__version__`. | `toolkits/MikroTik-RouterOS/__init__.py` |

### 4.3 Public API of `toolkits/MikroTik-RouterOS/__init__.py`

Phase 1 must make these names importable from the package root:

```python
from .config import MikroTikTarget, TargetRegistry, load_targets
from .models import CommandResult, CommandCategory, RouterIdentity
from .session import RouterOSSession
from .exceptions import (
    MikroTikError, AuthError, HostKeyError, ConnectionError_,
    CommandTimeoutError, CommandRejectedError, MultilineUnsupportedError,
    InteractiveInputRequiredError, SafeModeError, PagingError, NotAuthorizedError,
)
from .safety import classify, requires_confirmation, requires_hitl
```

`__all__` must list them. The adapter imports them through the alias:

```python
from toolkits.mikrotik_routeros import (
    MikroTikTarget, TargetRegistry, load_targets, RouterOSSession, ...
)
```

---

## 5. Per-Module Specifications

### 5.1 `config.py`

- [ ] `MikroTikTarget` (pydantic v2):
  - `id: str` — logical name used by the agent
  - `host: str`, `port: int = 22`
  - `username: str = "admin"`
  - `password: SecretStr | None`
  - `key_path: Path | None` — private key file
  - `key_passphrase: SecretStr | None`
  - `group: str | None` — for filtering
  - `known_hosts: Path | None` — explicit host-key file
  - `allow_unknown_host_key: bool = False` — opt-in insecure mode
  - `connect_timeout: int = 10`, `command_timeout: int = 30`
  - `console_login_params: str = "c"` — disables colour (documented RouterOS feature)
- [ ] `TargetRegistry` — `register`, `get`, `list_targets`, `unregister`
- [ ] `load_targets(path="mikrotik_targets.yaml")` — tolerant loader:
  - missing file → empty registry (never raises at import time)
  - env-var fallback: `MIKROTIK_PASSWORD`, `MIKROTIK_KEY`
- [ ] Validator: reject an id that is not a safe slug; reject `port` outside 1–65535.
      > **Note.** The id rule cannot be "must be a Python identifier": the
      > specification's own example id, `core-rtr-01`, contains a hyphen and
      > would be rejected by that stricter rule. The implemented rule accepts
      > `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` and rejects whitespace, shell
      > metacharacters, path separators and `..`.
- [ ] Secrets are `SecretStr` and must be redacted in `repr`/`str`.

### 5.2 `models.py`

- [ ] `CommandResult` — exactly the shape from `INVESTIGATION_REPORT.md` §6.4.
- [ ] `RouterIdentity` — model, serial number, RouterOS version, uptime, cpu/load, memory, disk.
- [ ] `CommandCategory` — `READ_ONLY | LOW | MEDIUM | HIGH | CRITICAL`.

### 5.3 `exceptions.py`

- [ ] Hierarchy mapped 1:1 onto the error taxonomy (`INVESTIGATION_REPORT.md` §7.3):
  `MikroTikError` → `AuthError`, `HostKeyError`, `ConnectionError_`, `CommandTimeoutError`,
  `CommandRejectedError`, `MultilineUnsupportedError`, `InteractiveInputRequiredError`,
  `SafeModeError`, `PagingError`, `NotAuthorizedError`.
- [ ] Every exception carries a **machine-readable `code`** matching the error
      codes in §6.3 of this document.

### 5.4 `parser.py`

- [ ] `parse_print_table(text) -> list[dict]` — parse the RouterOS `print` output:
  - the `Flags:`/`Columns:` header lines
  - the ` # DST-ADDRESS GATEWAY` column-title line
  - numbered rows with a flag column
  - tolerate a missing flags column, a single row, an empty result set
- [ ] `parse_detail(text) -> list[dict]` — parse the script-friendly `detail` format.
- [ ] `parse_identity(text) -> RouterIdentity` — parse `/system/resource/print`.

### 5.5 `session.py` — the core

- [ ] Embed the **validated** regexes from `INVESTIGATION_REPORT.md` §5.3:
  ```python
  PROMPT_RE = re.compile(...)
  CONTINUATION_RE = re.compile(r"line\s+\d+\s+of\s+\d+\s*>\s*$")
  VALUE_REQUEST_RE = re.compile(r"^[A-Za-z0-9 _\-/()']+:\s*$")
  ```
- [ ] `RouterOSSession` — async context manager:
  - [ ] `connect()` — key auth preferred, password auth supported, host-key policy applied
  - [ ] `_read_banner()` — tolerate the logo, the upgrade notice, the `/system note` and the
        *"Please press Enter to continue!"* prompt
  - [ ] `_read_until_prompt(timeout)` — returns the buffer and the parsed prompt
  - [ ] `run(command, timeout)` — write, read, strip the echo, strip the prompt, detect errors
  - [ ] `run_exec(command, timeout)` — one-shot `conn.run()`; returns stdout/stderr/exit status
  - [ ] `close()`
- [ ] **Error detection** — recognise at least:
  `invalid command name X`, `bad command name X`, `no such item (N)`,
  `failure: already have such address`, `syntax error (line 1 column N)`.
- [ ] **Safe mode** — detect `<SAFE>` in the prompt; expose `enter_safe_mode()` (Ctrl+X) and
      `exit_safe_mode(save=False)` (Ctrl+D).
- [ ] **Paging control** — auto-append `without-paging` to `print` commands; detect the paging
      prompt and abort with `PagingError`.
- [ ] **Fallback** — if no prompt is seen before the timeout, return the raw buffer with
      `PROMPT_NOT_DETECTED` rather than hanging or silently truncating.
- [ ] **Multiline guard** — reject a command containing `\n`, `;`, `&&` or `|`
      with `MultilineUnsupportedError`.
- [ ] `asyncssh` is imported **inside** `connect()` (or behind a guarded
      top-level import) so the module imports without it.

### 5.6 `safety.py`

- [ ] `classify(command) -> (CommandCategory, reasons)` — implement the table in `INVESTIGATION_REPORT.md` §7.4.
- [ ] `requires_confirmation(category) -> bool`
- [ ] `requires_hitl(category) -> bool`
- [ ] `contains_injection_patterns(command) -> list[str]`
- [ ] `is_management_path_change(command, current_interfaces) -> bool` — escalate to Critical
      when the change could drop the management path.

### 5.7 `py.typed`

- [ ] An empty marker file, so the package advertises inline type hints
      (PEP 561).

---

## 6. Agent Adapter

**Location:** `toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py` — a
**submodule of the toolkit package**, reached through the alias:

```python
from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import get_all_tools
```

The adapter is the only module of the package that imports LlamaIndex, and
it is imported **on demand**: `import toolkits` and
`import toolkits.mikrotik_routeros` never pull LlamaIndex into the process.

- [ ] Module docstring with the retrieval metadata block:
  ```python
  """
  MikroTik RouterOS Toolkit - SSH-based router configuration and monitoring.

  Category: Network
  Retriever Keywords: mikrotik, routeros, router, ssh, network, firewall, interface, ip, vlan, dhcp
  """
  ```
- [ ] Import the core package **through the alias**:
  ```python
  from toolkits.mikrotik_routeros import (
      MikroTikTarget, TargetRegistry, load_targets, RouterOSSession, ...
  )
  ```
  …wrapped in `try/except ImportError` so a missing optional dependency
  degrades gracefully instead of breaking the agent boot.
- [ ] Implement the 8 tools from `INVESTIGATION_REPORT.md` §7.1, each with a full Google-style docstring
      (`Args` / `Returns` / `Example` / `Keywords`).
- [ ] `get_all_tools() -> list[FunctionTool]` — every description ends with `Category: Network`.
- [ ] Registry bootstrap at import time: `load_targets()` — **must not raise** when the
      config file is absent.
- [ ] Error handling: return a structured `dict` with `ok=False` and an `error` code —
      never raise out of a tool function (existing toolkit convention).
- [ ] Redaction: a helper that strips any known secret from an outgoing string.

### 6.1 The 8 tools

| Tool | Description | Transport |
|---|---|---|
| `list_mikrotik_targets()` | List configured routers (id, host, group). No secrets. | — |
| `test_mikrotik_connection(target)` | Verify reachability + auth; return version/identity. | exec |
| `run_mikrotik_command(target, command, mode, confirm, timeout)` | Run one RouterOS CLI command. | auto |
| `get_routeros_config(target, section, ...)` | Read a config section as structured rows. | exec |
| `backup_routeros_config(target)` | `/export` the config and return it. | session |
| `get_routeros_identity(target)` | Model, serial, version, uptime, resources. | exec |
| `get_routeros_interfaces(target)` | Interfaces + running/disabled state. | exec |
| `get_routeros_health(target)` | CPU/memory/disk + recent error log. | exec |

### 6.2 Uniform result shape

```python
{"ok": True, "stdout": "...", "stderr": "", "exit_status": 0,
 "duration_ms": 132, "transport": "exec", "error": None, "rows": None,
 "safe_mode": False, "prompt_path": None}
```

### 6.3 Error codes

`AUTH_FAILED`, `HOST_KEY_MISMATCH`, `UNREACHABLE`, `TIMEOUT`, `COMMAND_REJECTED`,
`MULTILINE_UNSUPPORTED`, `INTERACTIVE_INPUT_REQUIRED`, `SAFE_MODE_ACTIVE`, `PAGING_DETECTED`,
`NOT_AUTHORIZED`, `PROMPT_NOT_DETECTED`, `UNKNOWN_TARGET`.

---

## 7. Integration

- [ ] `agent_tool_retriever.py`:
  - [ ] add `include_mikrotik_tools: bool = True` to `build_tool_retriever(...)`
  - [ ] add the guarded import block:
    ```python
    if include_mikrotik_tools:
        try:
            from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import (
                get_all_tools as _get_mikrotik,
            )
            all_tools.extend(_get_mikrotik())
        except ImportError:
            pass
    ```
- [ ] `agent-torvalds.py`:
  - [ ] `from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import (
        get_all_tools as get_mikrotik_tools,
    )` — behind a guard, so a broken toolkit degrades to no tools
  - [ ] aggregate into the agent's tool list
- [ ] `components/command_registry.py` — register the new commands so `\help` lists them.
- [ ] Optional: a `/router` style alias so the operator can invoke a command directly.
- [ ] `requirements.txt` — add the optional dependencies:
  ```ini
  # ---------------------------------------------------------------------------
  # MikroTik RouterOS Toolkit Dependencies
  # ---------------------------------------------------------------------------
  # Async SSH transport for the MikroTik RouterOS toolkit
  # (toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py).
  # NOTE: optional - the toolkit degrades gracefully if it is not installed.
  asyncssh>=2.24.1

  # Validation layer for the MikroTik target/config/result models.
  # NOTE: optional - the toolkit degrades gracefully if it is not installed.
  pydantic>=2.9

  # RouterOS REST/binary API client (TCP 8728) - optional secondary channel used
  # for structured reads. NOT a replacement for the SSH transport.
  routeros_api>=0.21.0
  ```
- [ ] `pytest.ini` — apply the **full** pytest contract of §3.4:
  ```ini
  [pytest]
  testpaths = tests chat_manager/tests toolkits/MikroTik-RouterOS/tests
  addopts = --import-mode=importlib
  markers =
      integration: tests that require a real device or network access
  ```
  All three changes are required: `addopts` enables relative imports in
  the package-local tests, the `testpaths` entry makes a bare `pytest` run
  collect them, and the marker registers the integration tests.
  *Verified:* the `import-mode` switch alone leaves the existing suite
  unchanged (76 failed / 722 passed in both modes — the 76 are pre-existing
  and unrelated), and adding the `testpaths` entry yields 723 passed.

---

## 8. Testing

### 8.1 Test files

| File | Location | Scope |
|---|---|---|
| `tests/test_mikrotik_toolkit.py` | repo root | tool-level tests with a mocked transport |
| `tests/test_mikrotik_session.py` | repo root | prompt parsing, echo stripping, error detection, safe mode, paging, multiline guard, timeouts |
| `tests/test_mikrotik_safety.py` | repo root | the full classifier table + injection patterns |
| `tests/test_mikrotik_parser.py` | repo root | `print`/`detail` parsing fixtures |
| `tests/test_mikrotik_config.py` | repo root | YAML loading, `SecretStr` redaction, validation |
| `toolkits/MikroTik-RouterOS/tests/test_package_layout.py` | module-local | asserts the layout contract of §4.2 holds |
| `toolkits/MikroTik-RouterOS/tests/*` | module-local | mirrors of the root suite, written for `--import-mode=importlib` |

**Placement rules (binding, see §3.4):**

- The package-local test directory **must not** contain `__init__.py`.
  Adding it breaks relative imports *and* aborts collection when a basename
  collides with a root test file.
- Package-local tests use **relative** imports (`from ..config import ...`)
  or the **alias** (`from toolkits.mikrotik_routeros import ...`).
  Never an absolute `from toolkits.MikroTik-RouterOS...` import — that is a
  `SyntaxError`.
- `pytest.ini` must set `addopts = --import-mode=importlib` and list
  `toolkits/MikroTik-RouterOS/tests` in `testpaths`, otherwise the
  package-local tests are silently **not collected**.

### 8.2 Test-quality requirements

- [ ] No test requires network access unless explicitly marked `integration`.
- [ ] A test asserts that a secret value never appears in a tool result or a log record.
- [ ] A test asserts that a multi-line command is rejected with `MULTILINE_UNSUPPORTED`.
- [ ] A test asserts that a `HIGH`/`CRITICAL` command without `confirm=True` is refused.
- [ ] A test asserts the layout contract: the alias resolves, the package imports
      with no optional dependencies present, no LlamaIndex import exists under
      the library half of the package, and importing the package or the alias
      shim does not pull LlamaIndex into the process.
- [ ] A test asserts the **package-local test contract** of §3.4: the test
      directory contains no `__init__.py`, and `pytest.ini` sets
      `--import-mode=importlib` in `addopts` and includes the
      package-local test directory in `testpaths`.

### 8.3 Integration test (opt-in)

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("MIKROTIK_TEST_HOST"), reason="no router configured")
def test_read_only_command_against_real_router(): ...
```

Register the marker in `pytest.ini`:

```ini
markers =
    integration: tests that require a real device or network access
```

---

## 9. Definition of Done

| # | Criterion |
|---|---|
| D1 | `toolkits/MikroTik-RouterOS/` exists at the repository root with the exact specified name |
| D2 | `toolkits/__init__.py` registers the `toolkits.mikrotik_routeros` alias and never raises |
| D3 | The core package imports with **zero** optional dependencies installed |
| D4 | The agent can connect to a MikroTik router over SSH and run a read-only command end-to-end |
| D5 | Write commands are classified, confirmed and audited |
| D6 | A critical change automatically takes a `/export` backup first |
| D7 | Multi-line input is rejected with a clear, actionable error |
| D8 | A changed host key produces a hard stop (`HOST_KEY_MISMATCH`) |
| D9 | No secret ever appears in a tool result, a log line or an exception message |
| D10 | The agent still boots when `asyncssh` is not installed |
| D11 | `pytest` is green; the prompt-regex corpus test is permanently green |
| D12 | The existing `\help` output lists the new commands |
| D13 | No LlamaIndex import exists under the library half of `toolkits/MikroTik-RouterOS/`; the agent adapter is the only exception, and it is never imported eagerly |
| D14 | All work is confined to the `self-development` clone on its own branch |
| D15 | The package-local test directory contains **no** `__init__.py` (§3.4) |
| D16 | `pytest.ini` sets `--import-mode=importlib` in `addopts` **and** lists the package-local test directory in `testpaths` |
| D17 | A bare `pytest` run collects the package-local tests (not silently skipped) |
| D18 | `verify_layout_contract.py` and `verify_test_contract.py` both report 100% pass |

---

## 10. Open Questions

| # | Question | Recommendation | Owner |
|---|---|---|---|
| Q1 | The `feature/ssh-toolkit` branch also creates `toolkits/__init__.py`. How are the two reconciled? | **Manual merge.** Keep the SSH docstring and the MikroTik alias block in the same file. The SSH package (`toolkits/ssh_toolkit/`) is underscore-named and needs no alias. | Maintainer |
| Q2 | Should this toolkit reuse `toolkits/ssh_toolkit/` (config, models, exceptions) or ship its own? | **Reuse.** That branch already has `SSHConfig`/`SSHResult`/typed exceptions and the same core-package + root-adapter architecture. Merge it first, then have the MikroTik package depend on it. | Maintainer |
| Q3 | Should the RouterOS API (`routeros_api`) be a first-class second transport? | **Phase 2.** Ship SSH only in v1; add the API later for structured reads if parsing proves painful. It doubles the credential surface. | Maintainer |
| Q4 | Which account should the agent use on the router? | A **dedicated `agent` user** in a restricted policy group, with public-key auth and `password-authentication=no`. Never `admin`. | Operator |
| Q5 | Should write operations require HITL approval by default, or only above a risk threshold? | **Threshold** (as designed in §7.4 of the investigation report): reads and cosmetic changes run automatically; high/critical require explicit approval. | Maintainer |
| Q6 | Where should the TOFU fingerprint store live? | `~/.config/agent-torvalds/mikrotik_known_hosts`, mode `0600`, one entry per target id. | Maintainer |
| Q7 | Can a CHR (Cloud Hosted Router) image be obtained to unblock precondition P6? | MikroTik's download server is unreachable from this environment. Either obtain the image through another network path, or test against physical hardware. | Operator |

---

*This specification is authoritative for the MikroTik RouterOS module layout.
All implementation work is to be performed in the `self-development` clone on
branch `feature/mikrotik-routeros-toolkit`.*
