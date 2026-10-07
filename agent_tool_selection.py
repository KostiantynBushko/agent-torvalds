"""
Tool Selection Module — Interactive startup tool selection.

This module provides utilities for:
  - Discovering all available tools from every toolkit.
  - Grouping tools by category / skill.
  - Parsing user selection input (individual indexes and ranges).
  - Running the interactive selection UI before agent startup.

Used by agent-torvalds.py when the user passes --select.

Category: Infrastructure
"""

import sys
from typing import List, Dict, Optional

from llama_index.core.tools import FunctionTool


# ---------------------------------------------------------------------------
# Toolkit discovery
# ---------------------------------------------------------------------------

def _discover_tools() -> List[FunctionTool]:
    """
    Import every toolkit module and call its get_all_tools() to collect
    the full list of available tools.

    Returns:
        List[FunctionTool]: All discovered tool instances.
    """
    tools: List[FunctionTool] = []

    # Always available
    from agent_math_toolkit import get_all_tools as _get_math
    tools.extend(_get_math())

    from agent_git_toolkit import get_all_tools as _get_git
    tools.extend(_get_git())

    from agent_github_toolkit import get_all_tools as _get_github
    tools.extend(_get_github())

    from agent_os_toolkit import get_all_tools as _get_os
    tools.extend(_get_os())

    from agent_db_toolkit import get_all_tools as _get_db
    tools.extend(_get_db())

    from agent_apt_toolkit import get_all_tools as _get_apt
    tools.extend(_get_apt())

    from agent_cache_system import get_all_tools as _get_cache
    tools.extend(_get_cache())

    from agent_xlsx_toolkit import get_all_tools as _get_xlsx
    tools.extend(_get_xlsx())

    from agent_data_analysis_toolkit import get_all_tools as _get_analysis
    tools.extend(_get_analysis())

    # Platform-specific
    if sys.platform.startswith("linux"):
        from agent_linux_toolkit import get_all_tools as _get_linux
        tools.extend(_get_linux())
    elif sys.platform.startswith("win"):
        from agent_windows_toolkit import get_all_tools as _get_windows
        tools.extend(_get_windows())

    return tools


# ---------------------------------------------------------------------------
# Category extraction helpers
# ---------------------------------------------------------------------------

def _extract_category(description: str) -> str:
    """
    Extract the category tag from a tool description string.

    Tool descriptions follow the pattern:
        "Short description. Category: <CategoryName>"

    Args:
        description: The tool's description metadata.

    Returns:
        Category string, or 'Uncategorized' if none found.
    """
    if "Category:" in description:
        return description.split("Category:")[-1].strip()
    return "Uncategorized"


def group_tools_by_category(tools: List[FunctionTool]) -> Dict[str, List[FunctionTool]]:
    """
    Group tools by their category tag extracted from descriptions.

    Args:
        tools: List of FunctionTool instances.

    Returns:
        Dict mapping category name → list of tools in that category.
    """
    groups: Dict[str, List[FunctionTool]] = {}
    for tool in tools:
        cat = _extract_category(tool.metadata.description)
        groups.setdefault(cat, []).append(tool)
    return groups


# ---------------------------------------------------------------------------
# Selection parser
# ---------------------------------------------------------------------------

def parse_tool_selection(value: str, maximum: int) -> List[int]:
    """
    Parse a user selection string into a sorted list of 1-based indexes.

    Supports:
      - Individual indexes:  "1,3,5"
      - Ranges:              "1-4"
      - Combinations:        "1-3,7,10"

    Args:
        value: Raw user input string.
        maximum: Total number of available items.

    Returns:
        Sorted list of valid 1-based indexes.

    Raises:
        ValueError: On invalid input.
    """
    selected: set = set()

    for part in value.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if start > end:
                raise ValueError(f"Invalid range: {part.strip()}")
            selected.update(range(start, end + 1))
        else:
            selected.add(int(part))

    invalid = [i for i in selected if i < 1 or i > maximum]
    if invalid:
        raise ValueError(
            f"Invalid indexes: {invalid}. Valid values are 1-{maximum}."
        )

    return sorted(selected)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_tools_flat(
    tools: List[FunctionTool],
) -> None:
    """
    Print all tools as a flat numbered list with short descriptions.

    Args:
        tools: List of FunctionTool instances.
    """
    print("\nAvailable tools:\n")
    for idx, tool in enumerate(tools, start=1):
        # Extract short description (first sentence before "Category:")
        desc = tool.metadata.description
        short_desc = desc.split("Category:")[0].strip().rstrip(".")
        print(f"  [{idx}] {tool.metadata.name}")
        print(f"      {short_desc}\n")


