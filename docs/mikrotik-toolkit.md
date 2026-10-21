# MikroTik RouterOS Toolkit

The MikroTik RouterOS toolkit lets the agent inspect and configure MikroTik
routers over SSH. It is the only toolkit in this repository that talks to a
network device, so it is also the only one with a strict safety model: every
write is classified, confirmed, and - above a risk threshold - approved by a
human.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [The tools](#4-the-tools)
5. [The interactive commands](#5-the-interactive-commands)
6. [The safety model](#6-the-safety-model)
7. [The transport](#7-the-transport)
8. [Limitations](#8-limitations)
9. [Security](#9-security)
10. [Troubleshooting](#10-troubleshooting)
11. [Architecture](#11-architecture)

---

## 1. Overview

The feature has two halves:

```
toolkits/MikroTik-RouterOS/    the reusable library - no LlamaIndex imports
        │
        ▼
agent_mikrotik_toolkit.py      the LlamaIndex adapter - the eight tools
        │
        ▼
agent-torvalds.py / -mw.py     the orchestrators
```

The core package can be used as a plain library by any Python application:

```python
from toolkits.mikrotik_routeros import MikroTikTarget, RouterOSSession

target = MikroTikTarget(id="core-rtr-01", host="10.0.0.1", username="agent")

async with RouterOSSession(target) as session:
    result = await session.run_exec("/system/resource/print")
    print(result.stdout)
```

> The directory name contains a hyphen, which is not a valid Python
> identifier. Import the package through the alias
> `toolkits.mikrotik_routeros`, which `toolkits/__init__.py` registers.
> See [MODULE_SPECIFICATION.md §3](../investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md).

---

## 2. Installation

The SSH transport needs `asyncssh`. It is an **optional** dependency: the
agent boots without it, and the toolkit simply reports that it is
unavailable.

```bash
pip install asyncssh>=2.24.1
```

The validation layer (`pydantic`) and the RouterOS API client
(`routeros_api`) are optional as well. `pydantic` has a built-in fallback
implementation, so the package imports and works without it.

```bash
pip install pydantic>=2.9       # optional - validation layer
pip install routeros_api>=0.21  # optional - a second transport, not used yet
```

---

## 3. Configuration

### 3.1 The target file

The routers are described in `mikrotik_targets.yaml` in the repository root.
Copy the annotated example and fill it in:

```bash
cp mikrotik_targets.yaml.example mikrotik_targets.yaml
```

`mikrotik_targets.yaml` is in `.gitignore`, so a real configuration with real
credentials never reaches the repository. Only the `.example` file is
tracked.

```yaml
targets:
  - id: core-rtr-01
    host: 10.0.0.1
    port: 22
    username: agent
    key_path: ~/.ssh/mikrotik_agent_ed25519
    group: core
    known_hosts: ~/.ssh/known_hosts
    allow_unknown_host_key: false
    connect_timeout: 10
    command_timeout: 30
```

| Field | Default | Meaning |
|---|---|---|
| `id` | *required* | Logical name. Letters, digits, `-`, `_` and `.`; must start with a letter or digit. |
| `host` | *required* | Hostname or IP address. |
| `port` | `22` | SSH port. |
| `username` | `admin` | SSH user. **Use a dedicated restricted account, not `admin`.** |
| `password` | — | Password. Redacted everywhere. |
| `key_path` | — | Private key file. **Preferred over a password.** |
| `key_passphrase` | — | Passphrase of the private key. Redacted everywhere. |
| `group` | — | Group name, used to filter the target list. |
| `known_hosts` | `~/.ssh/known_hosts` | The file used to verify the router's host key. |
| `allow_unknown_host_key` | `false` | Disables the host-key check. **Insecure - never enable in production.** |
| `connect_timeout` | `10` | Connection timeout in seconds. |
| `command_timeout` | `30` | Default command timeout in seconds. |
| `console_login_params` | `c` | RouterOS console parameters, appended as `user+params`. The default `c` disables the console colours. |

### 3.2 Environment variables

| Variable | Purpose |
|---|---|
| `MIKROTIK_TARGETS` | Path of the target file. Defaults to `mikrotik_targets.yaml`. |
| `MIKROTIK_PASSWORD` | Fallback password for targets that do not carry one. |
| `MIKROTIK_KEY` | Fallback private-key path for targets that do not carry one. |
| `MIKROTIK_SKIP_APPROVAL` | Set to `1` to skip the human approval for HIGH / CRITICAL commands. **Off by default.** |
| `MIKROTIK_APPROVAL_ANSWER` | Pre-answers the approval prompt (`yes` / `no`). Used by the test suite and by unattended runs. |

The environment only fills in what the file does **not** provide. A
credential in the file always wins.

### 3.3 The host key

The router's SSH host key is verified against `known_hosts` (the default is
`~/.ssh/known_hosts`). A **changed** host key is a hard stop with the error
code `HOST_KEY_MISMATCH` - it may mean a man-in-the-middle attack, or a
re-imaged router. The toolkit never retries it automatically.

To trust a router for the first time, add it the usual way:

```bash
ssh-keyscan -H 10.0.0.1 >> ~/.ssh/known_hosts
```

---

## 4. The tools

| Tool | Purpose | Transport |
|---|---|---|
| `list_mikrotik_targets(group="")` | List the configured routers. Never exposes a secret. | — |
| `test_mikrotik_connection(target)` | Verify reachability and auth; return the version and the identity. | exec |
| `run_mikrotik_command(target, command, mode="auto", confirm=False, timeout=30)` | Run one RouterOS CLI command. | auto |
| `get_routeros_config(target, section, detail=False, timeout=30)` | Read a config section as structured rows. | exec |
| `backup_routeros_config(target, timeout=60)` | `/export` the configuration and return it. | session |
| `get_routeros_identity(target, timeout=30)` | Model, serial, version, uptime, resources. | exec |
| `get_routeros_interfaces(target, timeout=30)` | Interfaces with their running / disabled state. | exec |
| `get_routeros_health(target, timeout=30)` | CPU, memory, disk and the recent error log. | exec |

> There is deliberately **no** free-form "apply this configuration" tool.
> Every write goes through `run_mikrotik_command` with the safety
> classifier in front of it, so there is exactly **one** chokepoint for
> confirmation, auditing and rollback.

### 4.1 The result shape

Every tool returns the same dictionary:

```python
{"ok": True, "stdout": "...", "stderr": "", "exit_status": 0,
 "duration_ms": 132, "transport": "exec", "error": None, "rows": None,
 "safe_mode": False, "prompt_path": None}
```

`rows` holds the parsed table when the output was a `print` table, and
`error` holds a machine-readable code when `ok` is `False`.

### 4.2 The error codes

| Code | Meaning | What to do |
|---|---|---|
| `AUTH_FAILED` | The credentials were rejected. | Check the target's credentials. Do not retry blindly. |
| `HOST_KEY_MISMATCH` | The stored host key differs. | **Stop.** Possible MITM or a re-imaged router. Needs human approval. |
| `UNREACHABLE` | Timeout, refused, no route. | Check the IP, the port and the firewall. |
| `TIMEOUT` | The command exceeded `timeout`. | Increase the timeout or split the command. |
| `COMMAND_REJECTED` | The router refused the command. | Fix the syntax. |
| `MULTILINE_UNSUPPORTED` | A multi-line or chained command was detected. | Rewrite it as a single line. |
| `INTERACTIVE_INPUT_REQUIRED` | The command asked for a value. | The operator must run it manually. |
| `SAFE_MODE_ACTIVE` | The router is in safe mode. | Leave safe mode explicitly before committing changes. |
| `PAGING_DETECTED` | The output paged despite `without-paging`. | Use a smaller result set. |
| `NOT_AUTHORIZED` | The policy forbids the operation. | Request the approval, or lower the risk. |
| `PROMPT_NOT_DETECTED` | The session never saw a RouterOS prompt. | The connection is probably broken. |
| `UNKNOWN_TARGET` | The target id is not configured. | Check `list_mikrotik_targets()`. |

---

## 5. The interactive commands

The operator can drive the toolkit directly from the REPL, next to the
`\projects` and `\chat-*` commands:

| Command | Purpose |
|---|---|
| `\routers` | List the configured routers. |
| `\router-health <target>` | Show the health of a router. |
| `\router-interfaces <target>` | List the interfaces of a router. |
| `\router-backup <target>` | Export the configuration of a router. |

They work in the classic REPL (`agent-torvalds.py`) and in the multi-window
TUI (`agent-torvalds-mw.py`), and they are listed by `\help` under
**Network Devices (MikroTik RouterOS)**.

---

## 6. The safety model

Every command is classified before it runs. The classification decides what
happens next.

| Risk | Examples | Behaviour |
|---|---|---|
| `READ_ONLY` | `*/print`, `*/get`, `*/find`, `*/monitor`, `*/export` | Executes directly. |
| `LOW` | `*/set` of a comment, `/system/clock`, `/log/*` | Executes directly, and is logged. |
| `MEDIUM` | `*/set` of `mtu`, `comment`, `disabled`, an address change | Needs `confirm=True`. |
| `HIGH` | `remove`, `disable`, `reboot`, the firewall, `/user/*`, `/certificate/*` | Needs `confirm=True` **and** a human approval. |
| `CRITICAL` | `reset-configuration`, `shutdown`, removing the management interface, changing a password | Needs `confirm=True` **and** a human approval, and is escalated when it would drop the management path. |

Three rules cut across the table:

1. **A multi-line or chained command is refused outright**
   (`MULTILINE_UNSUPPORTED`). MikroTik's SSH server provides no
   pseudo-terminal, so such a command cannot be delivered - and it is a
   common prompt-injection vector.
2. **A command that would drop the management path is escalated to
   `CRITICAL`.** Disabling or removing the interface that carries the
   session would cut the agent off from the router mid-change.
3. **`confirm=True` is not a substitute for the human approval.** A
   `CRITICAL` command needs both.

The human approval uses the same console prompt as every other
human-in-the-loop question in the agent. A timeout is a **refusal**, never
an approval.

### 6.1 The safe-mode workflow

RouterOS safe mode (Ctrl+X) keeps the configuration in RAM until it is
committed, so a mistake can be discarded. The session layer exposes
`enter_safe_mode()` and `exit_safe_mode(save=False)`.

The recommended workflow for a risky change is:

1. `backup_routeros_config(target)` - keep the current configuration.
2. Enter safe mode.
3. Apply the change.
4. Check that the router still answers.
5. Leave safe mode **without** saving to discard a change that broke
   something, or with `save=True` to commit it.

---

## 7. The transport

Two transports are available, and `mode="auto"` picks between them.

**`exec`** - a one-shot `ssh host 'command'`. The router's error text
arrives on **stderr** with a non-zero exit status, so stdout and stderr
are cleanly separated without any parsing heuristics. This is the preferred
transport for stateless reads.

**`session`** - one SSH connection, many commands. Required for stateful
operations (a `cd` changes the CLI context) and for commands whose output
must be captured verbatim, such as `/export`.

`mode="auto"` uses `exec` for a read-only command and `session` for a
change, so a sequence of changes shares one CLI context.

### 7.1 Paging

RouterOS pages its output when it does not fit on a screen, and over SSH
there is nobody to press a key. The session layer therefore appends
`without-paging` to every `print` command automatically. If a paging prompt
still appears, the command is aborted with `PAGING_DETECTED` rather than
hanging.

---

## 8. Limitations

**Multi-line commands are not supported.** MikroTik's SSH server provides no
pseudo-terminal. A script block (`{ ... }`), a chained command (`;`, `&&`,
`||`), a pipe (`|`) and a newline are all rejected with
`MULTILINE_UNSUPPORTED`. This is a property of the router, not of the
toolkit - see [INVESTIGATION_REPORT.md §3.2](../investigate/MikroTik-RouterOS/INVESTIGATION_REPORT.md).

**Interactive commands are not supported.** A command that asks for a value
(`/password` and friends) cannot be driven over a non-interactive channel.
The operator has to run it manually.

**The RouterOS API is not used yet.** `routeros_api` is listed as an
optional dependency for a future second transport, but v1 ships SSH only.

---

## 9. Security

**Never use the `admin` account.** Create a dedicated `agent` user in a
restricted policy group, use public-key authentication, and set
`password-authentication=no` on the router.

**Secrets are redacted everywhere.** The password and the key passphrase are
held as `SecretStr` and are scrubbed from every tool result, every log line
and every exception message before they leave the toolkit.

**The host key is verified.** A changed key is a hard stop, not a warning.

**The transport is hardened.** `asyncssh` is used with the host-key check
enabled, the console colours disabled (the `c` login parameter) and a
bounded timeout on every command.

### 9.1 The router-side checklist

- [ ] A dedicated `agent` user with a restricted policy group.
- [ ] `password-authentication=no` - public-key only.
- [ ] The agent's public key is the only authorised key.
- [ ] The `known_hosts` file is populated and read-only to the agent.
- [ ] `/ip/service` does not expose the SSH service to the internet.
- [ ] `allow_unknown_host_key` is `false` everywhere.

---

## 10. Troubleshooting

**"the 'asyncssh' package is required ... but is not installed"**
Install it: `pip install asyncssh`. The agent boots without it, but the
toolkit cannot do anything.

**"unknown target 'core-rtr-01'; configured targets are: (none configured)"**
The target file was not found or is empty. Check that `mikrotik_targets.yaml`
exists in the repository root, or that `MIKROTIK_TARGETS` points at the
right file. The file is looked up relative to the **current working
directory**.

**"the router rejected the credentials for user 'agent'"**
Check the user name and the key. Remember that the login user is
`agent+c` - the `+c` is the console parameter, not part of the name.

**`HOST_KEY_MISMATCH`**
The router's host key changed. This is a hard stop on purpose. If you are
sure the router was re-imaged, remove the old entry and add the new one:
`ssh-keygen -R 10.0.0.1`.

**`MULTILINE_UNSUPPORTED` but the command looks simple**
The command contains a `;`, a `|`, a `{` or a newline. Rewrite it as a
single line.

**`PAGING_DETECTED`**
The result set is too large for the transport. Narrow the query - add a
`where` clause, or read the section in parts.

**The command times out**
Raise the `timeout` argument (or the target's `command_timeout`). A full
`/export` of a large configuration needs noticeably more than 30 seconds.

---

## 11. Architecture

```
agent-torvalds.py
    ▼
agent_tool_retriever.py          (include_mikrotik_tools flag)
    ▼
agent_mikrotik_toolkit.py        (LlamaIndex adapter - the eight tools)
    ▼
toolkits/MikroTik-RouterOS/      (core package - no LlamaIndex imports)
    ├── config.py                (MikroTikTarget, TargetRegistry, load_targets)
    ├── models.py                (CommandResult, RouterIdentity, CommandCategory)
    ├── exceptions.py            (typed error hierarchy)
    ├── parser.py                (print / detail / identity parsing)
    ├── session.py               (RouterOSSession - exec + session transports)
    ├── safety.py                (risk classifier + confirmation policy)
    └── py.typed                 (PEP 561 marker)
```

The core package imports **no** LlamaIndex, which keeps it independently
testable and usable as a plain library. The `asyncssh` and `pydantic`
imports are lazy or guarded, so the package imports cleanly on a machine
where neither is installed.

### 11.1 The tests

| File | Scope |
|---|---|
| `toolkits/MikroTik-RouterOS/tests/` | The package-local suite (180 tests). |
| `tests/test_mikrotik_toolkit.py` | The tool layer with a mocked transport. |
| `tests/test_mikrotik_session.py` | The error taxonomy and the transport contract. |
| `tests/test_mikrotik_safety.py` | The classifier table and the injection patterns. |
| `tests/test_mikrotik_parser.py` | The `print` / `detail` parsing fixtures. |
| `tests/test_mikrotik_config.py` | The YAML loader, the redaction and the validation. |
| `tests/test_mikrotik_integration.py` | The opt-in tests against a real router. |

The integration tests are skipped unless `MIKROTIK_TEST_HOST` is set:

```bash
export MIKROTIK_TEST_HOST=10.0.0.1
export MIKROTIK_TEST_USER=agent
export MIKROTIK_TEST_KEY=~/.ssh/mikrotik_agent_ed25519

pytest tests/test_mikrotik_integration.py -m integration
```

---

*Authoritative design documents:*
[`MODULE_SPECIFICATION.md`](../investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md) ·
[`IMPLEMENTATION_PLAN.md`](../investigate/MikroTik-RouterOS/IMPLEMENTATION_PLAN.md) ·
[`INVESTIGATION_REPORT.md`](../investigate/MikroTik-RouterOS/INVESTIGATION_REPORT.md)
