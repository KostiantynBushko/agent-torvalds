"""
Data models for the MikroTik RouterOS toolkit.

Three model groups live here:

``CommandResult``
    The uniform result of a single RouterOS command. Its shape is fixed by
    the investigation report (§6.4) and is the contract between the core
    package and the agent adapter.
``RouterIdentity``
    The parsed contents of ``/system/resource/print``.
``CommandCategory``
    The risk classification of a command, produced by :mod:`.safety`.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from ._compat import BaseModel, Field

__all__ = [
    "CommandResult",
    "CommandCategory",
    "RouterIdentity",
]


class CommandCategory(str, Enum):
    """Risk category of a RouterOS command.

    The ordering is meaningful: the categories are ordered from least to most
    dangerous, so ``CommandCategory.HIGH > CommandCategory.LOW`` compares
    correctly even though the enum is a ``str`` subclass.
    """

    #: Pure reads (``*/print``, ``*/get``, ``*/find``, ``*/monitor``, ``*/export``).
    READ_ONLY = "READ_ONLY"

    #: Cosmetic changes (``*/set`` of a comment, ``/system/clock``, ``/log/*``).
    LOW = "LOW"

    #: Changes that affect connectivity but are easily reversible
    #: (``mtu``, ``disabled``, address changes).
    MEDIUM = "MEDIUM"

    #: Destructive or security-relevant changes
    #: (``remove``, ``reboot``, firewall rules, ``/user/*``, ``/certificate/*``).
    HIGH = "HIGH"

    #: Changes that can destroy the device or cut off the management path
    #: (``reset-configuration``, ``shutdown``, removing the management interface).
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        """Numeric rank of this category, lowest risk first."""
        return _CATEGORY_ORDER[self]

    def __lt__(self, other: object) -> bool:
        if isinstance(other, CommandCategory):
            return self.rank < other.rank
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, CommandCategory):
            return self.rank <= other.rank
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, CommandCategory):
            return self.rank > other.rank
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, CommandCategory):
            return self.rank >= other.rank
        return NotImplemented


_CATEGORY_ORDER: dict[CommandCategory, int] = {
    CommandCategory.READ_ONLY: 0,
    CommandCategory.LOW: 1,
    CommandCategory.MEDIUM: 2,
    CommandCategory.HIGH: 3,
    CommandCategory.CRITICAL: 4,
}


class CommandResult(BaseModel):
    """The uniform result of one RouterOS command.

    Attributes:
        command: The command that was issued.
        stdout: Standard output as returned by the router.
        stderr: Standard error. In ``exec`` mode the router's error text
            arrives here with a non-zero exit status, which gives a clean
            separation without parsing heuristics.
        exit_status: The router's exit code. ``None`` in session mode, where
            the status is inferred.
        duration_ms: Wall-clock duration of the command in milliseconds.
        transport: Which transport carried the command.
        ok: ``True`` when the command succeeded.
        error: Machine-readable error code (``AUTH_FAILED``, ``TIMEOUT``, ...)
            or ``None``.
        rows: Parsed table rows when the output was a ``print`` table.
        safe_mode: ``True`` when the router is in safe mode.
        prompt_path: The CLI path the router was in, e.g. ``"/ip/route"``.
    """

    command: str = Field(description="The command that was issued")
    stdout: str = Field(default="", description="Standard output from the router")
    stderr: str = Field(default="", description="Standard error from the router")
    exit_status: Optional[int] = Field(default=None, description="Router exit code")
    duration_ms: int = Field(default=0, description="Wall-clock duration in milliseconds")
    transport: str = Field(default="session", description="Transport: 'exec' or 'session'")
    ok: bool = Field(default=True, description="True when the command succeeded")
    error: Optional[str] = Field(default=None, description="Machine-readable error code")
    rows: Optional[list[dict]] = Field(default=None, description="Parsed table rows")
    safe_mode: bool = Field(default=False, description="True when the router is in safe mode")
    prompt_path: Optional[str] = Field(default=None, description="CLI path, e.g. '/ip/route'")

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of this result."""
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_status": self.exit_status,
            "duration_ms": self.duration_ms,
            "transport": self.transport,
            "ok": self.ok,
            "error": self.error,
            "rows": self.rows,
            "safe_mode": self.safe_mode,
            "prompt_path": self.prompt_path,
        }


class RouterIdentity(BaseModel):
    """The parsed contents of ``/system/resource/print``.

    Every field is optional because the exact set of properties printed by
    ``/system/resource/print`` varies between RouterOS versions and between
    device models. Missing values are simply ``None``.
    """

    model: Optional[str] = Field(default=None, description="Hardware model name")
    serial_number: Optional[str] = Field(default=None, description="Device serial number")
    routeros_version: Optional[str] = Field(default=None, description="RouterOS version string")
    firmware_version: Optional[str] = Field(default=None, description="Firmware version")
    uptime: Optional[str] = Field(default=None, description="Uptime, e.g. '3d4h5m6s'")
    cpu_load: Optional[str] = Field(default=None, description="CPU load percentage")
    cpu_count: Optional[str] = Field(default=None, description="Number of CPU cores")
    cpu_frequency: Optional[str] = Field(default=None, description="CPU frequency")
    free_memory: Optional[str] = Field(default=None, description="Free memory")
    total_memory: Optional[str] = Field(default=None, description="Total memory")
    free_disk: Optional[str] = Field(default=None, description="Free disk space")
    total_disk: Optional[str] = Field(default=None, description="Total disk space")
    board_name: Optional[str] = Field(default=None, description="Board name")
    architecture: Optional[str] = Field(default=None, description="CPU architecture")

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation of this identity."""
        return {
            "model": self.model,
            "serial_number": self.serial_number,
            "routeros_version": self.routeros_version,
            "firmware_version": self.firmware_version,
            "uptime": self.uptime,
            "cpu_load": self.cpu_load,
            "cpu_count": self.cpu_count,
            "cpu_frequency": self.cpu_frequency,
            "free_memory": self.free_memory,
            "total_memory": self.total_memory,
            "free_disk": self.free_disk,
            "total_disk": self.total_disk,
            "board_name": self.board_name,
            "architecture": self.architecture,
        }
