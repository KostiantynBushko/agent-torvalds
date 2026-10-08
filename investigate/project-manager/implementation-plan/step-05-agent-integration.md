# Step 05: Agent Integration

## Objective
Integrate the project manager toolkit into the main agent, register tools with the retriever, and extend the system prompt with project awareness context.

## Files to Modify
- `agent_tool_retriever.py`
- `agent-torvalds.py`

## Implementation Details

### 1. Register Project Manager Tools in Retriever
Modify `agent_tool_retriever.py` to include the new toolkit:

```python
def build_tool_retriever(
    llm,
    similarity_top_k: int = 8,
    # ... existing parameters ...
    include_project_manager_tools: bool = True,  # NEW
) -> tuple:
    # ... existing tool collection ...
    
    # NEW: Project Manager toolkit
    if include_project_manager_tools:
        from agent_project_manager import get_all_tools as _get_pm
        all_tools.extend(_get_pm())
    
    # ... rest of function unchanged ...
```

### 2. Extend System Prompt with Project Awareness
Modify the `SYSTEM_PROMPT` in `agent-torvalds.py` to include project context injection:

```python
# Add helper function to build project context
def build_project_context() -> str:
    """Build project context string for system prompt injection."""
    try:
        from workspace_config import WorkspaceConfig
        config = WorkspaceConfig(Path.cwd())
        projects = config.get_all_projects()
        
        if not projects:
            return ""
        
        context_lines = ["\nCurrent Workspace Projects:"]
        for p in projects:
            context_lines.append(
                f"  - {p['name']} ({p['type']}): {p['path']}"
            )
            if p.get('actions'):
                for action_name, cmd in p['actions'].items():
                    context_lines.append(f"    {action_name}: {cmd}")
        
        return "\n".join(context_lines)
    except Exception:
        return ""

# Modify SYSTEM_PROMPT to include project context section
SYSTEM_PROMPT = (
    "Your name is Torvalds an AI assistant that can directly interact with the host operating system..."
    # ... existing prompt ...
    
    "Project Management Capabilities:\n"
    "You can detect project types, manage workspace configurations, and auto-initialize Git repositories.\n"
    "When entering a new directory, scan for project indicators and configure accordingly.\n"
    "Use project-aware tools based on the detected project type.\n"
    
    "{project_context}"  # Placeholder for dynamic injection
)
```

### 3. Auto-Scan on Agent Initialization
Add project scanning during agent startup:

```python
def initialize_project_management():
    """Auto-scan and configure project on agent startup."""
    from project_scanner import ProjectScanner
    from workspace_config import WorkspaceConfig
    
    scanner = ProjectScanner()
    config = WorkspaceConfig(Path.cwd())
    
    # Check if already configured
    existing = config.get_all_projects()
    if existing:
        logger.info(f"Found {len(existing)} configured projects in workspace")
        return
    
    # Scan for projects
    candidates = scanner.get_candidates(str(Path.cwd()))
    if candidates:
        project_type, confidence = candidates[0]
        logger.info(f"Detected project type: {project_type} (confidence: {confidence:.2f})")
        
        # Auto-initialize if confidence is high
        if confidence >= 0.8:
            project_name = Path.cwd().name
            config.add_project(
                name=project_name,
                path=".",
                project_type=project_type,
                indicators=[t for t, _ in candidates],
                confidence=confidence,
                git_repo=(Path.cwd() / ".git").exists(),
            )
            logger.info(f"Auto-configured project: {project_name}")
```

### 4. Add CLI Flag for Project Management
Add a CLI option to control project management behavior:

```python
parser.add_argument(
    "--auto-scan",
    action="store_true",
    help="Auto-scan and configure projects on startup",
)
parser.add_argument(
    "--project-type",
    type=str,
    help="Override auto-detected project type",
)
```

### 5. Context Injection in Agent Workflow
Modify the agent workflow to inject project context before each query:

```python
# In the main agent loop, before processing a query:
project_context = build_project_context()
if project_context:
    agent.memory.put(f"CONTEXT: {project_context}")
```

## Acceptance Criteria
- [ ] Project manager tools are registered with the retriever
- [ ] Tools are semantically retrievable by query
- [ ] System prompt includes project context
- [ ] Auto-scan works on agent startup
- [ ] CLI flags work correctly
- [ ] Project context is injected into agent memory
- [ ] Integration tests verify end-to-end flow

## Dependencies
- Step 01: `project_scanner.py`
- Step 02: `workspace_config.py`
- Step 03: `agent_project_manager.py`
- Existing: `agent_tool_retriever.py`
- Existing: `agent-torvalds.py`
