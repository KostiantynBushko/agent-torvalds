"""
Parsers that turn Shodan CLI text output into structured Python data.

The Shodan CLI is a *text* interface: it prints human-readable tables rather
than emitting JSON.  These helpers reverse that formatting so the tools can
hand an LLM clean, structured records.

Every parser is defensive: it never raises on unexpected input, it simply
returns whatever it could confidently extract.  This keeps a single malformed
record from aborting an entire agent turn.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

__all__ = [
    "parse_search_results",
    "parse_host_output",
    "parse_stats",
    "parse_trends",
    "parse_domain_info",
    "parse_alert_list",
    "parse_scan_list",
    "parse_info",
    "parse_honeyscore",
    "parse_key_value_lines",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d[\d,]*")
_LABEL_RE = re.compile(r"^([^:]{1,40}?):\s*(.*)$")


def _to_int(value: str) -> Optional[int]:
    """Convert a possibly comma-grouped number to an int."""
    if value is None:
        return None
    cleaned = value.replace(",", "").strip()
    try:
        return int(cleaned)
    except (TypeError, ValueError):
        return None


def _split_tsv_row(line: str, expected: int) -> List[str]:
    """Split a TSV row, tolerating a trailing separator.

    The Shodan CLI appends the separator to *every* field, including the last,
    which yields one extra empty column.  We drop it when it is empty.
    """
    parts = line.split("\t")
    if len(parts) > expected and parts[-1] == "":
        parts = parts[:-1]
    while len(parts) < expected:
        parts.append("")
    return parts[:expected]


def _coerce(value: str) -> Any:
    """Convert a raw TSV cell into an int when it looks numeric."""
    stripped = value.strip()
    if stripped and re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return value


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def parse_search_results(
    stdout: str,
    fields: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Parse the tab-separated output of ``shodan search``.

    The CLI prints one row per match, with fields in the order given by the
    ``--fields`` option.  List-valued fields are joined with ``;``.

    Args:
        stdout: Raw stdout captured from the CLI.
        fields: The ordered list of field names that were requested.  When
            omitted, the first column is assumed to be ``ip_str`` and any
            additional columns get generic names.

    Returns:
        A list of dictionaries keyed by field name.
    """
    field_names = list(fields) if fields else ["ip_str"]
    records: List[Dict[str, Any]] = []

    for raw_line in stdout.splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue

        values = _split_tsv_row(line, len(field_names))
        record: Dict[str, Any] = {}
        for index, name in enumerate(field_names):
            value = values[index] if index < len(values) else ""
            record[name] = _coerce(value)
        records.append(record)

    return records


# ---------------------------------------------------------------------------
# host
# ---------------------------------------------------------------------------


def parse_host_output(stdout: str) -> Dict[str, Any]:
    """Parse the output of ``shodan host`` (pretty format).

    The pretty format is a sequence of ``Label: value`` lines followed by a
    ``Ports:`` section listing one service per line.

    Returns:
        A dictionary with general host attributes and a ``ports`` list.
    """
    host: Dict[str, Any] = {"ports": [], "vulnerabilities": [], "hostnames": []}
    in_ports = False

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.lower() == "ports:":
            in_ports = True
            continue

        if in_ports:
            port_entry = _parse_port_line(line)
            if port_entry:
                host["ports"].append(port_entry)
            continue

        match = _LABEL_RE.match(line)
        if not match:
            continue

        label = match.group(1).strip()
        value = match.group(2).strip()

        key = _normalise_label(label)
        if key is None:
            continue

        if key == "hostnames":
            host["hostnames"] = [h for h in value.split(";") if h]
        elif key == "vulnerabilities":
            host["vulnerabilities"] = [v.strip() for v in value.split() if v.strip()]
        elif key == "open_ports_count":
            host["open_ports_count"] = _to_int(value)
        else:
            host[key] = value

    return host


def _normalise_label(label: str) -> Optional[str]:
    """Map a pretty-print label to a stable snake_case key."""
    mapping = {
        "hostnames": "hostnames",
        "city": "city",
        "country": "country",
        "operating system": "os",
        "organization": "org",
        "updated": "last_update",
        "number of open ports": "open_ports_count",
        "vulnerabilities": "vulnerabilities",
    }
    return mapping.get(label.lower())


