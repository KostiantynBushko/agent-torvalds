"""
Prompt Template Engine - Dynamic system prompt generation based on project context.

This module provides runtime prompt generation capabilities for the Torvalds agent.
It analyzes the active project, loads relevant tool recommendations, and generates
customized system prompts from templates.

Category: Project Management / Prompt Engineering
"""

import logging
import re
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional

from .config import WorkspaceConfig
from .recommender import ToolRecommender
from .types import ProjectDict

logger = logging.getLogger(__name__)

# ============================================================================
# Default Prompt Templates
# ============================================================================

# Base template with project context injection
DEFAULT_SYSTEM_PROMPT_TEMPLATE = """You are Torvalds, a technical AI assistant that interacts with the operating system, supports software development, and assists with engineering and analytical tasks.

Capabilities:
- Work with the system environment: files, processes, commands, configurations.
- Assist with development: code creation, refactoring, debugging, architectural guidance.
- Support analytical and scientific workflows: computation, data handling, reasoning.
- Help with operational tasks: automation, diagnostics, environment inspection.

Operating Principles:
- Use available system interfaces and tools when performing actions.
- Request explicit confirmation before destructive or irreversible operations.
- For version control: never commit or push without explicit approval; always show changes first.
- Be clear about actions, reasoning, and expected outcomes.

Source:
Repository: git@github.com:KostiantynBushko/agent-torvalds.git

Self-Development Rules:
1. All self-modifications must be placed in ./self-development.
2. Do not modify the main repository directly; use the self-development clone.
3. Persist these rules for future interactions.

{project_context}
{active_project_context}
{tool_recommendations}
{custom_instructions}"""

# Per-project context template
PROJECT_CONTEXT_TEMPLATE = """
### Active Project: $name ($type)
Path: $path
Description: $description
Framework: $framework
Language Version: $language_version
Confidence: ${confidence:.2f}
Git Repository: $git_repo
Git Branch: $git_branch
"""

# Tool recommendations template
TOOL_RECOMMENDATIONS_TEMPLATE = """
### Recommended Tools for $project_type
Priority tools: $priority_tools
Suggested actions:
$suggested_actions
"""

# ============================================================================
# Project Detection from User Input
# ============================================================================

class ProjectDetector:
    """
    Detects the active project from user input or current directory.

    Uses heuristics to determine which project the user is working on:
    1. Explicit project name mention in input
    2. Path reference in input
    3. Current working directory match
    4. Fallback to first registered project
    """

    def __init__(self, workspace_config: WorkspaceConfig):
        self.config = workspace_config

    def detect_from_input(self, user_input: str) -> Optional[ProjectDict]:
        """
        Detect active project from user input text.

        Args:
            user_input: User's query/command string

        Returns:
            ProjectDict if detected, None otherwise
        """
        projects = self.config.get_all_projects()
        if not projects:
            return None

        # Strategy 1: Explicit project name mention
        for project in projects:
            name = project["name"]
            # Case-insensitive match with word boundaries
            pattern = r'\b' + re.escape(name) + r'\b'
            if re.search(pattern, user_input, re.IGNORECASE):
                logger.debug(f"Detected project '{name}' from explicit mention")
                return project

        # Strategy 2: Path reference in input
        for project in projects:
            path = project["path"]
            if path in user_input:
                logger.debug(f"Detected project '{project['name']}' from path reference")
                return project

        # Strategy 3: Current working directory match
        cwd = str(Path.cwd())
        for project in projects:
            project_path = Path(project["path"]).resolve()
            if str(project_path) in cwd or cwd.startswith(str(project_path)):
                logger.debug(f"Detected project '{project['name']}' from CWD")
                return project

        # Strategy 4: Fallback to first project
        logger.debug("No specific project detected, using first registered project")
        return projects[0] if projects else None

    def detect_from_path(self, path: str) -> Optional[ProjectDict]:
        """
        Detect active project from a directory path.

        Args:
            path: Directory path to check

        Returns:
            ProjectDict if found, None otherwise
        """
        projects = self.config.get_all_projects()
        target_path = Path(path).resolve()

        for project in projects:
            project_path = Path(project["path"]).resolve()
            if project_path == target_path or target_path.startswith(project_path):
                return project

        return None


