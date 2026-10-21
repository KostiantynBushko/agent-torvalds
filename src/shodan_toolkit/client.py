"""
High-level Python client for the Shodan CLI.

:class:`ShodanClient` wraps the text-oriented ``shodan`` command line and
returns structured Python data.  It is the layer that the LlamaIndex tools
delegate to, but it is perfectly usable on its own::

    from shodan_toolkit import ShodanClient

    client = ShodanClient()
    results = client.search("apache", limit=10)
    for record in results:
        print(record["ip_str"], record["port"])
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ShodanConfig, load_config
from .parsers import (
    parse_alert_list,
    parse_domain_info,
    parse_honeyscore,
    parse_host_output,
    parse_info,
    parse_scan_list,
    parse_search_results,
    parse_stats,
    parse_trends,
)
from .runner import (
    CommandResult,
    ShodanCLIError,
    ShodanError,
    ShodanRunner,
)

__all__ = ["ShodanClient"]

# Fields requested by default from `shodan search`.
DEFAULT_SEARCH_FIELDS = ["ip_str", "port", "hostnames", "data"]


class ShodanClient:
    """Structured access to the Shodan CLI.

    Args:
        config: Optional configuration.  When omitted, the configuration is
            resolved from the environment and the config file.
        runner: Optional pre-built runner (mostly useful for testing).
    """

    def __init__(
        self,
        config: Optional[ShodanConfig] = None,
        runner: Optional[ShodanRunner] = None,
    ):
        self.config = config or load_config()
        self._runner = runner or ShodanRunner(
            executable=self.config.executable,
            timeout=self.config.timeout,
            env=self._build_child_env(),
        )

    # -- setup ------------------------------------------------------------

    def _build_child_env(self) -> Dict[str, str]:
        """Build the environment handed to the CLI."""
        env: Dict[str, str] = dict(self.config.extra_env)

        # Point the CLI at our configured credential directory.
        shodan_dir = os.path.expanduser(self.config.shodan_config_dir)
        env["SHODAN_CONFIG_DIR"] = shodan_dir

        if self.config.api_key:
            env["SHODAN_API_KEY"] = self.config.api_key

        return env

    @property
    def runner(self) -> ShodanRunner:
        """The underlying CLI runner."""
        return self._runner

    def is_available(self) -> bool:
        """Return True when the Shodan CLI is installed and on PATH."""
        return self._runner.is_available()

    def version(self) -> str:
        """Return the version of the installed Shodan CLI."""
        return self._runner.version()

    # -- authentication ---------------------------------------------------

    def api_key_path(self) -> Path:
        """Return the path where the Shodan CLI stores its API key."""
        shodan_dir = os.path.expanduser(self.config.shodan_config_dir)
        return Path(shodan_dir) / "api_key"

    def has_api_key(self) -> bool:
        """Return True when an API key file is present."""
        return self.api_key_path().is_file()

    def init(self, api_key: str) -> Dict[str, Any]:
        """Initialise the Shodan CLI with an API key.

        The key is written to the CLI's own config directory with ``0600``
        permissions, exactly as ``shodan init`` would do.

        Args:
            api_key: The Shodan API key.

        Returns:
            ``{"success": bool, "key_file": str, "message": str}``.
        """
        api_key = api_key.strip()
        if not api_key:
            raise ShodanError("An API key is required.")

        shodan_dir = Path(os.path.expanduser(self.config.shodan_config_dir))
        shodan_dir.mkdir(parents=True, exist_ok=True)

        key_file = shodan_dir / "api_key"
        key_file.write_text(api_key, encoding="utf-8")
        os.chmod(key_file, 0o600)

        return {
            "success": True,
            "key_file": str(key_file),
            "message": "API key stored successfully.",
        }

    def account_info(self) -> Dict[str, Any]:
        """Return account information (query/scan credits)."""
        result = self._runner.run(["info"])
        return parse_info(result.stdout)

    # -- search -----------------------------------------------------------

    def search(
        self,
        query: str,
        limit: Optional[int] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search the Shodan database.

        Args:
            query: The Shodan search query (e.g. ``"apache port:80"``).
            limit: Maximum number of results.  Capped at 1000 by Shodan.
            fields: Fields to request.  Defaults to
                ``ip_str,port,hostnames,data``.

        Returns:
            A list of result dictionaries keyed by field name.
        """
        query = (query or "").strip()
        if not query:
            raise ShodanError("A search query is required.")

        if limit is None:
            limit = self.config.max_results
        limit = max(1, min(int(limit), 1000))

        field_names = list(fields) if fields else list(DEFAULT_SEARCH_FIELDS)

        args = [
            "search",
            "--no-color",
            "--fields",
            ",".join(field_names),
            "--limit",
            str(limit),
            query,
        ]

        result = self._runner.run(args)
        return parse_search_results(result.stdout, field_names)

    def count(self, query: str) -> int:
        """Return the number of results matching a query."""
        query = (query or "").strip()
        if not query:
            raise ShodanError("A search query is required.")

        result = self._runner.run(["count", query])
        try:
            return int(result.output.replace(",", ""))
        except ValueError as exc:
            raise ShodanCLIError(
                f"Unable to parse count output: {result.output!r}", result=result
            ) from exc

    def stats(
        self,
        query: str,
        facets: Optional[Sequence[str]] = None,
        limit: int = 10,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Return summary statistics (facets) for a query.

        Args:
            query: The Shodan search query.
            facets: Facet names, e.g. ``["country", "org"]``.
            limit: Number of entries per facet.

        Returns:
            Mapping of facet name to ``{"value", "count"}`` records.
        """
        query = (query or "").strip()
        if not query:
            raise ShodanError("A search query is required.")

        facet_names = list(facets) if facets else ["country", "org"]
        args = [
            "stats",
            "--no-color",
            "--limit",
            str(limit),
            "--facets",
            ",".join(facet_names),
            query,
        ]
        result = self._runner.run(args)
        return parse_stats(result.stdout)

    def trends(
        self,
        query: str,
        facets: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Query the Shodan historical database.

        Args:
            query: The Shodan search query.
            facets: Optional facet names to break the results down by.

        Returns:
            A list of ``{"month", "count", "facets"}`` records.
        """
        query = (query or "").strip()
        if not query:
            raise ShodanError("A search query is required.")

        args = ["trends", "--no-color"]
        if facets:
            args += ["--facets", ",".join(facets)]
        args.append(query)

        result = self._runner.run(args)
        return parse_trends(result.stdout)

    def download(
        self,
        query: str,
        filename: str,
        limit: int = 1000,
        fields: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Download search results into a compressed JSON file.

        Args:
            query: The Shodan search query.
            filename: Output path.  ``.json.gz`` is appended when missing.
            limit: Maximum number of results.
            fields: Optional subset of fields to download.

        Returns:
            A summary dict describing the download.
        """
        query = (query or "").strip()
        if not query:
            raise ShodanError("A search query is required.")
        if not filename.strip():
            raise ShodanError("An output filename is required.")

        args = ["download", "--limit", str(limit)]
        if fields:
            args += ["--fields", ",".join(fields)]
        args += [filename, query]

        result = self._runner.run(args)
        return {
            "success": result.ok,
            "output": result.output,
            "filename": filename
            if filename.endswith(".json.gz")
            else f"{filename}.json.gz",
        }

    # -- host -------------------------------------------------------------

    def host(self, ip: str, history: bool = False) -> Dict[str, Any]:
        """Return all known information for an IP address.

        Args:
            ip: The IPv4/IPv6 address.
            history: Include historical banners.

        Returns:
            A dictionary of host attributes including a ``ports`` list.
        """
        ip = (ip or "").strip()
        if not ip:
            raise ShodanError("An IP address is required.")

        args = ["host", "--no-color", "--format", "pretty"]
        if history:
            args.append("--history")
        args.append(ip)

        result = self._runner.run(args)
        host = parse_host_output(result.stdout)
        host["ip"] = ip
        return host

    def honeyscore(self, ip: str) -> Dict[str, Any]:
        """Check whether an IP address is a honeypot."""
        ip = (ip or "").strip()
        if not ip:
            raise ShodanError("An IP address is required.")

        result = self._runner.run(["honeyscore", ip])
        return parse_honeyscore(result.stdout)

    def myip(self, ipv6: bool = False) -> str:
        """Return the caller's public IP address as seen by Shodan."""
        args = ["myip"]
        if ipv6:
            args.insert(0, "--ipv6")
        result = self._runner.run(args)
        return result.output

    # -- domain -----------------------------------------------------------

    def domain_info(
        self,
        domain: str,
        details: bool = False,
        history: bool = False,
        record_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return DNS records for a domain.

        Args:
            domain: The domain name.
            details: Also resolve host information for the returned IPs.
            history: Include historical DNS data.
            record_type: Restrict to a single record type (e.g. ``A``).

        Returns:
            A list of ``{"subdomain", "type", "value", "ports"}`` records.
        """
        domain = (domain or "").strip()
        if not domain:
            raise ShodanError("A domain name is required.")

        args = ["domain", "--no-color"]
        if details:
            args.append("--details")
        if history:
            args.append("--history")
        if record_type:
            args += ["--type", record_type]
        args.append(domain)

        result = self._runner.run(args)
        return parse_domain_info(result.stdout)

    # -- alerts -----------------------------------------------------------

    def list_alerts(self, expired: bool = True) -> List[Dict[str, Any]]:
        """List the network alerts configured on the account."""
        args = ["alert", "list", "--expired", str(expired).lower()]
        result = self._runner.run(args)
        return parse_alert_list(result.stdout)

    def create_alert(self, name: str, netblocks: Sequence[str]) -> Dict[str, Any]:
        """Create a network alert for one or more netblocks."""
        name = (name or "").strip()
        if not name:
            raise ShodanError("An alert name is required.")
        if not netblocks:
            raise ShodanError("At least one netblock is required.")

        args = ["alert", "create", name, *netblocks]
        result = self._runner.run(args)
        return {
            "success": result.ok,
            "name": name,
            "netblocks": list(netblocks),
            "output": result.output,
        }

    def delete_alert(self, alert_id: str) -> Dict[str, Any]:
        """Delete a network alert by ID."""
        alert_id = (alert_id or "").strip()
        if not alert_id:
            raise ShodanError("An alert ID is required.")

        result = self._runner.run(["alert", "remove", alert_id])
        return {
            "success": result.ok,
            "alert_id": alert_id,
            "output": result.output,
        }

    # -- scans ------------------------------------------------------------

    def list_scans(self) -> List[Dict[str, Any]]:
        """List recently launched on-demand scans."""
        result = self._runner.run(["scan", "list"])
        return parse_scan_list(result.stdout)

    def scan_status(self, scan_id: str) -> str:
        """Return the status of an on-demand scan."""
        scan_id = (scan_id or "").strip()
        if not scan_id:
            raise ShodanError("A scan ID is required.")
        result = self._runner.run(["scan", "status", scan_id])
        return result.output

    def submit_scan(
        self,
        netblocks: Sequence[str],
        wait: int = 20,
        force: bool = False,
        filename: str = "",
    ) -> Dict[str, Any]:
        """Submit an on-demand scan for the given netblocks."""
        if not netblocks:
            raise ShodanError("At least one netblock is required.")

        args = ["scan", "submit", "--wait", str(wait)]
        if force:
            args.append("--force")
        if filename:
            args += ["--filename", filename]
        args += list(netblocks)

        result = self._runner.run(args)
        return {
            "success": result.ok,
            "netblocks": list(netblocks),
            "output": result.output,
        }

    # -- raw escape hatch -------------------------------------------------

    def run_raw(
        self,
        args: Sequence[str],
        check: bool = True,
    ) -> CommandResult:
        """Run an arbitrary Shodan CLI command.

        This is the escape hatch for commands that are not yet modelled by a
        dedicated method.
        """
        return self._runner.run(args, check=check)

    def to_json(self, payload: Any) -> str:
        """Serialise a payload to indented JSON (helper for tool responses)."""
        return json.dumps(payload, indent=2, default=str)
