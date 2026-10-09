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

import re
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


def _extract_short_description(description: str) -> str:
    """
    Extract the short description from a tool's full description string.

    Tool descriptions follow the pattern:
        "Short description. Category: <CategoryName>"

    Args:
        description: The tool's full description metadata.

    Returns:
        Short description string (before "Category:").
    """
    if "Category:" in description:
        return description.split("Category:")[0].strip().rstrip(".")
    return description.strip().rstrip(".")


# ---------------------------------------------------------------------------
# Description summarisation
# ---------------------------------------------------------------------------

# Canonical action groups and their trigger phrases.
# Each tuple: (pattern_regex, canonical_label)
# Patterns are checked in order; first match wins.
_ACTION_PATTERNS: list = [
    # --- Mathematics ---
    (r"(?i)\badd\s+two\s+numbers",              "arithmetic"),
    (r"(?i)\bsubtract",                          "arithmetic"),
    (r"(?i)\bmultiply",                          "arithmetic"),
    (r"(?i)\bdivide",                            "arithmetic"),
    (r"(?i)\braise.*power",                      "arithmetic"),
    (r"(?i)\bcalculate\s+remainder",             "compute"),
    (r"(?i)\bcalculate\s+square\s+root",         "compute"),
    (r"(?i)\bcalculate\s+sine",                  "trigonometry"),
    (r"(?i)\bcalculate\s+cosine",                "trigonometry"),
    (r"(?i)\bcalculate\s+tangent",               "trigonometry"),
    (r"(?i)\bcalculate\s+natural\s+logarithm",   "logarithms"),
    (r"(?i)\bcalculate\s+base-?10\s+logarithm",  "logarithms"),
    (r"(?i)\bcalculate\s+factorial",             "compute"),
    (r"(?i)\bevaluate.*expression",              "compute"),

    # --- Version Control ---
    (r"(?i)\bget\s+latest\s+commit",            "inspect"),
    (r"(?i)\binitialize.*repo",                  "repository"),
    (r"(?i)\badd\s+files\s+to\s+staging",       "staging"),
    (r"(?i)\badd\s+all.*staging",                "staging"),
    (r"(?i)\badd\s+a\s+remote",                  "remote"),
    (r"(?i)\bcreate\s+a\s+commit",               "commit"),
    (r"(?i)\bget\s+repository\s+status",         "inspect"),
    (r"(?i)\bgenerate\s+changelog",              "changelog"),
    (r"(?i)\bget\s+recent\s+commits",            "inspect"),
    (r"(?i)\bupdate\s+changelog",                "changelog"),
    (r"(?i)\bget\s+user\s+email",                "inspect"),
    (r"(?i)\bpush\s+changes",                    "remote"),
    (r"(?i)\blist\s+configured\s+remotes",       "inspect"),
    (r"(?i)\bset\s+upstream",                    "remote"),
    (r"(?i)\blist\s+all\s+branches",             "inspect"),
    (r"(?i)\bcreate\s+a\s+new\s+branch",         "branching"),
    (r"(?i)\bswitch\s+to\s+a\s+branch",          "branching"),
    (r"(?i)\bdelete\s+a\s+branch",               "cleanup"),
    (r"(?i)\brename.*branch",                    "cleanup"),
    (r"(?i)\bshow\s+file\s+differences",         "inspect"),
    (r"(?i)\bshow\s+staged\s+differences",       "inspect"),
    (r"(?i)\bpull\s+from\s+remote",              "remote"),
    (r"(?i)\bfetch\s+from\s+remote",             "remote"),
    (r"(?i)\bmerge\s+branches",                  "merge"),
    (r"(?i)\brebase\s+commits",                  "merge"),
    (r"(?i)\bcompare\s+branch\s+logs",           "inspect"),
    (r"(?i)\bverify.*auth",                      "inspect"),
    (r"(?i)\bget\s+github\s+user\s+information", "inspect"),
    (r"(?i)\bconfigure.*credentials",            "config"),
    (r"(?i)\bcreate\s+a\s+pull\s+request",       "collaborate"),
    (r"(?i)\blist\s+pull\s+requests",            "inspect"),
    (r"(?i)\bget\s+details.*pull\s+request",     "inspect"),
    (r"(?i)\bupdate.*pull\s+request",            "update"),
    (r"(?i)\bclose.*pull\s+request",             "collaborate"),
    (r"(?i)\bmerge.*pull\s+request",             "merge"),
    (r"(?i)\badd.*comment.*pull\s+request",      "collaborate"),
    (r"(?i)\bget.*file\s+changes.*pull",         "inspect"),
    (r"(?i)\bget.*comments.*pull\s+request",     "inspect"),
    (r"(?i)\bget.*review.*pull\s+request",       "inspect"),

    # --- Operating System ---
    (r"(?i)\bget\s+current\s+working\s+directory", "inspect"),
    (r"(?i)\blist\s+files",                         "inspect"),
    (r"(?i)\bcreate\s+an?\s+empty\s+file",          "create"),
    (r"(?i)\bcheck\s+if.*exists",                   "inspect"),
    (r"(?i)\bcreate\s+a\s+new\s+directory",         "create"),
    (r"(?i)\bremove.*file.*directory",               "delete"),
    (r"(?i)\bcopy.*file.*directory",                 "move/copy"),
    (r"(?i)\bmove.*rename.*file",                    "move/copy"),
    (r"(?i)\bread\s+file\s+contents",                "read/write"),
    (r"(?i)\bwrite\s+content\s+to\s+a\s+file",      "read/write"),
    (r"(?i)\bget\s+system\s+information",            "inspect"),

    # --- Database ---
    (r"(?i)\brun.*sql.*query",           "query"),

    # --- Package Management ---
    (r"(?i)\bfind.*package.*provides",   "discover"),
    (r"(?i)\bcheck.*available",          "inspect"),
    (r"(?i)\binstall.*apt.*package",     "install"),
    (r"(?i)\binstall\s+multiple",        "install"),
    (r"(?i)\bend-to-end",                "install"),
    (r"(?i)\bobtain.*password",          "auth"),
    (r"(?i)\btest.*password",           "auth"),
    (r"(?i)\bclear.*password",          "reset"),
    (r"(?i)\bset.*default.*prompt",     "config"),
    (r"(?i)\bget.*default.*prompt",     "inspect"),

    # --- Infrastructure ---
    (r"(?i)\bstore.*cache",          "cache"),
    (r"(?i)\bretrieve.*cache",       "cache"),
    (r"(?i)\bwipe.*cache",          "reset"),
    (r"(?i)\bview\s+cache\s+status", "inspect"),
    (r"(?i)\bupdate.*cached",        "update"),
    (r"(?i)\brecord.*repository",    "track"),
    (r"(?i)\blog.*error",            "track"),
    (r"(?i)\bstart.*session",        "session"),
    (r"(?i)\bend.*session",          "session"),
    (r"(?i)\bsave.*statistics",      "cache"),
    (r"(?i)\bget\s+summary",         "inspect"),

    # --- Data / Excel ---
    (r"(?i)\bread.*xlsx.*file",        "read/write"),
    (r"(?i)\bwrite.*xlsx.*file",       "read/write"),
    (r"(?i)\blist.*sheet\s+names",     "inspect"),
    (r"(?i)\bget.*value.*cell",        "inspect"),
    (r"(?i)\bset.*value.*cell",        "modify"),
    (r"(?i)\bget.*range\s+dimensions", "inspect"),
    (r"(?i)\bcopy.*sheet",             "move/copy"),
    (r"(?i)\bapply.*style",            "format"),
    (r"(?i)\bcreate.*workbook",        "create"),

    # --- Data / Analysis ---
    (r"(?i)\bload.*excel.*file",        "load"),
    (r"(?i)\bload.*csv.*file",          "load"),
    (r"(?i)\bgenerate.*statistics",     "compute"),
    (r"(?i)\bfilter.*rows",             "filter"),
    (r"(?i)\bgroup.*aggregate",         "aggregate"),
    (r"(?i)\bcreate.*pivot",            "aggregate"),
    (r"(?i)\bdetect.*missing",          "inspect"),
    (r"(?i)\bcompute.*correlation",     "compute"),
    (r"(?i)\bexport.*dictionaries",     "export"),
    (r"(?i)\bget.*unique",              "inspect"),
    (r"(?i)\bsort.*data",              "transform"),
    (r"(?i)\bcompute.*detailed.*statistics", "compute"),
    (r"(?i)\bget.*DataFrame.*information",  "inspect"),

    # --- System ---
    (r"(?i)\bexecute.*shell\s+command",        "execute"),
    (r"(?i)\bexecute\s+multiple.*commands",    "execute"),
    (r"(?i)\bparse.*command.*output",           "parse"),
    (r"(?i)\bget\s+system\s+information.*os",   "inspect"),
    (r"(?i)\bcheck.*file\s+permissions",        "inspect"),
    (r"(?i)\bexecute.*environment\s+variables",  "execute"),
]