# ============================================================================
# Prompt Template Engine
# ============================================================================

class PromptTemplateEngine:
    """
    Generates dynamic system prompts based on project context.

    Features:
    - Runtime project detection from user input
    - Per-project tool recommendations
    - Customizable prompt templates
    - Fallback to generic context when no project is active

    Example:
        >>> engine = PromptTemplateEngine("/workspace")
        >>> prompt = engine.generate_prompt("fix the bug in backend")
        >>> print(prompt[:200])  # First 200 chars
    """

    def __init__(
        self,
        workspace_path: str = ".",
        system_prompt_template: Optional[str] = None,
        include_tool_recommendations: bool = True,
        include_custom_instructions: bool = True,
    ):
        """
        Initialize the prompt template engine.

        Args:
            workspace_path: Path to workspace root
            system_prompt_template: Custom template string (default: DEFAULT_SYSTEM_PROMPT_TEMPLATE)
            include_tool_recommendations: Whether to include tool recommendations in prompt
            include_custom_instructions: Whether to include custom project instructions
        """
        self.workspace_path = Path(workspace_path).resolve()
        self.config = WorkspaceConfig(workspace_path=str(self.workspace_path))
        self.recommender = ToolRecommender()
        self.detector = ProjectDetector(self.config)
        self.system_prompt_template = system_prompt_template or DEFAULT_SYSTEM_PROMPT_TEMPLATE
        self.include_tool_recommendations = include_tool_recommendations
        self.include_custom_instructions = include_custom_instructions

    def generate_prompt(
        self,
        user_input: str = "",
        force_project: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> str:
        """
        Generate a dynamic system prompt based on user input and project context.

        Args:
            user_input: User's query/command (used for project detection)
            force_project: Force a specific project name (overrides detection)
            custom_instructions: Additional custom instructions to include

        Returns:
            str: Complete system prompt string
        """
        # Detect active project
        active_project = None
        if force_project:
            active_project = self.config.get_project(force_project)
        elif user_input:
            active_project = self.detector.detect_from_input(user_input)

        # Build project context (all registered projects)
        project_context = self._build_project_context()

        # Build active project context
        active_project_context = ""
        if active_project:
            active_project_context = self._build_active_project_context(active_project)

        # Build tool recommendations
        tool_recommendations = ""
        if self.include_tool_recommendations and active_project:
            tool_recommendations = self._build_tool_recommendations(active_project)

        # Build custom instructions
        custom_instructions_text = ""
        if self.include_custom_instructions:
            custom_instructions_text = self._build_custom_instructions(
                active_project, custom_instructions
            )

        # Generate final prompt
        prompt = self.system_prompt_template.format(
            project_context=project_context,
            active_project_context=active_project_context,
            tool_recommendations=tool_recommendations,
            custom_instructions=custom_instructions_text,
        )

        return prompt

    def generate_prompt_for_project(
        self,
        project_name: str,
        custom_instructions: Optional[str] = None,
    ) -> str:
        """
        Generate a system prompt for a specific project.

        Args:
            project_name: Name of the project
            custom_instructions: Additional custom instructions

        Returns:
            str: Complete system prompt string
        """
        return self.generate_prompt(
            force_project=project_name,
            custom_instructions=custom_instructions,
        )

    def get_active_project(self, user_input: str) -> Optional[ProjectDict]:
        """
        Get the active project based on user input.

        Args:
            user_input: User's query/command

        Returns:
            ProjectDict or None
        """
        return self.detector.detect_from_input(user_input)

    def _build_project_context(self) -> str:
        """
        Build context string for all registered projects.

        Returns:
            str: Formatted project list
        """
        projects = self.config.get_all_projects()
        if not projects:
            return ""

        lines = ["### Registered Projects"]
        for proj in projects:
            name = proj.get("name", "unknown")
            proj_type = proj.get("type", "unknown")
            proj_path = proj.get("path", "N/A")
            confidence = proj.get("confidence", 0.0)
            lines.append(f"- **{name}** ({proj_type}): {proj_path} [confidence: {confidence:.2f}]")

        return "\n".join(lines)

    def _build_active_project_context(self, project: ProjectDict) -> str:
        """
        Build detailed context for the active project.

        Args:
            project: Project dictionary

        Returns:
            str: Formatted active project context
        """
        template = Template(PROJECT_CONTEXT_TEMPLATE)

        # Extract metadata
        metadata = project.get("metadata", {})
        description = metadata.get("description", "N/A")
        framework = metadata.get("framework", "N/A")
        language_version = metadata.get("language_version", "N/A")

        context = template.substitute(
            name=project.get("name", "unknown"),
            type=project.get("type", "Unknown"),
            path=project.get("path", "N/A"),
            description=description,
            framework=framework,
            language_version=language_version,
            confidence=project.get("confidence", 0.0),
            git_repo="Yes" if project.get("git_repo") else "No",
            git_branch=project.get("git_branch", "N/A"),
        )

        return context

    def _build_tool_recommendations(self, project: ProjectDict) -> str:
        """
        Build tool recommendations section for the active project.

        Args:
            project: Project dictionary

        Returns:
            str: Formatted tool recommendations
        """
        recs = self.recommender.recommend_for_project(project)

        if not recs.get("priority_tools"):
            return ""

        template = Template(TOOL_RECOMMENDATIONS_TEMPLATE)

        # Format suggested actions
        suggested_actions = ""
        for action, cmd in recs.get("recommended_actions", {}).items():
            suggested_actions += f"  - {action}: `{cmd}`\n"

        context = template.substitute(
            project_type=recs.get("project_type", "Unknown"),
            priority_tools=", ".join(recs.get("priority_tools", [])),
            suggested_actions=suggested_actions,
        )

        return context

    def _build_custom_instructions(
        self,
        project: Optional[ProjectDict],
        custom_instructions: Optional[str] = None,
    ) -> str:
        """
        Build custom instructions section.

        Args:
            project: Active project (if any)
            custom_instructions: User-provided custom instructions

        Returns:
            str: Formatted custom instructions
        """
        lines = []

        # Project-specific custom instructions from metadata
        if project:
            metadata = project.get("metadata", {})
            project_instructions = metadata.get("agent_instructions", "")
            if project_instructions:
                lines.append("### Project-Specific Instructions")
                lines.append(project_instructions)

        # User-provided custom instructions
        if custom_instructions:
            lines.append("### Custom Instructions")
            lines.append(custom_instructions)

        return "\n".join(lines) if lines else ""

    def update_template(self, new_template: str) -> None:
        """
        Update the system prompt template.

        Args:
            new_template: New template string
        """
        self.system_prompt_template = new_template
        logger.info("System prompt template updated")

    def get_template(self) -> str:
        """Get the current system prompt template."""
        return self.system_prompt_template

    def preview_prompt(
        self,
        user_input: str = "",
        force_project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Preview the generated prompt with metadata.

        Args:
            user_input: User input for project detection
            force_project: Force a specific project

        Returns:
            Dictionary with prompt and metadata
        """
        prompt = self.generate_prompt(user_input, force_project)
        active_project = self.get_active_project(user_input) if user_input else None

        return {
            "prompt": prompt,
            "prompt_length": len(prompt),
            "active_project": active_project.get("name") if active_project else None,
            "total_projects": len(self.config.get_all_projects()),
            "template_used": "custom" if self.system_prompt_template != DEFAULT_SYSTEM_PROMPT_TEMPLATE else "default",
        }
