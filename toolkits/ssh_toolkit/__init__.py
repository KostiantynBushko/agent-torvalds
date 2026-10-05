"""
SSH Toolkit - Secure asynchronous SSH connectivity and remote command execution.

This module provides a reusable, self-contained Python package for secure
async SSH connectivity. It supports:
- Reusable SSH connection management
- Async-first command execution
- Password and private-key authentication
- Secure host-key verification
- Connection and command timeouts
- Keepalive support
- Predictable connection cleanup
- Structured results with Pydantic v2 validation
- Protection of passwords and secrets
- Typed toolkit-specific exceptions
- Registry of logical SSH targets

Pydantic v2 is the standard modeling and validation layer for configuration,
public data structures, target metadata, requests, and agent-facing results.

Usage as standalone library:
    from toolkits.ssh_toolkit import SSHConfig, SSHTransport
    
    config = SSHConfig(host="10.0.0.10", username="automation", password="secret")
    async with SSHTransport(config) as ssh:
        result = await ssh.execute("uname -a")

Usage with registry:
    from toolkits.ssh_toolkit import SSHConfig, SSHTargetRegistry, SSHTransport
    
    registry = SSHTargetRegistry()
    registry.register("server-01", SSHConfig(host="10.0.0.10", username="automation", password="secret"))
    config = registry.get("server-01")
    async with SSHTransport(config) as ssh:
        result = await ssh.execute("uptime")
"""

from .config import SSHConfig
from .models import SSHResult, SSHTargetInfo, SSHCommandRequest, SSHToolError, SSHCommandToolResult
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
    # Configuration
    "SSHConfig",
    # Models
    "SSHResult",
    "SSHTargetInfo",
    "SSHCommandRequest",
    "SSHToolError",
    "SSHCommandToolResult",
    # Registry
    "SSHTargetRegistry",
    # Transport
    "SSHTransport",
    # Exceptions
    "SSHToolkitError",
    "SSHConnectionError",
    "SSHAuthenticationError",
    "SSHHostKeyError",
    "SSHTimeoutError",
    "SSHExecutionError",
    "SSHUnknownTargetError",
]