def _normalize_action(description: str) -> str:
    """
    Map a tool description to a canonical action label.

    Uses ordered pattern matching against known phrase → category mappings.
    First regex that matches wins. Fallback: lowercase the first word.

    Args:
        description: A tool's short description.

    Returns:
        Canonical action label (e.g. "arithmetic", "remote", "read/write").
    """
    for pattern, label in _ACTION_PATTERNS:
        if re.search(pattern, description):
            return label

    # Fallback: first word lowercased
    return description.strip().split()[0].lower() if description.strip().split() else "misc"


def _cluster_actions(actions: List[str]) -> List[str]:
    """
    Deduplicate a list of canonical action labels while preserving order.

    Args:
        actions: List of normalised action labels.

    Returns:
        Deduplicated list of unique action labels.
    """
    seen: set = set()
    unique: list = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique


def _build_category_description(tools: List[FunctionTool]) -> str:
    """
    Build a comprehensive yet concise description that covers **all**
    tool actions within a category.

    Strategy:
      1. Extract the leading verb phrase from every tool description.
      2. Normalise each verb via pattern matching to canonical action groups.
      3. Deduplicate the canonical labels.
      4. Join them into a comma‑separated summary:
         "Actions: <action1>, <action2>, …"

    Args:
        tools: List of FunctionTool instances in this category.

    Returns:
        A one‑line description summarising the category's capabilities.
    """
    if not tools:
        return "No tools available"

    normalised = [
        _normalize_action(_extract_short_description(t.metadata.description))
        for t in tools
    ]

    unique = _cluster_actions(normalised)
    return f"Actions: {', '.join(unique)}"


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

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
    Only the category name, tool count, and a concise capability summary are
    shown — individual tool names are **not** displayed to keep the menu clean.

    Args:
        groups: Category → tools mapping.
    """
    print("\nAvailable tool categories (select by category index):\n")
    for idx, (category, tools) in enumerate(groups.items(), start=1):
        tool_count = len(tools)
        short_desc = _build_category_description(tools)
        print(f"  [{idx}] {category} ({tool_count} tools)")
        print(f"      {short_desc}")
    print()


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
    category_list = list(groups.keys())
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

    selected_categories = {category_list[i - 1] for i in selected_indexes}
    selected_tools = [
        t for t in all_tools
        if _extract_category(t.metadata.description) in selected_categories
    ]

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