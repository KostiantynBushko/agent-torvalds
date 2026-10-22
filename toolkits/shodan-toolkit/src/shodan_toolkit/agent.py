"""
Helpers for wiring the Shodan toolkit into a LlamaIndex ``FunctionAgent``.

This module removes the boilerplate required to build an agent that can
query Shodan, and provides a sensible default system prompt that teaches the
model how to use the tools effectively.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Sequence
from typing import Any, List, Optional

from .tools import get_all_tools

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "build_agent",
    "build_tools",
    "shodan_toolkit_context",
]


DEFAULT_SYSTEM_PROMPT = """\
You are a security research assistant with access to the Shodan internet
exposure database through a set of tools.

Guidelines:
- Start with `shodan_count` to gauge how large a result set is before
  running an expensive `shodan_search`.
- Use `shodan_stats` to break a query down by country, org, port or product
  instead of paging through raw results.
- Use `shodan_host` for everything known about a single IP address.
- Prefer narrow, specific queries (e.g. "product:nginx country:DE port:443")
  over broad ones (e.g. "nginx").
- Quote exact IPs, hostnames and banner data in your answers. Do not invent
  findings that the tools did not return.
- When you report vulnerability information, mention the observed banner and
  the port it came from.
- If a tool returns "success": false, read the "error" field, correct your
  query, and try again rather than guessing.
"""


def build_tools(
    include_mutating: bool = False,
    names: Optional[Sequence[str]] = None,
) -> List[Any]:
    """Build the list of LlamaIndex tools for the toolkit.

    Args:
        include_mutating: Include tools that change account state or consume
            credits.
        names: Explicit list of tool names to expose.

    Returns:
        A list of ``FunctionTool`` objects.
    """
    return get_all_tools(include_mutating=include_mutating, names=names)


def shodan_toolkit_context(client: Optional[Any] = None) -> str:
    """Build a short context block describing the toolkit's status.

    Useful for injecting into a system prompt so the model knows whether the
    CLI is installed and whether an API key is configured.

    Args:
        client: Optional client to inspect.  Defaults to the shared client.

    Returns:
        A human-readable status string.
    """
    from .tools import get_client

    client = client or get_client()

    lines = ["### Shodan Toolkit"]
    lines.append(f"- CLI installed: {'yes' if client.is_available() else 'no'}")

    if not client.is_available():
        lines.append("- Action required: install with `pip install shodan`")
        return "\n".join(lines)

    with contextlib.suppress(Exception):  # pragma: no cover - best effort
        lines.append(f"- CLI version: {client.version()}")

    lines.append(
        f"- API key configured: {'yes' if client.has_api_key() else 'no'}"
    )
    if not client.has_api_key():
        lines.append(
            "- Action required: run `shodan init <api-key>` "
            "or set SHODAN_TOOLKIT_API_KEY"
        )

    return "\n".join(lines)


def build_agent(
    llm: Optional[Any] = None,
    tools: Optional[Sequence[Any]] = None,
    system_prompt: Optional[str] = None,
    include_mutating: bool = False,
    tool_names: Optional[Sequence[str]] = None,
    **agent_kwargs: Any,
):
    """Build a LlamaIndex ``FunctionAgent`` wired up with the Shodan tools.

    Args:
        llm: The LLM to use.  When omitted the agent falls back to
            ``llama_index.core.Settings.llm``.
        tools: Explicit tool list.  When omitted the toolkit's tools are used.
        system_prompt: Custom system prompt.  Defaults to
            :data:`DEFAULT_SYSTEM_PROMPT`.
        include_mutating: Include state-changing / credit-consuming tools.
        tool_names: Explicit tool names to expose.
        **agent_kwargs: Extra keyword arguments forwarded to ``FunctionAgent``.

    Returns:
        A configured ``FunctionAgent``.
    """
    from llama_index.core.agent.workflow import FunctionAgent

    resolved_tools = list(tools) if tools is not None else build_tools(
        include_mutating=include_mutating, names=tool_names
    )

    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    context = shodan_toolkit_context()
    full_prompt = f"{prompt}\n\n{context}"

    agent_kwargs.setdefault("name", "shodan_agent")
    agent_kwargs.setdefault("description", "Security agent with Shodan access")

    return FunctionAgent(
        llm=llm,
        tools=resolved_tools,
        system_prompt=full_prompt,
        **agent_kwargs,
    )
