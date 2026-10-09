"""
Project Manager Toolkit - Project type detection and workspace management.

This module provides project recognition, workspace configuration,
and Git auto-initialization for the Torvalds AI Agent.

Category: Project Management
Retriever Keywords: project, workspace, detect, scan, configure, git init, agentworkspace
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from llama_index.core.tools import FunctionTool

from .scanner import ProjectScanner
from .config import WorkspaceConfig
from .manager import ProjectManager
from .executor import ActionExecutor
from .recommender import ToolRecommender

logger = logging.getLogger(__name__)


# ============================================================================
# Core Tool Functions
# ============================================================================


def scan_current_directory() -> str:
    """
    Scan the current working directory to detect project types.

    Returns:
        str: JSON string with detected project types and confidence scores

    Keywords: scan, detect, project type, identify
    """
    scanner = ProjectScanner()
    path = Path.cwd()
    candidates = scanner.get_candidates(str(path))

    result = {
        "path": str(path),
        "candidates": [{"type": t, "confidence": c} for t, c in candidates],
        "primary_type": candidates[0][0] if candidates else None,
    }

    return json.dumps(result, indent=2)


def scan_workspace(path: str = ".") -> str:
    """
    Scan a directory for multiple projects (workspace mode).

    Args:
        path: Directory path to scan (default: current directory)

    Returns:
        str: JSON string with all detected projects in the workspace

    Keywords: workspace, multi-project, scan all, subdirectories
    """
    scanner = ProjectScanner(max_depth=2)
    workspace_path = Path(path).resolve()

    projects = []
    for subdir in workspace_path.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("."):
            candidates = scanner.get_candidates(str(subdir))
            if candidates:
                projects.append({
                    "path": str(subdir),
                    "type": candidates[0][0],
                    "confidence": candidates[0][1],
                })

    result = {
        "workspace": str(workspace_path),
        "projects_found": len(projects),
        "projects": projects,
    }

    return json.dumps(result, indent=2)


def get_workspace_config(path: str = ".") -> str:
    """
    Load and return the workspace configuration.

    Args:
        path: Path to workspace root (default: current directory)

    Returns:
        str: JSON string with workspace configuration

    Keywords: config, workspace config, agentworkspace, settings
    """
    config = WorkspaceConfig(path)
    return json.dumps(config.config, indent=2, ensure_ascii=False)


def initialize_project(name: str, project_type: str, path: str = ".") -> str:
    """
    Initialize project tracking and auto-create Git repo if needed.

    Args:
        name: Project name
        project_type: Detected or specified project type
        path: Project path (default: current directory)

    Returns:
        str: JSON string with initialization results

    Keywords: init, initialize, setup, git init, register project
    """
    project_path = Path(path).resolve()
    scanner = ProjectScanner()
    config = WorkspaceConfig(str(project_path.parent))

    # Scan for indicators
    candidates = scanner.get_candidates(str(project_path))
    indicators = [t for t, _ in candidates] if candidates else []
    confidence = candidates[0][1] if candidates else 0.0

    # Check Git status
    git_exists = (project_path / ".git").exists()

    # Initialize Git if needed
    git_initialized = False
    if not git_exists:
        git_initialized = _init_git_repo(str(project_path))

    # Add to config
    config.add_project(
        name=name,
        path=str(project_path.relative_to(project_path.parent)),
        project_type=project_type,
        indicators=indicators,
        confidence=confidence,
        git_repo=git_exists or git_initialized,
    )

    result = {
        "project": name,
        "type": project_type,
        "path": str(project_path),
        "git_repo": git_exists or git_initialized,
        "git_initialized": git_initialized,
        "indicators_found": indicators,
        "confidence": confidence,
    }

    return json.dumps(result, indent=2)


def set_project_actions(project_name: str, actions: str) -> str:
    """
    Set build/run/test actions for a project.

    Args:
        project_name: Name of the project
        actions: JSON string with action commands

    Returns:
        str: Confirmation message

    Keywords: actions, build, run, test, commands, configure
    """
    config = WorkspaceConfig(Path.cwd())
    action_dict = json.loads(actions)
    config.set_actions(project_name, action_dict)
    return json.dumps({"status": "success", "project": project_name, "actions": action_dict}, indent=2)


def get_project_info(project_name: str) -> str:
    """
    Get detailed information about a tracked project.

    Args:
        project_name: Name of the project

    Returns:
        str: JSON string with project details

    Keywords: info, details, project info, status
    """
    config = WorkspaceConfig(Path.cwd())
    project = config.get_project(project_name)

    if not project:
        return json.dumps({"error": f"Project '{project_name}' not found"}, indent=2)

    return json.dumps(project, indent=2, ensure_ascii=False)


def execute_project_action(project_name: str, action_name: str, path: str = ".") -> str:
    """
    Execute a configured project action (build, test, run, clean).

    Args:
        project_name: Name of the project
        action_name: Action to execute (e.g., 'build', 'test', 'run', 'clean')
        path: Path to workspace root (default: current directory)

    Returns:
        str: JSON string with execution results

    Keywords: execute, run action, build, test, deploy
    """
    manager = ProjectManager(path)
    executor = ActionExecutor()

    # Get the action command
    command = manager.get_action(project_name, action_name)
    if not command:
        return json.dumps({
            "error": f"No action '{action_name}' configured for project '{project_name}'"
        }, indent=2)

    # Get project path
    project = manager.get_project(project_name)
    if not project:
        return json.dumps({"error": f"Project '{project_name}' not found"}, indent=2)

    project_path = Path(path) / project["path"]

    # Execute the action
    result = executor.execute(
        project_name=project_name,
        action_name=action_name,
        command=command,
        cwd=str(project_path),
    )

    return json.dumps(result.to_dict(), indent=2)


def get_tool_recommendations(project_name: str, path: str = ".") -> str:
    """
    Get tool and action recommendations for a project based on its type.

    Args:
        project_name: Name of the project
        path: Path to workspace root (default: current directory)

    Returns:
        str: JSON string with recommendations

    Keywords: recommend, suggest, tools, actions, best practices
    """
    manager = ProjectManager(path)
    recommender = ToolRecommender()

    project = manager.get_project(project_name)
    if not project:
        return json.dumps({"error": f"Project '{project_name}' not found"}, indent=2)

    recommendations = recommender.recommend_for_project(project)
    return json.dumps(recommendations, indent=2, ensure_ascii=False)


def get_workspace_summary(path: str = ".") -> str:
    """
    Get a summary of the workspace state including all registered projects.

    Args:
        path: Path to workspace root (default: current directory)

    Returns:
        str: JSON string with workspace summary

    Keywords: summary, overview, status, workspace info
    """
    manager = ProjectManager(path)
    summary = manager.get_workspace_summary()
    return json.dumps(summary, indent=2, ensure_ascii=False)


def discover_and_register_project(
    path: str,
    name: Optional[str] = None,
    force: bool = False,
    description: str = "",
    framework: str = "",
    language_version: str = "",
) -> str:
    """
    Scan a directory, detect its project type, and register it in the workspace.

    This is the main orchestration method that combines scanning and registration.

    Args:
        path: Directory path to scan and register
        name: Optional project name (default: derived from directory name)
        force: If True, register even if detection is ambiguous
        description: Optional project description
        framework: Framework name (e.g., FastAPI, React)
        language_version: Language version string

    Returns:
        str: JSON string with registration results

    Keywords: discover, register, auto-detect, scan and register
    """
    manager = ProjectManager(Path.cwd())
    project = manager.discover_and_register(
        path=path,
        name=name,
        force=force,
        description=description,
        framework=framework,
        language_version=language_version,
    )

    if not project:
        return json.dumps({
            "error": f"Could not detect project type for {path}. Use force=True to register anyway."
        }, indent=2)

    return json.dumps(project, indent=2, ensure_ascii=False)


# ============================================================================
# Helper Functions
# ============================================================================


def _init_git_repo(path: str) -> bool:
    """
    Initialize a Git repository in the given path.

    Args:
        path: Directory path to initialize

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        subprocess.run(
            ["git", "init"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "."],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit by AI agent"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to init git repo: {e}")
        return False


