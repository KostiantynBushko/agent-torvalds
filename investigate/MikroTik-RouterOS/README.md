# MikroTik RouterOS Toolkit — Investigation

**Date:** 2026-10-21
**Status:** Investigation complete — core technical risks validated empirically
**Target:** A `agent_mikrotik_toolkit.py` that connects to MikroTik routers over SSH, runs
RouterOS CLI commands, and returns structured, safely-gated results.

---

## Documents

| File | Purpose |
|---|---|
| [INVESTIGATION_REPORT.md](INVESTIGATION_REPORT.md) | The main report: protocol facts, library evaluation, empirical validation, architecture, risks |
| [PROPOSAL_mikrotik_toolkit.md](PROPOSAL_mikrotik_toolkit.md) | The proposal: scope, tool API, safety model, success metrics |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Phase-by-phase plan with exit criteria and open questions |

---

## Executive Summary

The capability is feasible. Two non-obvious protocol traps were identified and resolved:

1. **The MikroTik SSH server allocates no pseudo-tty.** MikroTik's own manual states that
   multi-line commands "will fail" over SSH. The toolkit must therefore send **exactly one
   single-line command** per call and reject `;`, `&&`, `|`, newlines explicitly.

2. **RouterOS is a stateful interactive CLI.** Completion is signalled by the **prompt**
   (`[admin@MikroTik] /ip/route>`, and `<SAFE>` in safe mode), not by EOF or a timer.

**Recommended stack:** `asyncssh` 2.24.1 (async transport, both `exec` and interactive modes,
precise host-key control) + `pydantic` v2 (config/result models, `SecretStr`) + an optional
`routeros_api` secondary channel for structured reads.

**Architecture:** one chokepoint (`run_mikrotik_command`) fronted by a risk classifier, with
HITL approval for high/critical changes, an automatic `/export` backup before critical changes,
safe-mode support, an audit trail, and enforced host-key verification (TOFU on first contact).

---

## Validation Results

All 12 hypotheses were validated against a purpose-built SSH harness that emulates the RouterOS
CLI (a real `sshd` with a `ForceCommand` script reproducing the banner, prompt, `print` table
format, error strings and safe-mode markers).

| # | Hypothesis | Result |
|---|---|---|
| V1 | `asyncssh` can drive an interactive RouterOS-style CLI | ✅ PASS |
| V2 | The prompt can be detected by regex (15 documented forms) | ✅ PASS (15/15) |
| V3 | `exec` mode separates stdout/stderr and yields an exit code | ✅ PASS |
| V4 | RouterOS errors are distinguishable from normal output | ✅ PASS |
| V5 | One session runs N commands without reconnecting | ✅ PASS (5 cmds in 4 ms) |
| V6 | Large `print` output is delivered intact | ✅ PASS (1388 bytes, 52 lines) |
| V7 | Host-key policy is enforceable (strict / TOFU / insecure) | ✅ PASS |
| V8 | A wrong host key is rejected | ✅ PASS (`KeyImportError`) |
| V9 | Command timeouts are enforced | ✅ PASS (`TimeoutError`) |
| V10 | Connection failures surface cleanly | ✅ PASS (`ConnectionRefusedError`) |
| V11 | The RouterOS API cannot speak to an SSH port | ✅ PASS (distinct protocols) |
| V12 | Colour-free login (`admin+c`) is available | ✅ PASS (documented) |

---

## Reproducing the Prototypes

The prototypes need the local SSH harness. Start it with:

```bash
cd /tmp/sshdtest
setsid /usr/sbin/sshd -f /tmp/sshdtest/sshd_config3 -D -e > /tmp/sshdtest/sshd3.log 2>&1 &
```

Then run the prototypes from the project venv:

```bash
cd self-development/investigate/MikroTik-RouterOS
PY=../../.venv/bin/python

$PY proto_prompt_regex.py   # V2  - prompt corpus (expect: ALL PASS)
$PY proto_asyncssh.py       # V1  - interactive session + prompt detection
$PY proto_exec.py           # V3/V4 - exec transport, stdout/stderr separation
$PY proto_session.py        # V5/V6 - session reuse + large output
$PY proto_hostkey.py        # V7/V8 - host-key policy matrix + TOFU
$PY proto_api.py            # V11 - the API is a separate transport
```

`proto_prompt_regex.py` is self-contained and needs no harness — it is the regression guard for
the prompt-detection logic.

---

## Key Design Constraints (carry into implementation)

| Constraint | Source |
|---|---|
| One single-line command per call | MikroTik SSH docs — no pseudo-tty |
| Reject `\n`, `;`, `&&`, `|` | Protocol limit + injection prevention |
| Always append `without-paging` to `print` | Paging would hang the session |
| Detect `<SAFE>` in the prompt | RouterOS safe mode |
| Log in as `admin+c` to disable colours | RouterOS console login parameters |
| Enforce host-key verification (TOFU) | RouterOS auto-generates its host key |
| Prefer a dedicated restricted user over `admin` | Least privilege |
| `/export` backup before critical changes | Lock-out recovery |

---

## Known Gap

The MikroTik download server is **unreachable** from this environment
(`download.mikrotik.com` → HTTP 404/403), so a **real** RouterOS instance (CHR container or
physical router) could not be used. The harness is a faithful *model* of RouterOS and validates
the protocol layer, but it cannot capture behavioural differences in a specific RouterOS release.

**Before production use, the `exec` vs `session` transport split and the write-command flows must
be confirmed against real hardware** (precondition P6 / open question Q6 in the implementation plan).

---

*All work performed in the `self-development` clone per the self-development rules. The main
repository was not modified.*
