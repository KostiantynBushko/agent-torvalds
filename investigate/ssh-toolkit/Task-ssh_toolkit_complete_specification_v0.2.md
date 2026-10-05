# SSH Toolkit

## Complete Architecture and Development Specification

**Version:** 0.1  
**Status:** Design specification  
**Primary package:** `toolkits.ssh_toolkit`  
**Agent adapter:** `agent_ssh_toolkit.py` at project root

## 1. Purpose

`ssh_toolkit` is a reusable, self-contained Python module for secure asynchronous SSH connectivity and remote command execution.

The toolkit has two independent consumption modes:

1. **Standalone Python library** for other application modules and domain-specific toolkits.
2. **Optional LlamaIndex FunctionAgent adapter** exposing carefully documented SSH functions as `FunctionTool` objects.


Pydantic v2 is the standard modeling and validation layer for configuration, public data structures, target metadata, requests, and agent-facing results.

---

## 2. Design Goals

The toolkit should provide:

- reusable SSH connection management;
- async-first command execution;
- password and private-key authentication;
- secure host-key verification;
- connection and command timeouts;
- keepalive support;
- predictable connection cleanup;
- structured results instead of untyped tuples;
- Pydantic v2 validation;
- protection of passwords and other secrets;
- typed toolkit-specific exceptions;
- a registry of logical SSH targets;
- optional LlamaIndex `FunctionTool` integration;
- compatibility with the project's existing `get_all_tools()` convention;
- a clean foundation for use by other toolkits.

---

## 3. Non-Goals

The generic SSH toolkit must not contain:

- Linux-specific business logic;
- device-vendor-specific command interpretation;
- LLM reasoning logic;
- credentials embedded in agent tool descriptions;
- automatic replay of ambiguously interrupted write commands;
- unrestricted secret retrieval functions.

Domain-specific interpretation belongs in the consuming toolkit.

---

## 4. Project Structure

```text
project_root/
|
|-- agent_ssh_toolkit.py
|
|-- toolkits/
|   |-- __init__.py
|   `-- ssh_toolkit/
|       |-- __init__.py
|       |-- config.py
|       |-- models.py
|       |-- exceptions.py
|       |-- registry.py
|       `-- ssh_transport.py
|
`-- tests/
    |-- ssh_toolkit/
    |   |-- test_config.py
    |   |-- test_models.py
    |   |-- test_registry.py
    |   |-- test_ssh_transport.py
    |   `-- integration/
    |       `-- test_real_ssh_server.py
    `-- test_agent_ssh_toolkit.py
```

---

## 5. Dependency Direction

```text
                    Functional Agent
                          |
                          v
                 agent_ssh_toolkit.py
                          |
                    public SSH API
                          |
              +-----------+-----------+
              |                       |
              v                       v
         registry.py             ssh_transport.py
              |                       |
              v                       v
          SSHConfig                SSH server

Higher-level toolkit
              |
              v
         SSHTransport
              |
              v
          SSH server
```

Rules:

- `ssh_toolkit` must not import higher-level toolkits.
- `ssh_transport.py` must not import LlamaIndex.
- `registry.py` must not import LlamaIndex.
- only the project-root `agent_ssh_toolkit.py` imports `FunctionTool` and depends on the LlamaIndex API.
- domain toolkits may import the public `ssh_toolkit` API.

---

## 6. Dependencies

Recommended core dependencies:

```text
pydantic >= 2
asyncssh
```

LlamaIndex is an optional dependency used only by the agent adapter.

Conceptually:

```text
ssh_toolkit core
    pydantic
    asyncssh

ssh_toolkit agent integration
    core dependencies
    llama-index-core
```

The selected SSH library can be changed later if the `SSHTransport` public contract remains stable.

---

## 7. `config.py`

`config.py` defines generic SSH connection configuration.

### 7.1 `SSHConfig`

```python
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class SSHConfig(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    host: str = Field(
        min_length=1,
        description="SSH server hostname or IP address",
    )

    username: str = Field(
        min_length=1,
        description="SSH username",
    )

    password: SecretStr | None = Field(
        default=None,
        description="SSH password",
    )

    port: int = Field(
        default=22,
        ge=1,
        le=65535,
    )

    connect_timeout: float = Field(
        default=10.0,
        gt=0,
    )

    command_timeout: float = Field(
        default=30.0,
        gt=0,
    )

    known_hosts: str | None = None

    client_keys: tuple[str, ...] = ()

    keepalive_interval: float | None = Field(
        default=30.0,
        gt=0,
    )
```

