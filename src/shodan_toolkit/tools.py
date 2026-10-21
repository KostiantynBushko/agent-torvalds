"""
LlamaIndex ``FunctionTool`` wrappers around the Shodan CLI.

Every function in this module is a *tool* in the LlamaIndex sense: it has a
type-annotated signature and a docstring, and :func:`get_all_tools` converts
them into :class:`llama_index.core.tools.FunctionTool` objects that a
``FunctionAgent`` can call.

Two categories of tools are exposed:

* **Read-only** — searching, looking up hosts, statistics, DNS.  These are
  safe to expose to an autonomous agent.
* **Mutating** — creating/deleting alerts and submitting scans.  These consume
  credits or change account state, so they are excluded from the default
  read-only toolset and must be opted into explicitly.

Tools never raise: failures are returned as a JSON payload with ``"success":
false`` so the agent can reason about the problem and try something else.
"""

from __future__ import annotations

import functools
import json
import logging
from collections.abc import Sequence
from typing import Any, Callable, Dict, List, Optional

from .client import ShodanClient
from .config import load_config
from .runner import ShodanError

logger = logging.getLogger(__name__)

__all__ = [
    "get_all_tools",
    "get_readonly_tools",
    "get_mutating_tools",
    "get_tools_by_name",
    "set_client",
    "get_client",
    "TOOL_REGISTRY",
    "ToolDefinition",
    "MUTATING_SHODAN_SUBCOMMANDS",
]


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------

_client: Optional[ShodanClient] = None


def get_client() -> ShodanClient:
    """Return the shared :class:`ShodanClient`, creating it on first use."""
    global _client
    if _client is None:
        _client = ShodanClient(load_config())
    return _client


def set_client(client: Optional[ShodanClient]) -> None:
    """Replace the shared client.

    Passing ``None`` resets the client so the next call rebuilds it from the
    current environment.  This is primarily useful for tests.
    """
    global _client
    _client = client


# ---------------------------------------------------------------------------
# Tool plumbing
# ---------------------------------------------------------------------------


def _ok(payload: Any) -> str:
    """Serialise a successful tool payload."""
    return json.dumps({"success": True, "data": payload}, indent=2, default=str)


def _fail(message: str, **extra: Any) -> str:
    """Serialise a failed tool payload."""
    body: Dict[str, Any] = {"success": False, "error": message}
    body.update(extra)
    return json.dumps(body, indent=2, default=str)


