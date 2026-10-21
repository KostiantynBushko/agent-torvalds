"""
Central Registry of Interactive Slash Commands.

Every interactive command supported by the Torvalds agent is declared here
exactly once, together with a short human-readable description.  Both
orchestrators — the classic ``agent-torvalds.py`` REPL and the multi-window
``agent-torvalds-mw.py`` TUI — render their ``\\help`` output from this
registry, so the help screen can never drift away from the real behaviour.

The registry is pure data: it never executes anything.  Dispatch stays in the
orchestrators, the registry only describes *what exists* and *where it comes
from*, which keeps the help output honest per runtime mode.

Feature flags allow the same registry to describe several modes:

  - ``hitl``           — Human-in-the-Loop runtime commands
  - ``chat_history``   — Chat History Manager commands
  - ``project_manager``— Project / workspace commands
  - ``tui``            — Commands that only exist inside the multi-window TUI

Category: Infrastructure
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

FEATURE_HITL = "hitl"
FEATURE_CHAT_HISTORY = "chat_history"
FEATURE_PROJECT_MANAGER = "project_manager"
FEATURE_MIKROTIK = "mikrotik"
FEATURE_TUI = "tui"


# ---------------------------------------------------------------------------
# Command specification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandSpec:
    """
    Description of a single interactive command.

    Attributes:
        name: Canonical command name, including the leading backslash.
        description: One-line, human-readable explanation.
        usage: The exact text the user types (may include an argument).
        category: Group the command belongs to.
        aliases: Alternative names for the same command.
        feature: Feature flag required for the command to be available.
    """

    name: str
    description: str
    usage: str = ""
    category: str = "General"
    aliases: Tuple[str, ...] = ()
    feature: str = ""

    @property
    def display(self) -> str:
        """Command name including its aliases, e.g. ``\\exit, \\quit``."""
        if self.aliases:
            return ", ".join((self.name,) + self.aliases)
        return self.name


@dataclass(frozen=True)
class HelpOptions:
    """
    Controls which command groups are visible in the help output.

    Attributes:
        hitl: Show the Human-in-the-Loop commands.
        chat_history: Show the Chat History Manager commands.
        project_manager: Show the Project / workspace commands.
        mikrotik: Show the MikroTik RouterOS commands.
        tui: Show commands that only exist inside the multi-window TUI.
        keyboard_shortcuts: Show the TUI keyboard navigation cheat sheet.
    """

    hitl: bool = True
    chat_history: bool = True
    project_manager: bool = True
    mikrotik: bool = True
    tui: bool = False
    keyboard_shortcuts: bool = False

    def allows(self, feature: str) -> bool:
        """
        Check whether a feature flag is enabled.

        Args:
            feature: Feature flag name (empty string means "always allowed").

        Returns:
            True when the feature is enabled.
        """
        if not feature:
            return True
        return bool(getattr(self, feature, True))


# ---------------------------------------------------------------------------
# The command table
# ---------------------------------------------------------------------------

COMMAND_SPECS: Tuple[CommandSpec, ...] = (
    # ---- General --------------------------------------------------------
    CommandSpec(
        name="\\help",
        description="Show this help message with every available command.",
        usage="\\help",
        category="General",
    ),
    CommandSpec(
        name="\\clear",
        description="Clear the current document viewer pane.",
        usage="\\clear",
        category="General",
        feature=FEATURE_TUI,
    ),
    CommandSpec(
        name="\\exit",
        description="Exit the Torvalds agent session.",
        usage="\\exit",
        category="General",
        aliases=("\\quit",),
    ),

    # ---- Statistics & diagnostics --------------------------------------
    CommandSpec(
        name="\\stats",
        description="View the request statistics summary (tokens, calls, errors).",
        usage="\\stats",
        category="Statistics",
    ),

    # ---- Human-in-the-Loop ---------------------------------------------
    CommandSpec(
        name="\\toggle-hitl",
        description="Toggle Human-in-the-Loop confirmations on or off.",
        usage="\\toggle-hitl",
        category="HITL",
        feature=FEATURE_HITL,
    ),
    CommandSpec(
        name="\\hitl-on",
        description="Enable Human-in-the-Loop confirmations.",
        usage="\\hitl-on",
        category="HITL",
        feature=FEATURE_HITL,
    ),
    CommandSpec(
        name="\\hitl-off",
        description="Disable Human-in-the-Loop confirmations.",
        usage="\\hitl-off",
        category="HITL",
        feature=FEATURE_HITL,
    ),
    CommandSpec(
        name="\\hitl-status",
        description="Show HITL configuration, question counts and timeouts.",
        usage="\\hitl-status",
        category="HITL",
        feature=FEATURE_HITL,
    ),
    CommandSpec(
        name="\\hitl-help",
        description="Show the Human-in-the-Loop command cheat sheet.",
        usage="\\hitl-help",
        category="HITL",
        feature=FEATURE_HITL,
    ),

    # ---- Tool selection -------------------------------------------------
    CommandSpec(
        name="\\tools",
        description="Open the interactive tool category selection menu.",
        usage="\\tools",
        category="Tools",
        feature=FEATURE_TUI,
    ),
    CommandSpec(
        name="\\tool-list",
        description="List every available tool with its description.",
        usage="\\tool-list",
        category="Tools",
        feature=FEATURE_TUI,
    ),
    CommandSpec(
        name="\\tool-select",
        description="Select tool categories non-interactively (e.g. 1-3,7).",
        usage="\\tool-select <spec>",
        category="Tools",
        feature=FEATURE_TUI,
    ),

    # ---- Project management ---------------------------------------------
    CommandSpec(
        name="\\projects",
        description="List the projects registered in the workspace.",
        usage="\\projects",
        category="Projects",
        aliases=("\\project-list",),
        feature=FEATURE_PROJECT_MANAGER,
    ),
    CommandSpec(
        name="\\project-info",
        description="Show details for a registered project.",
        usage="\\project-info <name>",
        category="Projects",
        feature=FEATURE_PROJECT_MANAGER,
    ),
    CommandSpec(
        name="\\project-status",
        description="Show the git status of the active project.",
        usage="\\project-status",
        category="Projects",
        feature=FEATURE_PROJECT_MANAGER,
    ),
    CommandSpec(
        name="\\project-summary",
        description="Show a full workspace summary.",
        usage="\\project-summary",
        category="Projects",
        feature=FEATURE_PROJECT_MANAGER,
    ),

    # ---- MikroTik RouterOS ----------------------------------------------
    CommandSpec(
        name="\\routers",
        description="List the configured MikroTik routers and their status.",
        usage="\\routers",
        category="Network",
        feature=FEATURE_MIKROTIK,
    ),
    CommandSpec(
        name="\\router-health",
        description="Show the health of a MikroTik router (CPU, memory, disk).",
        usage="\\router-health <target>",
        category="Network",
        feature=FEATURE_MIKROTIK,
    ),
    CommandSpec(
        name="\\router-interfaces",
        description="List the network interfaces of a MikroTik router.",
        usage="\\router-interfaces <target>",
        category="Network",
        feature=FEATURE_MIKROTIK,
    ),
    CommandSpec(
        name="\\router-backup",
        description="Export the configuration of a MikroTik router.",
        usage="\\router-backup <target>",
        category="Network",
        feature=FEATURE_MIKROTIK,
    ),

    # ---- Chat history ----------------------------------------------------
    CommandSpec(
        name="\\chat-sessions",
        description="List all chat sessions for the current user.",
        usage="\\chat-sessions",
        category="Chat",
        aliases=("\\chat-list",),
        feature=FEATURE_CHAT_HISTORY,
    ),
    CommandSpec(
        name="\\chat-select",
        description="Switch the active chat session.",
        usage="\\chat-select <id>",
        category="Chat",
        feature=FEATURE_CHAT_HISTORY,
    ),
    CommandSpec(
        name="\\chat-create",
        description="Create a new chat session.",
        usage="\\chat-create <name> [type]",
        category="Chat",
        feature=FEATURE_CHAT_HISTORY,
    ),
    CommandSpec(
        name="\\chat-delete",
        description="Delete a chat session.",
        usage="\\chat-delete <id>",
        category="Chat",
        feature=FEATURE_CHAT_HISTORY,
    ),
    CommandSpec(
        name="\\chat-rename",
        description="Rename a chat session.",
        usage="\\chat-rename <id> <new name>",
        category="Chat",
        feature=FEATURE_CHAT_HISTORY,
    ),
    CommandSpec(
        name="\\chat-info",
        description="Show details of the active chat session.",
        usage="\\chat-info",
        category="Chat",
        feature=FEATURE_CHAT_HISTORY,
    ),
    CommandSpec(
        name="\\chat-clear",
        description="Clear the active session message history.",
        usage="\\chat-clear",
        category="Chat",
        feature=FEATURE_CHAT_HISTORY,
    ),
)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORY_ORDER: Tuple[str, ...] = (
    "General",
    "Statistics",
    "HITL",
    "Tools",
    "Projects",
    "Network",
    "Chat",
)

CATEGORY_TITLES = {
    "General": "General",
    "Statistics": "Statistics & Diagnostics",
    "HITL": "Human-in-the-Loop (HITL)",
    "Tools": "Tool Selection",
    "Projects": "Project Management",
    "Network": "Network Devices (MikroTik RouterOS)",
    "Chat": "Chat History",
}


# ---------------------------------------------------------------------------
# TUI keyboard navigation cheat sheet
# ---------------------------------------------------------------------------

KEYBOARD_SHORTCUTS: Tuple[Tuple[str, str], ...] = (
    ("Enter", "Submit prompt / confirm HITL answer"),
    ("PgUp / PgDn", "Scroll document viewer up and down"),
    ("Up / Down", "Browse previous input command history"),
    ("Left / Right", "Move cursor horizontally in the input bar"),
    ("Home / End", "Jump to start / end of the input line"),
    ("Ctrl+C", "Cancel current input or exit if the buffer is empty"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HELP_COMMAND = "\\help"


def is_help_command(cmd: str) -> bool:
    """
    Check whether a command string is the help command.

    Args:
        cmd: The command string to check.

    Returns:
        True when the command is ``\\help`` (case-insensitive).
    """
    return (cmd or "").strip().lower() == HELP_COMMAND


def _usage_label(spec: CommandSpec) -> str:
    """
    Build the label shown in the help output for a command.

    Args:
        spec: The command specification.

    Returns:
        str: Usage text, with aliases appended when present.
    """
    usage = spec.usage or spec.name
    if not spec.aliases:
        return usage
    if len(spec.aliases) == 1:
        return f"{usage} or {spec.aliases[0]}"
    return f"{usage} or " + ", ".join(spec.aliases)


def iter_sections(
    options: Optional[HelpOptions] = None,
) -> Iterator[Tuple[str, List[CommandSpec]]]:
    """
    Iterate over the visible command sections.

    Args:
        options: Feature flags controlling visibility.

    Yields:
        Tuples of (section title, list of command specifications).
    """
    opts = options or HelpOptions()

    for category in CATEGORY_ORDER:
        specs = [
            spec
            for spec in COMMAND_SPECS
            if spec.category == category and opts.allows(spec.feature)
        ]
        if specs:
            yield CATEGORY_TITLES.get(category, category), specs


def get_command_specs(
    options: Optional[HelpOptions] = None,
) -> List[CommandSpec]:
    """
    Return every visible command specification.

    Args:
        options: Feature flags controlling visibility.

    Returns:
        Flat list of command specifications.
    """
    opts = options or HelpOptions()
    return [spec for spec in COMMAND_SPECS if opts.allows(spec.feature)]


def find_command(
    name: str,
    options: Optional[HelpOptions] = None,
) -> Optional[CommandSpec]:
    """
    Look up a command specification by name or alias.

    Args:
        name: Command name, with or without the leading backslash.
        options: Feature flags controlling visibility.

    Returns:
        The matching specification, or None when the command is unknown
        or not available in the current mode.
    """
    needle = (name or "").strip().lower()
    if not needle:
        return None

    if not needle.startswith("\\"):
        needle = "\\" + needle

    for spec in get_command_specs(options):
        candidates = (spec.name,) + spec.aliases
        if needle in tuple(c.lower() for c in candidates):
            return spec

    return None


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def build_help_markdown(options: Optional[HelpOptions] = None) -> str:
    """
    Render the help screen as Markdown.

    The Markdown flavour is used by the multi-window TUI, which displays the
    result inside its document pane.

    Args:
        options: Feature flags controlling visibility.

    Returns:
        str: Markdown document describing every available command.
    """
    opts = options or HelpOptions()

    lines: List[str] = [
        "# Torvalds AI Agent — Help & Commands",
        "",
        "Every interactive command available in this session:",
        "",
    ]

    for title, specs in iter_sections(opts):
        lines.append(f"### {title}")
        lines.append("")
        for spec in specs:
            lines.append(f"- `{_usage_label(spec)}` : {spec.description}")
        lines.append("")

    if opts.keyboard_shortcuts:
        lines.append("### Keyboard Navigation")
        lines.append("")
        for key, description in KEYBOARD_SHORTCUTS:
            lines.append(f"- **{key}** : {description}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_help_text(options: Optional[HelpOptions] = None) -> str:
    """
    Render the help screen as plain text.

    The plain-text flavour is used by the classic REPL, where a copy-paste
    friendly layout is more useful than Markdown tables.

    Args:
        options: Feature flags controlling visibility.

    Returns:
        str: Plain-text help screen describing every available command.
    """
    opts = options or HelpOptions()

    lines: List[str] = [
        "Torvalds AI Agent — Help & Commands",
        "========================================",
        "",
    ]

    for title, specs in iter_sections(opts):
        lines.append(title.upper())
        labels = [_usage_label(spec) for spec in specs]
        width = max(len(label) for label in labels)
        for label, spec in zip(labels, specs):
            lines.append(f"  {label.ljust(width)}  {spec.description}")
        lines.append("")

    if opts.keyboard_shortcuts:
        lines.append("KEYBOARD NAVIGATION")
        width = max(len(key) for key, _ in KEYBOARD_SHORTCUTS)
        for key, description in KEYBOARD_SHORTCUTS:
            lines.append(f"  {key.ljust(width)}  {description}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "CommandSpec",
    "HelpOptions",
    "HELP_COMMAND",
    "FEATURE_HITL",
    "FEATURE_CHAT_HISTORY",
    "FEATURE_PROJECT_MANAGER",
    "FEATURE_MIKROTIK",
    "FEATURE_TUI",
    "COMMAND_SPECS",
    "CATEGORY_ORDER",
    "CATEGORY_TITLES",
    "KEYBOARD_SHORTCUTS",
    "is_help_command",
    "iter_sections",
    "get_command_specs",
    "find_command",
    "build_help_markdown",
    "build_help_text",
]
