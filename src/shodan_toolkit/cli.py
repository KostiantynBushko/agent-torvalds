"""
Command-line interface for the Shodan toolkit.

This gives humans and scripts a quick way to exercise the same functionality
the agent tools expose, plus a ``doctor`` command that diagnoses setup issues.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any, List, Optional

from . import __version__
from .client import ShodanClient
from .config import load_config
from .runner import ShodanError

__all__ = ["main", "build_parser"]


def _emit(payload: Any, as_json: bool = True) -> None:
    """Print a payload either as JSON or as a human-readable summary."""
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
        return

    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                print(f"{key}:")
                print(json.dumps(value, indent=2, default=str))
            else:
                print(f"{key}: {value}")
    elif isinstance(payload, list):
        for item in payload:
            print(json.dumps(item, default=str))
    else:
        print(payload)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="shodan-toolkit",
        description="Python wrapper for the Shodan CLI with LlamaIndex agent tools.",
    )
    parser.add_argument(
        "--version", action="version", version=f"shodan-toolkit {__version__}"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Force JSON output (the default for most commands).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a JSON config file.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # doctor
    p_doctor = sub.add_parser(
        "doctor", help="Check that the toolkit is correctly configured."
    )
    p_doctor.add_argument(
        "--raw", action="store_true", help="Print the raw diagnostic payload."
    )

    # info
    p_info = sub.add_parser("info", help="Show account information and credits.")
    p_info.add_argument(
        "--text", action="store_true", help="Print a human-readable summary."
    )

    # version
    sub.add_parser("version", help="Show the Shodan CLI version.")

    # search
    p_search = sub.add_parser("search", help="Search the Shodan database.")
    p_search.add_argument("query", help="The Shodan search query.")
    p_search.add_argument(
        "--limit", type=int, default=100, help="Maximum number of results."
    )
    p_search.add_argument(
        "--fields",
        default=None,
        help="Comma-separated list of fields to request.",
    )
    p_search.add_argument(
        "--text", action="store_true", help="Print a human-readable summary."
    )

    # count
    p_count = sub.add_parser("count", help="Count hosts matching a query.")
    p_count.add_argument("query", help="The Shodan search query.")

    # host
    p_host = sub.add_parser("host", help="Look up an IP address.")
    p_host.add_argument("ip", help="The IP address to look up.")
    p_host.add_argument(
        "--history", action="store_true", help="Include historical banners."
    )

    # stats
    p_stats = sub.add_parser("stats", help="Get summary statistics for a query.")
    p_stats.add_argument("query", help="The Shodan search query.")
    p_stats.add_argument(
        "--facets", default=None, help="Comma-separated list of facets."
    )
    p_stats.add_argument(
        "--limit", type=int, default=10, help="Entries per facet."
    )

    # trends
    p_trends = sub.add_parser("trends", help="Query the historical database.")
    p_trends.add_argument("query", help="The Shodan search query.")
    p_trends.add_argument(
        "--facets", default=None, help="Comma-separated list of facets."
    )

    # domain
    p_domain = sub.add_parser("domain", help="Look up DNS records for a domain.")
    p_domain.add_argument("domain", help="The domain name.")
    p_domain.add_argument(
        "--details", action="store_true", help="Also resolve host information."
    )
    p_domain.add_argument(
        "--history", action="store_true", help="Include historical DNS data."
    )
    p_domain.add_argument(
        "--type", default=None, help="Restrict to a single record type."
    )

    # honeyscore
    p_honey = sub.add_parser("honeyscore", help="Check if an IP is a honeypot.")
    p_honey.add_argument("ip", help="The IP address to check.")

    # myip
    p_myip = sub.add_parser("myip", help="Get the public IP address.")
    p_myip.add_argument("--ipv6", action="store_true", help="Return the IPv6 address.")

    # alerts
    p_alerts = sub.add_parser("alerts", help="List network alerts.")
    p_alerts.add_argument(
        "--no-expired", action="store_true", help="Hide expired alerts."
    )

    # init
    p_init = sub.add_parser("init", help="Store the Shodan API key.")
    p_init.add_argument("api_key", help="Your Shodan API key.")
    p_init.add_argument(
        "--from-env",
        action="store_true",
        help="Read the API key from the SHODAN_API_KEY environment variable.",
    )

    # tools
    p_tools = sub.add_parser(
        "tools", help="List the available agent tools."
    )
    p_tools.add_argument(
        "--all",
        action="store_true",
        help="Include tools that change state or consume credits.",
    )
    p_tools.add_argument(
        "--schemas", action="store_true", help="Print the JSON schemas."
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_doctor(client: ShodanClient, args: argparse.Namespace) -> int:
    """Diagnose the toolkit's installation and configuration."""
    config = client.config
    key_path = client.api_key_path()

    checks: List[dict] = []

    # Distinguish "not installed" from "installed but not runnable" — the
    # latter is the common `pkg_resources` breakage, and needs a different
    # remedy than "pip install shodan".
    executable_found = client.runner.resolve_executable() is not None
    cli_available = client.is_available()

    if cli_available:
        cli_detail = client.config.executable
    elif executable_found:
        cli_detail = (
            f"'{client.config.executable}' was found but does not run "
            "(broken installation; see the version check below)"
        )
    else:
        cli_detail = f"'{client.config.executable}' not found on PATH"

    checks.append(
        {
            "name": "shodan_cli",
            "ok": cli_available,
            "detail": cli_detail,
        }
    )

    cli_version = None
    if cli_available:
        try:
            cli_version = client.version()
            checks.append(
                {"name": "shodan_cli_version", "ok": True, "detail": cli_version}
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "shodan_cli_version",
                    "ok": False,
                    "detail": str(exc),
                }
            )

    has_key = client.has_api_key()
    checks.append(
        {
            "name": "api_key",
            "ok": has_key,
            "detail": str(key_path) if has_key else f"not found at {key_path}",
        }
    )

    checks.append(
        {
            "name": "config",
            "ok": True,
            "detail": config.config_path or "(defaults)",
        }
    )

    # Warn when the resolved `shodan` belongs to a different virtualenv than
    # the one running the toolkit — a common source of confusing failures
    # when the toolkit is installed as a library.
    resolved = client.runner.resolve_executable()
    if resolved:
        interpreter = client.runner.interpreter_of(resolved)
        if interpreter:
            current = os.path.dirname(os.path.abspath(sys.executable))
            if os.path.dirname(os.path.abspath(interpreter)) != current:
                checks.append(
                    {
                        "name": "shodan_cli_env",
                        "ok": False,
                        "detail": (
                            f"'{resolved}' belongs to {interpreter}, but the "
                            f"toolkit runs under {sys.executable}. Install the "
                            "CLI in this environment: pip install "
                            f"'shodan-toolkit[cli]'"
                        ),
                    }
                )

    try:
        import llama_index.core  # noqa: F401

        checks.append(
            {"name": "llama_index", "ok": True, "detail": "installed"}
        )
    except Exception as exc:
        checks.append(
            {"name": "llama_index", "ok": False, "detail": str(exc)}
        )

    payload = {
        "toolkit_version": __version__,
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }

    if args.raw:
        _emit(payload)
        return 0 if payload["ok"] else 1

    print("Shodan Toolkit — Diagnostics")
    print("=" * 60)
    for check in checks:
        marker = "OK  " if check["ok"] else "FAIL"
        print(f"[{marker}] {check['name']:<22} {check['detail']}")
    print("=" * 60)
    print("Result:", "all checks passed" if payload["ok"] else "issues found")
    return 0 if payload["ok"] else 1


