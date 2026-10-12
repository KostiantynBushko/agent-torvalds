# Step 04: HITL Integration for Ambiguous Project Detection

## Objective
Integrate the existing Human-in-the-Loop (HITL) infrastructure with the project scanner to resolve ambiguous project type detections.

## Files to Modify/Create
- `agent_project_manager.py` (modify - add HITL function)
- `components/human_loop_handler.py` (reuse existing)

## Implementation Details

### 1. Leverage Existing HITL Components
The agent already has HITL infrastructure:
- `HumanLoopHandler` - Orchestrates human prompts
- `TimeoutManager` - Handles timeout for prompts
- `ConsoleInputModule` - Console-based input
- `WhiptailInputModule` - Dialog-based input (Linux)

### 2. Add HITL Resolution Function to Project Manager Toolkit

```python
def resolve_project_type_ambiguity(path: str = ".") -> str:
    """
    Prompt the user to resolve ambiguous project type detection.
    
    When the scanner detects multiple possible project types with similar
    confidence scores, this function presents the options to the user
    and lets them choose the correct project type.
    
    Args:
        path: Directory path to resolve (default: current directory)
        
    Returns:
        str: JSON string with the resolved project type
        
    Keywords: resolve, ambiguity, human-in-the-loop, choose, select, confirm
    """
    from components.human_loop_handler import HumanLoopHandler
    from components.timeout_manager import TimeoutManager
    
    scanner = ProjectScanner()
    candidates = scanner.get_candidates(path)
    
    if not candidates:
        return json.dumps({"error": "No project indicators found", "path": path})
    
    # If single candidate with high confidence, no ambiguity
    if len(candidates) == 1 and candidates[0][1] >= 0.8:
        return json.dumps({
            "resolved": True,
            "project_type": candidates[0][0],
            "confidence": candidates[0][1],
            "method": "auto",
        })
    
    # Build prompt for user
    options = []
    for i, (proj_type, confidence) in enumerate(candidates, 1):
        options.append(f"{i}. {proj_type} (confidence: {confidence:.2f})")
    
    prompt = (
        f"Multiple project types detected in '{path}':\n"
        f"\n" + "\n".join(options) +
        f"\n\nEnter the number of the correct project type (or 0 for Unknown):"
    )
    
    # Use existing HITL handler
    handler = HumanLoopHandler(
        method=os.environ.get("TORVALDS_HITL_METHOD", "console"),
        timeout=int(os.environ.get("TORVALDS_HITL_TIMEOUT", "30")),
    )
    
    try:
        response = handler.ask(prompt)
        
        # Parse response
        try:
            choice = int(response.strip())
            if choice == 0:
                selected_type = "Unknown"
            elif 1 <= choice <= len(candidates):
                selected_type = candidates[choice - 1][0]
            else:
                selected_type = candidates[0][0]  # Default to first
        except ValueError:
            selected_type = candidates[0][0]  # Default on invalid input
        
        return json.dumps({
            "resolved": True,
            "project_type": selected_type,
            "method": "human",
            "candidates": [{"type": t, "confidence": c} for t, c in candidates],
        }, indent=2)
        
    except TimeoutError:
        # Fallback to best guess on timeout
        return json.dumps({
            "resolved": True,
            "project_type": candidates[0][0],
            "method": "timeout-fallback",
            "note": "User did not respond in time, using best guess",
        }, indent=2)
```

### 3. Integrate Ambiguity Check into Project Initialization
Modify `initialize_project()` to call HITL when ambiguity is detected:

```python
def initialize_project(name: str, project_type: str = None, path: str = ".") -> str:
    project_path = Path(path).resolve()
    scanner = ProjectScanner()
    
    candidates = scanner.get_candidates(str(project_path))
    
    # Check for ambiguity
    if candidates and len(candidates) > 1:
        # Top 2 candidates are close in confidence
        if candidates[0][1] - candidates[1][1] < 0.15:
            # Trigger HITL resolution
            resolution = resolve_project_type_ambiguity(str(project_path))
            resolution_data = json.loads(resolution)
            project_type = resolution_data.get("project_type")
    
    # ... rest of initialization
```

### 4. Environment Variable Configuration
Use existing HITL environment variables:
- `TORVALDS_HITL_METHOD` - "console" or "whiptail"
- `TORVALDS_HITL_TIMEOUT` - Timeout in seconds
- `TORVALDS_HITL_DEFAULT_ANSWER` - Fallback answer

### 5. Add Tool to Registration
```python
FunctionTool.from_defaults(
    fn=resolve_project_type_ambiguity,
    name="resolve_project_type_ambiguity",
    description="Prompt user to resolve ambiguous project type detection",
)
```

## Acceptance Criteria
- [ ] Ambiguous cases trigger HITL prompt
- [ ] User can select correct project type
- [ ] Timeout falls back to best guess
- [ ] Works with both console and whiptail input methods
- [ ] Resolution result is returned as JSON
- [ ] Integration tests verify HITL flow

## Dependencies
- Step 01: `project_scanner.py`
- Existing: `components/human_loop_handler.py`
- Existing: `components/timeout_manager.py`