### 7.2 Configuration policy

Configuration models use:

```python
extra="forbid"
```

because a misspelled configuration property should fail immediately.

For example:

```python
SSHConfig(
    host="10.0.0.10",
    username="automation",
    prt=22,
)
```

must fail validation rather than silently ignoring `prt`.

### 7.3 Secret handling

Passwords use Pydantic `SecretStr`.

The actual value should only be unwrapped at the transport boundary:

```python
password = (
    config.password.get_secret_value()
    if config.password
    else None
)
```

Passwords, private key material, and passphrases must not be written to normal logs.

### 7.4 Environment configuration

`SSHConfig` should not directly read environment variables.

The application or dependency-injection layer is responsible for constructing it from:

- environment variables;
- configuration files;
- secret stores;
- database configuration;
- runtime application settings.

This keeps `ssh_toolkit` reusable.

---

## 8. `models.py`

`models.py` defines data contracts used by the standalone library and agent adapter.

### 8.1 `SSHResult`

```python
from pydantic import BaseModel, ConfigDict, Field


class SSHResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stdout: str = ""
    stderr: str = ""
    exit_status: int | None = None

    duration_ms: float | None = Field(
        default=None,
        ge=0,
    )
```

`SSHResult` represents transport-level facts. It does not determine whether output has domain-specific semantic meaning.

### 8.2 `SSHTargetInfo`

Agent-facing target metadata must be non-sensitive.

```python
class SSHTargetInfo(BaseModel):
    target_id: str
    host: str
    port: int
    username: str
```

It must not contain:

- password;
- raw private keys;
- passphrases;
- secret tokens.

### 8.3 `SSHCommandRequest`

```python
class SSHCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    command: str = Field(min_length=1)

    timeout: float | None = Field(
        default=None,
        gt=0,
        le=300,
    )
```

The upper timeout limit is an application policy and can be made configurable later.

### 8.4 Agent error model

```python
class SSHToolError(BaseModel):
    type: str
    message: str
```

### 8.5 Agent command result

```python
class SSHCommandToolResult(BaseModel):
    success: bool
    target: str

    stdout: str = ""
    stderr: str = ""

    exit_status: int | None = None
    duration_ms: float | None = None

    error: SSHToolError | None = None
```

### 8.6 Serialization

Pydantic models provide stable serialization:

```python
result.model_dump()
result.model_dump_json()
result.model_json_schema()
```

This is useful for applications, tests, logging metadata, APIs, and agent integration.

---

## 9. `exceptions.py`

The toolkit translates SSH-client-specific exceptions into a stable toolkit hierarchy.

```python
class SSHToolkitError(Exception):
    """Base exception for the SSH toolkit."""


class SSHConnectionError(SSHToolkitError):
    """SSH connection could not be established or was lost."""


class SSHAuthenticationError(SSHToolkitError):
    """SSH authentication failed."""


class SSHHostKeyError(SSHToolkitError):
    """SSH server host-key validation failed."""


class SSHTimeoutError(SSHToolkitError):
    """SSH connection or command exceeded its timeout."""


class SSHExecutionError(SSHToolkitError):
    """Remote command execution could not be completed."""


class SSHUnknownTargetError(SSHToolkitError):
    """Requested logical SSH target is not registered."""
```

Underlying AsyncSSH or other client-library exception classes should generally not leak from the public API.

---

## 10. `registry.py`

The target registry lets applications expose logical SSH target identifiers without exposing connection credentials to the Functional Agent.

### 10.1 Why a registry is needed

Avoid agent functions such as:

```python
async def execute_ssh_command(
    host: str,
    username: str,
    password: str,
    command: str,
):
    ...
```

Instead use:

```python
async def execute_ssh_command(
    target: str,
    command: str,
):
    ...
```

For example:

```text
linux-server-01 -> SSHConfig(...)
backup-server   -> SSHConfig(...)
```

The LLM receives the logical identifier, not credentials.

### 10.2 Registry API