def _parse_port_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single line of the ``Ports:`` section.

    Expected shape::

        80/tcp Apache (2.4.7)   (2017-06-14)
        443/tcp nginx
    """
    match = re.match(
        r"^(?P<port>\d+)\s*(?:/\s*(?P<transport>\w+))?\s*(?P<rest>.*)$",
        line,
    )
    if not match:
        return None

    rest = match.group("rest").strip()
    entry: Dict[str, Any] = {"port": int(match.group("port"))}

    transport = match.group("transport")
    if transport:
        entry["transport"] = transport

    # Optional trailing "(YYYY-MM-DD)" history marker.
    history = re.search(r"\((?P<date>\d{4}-\d{2}-\d{2})\)\s*$", rest)
    if history:
        entry["date"] = history.group("date")
        rest = rest[: history.start()].strip()

    # "product (version)" or just "product".
    product_match = re.match(
        r"^(?P<product>.*?)\s*\((?P<version>[^()]*)\)\s*$", rest
    )
    if product_match:
        entry["product"] = product_match.group("product").strip()
        entry["version"] = product_match.group("version").strip()
    elif rest:
        entry["product"] = rest

    return entry


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def parse_stats(stdout: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse the output of ``shodan stats``.

    The CLI prints one block per facet::

        Top 3 Results for Facet: country
        United States                    1,234
        Germany                            42

    Returns:
        Mapping of facet name to a list of ``{"value", "count"}`` dicts.
    """
    facets: Dict[str, List[Dict[str, Any]]] = {}
    current: Optional[str] = None
    header_re = re.compile(r"^Top\s+\d+\s+Results for Facet:\s*(?P<facet>.+)$")

    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        header = header_re.match(line.strip())
        if header:
            current = header.group("facet").strip()
            facets.setdefault(current, [])
            continue

        if current is None:
            continue

        # The value and count are separated by whitespace; the count is the
        # trailing numeric token.
        count_match = re.search(r"(?P<count>\d[\d,]*)\s*$", line)
        if not count_match:
            continue

        count = _to_int(count_match.group("count"))
        value = line[: count_match.start()].strip()
        if not value:
            continue

        facets[current].append({"value": value, "count": count})

    return facets


# ---------------------------------------------------------------------------
# trends
# ---------------------------------------------------------------------------


def parse_trends(stdout: str) -> List[Dict[str, Any]]:
    """Parse the output of ``shodan trends``.

    Two shapes are supported:

    * Without facets — ``2017-06        19,799,459``
    * With facets — a month, the facet name, then indented value/count rows.

    Returns:
        A list of ``{"month", "count", "facets"}`` records.
    """
    records: List[Dict[str, Any]] = []
    month_re = re.compile(r"^(?P<month>\d{4}-\d{2})(?P<rest>\s.*)?$")
    current: Optional[Dict[str, Any]] = None
    current_facet: Optional[str] = None

    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue

        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip())

        # A month header starts a new record.  Without facets the count is
        # appended to the same line, so it is handled here too.
        month_match = month_re.match(stripped) if indent == 0 else None
        if month_match:
            current = {
                "month": month_match.group("month"),
                "count": None,
                "facets": {},
            }
            records.append(current)
            current_facet = None

            rest = (month_match.group("rest") or "").strip()
            if rest:
                if rest.upper() == "N/A":
                    current["count"] = 0
                else:
                    count_match = re.search(r"(?P<count>\d[\d,]*)\s*$", rest)
                    if count_match:
                        current["count"] = _to_int(count_match.group("count"))
            continue

        if current is None:
            continue

        # "N/A" is emitted for months with no data.
        if stripped.upper() == "N/A":
            current["count"] = 0
            continue

        # A facet name line is indented by two spaces and carries no count.
        if indent == 2:
            current_facet = stripped
            current["facets"].setdefault(current_facet, [])
            continue

        count_match = re.search(r"(?P<count>\d[\d,]*)\s*$", stripped)
        if not count_match:
            continue

        count = _to_int(count_match.group("count"))
        label = stripped[: count_match.start()].strip()

        if indent >= 4 and current_facet is not None:
            current["facets"].setdefault(current_facet, []).append(
                {"value": label, "count": count}
            )
            continue

        if indent == 0:
            current["count"] = count

    return records


# ---------------------------------------------------------------------------
# domain
# ---------------------------------------------------------------------------


