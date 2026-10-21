# IMPLEMENTATION PLAN: MikroTik RouterOS Toolkit

**Date:** 2026-10-21 (revised for the `toolkits/` layout requirement)
**Repository:** agent-torvalds
**Branch:** `feature/mikrotik-routeros-toolkit` (in the `self-development` clone)
**Status:** Proposed — based on `INVESTIGATION_REPORT.md`
**Estimated Effort:** ~6 working days
**Authoritative layout spec:** [MODULE_SPECIFICATION.md](MODULE_SPECIFICATION.md)

> ⚠️ **The toolkit home directory is `toolkits/MikroTik-RouterOS/`** (capital
> `M`, `T`, `R`, `O`, `S`; hyphen between `MikroTik` and `RouterOS`), created
> under a new `toolkits/` directory at the repository root. The previous
> lowercase `toolkits/mikrotik/` path is **obsolete**.
>
> Because the hyphen makes the package unreachable by a plain `import`
> statement, all consumers use the alias `toolkits.mikrotik_routeros`, which is
> registered in `toolkits/__init__.py`. See
> [MODULE_SPECIFICATION.md §3](MODULE_SPECIFICATION.md#3-the-hyphen-problem-and-the-alias)
> for the empirically verified behaviour matrix.

---

## Table of Contents

1. [Preconditions](#1-preconditions)
2. [Phase 0 — Branch & Dependencies](#2-phase-0--branch--dependencies)
3. [Phase 1 — Core Package](#3-phase-1--core-package)
4. [Phase 2 — Agent Adapter](#4-phase-2--agent-adapter)
5. [Phase 3 — Integration](#5-phase-3--integration)
6. [Phase 4 — Tests](#6-phase-4--tests)
7. [Phase 5 — Documentation](#7-phase-5--documentation)
8. [Definition of Done](#8-definition-of-done)
9. [Open Questions](#9-open-questions)

---

## 1. Preconditions

| # | Precondition | Status |
|---|---|---|
| P1 | Work happens **only** in the `self-development` clone | ✅ Rule 1 & 2 of the self-development rules |
| P2 | Dedicated branch off `master` | ⬜ Created in Phase 0 |
| P3 | `asyncssh` importable in `self-development/.venv` | ✅ Verified (2.24.1) |
| P4 | `pydantic` importable | ✅ Verified (2.13.5) |
| P5 | `routeros_api` importable | ✅ Verified (0.21.0) |
| P6 | Real RouterOS available for the final integration test | ⚠️ **Not available locally** — MikroTik's download server is unreachable (HTTP 404/403). Needs CHR container or physical router. |
| P7 | Decision on reusing the `feature/ssh-toolkit` branch's config/models | ⬜ Open question (Q1) |

---

## 2. Phase 0 — Branch & Dependencies

**Duration:** 0.5 day

- [x] Create the branch in the self-development clone:
  ```bash
  cd self-development
  git checkout -b feature/mikrotik-routeros-toolkit master
  ```
- [x] **Create the toolkit home directory** (required layout):
  ```bash
  cd self-development
  mkdir -p toolkits/MikroTik-RouterOS
  ```
  The directory name is **exact** — `MikroTik-RouterOS`, capital `M`/`T`/`R`/`O`/`S`.
  A wrong-case directory fails with a confusing `ModuleNotFoundError` on
  Linux/macOS.
- [x] Add `toolkits/__init__.py` with the **import alias shim** that registers
      `toolkits.mikrotik_routeros` → `toolkits.MikroTik-RouterOS`.
      The shim must catch `Exception` (not just `ImportError`) so that
      `import toolkits` can never fail because of an optional dependency.
      See [MODULE_SPECIFICATION.md §3.3](MODULE_SPECIFICATION.md#33-the-resolution-a-sysmodules-alias).
- [x] Add the optional dependencies to `self-development/requirements.txt`:
  ```ini
  # ---------------------------------------------------------------------------
  # MikroTik RouterOS Toolkit Dependencies
  # ---------------------------------------------------------------------------
  # Async SSH transport for the MikroTik RouterOS toolkit (agent_mikrotik_toolkit.py).
  # NOTE: optional - the toolkit degrades gracefully if it is not installed.
  asyncssh>=2.24.1

  # Validation layer for the MikroTik target/config/result models.
  # NOTE: optional - the toolkit degrades gracefully if it is not installed.
  pydantic>=2.9

  # RouterOS REST/binary API client (TCP 8728) - optional secondary channel used
  # for structured reads. NOT a replacement for the SSH transport.
  routeros_api>=0.21.0
  ```
- [x] Confirm the imports are **guarded** so a missing dependency cannot break the agent boot.

---

## 3. Phase 1 — Core Package

**Duration:** 2 days
**Location:** `self-development/toolkits/MikroTik-RouterOS/`

The core package must **not** import LlamaIndex — that keeps it independently testable and lets it
reuse the SSH toolkit's primitives (see Q1).

### 3.0 Import rules (binding — see MODULE_SPECIFICATION.md §4.2)

| # | Rule | Why |
|---|---|---|
| I1 | Use **relative imports** inside the package: `from .config import MikroTikTarget`. | The absolute form contains the hyphen and is a `SyntaxError`. |
| I2 | Import the package from consumers via the alias: `from toolkits.mikrotik_routeros import ...`. | A plain `import` statement can never name a hyphenated package. |
| I3 | Import `asyncssh` / `pydantic` **lazily** or behind `try/except ImportError`. | The agent must boot without the optional dependencies. |
| I4 | Never import LlamaIndex from inside the package. | Keeps the core independently testable. |

### 3.1 `toolkits/MikroTik-RouterOS/__init__.py`

- [x] Export the public API: `MikroTikTarget`, `TargetRegistry`, `RouterOSSession`,
      `CommandResult`, `CommandCategory`, `get_registry`, `load_targets`.

### 3.2 `toolkits/MikroTik-RouterOS/config.py`

- [x] `MikroTikTarget` (pydantic v2):
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
- [x] `TargetRegistry` — `register`, `get`, `list_targets`, `unregister`
- [x] `load_targets(path="mikrotik_targets.yaml")` — tolerant loader:
  - missing file → empty registry (never raises at import time)
  - env-var fallback: `MIKROTIK_PASSWORD`, `MIKROTIK_KEY`
- [x] Validator: reject an id that is not a safe slug; reject `port` outside 1–65535.

### 3.3 `toolkits/MikroTik-RouterOS/models.py`

- [x] `CommandResult` — exactly the shape from `INVESTIGATION_REPORT.md` §6.4.
- [x] `RouterIdentity` — model, serial number, RouterOS version, uptime, cpu/load, memory, disk.
- [x] `CommandCategory` — `READ_ONLY | LOW | MEDIUM | HIGH | CRITICAL`.

### 3.4 `toolkits/MikroTik-RouterOS/exceptions.py`

- [x] Hierarchy mapped 1:1 onto the error taxonomy (§7.3):
  `MikroTikError` → `AuthError`, `HostKeyError`, `ConnectionError_`, `CommandTimeoutError`,
  `CommandRejectedError`, `MultilineUnsupportedError`, `InteractiveInputRequiredError`,
  `SafeModeError`, `PagingError`, `NotAuthorizedError`.

### 3.5 `toolkits/MikroTik-RouterOS/parser.py`

- [x] `parse_print_table(text) -> list[dict]` — parse the RouterOS `print` output:
  - the `Flags:`/`Columns:` header lines
  - the ` # DST-ADDRESS GATEWAY` column-title line
  - numbered rows with a flag column
  - tolerate a missing flags column, a single row, an empty result set
- [x] `parse_detail(text) -> list[dict]` — parse the script-friendly `detail` format.
- [x] `parse_identity(text) -> RouterIdentity` — parse `/system/resource/print`.

### 3.6 `toolkits/MikroTik-RouterOS/session.py` — the core

- [x] Embed the **validated** regexes from `INVESTIGATION_REPORT.md` §5.3:
  ```python
  PROMPT_RE = re.compile(...)
  CONTINUATION_RE = re.compile(r"line\s+\d+\s+of\s+\d+\s*>\s*$")
  VALUE_REQUEST_RE = re.compile(r"^[A-Za-z0-9 _\-/()']+:\s*$")
  ```
- [x] `RouterOSSession` — async context manager:
  - [x] `connect()` — key auth preferred, password auth supported, host-key policy applied
  - [x] `_read_banner()` — tolerate the logo, the upgrade notice, the `/system note` and the
        *"Please press Enter to continue!"* prompt
  - [x] `_read_until_prompt(timeout)` — returns the buffer and the parsed prompt
  - [x] `run(command, timeout)` — write, read, strip the echo, strip the prompt, detect errors
  - [x] `run_exec(command, timeout)` — one-shot `conn.run()`; returns stdout/stderr/exit status
  - [x] `close()`
- [x] **Error detection** — recognise at least:
  `invalid command name X`, `bad command name X`, `no such item (N)`,
  `failure: already have such address`, `syntax error (line 1 column N)`.
- [x] **Safe mode** — detect `<SAFE>` in the prompt; expose `enter_safe_mode()` (Ctrl+X) and
      `exit_safe_mode(save=False)` (Ctrl+D).
- [x] **Paging control** — auto-append `without-paging` to `print` commands; detect the paging
      prompt and abort with `PagingError`.
- [x] **Fallback** — if no prompt is seen before the timeout, return the raw buffer with
      `PROMPT_NOT_DETECTED` rather than hanging or silently truncating.
- [x] **Multiline guard** — reject a command containing `\n`, `;`, `&&` or `|`
      with `MultilineUnsupportedError`.

### 3.7 `toolkits/MikroTik-RouterOS/safety.py`

- [x] `classify(command) -> (CommandCategory, reasons)` — implement the table in §7.4.
- [x] `requires_confirmation(category) -> bool`
- [x] `requires_hitl(category) -> bool`
- [x] `contains_injection_patterns(command) -> list[str]`
- [x] `is_management_path_change(command, current_interfaces) -> bool` — escalate to Critical
      when the change could drop the management path.

### 3.8 `toolkits/MikroTik-RouterOS/__init__.py` — public API

- [x] Re-export the public API so it is importable from the package root:
  ```python
  from .config import MikroTikTarget, TargetRegistry, load_targets
  from .models import CommandResult, CommandCategory, RouterIdentity
  from .session import RouterOSSession
  from .exceptions import (MikroTikError, AuthError, HostKeyError, ...)
  from .safety import classify, requires_confirmation, requires_hitl
  ```
- [x] `__all__` lists every exported name.
- [x] `__version__ = "0.1.0"`.

### 3.9 Phase 1 exit criteria

- [x] Package-local suite green: 180 tests in `toolkits/MikroTik-RouterOS/tests/`
      (the root-level `tests/test_mikrotik_*.py` mirrors are Phase 4)
- [x] No LlamaIndex import anywhere under `toolkits/MikroTik-RouterOS/`
- [x] The 15-case prompt corpus test is green (regression guard for risk R2)
- [x] `from toolkits.mikrotik_routeros import MikroTikTarget` works from a consumer module
- [x] The package imports cleanly with **zero** optional dependencies installed

---

## 4. Phase 2 — Agent Adapter

**Duration:** 1 day
**Location:** `self-development/agent_mikrotik_toolkit.py` (project root — flat pattern)

- [ ] Module docstring with the retrieval metadata block:
  ```python
  """
  MikroTik RouterOS Toolkit - SSH-based router configuration and monitoring.

  Category: Network
  Retriever Keywords: mikrotik, routeros, router, ssh, network, firewall, interface, ip, vlan, dhcp
  """
  ```
- [ ] Import the core package **through the alias**, guarded so a missing
      optional dependency degrades gracefully instead of breaking the boot:
  ```python
  try:
      from toolkits.mikrotik_routeros import (
          MikroTikTarget, TargetRegistry, load_targets, RouterOSSession,
          CommandResult, CommandCategory, MikroTikError,
      )
  except ImportError:
      ...
  ```
- [ ] Implement the 8 tools from §7.1, each with a full Google-style docstring
      (`Args` / `Returns` / `Example` / `Keywords`).
- [ ] `get_all_tools() -> list[FunctionTool]` — every description ends with `Category: Network`.
- [ ] Registry bootstrap at import time: `load_targets()` — **must not raise** when the
      config file is absent.
- [ ] Error handling: return a structured `dict` with `ok=False` and an `error` code —
      never raise out of a tool function (existing toolkit convention).
- [ ] Redaction: a helper that strips any known secret from an outgoing string.

---

## 5. Phase 3 — Integration

**Duration:** 0.5 day

- [ ] `agent_tool_retriever.py`:
  - [ ] add `include_mikrotik_tools: bool = True` to `build_tool_retriever(...)`
  - [ ] add the guarded import block:
    ```python
    if include_mikrotik_tools:
        try:
            from agent_mikrotik_toolkit import get_all_tools as _get_mikrotik
            all_tools.extend(_get_mikrotik())
        except ImportError:
            pass
    ```
- [ ] `agent-torvalds.py`:
  - [ ] `from agent_mikrotik_toolkit import get_all_tools as get_mikrotik_tools`
  - [ ] aggregate into the agent's tool list
- [ ] `components/command_registry.py` — register the new commands so `\help` lists them.
- [ ] Optional: a `/router` style alias so the operator can invoke a command directly.

---

## 6. Phase 4 — Tests

**Duration:** 1.5 days

- [ ] `tests/test_mikrotik_toolkit.py` — tool-level tests with a mocked transport.
- [ ] `tests/test_mikrotik_session.py` — prompt parsing, echo stripping, error detection,
      safe mode, paging, the multiline guard, timeouts.
- [ ] `tests/test_mikrotik_safety.py` — the full classifier table + injection patterns.
- [ ] `tests/test_mikrotik_parser.py` — `print`/`detail` parsing fixtures.
- [ ] `tests/test_mikrotik_config.py` — YAML loading, `SecretStr` redaction, validation.
- [ ] `toolkits/MikroTik-RouterOS/tests/test_package_layout.py` — asserts the layout
      contract: the alias resolves, the package imports with no optional
      dependencies, and no LlamaIndex import exists under the package.
- [ ] Module-local tests live in `toolkits/MikroTik-RouterOS/tests/`. The pytest
      contract is **three** changes, not one:
  ```ini
  [pytest]
  testpaths = tests chat_manager/tests toolkits/MikroTik-RouterOS/tests
  import-mode = importlib
  ```
  1. **No `__init__.py`** in the package-local test directory. With it, pytest
     resolves the test module against the *root* `tests` package, relative
     imports fail with *"attempted relative import beyond top-level package"*,
     and a basename collision with a root test file aborts collection.
  2. `import-mode = importlib` so relative imports resolve against
     `toolkits.MikroTik-RouterOS.tests`.
  3. The `testpaths` entry, otherwise a bare `pytest` run **silently does not
     collect** the package-local tests.

  Verified: `import-mode` alone leaves the existing suite unchanged
  (76 failed / 722 passed in both modes — the 76 are pre-existing and
  unrelated); adding the `testpaths` entry yields 723 passed.
  See [MODULE_SPECIFICATION.md §3.4](MODULE_SPECIFICATION.md#34-where-tests-must-live-and-the-exact-pytest-contract).
- [ ] Integration test, opt-in via `MIKROTIK_TEST_HOST`:
  ```python
  @pytest.mark.integration
  @pytest.mark.skipif(not os.getenv("MIKROTIK_TEST_HOST"), reason="no router configured")
  def test_read_only_command_against_real_router(): ...
  ```
- [ ] Register the `integration` marker in `pytest.ini`:
  ```ini
  markers =
      integration: tests that require a real device or network access
  ```

**Test-quality requirements**

- [ ] No test requires network access unless explicitly marked `integration`.
- [ ] A test asserts that a secret value never appears in a tool result or a log record.
- [ ] A test asserts that a multi-line command is rejected with `MULTILINE_UNSUPPORTED`.
- [ ] A test asserts that a `HIGH`/`CRITICAL` command without `confirm=True` is refused.

---

## 7. Phase 5 — Documentation

**Duration:** 0.5 day

- [ ] `docs/mikrotik-toolkit.md` — configuration, the target file format, the tool reference,
      the transport-selection rules, the safety model, and the **multiline limitation**.
- [ ] `mikrotik_targets.yaml.example` — an annotated example (no real secrets).
- [ ] `README.md` — a short "Network devices" section.
- [ ] `CHANGELOG.md` — an entry for the new toolkit.

---

## 8. Definition of Done

| # | Criterion |
|---|---|
| D0 | `toolkits/MikroTik-RouterOS/` exists at the repository root with the exact specified name, under a new `toolkits/` directory |
| D0b | `toolkits/__init__.py` registers the `toolkits.mikrotik_routeros` alias and never raises |
| D0c | The core package imports with **zero** optional dependencies installed |
| D1 | The agent can connect to a MikroTik router over SSH and run a read-only command end-to-end |
| D2 | Write commands are classified, confirmed and audited |
| D3 | A critical change automatically takes a `/export` backup first |
| D4 | Multi-line input is rejected with a clear, actionable error |
| D5 | A changed host key produces a hard stop (`HOST_KEY_MISMATCH`) |
| D6 | No secret ever appears in a tool result, a log line or an exception message |
| D7 | The agent still boots when `asyncssh` is not installed |
| D8 | `pytest` is green; the prompt-regex corpus test is permanently green |
| D9 | The existing `\help` output lists the new commands |
| D10 | All work is confined to the `self-development` clone on its own branch |
| D11 | No LlamaIndex import exists under `toolkits/MikroTik-RouterOS/` |
| D12 | The package-local test directory contains **no** `__init__.py` |
| D13 | `pytest.ini` sets `--import-mode=importlib` in `addopts` **and** lists the package-local test directory in `testpaths` |
| D14 | A bare `pytest` run collects the package-local tests |

---

## 9. Open Questions

| # | Question | Recommendation | Owner |
|---|---|---|---|
| Q1 | Should this toolkit reuse `toolkits/ssh_toolkit/` from the `feature/ssh-toolkit` branch (config, models, exceptions) or ship its own? | **Reuse.** The branch already has `SSHConfig`/`SSHResult`/typed exceptions and the same architectural decision (core package + root adapter). Merge that branch first, then have `toolkits/MikroTik-RouterOS/` depend on it. | Maintainer |
| Q1b | The `feature/ssh-toolkit` branch also creates `toolkits/__init__.py` — how are the two reconciled? | **Manual merge.** Keep the SSH-toolkit docstring *and* the MikroTik alias block in the same file. The SSH package `toolkits/ssh_toolkit/` is underscore-named and needs no alias. | Maintainer |
| Q2 | Should the RouterOS API (`routeros_api`) be a first-class second transport? | **Phase 2.** Ship SSH only in v1; add the API later for structured reads if parsing proves painful. It doubles the credential surface. | Maintainer |
| Q3 | Which account should the agent use on the router? | A **dedicated `agent` user** in a restricted policy group, with public-key auth and `password-authentication=no`. Never `admin`. | Operator |
| Q4 | Should write operations require HITL approval by default, or only above a risk threshold? | **Threshold** (as designed in §7.4): reads and cosmetic changes run automatically; high/critical require explicit approval. | Maintainer |
| Q5 | Where should the TOFU fingerprint store live? | `~/.config/agent-torvalds/mikrotik_known_hosts`, mode `0600`, one entry per target id. | Maintainer |
| Q6 | Can a CHR (Cloud Hosted Router) image be obtained to unblock P6? | MikroTik's download server is unreachable from this environment. Either obtain the image through another network path, or test against physical hardware. | Operator |

---

*Plan derived from `INVESTIGATION_REPORT.md`. All implementation work is to be performed in the
`self-development` clone on branch `feature/mikrotik-routeros-toolkit`.*