def _cmd_tools(client: ShodanClient, args: argparse.Namespace) -> int:
    """List the agent tools exposed by the toolkit."""
    from .tools import TOOL_REGISTRY

    selected = [
        definition
        for definition in TOOL_REGISTRY.values()
        if args.all or definition.category == "read"
    ]

    if args.schemas:
        from .tools import get_all_tools

        tools = get_all_tools(include_mutating=args.all)
        payload = [
            {
                "name": tool.metadata.name,
                "description": tool.metadata.description,
                "parameters": tool.metadata.get_parameters_dict(),
            }
            for tool in tools
        ]
        _emit(payload)
        return 0

    print(f"Available tools ({len(selected)}):")
    print("=" * 72)
    for definition in sorted(selected, key=lambda d: d.name):
        marker = "read" if definition.category == "read" else "write"
        print(f"  {definition.name:<24} [{marker:<5}] {definition.description}")
    return 0


def _cmd_init(client: ShodanClient, args: argparse.Namespace) -> int:
    """Store the Shodan API key."""
    api_key = args.api_key
    if args.from_env:
        api_key = os.environ.get("SHODAN_API_KEY", "")
        if not api_key:
            print("SHODAN_API_KEY is not set in the environment.", file=sys.stderr)
            return 2

    try:
        result = client.init(api_key)
    except ShodanError as exc:
        print(f"Failed to store the API key: {exc}", file=sys.stderr)
        return 1

    print(f"{result['message']} -> {result['key_file']}")
    return 0


