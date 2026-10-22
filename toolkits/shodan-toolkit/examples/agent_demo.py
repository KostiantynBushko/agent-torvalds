"""
Demonstrates a LlamaIndex ``FunctionAgent`` driving the Shodan toolkit.

The Shodan CLI is replaced with a fake runner so the example runs offline
and without consuming API credits.

Run with::

    python examples/agent_demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import List

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.llms import MockLLM

from shodan_toolkit import get_all_tools
from shodan_toolkit.client import ShodanClient
from shodan_toolkit.config import ShodanConfig
from shodan_toolkit.runner import CommandResult, ShodanRunner
from shodan_toolkit.tools import set_client

# --- Fake CLI responses ----------------------------------------------------

SEARCH_OUTPUT = (
    "34.120.53.61\t443\t\tApache/2.4.41 (Ubuntu)\\n\n"
    "35.190.225.219\t80\t\tnginx/1.21.0\\n\n"
)
STATS_OUTPUT = (
    "Top 1 Results for Facet: country\n"
    "United States                        1,234\n"
)


class DemoRunner(ShodanRunner):
    """A runner that replays canned output instead of calling the CLI."""

    def __init__(self) -> None:
        super().__init__(executable="shodan")
        self.calls: List[List[str]] = []

    def resolve_executable(self):  # type: ignore[override]
        return "/usr/bin/shodan"

    def is_available(self) -> bool:  # type: ignore[override]
        return True

    def run(self, args, check: bool = True, timeout=None) -> CommandResult:
        args = list(args)
        self.calls.append(args)

        stdout = ""
        if args[0] == "search":
            stdout = SEARCH_OUTPUT
        elif args[0] == "stats":
            stdout = STATS_OUTPUT
        elif args[0] == "count":
            stdout = "1234\n"
        elif args[0] == "host":
            stdout = (
                "8.8.8.8\n"
                "Hostnames:            dns.google\n"
                "Country:              United States\n"
                "Organization:          Google LLC\n"
                "Number of open ports:  2\n"
            )

        return CommandResult(
            command=["shodan", *args], returncode=0, stdout=stdout, stderr=""
        )


async def main() -> int:
    """Run the demo agent against the fake CLI."""
    # Install the fake-backed client.
    client = ShodanClient(
        config=ShodanConfig(api_key="demo-key"), runner=DemoRunner()
    )
    set_client(client)

    tools = get_all_tools()
    agent = FunctionAgent(
        name="shodan_demo",
        description="Demo agent with Shodan access",
        llm=MockLLM(max_tokens=256),
        tools=tools,
        system_prompt=(
            "You are a security analyst. Use the Shodan tools to answer the "
            "user's questions about internet-exposed infrastructure."
        ),
    )

    print("Shodan Toolkit — Agent Demo")
    print("=" * 60)
    print(f"Agent: {agent.name}")
    print(f"Tools: {len(agent.tools)}")
    print("=" * 60)

    # Call the tools directly, exactly as the agent would.
    from shodan_toolkit import tools as tools_module

    print("\n1) shodan_count('nginx port:443')")
    print(json.dumps(json.loads(tools_module.shodan_count("nginx port:443")), indent=2))

    print("\n2) shodan_search('nginx', limit=5)")
    print(json.dumps(json.loads(tools_module.shodan_search("nginx", limit=5)), indent=2))

    print("\n3) shodan_stats('nginx')")
    print(json.dumps(json.loads(tools_module.shodan_stats("nginx")), indent=2))

    print("\n4) shodan_host('8.8.8.8')")
    print(json.dumps(json.loads(tools_module.shodan_host("8.8.8.8")), indent=2))

    print("\n" + "=" * 60)
    print("CLI commands that would have been executed:")
    for call in client.runner.calls:
        print("  shodan " + " ".join(call))

    set_client(None)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
