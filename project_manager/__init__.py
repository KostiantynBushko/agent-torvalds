"""
project_manager - Project management module for workspace orchestration.

Provides project type detection, workspace configuration management,
a unified ProjectManager interface, and LlamaIndex FunctionTools for
agent integration.

Usage:
    from project_manager import ProjectManager, ProjectScanner, WorkspaceConfig

    # Quick scan
    manager = ProjectManager("/path/to/workspace")
    result = manager.discover_and_register("./my-project")

    # Or use components directly
    from project_manager.scanner import ProjectScanner
    scanner = ProjectScanner()
    scores = scanner.scan_directory("./some-path")

    # Or use as LlamaIndex tools
    from project_manager.toolkit import get_all_tools
    tools = get_all_tools()

Category: Project Management
"""

from .scanner import ProjectScanner
from .config import WorkspaceConfig, validate_config, migrate_config
from .manager import ProjectManager
from .executor import ActionExecutor, ActionResult
from .recommender import ToolRecommender
from .toolkit import get_all_tools

# Public API
__all__ = [
    # Main orchestrator
    "ProjectManager",
    # Components (for direct use when needed)
    "ProjectScanner",
    "WorkspaceConfig",
    "ActionExecutor",
    "ActionResult",
    "ToolRecommender",
    # Config utilities
    "validate_config",
    "migrate_config",
    # Toolkit integration
    "get_all_tools",
]

__version__ = "1.0.0"
