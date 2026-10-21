# IMPLEMENTATION PLAN: MikroTik RouterOS Toolkit

**Date:** 2026-10-21
**Repository:** agent-torvalds
**Branch:** `feature/mikrotik-routeros-toolkit` (in the `self-development` clone)
**Status:** Proposed — based on `INVESTIGATION_REPORT.md`
**Estimated Effort:** ~6 working days

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

- [ ] Create the branch in the self-development clone:
  ```bash
  cd self-development
  git checkout -b feature/mikrotik-routeros-toolkit master
  ```
- [ ] Add the optional dependencies to `self-development/requirements.txt`:
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
- [ ] Confirm the imports are **guarded** so a missing dependency cannot break the agent boot.

---

## 3. Phase 1 — Core Package

**Duration:** 2 days
**Location:** `self-development/toolkits/mikrotik/`

The core package must **not** import LlamaIndex — that keeps it independently testable and lets it
reuse the SSH toolkit's primitives (see Q1).

### 3.1 `toolkits/mikrotik/__init__.py`

- [ ] Export the public API: `MikroTikTarget`, `TargetRegistry`, `RouterOSSession`,
      `CommandResult`, `CommandCategory`, `get_registry`, `load_targets`.

### 3.2 `toolkits/mikrotik/config.py`

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
- [ ] Validator: reject an id that is not a safe identifier; reject `port` outside 1–65535.

### 3.3 `toolkits/mikrotik/models.py`

- [ ] `CommandResult` — exactly the shape from `INVESTIGATION_REPORT.md` §6.4.
- [ ] `RouterIdentity` — model, serial number, RouterOS version, uptime, cpu/load, memory, disk.
- [ ] `CommandCategory` — `READ_ONLY | LOW | MEDIUM | HIGH | CRITICAL`.

### 3.4 `toolkits/mikrotik/exceptions.py`

- [ ] Hierarchy mapped 1:1 onto the error taxonomy (§7.3):
  `MikroTikError` → `AuthError`, `HostKeyError`, `ConnectionError_`, `CommandTimeoutError`,
  `CommandRejectedError`, `MultilineUnsupportedError`, `InteractiveInputRequiredError`,
  `SafeModeError`, `PagingError`, `NotAuthorizedError`.

### 3.5 `toolkits/mikrotik/parser.py`

- [ ] `parse_print_table(text) -> list[dict]` — parse the RouterOS `print` output:
  - the `Flags:`/`Columns:` header lines
  - the ` # DST-ADDRESS GATEWAY` column-title line
  - numbered rows with a flag column
  - tolerate a missing flags column, a single row, an empty result set
- [ ] `parse_detail(text) -> list[dict]` — parse the script-friendly `detail` format.
- [ ] `parse_identity(text) -> RouterIdentity` — parse `/system/resource/print`.

### 3.6 `toolkits/mikrotik/session.py` — the core

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

### 3.7 `toolkits/mikrotik/safety.py`

- [ ] `classify(command) -> (CommandCategory, reasons)` — implement the table in §7.4.
- [ ] `requires_confirmation(category) -> bool`
- [ ] `requires_hitl(category) -> bool`
- [ ] `contains_injection_patterns(command) -> list[str]`
- [ ] `is_management_path_change(command, current_interfaces) -> bool` — escalate to Critical
      when the change could drop the management path.

### 3.8 Phase 1 exit criteria

- [ ] `pytest tests/test_mikrotik_session.py tests/test_mikrotik_parser.py tests/test_mikrotik_safety.py` green
- [ ] No LlamaIndex import anywhere under `toolkits/mikrotik/`
- [ ] The 15-case prompt corpus test is green (regression guard for risk R2)

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
- [ ] Integration test, opt-in via `MIKROTIK_TEST_HOST`:
  ```python
  @pytest.mark.integration
  @pytest.mark.skipif(not os.getenv("MIKROTIK_TEST_HOST"), reason="no router configured")
  def test_read_only_command_against_real_router(): ...
  ```
- [ ] Register the `integration` marker in `pytest.ini`.

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

---

## 9. Open Questions

| # | Question | Recommendation | Owner |
|---|---|---|---|
| Q1 | Should this toolkit reuse `toolkits/ssh_toolkit/` from the `feature/ssh-toolkit` branch (config, models, exceptions) or ship its own? | **Reuse.** The branch already has `SSHConfig`/`SSHResult`/typed exceptions and the same architectural decision (core package + root adapter). Merge that branch first, then have `toolkits/mikrotik/` depend on it. | Maintainer |
| Q2 | Should the RouterOS API (`routeros_api`) be a first-class second transport? | **Phase 2.** Ship SSH only in v1; add the API later for structured reads if parsing proves painful. It doubles the credential surface. | Maintainer |
| Q3 | Which account should the agent use on the router? | A **dedicated `agent` user** in a restricted policy group, with public-key auth and `password-authentication=no`. Never `admin`. | Operator |
| Q4 | Should write operations require HITL approval by default, or only above a risk threshold? | **Threshold** (as designed in §7.4): reads and cosmetic changes run automatically; high/critical require explicit approval. | Maintainer |
| Q5 | Where should the TOFU fingerprint store live? | `~/.config/agent-torvalds/mikrotik_known_hosts`, mode `0600`, one entry per target id. | Maintainer |
| Q6 | Can a CHR (Cloud Hosted Router) image be obtained to unblock P6? | MikroTik's download server is unreachable from this environment. Either obtain the image through another network path, or test against physical hardware. | Operator |

---

*Plan derived from `INVESTIGATION_REPORT.md`. All implementation work is to be performed in the
`self-development` clone on branch `feature/mikrotik-routeros-toolkit`.*
