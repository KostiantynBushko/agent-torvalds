"""
Tests for the MikroTik RouterOS parsers as used by the adapter.

The package-local suite (``toolkits/MikroTik-RouterOS/tests/test_parser.py``)
covers the parsers in depth. This file verifies that the **adapter** turns
the raw router output into the structures the tools return: the identity
dictionary, the configuration rows and the decoded interface flags.

No network access is required.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_mikrotik_toolkit as mikrotik

from toolkits.mikrotik_routeros.parser import (
    parse_detail,
    parse_identity,
    parse_key_value_pairs,
    parse_print_table,
)


#: A real ``/system/resource/print`` output.
IDENTITY_OUTPUT = """                   uptime: 3d4h5m6s
                  version: 7.19.4 (stable)
         factory-software: 7.19.4
              free-hdd-space: 21.9MiB
         total-hdd-space: 64.0MiB
                cpu-load: 3%
             cpu-count: 4
           cpu-frequency: 1600MHz
               free-memory: 32.9MiB
              total-memory: 64.0MiB
                 board-name: RB5009UG+S+
                   model: RB5009UG+S+
             serial-number: HEX0123456789
       architecture-name: arm64
"""

#: A real ``/interface/print`` output.
INTERFACE_OUTPUT = """Flags: R - RUNNING; S - SLAVE; X - DISABLED
Columns: NAME, TYPE, ACTUAL-MTU, L2MTU, MAC-ADDRESS
  0  R ether1      ether        1500    1598  48:A9:8A:11:22:33
  1  R ether2      ether        1500    1598  48:A9:8A:11:22:34
  2  RS ether3     ether        1500    1598  48:A9:8A:11:22:35
  3  X  ether4     ether        1500    1598  48:A9:8A:11:22:36
"""

#: A real ``/ip/address/print`` output.
ADDRESS_OUTPUT = """Flags: X - DISABLED; I - INVALID, D - DYNAMIC
Columns: ADDRESS, NETWORK, INTERFACE
  0   10.0.0.1/24  10.0.0.0  ether1
  1   192.168.88.1/24  192.168.88.0  ether2
"""

#: A real ``detail`` output.
DETAIL_OUTPUT = """  0 name="ether1" default-name="ether1" type="ether" mtu=1500 l2mtu=1598
  1 name="ether2" default-name="ether2" type="ether" mtu=1500 l2mtu=1598
