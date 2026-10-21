"""
MikroTik RouterOS interactive commands.

These are the ``\\routers``-style commands that the operator can type
directly in the REPL, next to the ``\\projects`` and ``\\chat-*`` commands.
They are thin wrappers around the same toolkit functions the agent uses, so
there is exactly one implementation of every operation.

The handler never raises: a failure comes back as a readable message, and a
toolkit that is not installed produces a clear "not available" note instead
of a traceback.

Category: Network
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "is_mikrotik_command",
    "handle_mikrotik_command",
    "MIKROTIK_COMMANDS",
]


#: The commands this module handles, mapped to their argument count.
#:
#: The value is the number of required arguments: 0 means the command takes
#: none, 1 means it takes a target id.
MIKROTIK_COMMANDS: dict[str, int] = {
    "\\routers": 0,
    "\\router-health": 1,
    "\\router-interfaces": 1,
    "\\router-backup": 1,
}


def is_mikrotik_command(cmd: str) -> bool:
    """
    Check whether a command string is a MikroTik command.

    Args:
        cmd: The command string to check.

    Returns:
        True when the command is handled by this module.
    """
    if not cmd:
        return False

    name = cmd.strip().split(" ", 1)[0].lower()
    return name in MIKROTIK_COMMANDS


def _split(cmd: str) -> tuple[str, list[str]]:
    """Split a command into its name and its arguments."""
    parts = (cmd or "").strip().split()
    if not parts:
        return "", []
    return parts[0].lower(), parts[1:]


def _unavailable() -> str:
    """The message shown when the toolkit is not installed."""
    return (
        "The MikroTik RouterOS toolkit is not available in this installation. "
        "Install the optional 'asyncssh' dependency to enable it."
    )


def _format_targets(result: dict) -> str:
    """Render the target list as a Markdown table."""
    targets = result.get("targets") or []

    if not targets:
        return (
            "No MikroTik routers are configured.\n\n"
            "Add them to `mikrotik_targets.yaml` in the repository root, or point "
            "`MIKROTIK_TARGETS` at another configuration file."
        )

    lines = [
        "### MikroTik routers",
        "",
        "| id | host | port | user | group | auth |",
        "|---|---|---|---|---|---|",
    ]
    for target in targets:
        lines.append(
            "| `{id}` | {host} | {port} | {username} | {group} | {auth} |".format(
                id=target.get("id", ""),
                host=target.get("host", ""),
                port=target.get("port", ""),
                username=target.get("username", ""),
                group=target.get("group") or "-",
                auth=target.get("auth", ""),
            )
        )

    lines.append("")
    lines.append(f"**{result.get('count', len(targets))}** router(s) configured.")
    return "\n".join(lines)


def _format_health(result: dict) -> str:
    """Render the health report as Markdown."""
    if not result.get("ok"):
        return f"**Health check failed** (`{result.get('error')}`)\n\n{result.get('message', '')}"

    resources = result.get("resources") or {}
    lines = ["### Router health", ""]

    if resources:
        lines.append("| property | value |")
        lines.append("|---|---|")
        for key in (
            "model",
            "serial_number",
            "routeros_version",
            "uptime",
            "cpu_load",
            "cpu_count",
            "free_memory",
            "total_memory",
            "free_disk",
            "total_disk",
        ):
            value = resources.get(key)
            if value:
                lines.append(f"| {key} | {value} |")
        lines.append("")

    errors = result.get("errors") or []
    if errors:
        lines.append(f"**Recent errors ({len(errors)}):**")
        lines.append("")
        for entry in errors[:20]:
            lines.append(f"- `{entry}`")
    else:
        lines.append("No errors in the recent log.")

    return "\n".join(lines)


def _format_interfaces(result: dict) -> str:
    """Render the interface list as a Markdown table."""
    if not result.get("ok"):
        return (
            f"**Interface query failed** (`{result.get('error')}`)\n\n"
            f"{result.get('message', '')}"
        )

    interfaces = result.get("interfaces") or []

    if not interfaces:
        return "The router reported no interfaces."

    lines = [
        "### Interfaces",
        "",
        "| name | running | disabled | slave | type |",
        "|---|---|---|---|---|",
    ]
    for interface in interfaces:
        lines.append(
            "| {name} | {running} | {disabled} | {slave} | {type} |".format(
                name=interface.get("name", ""),
                running="yes" if interface.get("running") else "no",
                disabled="yes" if interface.get("disabled") else "no",
                slave="yes" if interface.get("slave") else "no",
                type=interface.get("TYPE") or interface.get("type") or "",
            )
        )

    return "\n".join(lines)


def _format_backup(result: dict) -> str:
    """Render the configuration export."""
    if not result.get("ok"):
        return (
            f"**Backup failed** (`{result.get('error')}`)\n\n{result.get('message', '')}"
        )

    config = result.get("config") or ""
    size = result.get("bytes", len(config))

    lines = [
        "### Configuration backup",
        "",
        f"**{size}** bytes exported.",
        "",
        "```",
    ]
    lines.append(config.rstrip())
    lines.append("```")

    return "\n".join(lines)


async def handle_mikrotik_command(cmd: str) -> Optional[str]:
    """
    Handle a MikroTik interactive command.

    Args:
        cmd: The command string, e.g. ``"\\routers"`` or
            ``"\\router-health core-rtr-01"``.

    Returns:
        The Markdown response, or ``None`` when the command is not a
        MikroTik command (the caller then handles it).
    """
    name, args = _split(cmd)

    if name not in MIKROTIK_COMMANDS:
        return None

    try:
        import agent_mikrotik_toolkit as mikrotik
    except ImportError as exc:
        logger.warning("The MikroTik toolkit is not available: %s", exc)
        return _unavailable()

    if not mikrotik.MIKROTIK_AVAILABLE:
        return _unavailable()

    required = MIKROTIK_COMMANDS[name]

    if len(args) < required:
        if name == "\\routers":
            return "Usage: `\\routers`"
        return f"Usage: `{name} <target>`"

    target = args[0] if args else ""

    try:
        if name == "\\routers":
            result = await mikrotik.list_mikrotik_targets()
            return _format_targets(result)

        if name == "\\router-health":
            result = await mikrotik.get_routeros_health(target)
            return _format_health(result)

        if name == "\\router-interfaces":
            result = await mikrotik.get_routeros_interfaces(target)
            return _format_interfaces(result)

        if name == "\\router-backup":
            result = await mikrotik.backup_routeros_config(target)
            return _format_backup(result)

    except Exception as exc:  # noqa: BLE001 - a command must never crash the REPL
        logger.exception("The MikroTik command %s failed", name)
        return f"**Error** running `{name}`: {exc}"

    return None