```python
from .config import SSHConfig
from .exceptions import SSHUnknownTargetError
from .models import SSHTargetInfo


class SSHTargetRegistry:
    def __init__(self) -> None:
        self._targets: dict[str, SSHConfig] = {}

    def register(
        self,
        target_id: str,
        config: SSHConfig,
    ) -> None:
        self._targets[target_id] = config

    def unregister(self, target_id: str) -> None:
        self._targets.pop(target_id, None)

    def get(self, target_id: str) -> SSHConfig:
        try:
            return self._targets[target_id]
        except KeyError as exc:
            raise SSHUnknownTargetError(target_id) from exc

    def list_targets(self) -> list[SSHTargetInfo]:
        return [
            SSHTargetInfo(
                target_id=target_id,
                host=config.host,
                port=config.port,
                username=config.username,
            )
            for target_id, config in self._targets.items()
        ]
```

### 10.3 Registry responsibilities

The registry:

- maps logical IDs to `SSHConfig`;
- provides non-sensitive target metadata;
- hides credential details from the agent;
- raises a typed error for unknown targets.

It should not persist secrets by itself in v0.1. Persistence and secret management remain application concerns.

---

## 11. `ssh_transport.py`

`SSHTransport` owns the protocol-level SSH lifecycle.

### 11.1 Public API

```python
class SSHTransport:
    def __init__(self, config: SSHConfig):
        self.config = config
        self._connection = None

    async def connect(self) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def execute(
        self,
        command: str,
        timeout: float | None = None,
    ) -> SSHResult:
        ...
```

### 11.2 Required capabilities

The transport should support:

- SSH TCP port selection;
- username authentication;
- password authentication;
- private-key authentication;
- server host-key validation;
- connection timeout;
- individual command timeout;
- keepalive;
- command stdout capture;
- command stderr capture;
- exit-status capture when supplied by the server;
- execution-duration measurement;
- deterministic connection cleanup.

### 11.3 Async context manager

Recommended:

```python
async with SSHTransport(config) as transport:
    result = await transport.execute("uname -a")
```

Conceptually:

```python
async def __aenter__(self):
    await self.connect()
    return self


async def __aexit__(self, exc_type, exc, tb):
    await self.disconnect()
```

### 11.4 Lazy connection

A lazy-connect model may be implemented so `execute()` establishes a connection if none exists.

If used, it must have explicit tests and documented behavior.

### 11.5 Transport boundary

The transport knows:

```text
connect
authenticate
execute command
collect output
close
```

It does not know:

```text
whether a Linux command is safe
whether a command changes configuration
what an LLM intended
```

---

## 12. Host-Key Verification

Production usage should validate the remote SSH server identity.

The toolkit must support known-hosts configuration.

Disabling host-key verification, if supported for development, must be an explicit choice. It should never happen silently as the production default.

Host-key failures should become:

```python
SSHHostKeyError
```

---

## 13. Authentication

v0.1 should support:

- password authentication;
- private-key authentication.

Future support may include:

- SSH agent;
- key passphrases;
- certificates;
- agent forwarding.

Authentication failures should become:

```python
SSHAuthenticationError
```

---

## 14. Timeout Model

At least two timeout types must be distinguished.

### 14.1 Connection timeout

Maximum duration for connection establishment:

```python
config.connect_timeout
```

### 14.2 Default command timeout

Default execution duration:

```python
config.command_timeout
```

### 14.3 Per-command override

```python
await transport.execute(
    "long-command",
    timeout=120.0,
)
```

Timeout failures should become:

```python
SSHTimeoutError
```

---

## 15. Connection Reuse and Concurrency

The async-first implementation should allow sequential reuse of an established connection.

Potential future concurrency options include:

- multiple SSH channels through one connection;
- per-connection locks;
- a connection pool.

v0.1 does not require pooling.

Concurrency behavior must be tested before claiming a single `SSHTransport` instance is safe for unrestricted concurrent use.

---

## 16. Reconnection and Retry Policy

Retries must be conservative.

Safe default rules:

1. reconnect before a new command if the existing connection is known to be closed;
2. do not blindly replay a command following an ambiguous mid-execution disconnect;
3. let the domain layer decide whether replay is safe;
4. read-only operations may later opt into controlled retries;
5. write commands require stronger replay/idempotency guarantees.

This separation is important because the generic SSH layer does not know command semantics.

---

## 17. Logging Policy

Logging may include:

- host;
- port;
- username when appropriate;
- target ID;
- command duration;
- success/failure category;
- connection duration.

Logging must not include:

- passwords;
- raw private keys;
- private-key passphrases;
- secret-store values.

Command logging should be configurable because a command string itself may contain sensitive parameters.

