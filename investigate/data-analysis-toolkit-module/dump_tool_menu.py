#!/usr/bin/env python3
"""Dump the startup tool menu, so two trees can be compared.

The tool menu is behaviour: the retriever matches against the tool
descriptions, the model reads them, and the startup menu groups the
tools by the category in their description.  A refactoring that moves a
toolkit must not change the menu by a single character.

Usage::

    python investigate/data-analysis-toolkit-module/dump_tool_menu.py > menu.txt

The dump is one line per tool: the tool name, the category and the
description, separated by a tab.  The order is the order of the menu.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT))

from agent_tool_selection import _discover_tools  # noqa: E402


def dump() -> str:
    """Return the menu as text - one line per tool."""
    lines: list[str] = []
    for tool in _discover_tools():
        metadata = tool.metadata
        lines.append(
            "\t".join(
                (
                    metadata.name,
                    metadata.description or "",
                    metadata.fn_schema.model_json_schema().get("description", "")
                    if hasattr(metadata, "fn_schema")
                    else "",
                )
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    sys.stdout.write(dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