def parse_domain_info(stdout: str) -> List[Dict[str, Any]]:
    """Parse the output of ``shodan domain``.

    Each record is printed as ``subdomain  TYPE  value`` optionally followed by
    a ``Ports:`` line.

    Returns:
        A list of ``{"subdomain", "type", "value", "ports"}`` dicts.
    """
    records: List[Dict[str, Any]] = []
    record_re = re.compile(
        r"^(?P<subdomain>\S+)\s+(?P<type>[A-Z0-9]+)\s+(?P<value>\S+)"
    )
    ports_re = re.compile(r"Ports:\s*(?P<ports>[\d,\s]+)$")

    def _parse_ports(text: str) -> List[int]:
        """Extract a list of port numbers from a "Ports: 25, 587" fragment."""
        return [
            int(part)
            for part in re.findall(r"\d+", text)
        ]

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # The CLI appends " Ports: 25, 587" to the record line itself.
        ports: List[int] = []
        ports_match = ports_re.search(line)
        if ports_match:
            ports = _parse_ports(ports_match.group("ports"))
            line = line[: ports_match.start()].strip()

        if line.lower().startswith("ports:"):
            # A standalone "Ports:" line applies to the previous record.
            if records:
                records[-1]["ports"] = _parse_ports(line.split(":", 1)[1])
            continue

        match = record_re.match(line)
        if not match:
            continue

        records.append(
            {
                "subdomain": match.group("subdomain"),
                "type": match.group("type"),
                "value": match.group("value"),
                "ports": ports,
            }
        )

    return records


# ---------------------------------------------------------------------------
# alerts
# ---------------------------------------------------------------------------


def parse_alert_list(stdout: str) -> List[Dict[str, Any]]:
    """Parse the output of ``shodan alert list``.

    Each alert is printed as ``<id>  <name>  <ip/net, ip/net>`` optionally
    followed by a ``Triggers:`` line and an ``expired`` marker.

    Returns:
        A list of alert dictionaries.
    """
    alerts: List[Dict[str, Any]] = []
    line_re = re.compile(
        r"^(?P<id>[0-9a-fA-F]{6,})\s+(?P<name>.+?)\s+"
        r"(?P<networks>[\d./,\sA-Fa-f]+?)\s*$"
    )

    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.strip().startswith("#"):
            continue

        if line.strip().lower().startswith("triggers:"):
            if alerts:
                triggers = line.split(":", 1)[1].strip()
                alerts[-1]["triggers"] = [
                    t.strip() for t in triggers.split(",") if t.strip()
                ]
            continue

        if line.strip().lower() == "expired":
            if alerts:
                alerts[-1]["expired"] = True
            continue

        match = line_re.match(line.strip())
        if not match:
            continue

        networks = [
            n.strip()
            for n in match.group("networks").split(",")
            if n.strip()
        ]
        alerts.append(
            {
                "id": match.group("id"),
                "name": match.group("name").strip(),
                "networks": networks,
                "triggers": [],
                "expired": False,
            }
        )

    return alerts


# ---------------------------------------------------------------------------
# scans
# ---------------------------------------------------------------------------


def parse_scan_list(stdout: str) -> List[Dict[str, Any]]:
    """Parse the output of ``shodan scan list``.

    Returns:
        A list of ``{"id", "status", "size", "created"}`` dicts.
    """
    scans: List[Dict[str, Any]] = []
    line_re = re.compile(
        r"^(?P<id>[0-9a-fA-F-]{6,})\s+(?P<status>\S+)\s+"
        r"(?P<size>\d+)\s+(?P<created>\S+)"
    )

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = line_re.match(line)
        if not match:
            continue

        scans.append(
            {
                "id": match.group("id"),
                "status": match.group("status"),
                "size": int(match.group("size")),
                "created": match.group("created"),
            }
        )

    return scans


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def parse_info(stdout: str) -> Dict[str, Any]:
    """Parse the output of ``shodan info`` (query/scan credits)."""
    info: Dict[str, Any] = {}
    for raw_line in stdout.splitlines():
        match = _LABEL_RE.match(raw_line.strip())
        if not match:
            continue
        label = match.group(1).strip().lower()
        value = match.group(2).strip()
        if "query" in label:
            info["query_credits"] = _to_int(value)
        elif "scan" in label:
            info["scan_credits"] = _to_int(value)
    return info


def parse_honeyscore(stdout: str) -> Dict[str, Any]:
    """Parse the output of ``shodan honeyscore``.

    Returns:
        ``{"verdict": str, "score": float}``.
    """
    verdict = ""
    score: Optional[float] = None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.lower().startswith("score:"):
            try:
                score = float(line.split(":", 1)[1].strip())
            except ValueError:
                score = None
            continue

        if not verdict:
            verdict = line

    return {"verdict": verdict, "score": score}


def parse_key_value_lines(stdout: str) -> Dict[str, str]:
    """Parse generic ``Label: value`` output into a dictionary.

    Used as a fallback for commands whose layout is not formally specified.
    """
    parsed: Dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _LABEL_RE.match(line)
        if match:
            parsed[match.group(1).strip()] = match.group(2).strip()
    return parsed
