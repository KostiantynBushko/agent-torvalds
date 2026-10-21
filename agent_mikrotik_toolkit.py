"""
MikroTik RouterOS Toolkit - SSH-based router configuration and monitoring.

This module is the **LlamaIndex adapter** for the MikroTik RouterOS toolkit.
It is the only place in the feature that knows about LlamaIndex; the reusable
library half lives in ``toolkits/MikroTik-RouterOS/`` and imports no
LlamaIndex code at all.

The adapter exposes eight tools:

============================================  ==========================
Tool                                          Purpose
============================================  ==========================
``list_mikrotik_targets``                     Show the configured routers
``test_mikrotik_connection``                  Verify reachability + auth
``run_mikrotik_command``                      Run one RouterOS CLI command
``get_routeros_config``                       Read a config section
``backup_routeros_config``                    ``/export`` the configuration
``get_routeros_identity``                     Model, serial, version, uptime
``get_routeros_interfaces``                   Interfaces + running state
``get_routeros_health``                       CPU / memory / disk + log
============================================  ==========================

Design decisions
----------------

**One chokepoint.** There is deliberately no free-form "apply this
configuration" tool. Every write goes through :func:`run_mikrotik_command`
with the safety classifier in front of it, so there is exactly one place
where confirmation, auditing and rollback are enforced.

**Structured errors instead of exceptions.** A tool never raises. It
returns a dictionary with ``ok=False`` and a machine-readable ``error`` code
(``AUTH_FAILED``, ``TIMEOUT``, ``COMMAND_REJECTED``, ...), so the model can
react to the failure instead of seeing a Python traceback. This follows the
existing toolkit convention of returning an error payload rather than
raising.

**Async under the hood, sync on the surface.** The transport
(:class:`RouterOSSession`) is asynchronous because ``asyncssh`` is. The tool
functions are declared ``async def``, which LlamaIndex's ``FunctionTool``
natively supports: it detects a coroutine function and awaits it in
``acall()`` - which is exactly the path the agent uses. The synchronous
``call()`` path works too, because LlamaIndex bridges it onto a worker
thread.

**Nothing raises at import time.** The core package is imported through its
alias inside a ``try/except``. A missing optional dependency (``asyncssh``)
degrades to a tool that reports the problem, rather than breaking the agent
boot.

Category: Network
Retriever Keywords: mikrotik, routeros, router, ssh, network, firewall, interface, ip, vlan, dhcp
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core package import - guarded, so a missing optional dependency never
# breaks the agent boot (MODULE_SPECIFICATION.md R3/R5).
# ---------------------------------------------------------------------------
try:
    from toolkits.mikrotik_routeros import (
        CommandCategory,
        CommandResult,
        MikroTikError,
        MikroTikTarget,
        RouterIdentity,
        RouterOSSession,
        TargetRegistry,
        classify,
        contains_injection_patterns,
        is_management_path_change,
        load_targets,
        requires_confirmation,
        requires_hitl,
    )

    MIKROTIK_AVAILABLE = True
    MIKROTIK_IMPORT_ERROR: Optional[str] = None
except Exception as _exc:  # noqa: BLE001 - the toolkit is optional
    MIKROTIK_AVAILABLE = False
    MIKROTIK_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

    # Placeholders so that the module always defines the names below. The
    # tools then report "unavailable" instead of raising NameError.
    CommandCategory = None  # type: ignore[assignment,misc]
    CommandResult = None  # type: ignore[assignment,misc]
    MikroTikError = Exception  # type: ignore[assignment,misc]
    MikroTikTarget = None  # type: ignore[assignment,misc]
    RouterIdentity = None  # type: ignore[assignment,misc]
    RouterOSSession = None  # type: ignore[assignment,misc]
    TargetRegistry = None  # type: ignore[assignment,misc]
    classify = None  # type: ignore[assignment]
    contains_injection_patterns = None  # type: ignore[assignment]
    is_management_path_change = None  # type: ignore[assignment]
    load_targets = None  # type: ignore[assignment]
    requires_confirmation = None  # type: ignore[assignment]
    requires_hitl = None  # type: ignore[assignment]

logger.info(
    "MikroTik toolkit adapter loaded (available=%s)", MIKROTIK_AVAILABLE
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Environment variable that points at the target configuration file.
ENV_TARGETS_PATH = "MIKROTIK_TARGETS"

#: Environment variable that disables the human-in-the-loop approval for
#: HIGH / CRITICAL commands. It exists for unattended runs and for tests.
#: It is **off** by default: a destructive router change always needs a human.
ENV_SKIP_APPROVAL = "MIKROTIK_SKIP_APPROVAL"

#: Environment variable that forces the approval prompt to be answered
#: automatically (used by the test suite).
ENV_APPROVAL_ANSWER = "MIKROTIK_APPROVAL_ANSWER"

#: The target registry. It is populated once at import time from
#: ``mikrotik_targets.yaml`` and can be reloaded by the operator.
_REGISTRY: Optional[Any] = None


def _targets_path() -> str:
    """Return the path of the target configuration file."""
    return os.environ.get(ENV_TARGETS_PATH, "mikrotik_targets.yaml")


def get_registry() -> Any:
    """Return the target registry, loading it on first use.

    The loader is tolerant: a missing or malformed configuration file
    yields an **empty** registry instead of raising, so importing this
    module can never break the agent boot.

    Returns:
        A :class:`TargetRegistry`.
    """
    global _REGISTRY

    if _REGISTRY is None:
        if not MIKROTIK_AVAILABLE:
            _REGISTRY = TargetRegistry() if TargetRegistry is not None else None
        else:
            try:
                _REGISTRY = load_targets(_targets_path())
            except Exception as exc:  # noqa: BLE001 - never break the boot
                logger.warning("Could not load the MikroTik targets: %s", exc)
                _REGISTRY = TargetRegistry()

    return _REGISTRY


def reload_registry() -> Any:
    """Re-read the target configuration file and replace the registry.

    Returns:
        The refreshed :class:`TargetRegistry`.
    """
    global _REGISTRY

    _REGISTRY = None
    return get_registry()


def _resolve_target(target_id: str) -> tuple[Any, Optional[dict]]:
    """Look a target up in the registry.

    Args:
        target_id: The logical target id.

    Returns:
        A tuple ``(target, error)``. Exactly one of the two is ``None``.
        When the target is unknown, *error* is a ready-made result
        dictionary with ``ok=False`` and the code ``UNKNOWN_TARGET``.
    """
    registry = get_registry()
    if registry is None:
        return None, _unavailable_result(
            "the MikroTik toolkit is not available in this installation"
        )

    target = registry.get(target_id)
    if target is None:
        known = ", ".join(t.id for t in registry.list_targets()) or "(none configured)"
        return None, {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "exit_status": None,
            "duration_ms": 0,
            "transport": None,
            "error": "UNKNOWN_TARGET",
            "rows": None,
            "safe_mode": False,
            "prompt_path": None,
            "message": (
                f"unknown target {target_id!r}; configured targets are: {known}"
            ),
        }

    return target, None


# ---------------------------------------------------------------------------
# Result shaping
# ---------------------------------------------------------------------------

#: The keys every tool result carries. The shape is fixed by
#: MODULE_SPECIFICATION.md section 6.2.
_RESULT_KEYS = (
    "ok",
    "stdout",
    "stderr",
    "exit_status",
    "duration_ms",
    "transport",
    "error",
    "rows",
    "safe_mode",
    "prompt_path",
)


def _unavailable_result(message: str) -> dict:
    """Return a result dictionary for "the toolkit is not usable"."""
    return {
        "ok": False,
        "stdout": "",
        "stderr": message,
        "exit_status": None,
        "duration_ms": 0,
        "transport": None,
        "error": "UNREACHABLE",
        "rows": None,
        "safe_mode": False,
        "prompt_path": None,
        "message": message,
    }


def _result_to_dict(result: Any) -> dict:
    """Convert a :class:`CommandResult` into the uniform result shape."""
    payload = {
        "ok": bool(result.ok),
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
        "exit_status": result.exit_status,
        "duration_ms": int(result.duration_ms or 0),
        "transport": result.transport,
        "error": result.error,
        "rows": result.rows,
        "safe_mode": bool(result.safe_mode),
        "prompt_path": result.prompt_path,
    }
    return payload


def _redact(text: str, secrets: Optional[list[str]] = None) -> str:
    """Remove every known secret from *text*.

    The router's own output can echo a value that was part of the command
    (a password, a key passphrase). This helper scrubs those values before
    the text reaches the model, a log line or an exception message
    (MODULE_SPECIFICATION.md R7 / D9).

    Args:
        text: The text to scrub.
        secrets: The secret values to remove. When omitted, the secrets of
            every registered target are used.

    Returns:
        The scrubbed text.
    """
    if not text:
        return text

    values = list(secrets or [])
    if not secrets:
        registry = get_registry()
        if registry is not None:
            for target in registry.list_targets():
                try:
                    values.extend(target.secret_values())
                except Exception:  # noqa: BLE001 - redaction must not fail
                    continue

    for value in values:
        # Never blank out the whole string with an empty secret.
        if value and value in text:
            text = text.replace(value, "***REDACTED***")

    return text


def _error_payload(exc: Exception) -> dict:
    """Turn an exception into the uniform result shape.

    The error code comes from the typed exception hierarchy when the
    exception is one of ours, and falls back to a generic code otherwise.
    The message is redacted, so a secret can never leak through an
    exception message.
    """
    if MIKROTIK_AVAILABLE and isinstance(exc, MikroTikError):
        code = exc.code
        message = exc.message
    else:
        code = "UNREACHABLE"
        message = str(exc)

    message = _redact(message)

    return {
        "ok": False,
        "stdout": "",
        "stderr": message,
        "exit_status": None,
        "duration_ms": 0,
        "transport": None,
        "error": code,
        "rows": None,
        "safe_mode": False,
        "prompt_path": None,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Human-in-the-loop approval
# ---------------------------------------------------------------------------


def _approval_is_disabled() -> bool:
    """Whether the human-in-the-loop approval is disabled by configuration.

    The escape hatch exists for unattended runs. It is off by default: a
    destructive router change always needs a human.
    """
    return os.environ.get(ENV_SKIP_APPROVAL, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _preconfigured_answer() -> Optional[bool]:
    """Return the answer configured through the environment, if any.

    ``MIKROTIK_APPROVAL_ANSWER`` accepts ``yes``/``y``/``true``/``1`` and
    ``no``/``n``/``false``/``0``. It is used by the test suite and by
    unattended runs that have already obtained the approval elsewhere.
    """
    raw = os.environ.get(ENV_APPROVAL_ANSWER, "").strip().lower()
    if not raw:
        return None
    if raw in ("yes", "y", "true", "1", "approve", "approved"):
        return True
    if raw in ("no", "n", "false", "0", "deny", "denied", "reject"):
        return False
    return None


async def _request_approval(command: str, target: Any, reasons: list[str]) -> bool:
    """Ask the operator to approve a HIGH or CRITICAL command.

    The prompt goes through the existing
    :class:`components.console_input_module.ConsoleInputModule`, so the
    approval looks and behaves like every other human-in-the-loop question
    in the agent.

    Args:
        command: The command that is about to run.
        target: The target the command would run on.
        reasons: The human-readable reasons the classifier gave.

    Returns:
        ``True`` when the command may run, ``False`` when it was refused
        (or the prompt timed out - a timeout is a refusal, never an
        approval).
    """
    configured = _preconfigured_answer()
    if configured is not None:
        logger.info(
            "MikroTik approval taken from %s: %s", ENV_APPROVAL_ANSWER, configured
        )
        return configured

    message = (
        f"\nRouterOS command requires approval\n"
        f"  target : {target.id} ({target.host})\n"
        f"  command: {command}\n"
        f"  reason : {'; '.join(reasons) or 'high risk command'}\n"
        f"\nExecute this command on the router? [y/N]"
    )

    try:
        from components.console_input_module import ConsoleInputModule

        timeout = int(os.environ.get("TORVALDS_HITL_TIMEOUT", "30"))
        answer = await ConsoleInputModule.prompt(
            message=message, default="n", timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001 - a failed prompt is a refusal
        logger.warning("The MikroTik approval prompt failed: %s", exc)
        return False

    return str(answer).strip().lower() in ("y", "yes")


# ---------------------------------------------------------------------------
# The safety gate
# ---------------------------------------------------------------------------


def _guard_command(command: str) -> Optional[dict]:
    """Apply the safety rules that do not need a round-trip.

    A multi-line or chained command is refused outright: MikroTik's SSH
    server provides no pseudo-terminal, so it cannot be delivered, and it is
    a common prompt-injection vector.

    Args:
        command: The command to check.

    Returns:
        ``None`` when the command is acceptable, otherwise a result
        dictionary describing the refusal.
    """
    if not command or not command.strip():
        return {
            "ok": False,
            "stdout": "",
            "stderr": "the command is empty",
            "exit_status": None,
            "duration_ms": 0,
            "transport": None,
            "error": "COMMAND_REJECTED",
            "rows": None,
            "safe_mode": False,
            "prompt_path": None,
            "message": "the command is empty",
        }

    patterns = contains_injection_patterns(command)
    if patterns:
        message = (
            "the command contains an unsupported or unsafe construct "
            f"({', '.join(patterns)}); MikroTik's SSH server cannot deliver "
            "a multi-line or chained command"
        )
        return {
            "ok": False,
            "stdout": "",
            "stderr": message,
            "exit_status": None,
            "duration_ms": 0,
            "transport": None,
            "error": "MULTILINE_UNSUPPORTED",
            "rows": None,
            "safe_mode": False,
            "prompt_path": None,
            "message": message,
        }

    return None


def _classify(command: str) -> tuple[Any, list[str]]:
    """Classify the risk of a command, escalating for the management path.

    A command that would drop the currently used management path is
    escalated to CRITICAL, because it would cut the agent off from the
    router mid-change.
    """
    category, reasons = classify(command)

    try:
        if is_management_path_change(command):
            category = CommandCategory.CRITICAL
            reasons = list(reasons) + [
                "the command may drop the management path of the router"
            ]
    except Exception:  # noqa: BLE001 - the escalation is best-effort
        pass

    return category, reasons


async def _take_backup(target: Any, command: str) -> Optional[str]:
    """Export the router's configuration before a critical change.

    The export is the operator's way back: if the change breaks the router,
    the previous configuration is in the result.

    Args:
        target: The router to export.
        command: The command that is about to run. It is only used for the
            log message.

    Returns:
        The exported configuration, or ``None`` when the backup failed.
    """
    try:
        async with RouterOSSession(target) as session:
            result = await session.run("/export", timeout=60)
    except Exception as exc:  # noqa: BLE001 - the caller reports the failure
        logger.warning(
            "The configuration backup before %r failed: %s", command, exc
        )
        return None

    if not result.ok:
        logger.warning(
            "The configuration backup before %r was rejected by the router", command
        )
        return None

    return _redact(result.stdout or "")


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------


async def list_mikrotik_targets(group: str = "") -> dict:
    """
    List the configured MikroTik routers.

    Use this to find out which routers the agent can reach and what their
    logical ids are. The ids are the ``target`` argument of every other
    MikroTik tool.

    No secret is ever returned: only the id, the host, the port, the
    username, the group and the authentication method.

    Args:
        group (str): Optional group name. When given, only the routers in
            that group are listed.

    Returns:
        dict: ``{"ok": True, "targets": [{"id": ..., "host": ...}, ...],
        "count": N, "groups": [...]}``. When no target is configured the
        result is still ``ok=True`` with an empty list.

    Example:
        >>> list_mikrotik_targets()
        {'ok': True, 'targets': [{'id': 'core-rtr-01', 'host': '10.0.0.1'}],
         'count': 1, 'groups': ['core']}

    Keywords: mikrotik, router, targets, list, routers, devices
    """
    registry = get_registry()
    if registry is None:
        return {
            "ok": False,
            "targets": [],
            "count": 0,
            "groups": [],
            "error": "UNREACHABLE",
            "message": "the MikroTik toolkit is not available in this installation",
        }

    try:
        targets = registry.list_targets(group or None)
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        return _error_payload(exc)

    return {
        "ok": True,
        "targets": [target.public_dict() for target in targets],
        "count": len(targets),
        "groups": registry.groups(),
        "error": None,
    }


async def test_mikrotik_connection(target: str) -> dict:
    """
    Check that a MikroTik router is reachable and that the credentials work.

    Use this before anything else when a router does not answer. It reports
    the RouterOS version and the device identity, and it distinguishes the
    common failure modes: unreachable, bad credentials, and a changed host
    key.

    Args:
        target (str): Logical target id from list_mikrotik_targets().

    Returns:
        dict: ``{"ok": True, "identity": {...}, "version": "7.19.4"}`` on
        success. On failure ``ok`` is ``False`` and ``error`` holds a
        machine-readable code (``UNREACHABLE``, ``AUTH_FAILED``,
        ``HOST_KEY_MISMATCH``, ``UNKNOWN_TARGET``).

    Example:
        >>> test_mikrotik_connection("core-rtr-01")
        {'ok': True, 'identity': {'model': 'RB5009UG+S+', ...}}

    Keywords: mikrotik, connection, test, reachable, authenticate, version
    """
    resolved, error = _resolve_target(target)
    if error is not None:
        return error

    try:
        async with RouterOSSession(resolved) as session:
            result = await session.run_exec("/system/resource/print")
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        return _error_payload(exc)

    payload = _result_to_dict(result)
    payload["stdout"] = _redact(payload["stdout"])
    payload["stderr"] = _redact(payload["stderr"])

    if not payload["ok"]:
        payload["message"] = payload["stderr"] or "the router refused the command"
        return payload

    identity = _parse_identity(payload["stdout"])
    payload["identity"] = identity
    payload["version"] = identity.get("routeros_version")
    payload["model"] = identity.get("model")
    payload["serial_number"] = identity.get("serial_number")
    return payload


async def run_mikrotik_command(
    target: str,
    command: str,
    mode: str = "auto",
    confirm: bool = False,
    timeout: int = 30,
) -> dict:
    """
    Run a single RouterOS CLI command on a MikroTik router over SSH.

    Use this to inspect or change the RouterOS configuration, for example
    ``/system/resource/print``, ``/ip/address/print`` or
    ``/interface/ether1/set/mtu=1500``.

    IMPORTANT: MikroTik's SSH server does not support pseudo-terminals, so
    ONLY a single one-line command may be sent. Multi-line scripts and
    block syntax (``{ ... }``) are not supported and are rejected with
    ``MULTILINE_UNSUPPORTED``. Commands that require interactive input
    (for example ``/password``) are not supported either.

    The command is classified before it runs. A read-only command runs
    directly. A configuration change needs ``confirm=True``. A HIGH or
    CRITICAL change additionally needs an explicit human approval, which
    this tool requests on the console - ``confirm=True`` is **not** a
    substitute for that approval.

    Args:
        target (str): Logical target id from list_mikrotik_targets().
        command (str): One single-line RouterOS CLI command. Do not add a
            trailing question mark.
        mode (str): ``"auto"`` (default) picks the stateless transport for
            a read and the stateful one otherwise, ``"exec"`` forces the
            one-shot transport and ``"session"`` forces the stateful one.
        confirm (bool): Must be ``True`` to execute a command that changes
            the configuration.
        timeout (int): Command timeout in seconds (default 30).

    Returns:
        dict: ``{"ok", "stdout", "stderr", "exit_status", "duration_ms",
        "transport", "error", "rows", "safe_mode", "prompt_path",
        "category", "reasons"}``. ``rows`` holds the parsed table when the
        output was a ``print`` table. On failure ``ok`` is ``False`` and
        ``error`` holds a machine-readable code.

    Example:
        >>> run_mikrotik_command("core-rtr-01", "/system/resource/print")
        {'ok': True, 'stdout': 'uptime: 3d4h5m6s ...', 'rows': None, ...}

    Keywords: mikrotik, routeros, command, run, execute, cli, configure, set
    """
    # The command is screened *before* the target is resolved: an unsafe
    # command must be refused regardless of whether the target exists.
    refused = _guard_command(command)
    if refused is not None:
        return refused

    resolved, error = _resolve_target(target)
    if error is not None:
        return error

    category, reasons = _classify(command)

    # A change needs an explicit confirmation from the caller.
    if requires_confirmation(category) and not confirm:
        message = (
            f"the command is classified as {category} "
            f"({'; '.join(reasons) or 'configuration change'}) and was not "
            "executed; re-run it with confirm=True to apply it"
        )
        payload = {
            "ok": False,
            "stdout": "",
            "stderr": message,
            "exit_status": None,
            "duration_ms": 0,
            "transport": None,
            "error": "NOT_AUTHORIZED",
            "rows": None,
            "safe_mode": False,
            "prompt_path": None,
            "message": message,
        }
        payload["category"] = category.value
        payload["reasons"] = reasons
        return payload

    # A HIGH or CRITICAL change needs a human, not just a flag.
    if requires_hitl(category) and not _approval_is_disabled():
        approved = await _request_approval(command, resolved, reasons)
        if not approved:
            message = (
                "the operator did not approve the command; nothing was changed "
                "on the router"
            )
            payload = {
                "ok": False,
                "stdout": "",
                "stderr": message,
                "exit_status": None,
                "duration_ms": 0,
                "transport": None,
                "error": "NOT_AUTHORIZED",
                "rows": None,
                "safe_mode": False,
                "prompt_path": None,
                "message": message,
            }
            payload["category"] = category.value
            payload["reasons"] = reasons
            return payload

    # A CRITICAL change takes a configuration backup first, so the operator
    # always has a copy of the state the router was in before the change.
    # The backup runs *after* the approval: a command the operator declined
    # must not touch the router at all.
    backup: Optional[str] = None
    if category == CommandCategory.CRITICAL:
        backup = await _take_backup(resolved, command)
        if backup is None:
            message = (
                "the configuration backup failed, so the critical command was "
                "not executed; fix the backup first and try again"
            )
            payload = {
                "ok": False,
                "stdout": "",
                "stderr": message,
                "exit_status": None,
                "duration_ms": 0,
                "transport": None,
                "error": "UNREACHABLE",
                "rows": None,
                "safe_mode": False,
                "prompt_path": None,
                "message": message,
            }
            payload["category"] = category.value
            payload["reasons"] = reasons
            return payload

    transport = _pick_transport(mode, category)

    try:
        if transport == "exec":
            async with RouterOSSession(resolved) as session:
                result = await session.run_exec(command, timeout=timeout)
        else:
            async with RouterOSSession(resolved) as session:
                result = await session.run(command, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        payload = _error_payload(exc)
        payload["category"] = category.value
        payload["reasons"] = reasons
        return payload

    payload = _result_to_dict(result)
    payload["stdout"] = _redact(payload["stdout"])
    payload["stderr"] = _redact(payload["stderr"])
    payload["category"] = category.value
    payload["reasons"] = reasons
    payload["command"] = command
    if backup is not None:
        payload["backup"] = backup
    if not payload["ok"] and payload["stderr"]:
        payload["message"] = payload["stderr"]
    return payload


async def get_routeros_config(
    target: str,
    section: str,
    detail: bool = False,
    timeout: int = 30,
) -> dict:
    """
    Read a RouterOS configuration section and return it as structured rows.

    Use this to inspect a part of the router configuration - addresses,
    routes, DHCP leases, firewall rules, DNS records - without parsing the
    raw table yourself.

    The section is a RouterOS path such as ``/ip/address`` or
    ``/ip/dns/static``. The tool appends ``/print`` itself, so the section
    must not contain a verb.

    Args:
        target (str): Logical target id from list_mikrotik_targets().
        section (str): RouterOS configuration path, e.g. ``/ip/address``.
        detail (bool): Use the script-friendly ``detail`` format, which
            prints one ``key=value`` block per item instead of a table.
        timeout (int): Command timeout in seconds (default 30).

    Returns:
        dict: ``{"ok": True, "section": "/ip/address", "rows": [...],
        "count": N, "stdout": "..."}``. Each row is a dictionary keyed by
        the column names. An empty section yields an empty list, not an
        error.

    Example:
        >>> get_routeros_config("core-rtr-01", "/ip/address")
        {'ok': True, 'section': '/ip/address',
         'rows': [{'index': 0, 'address': '10.0.0.1/24'}], 'count': 1}

    Keywords: mikrotik, routeros, config, section, address, route, dhcp, firewall, dns
    """
    if not section or not section.strip():
        message = "the section is empty"
        return {
            "ok": False,
            "stdout": "",
            "stderr": message,
            "exit_status": None,
            "duration_ms": 0,
            "transport": None,
            "error": "COMMAND_REJECTED",
            "rows": None,
            "safe_mode": False,
            "prompt_path": None,
            "message": message,
        }

    path = section.strip()
    if not path.startswith("/"):
        path = "/" + path

    verb = "print detail" if detail else "print"
    command = f"{path}/{verb}"

    refused = _guard_command(command)
    if refused is not None:
        return refused

    resolved, error = _resolve_target(target)
    if error is not None:
        return error

    try:
        async with RouterOSSession(resolved) as session:
            result = await session.run_exec(command, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        return _error_payload(exc)

    payload = _result_to_dict(result)
    payload["stdout"] = _redact(payload["stdout"])
    payload["stderr"] = _redact(payload["stderr"])
    payload["section"] = path

    if not payload["ok"]:
        payload["message"] = payload["stderr"] or "the router refused the command"
        return payload

    rows = payload.get("rows")
    if detail or not rows:
        rows = _parse_rows(payload["stdout"], detail=detail)
    payload["rows"] = rows
    payload["count"] = len(rows)
    return payload


async def backup_routeros_config(target: str, timeout: int = 60) -> dict:
    """
    Export the full MikroTik configuration and return it.

    Use this before a risky change, to have a copy of the configuration
    that can be restored, and to keep a record of what the router looked
    like before the change.

    The export is read-only: it does not modify the router. The output is
    the plain RouterOS ``/export`` text, which can be re-imported with
    ``/import``.

    Args:
        target (str): Logical target id from list_mikrotik_targets().
        timeout (int): Export timeout in seconds (default 60). A full export
            of a large configuration takes noticeably longer than a read.

    Returns:
        dict: ``{"ok": True, "config": "...", "stdout": "...",
        "bytes": N}``. The configuration is in the ``config`` key.

    Example:
        >>> backup_routeros_config("core-rtr-01")
        {'ok': True, 'config': '# oct/03/2026 12:00:00 by RouterOS 7.19.4\\n...',
         'bytes': 8123}

    Keywords: mikrotik, routeros, backup, export, config, save, restore
    """
    command = "/export"

    refused = _guard_command(command)
    if refused is not None:
        return refused

    resolved, error = _resolve_target(target)
    if error is not None:
        return error

    try:
        async with RouterOSSession(resolved) as session:
            result = await session.run(command, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        return _error_payload(exc)

    payload = _result_to_dict(result)
    payload["stdout"] = _redact(payload["stdout"])
    payload["stderr"] = _redact(payload["stderr"])

    if not payload["ok"]:
        payload["message"] = payload["stderr"] or "the router refused the export"
        return payload

    payload["config"] = payload["stdout"]
    payload["bytes"] = len(payload["stdout"])
    return payload


async def get_routeros_identity(target: str, timeout: int = 30) -> dict:
    """
    Read the identity and resource usage of a MikroTik router.

    Use this to find out which device this is: model, serial number,
    RouterOS version, uptime, CPU load, memory and disk.

    Args:
        target (str): Logical target id from list_mikrotik_targets().
        timeout (int): Command timeout in seconds (default 30).

    Returns:
        dict: ``{"ok": True, "identity": {"model": ..., "serial_number": ...,
        "routeros_version": ..., "uptime": ..., "cpu_load": ...},
        "stdout": "..."}``. Properties the router does not publish are
        ``None`` rather than missing.

    Example:
        >>> get_routeros_identity("core-rtr-01")
        {'ok': True, 'identity': {'model': 'RB5009UG+S+',
         'serial_number': 'H...", 'routeros_version': '7.19.4'}}

    Keywords: mikrotik, routeros, identity, model, serial, version, uptime, resource
    """
    resolved, error = _resolve_target(target)
    if error is not None:
        return error

    try:
        async with RouterOSSession(resolved) as session:
            result = await session.run_exec("/system/resource/print", timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        return _error_payload(exc)

    payload = _result_to_dict(result)
    payload["stdout"] = _redact(payload["stdout"])
    payload["stderr"] = _redact(payload["stderr"])

    if not payload["ok"]:
        payload["message"] = payload["stderr"] or "the router refused the command"
        return payload

    identity = _parse_identity(payload["stdout"])
    payload["identity"] = identity
    payload["version"] = identity.get("routeros_version")
    payload["model"] = identity.get("model")
    payload["serial_number"] = identity.get("serial_number")
    payload["uptime"] = identity.get("uptime")
    return payload


async def get_routeros_interfaces(target: str, timeout: int = 30) -> dict:
    """
    List the network interfaces of a MikroTik router and their state.

    Use this to see which interfaces exist, which ones are running, and
    which ones are disabled. A disabled interface is often the reason a
    service is unreachable.

    Args:
        target (str): Logical target id from list_mikrotik_targets().
        timeout (int): Command timeout in seconds (default 30).

    Returns:
        dict: ``{"ok": True, "interfaces": [{"name": "ether1",
        "running": True, "disabled": False, ...}], "count": N,
        "stdout": "..."}``. The ``flags`` field of the RouterOS table is
        decoded into ``running`` and ``disabled``.

    Example:
        >>> get_routeros_interfaces("core-rtr-01")
        {'ok': True, 'interfaces': [{'name': 'ether1', 'running': True}],
         'count': 4}

    Keywords: mikrotik, routeros, interface, ethernet, bridge, vlan, running, disabled
    """
    resolved, error = _resolve_target(target)
    if error is not None:
        return error

    try:
        async with RouterOSSession(resolved) as session:
            result = await session.run_exec("/interface/print", timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        return _error_payload(exc)

    payload = _result_to_dict(result)
    payload["stdout"] = _redact(payload["stdout"])
    payload["stderr"] = _redact(payload["stderr"])

    if not payload["ok"]:
        payload["message"] = payload["stderr"] or "the router refused the command"
        return payload

    rows = payload.get("rows")
    if not rows:
        rows = _parse_rows(payload["stdout"])

    interfaces = _parse_interfaces(rows)
    payload["interfaces"] = interfaces
    payload["count"] = len(interfaces)
    payload["rows"] = rows
    return payload


async def get_routeros_health(target: str, timeout: int = 30) -> dict:
    """
    Read the health of a MikroTik router: CPU, memory, disk and recent errors.

    Use this when a router misbehaves. It combines the resource usage with
    the most recent entries of the router's log, so a resource problem and
    the error that caused it are visible together.

    Args:
        target (str): Logical target id from list_mikrotik_targets().
        timeout (int): Command timeout in seconds (default 30).

    Returns:
        dict: ``{"ok": True, "resources": {...}, "errors": [...],
        "log": "..."}``. ``resources`` holds the identity fields (CPU
        load, memory, disk); ``errors`` holds the recent log lines that
        look like errors.

    Example:
        >>> get_routeros_health("core-rtr-01")
        {'ok': True, 'resources': {'cpu_load': '3%', ...},
         'errors': ['firewall: input chain rule ...']}

    Keywords: mikrotik, routeros, health, cpu, memory, disk, log, errors, status
    """
    resolved, error = _resolve_target(target)
    if error is not None:
        return error

    payload: dict = {
        "ok": True,
        "resources": {},
        "errors": [],
        "log": "",
        "stdout": "",
        "stderr": "",
        "exit_status": None,
        "duration_ms": 0,
        "transport": "exec",
        "error": None,
        "rows": None,
        "safe_mode": False,
        "prompt_path": None,
    }

    try:
        async with RouterOSSession(resolved) as session:
            resource_result = await session.run_exec(
                "/system/resource/print", timeout=timeout
            )
            log_result = await session.run_exec("/log/print", timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - never raise out of a tool
        return _error_payload(exc)

    if not resource_result.ok:
        payload = _result_to_dict(resource_result)
        payload["stdout"] = _redact(payload["stdout"])
        payload["stderr"] = _redact(payload["stderr"])
        payload["message"] = payload["stderr"] or "the router refused the command"
        return payload

    stdout = _redact(resource_result.stdout or "")
    payload["stdout"] = stdout
    payload["duration_ms"] = int(resource_result.duration_ms or 0) + int(
        log_result.duration_ms or 0
    )
    payload["resources"] = _parse_identity(stdout)
    payload["identity"] = payload["resources"]

    log_text = _redact(log_result.stdout or "")
    payload["log"] = log_text
    payload["errors"] = _extract_log_errors(log_text)

    return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pick_transport(mode: str, category: Any) -> str:
    """Decide which transport carries the command.

    A read-only command uses the stateless ``exec`` transport: it is one
    round-trip and its error text arrives cleanly separated on stderr. A
    change uses the stateful ``session`` transport, so that a sequence of
    commands shares one CLI context.
    """
    normalised = (mode or "auto").strip().lower()

    if normalised == "exec":
        return "exec"
    if normalised == "session":
        return "session"
    if normalised not in ("", "auto"):
        # An unknown mode is treated as "auto" rather than an error - the
        # tool must never fail because of a mistyped keyword.
        logger.info("Unknown transport mode %r, falling back to 'auto'", mode)

    if category == CommandCategory.READ_ONLY:
        return "exec"
    return "session"


def _parse_identity(text: str) -> dict:
    """Parse the output of ``/system/resource/print`` into a dictionary."""
    if not MIKROTIK_AVAILABLE:
        return {}

    try:
        from toolkits.mikrotik_routeros.parser import parse_identity

        return parse_identity(text).to_dict()
    except Exception as exc:  # noqa: BLE001 - a parse failure is not fatal
        logger.debug("Could not parse the router identity: %s", exc)
        return {}


def _parse_rows(text: str, detail: bool = False) -> list[dict]:
    """Parse a RouterOS table into rows."""
    if not MIKROTIK_AVAILABLE or not text:
        return []

    try:
        from toolkits.mikrotik_routeros.parser import parse_detail, parse_print_table

        return parse_detail(text) if detail else parse_print_table(text)
    except Exception as exc:  # noqa: BLE001 - a parse failure is not fatal
        logger.debug("Could not parse the router output: %s", exc)
        return []


def _parse_interfaces(rows: Optional[list[dict]]) -> list[dict]:
    """Decode the RouterOS interface table into a friendlier shape."""
    interfaces: list[dict] = []

    for row in rows or []:
        flags = row.get("flags") or []
        name = row.get("NAME") or row.get("name") or row.get("column_0") or ""

        entry = dict(row)
        entry["name"] = name
        entry["running"] = "R" in flags
        entry["disabled"] = "X" in flags
        entry["slave"] = "S" in flags
        entry["dynamic"] = "D" in flags

        interfaces.append(entry)

    return interfaces


def _extract_log_errors(text: str) -> list[str]:
    """Return the log lines that look like errors.

    A RouterOS log line has the shape::

        jan/02 10:00:00 firewall,info input chain accepted

    The *topic* is ``firewall`` and the *level* is the word that follows
    the first comma. A line whose level is not ``info`` or ``debug`` is
    reported as an error.

    A line that does not follow that shape is reported as well: an
    unrecognised log line is more likely to be a problem than a routine
    message, and silently dropping it would hide exactly the thing the
    operator asked to see.
    """
    if not text:
        return []

    errors: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        parts = stripped.split(",", 2)
        if len(parts) < 2:
            # Not a "topic,level message" line - report it anyway.
            errors.append(stripped)
            continue

        level = parts[1].strip().split(" ", 1)[0].strip().lower()

        if level not in ("info", "debug"):
            errors.append(stripped)

    return errors


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def get_all_tools() -> list[FunctionTool]:
    """
    Return all MikroTik RouterOS tools as FunctionTool objects.

    Each tool description ends with ``Category: Network`` so that the
    retriever can group it correctly.

    Returns:
        list[FunctionTool]: List of MikroTik FunctionTool objects.
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=list_mikrotik_targets,
            description=(
                "List the configured MikroTik routers with their ids, hosts and "
                "groups. Use this to find the target id for the other MikroTik "
                "tools. Never exposes secrets. Category: Network"
            ),
        ),
        FunctionTool.from_defaults(
            fn=test_mikrotik_connection,
            description=(
                "Check that a MikroTik router is reachable and that the "
                "credentials work, and return its RouterOS version and device "
                "identity. Use this first when a router does not answer. "
                "Category: Network"
            ),
        ),
        FunctionTool.from_defaults(
            fn=run_mikrotik_command,
            description=(
                "Run a single one-line RouterOS CLI command on a MikroTik router "
                "over SSH, e.g. '/system/resource/print' or '/ip/address/print'. "
                "Multi-line scripts are not supported by the MikroTik SSH server. "
                "Configuration changes are classified: they need confirm=True, and "
                "high-risk changes additionally need a human approval. "
                "Category: Network"
            ),
        ),
        FunctionTool.from_defaults(
            fn=get_routeros_config,
            description=(
                "Read a MikroTik RouterOS configuration section such as "
                "'/ip/address', '/ip/route', '/ip/dhcp-server/lease' or "
                "'/ip/firewall/filter' and return it as structured rows. "
                "Category: Network"
            ),
        ),
        FunctionTool.from_defaults(
            fn=backup_routeros_config,
            description=(
                "Export the full configuration of a MikroTik router with "
                "'/export' and return it as text, for a backup before a risky "
                "change. The export is read-only. Category: Network"
            ),
        ),
        FunctionTool.from_defaults(
            fn=get_routeros_identity,
            description=(
                "Get the identity of a MikroTik router: model, serial number, "
                "RouterOS version, uptime, CPU load, memory and disk. "
                "Category: Network"
            ),
        ),
        FunctionTool.from_defaults(
            fn=get_routeros_interfaces,
            description=(
                "List the network interfaces of a MikroTik router with their "
                "state, including which ones are running and which ones are "
                "disabled. Category: Network"
            ),
        ),
        FunctionTool.from_defaults(
            fn=get_routeros_health,
            description=(
                "Get the health of a MikroTik router: CPU load, memory, disk "
                "usage and the recent error log entries. Use this when the "
                "router misbehaves. Category: Network"
            ),
        ),
    ]


__all__ = [
    "get_all_tools",
    "list_mikrotik_targets",
    "test_mikrotik_connection",
    "run_mikrotik_command",
    "get_routeros_config",
    "backup_routeros_config",
    "get_routeros_identity",
    "get_routeros_interfaces",
    "get_routeros_health",
    "get_registry",
    "reload_registry",
    "MIKROTIK_AVAILABLE",
]