def _cmd_search(client: ShodanClient, args: argparse.Namespace) -> int:
    """Run a search and print the results."""
    fields = (
        [f.strip() for f in args.fields.split(",") if f.strip()]
        if args.fields
        else None
    )
    results = client.search(args.query, limit=args.limit, fields=fields)

    if args.text:
        for record in results:
            hostnames = record.get("hostnames") or ""
            if isinstance(hostnames, str):
                hostnames = hostnames.split(";")
            print(
                f"{record.get('ip_str', '?'):<16} "
                f"{str(record.get('port', '')):<6} "
                f"{';'.join(hostnames):<30} "
                f"{str(record.get('data', ''))[:60]}"
            )
        print(f"\n{len(results)} result(s)")
        return 0

    _emit({"query": args.query, "count": len(results), "results": results})
    return 0


def _cmd_count(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print the number of results for a query."""
    total = client.count(args.query)
    _emit({"query": args.query, "total": total})
    return 0


def _cmd_host(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print host information for an IP address."""
    _emit(client.host(args.ip, history=args.history))
    return 0


def _cmd_stats(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print facet statistics for a query."""
    facets = (
        [f.strip() for f in args.facets.split(",") if f.strip()]
        if args.facets
        else None
    )
    _emit(
        {
            "query": args.query,
            "facets": client.stats(args.query, facets=facets, limit=args.limit),
        }
    )
    return 0


def _cmd_trends(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print historical trends for a query."""
    facets = (
        [f.strip() for f in args.facets.split(",") if f.strip()]
        if args.facets
        else None
    )
    _emit({"query": args.query, "months": client.trends(args.query, facets=facets)})
    return 0


def _cmd_domain(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print DNS records for a domain."""
    _emit(
        client.domain_info(
            args.domain,
            details=args.details,
            history=args.history,
            record_type=args.type,
        )
    )
    return 0


def _cmd_honeyscore(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print the honeypot score for an IP address."""
    _emit(client.honeyscore(args.ip))
    return 0


def _cmd_myip(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print the public IP address."""
    _emit({"ip": client.myip(ipv6=args.ipv6)})
    return 0


def _cmd_info(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print account information."""
    info = client.account_info()
    if args.text:
        print(f"Query credits: {info.get('query_credits', 'unknown')}")
        print(f"Scan credits:  {info.get('scan_credits', 'unknown')}")
        return 0
    _emit(info)
    return 0


def _cmd_alerts(client: ShodanClient, args: argparse.Namespace) -> int:
    """List the configured network alerts."""
    alerts = client.list_alerts(expired=not args.no_expired)
    _emit({"count": len(alerts), "alerts": alerts})
    return 0


def _cmd_version(client: ShodanClient, args: argparse.Namespace) -> int:
    """Print version information."""
    payload: dict = {"toolkit_version": __version__}
    try:
        payload["shodan_cli_version"] = client.version()
    except Exception as exc:
        payload["shodan_cli_version"] = f"unavailable: {exc}"
    _emit(payload)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(config_path=args.config)
    client = ShodanClient(config)

    handlers = {
        "doctor": _cmd_doctor,
        "tools": _cmd_tools,
        "init": _cmd_init,
        "search": _cmd_search,
        "count": _cmd_count,
        "host": _cmd_host,
        "stats": _cmd_stats,
        "trends": _cmd_trends,
        "domain": _cmd_domain,
        "honeyscore": _cmd_honeyscore,
        "myip": _cmd_myip,
        "info": _cmd_info,
        "alerts": _cmd_alerts,
        "version": _cmd_version,
    }

    handler = handlers.get(args.command)
    if handler is None:  # pragma: no cover - argparse guards this
        parser.error(f"Unknown command: {args.command}")
        return 2

    try:
        return handler(client, args)
    except ShodanError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
