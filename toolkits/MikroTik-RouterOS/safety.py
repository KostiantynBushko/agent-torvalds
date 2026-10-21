"""
Safety layer: the command risk classifier and the confirmation policy.

The classifier is the single chokepoint in front of every write. It answers
one question - *how dangerous is this command?* - and the policy functions
turn that answer into a decision:

* :func:`requires_confirmation` - must the operator approve the command?
* :func:`requires_hitl` - must the command go through human-in-the-loop?

The classifier is a **pre-filter**, not a guarantee. It is rule-based and
deliberately conservative: an unrecognised command that looks like a change
is treated as a change.

Classification order
--------------------

1. A command containing a newline, a chain operator or a script block is
   refused outright (reported as CRITICAL so no caller can mistake it for a
   harmless read).
2. Explicitly critical targets (``reset-configuration``, ``shutdown``, a
   password change) are CRITICAL.
3. A **read-only verb** (``print``, ``get``, ``find``, ``monitor``,
   ``export``, ``show``, ``stats``) is READ_ONLY - regardless of the path it
   is applied to. This check comes before the change rules, so
   ``/ip/dns/print`` is a read and not a DNS change.
4. Explicitly high-risk targets (``reboot``, ``remove``, ``disable``, the
   firewall, ``/user/*``, ``/certificate/*``) are HIGH.
5. Everything else is a change, and is graded by the property it touches:
   cosmetic properties are LOW, connectivity properties are MEDIUM, and an
   unrecognised property is MEDIUM as well.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .models import CommandCategory

__all__ = [
    "classify",
    "requires_confirmation",
    "requires_hitl",
    "contains_injection_patterns",
    "is_management_path_change",
    "MULTILINE_PATTERNS",
    "READ_ONLY_VERBS",
]


# ---------------------------------------------------------------------------
# Multiline / chaining guard
# ---------------------------------------------------------------------------

#: Patterns that indicate a multi-line or chained command. MikroTik's SSH
#: server provides no pseudo-terminal, so these cannot be delivered - and
#: they are a common prompt-injection vector.
MULTILINE_PATTERNS: tuple[str, ...] = (
    r"\n",
    r"\r",
    r";",
    r"&&",
    r"\|\|",
    r"\|",
    r"\{",
    r"\}",
)

_MULTILINE_RE = re.compile("|".join(MULTILINE_PATTERNS))


def contains_injection_patterns(command: str) -> list[str]:
    """Return the injection-like patterns present in *command*.

    A command that contains any of these is rejected before it reaches the
    router. The returned list names the patterns that matched, so the caller
    can explain *why* the command was refused.

    Args:
        command: The command to inspect.

    Returns:
        A list of human-readable pattern names. Empty when the command is
        clean.
    """
    if not command:
        return []

    found: list[str] = []
    for name, pattern in (
        ("newline", r"[\r\n]"),
        ("semicolon", r";"),
        ("and-chain", r"&&"),
        ("or-chain", r"\|\|"),
        ("pipe", r"\|"),
        ("script-block", r"[{}]"),
        ("backslash-continuation", r"\\\s*$"),
    ):
        if re.search(pattern, command):
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

#: Verbs that never change the configuration.
READ_ONLY_VERBS: frozenset[str] = frozenset(
    {"print", "get", "find", "monitor", "export", "show", "stats", "info", "print-all"}
)

#: Verbs that always change the configuration.
_CHANGE_VERBS: frozenset[str] = frozenset(
    {"set", "add", "remove", "enable", "disable", "unset", "clear", "put", "start", "stop"}
)

#: Properties that only affect presentation - cosmetic, trivially reversible.
_LOW_RISK_PROPERTIES: tuple[str, ...] = (
    "comment",
    "name",
    "note",
    "description",
    "disabled=no",
)

#: Properties that affect connectivity or addressing.
_MEDIUM_RISK_PROPERTIES: tuple[str, ...] = (
    "mtu",
    "actual-mtu",
    "l2mtu",
    "address",
    "gateway",
    "netmask",
    "network",
    "dns-server",
    "dhcp-option",
    "lease-time",
    "distance",
    "target-scope",
    "disabled=yes",
)

#: Targets that are critical no matter what they do.
_CRITICAL_TARGETS: tuple[tuple[str, str], ...] = (
    (r"^/system/reset-configuration", "wipes the configuration"),
    (r"^/system/shutdown", "powers the router down"),
    # A password change is critical wherever it happens - "/user/set/admin/
    # password=..." and "/interface/ether1/set/password=..." included.
    (r"/password=", "changes a password"),
)

#: Targets that are high risk.
_HIGH_RISK_TARGETS: tuple[tuple[str, str], ...] = (
    (r"^/system/reboot", "reboots the router"),
    (r"^/system/user", "changes a user account"),
    (r"^/user/", "changes a user account"),
    (r"^/certificate/", "changes a certificate"),
    (r"^/ip/firewall/", "changes the firewall"),
    (r"^/ip/service/", "changes a service"),
    (r"^/system/script/", "changes a script"),
    (r"^/tool/fetch", "fetches a file from the internet"),
    (r"^/system/ssh/", "changes the SSH service"),
    (r"^/interface/[^/]+/remove", "removes an interface"),
    (r"^/ip/dhcp-server/", "changes the DHCP server"),
    (r"^/queue/", "changes a queue"),
    (r"^/routing/filter", "changes a routing filter"),
)

#: Verbs that are destructive on their own.
_HIGH_RISK_VERBS: tuple[tuple[str, str], ...] = (
    (r"remove", "removes an item"),
    (r"disable", "disables an item"),
)

#: Paths whose changes are cosmetic even though the verb is ``set``.
_LOW_RISK_PATHS: tuple[tuple[str, str], ...] = (
    (r"^/system/clock", "changes the system clock"),
    (r"^/log/", "changes the log"),
    (r"^/system/note", "changes the login note"),
    (r"^/system/scheduler", "changes the scheduler"),
)

#: Interface names that typically carry the management path.
_DEFAULT_MANAGEMENT_INTERFACES = ("ether1", "wan", "lan", "bridge", "sfp", "sfp-sfpplus1")


def _normalise(command: str) -> str:
    """Normalise a command for matching.

    Collapses whitespace and lowercases it. Arguments keep their values; the
    matching patterns are written accordingly.
    """
    if not command:
        return ""
    return " ".join(command.strip().split()).lower()


def _path_of(command: str) -> str:
    """Return the command path (the leading ``/a/b/c`` token), lowercased."""
    text = " ".join((command or "").strip().split())
    if not text:
        return ""
    match = re.match(r"^(/[^\s]*)", text)
    if match:
        return match.group(1).lower()
    return text.lower()


def _verb_of(command: str) -> str:
    """Return the command verb, i.e. the last path segment."""
    path = _path_of(command)
    if not path:
        return ""
    return path.rsplit("/", 1)[-1]


def _properties_of(command: str) -> list[str]:
    """Return the ``name=value`` properties a command sets."""
    return [
        match.group("key")
        for match in re.finditer(r"(?P<key>[A-Za-z0-9_.-]+)=", command or "")
    ]


def _first_match(command: str, table: Iterable[tuple[str, str]]) -> Optional[str]:
    """Return the reason of the first matching rule, or ``None``."""
    path = _path_of(command)
    lowered = _normalise(command)
    for pattern, reason in table:
        if re.search(pattern, path) or re.search(pattern, lowered):
            return reason
    return None


def classify(command: str) -> tuple[CommandCategory, list[str]]:
    """Classify the risk of a RouterOS command.

    Args:
        command: The command to classify.

    Returns:
        A tuple ``(category, reasons)``. ``reasons`` lists the human-readable
        explanations that led to the category; it is empty for a read-only
        command.

    The rules are applied in the order documented in the module docstring.
    An unrecognised command is never classified as read-only.
    """
    if not command or not command.strip():
        return CommandCategory.READ_ONLY, []

    # 1. Multi-line / chaining is refused before anything else.
    if _MULTILINE_RE.search(command):
        return (
            CommandCategory.CRITICAL,
            ["command contains a newline, a chain operator or a script block"],
        )

    # 2. Explicitly critical targets.
    reason = _first_match(command, _CRITICAL_TARGETS)
    if reason:
        return CommandCategory.CRITICAL, [reason]

    verb = _verb_of(command)

    # 3. A read-only verb is a read, whatever path it is applied to.
    if verb in READ_ONLY_VERBS:
        return CommandCategory.READ_ONLY, []

    # 4. Explicitly high-risk targets and verbs.
    reason = _first_match(command, _HIGH_RISK_TARGETS)
    if reason:
        return CommandCategory.HIGH, [reason]

    reason = _first_match(command, _HIGH_RISK_VERBS)
    if reason:
        return CommandCategory.HIGH, [reason]

    # 5. A change - grade it by the property it touches.
    reason = _first_match(command, _LOW_RISK_PATHS)
    if reason:
        return CommandCategory.LOW, [reason]

    properties = _properties_of(command)
    lowered = _normalise(command)

    if properties:
        for prop in properties:
            if prop == "disabled" and re.search(r"/set/disabled=yes", lowered):
                return CommandCategory.HIGH, ["disables an item"]
            if prop == "password":
                return CommandCategory.CRITICAL, ["changes a password"]
        for prop in properties:
            if any(prop == low or lowered.endswith(f"/{low}") for low in _LOW_RISK_PROPERTIES):
                return CommandCategory.LOW, [f"changes the cosmetic property {prop!r}"]
        for prop in properties:
            if prop in _MEDIUM_RISK_PROPERTIES:
                return CommandCategory.MEDIUM, [f"changes the {prop} property"]

    if verb == "set":
        return CommandCategory.MEDIUM, ["changes a configuration value"]
    if verb in ("add", "unset", "clear", "put"):
        return CommandCategory.MEDIUM, [f"adds or modifies an item ({verb})"]

    # 6. Unknown - assume it changes something.
    return CommandCategory.MEDIUM, ["unrecognised command - treated as a configuration change"]


def requires_confirmation(category: CommandCategory) -> bool:
    """Whether a command in this category needs the operator's approval.

    Reads and cosmetic changes run automatically; everything from MEDIUM
    upwards needs an explicit ``confirm=True``.
    """
    return category >= CommandCategory.MEDIUM


def requires_hitl(category: CommandCategory) -> bool:
    """Whether a command in this category needs human-in-the-loop approval.

    Only HIGH and CRITICAL commands need HITL. ``confirm=True`` is **not** a
    substitute for HITL on a CRITICAL command.
    """
    return category >= CommandCategory.HIGH


def is_management_path_change(
    command: str,
    current_interfaces: Optional[Iterable[str]] = None,
) -> bool:
    """Whether the command could drop the currently used management path.

    A command that disables or removes the interface that carries the
    management session would cut the agent off from the router. Such a
    command must be escalated to CRITICAL.

    Args:
        command: The command to inspect.
        current_interfaces: The interfaces currently in use. When omitted, the
            common defaults (``ether1``, ``wan``, ``lan``, ``bridge``) are
            assumed.

    Returns:
        ``True`` when the command touches a management interface in a way
        that could disconnect the session.
    """
    if not command:
        return False

    path = _path_of(command)
    lowered = _normalise(command)

    interfaces = (
        {str(i).strip().lower() for i in current_interfaces}
        if current_interfaces
        else set(_DEFAULT_MANAGEMENT_INTERFACES)
    )
    if not interfaces:
        return False

    # Only an interface-scoped command can change the management path.
    match = re.match(r"^/interface/([^/\s]+)/", path)
    if not match:
        return False

    interface = match.group(1).lower()
    if interface not in interfaces:
        return False

    # Disabling, removing or renaming the interface is what drops the path.
    if re.search(r"/set/disabled=yes", lowered):
        return True
    if re.search(r"^/interface/[^/]+/remove", lowered):
        return True
    if re.search(r"/set/name=", lowered):
        return True
    if re.search(r"/set/actual-mtu=0", lowered):
        return True

    return False