---

## 18. Core Public Package API

`toolkits/ssh_toolkit/__init__.py` should expose the supported standalone API.

```python
from .config import SSHConfig
from .models import SSHResult, SSHTargetInfo
from .registry import SSHTargetRegistry
from .ssh_transport import SSHTransport
from .exceptions import (
    SSHToolkitError,
    SSHConnectionError,
    SSHAuthenticationError,
    SSHHostKeyError,
    SSHTimeoutError,
    SSHExecutionError,
    SSHUnknownTargetError,
)

__all__ = [
    "SSHConfig",
    "SSHResult",
    "SSHTargetInfo",
    "SSHTargetRegistry",
    "SSHTransport",
    "SSHToolkitError",
    "SSHConnectionError",
    "SSHAuthenticationError",
    "SSHHostKeyError",
    "SSHTimeoutError",
    "SSHExecutionError",
    "SSHUnknownTargetError",
]
```

`agent_ssh_toolkit.py` lives at the project root and is not part of the `toolkits.ssh_toolkit` package. Therefore the reusable SSH package has no LlamaIndex dependency. Only the root agent adapter depends on the LlamaIndex API.

---

## 19. Standalone Usage

### 19.1 Direct transport use

```python
from toolkits.ssh_toolkit import SSHConfig, SSHTransport


config = SSHConfig(
    host="10.0.0.10",
    username="automation",
    password="secret",
)

async with SSHTransport(config) as ssh:
    result = await ssh.execute("uname -a")

print(result.stdout)
```

### 19.2 Registry use

```python
from toolkits.ssh_toolkit import (
    SSHConfig,
    SSHTargetRegistry,
    SSHTransport,
)


registry = SSHTargetRegistry()

registry.register(
    "linux-server-01",
    SSHConfig(
        host="10.0.0.10",
        username="automation",
        password="secret",
    ),
)

config = registry.get("linux-server-01")

async with SSHTransport(config) as ssh:
    result = await ssh.execute("uptime")
```

No LlamaIndex dependency is required.

---

## 20. Functional Agent Integration

The reusable SSH module can also be exposed to a LlamaIndex FunctionAgent through the project-root adapter:

```text
agent_ssh_toolkit.py
```

This follows the same project convention as existing agent toolkits:

```python
def get_all_tools() -> list[FunctionTool]:
    ...
```

The agent adapter must wrap the core SSH API rather than reimplement SSH.

---

## 21. Agent Adapter Configuration

The agent adapter needs access to an `SSHTargetRegistry`.

A preferred approach is explicit initialization rather than hardcoding credentials in the module.

For example:

```python
_registry: SSHTargetRegistry | None = None


def configure_agent_ssh_toolkit(
    registry: SSHTargetRegistry,
) -> None:
    global _registry
    _registry = registry
```

Application startup:

```python
registry = SSHTargetRegistry()
registry.register("server-01", server_config)
registry.register("router-lab", router_config)

configure_agent_ssh_toolkit(registry)
```

An application dependency container can replace the module-level registry later without changing the agent tool signatures.

---

## 22. Agent-Facing Functions

Recommended v0.1 functions:

### 22.1 `list_ssh_targets()`

Purpose:

- list targets available to the agent;
- help the agent select a target;
- return only non-sensitive metadata.

Signature:

```python
async def list_ssh_targets() -> list[SSHTargetInfo]:
    ...
```

This is a read-only, low-risk operation.

### 22.2 `get_ssh_target_info(target)`

Purpose:

- retrieve non-sensitive metadata for one target.

Signature:

```python
async def get_ssh_target_info(
    target: str,
) -> SSHTargetInfo:
    ...
```

Never return credentials.

### 22.3 `test_ssh_connection(target)`

Purpose:

- verify that a target can be reached and authenticated;
- diagnose SSH connectivity without running an arbitrary administration command.

Signature:

```python
async def test_ssh_connection(
    target: str,
) -> dict:
    ...
```

A future typed model such as `SSHConnectionTestResult` is preferable to a dictionary.

### 22.4 `execute_ssh_command(target, command, timeout)`

Purpose:

- execute a remote command on a registered SSH target.

Signature:

```python
async def execute_ssh_command(
    target: str,
    command: str,
    timeout: float | None = None,
) -> SSHCommandToolResult:
    ...
```

This is a high-risk operation because command behavior depends entirely on the command supplied.