"""


class TestPrintTable:
    """The ``print`` table parser."""

    def test_parses_the_columns_and_the_rows(self):
        rows = parse_print_table(ADDRESS_OUTPUT)
        assert len(rows) == 2
        assert rows[0]["ADDRESS"] == "10.0.0.1/24"
        assert rows[0]["NETWORK"] == "10.0.0.0"
        assert rows[0]["INTERFACE"] == "ether1"

    def test_decodes_the_flag_column(self):
        rows = parse_print_table(INTERFACE_OUTPUT)
        assert rows[0]["flags"] == ["R"]
        assert rows[2]["flags"] == ["R", "S"]
        assert rows[3]["flags"] == ["X"]

    def test_an_empty_table_yields_no_rows(self):
        assert parse_print_table("") == []
        assert parse_print_table("Flags: R - RUNNING\nColumns: NAME\n") == []

    def test_a_single_row_is_parsed(self):
        rows = parse_print_table("Columns: NAME\n  0 ether1\n")
        assert len(rows) == 1
        assert rows[0]["NAME"] == "ether1"


class TestDetail:
    """The ``detail`` parser."""

    def test_parses_the_key_value_pairs(self):
        rows = parse_detail(DETAIL_OUTPUT)
        assert len(rows) == 2
        assert rows[0]["name"] == "ether1"
        assert rows[0]["type"] == "ether"
        assert rows[0]["mtu"] == "1500"


class TestIdentity:
    """The ``/system/resource/print`` parser."""

    def test_parses_every_published_property(self):
        identity = parse_identity(IDENTITY_OUTPUT).to_dict()

        assert identity["model"] == "RB5009UG+S+"
        assert identity["serial_number"] == "HEX0123456789"
        assert identity["uptime"] == "3d4h5m6s"
        assert identity["cpu_load"] == "3%"
        assert identity["cpu_count"] == "4"
        assert identity["free_memory"] == "32.9MiB"
        assert identity["total_memory"] == "64.0MiB"
        assert identity["free_disk"] == "21.9MiB"
        assert identity["total_disk"] == "64.0MiB"
        assert identity["board_name"] == "RB5009UG+S+"
        assert identity["architecture"] == "arm64"

    def test_splits_the_version_line(self):
        identity = parse_identity(IDENTITY_OUTPUT).to_dict()
        assert identity["routeros_version"] == "7.19.4 (stable)"

    def test_a_missing_property_stays_none(self):
        identity = parse_identity("uptime: 1h\n").to_dict()
        assert identity["uptime"] == "1h"
        assert identity["model"] is None


class TestKeyValuePairs:
    """The property parser."""

    def test_parses_one_property_per_line(self):
        values = parse_key_value_pairs("uptime: 3d\ncpu-load: 5%\n")
        assert values["uptime"] == "3d"
        assert values["cpu_load"] == "5%"

    def test_parses_the_compact_routeros_7_layout(self):
        values = parse_key_value_pairs("uptime: 3d cpu-load: 5% free-memory: 32MiB\n")
        assert values["uptime"] == "3d"
        assert values["cpu_load"] == "5%"
        assert values["free_memory"] == "32MiB"


class TestAdapterHelpers:
    """The adapter's own parsing helpers."""

    def test_the_identity_helper_returns_a_dictionary(self):
        identity = mikrotik._parse_identity(IDENTITY_OUTPUT)
        assert identity["model"] == "RB5009UG+S+"

    def test_the_identity_helper_survives_garbage(self):
        """Garbage in, an empty identity out - never an exception."""
        identity = mikrotik._parse_identity("not a router output")
        assert isinstance(identity, dict)
        assert all(value is None for value in identity.values())

    def test_the_row_helper_parses_a_table(self):
        rows = mikrotik._parse_rows(ADDRESS_OUTPUT)
        assert len(rows) == 2

    def test_the_row_helper_parses_a_detail_table(self):
        rows = mikrotik._parse_rows(DETAIL_OUTPUT, detail=True)
        assert len(rows) == 2
        assert rows[0]["name"] == "ether1"

    def test_the_row_helper_survives_garbage(self):
        assert mikrotik._parse_rows("") == []

    def test_the_interface_helper_decodes_the_flags(self):
        rows = parse_print_table(INTERFACE_OUTPUT)
        interfaces = mikrotik._parse_interfaces(rows)

        by_name = {i["name"]: i for i in interfaces}
        assert by_name["ether1"]["running"] is True
        assert by_name["ether1"]["disabled"] is False
        assert by_name["ether3"]["slave"] is True
        assert by_name["ether4"]["disabled"] is True
        assert by_name["ether4"]["running"] is False

    def test_the_interface_helper_survives_no_rows(self):
        assert mikrotik._parse_interfaces(None) == []


class TestLogErrors:
    """The log error filter."""

    def test_an_error_line_is_reported(self):
        errors = mikrotik._extract_log_errors(
            "jan/02 10:00:00 system,error something broke\n"
        )
        assert len(errors) == 1
        assert "something broke" in errors[0]

    def test_an_info_line_is_not_reported(self):
        errors = mikrotik._extract_log_errors(
            "jan/02 10:00:00 firewall,info input chain accepted\n"
        )
        assert errors == []

    def test_a_debug_line_is_not_reported(self):
        errors = mikrotik._extract_log_errors(
            "jan/02 10:00:00 system,debug a detail message\n"
        )
        assert errors == []

    def test_no_log_means_no_errors(self):
        assert mikrotik._extract_log_errors("") == []
