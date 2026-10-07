"""
Workspace Config - Configuration persistence layer for project metadata.

Manages `.agentworkspace.json` files for storing project metadata,
build commands, Git status, and other workspace configuration.

Category: Project Management
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import (
    DEFAULT_CONFIG,
    DEFAULT_PROJECT,
    DEFAULT_SCHEMA_VERSION,
    REQUIRED_CONFIG_FIELDS,
    REQUIRED_PROJECT_FIELDS,
    ConfigDict,
    ProjectDict,
    ActionsDict,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Schema Validation and Migration
# ============================================================================

def validate_config(config: ConfigDict) -> bool:
    """
    Validate workspace config structure.

    Args:
        config: Configuration dictionary to validate

    Returns:
        True if valid, raises ValueError otherwise
    """
    if not isinstance(config, dict):
        raise ValueError("Config must be a dictionary")

    missing_fields = [f for f in REQUIRED_CONFIG_FIELDS if f not in config]
    if missing_fields:
        raise ValueError(f"Config missing required fields: {missing_fields}")

    if not isinstance(config.get("projects"), list):
        raise ValueError("'projects' field must be a list")

    for i, project in enumerate(config["projects"]):
        if not isinstance(project, dict):
            raise ValueError(f"Project at index {i} must be a dictionary")
        missing_proj_fields = [f for f in REQUIRED_PROJECT_FIELDS if f not in project]
        if missing_proj_fields:
            raise ValueError(
                f"Project '{project.get('name', i)}' missing required fields: {missing_proj_fields}"
            )

    return True


def migrate_config(config: ConfigDict) -> ConfigDict:
    """
    Migrate config from older schema versions to current.

    Args:
        config: Configuration dictionary to migrate

    Returns:
        Migrated configuration dictionary
    """
    # Ensure all default fields exist
    for field, default_value in DEFAULT_CONFIG.items():
        if field not in config:
            config[field] = default_value

    # Migrate projects
    for project in config.get("projects", []):
        for field, default_value in DEFAULT_PROJECT.items():
            if field not in project:
                project[field] = default_value

    config["version"] = DEFAULT_SCHEMA_VERSION
    return config


# ============================================================================
# WorkspaceConfig Class
# ============================================================================

class WorkspaceConfig:
    """
    Manages .agentworkspace.json configuration files for project metadata.

    Handles loading, saving, and manipulation of workspace configuration
    including project entries, actions, and metadata.

    Args:
        workspace_path: Path to the workspace root directory
        config_filename: Name of the config file (default: .agentworkspace.json)
        auto_save: Whether to auto-save on every mutation (default: True)
    """

    DEFAULT_CONFIG_FILENAME = ".agentworkspace.json"

    def __init__(
        self,
        workspace_path: str,
        config_filename: str = DEFAULT_CONFIG_FILENAME,
        auto_save: bool = True,
    ):
        self.workspace_path = Path(workspace_path).resolve()
        self.config_filename = config_filename
        self.config_path = self.workspace_path / self.config_filename
        self.auto_save = auto_save
        self.config: ConfigDict = self._load() or self._default_config()

        # Ensure workspace path is set
        self.config["workspace_path"] = str(self.workspace_path)

    def _load(self) -> Optional[ConfigDict]:
        """Load config from disk. Returns None if file doesn't exist or is invalid."""
        if not self.config_path.exists():
            return None

        try:
            raw_content = self.config_path.read_text(encoding="utf-8")
            config: ConfigDict = json.loads(raw_content)

            # Migrate and validate
            config = migrate_config(config)
            validate_config(config)

            logger.debug(f"Loaded workspace config from {self.config_path}")
            return config

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config file: {e}")
            return None
        except ValueError as e:
            logger.warning(f"Config validation failed, using defaults: {e}")
            return None
        except OSError as e:
            logger.error(f"Failed to read config file: {e}")
            return None

    def _default_config(self) -> ConfigDict:
        """Create default config structure."""
        now = datetime.now().isoformat()
        return {
            "version": DEFAULT_SCHEMA_VERSION,
            "workspace_path": str(self.workspace_path),
            "created_at": now,
            "updated_at": now,
            "projects": [],
        }

    def save(self) -> None:
        """Persist config to disk."""
        self.config["updated_at"] = datetime.now().isoformat()

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self.config, indent=2, ensure_ascii=False)
            self.config_path.write_text(content, encoding="utf-8")
            logger.debug(f"Saved workspace config to {self.config_path}")
        except OSError as e:
            logger.error(f"Failed to save config file: {e}")
            raise

    def add_project(
        self,
        name: str,
        path: str,
        project_type: str,
        indicators: List[str],
        confidence: float,
        git_repo: bool = False,
        git_branch: str = "",
        description: str = "",
        framework: str = "",
        language_version: str = "",
    ) -> ProjectDict:
        """
        Add a new project entry to the workspace config.

        Args:
            name: Project name
            path: Relative path to the project
            project_type: Detected project type
            indicators: List of indicator files found
            confidence: Detection confidence score (0.0-1.0)
            git_repo: Whether this is a Git repository
            git_branch: Current Git branch name
            description: Optional project description
            framework: Framework name (e.g., FastAPI, React)
            language_version: Language version string

        Returns:
            The created project dictionary

        Raises:
            ValueError: If a project with the same name already exists
        """
        if self.get_project(name):
            raise ValueError(f"Project '{name}' already exists in workspace")

        project: ProjectDict = {
            "name": name,
            "path": path,
            "type": project_type,
            "git_repo": git_repo,
            "git_branch": git_branch,
            "indicators_found": indicators,
            "confidence": round(confidence, 3),
            "actions": {},
            "metadata": {},
        }

        if description:
            project["metadata"]["description"] = description
        if framework:
            project["metadata"]["framework"] = framework
        if language_version:
            project["metadata"]["language_version"] = language_version

        self.config["projects"].append(project)

        if self.auto_save:
            self.save()

        logger.info(f"Added project '{name}' to workspace config")
        return project

    def update_project(self, name: str, **kwargs) -> ProjectDict:
        """
        Update an existing project entry.

        Args:
            name: Project name to update
            **kwargs: Fields to update

        Returns:
            Updated project dictionary

        Raises:
            ValueError: If project not found
        """
        project = self.get_project(name)
        if not project:
            raise ValueError(f"Project '{name}' not found in workspace")

        if "name" in kwargs and kwargs["name"] != name:
            raise ValueError("Cannot change project name through update. Use rename_project instead.")

        project.update(kwargs)

        if self.auto_save:
            self.save()

        logger.info(f"Updated project '{name}' in workspace config")
        return project

    def get_project(self, name: str) -> Optional[ProjectDict]:
        """Get a project entry by name. Returns None if not found."""
        for project in self.config.get("projects", []):
            if project["name"] == name:
                return project
        return None

    def remove_project(self, name: str) -> bool:
        """
        Remove a project entry from the workspace.

        Args:
            name: Project name to remove

        Returns:
            True if removed, False if not found
        """
        for i, project in enumerate(self.config.get("projects", [])):
            if project["name"] == name:
                del self.config["projects"][i]

                if self.auto_save:
                    self.save()

                logger.info(f"Removed project '{name}' from workspace config")
                return True

        return False

    def rename_project(self, old_name: str, new_name: str) -> ProjectDict:
        """
        Rename a project entry.

        Args:
            old_name: Current project name
            new_name: New project name

        Returns:
            Updated project dictionary

        Raises:
            ValueError: If old name not found or new name already exists
        """
        if self.get_project(new_name):
            raise ValueError(f"Project '{new_name}' already exists")

        project = self.get_project(old_name)
        if not project:
            raise ValueError(f"Project '{old_name}' not found")

        project["name"] = new_name

        if self.auto_save:
            self.save()

        logger.info(f"Renamed project '{old_name}' to '{new_name}'")
        return project

    def set_actions(self, name: str, actions: ActionsDict) -> None:
        """
        Set build/run/test/clean actions for a project.

        Args:
            name: Project name
            actions: Dictionary mapping action names to commands

        Raises:
            ValueError: If project not found
        """
        project = self.get_project(name)
        if not project:
            raise ValueError(f"Project '{name}' not found in workspace")

        project["actions"] = actions

        if self.auto_save:
            self.save()

        logger.info(f"Set actions for project '{name}'")

    def set_action(self, name: str, action_name: str, command: str) -> None:
        """
        Set a single action command for a project.

        Args:
            name: Project name
            action_name: Action name (e.g., 'build', 'test')
            command: Command string to execute

        Raises:
            ValueError: If project not found
        """
        project = self.get_project(name)
        if not project:
            raise ValueError(f"Project '{name}' not found in workspace")

        if "actions" not in project:
            project["actions"] = {}

        project["actions"][action_name] = command

        if self.auto_save:
            self.save()

        logger.info(f"Set action '{action_name}' for project '{name}'")

    def get_all_projects(self) -> List[ProjectDict]:
        """Return all projects in the workspace."""
        return self.config.get("projects", [])

    def get_project_types(self) -> Dict[str, List[str]]:
        """
        Group projects by their type.

        Returns:
            Dictionary mapping project types to lists of project names
        """
        types: Dict[str, List[str]] = {}
        for project in self.config.get("projects", []):
            proj_type = project.get("type", "Unknown")
            if proj_type not in types:
                types[proj_type] = []
            types[proj_type].append(project["name"])
        return types

    def clear_projects(self) -> None:
        """Remove all projects from the workspace config."""
        self.config["projects"] = []

        if self.auto_save:
            self.save()

        logger.info("Cleared all projects from workspace config")

    def get_config(self) -> ConfigDict:
        """Get the raw configuration dictionary."""
        return self.config

    def to_json(self) -> str:
        """Serialize config to JSON string."""
        return json.dumps(self.config, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, config: ConfigDict, workspace_path: str = "") -> "WorkspaceConfig":
        """
        Create WorkspaceConfig from a dictionary.

        Args:
            config: Configuration dictionary
            workspace_path: Optional workspace path override

        Returns:
            WorkspaceConfig instance
        """
        migrate_config(config)
        validate_config(config)

        path = workspace_path or config.get("workspace_path", ".")
        instance = cls(workspace_path=path, auto_save=False)
        instance.config = config
        return instance