# ============================================================================
# Tool Registration
# ============================================================================


def get_all_tools() -> List[FunctionTool]:
    """
    Return all project manager tools.

    Returns:
        List[FunctionTool]: List of all project management FunctionTool objects
    """
    return [
        FunctionTool.from_defaults(
            fn=scan_current_directory,
            name="scan_current_directory",
            description="Scan current directory to detect project type. Use for identifying project types based on file indicators. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=scan_workspace,
            name="scan_workspace",
            description="Scan directory for multiple projects. Use for workspace mode to detect all projects in subdirectories. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_workspace_config,
            name="get_workspace_config",
            description="Get workspace configuration. Use for loading .agentworkspace.json settings. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=initialize_project,
            name="initialize_project",
            description="Initialize project tracking and git repo. Use for registering projects and auto-initializing Git. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=set_project_actions,
            name="set_project_actions",
            description="Set build/run/test actions for a project. Use for configuring project commands. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_project_info,
            name="get_project_info",
            description="Get project details. Use for retrieving information about tracked projects. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=execute_project_action,
            name="execute_project_action",
            description="Execute a configured project action. Use for running build, test, or other project commands. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_tool_recommendations,
            name="get_tool_recommendations",
            description="Get tool and action recommendations for a project. Use for project-aware tool suggestions. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=get_workspace_summary,
            name="get_workspace_summary",
            description="Get workspace summary. Use for overview of all registered projects and their status. Category: Project Management",
        ),
        FunctionTool.from_defaults(
            fn=discover_and_register_project,
            name="discover_and_register_project",
            description="Discover and register a project. Use for auto-detecting project type and registering it in the workspace. Category: Project Management",
        ),
    ]