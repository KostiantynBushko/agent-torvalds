# MikroTik RouterOS Toolkit (`toolkits/MikroTik-RouterOS`)

> **Inspect and configure MikroTik routers over SSH — with a safety model that
> classifies, confirms and gates every write.**

`toolkits/MikroTik-RouterOS/` is the **reusable library half** of the MikroTik
RouterOS feature. It speaks the RouterOS CLI over SSH, parses the output into
structured data, and applies a rule-based risk classifier to every command
before it is allowed to run.

The package contains **no LlamaIndex imports**. That is deliberate: it stays
independently testable, and any Python application can use it as a plain
library. The LlamaIndex adapter — the part that exposes the tools to the agent
— lives at the project root as `agent_mikrotik_toolkit.py` and imports this
package.

```
toolkits/MikroTik-RouterOS/    the reusable library — no LlamaIndex imports
        │
        ▼
agent_mikrotik_toolkit.py      the LlamaIndex adapter — the eight tools
        │
        ▼
agent-torvalds.py / -mw.py     the orchestrators
```

---

## Table of Contents

- [Overview](#overview)
- [Layout](#layout)
- [Importing the package](#importing-the-package)
- [Public API](#public-api)
- [The risk classifier](#the-risk-classifier)
- [The safety model](#the-safety-model)
- [The transports](#the-transports)
- [The command result](#the-command-result)
- [The error taxonomy](#the-error-taxonomy)
- [Configuration](#configuration)
- [Using the library directly](#using-the-library-directly)
- [The agent tools](#the-agent-tools)
- [The interactive commands](#the-interactive-commands)
- [Security](#security)
- [Limitations](#limitations)
- [Testing](#testing)
- [Design documents](#design-documents)

---

## Overview

MikroTik routers expose a full management CLI over SSH. This package drives
that CLI programmatically:

- **Structured reads.** `/ip/address/print` comes back as a list of
  dictionaries, not a wall of ASCII table. The parser handles the column
  flags (`R`, `S`, `X`, `D`), the `;;;` section separators and the wrapped
  `detail` format.
- **A single chokepoint.** Every command that reaches a router passes through
  one classifier, so there is exactly one place where the safety policy lives.
- **No silent writes.** A configuration change needs an explicit `confirm=True`;
  a HIGH or CRITICAL change additionally needs a human approval on the console.
  `confirm=True` is **not** a substitute for that approval.
- **Secrets never leak.** Passwords and key passphrases are held as
  `SecretStr` and scrubbed from every result, log line and exception message.

### Why the design is shaped this way

Two protocol facts, both established empirically during the investigation
(see [Design documents](#design-documents)), drive the whole architecture:

1. **MikroTik's SSH server allocates no pseudo-terminal.** MikroTik's own
   manual states that multi-line commands "will fail" over SSH. The toolkit
   therefore sends **exactly one single-line command** per call and refuses
   `\n`, `;`, `&&`, `|`, `||` and `{ }` outright.
2. **RouterOS is a stateful interactive CLI.** Completion is signalled by the
   **prompt** (`[admin@MikroTik] /ip/route>`, and `<SAFE>` in safe mode), not
   by EOF or a timer. The session transport reads until it sees a prompt.

---

## Layout

```
toolkits/MikroTik-RouterOS/
├── __init__.py          # public API surface + the alias fallback loader
├── config.py            # MikroTikTarget, TargetRegistry, load_targets
├── models.py            # CommandResult, RouterIdentity, CommandCategory
├── exceptions.py        # typed error hierarchy
├── parser.py            # print / detail / identity parsing
├── session.py           # RouterOSSession (exec + session transports)
├── safety.py            # risk classifier + confirmation policy
├── _compat.py           # optional-dependency compatibility layer
├── py.typed             # PEP 561 marker
├── README.md            # this file
└── tests/               # module-local tests (NO __init__.py — see below)
```

| Module | Responsibility |
|---|---|
| `config.py` | The target model, the registry, and the tolerant YAML loader |
| `models.py` | The uniform result shape, the identity model, the risk enum |
| `exceptions.py` | The typed error hierarchy and the `ERROR_CODES` set |
| `parser.py` | Turning RouterOS text output into structured rows |
| `session.py` | The SSH transport: connect, run, read-until-prompt |
| `safety.py` | `classify()` and the confirmation / HITL policy |
| `_compat.py` | A pydantic-free fallback so the package imports without it |

> ⚠️ **The hyphen is not a valid Python identifier.**
> `from toolkits.MikroTik-RouterOS import ...` is a `SyntaxError`. The package
> is reached through the alias that `toolkits/__init__.py` registers — see
> [Importing the package](#importing-the-package).

> ⚠️ **The module-local `tests/` directory must not contain an `__init__.py`.**
> With it, pytest resolves the test module against the *root* `tests` package,
> relative imports fail with "attempted relative import beyond top-level
> package", and a basename collision with a root test file aborts the whole
> collection. The suite also needs `--import-mode=importlib`, which
> `pytest.ini` sets through `addopts`. Full reasoning:
> [MODULE_SPECIFICATION.md §3.4](../../investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md#34-where-tests-must-live-and-the-exact-pytest-contract).

The directory name is **case-sensitive** on Linux/macOS: exactly
`MikroTik-RouterOS` (capital `M`, `T`, `R`, `O`, `S`).

---

## Importing the package

`toolkits/__init__.py` registers an alias that points at the very same package
object, so the hyphenated directory is reachable under a valid identifier:

```python
from toolkits.mikrotik_routeros import MikroTikTarget, classify
import toolkits.mikrotik_routeros as mikrotik_routeros
```

The alias is registered only if the package is actually importable, so
`import toolkits` never fails when the optional toolkit or one of its optional
dependencies is absent.

Two further forms also work:

```python
# Explicit, via importlib
import importlib
mikrotik = importlib.import_module("toolkits.MikroTik-RouterOS")

# The package's own fallback, for pytest's "prepend" import mode
from toolkits.MikroTik-RouterOS import MikroTikTarget
```

Inside the package, only **relative** imports (`from .config import ...`) are
valid. They are the only form that works when the package is loaded through
`importlib.import_module("toolkits.MikroTik-RouterOS")` — an absolute import
would contain the hyphen and be a `SyntaxError`.

---

## Public API

Everything below is re-exported from `toolkits.mikrotik_routeros`.

### Configuration

| Name | Description |
|---|---|
| `MikroTikTarget` | A validated connection target (host, port, credentials, host-key policy, timeouts) |
| `TargetRegistry` | An in-memory registry of targets, keyed by id |
| `load_targets` | The tolerant YAML loader for `mikrotik_targets.yaml` |
| `DEFAULT_TARGETS_PATH` | `"mikrotik_targets.yaml"` |
| `ENV_PASSWORD` / `ENV_KEY` | The environment variables for the credential fallbacks |

### Models

| Name | Description |
|---|---|
| `CommandResult` | The uniform structured result of one RouterOS command |
| `RouterIdentity` | The parsed contents of `/system/resource/print` |
| `CommandCategory` | The risk enum: `READ_ONLY`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |

`CommandCategory` is a `str` enum whose members are **ordered** from least to
most dangerous, so `CommandCategory.HIGH > CommandCategory.LOW` compares
correctly.

### Session

| Name | Description |
|---|---|
| `RouterOSSession` | An async context manager that drives the SSH transport |

### Safety

| Name | Description |
|---|---|
| `classify` | `command -> (CommandCategory, reasons)` |
| `requires_confirmation` | Whether a category needs `confirm=True` |
| `requires_hitl` | Whether a category needs a human approval |
| `contains_injection_patterns` | The injection-like patterns present in a command |
| `is_management_path_change` | Whether a command could drop the management path |

### Errors

`MikroTikError` and its subclasses — see
[the error taxonomy](#the-error-taxonomy).

---

## The risk classifier

`classify()` is the single chokepoint in front of every command that reaches a
router. It answers one question: *how dangerous is this command?*

The rules are applied in this order:

| # | Rule | Result |
|---|---|---|
| 1 | The command contains a newline, a chain operator or a script block | `CRITICAL` — refused outright |
| 2 | The command targets `reset-configuration`, `shutdown`, or sets `password=` | `CRITICAL` |
| 3 | The verb is a **read-only** verb (`print`, `get`, `find`, `monitor`, `export`, `show`, `stats`, `info`) | `READ_ONLY` — regardless of path |
| 4 | The command targets `reboot`, `remove`, `disable`, `/user/*`, `/certificate/*`, `/ip/firewall/*`, `/ip/service/*`, `/tool/fetch`, … | `HIGH` |
| 5 | The command is a change | graded by the property it touches |

Rule 3 comes **before** the change rules, so `/ip/dns/print` is a read and not
a DNS change. Rule 5 grades the change:

| Grade | Properties |
|---|---|
| `LOW` | `comment`, `name`, `note`, `description`, `disabled=no`, `/system/clock`, `/log/*` |
| `MEDIUM` | `mtu`, `address`, `gateway`, `netmask`, `dns-server`, `dhcp-option`, `lease-time`, `distance`, `disabled=yes` (on a non-management path) |
| `MEDIUM` | An unrecognised property — an unknown command is **never** assumed to be a read |

```python
>>> from toolkits.mikrotik_routeros import classify
>>> classify("/system/resource/print")
(<CommandCategory.READ_ONLY: 'READ_ONLY'>, [])
>>> classify("/ip/address/print")
(<CommandCategory.READ_ONLY: 'READ_ONLY'>, [])
>>> classify("/interface/ether1/set/mtu=1500")
(<CommandCategory.MEDIUM: 'MEDIUM'>, ['changes the mtu property'])
>>> classify("/system/reset-configuration")
(<CommandCategory.CRITICAL: 'CRITICAL'>, ['wipes the configuration'])
>>> classify("/ip/address/print; reboot")
(<CommandCategory.CRITICAL: 'CRITICAL'>,
 ['command contains a newline, a chain operator or a script block'])
```

The classifier is a **pre-filter, not a guarantee**. It is rule-based and
deliberately conservative: an unrecognised command that looks like a change is
treated as a change.

---

## The safety model

```
  command
      │
      ▼
  ┌───────────────────────┐
  │ 1. multiline / chain  │──► refused (MULTILINE_UNSUPPORTED)
  └───────────┬───────────┘
              ▼
  ┌───────────────────────┐
  │ 2. classify()         │
  └───────────┬───────────┘
              ▼
   READ_ONLY / LOW ──► runs directly
              │
        MEDIUM ──────► needs confirm=True
              │
    HIGH/CRITICAL ───► needs confirm=True **and** a human approval
              │
              ▼
   ┌───────────────────────┐
  │ 3. management-path    │──► escalate to CRITICAL
  │    check              │
  └───────────┬───────────┘
              ▼
   ┌───────────────────────┐
  │ 4. host-key check     │──► hard stop (HOST_KEY_MISMATCH)
  └───────────┬───────────┘
              ▼
   ┌───────────────────────┐
  │ 5. /export backup     │──► only for CRITICAL, and only *after*
  │    (if approved)       │    the approval
  └───────────┬───────────┘
              ▼
           the router
```

The rules that matter most:

- **`confirm=True` is not an approval.** For a HIGH or CRITICAL command, the
  tool prompts the operator on the console. A timeout is a **refusal**, not an
  approval.
- **A management-path change is escalated.** Disabling, removing or renaming
  the interface that carries the session is escalated to `CRITICAL`, so it
  always takes the strictest path.
- **The backup happens after the approval.** A CRITICAL change takes an
  `/export` first — but only *after* the human has approved it, so a declined
  command never touches the router at all.
- **A host-key mismatch is a hard stop.** It may indicate a man-in-the-middle
  attack or a re-imaged router. It is never retried automatically.
- **The escape hatch is off by default.** `MIKROTIK_SKIP_APPROVAL` skips the
  human approval for unattended runs. It defaults to off, and it only affects
  the HITL step — `confirm=True` is still required.

---

## The transports

The package implements two transports, and `mode="auto"` picks between them.

| Transport | Kind | Used for | Why |
|---|---|---|---|
| `exec` | stateless, one round-trip | read-only commands | The router's error text arrives cleanly separated on stderr, with a real exit code — no heuristics needed |
| `session` | stateful, one CLI context | changes | A sequence of commands shares one context; safe-mode handling and the prompt state are available |

`mode="auto"` selects `exec` for a `READ_ONLY` command and `session` for
everything else. `mode="exec"` and `mode="session"` force the choice. An
unknown mode is treated as `auto` rather than an error — the tool must never
fail because of a mistyped keyword.

### Paging

RouterOS paginated output by default, which would hang an automated session.
The toolkit appends `without-paging` to `print` commands automatically and
reports `PAGING_DETECTED` if a paging prompt still appears.

### Safe mode

RouterOS safe mode rolls back the configuration when the session ends. The
session layer recognises the `<SAFE>` marker in the prompt, reports
`safe_mode=True` on the result, and exposes `enter_safe_mode()` /
`exit_safe_mode(save=...)` for a scripted workflow.

---

## The command result

Every command — successful or not — returns the same shape. A tool never
raises: it returns `ok=False` with a machine-readable error code.

```python
{
    "command": "/system/resource/print",
    "stdout": "uptime: 3d4h5m6s ...",
    "stderr": "",
    "exit_status": 0,
    "duration_ms": 142,
    "transport": "exec",
    "ok": True,
    "error": None,            # machine-readable code on failure
    "rows": [...],            # parsed table rows, when the output was a table
    "safe_mode": False,
    "prompt_path": "/",       # the CLI path the router was in
    "category": "READ_ONLY",  # the risk classification
    "reasons": [],            # why that classification was reached
}
```

`rows` holds the parsed table when the output was a `print` table:

```python
>>> get_routeros_config("core-rtr-01", "/ip/address")
{'ok': True, 'section': '/ip/address', 'count': 2, 'rows': [
    {'address': '10.0.0.1/24', 'network': '10.0.0.0', 'interface': 'ether1'},
    {'address': '192.168.88.1/24', 'network': '192.168.88.0', 'interface': 'bridge'},
]}
```

The `detail` format (one `key=value` block per item) is parsed into the same
row shape, so a caller does not have to care which format was used.

---

## The error taxonomy

Every error carries a **machine-readable** code, so the agent adapter can
return a structured error without parsing prose.

```
MikroTikError
├── AuthError                    AUTH_FAILED
├── HostKeyError                 HOST_KEY_MISMATCH
├── ConnectionError_             UNREACHABLE
├── CommandTimeoutError          TIMEOUT
├── CommandRejectedError         COMMAND_REJECTED
├── MultilineUnsupportedError    MULTILINE_UNSUPPORTED
├── InteractiveInputRequiredError INTERACTIVE_INPUT_REQUIRED
├── SafeModeError                SAFE_MODE_ACTIVE
├── PagingError                  PAGING_DETECTED
└── NotAuthorizedError           NOT_AUTHORIZED
```

Two further codes exist in the taxonomy but are not transport errors, so they
have no dedicated class:

| Code | Meaning |
|---|---|
| `PROMPT_NOT_DETECTED` | The session never saw a RouterOS prompt. Reported through `CommandResult.error` rather than by raising, because the raw buffer is still useful to the caller |
| `UNKNOWN_TARGET` | The requested target id is not in the registry |

The trailing underscore in `ConnectionError_` avoids shadowing the builtin
`ConnectionError`.

---

## Configuration

The routers are described in `mikrotik_targets.yaml` in the repository root.
Copy the annotated example and fill it in:

```bash
cp mikrotik_targets.yaml.example mikrotik_targets.yaml
```

`mikrotik_targets.yaml` is in `.gitignore`, so a real configuration with real
credentials never reaches the repository — only the `.example` file is tracked.

```yaml
targets:
  - id: core-rtr-01
    host: 10.0.0.1
    port: 22
    username: agent
    group: core
    key_path: ~/.ssh/mikrotik_agent_ed25519
    allow_unknown_host_key: false
    connect_timeout: 10
    command_timeout: 30
```

### Target fields

| Field | Default | Description |
|---|---|---|
| `id` | *required* | The logical name. A safe slug: letters, digits, `-`, `_`, `.`; must start with a letter or digit |
| `host` | *required* | Hostname or IP address |
| `port` | `22` | The SSH service port |
| `username` | `admin` | The SSH username. A dedicated restricted account is strongly recommended |
| `password` | - | The password. Held as `SecretStr`, redacted everywhere |
| `key_path` | - | The private key file. Preferred over a password |
| `key_passphrase` | - | The key passphrase. Held as `SecretStr` |
| `group` | - | An optional group name, used to filter the target list |
| `known_hosts` | - | The OpenSSH `known_hosts` file used to verify the host key |
| `allow_unknown_host_key` | `false` | Disables host-key verification. **Never enable this in production** |
| `connect_timeout` | `10` | The connection timeout, in seconds |
| `command_timeout` | `30` | The default command timeout, in seconds |
| `console_login_params` | `c` | The RouterOS console parameters appended as `user+params`. The default `c` disables console colours, which removes ANSI escapes from the output and makes the parsing reliable |

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `MIKROTIK_TARGETS` | `mikrotik_targets.yaml` | The path of the target configuration file |
| `MIKROTIK_PASSWORD` | - | The fallback password for targets that carry none |
| `MIKROTIK_KEY` | - | The fallback private-key path for targets that carry none |

### The loader is tolerant by design

`load_targets()` never raises:

- a missing file yields an **empty registry**;
- a malformed entry is **skipped**, not fatal;
- a broken YAML document yields an empty registry;
- unknown keys are **ignored**, so a config file may carry extra documentation
  fields.

Importing the adapter can therefore never break the agent boot.

---

## Using the library directly

The package is a plain library. Nothing requires LlamaIndex.

```python
import asyncio

from toolkits.mikrotik_routeros import (
    RouterOSSession,
    classify,
    load_targets,
)


async def main() -> None:
    registry = load_targets("mikrotik_targets.yaml")
    target = registry.get("core-rtr-01")
    if target is None:
        raise SystemExit("no such target")

    async with RouterOSSession(target) as session:
        result = await session.run("/system/resource/print")
        print(result.ok, result.rows, result.prompt_path)


asyncio.run(main())
```

Classify a command before you send it:

```python
from toolkits.mikrotik_routeros import classify, requires_confirmation, requires_hitl

category, reasons = classify("/ip/firewall/filter/add")
if requires_confirmation(category):
    ...  # ask the operator
if requires_hitl(category):
    ...  # ask a human
```

The optional dependency is `asyncssh`:

```bash
pip install asyncssh
```

The package imports without it — the agent boots either way, and the toolkit
reports that it is unavailable.

---

## The agent tools

The adapter `agent_mikrotik_toolkit.py` exposes the package to the agent as
eight tools. Each is a coroutine function, so LlamaIndex's `FunctionTool`
detects and awaits it in `acall()`.

| Tool | Purpose |
|---|---|
| `list_mikrotik_targets(group="")` | List the configured routers with their ids, hosts and groups. Never exposes secrets |
| `test_mikrotik_connection(target)` | Check reachability and credentials, and return the RouterOS version and device identity |
| `run_mikrotik_command(target, command, mode, confirm, timeout)` | Run one single-line RouterOS CLI command |
| `get_routeros_config(target, section, detail, timeout)` | Read a configuration section as structured rows |
| `backup_routeros_config(target, timeout)` | Export the full configuration with `/export` and return it as text |
| `get_routeros_identity(target, timeout)` | Model, serial number, RouterOS version, uptime, CPU, memory, disk |
| `get_routeros_interfaces(target, timeout)` | The network interfaces with their state, running and disabled |
| `get_routeros_health(target, timeout)` | CPU load, memory, disk usage and the recent error log entries |

### Integration points

| File | What was added |
|---|---|
| `agent_mikrotik_toolkit.py` | The adapter itself, at the project root (the flat pattern) |
| `agent_tool_retriever.py` | An `include_mikrotik_tools` flag and a guarded import block |
| `agent-torvalds.py` | The tools aggregated into the tool collection |
| `agent-torvalds-mw.py` | The same, for the multi-window orchestrator — the two stay in parity |
| `components/command_registry.py` | The new commands registered, so `\help` lists them |
| `components/mikrotik_commands.py` | The handler behind the interactive commands |

The core package is imported through its alias inside a `try/except`, so a
missing optional dependency degrades gracefully instead of breaking the agent
boot.

---

## The interactive commands

| Command | Description |
|---|---|
| `\routers` | List the configured MikroTik routers and their status |
| `\router-health <target>` | Show the health of a router — CPU, memory, disk |
| `\router-interfaces <target>` | List the network interfaces of a router |
| `\router-backup <target>` | Export the configuration of a router |

They are registered in `components/command_registry.py`, so `\help` lists them
under **"Network Devices (MikroTik RouterOS)"**.

---

## Security

- **Secrets are redacted everywhere.** Passwords and key passphrases are
  `SecretStr` and are scrubbed from every result, log line and exception
  message. `list_mikrotik_targets()` returns a `public_dict()` that contains
  no secret at all.
- **Host-key verification is enforced.** The default is strict, with a
  trust-on-first-use fallback. A mismatch raises `HostKeyError` and stops.
- **`allow_unknown_host_key` is an opt-in insecure mode** and is off by
  default. It exists for a lab router whose key changes on every re-image.
- **The `admin` account is not required.** A dedicated restricted user is
  recommended, so the toolkit is not running with full privileges by default.

### The router-side checklist

Before pointing the agent at a router:

1. Create a dedicated user with only the policies it needs.
2. Restrict that user's access to the management interface.
3. Ensure the SSH service is enabled and reachable.
4. Pin the router's host key into the `known_hosts` file.

---

## Limitations

- **One single-line command per call.** MikroTik's SSH server has no
  pseudo-terminal, so multi-line scripts and block syntax cannot be delivered.
- **No interactive input.** A command that prompts — for example `/password` —
  cannot be driven over a non-interactive channel. It is reported as
  `INTERACTIVE_INPUT_REQUIRED` and the operator must run it manually.
- **The API is not used.** The RouterOS API is a separate protocol and cannot
  speak to an SSH port. Everything here goes over SSH.
- **Not yet validated against real hardware.** The MikroTik download server is
  unreachable from the development environment, so the protocol layer was
  validated against a faithful SSH harness that emulates the RouterOS CLI
  rather than a physical router. The `exec` vs `session` transport split and
  the write-command flows must be confirmed against real hardware before
  production use. The opt-in integration suite is the mechanism for that.

---

## Testing

```bash
cd self-development

# The module-local suite
.venv/bin/python -m pytest toolkits/MikroTik-RouterOS/tests -q

# The project-level suite for the adapter
.venv/bin/python -m pytest tests/test_mikrotik_*.py -q

# The whole suite
.venv/bin/python -m pytest -q
```

| Suite | Count | Location |
|---|---|---|
| Module-local | 180 | `toolkits/MikroTik-RouterOS/tests/` |
| Adapter | 150 | `tests/test_mikrotik_*.py` |
| Integration | opt-in | `tests/test_mikrotik_integration.py` |

The integration suite talks to a **real** router and is skipped unless
`MIKROTIK_TEST_HOST` is set, so the default test run never touches the
network:

```bash
export MIKROTIK_TEST_HOST=10.0.0.1
export MIKROTIK_TEST_USER=agent
export MIKROTIK_TEST_KEY=~/.ssh/mikrotik_agent_ed25519
.venv/bin/python -m pytest tests/test_mikrotik_integration.py -m integration
```

Two executable contracts check the specification itself:

```bash
.venv/bin/python investigate/MikroTik-RouterOS/verify_layout_contract.py   # 20/20
.venv/bin/python investigate/MikroTik-RouterOS/verify_test_contract.py     # 13/13
```

A **FAIL** means the repository violates a contract the document states — the
document is right, the implementation is wrong.

---

## Design documents

The investigation, the specification and the plan live in
[`investigate/MikroTik-RouterOS/`](../../investigate/MikroTik-RouterOS/):

| File | Purpose |
|---|---|
| [MODULE_SPECIFICATION.md](../../investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md) | **Authoritative.** The module layout, the import contract, the per-module implementation rules |
| [INVESTIGATION_REPORT.md](../../investigate/MikroTik-RouterOS/INVESTIGATION_REPORT.md) | The main report: protocol facts, library evaluation, empirical validation, architecture, risks |
| [PROPOSAL_mikrotik_toolkit.md](../../investigate/MikroTik-RouterOS/PROPOSAL_mikrotik_toolkit.md) | The proposal: scope, tool API, safety model, success metrics |
| [IMPLEMENTATION_PLAN.md](../../investigate/MikroTik-RouterOS/IMPLEMENTATION_PLAN.md) | The phase-by-phase plan with exit criteria and open questions |

The end-user reference — installation, configuration, the tool reference, the
safety model, troubleshooting — is in
[docs/mikrotik-toolkit.md](../../docs/mikrotik-toolkit.md).

---

*Part of the Torvalds AI Agent Toolkit. See the
[project README](../../README.md) for the full picture.*