---

## 23. Example Agent Wrapper Implementation

```python
async def execute_ssh_command(
    target: str,
    command: str,
    timeout: float | None = None,
) -> SSHCommandToolResult:
    registry = _require_registry()

    try:
        config = registry.get(target)

        async with SSHTransport(config) as transport:
            result = await transport.execute(
                command,
                timeout=timeout,
            )

        return SSHCommandToolResult(
            success=True,
            target=target,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_status=result.exit_status,
            duration_ms=result.duration_ms,
        )

    except SSHToolkitError as exc:
        return SSHCommandToolResult(
            success=False,
            target=target,
            error=SSHToolError(
                type=exc.__class__.__name__,
                message=str(exc),
            ),
        )
```

The standalone transport continues to use exceptions. The agent boundary translates failures into predictable structured results.

---

## 24. `get_all_tools()` Contract

The adapter should preserve the existing toolkit-loading convention.

```python
import logging

from llama_index.core.tools import FunctionTool


logger = logging.getLogger(__name__)


def get_all_tools() -> list[FunctionTool]:
    """
    Return all SSH tools as FunctionTool objects for on-demand loading.

    Each tool includes category and risk information for better
    retrieval and orchestration.

    Returns:
        list[FunctionTool]: List of SSH FunctionTool objects.
    """

    logger.info("get_all_tools called")

    return [
        FunctionTool.from_defaults(
            fn=list_ssh_targets,
            description=(
                "List SSH targets available to the agent. "
                "Use when selecting a registered remote system. "
                "Does not expose passwords, private keys, or credentials. "
                "Category: SSH. Risk: Read"
            ),
        ),
        FunctionTool.from_defaults(
            fn=get_ssh_target_info,
            description=(
                "Get non-sensitive information about a registered SSH "
                "target, including logical target ID, host, port, and "
                "username. Never returns credentials. "
                "Category: SSH. Risk: Read"
            ),
        ),
        FunctionTool.from_defaults(
            fn=test_ssh_connection,
            description=(
                "Test connectivity and authentication to a registered "
                "SSH target. Use for SSH connection diagnostics. "
                "Does not execute an arbitrary administration command. "
                "Category: SSH. Risk: Read"
            ),
        ),
        FunctionTool.from_defaults(
            fn=execute_ssh_command,
            description=(
                "Execute a remote command on a registered SSH target "
                "and return stdout, stderr, exit status, and duration. "
                "The supplied command may modify or delete remote data. "
                "Use a more specific domain tool when one is available. "
                "Category: SSH. Risk: High"
            ),
        ),
    ]
```

---

## 25. Read-Only Tool Loader

Because arbitrary SSH execution is significantly more powerful than target discovery or connectivity testing, the adapter should optionally provide a restricted loader.

```python
def get_readonly_tools() -> list[FunctionTool]:
    return [
        FunctionTool.from_defaults(
            fn=list_ssh_targets,
            description="...",
        ),
        FunctionTool.from_defaults(
            fn=get_ssh_target_info,
            description="...",
        ),
        FunctionTool.from_defaults(
            fn=test_ssh_connection,
            description="...",
        ),
    ]
```

Then:

```python
def get_all_tools() -> list[FunctionTool]:
    return [
        *get_readonly_tools(),
        FunctionTool.from_defaults(
            fn=execute_ssh_command,
            description="... Risk: High",
        ),
    ]
```

This gives the application a simple security boundary without changing individual tool functions.

---

## 26. Risk Model

Recommended classifications:

| Function | Risk |
|---|---|
| `list_ssh_targets()` | READ |
| `get_ssh_target_info()` | READ |
| `test_ssh_connection()` | READ |
| `execute_ssh_command()` | HIGH |

The command execution tool is high risk because a command can be destructive even if the SSH transport itself is generic.

Future policies may distinguish known read-only commands from writes, but generic shell-command safety cannot be reliably inferred from arbitrary command strings alone.

---

## 27. Agent Tool Selection Policy

A Functional Agent should prefer a more specific domain tool whenever one exists.


```python
list_interfaces()
list_routes()
list_nat_rules()
```

rather than:

```python
execute_ssh_command(
    command="/ip route print",
)
```

Even when both ultimately use `SSHTransport`.

The architecture separates:

```text
transport reuse
```

from:

```text
tool semantics
```

Domain-specific tools provide stronger typing, validation, parsing, risk classification, and predictable results.

