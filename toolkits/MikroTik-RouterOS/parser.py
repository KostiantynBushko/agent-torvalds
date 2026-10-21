"""
Parsers for RouterOS CLI output.

RouterOS prints its tables in a fixed-width, column-aligned format::

    Flags: R - RUNNING
    Columns: NAME, TYPE, ACTUAL-MTU, L2MTU
     0  R ether1      ether        1500    1598
     1  R ether2      ether        1500    1598

and its ``detail`` output in a script-friendly ``key=value`` form::

     0 name="ether1" default-name="ether1" type="ether" mtu=1500

The parsers here are deliberately forgiving. RouterOS output varies between
versions, models and locales, and a parser that raises on an unexpected
format is worse than one that returns a partial result.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import re
from typing import Optional

from .models import RouterIdentity

__all__ = [
    "parse_print_table",
    "parse_detail",
    "parse_identity",
    "parse_key_value_pairs",
]


#: ``Columns: NAME, TYPE, ACTUAL-MTU`` - the declared column order.
_COLUMNS_RE = re.compile(r"^Columns:\s*(?P<columns>.*)$", re.IGNORECASE)

#: ``Flags: R - RUNNING`` - the flag legend.
_FLAGS_RE = re.compile(r"^Flags:\s*(?P<flags>.*)$", re.IGNORECASE)

#: A numbered row: ``  0  R ether1  ether  1500  1598``.
_ROW_RE = re.compile(r"^\s*(?P<index>\d+)\s+(?P<rest>.*)$")

#: A flag token inside a row: ``R``, ``X``, ``D``, ``B`` ...
_FLAG_TOKEN_RE = re.compile(r"^(?P<flags>[A-Z]+)\s+(?P<rest>.*)$")

#: ``key=value`` inside a ``detail`` row.
_DETAIL_KV_RE = re.compile(r"(?P<key>[A-Za-z0-9_.-]+)=(?P<value>\"[^\"]*\"|\S*)")

#: ``  uptime: 3d4h5m6s`` - a ``key: value`` property line.
#:
#: A key is a run of letters, digits, spaces, dots, underscores and hyphens
#: that is followed by a colon. The value part is deliberately *not* part of
#: the match, so that several properties on one compact line can be found
#: with :meth:`re.Pattern.finditer`.
#:
#: The key may not contain a colon and may not be preceded by a word
#: character, otherwise the value of one property would be mistaken for the
#: key of the next one.
_PROPERTY_RE = re.compile(
    r"(?<![A-Za-z0-9_.\-/])"
    r"(?P<key>[A-Za-z][A-Za-z0-9_.\-/]*)"
    r"\s*:\s*"
)

#: A quoted value, e.g. ``"RB5009UG+S+"``.
_QUOTED_RE = re.compile(r'"(?P<value>[^"]*)"')


def _strip_quotes(value: str) -> str:
    """Remove a single layer of surrounding double quotes."""
    value = value.strip()
    match = _QUOTED_RE.fullmatch(value)
    if match:
        return match.group("value")
    return value


def _split_columns(line: str) -> list[str]:
    """Split a table row into its cell values.

    RouterOS aligns columns with two-or-more spaces, but a cell value may
    itself contain a single space (``actual-mtu`` values, interface types).
    A run of two or more spaces therefore marks a column boundary.
    """
    stripped = line.strip()
    if not stripped:
        return []
    return [cell for cell in re.split(r"\s{2,}", stripped) if cell]


def _extract_flags(rest: str) -> tuple[list[str], str]:
    """Split a leading flag token off a row.

    Returns:
        ``(flags, remainder)``. The flag list is empty when the row has no
        flag column.
    """
    match = _FLAG_TOKEN_RE.match(rest)
    if not match:
        return [], rest
    # A flag column consists of upper-case letters only. A row that begins
    # with a word like "ether1" is not a flag column.
    flags = match.group("flags")
    if not flags.isalpha() or not flags.isupper():
        return [], rest
    return list(flags), match.group("rest")


def parse_print_table(text: str) -> list[dict]:
    """Parse a RouterOS ``print`` table into a list of row dictionaries.

    The ``Flags:`` and ``Columns:`` header lines are consumed. Each data row
    becomes a dictionary keyed by the column names; a row that carries a flag
    column gets a ``"flags"`` entry as well, and every row gets its
    zero-based ``"index"``.

    Args:
        text: The raw ``print`` output.

    Returns:
        One dictionary per row. Empty when the table is empty.
    """
    if not text:
        return []

    columns: list[str] = []
    rows: list[dict] = []
    index = 0

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        columns_match = _COLUMNS_RE.match(line.strip())
        if columns_match:
            columns = [
                col.strip()
                for col in columns_match.group("columns").split(",")
                if col.strip()
            ]
            continue

        if _FLAGS_RE.match(line.strip()):
            # The flag legend is metadata, not a row.
            continue

        row_match = _ROW_RE.match(line)
        if row_match:
            rest = row_match.group("rest")
        else:
            # Some tables are printed without a leading index column
            # (e.g. "/ip/address/print"). Such a row still has cells.
            rest = line

        flags, rest = _extract_flags(rest)
        cells = _split_columns(rest)

        if not cells:
            continue

        entry: dict = {"index": index}
        if flags:
            entry["flags"] = flags

        if columns:
            for position, name in enumerate(columns):
                entry[name] = cells[position] if position < len(cells) else ""
        else:
            # No ``Columns:`` header - fall back to positional names.
            for position, cell in enumerate(cells):
                entry[f"column_{position}"] = cell

        rows.append(entry)
        index += 1

    return rows


def parse_detail(text: str) -> list[dict]:
    """Parse a RouterOS ``detail`` table into a list of row dictionaries.

    The ``detail`` format prints one item per block, with each property on
    its own line as ``key=value``::

         0 name="ether1" type="ether" mtu=1500
         1 name="ether2" type="ether" mtu=1500

    A property whose value contains spaces is printed by RouterOS on its own
    continuation line; such a line has no ``=`` and is appended to the
    previous value.

    Args:
        text: The raw ``detail`` output.

    Returns:
        One dictionary per item. Empty when there is no output.
    """
    if not text:
        return []

    rows: list[dict] = []
    current: dict = {}
    last_key: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if _COLUMNS_RE.match(line) or _FLAGS_RE.match(line):
            continue

        # A new item starts with its index.
        row_match = _ROW_RE.match(line)
        if row_match and "=" in row_match.group("rest"):
            if current:
                rows.append(current)
            current = {"index": len(rows)}
            last_key = None
            body = row_match.group("rest")
        elif "=" in line and current:
            body = line
        elif current:
            # A continuation of the previous property.
            if last_key is not None:
                current[last_key] = f"{current.get(last_key, '')} {line}".strip()
            continue
        else:
            continue

        for match in _DETAIL_KV_RE.finditer(body):
            key = match.group("key")
            value = _strip_quotes(match.group("value"))
            current[key] = value
            last_key = key

    if current:
        rows.append(current)

    return rows


def _normalise_key(key: str) -> str:
    """Normalise a property name to a snake_case lookup key."""
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def parse_key_value_pairs(text: str) -> dict:
    """Parse ``key: value`` property lines into a dictionary.

    Used for the ``detail``-free property output of commands such as
    ``/system/resource/print``.

    Two layouts are supported:

    * one property per line (the classic RouterOS layout)::

          uptime: 3d4h5m6s
          cpu-load: 3%

    * several properties on one line (the compact RouterOS 7 layout)::

          uptime: 3d4h5m6s cpu-load: 3% free-memory: 32.9MiB

    Args:
        text: The raw output.

    Returns:
        A mapping of property name to value. Values are stripped of
        surrounding quotes.
    """
    result: dict = {}
    if not text:
        return result

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        matches = list(_PROPERTY_RE.finditer(line))
        if not matches:
            continue

        # A single match on the line: the value is the rest of the line.
        if len(matches) == 1:
            match = matches[0]
            key = _normalise_key(match.group("key"))
            value = _strip_quotes(line[match.end() :].strip())
            result[key] = value
            continue

        # Several matches: each value runs up to the next key. The last
        # value runs to the end of the line.
        for position, match in enumerate(matches):
            key = _normalise_key(match.group("key"))
            # ``match.end()`` is the end of the whole match, i.e. after the
            # colon and any whitespace - that is where the value starts.
            start = match.end()
            if position + 1 < len(matches):
                end = matches[position + 1].start()
            else:
                end = len(line)
            value = _strip_quotes(line[start:end].strip())
            result[key] = value

    return result


#: Maps the property names printed by ``/system/resource/print`` onto the
#: fields of :class:`~.models.RouterIdentity`.
_IDENTITY_FIELDS: dict[str, str] = {
    "uptime": "uptime",
    "cpu": "cpu_load",
    "cpu_count": "cpu_count",
    "cpu_frequency": "cpu_frequency",
    "cpu_load": "cpu_load",
    "free_memory": "free_memory",
    "total_memory": "total_memory",
    "free_hdd_space": "free_disk",
    "total_hdd_space": "total_disk",
    "free_disk": "free_disk",
    "total_disk": "total_disk",
    "board_name": "board_name",
    "model": "model",
    "serial_number": "serial_number",
    "routeros_version": "routeros_version",
    "firmware_version": "firmware_version",
    "architecture_name": "architecture",
    "architecture": "architecture",
    "version": "routeros_version",
}


def parse_identity(text: str) -> RouterIdentity:
    """Parse the output of ``/system/resource/print``.

    RouterOS prints the properties either as indented ``key: value`` lines
    (the classic layout) or as a compact ``key: value`` block. Both are
    accepted. Unknown properties are ignored, and a property that is absent
    stays ``None``.

    Args:
        text: The raw output of ``/system/resource/print``.

    Returns:
        A :class:`~.models.RouterIdentity` with whatever could be parsed.
    """
    properties = parse_key_value_pairs(text)

    values: dict = {}
    for raw_key, raw_value in properties.items():
        field = _IDENTITY_FIELDS.get(raw_key)
        if field is None:
            # The "version" line carries both the RouterOS and the firmware
            # version, separated by whitespace.
            continue
        value = raw_value.strip()
        if value:
            values[field] = value

    # RouterOS 7 prints the RouterOS version and the firmware version on a
    # single "version" line: "7.19.4 (stable)".
    version = properties.get("version")
    if version:
        if "routeros_version" not in values:
            values["routeros_version"] = version
        if "firmware_version" not in values and " " in version:
            values["firmware_version"] = version.split(" ", 1)[1].strip("() ")

    return RouterIdentity(**values)
