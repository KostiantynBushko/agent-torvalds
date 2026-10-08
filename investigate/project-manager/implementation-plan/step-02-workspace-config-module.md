# Step 02: Workspace Config Module

## Objective
Create the configuration persistence layer that manages `.agentworkspace.json` files for storing project metadata, build commands, and Git status.

## Files to Create
- `project-manager/workspace_config.py`

## Implementation Details

### 1. Configuration Schema
Define the `.agentworkspace.json` schema:

```python
WORKSPACE_SCHEMA = {
    "version": "1.0",
    "workspace_path": "/absolute/path",
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp",
    "projects": [
        {
            "name": "string",
            "path": "relative/path/",
            "type": "Python|Node.js|Java|C/C++|Rust|Go|ESP32|Yocto|...",
            "git_repo": true,
            "git_branch": "main",
            "indicators_found": ["requirements.txt", "pyproject.toml"],
            "confidence": 0.95,
            "actions": {
                "build": "make build",
                "run": "python main.py",
                "test": "pytest",
                "clean": "make clean"
            },
            "metadata": {
                "description": "Optional project description",
                "framework": "FastAPI|Django|React|...",
                "language_version": "3.11|18|17|..."
            }
        }
    ]
}
```

### 2. WorkspaceConfig Class
Create a `WorkspaceConfig` class with the following methods:

```python
class WorkspaceConfig:
    CONFIG_FILENAME = ".agentworkspace.json"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path).resolve()
        self.config_path = self.workspace_path / self.CONFIG_FILENAME
        self.config = self._load() or self._default_config()
    
    def _load(self) -> Optional[Dict]:
        """Load config from disk"""
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return None
    
    def _default_config(self) -> Dict:
        """Create default config structure"""
        return {
            "version": "1.0",
            "workspace_path": str(self.workspace_path),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "projects": []
        }
    
    def save(self):
        """Persist config to disk"""
        self.config["updated_at"] = datetime.now().isoformat()
        self.config_path.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def add_project(self, name: str, path: str, project_type: str, 
                    indicators: List[str], confidence: float,
                    git_repo: bool = False) -> Dict:
        """Add a new project entry"""
        project = {
            "name": name,
            "path": path,
            "type": project_type,
            "git_repo": git_repo,
            "indicators_found": indicators,
            "confidence": confidence,
            "actions": {},
            "metadata": {}
        }
        self.config["projects"].append(project)
        self.save()
        return project
    
    def update_project(self, name: str, **kwargs):
        """Update an existing project entry"""
        for project in self.config["projects"]:
            if project["name"] == name:
                project.update(kwargs)
                self.save()
                return project
        raise ValueError(f"Project '{name}' not found")
    
    def get_project(self, name: str) -> Optional[Dict]:
        """Get project by name"""
        for project in self.config["projects"]:
            if project["name"] == name:
                return project
        return None
    
    def remove_project(self, name: str) -> bool:
        """Remove a project entry"""
        for i, project in enumerate(self.config["projects"]):
            if project["name"] == name:
                del self.config["projects"][i]
                self.save()
                return True
        return False
    
    def set_actions(self, name: str, actions: Dict[str, str]):
        """Set build/run/test actions for a project"""
        project = self.get_project(name)
        if project:
            project["actions"] = actions
            self.save()
    
    def get_all_projects(self) -> List[Dict]:
        """Return all projects in workspace"""
        return self.config.get("projects", [])
```

### 3. Schema Validation
- Validate config structure on load
- Handle missing fields with defaults
- Support migration from older config versions

### 4. Config File Location Strategy
- Primary: `.agentworkspace.json` in workspace root
- Fallback: `~/.agent-torvalds/workspace.json` for global settings
- Per-project: Support `.agent-project.json` in subdirectories

### 5. Thread Safety
- Use file locking for concurrent access
- Implement read/write locks if needed

## Acceptance Criteria
- [ ] Config file is created with correct schema
- [ ] Projects can be added, updated, and removed
- [ ] Config persists across agent sessions
- [ ] Schema validation catches malformed configs
- [ ] Config file uses UTF-8 encoding
- [ ] Unit tests pass for all operations

## Dependencies
- Standard library: `json`, `pathlib`, `datetime`, `typing`
- Optional: `jsonschema` for validation (can be added later)
