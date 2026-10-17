"""
Project Manager - Orchestration layer for project detection and workspace management.

Coordinates project scanning, type detection, workspace registration, and action
management. This is the primary entry point for project management functionality.

Category: Project Management
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .scanner import ProjectScanner
from .config import WorkspaceConfig
from .types import (
    ConfigDict,
    ProjectDict,
    ActionsDict,
)

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    Orchestrates project detection, registration, and lifecycle management.

    Combines ProjectScanner and WorkspaceConfig to provide a unified interface
    for discovering, registering, and managing projects in a workspace.

    Args:
        workspace_path: Path to the workspace root directory
        max_depth: Maximum directory depth for scanning (default: 3)
        confidence_threshold: Minimum confidence for auto-detection (default: 0.6)
        auto_save: Whether to auto-save config on mutations (default: True)

    Example:
        >>> manager = ProjectManager("/path/to/workspace")
        >>> result = manager.discover_and_register("./my-python-project")
        >>> manager.run_action("my-python-project", "test")
    """

    def __init__(
        self,
        workspace_path: str = ".",
        max_depth: int = 3,
        confidence_threshold: float = 0.6,
        auto_save: bool = True,
    ):
        self.workspace_path = Path(workspace_path).resolve()
        self.scanner = ProjectScanner(
            max_depth=max_depth,
            confidence_threshold=confidence_threshold,
        )
        self.config = WorkspaceConfig(
            workspace_path=str(self.workspace_path),
            auto_save=auto_save,
        )

    # ------------------------------------------------------------------
    # Discovery & Registration
    # ------------------------------------------------------------------

    def scan(self, path: str) -> Dict[str, float]:
        """
        Scan a directory and return confidence scores for all detected project types.

        Args:
            path: Directory path to scan

        Returns:
            Dictionary mapping project types to confidence scores
        """
        return self.scanner.scan_directory(path)

    def detect(self, path: str) -> Optional[str]:
        """
        Detect the project type for a directory.

        Args:
            path: Directory path to detect

        Returns:
            Detected project type or None if ambiguous/below threshold
        """
        return self.scanner.detect_project_type(path)

    def get_candidates(self, path: str) -> List[tuple]:
        """
        Get all candidate project types with confidence scores.

        Args:
            path: Directory path to scan

        Returns:
            List of (project_type, confidence) tuples sorted by confidence descending
        """
        return self.scanner.get_candidates(path)

    def discover_and_register(
        self,
        path: str,
        name: Optional[str] = None,
        force: bool = False,
        description: str = "",
        framework: str = "",
        language_version: str = "",
    ) -> Optional[ProjectDict]:
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
            Registered project dictionary, or None if detection failed and force=False

        Raises:
            ValueError: If a project with the same name already exists
        """
        project_path = Path(path).resolve()
        rel_path = str(project_path.relative_to(self.workspace_path))

        # Detect project type
        detected_type = self.detect(str(project_path))
        candidates = self.get_candidates(str(project_path))

        if detected_type is None:
            if not force:
                logger.warning(
                    f"Could not detect project type for {path}. "
                    f"Use force=True to register anyway."
                )
                return None

            # Force registration with "Unknown" type
            detected_type = "Unknown"
            confidence = 0.0
            indicators = []
        else:
            # Get confidence and indicators for the detected type
            confidence = self.scan(str(project_path)).get(detected_type, 0.0)
            indicators = [ind for ind, _ in self.scanner.get_project_indicators(detected_type)]

        # Derive name from directory if not provided
        if name is None:
            name = project_path.name

        # Check if project already exists
        existing = self.config.get_project(name)
        if existing:
            if force:
                logger.info(f"Project '{name}' already exists, updating...")
                return self.config.update_project(
                    name,
                    type=detected_type,
                    confidence=confidence,
                    indicators_found=indicators,
                )
            raise ValueError(f"Project '{name}' already exists in workspace")

        # Check git status
        git_info = self._get_git_info(str(project_path))

        # Register the project
        project = self.config.add_project(
            name=name,
            path=rel_path,
            project_type=detected_type,
            indicators=indicators,
            confidence=confidence,
            git_repo=git_info.get("is_repo", False),
            git_branch=git_info.get("branch", ""),
            description=description,
            framework=framework,
            language_version=language_version,
        )

        logger.info(f"Registered project '{name}' as {detected_type} (confidence: {confidence:.3f})")
        return project

    # ------------------------------------------------------------------
    # Load Project (NEW)
    # ------------------------------------------------------------------

    def load_project(
        self,
        path: str,
        project_name: Optional[str] = None,
        force: bool = False,
        description: str = "",
        framework: str = "",
        language_version: str = "",
    ) -> Dict[str, Any]:
        """
        Load a project from a given path.

        This is the unified entry point for loading a project. It handles two cases:

        1. **Existing workspace**: If `.agentworkspace.json` exists at the target path,
           it loads the project from the workspace config. If `project_name` is provided,
           it returns that specific project; otherwise it returns the first project
           whose path matches the given path.

        2. **No workspace**: If `.agentworkspace.json` does not exist, it creates a new
           workspace, scans the directory, registers the project, and returns it.

        Args:
            path: Directory path of the project to load
            project_name: Optional project name to look up (only used when loading
                         from an existing workspace)
            force: If True, register even if detection is ambiguous (only used when
                   creating a new workspace)
            description: Optional project description (only used when creating a new workspace)
            framework: Framework name (only used when creating a new workspace)
            language_version: Language version string (only used when creating a new workspace)

        Returns:
            Dictionary with load results including project metadata and load method

        Raises:
            FileNotFoundError: If the path does not exist or is not a directory
            ValueError: If project_name is not found in the existing workspace
        """
        project_path = Path(path).resolve()

        if not project_path.is_dir():
            raise FileNotFoundError(f"Path is not a directory: {project_path}")

        workspace_file = project_path / WorkspaceConfig.DEFAULT_CONFIG_FILENAME

        if workspace_file.exists():
            # Case 1: Existing workspace — load from config
            return self._load_from_existing_workspace(project_path, project_name)
        else:
            # Case 2: No workspace — create, scan, register, and return
            return self._create_and_load(project_path, project_name, force, description, framework, language_version)

    def _load_from_existing_workspace(
        self,
        project_path: Path,
        project_name: Optional[str],
    ) -> Dict[str, Any]:
        """
        Load a project from an existing workspace config.

        Args:
            project_path: Resolved path to the project directory
            project_name: Optional project name to look up

        Returns:
            Dictionary with loaded project data and metadata
        """
        # Create a fresh WorkspaceConfig pointing at the target workspace
        config = WorkspaceConfig(workspace_path=str(project_path))
        projects = config.get_all_projects()

        if not projects:
            raise ValueError(
                f"Workspace exists at {project_path} but contains no registered projects"
            )

        # If project_name is given, look it up directly
        if project_name:
            project = config.get_project(project_name)
            if not project:
                available = [p["name"] for p in projects]
                raise ValueError(
                    f"Project '{project_name}' not found in workspace. "
                    f"Available: {available}"
                )
            return self._build_load_result(project, "existing_workspace", str(project_path))

        # Otherwise, try to match by path
        target_str = str(project_path)
        for proj in projects:
            proj_path = proj.get("path", "")
            # Handle relative paths stored in config
            if proj_path.startswith("."):
                full_proj_path = str(project_path / proj_path).rstrip("/")
            else:
                full_proj_path = proj_path

            if full_proj_path == target_str or proj_path == ".":
                return self._build_load_result(proj, "existing_workspace", str(project_path))

        # No match — return the first project as fallback
        logger.warning(
            f"No project matched path {project_path}, returning first project: {projects[0]['name']}"
        )
        return self._build_load_result(projects[0], "existing_workspace_fallback", str(project_path))

    def _create_and_load(
        self,
        project_path: Path,
        project_name: Optional[str],
        force: bool,
        description: str,
        framework: str,
        language_version: str,
    ) -> Dict[str, Any]:
        """
        Create a new workspace, scan, register, and return the project.

        Args:
            project_path: Resolved path to the project directory
            project_name: Optional project name override
            force: If True, register even if detection is ambiguous
            description: Optional project description
            framework: Framework name
            language_version: Language version string

        Returns:
            Dictionary with newly registered project data and metadata
        """
        # Create a new ProjectManager scoped to this project's directory
        manager = ProjectManager(
            workspace_path=str(project_path),
            auto_save=True,
        )

        project = manager.discover_and_register(
            path=str(project_path),
            name=project_name,
            force=force,
            description=description,
            framework=framework,
            language_version=language_version,
        )

        if project is None:
            return {
                "status": "failed",
                "message": f"Could not detect project type for {project_path}. Use force=True.",
                "path": str(project_path),
                "workspace_created": True,
            }

        return self._build_load_result(project, "new_workspace", str(project_path))

    @staticmethod
    def _build_load_result(
        project: ProjectDict,
        method: str,
        workspace_path: str,
    ) -> Dict[str, Any]:
        """
        Build a standardized load result dictionary.

        Args:
            project: The loaded/registered project dictionary
            method: How the project was loaded ("existing_workspace", "new_workspace", etc.)
            workspace_path: Path to the workspace

        Returns:
            Standardized result dictionary
        """
        return {
            "status": "loaded",
            "method": method,
            "workspace_path": workspace_path,
            "project": {
                "name": project.get("name", "unknown"),
                "path": project.get("path", ""),
                "type": project.get("type", "Unknown"),
                "confidence": project.get("confidence", 0.0),
                "git_repo": project.get("git_repo", False),
                "git_branch": project.get("git_branch", ""),
                "indicators_found": project.get("indicators_found", []),
                "actions": project.get("actions", {}),
                "metadata": project.get("metadata", {}),
            },
        }

    # ------------------------------------------------------------------
    # Project Management
    # ------------------------------------------------------------------

    def get_project(self, name: str) -> Optional[ProjectDict]:
        """Get a project by name."""
        return self.config.get_project(name)

    def get_all_projects(self) -> List[ProjectDict]:
        """Get all registered projects."""
        return self.config.get_all_projects()

    def update_project(self, name: str, **kwargs) -> ProjectDict:
        """Update a project's metadata."""
        return self.config.update_project(name, **kwargs)

    def remove_project(self, name: str) -> bool:
        """Remove a project from the workspace."""
        return self.config.remove_project(name)

    def rename_project(self, old_name: str, new_name: str) -> ProjectDict:
        """Rename a project."""
        return self.config.rename_project(old_name, new_name)

    # ------------------------------------------------------------------
    # Action Management
    # ------------------------------------------------------------------

    def set_actions(self, name: str, actions: ActionsDict) -> None:
        """Set all actions for a project."""
        self.config.set_actions(name, actions)

    def set_action(self, name: str, action_name: str, command: str) -> None:
        """Set a single action for a project."""
        self.config.set_action(name, action_name, command)

    def get_action(self, name: str, action_name: str) -> Optional[str]:
        """
        Get an action command for a project.

        Args:
            name: Project name
            action_name: Action name

        Returns:
            Command string or None if not set
        """
        project = self.config.get_project(name)
        if not project:
            return None
        return project.get("actions", {}).get(action_name)

    def get_actions(self, name: str) -> ActionsDict:
        """Get all actions for a project."""
        project = self.config.get_project(name)
        if not project:
            return {}
        return project.get("actions", {})

    # ------------------------------------------------------------------
    # Workspace Summary
    # ------------------------------------------------------------------

    def get_workspace_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the workspace state.

        Returns:
            Dictionary with workspace statistics and project information
        """
        projects = self.get_all_projects()
        type_groups = self.config.get_project_types()

        return {
            "workspace_path": str(self.workspace_path),
            "total_projects": len(projects),
            "project_types": type_groups,
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

    def print_summary(self) -> None:
        """Print a human-readable workspace summary to logger."""
        summary = self.get_workspace_summary()
        logger.info("=" * 60)
        logger.info(f"Workspace: {summary['workspace_path']}")
        logger.info(f"Total projects: {summary['total_projects']}")
        logger.info("-" * 60)

        for proj in summary["projects"]:
            git_status = " (git)" if proj["git_repo"] else ""
            actions_status = " [has actions]" if proj["has_actions"] else ""
            logger.info(
                f"  {proj['name']:<30} {proj['type']:<15} "
                f"conf:{proj['confidence']:.3f}{git_status}{actions_status}"
            )

        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_git_info(path: str) -> Dict[str, Any]:
        """
        Get Git repository information for a path.

        Returns:
            Dictionary with 'is_repo' and 'branch' keys
        """
        import subprocess

        try:
            result = subprocess.run(
                ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            is_repo = result.returncode == 0 and result.stdout.strip() == "true"

            if not is_repo:
                return {"is_repo": False, "branch": ""}

            result = subprocess.run(
                ["git", "-C", path, "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            branch = result.stdout.strip() if result.returncode == 0 else ""

            return {"is_repo": True, "branch": branch}

        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return {"is_repo": False, "branch": ""}
