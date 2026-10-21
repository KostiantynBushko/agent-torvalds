"""Tests for the output parsers."""

from __future__ import annotations

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


class TestParseSearchResults:
    def test_parses_tsv_rows(self) -> None:
        stdout = (
            "8.8.8.8\t53\tdns.google\t\n"
            "1.1.1.1\t53\tone.one.one.one\t\n"
        )
        records = parse_search_results(
            stdout, ["ip_str", "port", "hostnames", "data"]
        )

        assert len(records) == 2
        assert records[0]["ip_str"] == "8.8.8.8"
        assert records[0]["port"] == 53
        assert records[0]["hostnames"] == "dns.google"
        assert records[1]["ip_str"] == "1.1.1.1"

    def test_coerces_numeric_fields(self) -> None:
        records = parse_search_results("1.2.3.4\t8080\t\n", ["ip_str", "port", "data"])
        assert records[0]["port"] == 8080

    def test_ignores_blank_lines(self) -> None:
        records = parse_search_results(
            "\n1.2.3.4\t80\t\n\n", ["ip_str", "port", "data"]
        )
        assert len(records) == 1

    def test_missing_trailing_fields_are_padded(self) -> None:
        records = parse_search_results("1.2.3.4\t80\n", ["ip_str", "port", "data"])
        assert records[0]["data"] == ""

    def test_handles_empty_output(self) -> None:
        assert parse_search_results("", ["ip_str"]) == []


class TestParseHostOutput:
    def test_parses_pretty_host(self) -> None:
        stdout = (
            "8.8.8.8\n"
            "Hostnames:            dns.google;google-public-dns-a.google.com\n"
            "City:                 Mountain View\n"
            "Country:              United States\n"
            "Operating System:      Linux\n"
            "Organization:          Google LLC\n"
            "Updated:               2024-01-01T00:00:00.000000\n"
            "Number of open ports:  2\n"
            "Vulnerabilities:       CVE-2021-1234\n"
            "\n"
            "Ports:\n"
            "    53/udp dnsmasq \n"
            "   443/tcp nginx (1.18.0)  (2024-01-01)\n"
        )
        host = parse_host_output(stdout)

        assert host["city"] == "Mountain View"
        assert host["country"] == "United States"
        assert host["os"] == "Linux"
        assert host["org"] == "Google LLC"
        assert host["open_ports_count"] == 2
        assert host["vulnerabilities"] == ["CVE-2021-1234"]
        assert host["hostnames"] == ["dns.google", "google-public-dns-a.google.com"]

    def test_parses_port_entries(self) -> None:
        stdout = "Ports:\n   443/tcp nginx (1.18.0)  (2024-01-01)\n    53/udp dnsmasq \n"
        host = parse_host_output(stdout)

        assert len(host["ports"]) == 2
        assert host["ports"][0]["port"] == 443
        assert host["ports"][0]["transport"] == "tcp"
        assert host["ports"][0]["product"] == "nginx"
        assert host["ports"][0]["version"] == "1.18.0"
        assert host["ports"][0]["date"] == "2024-01-01"
        assert host["ports"][1]["port"] == 53
        assert host["ports"][1]["transport"] == "udp"

    def test_handles_empty_output(self) -> None:
        host = parse_host_output("")
        assert host["ports"] == []
        assert host["vulnerabilities"] == []


class TestParseStats:
    def test_parses_facets(self) -> None:
        stdout = (
            "Top 2 Results for Facet: country\n"
            "United States                    1,234\n"
            "Germany                            42\n"
            "\n"
            "Top 1 Results for Facet: org\n"
            "Google LLC                        99\n"
        )
        facets = parse_stats(stdout)

        assert facets["country"] == [
            {"value": "United States", "count": 1234},
            {"value": "Germany", "count": 42},
        ]
        assert facets["org"] == [{"value": "Google LLC", "count": 99}]

    def test_handles_empty_output(self) -> None:
        assert parse_stats("") == {}


class TestParseTrends:
    def test_parses_monthly_counts(self) -> None:
        stdout = "2017-06               19,799,459\n2017-07               21,077,099\n"
        records = parse_trends(stdout)

        assert len(records) == 2
        assert records[0]["month"] == "2017-06"
        assert records[0]["count"] == 19799459
        assert records[1]["count"] == 21077099

    def test_parses_facet_breakdown(self) -> None:
        stdout = (
            "2017-06\n"
            "  os\n"
            "    Linux 3.x                                          146,502\n"
            "    Windows 7 or 8                                       2,189\n"
        )
        records = parse_trends(stdout)

        assert len(records) == 1
        assert records[0]["month"] == "2017-06"
        assert records[0]["facets"]["os"] == [
            {"value": "Linux 3.x", "count": 146502},
            {"value": "Windows 7 or 8", "count": 2189},
        ]

    def test_handles_na_marker(self) -> None:
        records = parse_trends("2017-06\nN/A\n")
        assert records[0]["count"] == 0


class TestParseDomainInfo:
    def test_parses_records(self) -> None:
        stdout = (
            "EXAMPLE.COM\n"
            "\n"
            "www                             A          93.184.216.34\n"
            "\n"
            "mail                            A          93.184.216.35  Ports: 25, 587\n"
            "\n"
        )
        records = parse_domain_info(stdout)

        assert len(records) == 2
        assert records[0]["subdomain"] == "www"
        assert records[0]["type"] == "A"
        assert records[0]["value"] == "93.184.216.34"
        assert records[0]["ports"] == []
        assert records[1]["ports"] == [25, 587]

    def test_handles_empty_output(self) -> None:
        assert parse_domain_info("") == []


class TestParseAlertList:
    def test_parses_alerts(self) -> None:
        stdout = (
            "# Alert ID       Name                 IP/ Network\n"
            "abcdef123456     my-alert             8.8.8.0/24, 1.1.1.0/24 \n"
            "Triggers: new_service, malware\n"
            "0123456789ab     other-alert          9.9.9.0/24 \n"
            "expired\n"
        )
        alerts = parse_alert_list(stdout)

        assert len(alerts) == 2
        assert alerts[0]["id"] == "abcdef123456"
        assert alerts[0]["name"] == "my-alert"
        assert alerts[0]["networks"] == ["8.8.8.0/24", "1.1.1.0/24"]
        assert alerts[0]["triggers"] == ["new_service", "malware"]
        assert alerts[1]["expired"] is True

    def test_handles_empty_output(self) -> None:
        assert parse_alert_list("") == []


class TestParseScanList:
    def test_parses_scans(self) -> None:
        stdout = (
            "# 2 Scans Total - Showing 10 most recent scans:\n"
            "# Scan ID       Status         Size        Timestamp\n"
            "abc-123        RUNNING        1024        2024-01-01T00:00:00.000000\n"
        )
        scans = parse_scan_list(stdout)

        assert len(scans) == 1
        assert scans[0]["id"] == "abc-123"
        assert scans[0]["status"] == "RUNNING"
        assert scans[0]["size"] == 1024


class TestParseMisc:
    def test_parse_info(self) -> None:
        stdout = "Query credits available: 100\nScan credits available: 50\n"
        info = parse_info(stdout)
        assert info["query_credits"] == 100
        assert info["scan_credits"] == 50

    def test_parse_honeyscore(self) -> None:
        stdout = "Honeypot detected\nScore: 1.0\n"
        score = parse_honeyscore(stdout)
        assert score["verdict"] == "Honeypot detected"
        assert score["score"] == 1.0
