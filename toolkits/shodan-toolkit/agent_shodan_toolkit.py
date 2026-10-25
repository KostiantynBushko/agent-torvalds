"""
Shodan Toolkit - internet-exposure intelligence for the Torvalds Agent.

This module is the **LlamaIndex adapter** for the Shodan toolkit. It is the
only place in the feature that knows about LlamaIndex; the reusable library
half lives in the same package and imports no LlamaIndex code at import time.

Where it lives
--------------

The adapter is a **submodule of the toolkit package**, not a file at the
project root any more.  Inside this repository the package is reached
through the alias registered by ``toolkits/__init__.py``::

    from toolkits.shodan_toolkit.agent_shodan_toolkit import get_all_tools

That is the one canonical import path for the adapter here.  The core
package is pulled in with a **relative** import (``from . import ...``), so
the adapter always works with the very same module objects the package
exports - and it keeps working when the toolkit is installed as a
standalone distribution, where no ``toolkits`` package exists at all.

The adapter exposes the toolkit's tools under the ``Security`` category:

============================================  ==========================
Tool                                          Purpose
============================================  ==========================
``shodan_search``                             Search the Shodan database
``shodan_count``                              Count hosts matching a query
``shodan_host``                               Everything known about one IP
``shodan_stats``                              Facet breakdown for a query
``shodan_trends``                             Historical database trends
``shodan_domain_info``                        DNS records for a domain
``shodan_honeyscore``                         Is this IP a honeypot?
``shodan_myip``                               The public IP Shodan sees
``shodan_account_info``                       Account and credit balance
``shodan_list_alerts``                        Configured network alerts
``shodan_list_scans``                         Recently launched scans
``shodan_raw``                                Raw CLI output (guarded)
``shodan_create_alert``                       Create a network alert (write)
``shodan_delete_alert``                       Delete a network alert (write)
``shodan_submit_scan``                        Submit an on-demand scan (write)
``shodan_download``                           Download results to a file (write)
============================================  ==========================

Design decisions
----------------

**Read-only by default.** The upstream toolkit already splits its registry
into a ``read`` and a ``write`` category. Only the ``read`` tools are
exposed to the agent unless the operator explicitly opts in, because the
``write`` tools create and delete alerts, submit scans and consume Shodan
credits. The opt-in is a single environment variable, so it is honoured
consistently by every load path (retriever, ``--select`` menu, both
orchestrators) without any of them needing to know about it::

    TORVALDS_SHODAN_ALLOW_MUTATING=1

**No re-implementation.** The adapter does not wrap the tool functions. It
re-uses the upstream implementations verbatim and only rewrites the
*description* so that the tool carries the ``Category: Security`` tag the
startup selection menu needs. The behaviour - including the error payload
convention and the raw-command guard - stays exactly as the toolkit defines
it, and stays testable on its own.

**Nothing raises at import time.** The core package is imported inside a
``try/except``. A missing optional dependency, a missing ``shodan`` CLI or an
unconfigured API key degrades to a toolkit that reports the problem, rather
than breaking the agent boot.

**The CLI is optional.** The toolkit drives the ``shodan`` command line
binary. When the binary is not on ``PATH`` the tools return a structured
error payload explaining that, instead of raising.

Category: Security
Retriever Keywords: shodan, internet exposure, attack surface, banner, honeypot, dns, scan, vulnerability, reconnaissance, cve, open ports
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


#: The category the tools are filed under in the startup selection menu.
CATEGORY = "Security"

#: Environment variable that opts the agent into the write-capable tools.
MUTATING_ENV_VAR = "TORVALDS_SHODAN_ALLOW_MUTATING"

#: Values of :data:`MUTATING_ENV_VAR` that count as "yes".
_TRUTHY = frozenset({"1", "true", "yes", "on"})


# ---------------------------------------------------------------------------
# Core package import - guarded, so a missing toolkit never breaks the boot.
# ---------------------------------------------------------------------------
try:
    from . import TOOL_REGISTRY
    from . import tools as _shodan_tools
except Exception as exc:  # noqa: BLE001 - the toolkit is optional
    # The package is absent, or one of its dependencies is missing.
    # The toolkit is designed to degrade gracefully, so this must stay silent.
    TOOL_REGISTRY = {}
    _shodan_tools = None
    _IMPORT_ERROR: Optional[BaseException] = exc
    logger.debug("Shodan toolkit core package unavailable: %s", exc)
else:
    _IMPORT_ERROR = None


#: True when the core package was imported successfully.
SHODAN_AVAILABLE = TOOL_REGISTRY != {} and _IMPORT_ERROR is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mutating_enabled() -> bool:
    """Return True when the operator opted into the write-capable tools."""
    raw = os.environ.get(MUTATING_ENV_VAR, "")
    return raw.strip().lower() in _TRUTHY


def _describe(description: str) -> str:
    """Append the category tag to a tool description.

    The startup selection menu groups tools by the ``Category: <Name>``
    suffix of their description, so every tool the adapter exposes has to
    carry one.
    """
    text = (description or "").strip()
    if f"Category: {CATEGORY}" in text:
        return text
    return f"{text} Category: {CATEGORY}"


def _build_tool(name: str, definition: Any) -> FunctionTool:
    """Turn one upstream ``ToolDefinition`` into a ``FunctionTool``."""
    description = definition.description or (definition.fn.__doc__ or "")
    return FunctionTool.from_defaults(
        fn=definition.fn,
        name=definition.name,
        description=_describe(description),
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def get_all_tools(include_mutating: Optional[bool] = None) -> list[FunctionTool]:
    """
    Return the Shodan tools as FunctionTool objects.

    Args:
        include_mutating: Include the tools that change account state or
            consume credits (alerts, scans, downloads).  When left at
            ``None`` the decision is taken from the
            ``TORVALDS_SHODAN_ALLOW_MUTATING`` environment variable, so that
            every load path behaves the same way.

    Returns:
        list[FunctionTool]: The Shodan FunctionTool objects, each with a
        description ending in ``Category: Security``.  Empty when the
        toolkit is not installed.
    """
    if not SHODAN_AVAILABLE:
        logger.info("Shodan toolkit not available - no tools registered")
        return []

    if include_mutating is None:
        include_mutating = _mutating_enabled()

    tools: list[FunctionTool] = []
    for name, definition in TOOL_REGISTRY.items():
        if definition.category != "read" and not include_mutating:
            continue
        tools.append(_build_tool(name, definition))

    logger.info(
        "get_all_tools called: %d tools (mutating=%s)", len(tools), include_mutating
    )
    return tools


def get_readonly_tools() -> list[FunctionTool]:
    """Return only the read-only Shodan tools."""
    return get_all_tools(include_mutating=False)


def get_mutating_tools() -> list[FunctionTool]:
    """Return only the tools that change account state or consume credits."""
    if not SHODAN_AVAILABLE:
        return []
    return [
        _build_tool(name, definition)
        for name, definition in TOOL_REGISTRY.items()
        if definition.category != "read"
    ]


def get_toolkit_status() -> dict:
    """
    Report whether the toolkit can be used right now.

    Returns:
        dict: ``available`` (the core package imported), ``cli_available``
        (the ``shodan`` binary is on PATH), ``has_api_key`` (a key is
        configured) and ``error`` (the import error, if any).
    """
    status: dict = {
        "available": SHODAN_AVAILABLE,
        "cli_available": False,
        "has_api_key": False,
        "error": str(_IMPORT_ERROR) if _IMPORT_ERROR else None,
    }
    if not SHODAN_AVAILABLE or _shodan_tools is None:
        return status

    try:
        client = _shodan_tools.get_client()
        status["cli_available"] = bool(client.is_available())
        status["has_api_key"] = bool(client.has_api_key())
    except Exception as exc:  # noqa: BLE001 - status must never raise
        status["error"] = str(exc)

    return status


__all__ = [
    "get_all_tools",
    "get_readonly_tools",
    "get_mutating_tools",
    "get_toolkit_status",
    "CATEGORY",
    "MUTATING_ENV_VAR",
    "SHODAN_AVAILABLE",
]
