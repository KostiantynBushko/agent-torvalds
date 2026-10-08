"""
Project Manager Toolkit - Project type detection and workspace management.

This module provides project recognition, workspace configuration,
project lifecycle management, and Human-in-the-Loop (HITL) resolution
for ambiguous project type detections as LlamaIndex FunctionTools.

Integrates with the project_manager package (ProjectScanner, WorkspaceConfig,
ProjectManager) and existing HITL infrastructure to provide a unified
interface for discovering, registering, and managing projects in a workspace.

Category: Project Management
Retriever Keywords: project, workspace, detect, scan, configure, register, manage, agentworkspace, hitl
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from llama_index.core.tools import FunctionTool

from project_manager import ProjectManager, ProjectScanner, WorkspaceConfig

logger = logging.getLogger(__name__)

# =============================================================================
# Helper Functions
# =============================================================================


def _resolve_path(path: str) -> str:
    """
    Resolve a path string to an absolute path.

    Handles relative paths, '.' for current directory, and environment variables.

    Args:
        path: Path string to resolve

    Returns:
        Resolved absolute path string
    """
    if not path or path == ".":
        return str(Path.cwd())
    return str(Path(path).resolve())


def _safe_json_dumps(data: Any, default: str = "N/A") -> str:
    """
    Safely serialize data to JSON string.

    Args:
        data: Data to serialize
        default: Default string for None values

    Returns:
        JSON string representation
    """
    if data is None:
        return default
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _check_ambiguity(candidates: List[tuple]) -> bool:
    """
    Check if project type detection is ambiguous.

    Ambiguity is defined as having multiple candidates where the top 2
    have a confidence gap less than 0.15.

    Args:
        candidates: List of (project_type, confidence) tuples sorted by confidence

    Returns:
        True if detection is ambiguous
    """
    if len(candidates) <= 1:
        return False

    gap = candidates[0][1] - candidates[1][1]
    return gap < 0.15


def _get_hitl_timeout() -> int:
    """Get HITL timeout from environment."""
    try:
        return int(os.environ.get("TORVALDS_HITL_TIMEOUT", "30"))
    except (ValueError, TypeError):
        return 30


# =============================================================================
# Tier 1: Project Detection
# =============================================================================


def scan_directory(path: str = ".") -> str:
    """
    Scan a directory to detect project types with confidence scores.

    Use this tool to identify what kind of project exists in a directory.
    Returns confidence scores for all detected project types.

    Args:
        path (str): Directory path to scan (default: current directory)

    Returns:
        str: JSON string with detected project types and confidence scores

    Example:
        >>> scan_directory("/home/user/my-python-project")
        '{\\n  "path": "/home/user/my-python-project",\\n  "scores": {"Python": 0.95},\\n  ...\\n}'

    Keywords: scan, detect, project type, identify, confidence
    """
    logger.info(f"scan_directory called with path: {path}")
    try:
        resolved_path = _resolve_path(path)

        if not os.path.isdir(resolved_path):
            return json.dumps({"error": f"Path is not a directory: {resolved_path}"}, indent=2)

        scanner = ProjectScanner()
        scores = scanner.scan_directory(resolved_path)
        candidates = scanner.get_candidates(resolved_path)
        detected_type = scanner.detect_project_type(resolved_path)
        is_ambiguous = _check_ambiguity(candidates)

        result = {
            "path": resolved_path,
            "scores": scores,
            "candidates": [{"type": t, "confidence": c} for t, c in candidates],
            "detected_type": detected_type,
            "ambiguous": is_ambiguous,
            "supported_types": scanner.get_supported_types(),
        }

        return _safe_json_dumps(result)
    except Exception as e:
        logger.error(f"scan_directory failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def get_project_indicators(project_type: str) -> str:
    """
    Get the indicator files used to detect a specific project type.

    Use this tool to understand what files/signals the scanner looks for
    when identifying a particular project type.

    Args:
        project_type (str): The project type to get indicators for
                            (e.g., 'Python', 'Node.js', 'Rust', 'Go')

    Returns:
        str: JSON string with indicator definitions and weights

    Example:
        >>> get_project_indicators("Python")
        '{\\n  "type": "Python",\\n  "indicators": [["pyproject.toml", 0.9], ...]\\n}'

    Keywords: indicators, detection, signals, files, weights
    """
    logger.info(f"get_project_indicators called with project_type: {project_type}")
    try:
        scanner = ProjectScanner()
        indicators = scanner.get_project_indicators(project_type)

        if not indicators:
            supported = scanner.get_supported_types()
            return json.dumps({
                "type": project_type,
                "found": False,
                "message": f"Unknown project type '{project_type}'",
                "supported_types": supported,
            }, indent=2)

        result = {
            "type": project_type,
            "found": True,
            "indicators": [{"file": ind, "weight": w} for ind, w in indicators],
        }

        return _safe_json_dumps(result)
    except Exception as e:
        logger.error(f"get_project_indicators failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Tier 2: Workspace Configuration
# =============================================================================


def get_workspace_config(path: str = ".") -> str:
    """
    Load and return the workspace configuration.

    Use this tool to inspect the current workspace state, including
    registered projects, their types, and configuration.

    Args:
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with workspace configuration

    Example:
        >>> get_workspace_config("/home/user/workspace")
        '{\\n  "version": "1.0",\\n  "projects": [...],\\n  ...\\n}'

    Keywords: config, workspace config, agentworkspace, settings, state
    """
    logger.info(f"get_workspace_config called with path: {path}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        return _safe_json_dumps(config.get_config())
    except Exception as e:
        logger.error(f"get_workspace_config failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def list_projects(path: str = ".") -> str:
    """
    List all registered projects in the workspace.

    Use this tool to see what projects have been discovered and registered
    in the workspace configuration.

    Args:
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with list of registered projects

    Example:
        >>> list_projects("/home/user/workspace")
        '{\\n  "projects": [...],\\n  "count": 3\\n}'

    Keywords: list, projects, registered, workspace contents
    """
    logger.info(f"list_projects called with path: {path}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        projects = config.get_all_projects()

        result = {
            "workspace_path": resolved_path,
            "count": len(projects),
            "projects": [
                {
                    "name": p["name"],
                    "type": p["type"],
                    "confidence": p["confidence"],
                    "git_repo": p["git_repo"],
                    "has_actions": bool(p.get("actions")),
                }
                for p in projects
            ],
        }

        return _safe_json_dumps(result)
    except Exception as e:
        logger.error(f"list_projects failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def get_project_details(project_name: str, path: str = ".") -> str:
    """
    Get detailed information about a specific registered project.

    Use this tool to inspect the full metadata of a registered project
    including type, confidence, indicators, actions, and git status.

    Args:
        project_name (str): Name of the project to look up
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with project details or error message

    Example:
        >>> get_project_details("my-python-project")
        '{\\n  "name": "my-python-project",\\n  "type": "Python",\\n  ...\\n}'

    Keywords: details, project info, metadata, inspect
    """
    logger.info(f"get_project_details called with project_name: {project_name}, path: {path}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        project = config.get_project(project_name)

        if not project:
            all_projects = config.get_all_projects()
            return json.dumps({
                "error": f"Project '{project_name}' not found",
                "available_projects": [p["name"] for p in all_projects],
            }, indent=2)

        return _safe_json_dumps(project)
    except Exception as e:
        logger.error(f"get_project_details failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Tier 3: Project Registration and Management
# =============================================================================


def register_project(
    path: str,
    name: Optional[str] = None,
    force: bool = False,
    ask_on_ambiguous: bool = True,
    description: str = "",
    framework: str = "",
    language_version: str = "",
    workspace_path: str = ".",
) -> str:
    """
    Scan a directory, detect its project type, and register it in the workspace.

    Use this tool to discover and register a new project in the workspace.
    Automatically detects the project type and stores metadata in .agentworkspace.json.

    When detection is ambiguous (multiple types with similar confidence),
    the HITL system will prompt the user to choose the correct type.

    Args:
        path (str): Directory path of the project to register
        name (str, optional): Project name (default: derived from directory name)
        force (bool): If True, register even if detection is ambiguous (default: False)
        ask_on_ambiguous (bool): If True, prompt user when detection is ambiguous (default: True)
        description (str): Optional project description
        framework (str): Framework name (e.g., FastAPI, React)
        language_version (str): Language version string (e.g., 3.11, 18)
        workspace_path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with registration results

    Example:
        >>> register_project("/home/user/my-project", workspace_path="/home/user")
        '{\\n  "status": "registered",\\n  "project": {...}\\n}'

    Keywords: register, discover, add project, detect and register, new project
    """
    logger.info(f"register_project called with path: {path}, name: {name}, force: {force}")
    try:
        resolved_path = _resolve_path(path)
        resolved_workspace = _resolve_path(workspace_path)

        if not os.path.isdir(resolved_path):
            return json.dumps({"error": f"Path is not a directory: {resolved_path}"}, indent=2)

        scanner = ProjectScanner()
        candidates = scanner.get_candidates(resolved_path)
        detected_type = scanner.detect_project_type(resolved_path)

        # Check for ambiguity and optionally ask user
        resolution_method = "auto"
        if detected_type is None and candidates:
            is_ambiguous = _check_ambiguity(candidates)
            if is_ambiguous and ask_on_ambiguous and not force:
                # Trigger HITL resolution
                resolution_result = _resolve_ambiguity_sync(candidates, resolved_path)
                detected_type = resolution_result.get("project_type", candidates[0][0])
                resolution_method = resolution_result.get("method", "human")
            elif not force:
                return json.dumps({
                    "status": "failed",
                    "message": f"Could not detect project type for {resolved_path}. "
                               f"Use force=True to register anyway.",
                    "path": resolved_path,
                    "candidates": [{"type": t, "confidence": c} for t, c in candidates],
                }, indent=2)
            else:
                detected_type = candidates[0][0]

        manager = ProjectManager(workspace_path=resolved_workspace)
        project = manager.discover_and_register(
            path=resolved_path,
            name=name,
            force=force,
            description=description,
            framework=framework,
            language_version=language_version,
        )

        if project is None:
            return json.dumps({
                "status": "failed",
                "message": f"Could not detect project type for {resolved_path}.",
                "path": resolved_path,
            }, indent=2)

        result = {
            "status": "registered",
            "project": {
                "name": project["name"],
                "type": project["type"],
                "confidence": project["confidence"],
                "git_repo": project["git_repo"],
                "indicators_found": project["indicators_found"],
            },
            "resolution_method": resolution_method,
        }

        return _safe_json_dumps(result)
    except ValueError as e:
        return json.dumps({"status": "exists", "message": str(e)}, indent=2)
    except Exception as e:
        logger.error(f"register_project failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def update_project(
    project_name: str,
    **kwargs,
) -> str:
    """
    Update metadata for a registered project.

    Use this tool to modify project properties like type, confidence, or metadata.

    Args:
        project_name (str): Name of the project to update
        **kwargs: Fields to update (type, confidence, metadata, etc.)

    Returns:
        str: JSON string with updated project data

    Example:
        >>> update_project("my-project", type="Python", confidence=0.95)
        '{\\n  "status": "updated",\\n  "project": {...}\\n}'

    Keywords: update, modify, change, edit project
    """
    logger.info(f"update_project called with project_name: {project_name}, kwargs: {kwargs}")
    try:
        manager = ProjectManager()
        project = manager.update_project(project_name, **kwargs)

        result = {
            "status": "updated",
            "project": project,
        }

        return _safe_json_dumps(result)
    except ValueError as e:
        return json.dumps({"status": "not_found", "message": str(e)}, indent=2)
    except Exception as e:
        logger.error(f"update_project failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def remove_project(project_name: str, path: str = ".") -> str:
    """
    Remove a project from the workspace configuration.

    Use this tool to unregister a project that is no longer relevant.

    Args:
        project_name (str): Name of the project to remove
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with removal status

    Example:
        >>> remove_project("old-project")
        '{\\n  "status": "removed",\\n  "project": "old-project"\\n}'

    Keywords: remove, delete, unregister, drop project
    """
    logger.info(f"remove_project called with project_name: {project_name}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        removed = config.remove_project(project_name)

        if not removed:
            return json.dumps({
                "status": "not_found",
                "message": f"Project '{project_name}' not found in workspace",
            }, indent=2)

        return json.dumps({
            "status": "removed",
            "project": project_name,
        }, indent=2)
    except Exception as e:
        logger.error(f"remove_project failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def rename_project(old_name: str, new_name: str, path: str = ".") -> str:
    """
    Rename a registered project.

    Use this tool to fix project naming or standardize naming conventions.

    Args:
        old_name (str): Current project name
        new_name (str): New project name
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with rename results

    Example:
        >>> rename_project("old-name", "new-name")
        '{\\n  "status": "renamed",\\n  "old": "old-name",\\n  "new": "new-name"\\n}'

    Keywords: rename, change name, project name
    """
    logger.info(f"rename_project called with old_name: {old_name}, new_name: {new_name}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        project = config.rename_project(old_name, new_name)

        return json.dumps({
            "status": "renamed",
            "project": project,
        }, indent=2)
    except ValueError as e:
        return json.dumps({"status": "error", "message": str(e)}, indent=2)
    except Exception as e:
        logger.error(f"rename_project failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Tier 4: Action Management
# =============================================================================


def set_project_actions(
    project_name: str,
    actions: str,
    path: str = ".",
) -> str:
    """
    Set build/run/test/clean actions for a project.

    Use this tool to configure what commands should be executed for common
    project operations like building, testing, or running.

    Args:
        project_name (str): Name of the project
        actions (str): JSON string mapping action names to commands
                      Example: '{\"build\": \"make build\", \"test\": \"pytest\"}'
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with confirmation

    Example:
        >>> set_project_actions("my-project", '{"build": "make", "test": "pytest"}')
        '{\\n  "status": "success",\\n  "actions": {...}\\n}'

    Keywords: actions, build, run, test, commands, configure
    """
    logger.info(f"set_project_actions called with project_name: {project_name}")
    try:
        resolved_path = _resolve_path(path)
        action_dict = json.loads(actions)
        config = WorkspaceConfig(workspace_path=resolved_path)
        config.set_actions(project_name, action_dict)

        return json.dumps({
            "status": "success",
            "project": project_name,
            "actions": action_dict,
        }, indent=2)
    except ValueError as e:
        if "not found" in str(e):
            return json.dumps({"status": "not_found", "message": str(e)}, indent=2)
        return json.dumps({"status": "error", "message": f"Invalid JSON: {str(e)}"}, indent=2)
    except Exception as e:
        logger.error(f"set_project_actions failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def set_single_action(
    project_name: str,
    action_name: str,
    command: str,
    path: str = ".",
) -> str:
    """
    Set a single action command for a project.

    Use this tool to add or update one specific action without replacing
    all existing actions.

    Args:
        project_name (str): Name of the project
        action_name (str): Action name (e.g., 'build', 'test', 'run', 'clean')
        command (str): Command string to execute
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with confirmation

    Example:
        >>> set_single_action("my-project", "test", "pytest tests/")
        '{\\n  "status": "success",\\n  "action": "test",\\n  "command": "pytest tests/"\\n}'

    Keywords: action, single action, add action, command
    """
    logger.info(f"set_single_action called with project_name: {project_name}, action: {action_name}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        config.set_action(project_name, action_name, command)

        return json.dumps({
            "status": "success",
            "project": project_name,
            "action": action_name,
            "command": command,
        }, indent=2)
    except ValueError as e:
        return json.dumps({"status": "not_found", "message": str(e)}, indent=2)
    except Exception as e:
        logger.error(f"set_single_action failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def get_project_actions(project_name: str, path: str = ".") -> str:
    """
    Get all configured actions for a project.

    Use this tool to inspect what commands are configured for a project.

    Args:
        project_name (str): Name of the project
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with action commands

    Example:
        >>> get_project_actions("my-project")
        '{\\n  "project": "my-project",\\n  "actions": {"build": "make", ...}\\n}'

    Keywords: actions, get actions, commands, configured
    """
    logger.info(f"get_project_actions called with project_name: {project_name}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        project = config.get_project(project_name)

        if not project:
            return json.dumps({
                "status": "not_found",
                "message": f"Project '{project_name}' not found",
            }, indent=2)

        return json.dumps({
            "project": project_name,
            "actions": project.get("actions", {}),
        }, indent=2)
    except Exception as e:
        logger.error(f"get_project_actions failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Tier 5: HITL Integration for Ambiguous Detection
# =============================================================================


def _resolve_ambiguity_sync(candidates: List[tuple], path: str) -> Dict[str, Any]:
    """
    Synchronous wrapper for HITL ambiguity resolution.

    Uses the existing HITL infrastructure (ConsoleInputModule) to prompt
    the user when project type detection is ambiguous.

    Args:
        candidates: List of (project_type, confidence) tuples
        path: Path being scanned

    Returns:
        Dictionary with resolution results
    """
    timeout = _get_hitl_timeout()
    default_answer = os.environ.get("TORVALDS_HITL_DEFAULT_ANSWER", "1")

    # Build prompt
    options = []
    for i, (proj_type, confidence) in enumerate(candidates, 1):
        options.append(f"{i}. {proj_type} (confidence: {confidence:.2f})")

    prompt_text = (
        f"\nMultiple project types detected in '{path}':\n"
        f"\n" + "\n".join(options) +
        f"\n\nEnter the number of the correct project type (default: 1, timeout: {timeout}s):"
    )

    # Use ConsoleInputModule for synchronous-style input
    try:
        from components.console_input_module import ConsoleInputModule

        async def _do_prompt():
            console = ConsoleInputModule()
            response = await ConsoleInputModule.prompt(
                message=prompt_text,
                default=default_answer,
                timeout=timeout,
            )
            return response

        # Run async prompt synchronously
        response, timed_out = asyncio.run(_do_prompt()), False
    except Exception as e:
        logger.warning(f"HITL prompt failed, using best guess: {e}")
        return {
            "project_type": candidates[0][0],
            "method": "error-fallback",
            "note": f"HITL prompt failed: {e}",
        }

    # Parse response
    try:
        choice = int(response.strip()) if response.strip() else 1
        if choice == 0:
            selected_type = "Unknown"
        elif 1 <= choice <= len(candidates):
            selected_type = candidates[choice - 1][0]
        else:
            selected_type = candidates[0][0]
    except ValueError:
        selected_type = candidates[0][0]

    return {
        "project_type": selected_type,
        "method": "human",
        "candidates": [{"type": t, "confidence": c} for t, c in candidates],
    }


def resolve_project_type_ambiguity(path: str = ".") -> str:
    """
    Prompt the user to resolve ambiguous project type detection.

    When the scanner detects multiple possible project types with similar
    confidence scores, this function presents the options to the user
    and lets them choose the correct project type.

    Uses the existing HITL infrastructure with configurable timeout.

    Args:
        path (str): Directory path to resolve (default: current directory)

    Returns:
        str: JSON string with the resolved project type

    Example:
        >>> resolve_project_type_ambiguity("/home/user/ambiguous-project")
        '{\\n  "resolved": true,\\n  "project_type": "Python",\\n  ...\\n}'

    Keywords: resolve, ambiguity, human-in-the-loop, choose, select, confirm, hitl
    """
    logger.info(f"resolve_project_type_ambiguity called with path: {path}")
    try:
        resolved_path = _resolve_path(path)

        if not os.path.isdir(resolved_path):
            return json.dumps({"error": f"Path is not a directory: {resolved_path}"}, indent=2)

        scanner = ProjectScanner()
        candidates = scanner.get_candidates(resolved_path)

        if not candidates:
            return json.dumps({
                "resolved": False,
                "error": "No project indicators found",
                "path": resolved_path,
            }, indent=2)

        # If single candidate with high confidence, no ambiguity
        if len(candidates) == 1 and candidates[0][1] >= 0.8:
            return json.dumps({
                "resolved": True,
                "project_type": candidates[0][0],
                "confidence": candidates[0][1],
                "method": "auto",
                "note": "Single high-confidence detection, no ambiguity",
            }, indent=2)

        # Check if actually ambiguous
        if not _check_ambiguity(candidates):
            return json.dumps({
                "resolved": True,
                "project_type": candidates[0][0],
                "confidence": candidates[0][1],
                "method": "auto",
                "note": "Clear winner detected, no ambiguity",
            }, indent=2)

        # Trigger HITL resolution
        resolution = _resolve_ambiguity_sync(candidates, resolved_path)

        return json.dumps({
            "resolved": True,
            "project_type": resolution["project_type"],
            "method": resolution["method"],
            "candidates": resolution.get("candidates", []),
        }, indent=2)

    except TimeoutError:
        # Fallback to best guess on timeout
        return json.dumps({
            "resolved": True,
            "project_type": candidates[0][0] if candidates else "Unknown",
            "method": "timeout-fallback",
            "note": "User did not respond in time, using best guess",
        }, indent=2)
    except Exception as e:
        logger.error(f"resolve_project_type_ambiguity failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Tier 6: Workspace Summary and Utilities
# =============================================================================


def get_workspace_summary(path: str = ".") -> str:
    """
    Get a comprehensive summary of the workspace state.

    Use this tool to get an overview of all registered projects, their types,
    git status, and action configuration.

    Args:
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with workspace summary

    Example:
        >>> get_workspace_summary()
        '{\\n  "workspace_path": "...",\\n  "total_projects": 3,\\n  ...\\n}'

    Keywords: summary, overview, workspace state, status
    """
    logger.info(f"get_workspace_summary called with path: {path}")
    try:
        resolved_path = _resolve_path(path)
        manager = ProjectManager(workspace_path=resolved_path)
        summary = manager.get_workspace_summary()

        return _safe_json_dumps(summary)
    except Exception as e:
        logger.error(f"get_workspace_summary failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def get_project_types_summary(path: str = ".") -> str:
    """
    Get a summary of projects grouped by type.

    Use this tool to see what types of projects exist in the workspace
    and how many of each type.

    Args:
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with type grouping

    Example:
        >>> get_project_types_summary()
        '{\\n  "types": {"Python": ["proj1", "proj2"], "Node.js": ["proj3"]}\\n}'

    Keywords: types, group, categorize, project types
    """
    logger.info(f"get_project_types_summary called with path: {path}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        type_groups = config.get_project_types()

        return json.dumps({
            "workspace_path": resolved_path,
            "types": type_groups,
            "type_count": len(type_groups),
        }, indent=2)
    except Exception as e:
        logger.error(f"get_project_types_summary failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


def clear_all_projects(path: str = ".") -> str:
    """
    Remove all projects from the workspace configuration.

    WARNING: This is a destructive operation that cannot be undone.
    Use this tool to reset the workspace configuration.

    Args:
        path (str): Path to workspace root (default: current directory)

    Returns:
        str: JSON string with confirmation

    Example:
        >>> clear_all_projects()
        '{\\n  "status": "cleared",\\n  "message": "All projects removed"\\n}'

    Keywords: clear, reset, remove all, wipe
    """
    logger.info(f"clear_all_projects called with path: {path}")
    try:
        resolved_path = _resolve_path(path)
        config = WorkspaceConfig(workspace_path=resolved_path)
        project_count = len(config.get_all_projects())
        config.clear_projects()

        return json.dumps({
            "status": "cleared",
            "projects_removed": project_count,
            "message": "All projects removed from workspace",
        }, indent=2)
    except Exception as e:
        logger.error(f"clear_all_projects failed: {e}")
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Tool Registration
# =============================================================================


def get_all_tools() -> List[FunctionTool]:
    """
    Return all project manager tools as FunctionTool objects for on-demand loading.

    Each tool includes category metadata for better retrieval.

    Returns:
        List[FunctionTool]: List of Project Manager FunctionTool objects
    """
    logger.info("get_all_tools called for Project Manager Toolkit")
    return [
        # Tier 1: Project Detection
        FunctionTool.from_defaults(
            fn=scan_directory,
            name="scan_directory",
            description="Scan a directory to detect project types with confidence scores. "
                        "Returns ambiguity flag. Use for identifying what kind of project exists. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_project_indicators,
            name="get_project_indicators",
            description="Get indicator files used to detect a specific project type. "
                        "Use for understanding detection signals. Category: Project Management",
        ),
        # Tier 2: Workspace Configuration
        FunctionTool.from_defaults(
            fn=get_workspace_config,
            name="get_workspace_config",
            description="Load and return workspace configuration. "
                        "Use for inspecting workspace state and registered projects. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=list_projects,
            name="list_projects",
            description="List all registered projects in the workspace. "
                        "Use for seeing what projects are tracked. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_project_details,
            name="get_project_details",
            description="Get detailed information about a specific registered project. "
                        "Use for inspecting project metadata. Category: Project Management",
        ),
        # Tier 3: Project Registration and Management
        FunctionTool.from_defaults(
            fn=register_project,
            name="register_project",
            description="Scan a directory, detect its type, and register it in the workspace. "
                        "Automatically triggers HITL when detection is ambiguous. "
                        "Use for discovering and registering new projects. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=update_project,
            name="update_project",
            description="Update metadata for a registered project. "
                        "Use for modifying project properties. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=remove_project,
            name="remove_project",
            description="Remove a project from the workspace configuration. "
                        "Use for unregistering projects. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=rename_project,
            name="rename_project",
            description="Rename a registered project. "
                        "Use for fixing or standardizing project names. Category: Project Management",
        ),
        # Tier 4: Action Management
        FunctionTool.from_defaults(
            fn=set_project_actions,
            name="set_project_actions",
            description="Set build/run/test/clean actions for a project. "
                        "Use for configuring project commands. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=set_single_action,
            name="set_single_action",
            description="Set a single action command for a project without replacing others. "
                        "Use for adding individual commands. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_project_actions,
            name="get_project_actions",
            description="Get all configured actions for a project. "
                        "Use for inspecting project commands. Category: Project Management",
        ),
        # Tier 5: HITL Integration
        FunctionTool.from_defaults(
            fn=resolve_project_type_ambiguity,
            name="resolve_project_type_ambiguity",
            description="Prompt user to resolve ambiguous project type detection using HITL. "
                        "Use when scanner finds multiple similar-confidence types. "
                        "Supports timeout fallback. Category: Project Management",
        ),
        # Tier 6: Workspace Summary and Utilities
        FunctionTool.from_defaults(
            fn=get_workspace_summary,
            name="get_workspace_summary",
            description="Get a comprehensive summary of the workspace state. "
                        "Use for workspace overview. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_project_types_summary,
            name="get_project_types_summary",
            description="Get projects grouped by type. "
                        "Use for type categorization overview. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=clear_all_projects,
            name="clear_all_projects",
            description="Remove all projects from workspace. WARNING: Destructive operation. "
                        "Use for resetting workspace config. Category: Project Management",
        ),
    ]


# =============================================================================
# CLI Demo
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("Project Manager Toolkit - Demo")
    print("=" * 70)

    # Demo: scan current directory
    print("\n--- Scanning current directory ---")
    result = scan_directory(".")
    print(result)

    # Demo: get workspace config
    print("\n--- Workspace Config ---")
    result = get_workspace_config(".")
    print(result)

    # Demo: list projects
    print("\n--- List Projects ---")
    result = list_projects(".")
    print(result)

    # Demo: workspace summary
    print("\n--- Workspace Summary ---")
    result = get_workspace_summary(".")
    print(result)

    print("\n" + "=" * 70)
    print("Demo complete.")