def _tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator turning exceptions into structured error payloads.

    The wrapper preserves the original signature and docstring so that
    ``FunctionTool.from_defaults`` can still build a correct schema.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return func(*args, **kwargs)
        except ShodanError as exc:
            logger.warning("Shodan tool %s failed: %s", func.__name__, exc)
            return _fail(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected error in Shodan tool %s", func.__name__)
            return _fail(f"Unexpected error: {exc}")

    return wrapper


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@_tool
def shodan_search(
    query: str,
    limit: int = 100,
    fields: Optional[List[str]] = None,
) -> str:
    """Search the Shodan database for hosts matching a query.

    Args:
        query: The Shodan search query. Examples: "apache port:80",
            "product:nginx country:DE", "ssl:" , "has_screenshot:true".
        limit: Maximum number of results to return (1-1000, default 100).
        fields: Banner fields to return. Defaults to
            ["ip_str", "port", "hostnames", "data"].

    Returns:
        JSON with "success" and "data" containing a list of matching hosts.
    """
    client = get_client()
    results = client.search(query, limit=limit, fields=fields)
    return _ok({"query": query, "count": len(results), "results": results})


@_tool
def shodan_count(query: str) -> str:
    """Count how many hosts match a Shodan search query.

    Args:
        query: The Shodan search query, e.g. "apache port:443 country:FR".

    Returns:
        JSON with "success" and "data" containing the total result count.
    """
    client = get_client()
    total = client.count(query)
    return _ok({"query": query, "total": total})


@_tool
def shodan_host(ip: str, history: bool = False) -> str:
    """Look up everything Shodan knows about a single IP address.

    Args:
        ip: The IP address to look up, e.g. "8.8.8.8".
        history: Include historical banners and past observations.

    Returns:
        JSON with "success" and "data" containing host attributes such as
        hostnames, city, country, os, org, open ports and vulnerabilities.
    """
    client = get_client()
    host = client.host(ip, history=history)
    return _ok(host)


@_tool
def shodan_stats(
    query: str,
    facets: Optional[List[str]] = None,
    limit: int = 10,
) -> str:
    """Get summary statistics and breakdowns for a Shodan search query.

    Args:
        query: The Shodan search query.
        facets: Dimensions to break the results down by. Common facets are
            "country", "org", "asn", "port", "product", "os", "version".
            Defaults to ["country", "org"].
        limit: Number of entries to return per facet (default 10).

    Returns:
        JSON with "success" and "data" mapping each facet to its top values.
    """
    client = get_client()
    stats = client.stats(query, facets=facets, limit=limit)
    return _ok({"query": query, "facets": stats})


@_tool
def shodan_trends(query: str, facets: Optional[List[str]] = None) -> str:
    """Query the Shodan historical database to see how a query trends over time.

    Args:
        query: The Shodan search query.
        facets: Optional dimensions to break each month down by, e.g.
            ["os", "country"].

    Returns:
        JSON with "success" and "data" containing one record per month with
        the result count and any facet breakdowns.
    """
    client = get_client()
    trends = client.trends(query, facets=facets)
    return _ok({"query": query, "months": trends})


@_tool
def shodan_domain_info(
    domain: str,
    details: bool = False,
    history: bool = False,
    record_type: Optional[str] = None,
) -> str:
    """Look up DNS records for a domain name.

    Args:
        domain: The domain to look up, e.g. "example.com".
        details: Also resolve Shodan host information for the returned IPs.
        history: Include historical DNS data.
        record_type: Restrict results to one record type, e.g. "A", "AAAA",
            "CNAME", "MX", "TXT", "NS".

    Returns:
        JSON with "success" and "data" listing the DNS records found.
    """
    client = get_client()
    records = client.domain_info(
        domain, details=details, history=history, record_type=record_type
    )
    return _ok({"domain": domain, "count": len(records), "records": records})


@_tool
def shodan_honeyscore(ip: str) -> str:
    """Check whether an IP address is a honeypot.

    Args:
        ip: The IP address to check, e.g. "1.1.1.1".

    Returns:
        JSON with "success" and "data" containing the verdict and a score
        between 0.0 and 1.0.
    """
    client = get_client()
    score = client.honeyscore(ip)
    return _ok({"ip": ip, **score})


@_tool
def shodan_myip(ipv6: bool = False) -> str:
    """Get the public IP address that Shodan sees for this machine.

    Args:
        ipv6: Return the IPv6 address instead of the IPv4 one.

    Returns:
        JSON with "success" and "data" containing the public IP address.
    """
    client = get_client()
    address = client.myip(ipv6=ipv6)
    return _ok({"ip": address, "ipv6": ipv6})


@_tool
def shodan_account_info() -> str:
    """Get information about the configured Shodan account.

    Returns:
        JSON with "success" and "data" containing the remaining query credits
        and scan credits.
    """
    client = get_client()
    info = client.account_info()
    return _ok(info)


@_tool
def shodan_list_alerts(include_expired: bool = True) -> str:
    """List the network alerts configured on the Shodan account.

    Args:
        include_expired: Also list alerts that have already expired.

    Returns:
        JSON with "success" and "data" listing each alert's id, name,
        monitored networks and triggers.
    """
    client = get_client()
    alerts = client.list_alerts(expired=include_expired)
    return _ok({"count": len(alerts), "alerts": alerts})


@_tool
def shodan_create_alert(name: str, netblocks: List[str]) -> str:
    """Create a network alert that monitors one or more IP netblocks.

    Args:
        name: A human-readable name for the alert.
        netblocks: The networks to monitor, e.g. ["8.8.8.0/24"].

    Returns:
        JSON with "success" and "data" describing the created alert.
    """
    client = get_client()
    result = client.create_alert(name, netblocks)
    return _ok(result)


@_tool
def shodan_delete_alert(alert_id: str) -> str:
    """Delete a network alert from the Shodan account.

    Args:
        alert_id: The ID of the alert to delete.

    Returns:
        JSON with "success" and "data" confirming the deletion.
    """
    client = get_client()
    result = client.delete_alert(alert_id)
    return _ok(result)


@_tool
def shodan_list_scans() -> str:
    """List recently launched on-demand Shodan scans.

    Returns:
        JSON with "success" and "data" listing each scan's id, status, size
        and creation time.
    """
    client = get_client()
    scans = client.list_scans()
    return _ok({"count": len(scans), "scans": scans})


@_tool
def shodan_submit_scan(
    netblocks: List[str],
    wait: int = 20,
) -> str:
    """Submit an on-demand Shodan scan for one or more netblocks.

    Note: this consumes scan credits from the account.

    Args:
        netblocks: The networks to scan, e.g. ["8.8.8.0/24"].
        wait: Seconds to wait for results before returning (default 20).

    Returns:
        JSON with "success" and "data" describing the submitted scan.
    """
    client = get_client()
    result = client.submit_scan(netblocks, wait=wait)
    return _ok(result)


@_tool
def shodan_scan_status(scan_id: str) -> str:
    """Get the status of an on-demand Shodan scan.

    Args:
        scan_id: The ID of the scan to check.

    Returns:
        JSON with "success" and "data" containing the scan status.
    """
    client = get_client()
    status = client.scan_status(scan_id)
    return _ok({"scan_id": scan_id, "status": status})


@_tool
def shodan_download(
    query: str,
    filename: str,
    limit: int = 1000,
    fields: Optional[List[str]] = None,
) -> str:
    """Download Shodan search results into a compressed JSON file on disk.

    Args:
        query: The Shodan search query.
        filename: Where to write the file. ".json.gz" is added if missing.
        limit: Maximum number of results to download (default 1000).
        fields: Optional subset of banner fields to download.

    Returns:
        JSON with "success" and "data" describing the saved file.
    """
    client = get_client()
    result = client.download(query, filename, limit=limit, fields=fields)
    return _ok(result)


#: Subcommands that change account state, consume credits, or touch the
#: local filesystem.  ``shodan_raw`` refuses to run these so that the tool
#: stays inside the "read-only" category it is registered under.
MUTATING_SHODAN_SUBCOMMANDS = frozenset(
    {
        # Alerts — create/delete network monitors.
        "alert create",
        "alert remove",
        "alert clear",
        "alert import",
        "alert domain",
        # Scans — consume scan credits.
        "scan submit",
        "scan internet",
        # Bulk downloads — consume credits and write files.
        "data download",
        "download",
        # Organisation membership — mutates the account.
        "org add",
        "org remove",
        # Local credential handling.
        "init",
    }
)


#: Subcommand groups whose second word selects the actual action.
_GROUP_SUBCOMMANDS = frozenset({"alert", "scan", "org", "data"})


def _normalise_subcommand(args: Sequence[str]) -> str:
    """Return the leading subcommand words of an argv list.

    ``["alert", "create", "x"]`` becomes ``"alert create"``, while
    ``["init", "KEY"]`` becomes ``"init"`` — a group name only absorbs a
    second word when it is one of the known subcommand groups.

    Options (``-``-prefixed tokens) are skipped, so ``["--color", "alert",
    "list"]`` still resolves to ``"alert list"``.
    """
    words: List[str] = []
    for arg in args:
        if arg.startswith("-"):
            continue
        lowered = arg.lower()

        if not words:
            words.append(lowered)
            continue

        # Only a known group may absorb its second word.
        if len(words) == 1 and words[0] in _GROUP_SUBCOMMANDS:
            words.append(lowered)
        break

    return " ".join(words)


def _is_mutating_command(args: Sequence[str]) -> bool:
    """Return True when the argv invokes a state-changing subcommand.

    Both the one-word form (``["init"]``) and the two-word form
    (``["alert", "create"]``) are matched, so ``alert list`` stays allowed
    while ``alert create`` is refused.
    """
    subcommand = _normalise_subcommand(args)
    if not subcommand:
        return False

    if subcommand in MUTATING_SHODAN_SUBCOMMANDS:
        return True

    # A bare group name such as "alert" is not a runnable command, but treat
    # it as mutating so it can never slip through to the CLI.
    return subcommand in {"alert", "scan", "org", "data"}


@_tool
def shodan_raw(args: List[str]) -> str:
    """Run an arbitrary Shodan CLI command and return its raw output.

    This is an escape hatch for CLI functionality that has no dedicated tool.
    It only runs *read-only* subcommands: commands that would change account
    state, consume credits, or write files are refused, because this tool is
    registered in the read-only category and is handed to autonomous agents.

    Args:
        args: The CLI arguments, without the leading "shodan". For example
            ["host", "1.1.1.1"] or ["alert", "list"].

    Returns:
        JSON with "success" and "data" containing the command's stdout.
        Mutating commands return a "success": false payload explaining why.
    """
    if _is_mutating_command(args):
        return _fail(
            "shodan_raw only runs read-only commands; "
            f"'{_normalise_subcommand(args)}' changes account state or "
            "consumes credits. Use the dedicated tool instead.",
            command=" ".join(["shodan", *args]),
        )

    client = get_client()
    result = client.run_raw(args)
    return _ok(
        {
            "command": " ".join(["shodan", *args]),
            "returncode": result.returncode,
            "output": result.output,
        }
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ToolDefinition:
    """Metadata about a single tool.

    Attributes:
        name: The function name exposed to the agent.
        fn: The callable implementing the tool.
        category: Either "read" or "write".
        description: Short human-readable summary.
    """

    def __init__(
        self,
        name: str,
        fn: Callable[..., Any],
        category: str,
        description: str,
    ):
        self.name = name
        self.fn = fn
        self.category = category
        self.description = description

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ToolDefinition(name={self.name!r}, category={self.category!r})"


def _define(
    name: str,
    fn: Callable[..., Any],
    category: str,
    description: str,
) -> ToolDefinition:
    return ToolDefinition(name=name, fn=fn, category=category, description=description)


TOOL_REGISTRY: Dict[str, ToolDefinition] = {
    definition.name: definition
    for definition in [
        _define(
            "shodan_search",
            shodan_search,
            "read",
            "Search the Shodan database for hosts matching a query.",
        ),
        _define(
            "shodan_count",
            shodan_count,
            "read",
            "Count hosts matching a Shodan search query.",
        ),
        _define(
            "shodan_host",
            shodan_host,
            "read",
            "Look up all known information about a single IP address.",
        ),
        _define(
            "shodan_stats",
            shodan_stats,
            "read",
            "Get summary statistics and facet breakdowns for a query.",
        ),
        _define(
            "shodan_trends",
            shodan_trends,
            "read",
            "Query the Shodan historical database for trends over time.",
        ),
        _define(
            "shodan_domain_info",
            shodan_domain_info,
            "read",
            "Look up DNS records for a domain name.",
        ),
        _define(
            "shodan_honeyscore",
            shodan_honeyscore,
            "read",
            "Check whether an IP address is a honeypot.",
        ),
        _define(
            "shodan_myip",
            shodan_myip,
            "read",
            "Get the public IP address Shodan sees for this machine.",
        ),
        _define(
            "shodan_account_info",
            shodan_account_info,
            "read",
            "Get account information and remaining credits.",
        ),
        _define(
            "shodan_list_alerts",
            shodan_list_alerts,
            "read",
            "List the network alerts configured on the account.",
        ),
        _define(
            "shodan_list_scans",
            shodan_list_scans,
            "read",
            "List recently launched on-demand scans.",
        ),
        _define(
            "shodan_raw",
            shodan_raw,
            "read",
            "Run an arbitrary Shodan CLI command and return raw output.",
        ),
        _define(
            "shodan_create_alert",
            shodan_create_alert,
            "write",
            "Create a network alert monitoring one or more netblocks.",
        ),
        _define(
            "shodan_delete_alert",
            shodan_delete_alert,
            "write",
            "Delete a network alert from the account.",
        ),
        _define(
            "shodan_submit_scan",
            shodan_submit_scan,
            "write",
            "Submit an on-demand Shodan scan for one or more netblocks.",
        ),
        _define(
            "shodan_download",
            shodan_download,
            "write",
            "Download search results into a compressed JSON file.",
        ),
    ]
}


def _to_function_tool(definition: ToolDefinition):
    """Convert a :class:`ToolDefinition` into a LlamaIndex FunctionTool."""
    from llama_index.core.tools import FunctionTool

    return FunctionTool.from_defaults(
        fn=definition.fn,
        name=definition.name,
        description=definition.description or (definition.fn.__doc__ or ""),
    )


def get_all_tools(
    include_mutating: bool = False,
    names: Optional[Sequence[str]] = None,
) -> List[Any]:
    """Return the toolkit's tools as LlamaIndex ``FunctionTool`` objects.

    Args:
        include_mutating: When True, also include tools that change account
            state or consume credits (alerts, scans, downloads).  Off by
            default so an autonomous agent stays read-only.
        names: Optional explicit list of tool names to include.  When given,
            the ``include_mutating`` flag is ignored and only the requested
            tools are returned.

    Returns:
        A list of ``FunctionTool`` objects ready to hand to an agent.
    """
    if names is not None:
        selected = [name for name in names if name in TOOL_REGISTRY]
    else:
        selected = [
            name
            for name, definition in TOOL_REGISTRY.items()
            if include_mutating or definition.category == "read"
        ]

    return [_to_function_tool(TOOL_REGISTRY[name]) for name in selected]


def get_readonly_tools() -> List[Any]:
    """Return only the read-only tools."""
    return get_all_tools(include_mutating=False)


def get_mutating_tools() -> List[Any]:
    """Return only the tools that change state or consume credits."""
    return get_all_tools(include_mutating=True, names=[
        name
        for name, definition in TOOL_REGISTRY.items()
        if definition.category == "write"
    ])


def get_tools_by_name(names: Sequence[str]) -> List[Any]:
    """Return the named tools, silently skipping unknown names."""
    return get_all_tools(names=list(names))
