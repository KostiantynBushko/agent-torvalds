# PROPOSAL: MikroTik RouterOS Toolkit

**Date:** 2026-10-21
**Author:** Torvalds AI Agent
**Repository:** agent-torvalds
**Status:** Proposed
**Priority:** Medium
**Estimated Effort:** ~6 working days
**Related:** [INVESTIGATION_REPORT.md](INVESTIGATION_REPORT.md) · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Problem Statement](#2-problem-statement)
3. [Proposed Solution](#3-proposed-solution)
4. [Tool API](#4-tool-api)
5. [Safety Model](#5-safety-model)
6. [Implementation Plan](#6-implementation-plan)
7. [Risks & Mitigations](#7-risks--mitigations)
8. [Success Metrics](#8-success-metrics)

---

## 1. Overview

This proposal outlines the implementation of a **MikroTik RouterOS toolkit** that lets the agent
connect to MikroTik routers over SSH, run RouterOS CLI commands, and return structured results.

**Primary use case:** the operator asks *"check the routing table on core-rtr-01"* or
*"set the MTU on ether3 to 1500"* and the agent performs the action on the real device, safely.

**Scope of v1:**

- SSH transport to a configured set of routers (async, `asyncssh`).
- Read and write of RouterOS CLI commands, with a risk classifier and confirmation gate.
- Structured parsing of `print` output into rows.
- Optional `/export` backup before critical changes.
- A REST/structured-read path via the RouterOS API is **out of scope for v1**.

---

## 2. Problem Statement

### 2.1 Current Limitations

1. **No network-device access.** The agent can manipulate git, databases, files and the local
   system, but has no way to reach a router, switch or firewall. Network questions are answered
   from the model's memory, not from the live device.

2. **No safe path for configuration changes.** Even with raw SSH, an agent that can type
   `/system/reset-configuration` can brick a router. There is no classification, confirmation,
   backup or audit trail.

3. **No protocol knowledge.** RouterOS is not a POSIX shell. A naive implementation that writes a
   command and reads until EOF will hang on paged output, mis-detect completion, and mis-handle
   the two documented protocol traps (no pseudo-tty; stateful prompt).

4. **No credential boundary.** Credentials must never reach the LLM context, the logs, or a tool
   return value.

### 2.2 Why this is not simply "run the `ssh` command"

The `agent_linux_toolkit.py` / `agent_os_toolkit.py` families can run local shell commands, but they
are **not** a solution for this:

| Requirement | Local shell `ssh` | Dedicated toolkit |
|---|---|---|
| Non-interactive, one-shot execution | ✅ | ✅ |
| Host-key policy (TOFU + persistence) | ❌ (would need an external `known_hosts` file) | ✅ in-process |
| Structured result + machine-readable errors | ❌ (free text) | ✅ |
| Risk classification / confirmation | ❌ | ✅ |
| Automatic `/export` backup before a critical change | ❌ | ✅ |
| Credential isolation (never in the LLM context) | ⚠️ | ✅ |

---

## 3. Proposed Solution

### 3.1 Architecture

```
agent-torvalds.py
    ▼
agent_tool_retriever.py            (include_mikrotik_tools flag)
    ▼
agent_mikrotik_toolkit.py          (LlamaIndex adapter — project root, flat pattern)
    ▼
toolkits/mikrotik/                 (core package — no LlamaIndex imports)
    ├── config.py      targets, credentials, registry
    ├── models.py      CommandResult, RouterIdentity
    ├── exceptions.py  typed error hierarchy
    ├── session.py     RouterOSSession (exec + session transports, prompt parsing)
    ├── safety.py      command classifier, confirmation policy
    └── parser.py      RouterOS print/detail table parser
```

### 3.2 Two transports, one result shape

| | `exec` mode | `session` mode |
|---|---|---|
| Mechanism | `conn.run("/ip address print")` | `open_session()` + prompt loop |
| Connections | one per command | one per session, N commands |
| stdout / stderr | cleanly separated | separated |
| Exit status | real exit code | inferred from the error text |
| State (`cd`, `set` sequences) | ✗ | ✓ |
| Safe mode awareness | ✗ | ✓ |
| Paging control | via `without-paging` | ✓ |
| Use for | stateless reads | writes, stateful flows, terminal commands |

`mode="auto"` selects the transport from the command category.

### 3.3 The two protocol traps (handled by design)

1. **No pseudo-tty on the MikroTik SSH server** → the toolkit sends **exactly one single-line
   command** per call and rejects `\n`, `;`, `&&`, `|` with `MULTILINE_UNSUPPORTED`.
2. **RouterOS is a stateful interactive CLI** → completion is detected by matching the
   **prompt** (a validated regex covering all 15 documented forms, including submenu paths and
   the `<SAFE>` marker), never by a sleep or by reading to EOF.

---

## 4. Tool API

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

Every tool returns a **dict** with a uniform shape:

```python
{"ok": True, "stdout": "...", "stderr": "", "exit_status": 0,
 "duration_ms": 132, "transport": "exec", "error": None, "rows": None,
 "safe_mode": False, "prompt_path": None}
```

Errors use a **machine-classifiable** code so the agent can self-correct:
`AUTH_FAILED`, `HOST_KEY_MISMATCH`, `UNREACHABLE`, `TIMEOUT`, `COMMAND_REJECTED`,
`MULTILINE_UNSUPPORTED`, `INTERACTIVE_INPUT_REQUIRED`, `SAFE_MODE_ACTIVE`, `PAGING_DETECTED`,
`NOT_AUTHORIZED`.

---

## 5. Safety Model

### 5.1 Command classification

| Risk | Examples | Behaviour |
|---|---|---|
| Read-only | `*/print`, `*/get`, `*/find`, `*/monitor`, `*/export` | execute |
| Low | cosmetic `set`, `/system/clock`, `/log/*` | log + execute |
| Medium | `set` of `mtu`/`comment`/`disabled`, address changes | log + execute with `confirm` |
| High | `remove`, `disable`, `reboot`, firewall rules, `/user/*`, `/certificate/*` | **HITL approval** |
| Critical | `reset-configuration`, `shutdown`, management-interface removal, admin password change | **HITL approval + automatic `/export` backup** |

### 5.2 Guardrails

- **One chokepoint** — every write passes through `run_mikrotik_command`, so classification,
  confirmation, backup and audit cannot be bypassed.
- **No chaining** — `;`, `&&`, `|`, newlines rejected outright (also blocks injection pivots).
- **Safe mode** — offered for high-risk changes so an accidental lock-out self-heals
  (RouterOS discards the changes on disconnect).
- **Backup first** — critical changes automatically trigger `/export`.
- **Audit trail** — every command, its risk class, its result and its duration are logged.
  Credentials are never logged.
- **Host-key enforcement** — TOFU on first contact with a persisted fingerprint; a changed key is
  a hard stop.

### 5.3 Credentials

`pydantic.SecretStr` throughout; secrets never returned by any tool, never written to the logs,
and redacted from every outgoing string. `list_mikrotik_targets()` exposes only id/host/group.

---

## 6. Implementation Plan

| Phase | Content | Duration |
|---|---|---|
| 0 | Branch + optional dependencies in `requirements.txt` | 0.5 d |
| 1 | Core package `toolkits/mikrotik/` (config, models, exceptions, parser, session, safety) | 2 d |
| 2 | Agent adapter `agent_mikrotik_toolkit.py` + the 8 tools | 1 d |
| 3 | Integration into `agent_tool_retriever.py`, `agent-torvalds.py`, `command_registry.py` | 0.5 d |
| 4 | Tests (unit + opt-in integration) | 1.5 d |
| 5 | Documentation, example config, CHANGELOG | 0.5 d |
| | **Total** | **~6 d** |

Full detail in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

---

## 7. Risks & Mitigations

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Multi-line commands silently fail (no pty) | High | Reject multi-line input explicitly; documented protocol limit |
| R2 | Prompt detection fails on an unseen prompt form | High | Regex validated against 15 documented forms; fallback returns the raw buffer with `PROMPT_NOT_DETECTED` |
| R3 | `print` output pages and hangs | High | Auto-append `without-paging`; detect the paging prompt and abort |
| R4 | Lock-out of the management interface | **Critical** | Risk classification + HITL + auto `/export` backup + safe mode |
| R5 | Host-key MITM | **Critical** | Enforced host-key policy; TOFU with a persisted fingerprint; a changed key is a hard stop |
| R6 | Credential leakage | High | `SecretStr`, log redaction, no secrets in tool output |
| R7 | Missing `asyncssh` breaks the agent boot | Medium | Optional dependency + `try/except ImportError` guard (existing convention) |
| R8 | Slow/unreachable router blocks the agent | Medium | Async transport (does not block the event loop) + timeouts |
| R9 | RouterOS version differences in output format | Medium | Tolerant parser; `proplist`/`detail` to normalise the output |
| R10 | Command injection via a crafted command | High | Reject chaining metacharacters; validate the command grammar |
| R11 | Overlap with the `feature/ssh-toolkit` branch | Medium | Reuse its config/models/exceptions once merged (see Q1 in the plan) |
| R12 | Safe-mode state is invisible | Medium | Detect `<SAFE>` in the prompt; surface `safe_mode` in every result |

---

## 8. Success Metrics

| # | Metric | Target |
|---|---|---|
| M1 | Read command end-to-end against a real router | ✅ works, < 1 s |
| M2 | Write command refused without confirmation | ✅ 100 % of HIGH/CRITICAL commands |
| M3 | Automatic backup before a critical change | ✅ 100 % |
| M4 | Secrets in tool output / logs | **0** occurrences (automated assertion) |
| M5 | Agent boot with `asyncssh` absent | ✅ no crash |
| M6 | Prompt-regex corpus test | ✅ permanently green |
| M7 | Test suite runtime (unit only) | < 30 s |

---

*Proposed in `self-development/investigate/MikroTik-RouterOS/`. All implementation work is to be
performed in the `self-development` clone on branch `feature/mikrotik-routeros-toolkit`.*