---

## 28. Functional Agent Architecture

```text
                       FunctionAgent
                      /            \
                     /              \
                    v                v
                    |                |
                    |                |
                    +-------+--------+
                            |
                            v
                       ssh_toolkit
                            |
                            v
                           SSH
```

The same SSH infrastructure can therefore support both generic administration and specialized domain agents.

---

## 29. Credential Security for Agents

Agent tool inputs must not include SSH passwords or private keys.

Avoid:

```python
execute_ssh_command(
    host="10.0.0.10",
    username="root",
    password="secret",
    command="...",
)
```

Prefer:

```python
execute_ssh_command(
    target="server-01",
    command="...",
)
```

The trusted registry resolves the actual connection configuration.

The agent may be allowed to see:

- logical target ID;
- host or IP if application policy permits;
- port;
- username.

It must not receive secrets from `SSHTargetInfo`.

---

## 30. Command Security

`execute_ssh_command()` is effectively remote code execution on an authorized target.

The application should consider:

- permission-based loading of the tool;
- explicit human approval for high-risk workflows;
- target allowlists;
- command allowlists for constrained deployments;
- server-side least-privilege accounts;
- audit logging;
- command redaction rules;
- execution timeout limits;
- disabling the arbitrary command tool where domain-specific tools are sufficient.

Do not rely on an LLM prompt as the only security control.

---

## 31. Least-Privilege Accounts

The SSH account used for a target should have only the permissions required by its intended workflows.

Examples:

- read-only diagnostic account for monitoring;
- non-root Linux automation user with controlled `sudo` privileges.

The target registry enables different credentials and policies per logical target.

---

## 32. Pydantic and Agent Schemas

Pydantic models provide useful schemas for future agent/API integration:

```python
SSHCommandRequest.model_json_schema()
SSHTargetInfo.model_json_schema()
SSHCommandToolResult.model_json_schema()
```

Even when LlamaIndex derives FunctionTool parameters from function signatures, using Pydantic in the implementation establishes a common validation contract for direct Python, API, test, and agent consumers.

Future write-like or privileged tools should use explicit request models where this improves safety and maintainability.

---

## 33. Testing Strategy

Testing is divided into five levels.

### 33.1 Pydantic model tests

Validate:

- required fields;
- port range;
- positive timeout values;
- forbidden unexpected fields;
- `SecretStr` handling;
- result serialization;
- target metadata never contains credentials.

### 33.2 Registry tests

Validate:

- register;
- replace/update policy;
- unregister;
- get existing target;
- unknown target error;
- list target metadata;
- no credential leakage.

### 33.3 Transport unit tests

Validate:

- successful connection;
- authentication failure;
- host-key failure;
- connection timeout;
- command timeout;
- stdout;
- stderr;
- exit status;
- cleanup;
- context manager;
- disconnected connection behavior;
- error normalization.

### 33.4 SSH integration tests

Use a controlled SSH server to validate real protocol behavior.

Test password and key authentication separately.

### 33.5 Agent adapter tests

Validate:

- `get_all_tools()` returns all expected tools;
- `get_readonly_tools()` excludes arbitrary execution;
- descriptions contain categories and risk classifications;
- unknown targets become structured agent errors;
- credentials never appear in tool results;
- command output is represented correctly;
- the FunctionAgent can select target discovery before execution when appropriate.

---

## 34. Suggested Test Cases

Examples:

```text
"What SSH systems can I access?"
    -> list_ssh_targets

"Can you check whether server-01 accepts SSH connections?"
    -> test_ssh_connection

"What SSH port does router-lab use?"
    -> get_ssh_target_info

"Run uptime on server-01"
    -> execute_ssh_command

```

---

## 35. Development Plan

### Phase 1: Package skeleton

Create:

```text
config.py
models.py
exceptions.py
registry.py
ssh_transport.py
__init__.py
```

Add Pydantic v2 models and tests.

### Phase 2: SSH transport

Implement:

- connection lifecycle;
- password authentication;
- key authentication;
- host-key validation;
- execution;
- stdout/stderr/status capture;
- timeouts;
- structured exceptions.

### Phase 3: Registry

Implement named target management and non-sensitive target information.

### Phase 4: Standalone integration


### Phase 5: Functional Agent adapter

Create:

```text
agent_ssh_toolkit.py
```

Implement:

