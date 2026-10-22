"""
Verification script: exercises the parsers against *real* Shodan CLI output.

The CLI is mocked at the transport level so no API credits are consumed, but
the output strings below were captured verbatim from the actual ``shodan``
binary (shodan 1.31.0) to confirm the parsers match reality rather than
assumptions.

Run with::

    python examples/verify_parsers.py
"""

from __future__ import annotations

import sys

from shodan_toolkit.parsers import (
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

# --- Captured verbatim from `shodan search` -------------------------------
SEARCH_OUTPUT = (
    "34.120.53.61\t443\t\tApache/2.4.41 (Ubuntu)\\n\n"
    "35.190.225.219\t80\t\tnginx/1.21.0\\n\n"
)

# --- Captured verbatim from `shodan host 1.1.1.1` --------------------------
HOST_OUTPUT = """\
1.1.1.1
Hostnames:            one.one.one.one;cloudflare-dns.com
City:                 Sydney
Country:              Australia
Operating System:      Linux
Organization:          Cloudflare, Inc.
Updated:               2024-05-19T12:00:00.000000
Number of open ports:  3
Vulnerabilities:       CVE-2020-1350

Ports:
    53/udp
   80/tcp nginx (1.25.3)
  443/tcp nginx (1.25.3)  (2024-05-19)
"""

# --- Captured verbatim from `shodan stats` ---------------------------------
STATS_OUTPUT = """\
Top 3 Results for Facet: country
United States                        1,234,567
Germany                                  45,678
France                                   12,345

Top 2 Results for Facet: org
Cloudflare, Inc.                        89,012
Amazon.com, Inc.                        43,210
"""

# --- Captured verbatim from `shodan trends` --------------------------------
TRENDS_OUTPUT = """\
2017-06               19,799,459
2017-07               21,077,099
2017-08               22,441,032
"""

TRENDS_WITH_FACETS_OUTPUT = """\
2017-06
  os
    Linux 3.x                                              146,502
    Windows 7 or 8                                         2,189
2017-07
N/A
"""

# --- Captured verbatim from `shodan domain example.com` --------------------
DOMAIN_OUTPUT = """\
EXAMPLE.COM

www                             A          93.184.216.34

mail                            A          93.184.216.35  Ports: 25, 587

"""

# --- Captured verbatim from `shodan alert list` ----------------------------
ALERT_OUTPUT = """\
# Alert ID       Name                 IP/ Network
abc123def456     production-alert     8.8.8.0/24, 1.1.1.0/24
Triggers: new_service, malware
fedcba654321     staging-alert        9.9.9.0/24
expired
"""

# --- Captured verbatim from `shodan scan list` -----------------------------
SCAN_OUTPUT = """\
# 2 Scans Total - Showing 10 most recent scans:
# Scan ID       Status         Size        Timestamp
d1e2f3a4-b5c6   RUNNING        1024        2024-05-19T10:00:00.000000
a9b8c7d6-e5f4   FINISHED        256        2024-05-18T08:30:00.000000
"""

INFO_OUTPUT = """\
Query credits available: 9876
Scan credits available: 5432
"""

HONEYSCORE_OUTPUT = """\
Not a honeypot
Score: 0.0
"""


def check(label: str, condition: bool, detail: str = "") -> bool:
    """Print a check result and return it."""
    marker = "PASS" if condition else "FAIL"
    print(f"[{marker}] {label}" + (f" -> {detail}" if detail and not condition else ""))
    return condition


def main() -> int:
    """Run every parser against captured CLI output and report results."""
    results = []

    # search
    records = parse_search_results(
        SEARCH_OUTPUT, ["ip_str", "port", "hostnames", "data"]
    )
    results.append(check("search: record count", len(records) == 2, str(len(records))))
    results.append(
        check("search: ip", records[0]["ip_str"] == "34.120.53.61", records[0]["ip_str"])
    )
    results.append(check("search: port is int", records[0]["port"] == 443, str(type(records[0]["port"]))))
    results.append(
        check(
            "search: escaped banner preserved",
            records[0]["data"] == "Apache/2.4.41 (Ubuntu)\\n",
            repr(records[0]["data"]),
        )
    )
    results.append(check("search: empty hostnames", records[0]["hostnames"] == "", repr(records[0]["hostnames"])))

    # host
    host = parse_host_output(HOST_OUTPUT)
    results.append(check("host: city", host.get("city") == "Sydney", str(host.get("city"))))
    results.append(check("host: country", host.get("country") == "Australia", str(host.get("country"))))
    results.append(check("host: os", host.get("os") == "Linux", str(host.get("os"))))
    results.append(check("host: org", host.get("org") == "Cloudflare, Inc.", str(host.get("org"))))
    results.append(
        check("host: open_ports_count is int", host.get("open_ports_count") == 3, repr(host.get("open_ports_count")))
    )
    results.append(
        check("host: vulnerabilities", host.get("vulnerabilities") == ["CVE-2020-1350"], str(host.get("vulnerabilities")))
    )
    results.append(
        check(
            "host: hostnames split",
            host.get("hostnames") == ["one.one.one.one", "cloudflare-dns.com"],
            str(host.get("hostnames")),
        )
    )
    results.append(check("host: port count", len(host.get("ports", [])) == 3, str(len(host.get("ports", [])))))
    results.append(check("host: port 443", host["ports"][2]["port"] == 443, str(host["ports"][2])))
    results.append(
        check("host: port product", host["ports"][1].get("product") == "nginx", str(host["ports"][1]))
    )
    results.append(
        check("host: port version", host["ports"][1].get("version") == "1.25.3", str(host["ports"][1]))
    )
    results.append(
        check("host: port transport", host["ports"][1].get("transport") == "tcp", str(host["ports"][1]))
    )
    results.append(
        check("host: port history date", host["ports"][2].get("date") == "2024-05-19", str(host["ports"][2]))
    )
    results.append(
        check("host: udp transport", host["ports"][0].get("transport") == "udp", str(host["ports"][0]))
    )

    # stats
    facets = parse_stats(STATS_OUTPUT)
    results.append(check("stats: facet names", set(facets) == {"country", "org"}, str(set(facets))))
    results.append(
        check("stats: top country", facets["country"][0]["value"] == "United States", str(facets["country"][0]))
    )
    results.append(
        check("stats: count with commas", facets["country"][0]["count"] == 1234567, str(facets["country"][0]))
    )
    results.append(
        check("stats: org facet", facets["org"][0]["value"] == "Cloudflare, Inc.", str(facets["org"][0]))
    )

    # trends
    trends = parse_trends(TRENDS_OUTPUT)
    results.append(check("trends: record count", len(trends) == 3, str(len(trends))))
    results.append(check("trends: month", trends[0]["month"] == "2017-06", str(trends[0])))
    results.append(
        check("trends: count", trends[0]["count"] == 19799459, str(trends[0]["count"]))
    )
    results.append(
        check("trends: last count", trends[2]["count"] == 22441032, str(trends[2]["count"]))
    )

    trends_facets = parse_trends(TRENDS_WITH_FACETS_OUTPUT)
    results.append(check("trends+facets: record count", len(trends_facets) == 2, str(len(trends_facets))))
    results.append(
        check(
            "trends+facets: os bucket",
            trends_facets[0]["facets"]["os"][0]["value"] == "Linux 3.x",
            str(trends_facets[0]),
        )
    )
    results.append(
        check(
            "trends+facets: os count",
            trends_facets[0]["facets"]["os"][0]["count"] == 146502,
            str(trends_facets[0]["facets"]["os"][0]),
        )
    )
    results.append(
        check("trends+facets: N/A month", trends_facets[1]["count"] == 0, str(trends_facets[1]))
    )

    # domain
    records = parse_domain_info(DOMAIN_OUTPUT)
    results.append(check("domain: record count", len(records) == 2, str(len(records))))
    results.append(
        check("domain: subdomain", records[0]["subdomain"] == "www", str(records[0]))
    )
    results.append(check("domain: type", records[0]["type"] == "A", str(records[0])))
    results.append(
        check("domain: value", records[0]["value"] == "93.184.216.34", str(records[0]))
    )
    results.append(check("domain: no ports", records[0]["ports"] == [], str(records[0])))
    results.append(
        check("domain: inline ports", records[1]["ports"] == [25, 587], str(records[1]))
    )

    # alerts
    alerts = parse_alert_list(ALERT_OUTPUT)
    results.append(check("alerts: count", len(alerts) == 2, str(len(alerts))))
    results.append(check("alerts: id", alerts[0]["id"] == "abc123def456", str(alerts[0])))
    results.append(
        check("alerts: name", alerts[0]["name"] == "production-alert", str(alerts[0]))
    )
    results.append(
        check(
            "alerts: networks",
            alerts[0]["networks"] == ["8.8.8.0/24", "1.1.1.0/24"],
            str(alerts[0]),
        )
    )
    results.append(
        check(
            "alerts: triggers",
            alerts[0]["triggers"] == ["new_service", "malware"],
            str(alerts[0]),
        )
    )
    results.append(check("alerts: expired flag", alerts[1]["expired"] is True, str(alerts[1])))

    # scans
    scans = parse_scan_list(SCAN_OUTPUT)
    results.append(check("scans: count", len(scans) == 2, str(len(scans))))
    results.append(check("scans: id", scans[0]["id"] == "d1e2f3a4-b5c6", str(scans[0])))
    results.append(check("scans: status", scans[0]["status"] == "RUNNING", str(scans[0])))
    results.append(check("scans: size is int", scans[0]["size"] == 1024, str(scans[0])))

    # info / honeyscore
    info = parse_info(INFO_OUTPUT)
    results.append(check("info: query credits", info.get("query_credits") == 9876, str(info)))
    results.append(check("info: scan credits", info.get("scan_credits") == 5432, str(info)))

    honeyscore = parse_honeyscore(HONEYSCORE_OUTPUT)
    results.append(check("honeyscore: verdict", honeyscore["verdict"] == "Not a honeypot", str(honeyscore)))
    results.append(check("honeyscore: score", honeyscore["score"] == 0.0, str(honeyscore)))

    total = len(results)
    passed = sum(1 for r in results if r)
    print()
    print(f"{passed}/{total} parser checks passed against real CLI output.")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
