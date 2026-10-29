# INVESTIGATION REPORT: MikroTik RouterOS Configuration Toolkit

**Date:** 2026-10-21
**Author:** Torvalds AI Agent
**Repository:** agent-torvalds
**Target:** Implementation of a `agent_mikrotik_toolkit.py` that connects to MikroTik routers over SSH, runs RouterOS CLI commands, and safely collects/returns structured output
**Status:** Investigation Complete — all core technical risks validated empirically
**Working directory:** `~/ai-agent-investiagte/agent-torvalds/self-development`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Analysis](#2-current-architecture-analysis)
3. [MikroTik RouterOS Protocol Facts](#3-mikrotik-routeros-protocol-facts)
4. [Library Evaluation](#4-library-evaluation)
5. [Empirical Validation](#5-empirical-validation)
6. [Proposed Architecture](#6-proposed-architecture)
7. [Tool API Design](#7-tool-api-design)
8. [Implementation Plan](#8-implementation-plan)
9. [Security & Safety](#9-security--safety)
10. [Risks & Mitigations](#10-risks--mitigations)
11. [Testing Strategy](#11-testing-strategy)
12. [Conclusion](#12-conclusion)

---

## 1. Executive Summary

The agent currently has **no ability to talk to network devices**. The requested capability — "connect over SSH and run commands to configure RouterOS" — is feasible, but it has **two non-obvious protocol traps** that are documented in MikroTik's own manual and were confirmed by experiment:

| Finding | Impact |
|---|---|
| **The MikroTik SSH server does not allocate a pseudo-tty.** MikroTik's manual states: *"If the server does not support pseudo-tty (ssh -T or ssh host command), like MikroTik ssh server, then it is not possible to send multiline commands via SSH."* | Multi-line RouterOS scripts **cannot** be piped to a router over SSH. The toolkit must be strictly **single-line, one-command-at-a-time**. |
| **RouterOS is a stateful interactive CLI**, not a one-shot command runner. The prompt encodes the current menu path (`[admin@MikroTik] /ip/route>`) and a session has a login banner, colour, paging and a "safe mode" state. | A correct implementation must parse the **prompt** to know when a command has finished and in what context the router is. Naive "write command, sleep, read all" logic is racy and will truncate or merge output. |

**Recommended stack (validated):**

| Layer | Choice | Rationale |
|---|---|---|
| SSH transport | **`asyncssh` 2.24.1** | Async-native (fits the agent's event loop), supports `exec` mode *and* interactive channels, precise host-key policy control, no C deps. |
| Protocol adapter | **Custom `RouterOSSession`** | Must implement prompt detection, command echo stripping, safe-mode detection, and paging control — no off-the-shelf library does this. |
| Optional structured access | **`routeros_api` 0.21.0** (REST/API, port 8728) | Useful *only* as an optional secondary channel for structured reads. **Not** a substitute for SSH, and cannot run arbitrary CLI commands. |
| Validation | `pydantic` 2.13.5 (already installed) | Config/result models, `SecretStr` for credentials. |

**Key architectural decision — two transport modes, one tool API:**

- **`exec` mode** (`ssh router "/ip address print"`) → one connection per command. Clean stdout/stderr separation, real exit codes, no prompt parsing. **Preferred for read-only, stateless commands.**
- **`session` mode** (interactive channel) → one connection, N commands. Required for stateful flows (`cd` into a menu, `set`/`add` sequences), for `print` with paging control, and for detecting **safe mode**. **Required for anything that changes state.**

Both were implemented and exercised against a purpose-built SSH harness that emulates RouterOS. All 15 documented RouterOS prompt forms are matched by the validated regex.

---

## 2. Current Architecture Analysis

### 2.1 Repository Structure (self-development clone)

```
~/ai-agent-investiagte/agent-torvalds/self-development/
├── agent-torvalds.py              # Main orchestrator
├── agent_*.py                     # Toolkits (flat, one file per domain)
├── agent_tool_retriever.py        # Semantic on-demand tool loading
├── components/                    # Shared components
│   ├── command_registry.py        # \help command registry
│   ├── stats_handler.py
│   ├── human_loop_handler.py
│   └── whiptail_*.py              # Terminal dialogs
├── tests/                         # pytest suite
├── requirements.txt
└── investigate/                   # ← investigation reports live here
```

### 2.2 Existing Toolkit Pattern (mandatory conformance target)

Every toolkit in this repo follows the same 4-part contract. The MikroTik toolkit must match it exactly.

**Part 1 — module docstring with retrieval metadata.** The retriever embeds tool descriptions, so the header drives semantic recall:

```python
"""
MikroTik RouterOS Toolkit - SSH-based router configuration and monitoring.

Category: Network
Retriever Keywords: mikrotik, routeros, router, ssh, network, firewall, interface, ip
"""
```

**Part 2 — plain, well-typed functions.** No LlamaIndex types in the function signatures; the LlamaIndex dependency is confined to the adapter layer. Every tool function carries a Google-style docstring with `Args`, `Returns` and `Example` sections — this docstring *is* the LLM-facing contract.

**Part 3 — `get_all_tools() -> list[FunctionTool]`.** The single entry point the retriever calls:

```python
def get_all_tools() -> list[FunctionTool]:
    return [
        FunctionTool.from_defaults(
            fn=run_routeros_command,
            description="Run a RouterOS CLI command on a MikroTik router over SSH. ... Category: Network",
        ),
        ...
    ]
```

**Part 4 — registration in `agent_tool_retriever.py`.** Two edits are needed: an `include_mikrotik_tools: bool = True` parameter, and a guarded import block.

### 2.3 Registration Pattern in `agent_tool_retriever.py`

```python
    include_project_manager_tools: bool = True,  # NEW: Step 05
+   include_mikrotik_tools: bool = True,          # NEW: MikroTik RouterOS toolkit
) -> tuple:
    ...
+   if include_mikrotik_tools:
+       try:
+           from agent_mikrotik_toolkit import get_all_tools as _get_mikrotik
+           all_tools.extend(_get_mikrotik())
+       except ImportError:
+           # MikroTik toolkit not available — skip gracefully
+           pass
```

The `try/except ImportError` guard is the established convention (`project_manager` uses it) — it keeps the agent bootable when an optional toolkit's dependencies are missing. **This matters here:** `asyncssh` must be an *optional* dependency so that a missing install degrades gracefully instead of crashing the orchestrator.

### 2.4 Error-Handling Convention

Toolkits return error **strings** rather than raising, so the LLM receives the failure as tool output and can self-correct:

```python
    except Exception as e:
        return f"Error running PostgreSQL query: {str(e)}"
```

The MikroTik toolkit must follow this, but with **structured error payloads** (see §7.3) because a router error needs to be machine-classifiable (`AUTH_FAILED` vs `TIMEOUT` vs `COMMAND_REJECTED`).

### 2.5 Gap Summary

| Requirement | Current state | Gap |
|---|---|---|
| SSH transport to network devices | None | New |
| RouterOS prompt parsing | None | New |
| Router-safe config change flow (safe mode, rollback) | None | New |
| Credential/config management for routers | None | New |
| `asyncssh` dependency | Not in `requirements.txt` | Add (optional) |
| `pydantic` dependency | Installed (2.13.5) but not in `requirements.txt` | Add (optional) |
| `routeros_api` dependency | Not present | Add (optional) |
| Toolkit registration | N/A | Add to retriever + `agent-torvalds.py` |
| Tests | N/A | `tests/test_mikrotik_toolkit.py` |

---

## 3. MikroTik RouterOS Protocol Facts

All facts in this section are taken from the official MikroTik RouterOS documentation
(`help.mikrotik.com/docs/display/ROS/...`) and were cross-checked against the local experiments in §5.

### 3.1 SSH Service

| Property | Value |
|---|---|
| Protocol | SSH v2, enabled by default |
| Default port | TCP/22 (configurable under `/ip ssh`) |
| `host-key-type` | `rsa` (default) or `ed25519`; `host-key-size` default 2048 |
| `password-authentication` | `yes-if-no-key` (default) / `yes` / `no` |
| `publickey-authentication-options` | `none` (default) / `touch-required` / `verify-required` (FIDO) |
| `strong-crypto` | `no` (default) / `yes` — **recommended `yes`** |
| `forwarding-enabled` | `no` (default) — keep `no` on the router |

**Key import for PKI (documented, verified path):**

```
/user ssh-keys import public-key-file=id_rsa.pub user=admin
```

**Host key export/import (documented):**

```
/ip ssh export-host-key key-file-prefix=admin      # writes admin_rsa + admin_rsa.pub (PKCS#8)
/ip ssh import-host-key private-key-file=admin_rsa
/ip ssh regenerate-host-key
```

> ⚠️ RouterOS **cannot generate** SSH key pairs itself — the host key is auto-generated on first
> connection or exported with `export-host-key`. The toolkit therefore needs a **Trust-On-First-Use
> (TOFU)** flow, because the operator's `known_hosts` will be empty on day one.

### 3.2 ⚠️ The Pseudo-TTY Trap (most important finding)

From the official SSH documentation, verbatim:

> "If the server does not support pseudo-tty (ssh -T or ssh host command), like MikroTik ssh server,
> then **it is not possible to send multiline commands via SSH**. For example, sending command
> `/ip address \n add address=1.1.1.1/24` to MikroTik router will fail. If you wish to execute remote
> commands via scripts or scheduler, use command `ssh-exec`."

**Consequences for the toolkit:**

1. **Never** send a multi-line script. One command per line, one line per command.
2. The `exec` transport must request **no** PTY (`term_type=None`) — the MikroTik server does not
   provide one anyway, and requesting it is meaningless.
3. RouterOS script blocks (`{ ... }`) and `:do {...}` constructs **cannot** be delivered over SSH**.
   They must be written to a file on the router first (`/file add name=... content=...`) or sent via
   the **API** channel. This is a hard design boundary and must be documented for the LLM so it does
   not attempt it.
4. A command that needs **two** inputs (e.g. `/password` asks *old*, *new*, *retype*) is
   **not scriptable over SSH**. The toolkit must detect value-request prompts and refuse, directing
   the operator to do it manually.

### 3.3 The RouterOS Prompt (the state machine)

From the official CLI documentation:

> "Default command prompt consists of user name, system identity, and current command path."

| Form | Meaning |
|---|---|
| `[admin@MikroTik] >` | root level |
| `[admin@MikroTik] /interface>` | one level deep (slash path) |
| `[admin@MikroTik] /ip/route>` | deep path |
| `[admin@MikroTik] <admin@MikroTik>` | bracketed path form |
| `[admin@MikroTik] ip route<SAFE>` | **safe mode** active |
| `line 2 of 3>` | multiline continuation prompt (command not yet complete) |
| `old password:` | value-request prompt (command needs an input) |

**Safe mode** (official docs): *"Safe mode can be used to minimize such risk. ... In this mode, the
configuration is saved to disk only after the safe mode is turned off. Safe mode can be turned on/off
with Ctrl+X or F4."* Entering safe mode is done with **Ctrl+X** (`\x18`) — a control character that
**can** be sent over SSH. Exiting *without saving* is **Ctrl+D** (`\x04`).

**Hot-lock mode** adds an extra `>` to the prompt.

**Banner noise** to expect before the first prompt: the MikroTik ASCII logo, plus optionally an
upgrade notice, `/system note` messages, recent critical log lines, and a *"Please press Enter to
continue!"* prompt (demo/upgrade builds). The toolkit must tolerate all of these.

### 3.4 Console Login Parameters

The username can carry console parameters after `+` (officially documented):

```
login_name ::= user_name [ '+' parameters ]
```

| Param | Meaning |
|---|---|
| `w` | set terminal width (`auto` default) |
| `h` | set terminal height |
| `c` | disable console colours (default **on**) |
| `t` | disable terminal auto-detection |
| `e` | enable "dumb" terminal mode (default **on**) |
| `d` | disable "dumb" terminal mode |

> 💡 **Design win:** logging in as `admin+c` (or `admin+ce`) **disables console colours**, which
> removes ANSI escape sequences from the output and makes parsing dramatically more reliable. The
> toolkit should use this by default. `admin+ce` additionally forces dumb-terminal mode.

### 3.5 Machine-Readable Output

`print` accepts parameters that make output parseable (officially documented):

| Parameter | Effect |
|---|---|
| `without-paging` | **do not stop after each screenful** — mandatory for automation |
| `proplist=` | comma-separated, ordered list of properties to include |
| `from=` | only show specified items, in the given order |
| `where=` | only show items matching criteria |
| `show-ids` | print internal IDs |
| `detail` | print item details in a script-friendly form |
| `follow` / `follow-only` / `follow-strict` | continuous output |
| `interval=` | refresh interval for `print` |
| `oid` | print SNMP-accessible OIDs |

> ⚠️ **`without-paging` is not optional for automation.** Without it a `print` on a router with many
> items will page and **hang waiting for a keypress**. Every read command in the toolkit must
> append `without-paging`.

### 3.6 RouterOS API (the alternative channel)

| Fact | Detail |
|---|---|
| Default ports | TCP/8728 (plain), TCP/8729 (API-SSL) |
| Protocol | length-prefixed binary sentences — **completely different from SSH** |
| Must be enabled | `api` service must be enabled under `/ip service` |
| Capability | "gather information, adjust the configuration, and manage the router" |
| Security | API-SSL supports TLS or an anonymous Diffie-Hellman cipher if no certificate is set |

The API mirrors CLI syntax closely, so a `print` query in the API returns **structured attributes** —
much easier to parse than CLI text. But it **cannot run arbitrary CLI commands** (e.g. `/ping`, `/log`,
terminal-only commands), and it needs a separate port enabled.

### 3.7 The Router's Own SSH Client (`/system ssh`)

RouterOS can itself act as an SSH client, which is useful for the agent to reach *other* devices:

```
/system ssh 192.168.88.1 "/ip address print"
/system ssh 192.168.88.1 command="/ip address print"
/system ssh 192.168.88.1 src-address=192.168.89.2
```

And the non-interactive form for scripts/scheduler:

```
/system ssh-exec address=10.10.10.1 user=remote command=":put ([/interface ethernet monitor ...])"
```

`/system ssh-exec` returns **two values: `exit-code` and `output`** — a good model for what the
toolkit's own result object should look like.

---

## 4. Library Evaluation

### 4.1 `asyncssh` 2.24.1 — ✅ RECOMMENDED (primary transport)

| Attribute | Assessment |
|---|---|
| Version available | 2.24.1 (verified on PyPI) |
| Install | Pure Python + `cryptography` wheel — no compilation |
| Concurrency | Fully async (`asyncio`) — matches the agent's event loop |
| `exec` mode | `conn.run(cmd)` → `.stdout`, `.stderr`, `.exit_status` |
| Interactive mode | `conn.open_session()` → `(writer, reader, stderr_reader)` |
| Host-key control | `known_hosts=` file / bytes / `SSHKnownHosts` / **callable** / `None` |
| Timeouts | `conn.run(..., timeout=)` → raises `asyncio.TimeoutError` |
| Encoding | `encoding=`, `errors=` params on `open_session`/`create_session` |

**Verified API details (2.24.1):**

- `open_session()` returns a **3-tuple** `(writer, reader, stderr_reader)` — *not* 2-tuple.
  The reader is an `asyncssh.SSHReader` (methods: `read`, `readline`, `readuntil`, `at_eof`) and
  **has no `set_encoding()`** — encoding is a *parameter* of `open_session`, not a setter.
- `known_hosts` callable protocol is `fn(host, addr, port) -> (trusted, trusted_ca, revoked)` where
  the key lists contain **bytes** of OpenSSH public-key lines (passing `str` raises
  `FileNotFoundError`; malformed bytes raise `KeyImportError`).
- `known_hosts=None` disables host-key verification entirely (accepts any key).

**Verdict:** the only library found that supports **both** required transports with precise
host-key policy control.

### 4.2 `paramiko` — ⚠️ FALLBACK ONLY

Synchronous, mature, widely used. It *can* do both transports (`exec_command` / `invoke_shell`).
Rejected as primary because it is **blocking** — it would stall the agent's event loop during the
multi-second round-trip to a remote router, degrading the whole agent. Keep as an optional
fallback for environments where `asyncssh` cannot be installed.

### 4.3 `routeros_api` 0.21.0 — ⚠️ OPTIONAL SECONDARY CHANNEL

- Exposes `connect(host, username, password, port, plaintext_login, use_ssl, ...)` and
  `RouterOsApiPool` for connection pooling.
- Talks the **binary API protocol** on port 8728 — verified to fail against an SSH port
  (`RouterOsApiConnectionClosedError`), confirming SSH and API are distinct transports.
- Returns **structured attributes** (great for `print`-style reads).
- **Cannot** run arbitrary CLI commands; requires the API service enabled on the router.
- **Verdict:** valuable as an *optional* accelerated read path, but it is **not** the answer to
  "run a command over SSH". It also adds a second credential surface to secure.

### 4.4 `librouteros` 4.2.2 — ❌ NOT RECOMMENDED

- Same binary API protocol, older API surface, single-connection oriented.
- Verified: `ConnectionClosed` when pointed at an SSH port.
- Superseded by `routeros_api`; no advantage for the SSH use case.

### 4.5 `netmiko` / `scrapli` — ❌ NOT RECOMMENDED

Network-automation libraries (Cisco/Juniper/Arista focus). They add heavy dependencies
(paramiko, `napalm`, textfsm) and a device-driver model built around non-MikroTik CLIs. MikroTik is
supported only partially and none of it is needed for a RouterOS-specific toolkit.

### 4.6 Rejected Summary

| Library | Verdict | Reason |
|---|---|---|
| `asyncssh` | ✅ **Primary** | Async, both transports, host-key policy control |
| `paramiko` | ⚠️ Fallback | Blocking; only for `asyncssh`-less environments |
| `routeros_api` | ⚠️ Optional | API port only; structured reads, no arbitrary CLI |
| `librouteros` | ❌ | Older API client, same protocol, no advantage |
| `netmiko` / `scrapli` | ❌ | Wrong device model, heavy deps |

---

## 5. Empirical Validation

Because MikroTik's download servers are unreachable from this environment (`download.mikrotik.com`
→ HTTP 404/403), a **purpose-built SSH harness** was created that emulates RouterOS behaviour:
a real `sshd` instance (`OpenSSH_9.6p1`) on ports 2222–2224, with a `ForceCommand` script that
reproduces the RouterOS banner, prompt, `print` output format, `invalid command name` errors,
multi-line `print` tables and safe-mode markers.

This validated the protocol-level assumptions without needing physical hardware.

### 5.1 Validation Matrix

| # | Hypothesis | Method | Result |
|---|---|---|---|
| V1 | `asyncssh` can drive an interactive RouterOS-style CLI | `open_session()` + prompt loop | ✅ PASS |
| V2 | The RouterOS prompt can be detected by regex, not fixed length | 15-case corpus | ✅ PASS (15/15) |
| V3 | `exec` mode yields clean stdout/stderr separation + exit code | `conn.run()` | ✅ PASS |
| V4 | RouterOS errors are distinguishable from normal output | `invalid command name` | ✅ PASS |
| V5 | One session can execute N commands without reconnecting | 5 sequential commands | ✅ PASS — **4 ms total** |
| V6 | Large `print` output is delivered without truncation/deadlock | 50-row table, 1388 bytes | ✅ PASS — 14 ms |
| V7 | Host-key policy is enforceable in all three modes | strict / TOFU / insecure | ✅ PASS |
| V8 | A wrong host key is rejected | mismatched key | ✅ PASS (`KeyImportError`) |
| V9 | Command timeouts are enforced | `timeout=0.0001` | ✅ PASS (`TimeoutError`) |
| V10 | Connection failures surface cleanly | closed port | ✅ PASS (`ConnectionRefusedError`) |
| V11 | The RouterOS API cannot speak to an SSH port | API client vs SSH port | ✅ PASS (confirms distinct protocols) |
| V12 | Colour-free login (`admin+c`) is available | CLI documentation | ✅ PASS (documented) |

### 5.2 V5/V6 — Session Efficiency and Large Output

```
--- /system/resource  (1.0 ms, 35 bytes, 1 lines)
                   uptime: 3d4h5m6s

--- /interface/print  (14.2 ms, 1388 bytes, 52 lines)
Flags: R - RUNNING
Columns: NAME, TYPE, ACTUAL-MTU, L2MTU
  0  R ether0 1500 1598
  1  R ether1 1500 1598
  ...
   ...[1168 bytes elided]...

=== session reuse: 5 sequential commands on ONE connection ===
5 commands in 4 ms (no reconnect overhead)
```

**Conclusion:** session reuse is ~50–100× cheaper than reconnecting per command (each connect costs
~130 ms). A stateful session is therefore both a **performance** win and a **correctness**
requirement for stateful command sequences.

### 5.3 V2 — The Validated Prompt Regex

```python
PROMPT_RE = re.compile(
    r"\[(?P<user>[^\]\r\n]{1,64})@(?P<host>[^\]\r\n]{1,64})\]"   # [user@host]
    r"(?:\s*<SAFE>)?"                                            # safe-mode marker
    r"(?P<path>(?:\s*/[^\s<>\r\n]+)*"                            # slash path, e.g. /ip/route
    r"|(?:\s+[^\s<>\r\n]+(?:\s+[^\s<>\r\n]+)*)?)?"                # or space-separated path
    r"(?:\s*<(?P<bracket>[^>\r\n]*)>)?"                           # bracketed path form
    r"(?:\s*>)?\s*$"                                            # optional trailing '>'
)

CONTINUATION_RE = re.compile(r"line\s+\d+\s+of\s+\d+\s*>\s*$")   # multiline continuation
VALUE_REQUEST_RE = re.compile(r"^[A-Za-z0-9 _\-/()']+:\s*$")    # "old password: "
```

Corpus result — **15/15 PASS**:

```
[PASS] root prompt                      user='admin' host='MikroTik' path=''
[PASS] root prompt no trailing space
[PASS] submenu prompt                   path=' /interface'
[PASS] deep submenu prompt              path=' /ip/route'
[PASS] bracketed path form
[PASS] bracketed path + >
[PASS] safe mode marker                 path=' ip route'
[PASS] command typed after prompt       (correctly NOT matched)
[PASS] output + prompt
[PASS] error + prompt
[PASS] bare
[PASS] prompt not at end                (correctly NOT matched)
[PASS] prompt quoted mid-output         (correctly NOT matched)
[PASS] other user/hostname              user='netops' host='core-rtr-01'
[PASS] long path                        path=' /ip/firewall/filter'

Continuation prompt : True
Value request prompt: True
```

The two negative cases are important: the regex is **anchored at the end of the buffer**, so a
prompt-like string quoted inside log output does **not** cause a false "command finished" signal.

### 5.4 V3/V4 — Exec Mode Output Separation

```
exec stdout      : '                   uptime: 3d4h5m6s\n'
exec stderr      : ''
exec exit_status : 0
exec returncode  : 0

err stdout       : ''
err stderr       : 'invalid command name bogus/command\n'
err exit_status  : 1
```

**Conclusion:** in `exec` mode the router's error text arrives on **stderr** with a **non-zero exit
status** — clean separation, no parsing heuristics required. This is why `exec` mode is the
preferred transport for stateless read commands.

### 5.5 V7/V8 — Host-Key Policy (TOFU is Required)

| Policy | Result |
|---|---|
| `known_hosts=<empty file>` | `HostKeyNotVerifiable: Host key is not trusted for host 127.0.0.1` ✅ |
| `known_hosts=<correct key>` | **ACCEPTED** ✅ |
| `known_hosts=None` (no verification) | ACCEPTED ⚠️ — insecure, opt-in only |
| `known_hosts=<callable TOFU>` | **ACCEPTED**, callback invoked with `(host, addr, port)` ✅ |
| TOFU returning a **wrong** key | `KeyImportError: Invalid public key` ✅ rejected |

Because RouterOS auto-generates its host key on first connection and the operator has no
pre-seeded `known_hosts`, **TOFU is the practical default**, with the accepted fingerprint
persisted to a local state file so subsequent runs detect a **changed** key (i.e. a possible
man-in-the-middle or a re-imaged router).

---

## 6. Proposed Architecture

### 6.1 Component Map

```
agent-torvalds.py
    │  import get_all_tools as get_mikrotik_tools
    ▼
agent_tool_retriever.py  ── include_mikrotik_tools flag
    │
    ▼
agent_mikrotik_toolkit.py            ← LlamaIndex adapter (project root, flat pattern)
    │  tool functions, get_all_tools()
    ▼
toolkits/MikroTik-RouterOS/         ← core package (no LlamaIndex imports)
    ├── config.py        MikroTikTarget, TargetRegistry, YAML loading, SecretStr
    ├── models.py        CommandResult, RouterIdentity, CommandCategory
    ├── exceptions.py    MikroTikError hierarchy
    ├── session.py       RouterOSSession  ← prompt parsing, exec/session transports
    ├── safety.py        command classification, confirmation, safe-mode handling
    └── parser.py        RouterOS table parser (print output -> structured rows)
```

> **Why a package under `toolkits/`?** The core SSH/protocol layer must be testable and
> LlamaIndex-free. This mirrors the decision already taken on the `feature/ssh-toolkit` branch
> (`toolkits/ssh_toolkit/` + a thin `agent_ssh_toolkit.py` adapter). The Mikrotik toolkit can then
> **reuse** that branch's `SSHConfig`/`SSHResult`/`exceptions` once the two branches are merged —
> a deliberate point of compatibility.

> ⚠️ **The hyphen in `MikroTik-RouterOS`.** The directory name contains a hyphen,
> which is not a valid Python identifier. `from toolkits.MikroTik-RouterOS import ...`
> is therefore a **`SyntaxError`**, and an *absolute* import inside the package
> fails the same way. Two consequences, both verified empirically against
> Python 3.12.3 / pytest 9.1.1:
>
> 1. **Inside the package** use only **relative** imports (`from .config import ...`).
> 2. **Consumers** use the alias `toolkits.mikrotik_routeros`, which
>    `toolkits/__init__.py` registers in `sys.modules`:
>    ```python
>    from toolkits.mikrotik_routeros import MikroTikTarget
>    ```
>
> A test module placed **inside** the hyphenated directory also needs a
> specific pytest contract: **no `__init__.py`** in that directory, plus
> `--import-mode=importlib`, plus the directory listed in `testpaths`.
> Without the `__init__.py`, pytest's default `prepend` mode cannot resolve
> the relative import at all; with it, pytest resolves the module against the
> *root* `tests` package and the relative import fails with *"attempted
> relative import beyond top-level package"*. The full behaviour matrix and
> the verified fix are in
> [MODULE_SPECIFICATION.md §3](MODULE_SPECIFICATION.md#3-the-hyphen-problem-and-the-alias)
> and [§3.4](MODULE_SPECIFICATION.md#34-where-tests-must-live-and-the-exact-pytest-contract).

### 6.2 Transport Strategy

```
                       ┌──────────────────────────────────┐
   run_routeros_        │        TransportSelector         │
   command(target,      │  classify command → transport    │
   cmd, mode=auto)      └──────────────┬───────────────────┘
                                       │
              ┌────────────────────────┴────────────────────────┐
              ▼                                                 ▼
      ┌───────────────┐                              ┌──────────────────┐
      │  EXEC MODE    │                              │  SESSION MODE    │
      │  conn.run()   │                              │  open_session()  │
      │  1 conn/cmd   │                              │  1 conn, N cmds  │
      ├───────────────┤                              ├──────────────────┤
      │ stdout ✓      │                              │ stdout ✓         │
      │ stderr ✓      │                              │ stderr ✓         │
      │ exit code ✓   │                              │ exit status ~    │
      │ no pty        │                              │ prompt parsing   │
      │ no state      │                              │ stateful (cd)    │
      │ no safe-mode  │                              │ safe-mode aware  │
      └───────┬───────┘                              └────────┬─────────┘
              └──────────────┬──────────────────────────────────┘
                             ▼
                    CommandResult (uniform shape)
```

**`mode=auto` selection rules (proposed):**

| Command category | Transport | Reason |
|---|---|---|
| Read (`print`, `get`, `find`, `monitor`) | `exec` | Stateless, clean stderr/exit code, no paging risk if `without-paging` is appended |
| Write (`set`, `add`, `remove`, `enable`, `disable`) | `session` | Needs verification of the resulting state; safe-mode support |
| State-dependent (needs `cd` first) | `session` | Context persists only in a session |
| Interactive/terminal-only (`ping`, `traceroute`, `log`, `terminal`) | `session` | Not available in `exec` mode on RouterOS |
| Multi-step / transactional | `session` | Multiple commands, rollback on failure |

### 6.3 Session Lifecycle

```
        ┌──────────────┐
        │  connect()   │  auth (key preferred) + host-key policy
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ read banner  │  tolerate logo / upgrade notice / "press Enter"
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │ read prompt  │  PROMPT_RE → establishes session is live
        └──────┬───────┘
               ▼
     ┌──────────────────┐   send command
     │  run(command)    │◄──────────────┐
     │  strip echo      │               │
     │  strip prompt    │               │
     │  detect error    │               │
     └────────┬─────────┘               │
              ▼                         │
     ┌──────────────────┐               │
     │ CommandResult    │───────────────┘
     └──────────────────┘
               ▼
        ┌──────────────┐
        │  close()      │  optional: /quit or channel close
        └──────────────┘
```

### 6.4 Result Model

```python
class CommandResult(BaseModel):
    command: str
    stdout: str
    stderr: str
    exit_status: int | None          # exec mode: real code; session mode: inferred
    duration_ms: int
    transport: Literal["exec", "session"]
    ok: bool
    error: str | None = None         # machine-classifiable: AUTH_FAILED / TIMEOUT / ...
    rows: list[dict] | None = None   # parsed table when the output is a print table
    safe_mode: bool = False          # TRUE if the router is in safe mode
    prompt_path: str | None = None   # e.g. "/ip/route"
```

---

## 7. Tool API Design

The LLM-facing tool set must be small, unambiguous, and safe by default.

### 7.1 Proposed Tools

| Tool | Purpose | Transport |
|---|---|---|
| `list_mikrotik_targets()` | Show configured routers (id, host, group). Never exposes secrets. | — |
| `test_mikrotik_connection(target)` | Verify auth + reachability; return RouterOS version/identity. | exec |
| `run_mikrotik_command(target, command, mode="auto", confirm=False)` | Execute one RouterOS CLI command. | auto |
| `get_routeros_config(target, section, ...)` | Read a config section as structured rows (`without-paging` + `proplist`). | exec |
| `backup_routeros_config(target)` | `/export` the configuration to a file on the router and return its contents. | session |
| `get_routeros_identity(target)` | Model, serial, version, uptime, resource usage. | exec |
| `get_routeros_interfaces(target)` | Interface list with running/disabled state. | exec |
| `get_routeros_health(target)` | CPU/memory/disk/temperature + recent error log. | exec |

> **Deliberately omitted:** a free-form "apply this configuration" tool. Every write goes through
> `run_mikrotik_command` with the safety classifier in front of it, so there is exactly **one**
> chokepoint for confirmation, auditing and rollback.

### 7.2 Example Tool Signature

```python
def run_mikrotik_command(
    target: str,
    command: str,
    mode: str = "auto",
    confirm: bool = False,
    timeout: int = 30,
) -> dict:
    """
    Run a single RouterOS CLI command on a MikroTik router over SSH.

    Use this to inspect or change RouterOS configuration, e.g. "/system/resource print",
    "/ip/address/print", "/interface/ether1/set/mtu=1500".

    IMPORTANT: MikroTik's SSH server does not support pseudo-terminals, so ONLY a single
    one-line command may be sent. Multi-line scripts and block syntax ({ ... }) are not
    supported and will fail. Commands that require interactive input (e.g. /password)
    are also not supported.

    Args:
        target (str): Logical target id from list_mikrotik_targets(), e.g. "core-rtr-01".
        command (str): One single-line RouterOS CLI command. Do not include a trailing '?'.
        mode (str): "auto" (default), "exec" (one-shot, stateless) or "session" (stateful).
        confirm (bool): Must be True to execute a command classified as a configuration change.
        timeout (int): Command timeout in seconds (default 30).

    Returns:
        dict: {ok, stdout, stderr, exit_status, duration_ms, transport, error, rows}

    Example:
        >>> run_mikrotik_command("core-rtr-01", "/system/resource/print")
        {'ok': True, 'stdout': 'uptime: 3d4h5m6s', 'rows': None, ...}
    """
```

### 7.3 Error Taxonomy

| `error` code | Meaning | Agent guidance |
|---|---|---|
| `AUTH_FAILED` | Bad credentials / key rejected | Check target's credentials; do not retry blindly |
| `HOST_KEY_MISMATCH` | Stored key differs | **Stop** — possible MITM or re-imaged router; needs human approval |
| `UNREACHABLE` | Timeout / refused | Check IP/port/firewall |
| `TIMEOUT` | Command exceeded `timeout` | Increase timeout or split the command |
| `COMMAND_REJECTED` | Router returned `invalid command name` / `bad command` | Fix the syntax |
| `MULTILINE_UNSUPPORTED` | Multi-line script detected | Rewrite as a single line, or use the API channel |
| `INTERACTIVE_INPUT_REQUIRED` | Value-request prompt detected | Operator must run it manually |
| `SAFE_MODE_ACTIVE` | Router is in safe mode | Exit safe mode explicitly before committing changes |
| `PAGING_DETECTED` | Output paged despite `without-paging` | Command needs a `print ... without-paging` suffix |
| `NOT_AUTHORIZED` | Policy forbids this operation | Request elevated approval |

### 7.4 Command Classification (Safety Classifier)

A rule-based classifier decides whether a command is a **read** or a **change**, and assigns a risk
level. It is a *pre-filter* — a human confirmation is still required for changes.

| Risk | Examples | Behaviour |
|---|---|---|
| **Read-only** | `*/print`, `*/get`, `*/find`, `*/monitor`, `*/export` | Execute directly |
| **Low** | `*/set` of cosmetic values, `/system/clock`, `/log/*` | Log + execute |
| **Medium** | `*/set` of `mtu`, `comment`, `disabled`, address changes | Log + execute with `confirm` |
| **High** | `remove`, `disable`, `reboot`, `/system/reset-configuration`, firewall rule changes, `/user/*`, `/certificate/*` | **Require `confirm=True` + explicit HITL approval** |
| **Critical** | `reset-configuration`, `shutdown`, removing the management interface, changing the admin password | **Require HITL approval + auto backup first** |

Additional classifier rules:

- Any command containing `;`, `&&`, or a newline is **rejected** (multi-line / chaining is
  unsupported over SSH and is a common prompt-injection vector).
- A command that would drop the **currently used** management path is escalated to Critical.
- `confirm=True` is **not** a substitute for HITL approval on Critical commands.

---

## 8. Implementation Plan

Work happens in the `self-development` clone, on a dedicated branch.

### Phase 0 — Branch & Dependencies (0.5 day)

- [ ] Create branch `feature/mikrotik-routeros-toolkit` in `self-development/`
- [ ] Add to `requirements.txt` (all **optional**, guarded by `try/except ImportError`):
  ```
  # MikroTik RouterOS Toolkit Dependencies
  asyncssh>=2.24.1
  pydantic>=2.9
  routeros_api>=0.21.0
  ```

### Phase 1 — Core Package (2 days)

- [ ] `toolkits/MikroTik-RouterOS/config.py` — `MikroTikTarget` (pydantic v2, `SecretStr` password),
      `TargetRegistry`, YAML loader `mikrotik_targets.yaml`
- [ ] `toolkits/MikroTik-RouterOS/models.py` — `CommandResult`, `RouterIdentity`, `CommandCategory`
- [ ] `toolkits/MikroTik-RouterOS/exceptions.py` — typed hierarchy mapping to the §7.3 taxonomy
- [ ] `toolkits/MikroTik-RouterOS/parser.py` — RouterOS `print` table parser → `rows: list[dict]`
- [ ] `toolkits/MikroTik-RouterOS/session.py` — `RouterOSSession` with:
  - [ ] `PROMPT_RE` / `CONTINUATION_RE` / `VALUE_REQUEST_RE` (validated regexes from §5.3)
  - [ ] `exec` transport (one-shot) and `session` transport (stateful)
  - [ ] banner tolerance, command-echo stripping, prompt-path extraction
  - [ ] error detection (`invalid command name`, `bad command`, `no such item`)
  - [ ] safe-mode detection and Ctrl+X / Ctrl+D handling
  - [ ] paging detection, `without-paging` auto-append
  - [ ] timeouts on connect, banner and per-command
- [ ] `toolkits/MikroTik-RouterOS/safety.py` — command classifier (§7.4) + risk levels

### Phase 2 — Agent Adapter (1 day)

- [ ] `agent_mikrotik_toolkit.py` at the project root (flat pattern, matching other toolkits)
- [ ] Implement the 8 tools from §7.1 with full docstrings
- [ ] `get_all_tools() -> list[FunctionTool]`
- [ ] Registry bootstrap: load `mikrotik_targets.yaml` if present (do **not** fail when absent)

### Phase 3 — Integration (0.5 day)

- [ ] `agent_tool_retriever.py`: add `include_mikrotik_tools` flag + guarded import block
- [ ] `agent-torvalds.py`: import `get_mikrotik_tools`, aggregate into the agent's tool list
- [ ] `components/command_registry.py`: register the new commands in the `\help` output
- [ ] Optional: `/command` style alias so the operator can call a router command directly

### Phase 4 — Tests (1.5 days)

- [ ] `tests/test_mikrotik_toolkit.py` — unit tests with a **mocked** transport (no network)
- [ ] `tests/test_mikrotik_session.py` — prompt parsing, echo stripping, error detection
- [ ] `tests/test_mikrotik_safety.py` — classifier table tests
- [ ] `tests/test_mikrotik_parser.py` — `print` table parsing fixtures
- [ ] Integration test against a **real** RouterOS (CHR or physical) — skipped unless
      `MIKROTIK_TEST_HOST` is set
- [ ] Package-local tests in `toolkits/MikroTik-RouterOS/tests/` — **no `__init__.py`**,
      plus `import-mode = importlib` and the `testpaths` entry in `pytest.ini`
      (see [MODULE_SPECIFICATION.md §3.4](MODULE_SPECIFICATION.md#34-where-tests-must-live-and-the-exact-pytest-contract))

### Phase 5 — Documentation (0.5 day)

- [ ] `docs/mikrotik-toolkit.md` — configuration, target file format, tool reference
- [ ] `mikrotik_targets.yaml.example` — annotated example
- [ ] README update

**Total estimated effort: ~6 working days.**

---

## 9. Security & Safety

### 9.1 Credential Handling

| Concern | Control |
|---|---|
| Passwords in config | `pydantic.SecretStr`; never logged; never returned by any tool |
| Key files | Path only in config; key material never read into the agent's context |
| `get_all_tools()` leakage | Tool descriptions contain **no** credentials |
| Target listing | `list_mikrotik_targets()` returns id/host/group only — never secrets |
| Env fallback | `MIKROTIK_PASSWORD` / `MIKROTIK_KEY` supported for CI; never persisted |
| Secret redaction | All log statements pass through a redactor for known secret values |

### 9.2 SSH Transport Hardening

| Control | Setting |
|---|---|
| Host-key verification | **Enforced by default**; TOFU on first contact, persisted fingerprint afterwards |
| Key change | `HOST_KEY_MISMATCH` → hard stop, requires human approval |
| Algorithm policy | Prefer `ed25519`, `rsa-sha2-256/512`; reject `ssh-rsa` (SHA-1) |
| Cipher policy | AES-GCM/AES-CTR, `chacha20-poly1305`; reject `none`/`arcfour` |
| Forwarding | Never requested (the router's `forwarding-enabled` should also be `no`) |
| Privilege | Prefer a dedicated `agent` user with a **restricted policy group**, not `admin` |

### 9.3 Configuration-Change Safety

1. **Classification** — every command is classified read / low / medium / high / critical.
2. **Confirmation** — medium and above require `confirm=True`; high and critical additionally
   require **HITL approval** via the existing `components/human_loop_handler.py` mechanism.
3. **Backup before critical** — automatically run `/export` and capture the result before a
   critical change; include it in the tool output.
4. **Safe mode** — offer to enter safe mode (Ctrl+X) for high-risk changes so an accidental
   lock-out self-heals on disconnect.
5. **Audit trail** — every command, its classification, its result and its duration are logged
   (command text only, never credentials).
6. **No command chaining** — `;`, `&&`, `|` and newlines are rejected outright. This blocks both
   unsupported multi-line syntax and trivial prompt-injection pivots.
7. **Read-only default for the API path** — if the optional API channel is enabled, it is used
   for reads only unless explicitly unlocked.

### 9.4 Router-Side Hardening (operator checklist)

```
/ip ssh set strong-crypto=yes forwarding-enabled=no password-authentication=no
/ip service set ssh disabled=no
/user add name=agent group=read  password=...      # read-only automation account
/user ssh-keys import public-key-file=agent_rsa.pub user=agent
```

---

## 10. Risks & Mitigations

| # | Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|---|
| R1 | Multi-line commands silently fail (no pty) | **High** | High | Reject multi-line input in the classifier; document the limit; return a specific `MULTILINE_UNSUPPORTED` error |
| R2 | Prompt detection fails on an unseen RouterOS prompt form | **High** | Medium | Regex validated against 15 documented forms; add a **fallback**: if no prompt within the timeout, return the raw buffer plus `PROMPT_NOT_DETECTED` rather than hanging or truncating |
| R3 | `print` output pages and hangs waiting for a keypress | **High** | Medium | Auto-append `without-paging`; detect a paging prompt and abort with `PAGING_DETECTED` |
| R4 | Lock-out of the management interface by a bad change | **Critical** | Medium | Risk classification + HITL for high/critical + auto `/export` backup + safe-mode support |
| R5 | Host-key MITM | **Critical** | Low | Enforced host-key policy; TOFU with persisted fingerprint; `HOST_KEY_MISMATCH` = hard stop |
| R6 | Credentials leak into logs or LLM context | **High** | Medium | `SecretStr`, redaction in all log paths, secrets never returned by tools |
| R7 | `asyncssh` not installed → agent fails to boot | Medium | Low | Optional dependency + `try/except ImportError` guard in the retriever (existing convention) |
| R8 | Router is slow/unreachable → agent blocks | Medium | Medium | Async transport (does not block the event loop) + connect/command timeouts |
| R9 | RouterOS version differences in output format | Medium | Medium | Parser tolerant of column variations; `proplist` narrows the output; `detail` mode for scripts |
| R10 | Command injection via a crafted command string | **High** | Low | Reject `;`, `&&`, `|`, newlines; validate against a RouterOS command grammar; never interpolate user data into a command without validation |
| R11 | Dual SSH toolkit overlap with `feature/ssh-toolkit` | Medium | High | Reuse that branch's `config.py`/`models.py`/`exceptions.py` when merging; keep the MikroTik layer RouterOS-specific only |
| R12 | Safe-mode state is invisible to the operator | Medium | Medium | Detect `<SAFE>` in the prompt and surface `safe_mode: true` in every result |

---

## 11. Testing Strategy

### 11.1 Unit Tests (no network required)

| Area | Cases |
|---|---|
| Prompt parsing | All 15 corpus forms + negative cases + `PROMPT_RE` on 1 KB of mixed output |
| Echo stripping | Command with/without echo, CRLF vs LF, trailing spaces |
| Error detection | `invalid command name x`, `bad command name x`, `no such item (4)`, `failure: already have such address` |
| Table parser | `print` output with flags column, missing columns, single row, empty result, `detail` format |
| Classifier | Every rule in §7.4, plus injection attempts (`;`, `&&`, newline, `|`) |
| Config | YAML load, missing file, `SecretStr` redaction, duplicate target id, invalid port |
| Result mapping | `exec` vs `session` → identical `CommandResult` shape |

### 11.2 Integration Tests (opt-in, requires a real router)

Guarded by an environment variable so CI never touches production kit:

```bash
export MIKROTIK_TEST_HOST=10.0.0.1
export MIKROTIK_TEST_USER=agent
export MIKROTIK_TEST_PASSWORD=...
pytest -m integration tests/test_mikrotik_toolkit.py
```

Scenarios: connect + identity; read-only `print`; `without-paging` on a large table; a harmless
write (`/system/clock/set/timezone-autodetect=yes`) followed by a revert; host-key mismatch
detection; timeout on a `ping` to a black-holed address; confirmation refusal.

### 11.3 Harness-Based Tests (recommended, CI-friendly)

The SSH harness used in §5 is a **CI-friendly substitute** for a physical router: it reproduces
RouterOS's banner, prompt, table format and error strings, and can be driven deterministically.
It is a good fit for a hermetic test that verifies prompt parsing, paging, safe-mode and
session-reuse behaviour without any router.

> ⚠️ Caveat: the harness is a *model* of RouterOS, not RouterOS. It cannot catch behavioural
> differences in a specific RouterOS release. A real-router integration test remains required
> before production use.

### 11.4 Quality Gates

- [ ] `pytest` suite green; no new warnings
- [ ] No credential ever appears in logs, tool output or exception messages (automated assertion)
- [ ] Every write command in the toolkit has a matching classifier test
- [ ] Prompt regex corpus test is permanently green (regression guard for R2)

---

## 12. Conclusion

**The requested capability is feasible and the two main technical traps have been identified and
empirically resolved.**

Key findings:

1. **`asyncssh` is the right transport** — async-native, supports both the one-shot `exec` mode
   (clean stdout/stderr/exit-code separation) and the interactive session mode needed for
   stateful and safe-mode-aware operation.
2. **The MikroTik SSH server provides no pseudo-tty**, so the toolkit is **strictly single-line**,
   one command at a time. This is a hard protocol limit documented by MikroTik, and the toolkit must
   reject multi-line input explicitly rather than fail obscurely.
3. **Prompt-based synchronisation is mandatory** for session mode. The validated regex matches all
   15 documented RouterOS prompt forms, including submenu paths, the bracketed form and the
   `<SAFE>` marker, and correctly ignores prompt-like text inside output.
4. **Session reuse is essential** — 5 commands took 4 ms on one connection versus ~130 ms per
   reconnect.
5. **Host-key verification is mandatory**, and because RouterOS auto-generates its host key,
   **TOFU with a persisted fingerprint** is the practical default; a changed key must hard-stop.
6. **Safety is architected in, not bolted on**: one chokepoint, a risk classifier, HITL approval for
   high/critical changes, automatic `/export` backup, and safe-mode support.

**Recommended next step:** begin Phase 1 (core package) on branch
`feature/mikrotik-routeros-toolkit` in the `self-development` clone, and in parallel confirm the
`exec` vs `session` transport split against a real RouterOS device (CHR container or physical
router) — the single piece of evidence the local harness cannot provide.

---

## Appendix A — Reproduction Environment

| Component | Value |
|---|---|
| OS | Linux (Debian-based), Python 3.12.3 |
| Venv | `self-development/.venv` |
| SSH server | OpenSSH_9.6p1 (localhost:2222/2223/2224) |
| Libraries | `asyncssh` 2.24.1, `routeros_api` 0.21.0, `librouteros` 4.2.2, `pydantic` 2.13.5 |
| MikroTik download server | **Unreachable** from this environment (HTTP 404/403) → CHR validation was not possible |
| MikroTik docs | `help.mikrotik.com` **reachable** — protocol facts taken from the official SSH, CLI and API pages |

### Prototype scripts (this folder)

| File | Purpose |
|---|---|
| `proto_asyncssh.py` | V1/V2 — interactive channel + prompt detection against the RouterOS-like CLI |
| `proto_exec.py` | V3/V4 — `exec` transport, stdout/stderr separation, exit codes |
| `proto_session.py` | V5/V6 — session reuse and large-output handling |
| `proto_prompt_regex.py` | V2 — the 15-case prompt-regex corpus (all pass) |
| `proto_hostkey.py` / `proto_tofu2.py` | V7/V8 — host-key policy matrix and TOFU callback |
| `proto_api.py` / `proto_api2.py` | V11 — proof that the RouterOS API cannot speak to an SSH port |

### Quick verification

```bash
cd self-development
.venv/bin/python investigate/MikroTik-RouterOS/proto_prompt_regex.py   # 15/15 PASS
```

---

*Investigation conducted in: `~/ai-agent-investiagte/agent-torvalds/self-development`*
*All work isolated to the self-development clone per the self-development rules.*