- `list_ssh_targets()`;
- `get_ssh_target_info()`;
- `test_ssh_connection()`;
- `execute_ssh_command()`;
- `get_readonly_tools()`;
- `get_all_tools()`.

### Phase 6: Security hardening

Add:

- audit events;
- configurable command logging/redaction;
- target policy hooks;
- optional command allowlists;
- application approval hooks for high-risk execution.

### Phase 7: Scalability

If required later, investigate:

- pooled connections;
- concurrent channels;
- persistent registry providers;
- external secret stores;
- per-target policy metadata.

---

## 36. Future Registry Evolution

A future registry entry may combine configuration and policy:

```python
class SSHTarget(BaseModel):
    target_id: str
    config: SSHConfig
    allow_agent_execution: bool = False
    tags: set[str] = set()
```

Sensitive information still must not be returned by agent-facing metadata functions.

Possible target tags:

```text
production
staging
linux
network
router
read-only
high-risk
```

These could support retrieval and authorization in later versions.

---

## 37. Future Policy Interface

A future execution policy could evaluate:

```python
policy.authorize(
    target=target_id,
    operation="execute_ssh_command",
    command=command,
)
```

Possible decisions:

```text
ALLOW
DENY
REQUIRE_APPROVAL
```

Policy belongs above transport so `SSHTransport` remains generic.

---



```python
from toolkits.ssh_toolkit import SSHConfig, SSHTransport
```


```text
      |
      |
SSHTransport
      |
```


---

## 39. Example Application Bootstrap

```python
from toolkits.ssh_toolkit import SSHConfig, SSHTargetRegistry
from agent_ssh_toolkit import (
    configure_agent_ssh_toolkit,
    get_all_tools,
)


registry = SSHTargetRegistry()

registry.register(
    "server-01",
    SSHConfig(
        host="10.0.0.10",
        username="automation",
        password="secret",
    ),
)

registry.register(
    "router-lab",
    SSHConfig(
        host="192.168.88.1",
        username="automation",
        password="router-secret",
    ),
)

configure_agent_ssh_toolkit(registry)

ssh_tools = get_all_tools()
```

The Functional Agent receives the tools, while secret material remains inside trusted application configuration.

---

## 40. v0.1 Public Functions

### Core library

```python
SSHConfig(...)
SSHTransport(...)
SSHTargetRegistry.register(...)
SSHTargetRegistry.unregister(...)
SSHTargetRegistry.get(...)
SSHTargetRegistry.list_targets(...)
```

### Agent adapter

```python
configure_agent_ssh_toolkit(...)
list_ssh_targets(...)
get_ssh_target_info(...)
test_ssh_connection(...)
execute_ssh_command(...)
get_readonly_tools()
get_all_tools()
```

---

## 41. v0.1 Definition of Done

v0.1 is complete when:

- the core module works independently of LlamaIndex;
- Pydantic v2 validates SSH configuration and public data models;
- passwords use `SecretStr`;
- password and private-key authentication are supported;
- host-key verification has a secure, explicit model;
- connection and command timeouts work;
- `SSHResult` consistently returns output/status information;
- transport failures use toolkit-specific exceptions;
- connection cleanup is deterministic;
- `SSHTargetRegistry` manages logical target IDs without leaking credentials;
- the LlamaIndex adapter uses the existing `get_all_tools()` pattern;
- `get_readonly_tools()` provides a restricted alternative;
- agent-facing target information never contains credentials;
- `execute_ssh_command()` is clearly classified as high risk;
- higher-level toolkits can reuse `SSHTransport` directly;
- integration tests succeed against a controlled SSH environment.

---

## 42. Final Architecture Summary

```text
ssh_toolkit/
    config.py
        Pydantic SSHConfig

    models.py
        SSHResult
        SSHTargetInfo
        SSHCommandRequest
        SSHCommandToolResult

    exceptions.py
        stable SSH exception hierarchy

    registry.py
        logical target -> SSHConfig

    ssh_transport.py
        reusable async SSH implementation

project_root/agent_ssh_toolkit.py
    optional LlamaIndex integration
        list_ssh_targets
        get_ssh_target_info
        test_ssh_connection
        execute_ssh_command
        get_readonly_tools
        get_all_tools
```

The architectural rule is:

```text
SSH transport is generic infrastructure.
Agent support is an optional adapter.
Credentials belong to trusted configuration.
Domain-specific tools should be preferred over arbitrary SSH execution.
```
