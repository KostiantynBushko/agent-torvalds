"""
project_manage - Project management module for workspace orchestration.

Provides project type detection, workspace configuration management,
and a unified ProjectManager interface for discovering and managing projects.

Usage:
    from project_manage import ProjectManager, ProjectScanner, WorkspaceConfig

    # Quick scan
    manager = ProjectManager("/path/to/workspace")
    result = manager.discover_and_register("./my-project")

    # Or use components directly
    from project_manage.scanner import ProjectScanner
    scanner = ProjectScanner()
    scores = scanner.scan_directory("./some-path")

Category: Project Management
"""

from .scanner import ProjectScanner
from .config import WorkspaceConfig, validate_config, migrate_config
from .manager import ProjectManager

# Public API
__all__ = [
    # Main orchestrator
    "ProjectManager",
    # Components (for direct use when needed)
    "ProjectScanner",
    "WorkspaceConfig",
    # Config utilities
    "validate_config",
    "migrate_config",
]

__version__ = "1.0.0"
