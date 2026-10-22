"""
shodan-toolkit
==============

A Python wrapper around the `Shodan <https://www.shodan.io>`_ command-line
interface, designed to expose Shodan's internet-exposure data to
LlamaIndex ``FunctionAgent`` instances.

Quick start::

    from shodan_toolkit import ShodanClient, get_all_tools

    # Structured Python API
    client = ShodanClient()
    results = client.search("apache port:80", limit=5)

    # LlamaIndex tools
    tools = get_all_tools()
    agent = FunctionAgent(tools=tools, llm=llm)

Command-line::

    shodan-toolkit info
    shodan-toolkit search "nginx" --limit 5
    shodan-toolkit doctor
"""

from __future__ import annotations

__version__ = "0.1.0"

from .agent import (
    DEFAULT_SYSTEM_PROMPT,
    build_agent,
    build_tools,
    shodan_toolkit_context,
)
from .client import ShodanClient
from .config import ShodanConfig, load_config
from .runner import (
    CommandResult,
    ShodanAuthError,
    ShodanCLIError,
    ShodanError,
    ShodanNotInstalledError,
    ShodanRunner,
)
from .tools import (
    TOOL_REGISTRY,
    get_all_tools,
    get_mutating_tools,
    get_readonly_tools,
    get_tools_by_name,
    set_client,
)

__all__ = [
    "__version__",
    # Core
    "ShodanClient",
    "ShodanConfig",
    "load_config",
    # Runner
    "ShodanRunner",
    "CommandResult",
    "ShodanError",
    "ShodanAuthError",
    "ShodanCLIError",
    "ShodanNotInstalledError",
    # Tools
    "get_all_tools",
    "get_readonly_tools",
    "get_mutating_tools",
    "get_tools_by_name",
    "set_client",
    "TOOL_REGISTRY",
    # Agent
    "build_agent",
    "build_tools",
    "shodan_toolkit_context",
    "DEFAULT_SYSTEM_PROMPT",
]
