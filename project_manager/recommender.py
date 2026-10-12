"""
Project-Aware Tool Recommender - Suggest relevant tools based on project type.

Analyzes the detected project type and recommends the most relevant tools
from the available toolkit for that project type.

Category: Project Management
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# Tool Recommendation Database
# ============================================================================
# Maps project types to recommended tool categories and specific tools.

PROJECT_TOOL_RECOMMENDATIONS: Dict[str, Dict[str, Any]] = {
    "Python": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
            "check_command_exists",
            "install_package",
        ],
        "recommended_actions": {
            "build": "python -m build",
            "test": "pytest",
            "lint": "flake8 .",
            "format": "black .",
            "type-check": "mypy .",
        },
        "description": "Python project with pip/poetry/setuptools",
    },
    "Node.js": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
            "check_command_exists",
        ],
        "recommended_actions": {
            "install": "npm install",
            "build": "npm run build",
            "test": "npm test",
            "lint": "npm run lint",
            "dev": "npm run dev",
        },
        "description": "Node.js project with npm/yarn/pnpm",
    },
    "Java": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
        ],
        "recommended_actions": {
            "build": "mvn clean compile",
            "test": "mvn test",
            "package": "mvn package",
            "clean": "mvn clean",
        },
        "description": "Java project with Maven/Gradle",
    },
    "Rust": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
        ],
        "recommended_actions": {
            "build": "cargo build",
            "test": "cargo test",
            "check": "cargo check",
            "clippy": "cargo clippy",
            "fmt": "cargo fmt",
        },
        "description": "Rust project with Cargo",
    },
    "Go": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
        ],
        "recommended_actions": {
            "build": "go build ./...",
            "test": "go test ./...",
            "vet": "go vet ./...",
            "fmt": "go fmt ./...",
        },
        "description": "Go project with go.mod",
    },
    "C/C++": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
        ],
        "recommended_actions": {
            "build": "cmake --build .",
            "test": "ctest",
            "clean": "make clean",
        },
        "description": "C/C++ project with CMake/Make",
    },
    "ESP32/FreeRTOS": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
        ],
        "recommended_actions": {
            "build": "idf.py build",
            "flash": "idf.py flash",
            "monitor": "idf.py monitor",
            "clean": "idf.py fullclean",
        },
        "description": "ESP32/FreeRTOS project with ESP-IDF",
    },
    "Yocto": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
        ],
        "recommended_actions": {
            "build": "bitbake <target>",
            "clean": "bitbake -c clean <target>",
        },
        "description": "Yocto/BitBake embedded Linux project",
    },
    "FPGA": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
        ],
        "recommended_actions": {
            "synthesize": "vivado -mode batch -source synthesize.tcl",
            "implement": "vivado -mode batch -source implement.tcl",
        },
        "description": "FPGA hardware design project",
    },
    "Data Science": {
        "priority_tools": [
            "execute_shell_command",
            "read_file",
            "write_file",
            "check_command_exists",
        ],
        "recommended_actions": {
            "notebook": "jupyter notebook",
            "test": "pytest",
        },
        "description": "Data science project with Jupyter notebooks",
    },
}


class ToolRecommender:
    """
    Recommends tools and actions based on project type.

    Analyzes the detected project type and suggests the most relevant
    tools and default actions for that project type.

    Example:
        >>> recommender = ToolRecommender()
        >>> recs = recommender.recommend_for_type("Python")
        >>> print(recs["priority_tools"])
        ['execute_shell_command', 'read_file', ...]
    """

    def __init__(self):
        self.recommendations = PROJECT_TOOL_RECOMMENDATIONS

    def recommend_for_type(
        self, project_type: str
    ) -> Dict[str, Any]:
        """
        Get tool and action recommendations for a project type.

        Args:
            project_type: The detected project type string

        Returns:
            Dictionary with priority_tools, recommended_actions, and description
        """
        if project_type in self.recommendations:
            return self.recommendations[project_type].copy()

        # Fallback to generic recommendations
        return self._get_generic_recommendations()

    def recommend_for_project(
        self, project: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get tool and action recommendations for a registered project.

        Args:
            project: Project dictionary from workspace config

        Returns:
            Dictionary with recommendations including project-specific info
        """
        project_type = project.get("type", "Unknown")
        recs = self.recommend_for_type(project_type)

        # Merge with project-specific actions if they exist
        project_actions = project.get("actions", {})
        if project_actions:
            recs["configured_actions"] = project_actions
            recs["message"] = "Project has custom actions configured"
        else:
            recs["message"] = "No custom actions configured, using defaults"

        recs["project_name"] = project.get("name", "unknown")
        recs["project_type"] = project_type

        return recs

    def get_supported_types(self) -> List[str]:
        """Get all project types that have specific recommendations."""
        return list(self.recommendations.keys())

    def has_recommendations(self, project_type: str) -> bool:
        """Check if a project type has specific recommendations."""
        return project_type in self.recommendations

    def _get_generic_recommendations(self) -> Dict[str, Any]:
        """Get generic fallback recommendations for unknown project types."""
        return {
            "priority_tools": [
                "execute_shell_command",
                "read_file",
                "write_file",
                "ls",
            ],
            "recommended_actions": {},
            "description": "Generic project - no specific recommendations available",
            "message": "Unknown project type, using generic recommendations",
        }

    def build_context_string(
        self, project: Dict[str, Any]
    ) -> str:
        """
        Build a context string with tool recommendations for system prompt injection.

        Args:
            project: Project dictionary from workspace config

        Returns:
            Formatted string with recommendations
        """
        recs = self.recommend_for_project(project)

        lines = [
            f"\nProject: {recs.get('project_name', 'unknown')} ({recs.get('project_type', 'Unknown')})",
            f"Description: {recs.get('description', 'N/A')}",
        ]

        if recs.get("priority_tools"):
            lines.append(
                f"Recommended tools: {', '.join(recs['priority_tools'])}"
            )

        if recs.get("recommended_actions"):
            lines.append("Suggested default actions:")
            for action, cmd in recs["recommended_actions"].items():
                lines.append(f"  - {action}: {cmd}")

        if recs.get("configured_actions"):
            lines.append("Configured actions:")
            for action, cmd in recs["configured_actions"].items():
                lines.append(f"  - {action}: {cmd}")

        return "\n".join(lines)
