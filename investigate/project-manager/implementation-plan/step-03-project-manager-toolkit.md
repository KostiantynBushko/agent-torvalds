# Step 03: Project Manager Toolkit

## Objective
Create the main `agent_project_manager.py` toolkit that exposes project management capabilities as LlamaIndex FunctionTools, integrating the scanner and config modules.

## Files to Create
- `self-development/agent_project_manager.py`

## Implementation Details

### 1. Toolkit Structure
Follow the same pattern as existing toolkits (e.g., `agent_os_toolkit.py`):

```python
"""
Project Manager Toolkit - Project type detection and workspace management.

This module provides project recognition, workspace configuration,
and Git auto-initialization for the Torvalds AI Agent.

Category: Project Management
Retriever Keywords: project, workspace, detect, scan, configure, git init, agentworkspace
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from llama_index.core.tools import FunctionTool

from project_scanner import ProjectScanner
from workspace_config import WorkspaceConfig

logger = logging.getLogger(__name__)
```

### 2. Core Functions (as Tools)

#### `scan_current_directory()`
```python
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
```

#### `scan_workspace()`
```python
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
```

#### `get_workspace_config()`
```python
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
```

#### `initialize_project()`
```python
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
```

#### `set_project_actions()`
```python
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
```

#### `get_project_info()`
```python
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
```

### 3. Helper Functions

```python
def _init_git_repo(path: str) -> bool:
    """Initialize a Git repository in the given path."""
    try:
        import subprocess
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
```

### 4. Tool Registration

```python
def get_all_tools() -> List[FunctionTool]:
    """Return all project manager tools."""
    return [
        FunctionTool.from_defaults(
            fn=scan_current_directory,
            name="scan_current_directory",
            description="Scan current directory to detect project type",
        ),
        FunctionTool.from_defaults(
            fn=scan_workspace,
            name="scan_workspace",
            description="Scan directory for multiple projects",
        ),
        FunctionTool.from_defaults(
            fn=get_workspace_config,
            name="get_workspace_config",
            description="Get workspace configuration",
        ),
        FunctionTool.from_defaults(
            fn=initialize_project,
            name="initialize_project",
            description="Initialize project tracking and git repo",
        ),
        FunctionTool.from_defaults(
            fn=set_project_actions,
            name="set_project_actions",
            description="Set build/run/test actions for a project",
        ),
        FunctionTool.from_defaults(
            fn=get_project_info,
            name="get_project_info",
            description="Get project details",
        ),
    ]
```

## Acceptance Criteria
- [ ] All functions are exposed as LlamaIndex FunctionTools
- [ ] `get_all_tools()` returns all 6 tools
- [ ] Tools follow the same pattern as existing toolkits
- [ ] Git initialization works correctly
- [ ] Project tracking persists via WorkspaceConfig
- [ ] Error handling is robust
- [ ] Unit tests pass for all tools

## Dependencies
- `project_scanner.py` (Step 01)
- `workspace_config.py` (Step 02)
- LlamaIndex `FunctionTool`