def display_categories_for_selection(
    groups: Dict[str, List[FunctionTool]],
) -> None:
    """
    Print categories (groups) as a numbered list for user selection.

    Each *category* gets a unique number so the user can select entire groups.
    Individual tools within each category are shown for reference but are not
    individually selectable.

    Args:
        groups: Category → tools mapping.
    """
    print("\nAvailable tool categories (select by category index):\n")
    for idx, (category, tools) in enumerate(groups.items(), start=1):
        tool_count = len(tools)
        tool_names = ", ".join(t.metadata.name for t in tools)
        print(f"  [{idx}] {category} ({tool_count} tools)")
        print(f"      Tools: {tool_names}")
    print()  # trailing newline


# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------

def select_tools_interactively(
    all_tools: Optional[List[FunctionTool]] = None,
) -> List[FunctionTool]:
    """
    Display available tool categories, prompt the user to select which
    categories to include, and return all tools from the selected categories.

    The flow:
      1. Discover tools (or use provided list).
      2. Group them by category.
      3. Display categories with tool counts.
      4. Prompt for category selection (supports ranges).
      5. Validate & retry on invalid input.
      6. Show summary and return all tools from selected categories.

    Args:
        all_tools: Optional pre-discovered tool list. If None, discovery runs.

    Returns:
        List of FunctionTool instances from the selected categories.
    """
    if all_tools is None:
        all_tools = _discover_tools()

    groups = group_tools_by_category(all_tools)
    category_list = list(groups.keys())  # ordered list of category names
    display_categories_for_selection(groups)

    total_categories = len(category_list)

    while True:
        try:
            raw = input(
                f"Select categories [example: 1,2,5 or 1-3] (1-{total_categories}): "
            ).strip()

            if not raw:
                print("No selection made. Please enter at least one category index.\n")
                continue

            selected_indexes = parse_tool_selection(raw, maximum=total_categories)

            # Guard: empty selection after parsing (shouldn't happen, but just in case)
            if not selected_indexes:
                print("No categories selected. Please try again.\n")
                continue

            break

        except ValueError as exc:
            print(f"  ✗ {exc}\n")
            continue
        except EOFError:
            print("\n  Input stream ended. Aborting selection.")
            return []
        except KeyboardInterrupt:
            print("\n  Interrupted. Aborting selection.")
            return []

    # Build selected tool list from selected categories
    selected_categories = {category_list[i - 1] for i in selected_indexes}
    selected_tools = [
        t for t in all_tools
        if _extract_category(t.metadata.description) in selected_categories
    ]

    # Summary
    print(
        f"\nSelected {len(selected_categories)} categories ({len(selected_tools)} of {len(all_tools)} tools):"
    )
    for cat in selected_categories:
        cat_tools = groups[cat]
        print(f"  ✓ {cat} ({len(cat_tools)} tools)")
    print()

    return selected_tools


# ---------------------------------------------------------------------------
# Programmatic selection by category
# ---------------------------------------------------------------------------

def select_tools_by_category(
    all_tools: Optional[List[FunctionTool]] = None,
    categories: Optional[List[str]] = None,
) -> List[FunctionTool]:
    """
    Return tools whose category is in the given whitelist.

    Useful for future non-interactive mode (e.g. --select-tools).

    Args:
        all_tools: Pre-discovered tool list.
        categories: Category names to include (case-insensitive).

    Returns:
        Filtered list of tools.
    """
    if all_tools is None:
        all_tools = _discover_tools()

    if not categories:
        return []

    lower_cats = {c.lower() for c in categories}
    return [
        t for t in all_tools
        if _extract_category(t.metadata.description).lower() in lower_cats
    ]