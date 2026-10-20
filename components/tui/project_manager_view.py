"""
Project Manager View for Torvalds Multi-Window Console.

Renders project/workspace information as Markdown so the multi-window agent
can expose the same project management features as the classic orchestrator
(``agent-torvalds.py``):
  - ``\\projects`` — list registered projects in the workspace
  - ``\\project-info <name>`` — show details of a single project
  - ``\\project-status`` — show the git status of the active project
  - ``\\project-summary`` — show a full workspace summary

The underlying work is delegated to the ``project_manager`` package so the
behaviour matches the classic orchestrator exactly.

Category: Project Management
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

PROJECT_COMMANDS = {
    "\\projects": "list",
    "\\project-list": "list",
    "\\project-info": "info",
    "\\project-status": "status",
    "\\project-summary": "summary",
}

PROJECT_COMMAND_PREFIXES = tuple(f"{cmd} " for cmd in PROJECT_COMMANDS)


def is_project_command(cmd: str) -> bool:
    """
    Check whether a command string targets the project manager.

    Args:
        cmd: The command string to check.

    Returns:
        True if the command is a project management command.
    """
    cmd_lower = (cmd or "").strip().lower()
    if not cmd_lower:
        return False
    return cmd_lower in PROJECT_COMMANDS or cmd_lower.startswith(PROJECT_COMMAND_PREFIXES)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _load_json(payload: str) -> Dict[str, Any]:
    """
    Parse a JSON payload returned by the project manager toolkit.

    Args:
        payload: Raw JSON string.

    Returns:
        Parsed dictionary, or an empty dict when parsing fails.
    """
    try:
        data = json.loads(payload)
        return data if isinstance(data, dict) else {"result": data}
    except Exception as exc:
        logger.warning("Could not parse project manager payload: %s", exc)
        return {"error": str(exc)}


def _has_error(data: Dict[str, Any]) -> bool:
    """
    Check whether a parsed payload carries a real error.

    The project manager toolkit always includes an ``error`` key, but sets it
    to ``None`` when the operation succeeded, so a plain ``"error" in data``
    check would report false failures.

    Args:
        data: Parsed payload dictionary.

    Returns:
        True when the payload contains a non-empty error message.
    """
    return bool(data.get("error"))


def _escape(value: Any) -> str:
    """
    Escape a value so it can be embedded in a Markdown table cell.

    Args:
        value: Arbitrary value.

    Returns:
        str: Escaped, single-line string.
    """
    return str(value).replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_projects_markdown() -> str:
    """
    Render the list of registered projects in the workspace.

    Returns:
        str: Markdown document listing the projects.
    """
    from project_manager.agent_project_manager_toolkit import list_projects

    data = _load_json(list_projects("."))

    if _has_error(data):
        return f"# 📁 Projects\n\n**Error:** {data['error']}"

    projects = data.get("projects", []) or []
    workspace = data.get("workspace_path", ".")

    lines = [
        "# 📁 Registered Projects",
        "",
        f"**Workspace:** `{workspace}`  •  **Count:** {data.get('count', len(projects))}",
        "",
    ]

    if not projects:
        lines.append("No projects registered yet.")
        lines.append("")
        lines.append("Use `--auto-scan` at startup or `\\project-summary` for details.")
        return "\n".join(lines)

    lines.extend([
        "| Project | Type | Confidence | Git | Actions |",
        "| :--- | :--- | ---: | :---: | :---: |",
    ])

    for project in projects:
        lines.append(
            f"| {project.get('name', 'unknown')} "
            f"| {project.get('type', 'Unknown')} "
            f"| {project.get('confidence', 0):.2f} "
            f"| {'✅' if project.get('git_repo') else '—'} "
            f"| {'✅' if project.get('has_actions') else '—'} |"
        )

    lines.extend([
        "",
        "Inspect one project with `\\project-info <name>`.",
    ])

    return "\n".join(lines)


def render_project_info_markdown(project_name: str) -> str:
    """
    Render detailed information about a single project.

    Args:
        project_name: Name of the project to inspect.

    Returns:
        str: Markdown document describing the project.
    """
    from project_manager.agent_project_manager_toolkit import get_project_details

    data = _load_json(get_project_details(project_name, "."))

    if _has_error(data):
        available = data.get("available_projects") or []
        lines = [f"# 📁 Project: {project_name}", "", f"**Error:** {data['error']}"]
        if available:
            lines.extend(["", "**Available projects:**", ""])
            lines.extend(f"- `{name}`" for name in available)
        return "\n".join(lines)

    metadata = data.get("metadata", {}) or {}

    lines = [
        f"# 📁 Project: {data.get('name', project_name)}",
        "",
        "| Field | Value |",
        "| :--- | :--- |",
        f"| Type | {data.get('type', 'Unknown')} |",
        f"| Confidence | {data.get('confidence', 0):.2f} |",
        f"| Path | `{data.get('path', 'N/A')}` |",
        f"| Git Repository | {'Yes' if data.get('git_repo') else 'No'} |",
        f"| Git Branch | {data.get('git_branch', 'N/A')} |",
        f"| Description | {_escape(metadata.get('description', 'N/A'))} |",
        f"| Framework | {_escape(metadata.get('framework', 'N/A'))} |",
        f"| Language Version | {_escape(metadata.get('language_version', 'N/A'))} |",
    ]

    actions = data.get("actions") or {}
    if actions:
        lines.extend([
            "",
            "### Configured Actions",
            "",
            "| Action | Command |",
            "| :--- | :--- |",
        ])
        for action, command in actions.items():
            lines.append(f"| {action} | `{_escape(command)}` |")

    return "\n".join(lines)


def render_project_status_markdown() -> str:
    """
    Render the git status of the currently active project.

    The ``check_git_status`` tool returns a nested ``files`` list where each
    entry carries its own ``status``/``staged``/``modified``/``untracked``
    flags, so the file lists are derived from that structure.

    Returns:
        str: Markdown document describing the working tree state.
    """
    from project_manager.agent_project_manager_toolkit import check_git_status

    data = _load_json(check_git_status("."))

    if _has_error(data):
        return f"# 📁 Git Status\n\n**Error:** {data['error']}"

    if not data.get("is_git_repo", False):
        return (
            "# 📁 Git Status\n\n"
            f"`{data.get('path', '.')}` is not a Git repository."
        )

    lines = [
        "# 📁 Git Status",
        "",
        f"**Path:** `{data.get('path', '.')}`  •  "
        f"**Branch:** `{data.get('branch', 'N/A')}`  •  "
        f"**Commit:** `{data.get('commit_hash', 'N/A')}`",
        "",
        "| State | Flag |",
        "| :--- | :---: |",
        f"| Uncommitted changes | {'✅' if data.get('has_uncommitted') else '—'} |",
        f"| Staged changes | {'✅' if data.get('has_staged') else '—'} |",
        f"| Untracked files | {'✅' if data.get('has_untracked') else '—'} |",
        f"| Modified files | {'✅' if data.get('has_modified') else '—'} |",
        f"| Uncommitted count | {data.get('uncommitted_count', 0)} |",
    ]

    # Group the per-file entries by their status flags.
    groups = {
        "Modified": [],
        "Staged": [],
        "Untracked": [],
        "Deleted": [],
        "Renamed": [],
    }

    for file_entry in data.get("files") or []:
        path = file_entry.get("path", "N/A")
        if file_entry.get("deleted"):
            groups["Deleted"].append(path)
        elif file_entry.get("renamed"):
            groups["Renamed"].append(path)
        elif file_entry.get("untracked"):
            groups["Untracked"].append(path)
        elif file_entry.get("staged"):
            groups["Staged"].append(path)
        elif file_entry.get("modified"):
            groups["Modified"].append(path)

    for title, paths in groups.items():
        if not paths:
            continue
        lines.extend(["", f"### {title} ({len(paths)})", ""])
        lines.extend(f"- `{_escape(p)}`" for p in paths)

    return "\n".join(lines)


def render_project_summary_markdown() -> str:
    """
    Render a comprehensive workspace summary.

    Returns:
        str: Markdown document summarizing the workspace.
    """
    from project_manager.agent_project_manager_toolkit import get_workspace_summary

    data = _load_json(get_workspace_summary("."))

    if _has_error(data):
        return f"# 📁 Workspace Summary\n\n**Error:** {data['error']}"

    lines = [
        "# 📁 Workspace Summary",
        "",
        f"**Workspace:** `{data.get('workspace_path', '.')}`",
        f"**Total projects:** {data.get('total_projects', 0)}",
        "",
    ]

    types = data.get("project_types") or {}
    if types:
        lines.extend(["### Projects by Type", ""])
        for project_type, names in types.items():
            lines.append(f"- **{project_type}** ({len(names)}): {', '.join(names)}")

    projects = data.get("projects") or []
    if projects:
        lines.extend(["", "### Registered Projects", ""])
        for project in projects:
            lines.append(
                f"- **{project.get('name', 'unknown')}** "
                f"({project.get('type', 'Unknown')})"
                f"{' [git]' if project.get('git_repo') else ''}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

def handle_project_command_markdown(cmd: str) -> Optional[str]:
    """
    Execute a project management command and return a Markdown rendering.

    Args:
        cmd: The project command to execute.

    Returns:
        str: Markdown document with the result, or None if the command was
        not a project management command.
    """
    if not is_project_command(cmd):
        return None

    cmd_lower = cmd.strip().lower()

    try:
        if cmd_lower in ("\\projects", "\\project-list"):
            return render_projects_markdown()

        if cmd_lower == "\\project-info":
            return (
                "# 📁 Project Info\n\n"
                "**Usage:** `\\project-info <project_name>`"
            )

        if cmd_lower.startswith("\\project-info "):
            project_name = cmd.strip().split(maxsplit=1)[1].strip()
            if not project_name:
                return "# 📁 Project Info\n\n**Usage:** `\\project-info <project_name>`"
            return render_project_info_markdown(project_name)

        if cmd_lower == "\\project-status":
            return render_project_status_markdown()

        if cmd_lower == "\\project-summary":
            return render_project_summary_markdown()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Project command failed: %s", exc)
        return f"# 📁 Project Command\n\n**Error:** {exc}"

    return None


__all__ = [
    "PROJECT_COMMANDS",
    "is_project_command",
    "render_projects_markdown",
    "render_project_info_markdown",
    "render_project_status_markdown",
    "render_project_summary_markdown",
    "handle_project_command_markdown",
]
