"""
Tests for the RouterOS output parsers.

These tests live inside the hyphenated package directory, so they use
**relative** imports (``from ..parser import ...``).

This directory must **not** contain an ``__init__.py`` - see
MODULE_SPECIFICATION.md section 3.4. The suite runs under
``--import-mode=importlib``, which ``pytest.ini`` sets through ``addopts``.
"""

from __future__ import annotations

from ..parser import (
    parse_detail,
    parse_identity,
    parse_key_value_pairs,
    parse_print_table,
)


# ---------------------------------------------------------------------------
# parse_print_table
# ---------------------------------------------------------------------------

PRINT_WITH_FLAGS = """Flags: R - RUNNING
Columns: NAME, TYPE, ACTUAL-MTU, L2MTU
  0  R ether1      ether        1500    1598
  1  R ether2      ether        1500    1598
"""


def test_parse_print_table_with_flags_and_columns():
    rows = parse_print_table(PRINT_WITH_FLAGS)

    assert len(rows) == 2
    assert rows[0]["index"] == 0
    assert rows[0]["flags"] == ["R"]
    assert rows[0]["NAME"] == "ether1"
    assert rows[0]["TYPE"] == "ether"
    assert rows[0]["ACTUAL-MTU"] == "1500"
    assert rows[0]["L2MTU"] == "1598"
    assert rows[1]["NAME"] == "ether2"


def test_parse_print_table_without_a_flags_column():
    text = """Columns: ADDRESS, NETWORK, INTERFACE
  192.168.88.1/24  192.168.88.0  ether1
"""

    rows = parse_print_table(text)

    assert len(rows) == 1
    assert rows[0]["ADDRESS"] == "192.168.88.1/24"
    assert rows[0]["NETWORK"] == "192.168.88.0"
    assert rows[0]["INTERFACE"] == "ether1"
    assert "flags" not in rows[0]


def test_parse_print_table_with_a_single_row():
    rows = parse_print_table("Columns: NAME\n  0 ether1\n")

    assert len(rows) == 1
    assert rows[0]["NAME"] == "ether1"


def test_parse_print_table_with_an_empty_result_set():
    assert parse_print_table("") == []
    assert parse_print_table("Flags: R - RUNNING\nColumns: NAME\n") == []


def test_parse_print_table_ignores_the_header_lines():
    rows = parse_print_table(PRINT_WITH_FLAGS)

    for row in rows:
        assert "Flags:" not in row.values()
        assert "Columns:" not in row.values()


def test_parse_print_table_without_a_columns_header():
    """Positional names are used when the router prints no Columns line."""
    rows = parse_print_table("  0  R ether1  1500\n")

    assert len(rows) == 1
    assert rows[0]["flags"] == ["R"]
    assert rows[0]["column_0"] == "ether1"
    assert rows[0]["column_1"] == "1500"


def test_parse_print_table_pads_a_short_row():
    rows = parse_print_table("Columns: NAME, TYPE, MTU\n  0 ether1\n")

    assert rows[0]["NAME"] == "ether1"
    assert rows[0]["TYPE"] == ""
    assert rows[0]["MTU"] == ""


# ---------------------------------------------------------------------------
# parse_detail
# ---------------------------------------------------------------------------

DETAIL_TEXT = """ 0 name="ether1" default-name="ether1" type="ether" mtu=1500 l2mtu=1598
 1 name="ether2" default-name="ether2" type="ether" mtu=1500 l2mtu=1598
"""


def test_parse_detail():
    rows = parse_detail(DETAIL_TEXT)

    assert len(rows) == 2
    assert rows[0]["index"] == 0
    assert rows[0]["name"] == "ether1"
    assert rows[0]["default-name"] == "ether1"
    assert rows[0]["type"] == "ether"
    assert rows[0]["mtu"] == "1500"
    assert rows[1]["name"] == "ether2"


def test_parse_detail_strips_quotes():
    rows = parse_detail(' 0 name="ether1"\n')
    assert rows[0]["name"] == "ether1"


def test_parse_detail_with_no_output():
    assert parse_detail("") == []


def test_parse_detail_with_one_item():
    rows = parse_detail(' 0 name="ether1" mtu=1500\n')
    assert len(rows) == 1
    assert rows[0]["name"] == "ether1"


# ---------------------------------------------------------------------------
# parse_key_value_pairs
# ---------------------------------------------------------------------------

def test_parse_key_value_pairs():
    result = parse_key_value_pairs(
        """
                   uptime: 3d4h5m6s
            cpu-load: 3%
           free-memory: 32.9MiB
"""
    )

    assert result["uptime"] == "3d4h5m6s"
    assert result["cpu_load"] == "3%"
    assert result["free_memory"] == "32.9MiB"


def test_parse_key_value_pairs_with_empty_input():
    assert parse_key_value_pairs("") == {}


# ---------------------------------------------------------------------------
# parse_identity
# ---------------------------------------------------------------------------

IDENTITY_TEXT = """                   uptime: 3d4h5m6s
                  cpu: ARM64
                cpu-count: 4
            cpu-frequency: 1600MHz
                cpu-load: 3%
           free-memory: 32.9MiB
          total-memory: 64.0MiB
        free-hdd-space: 4.2MiB
       total-hdd-space: 16.0MiB
             board-name: RB5009UG+S+
          model: RB5009UG+S+
     serial-number: HEX1234567890
     routeros-version: 7.19.4
     firmware-version: 7.19.4
  architecture-name: arm64
"""


def test_parse_identity():
    identity = parse_identity(IDENTITY_TEXT)

    assert identity.uptime == "3d4h5m6s"
    assert identity.model == "RB5009UG+S+"
    assert identity.serial_number == "HEX1234567890"
    assert identity.routeros_version == "7.19.4"
    assert identity.firmware_version == "7.19.4"
    assert identity.cpu_count == "4"
    assert identity.cpu_frequency == "1600MHz"
    assert identity.cpu_load == "3%"
    assert identity.free_memory == "32.9MiB"
    assert identity.total_memory == "64.0MiB"
    assert identity.free_disk == "4.2MiB"
    assert identity.total_disk == "16.0MiB"
    assert identity.architecture == "arm64"


def test_parse_identity_with_a_compact_output():
    """RouterOS 7 prints the properties as one compact line."""
    identity = parse_identity(
        "uptime: 3d4h5m6s cpu: ARM64 cpu-count: 4 free-memory: 32.9MiB"
    )

    assert identity.uptime == "3d4h5m6s"
    assert identity.cpu_count == "4"
    assert identity.free_memory == "32.9MiB"


def test_parse_identity_with_empty_output():
    identity = parse_identity("")

    assert identity.uptime is None
    assert identity.model is None
    assert identity.serial_number is None


def test_parse_identity_ignores_unknown_properties():
    identity = parse_identity("uptime: 1d some-future-property: whatever\n")

    assert identity.uptime == "1d"
