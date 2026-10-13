# Runtime Prompt Injection for Project-Aware Agent Behavior

## Overview

Runtime prompt injection dynamically generates the agent's system prompt based on the active project context. Instead of a static system prompt, the agent adapts its behavior, tool recommendations, and instructions based on what project the user is currently working on.

## Problem Statement

Currently, the agent uses a static system prompt with basic project context injection (just listing registered projects). This doesn't provide:
- **Active project awareness** - The agent doesn't know which project the user is working on
- **Contextual tool recommendations** - No guidance on which tools are most relevant for the current project type
- **Project-specific instructions** - No way to inject custom instructions per project
- **Dynamic adaptation** - The prompt doesn't change based on user intent

## Solution Architecture

### Components

```
┌─────────────────────────────────────────────────┐
│              PromptTemplateEngine                │
│                                                 │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ProjectDetector│  │ToolRecommender│             │
│  └──────────────┘  └──────────────┘             │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │         Template System                  │   │
│  │  - Base system prompt template           │   │
│  │  - Project context injection             │   │
│  │  - Active project details                │   │
│  │  - Tool recommendations                  │   │
│  │  - Custom instructions                   │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### ProjectDetector

Detects the active project from user input using multiple strategies:

1. **Explicit mention** - User mentions project name directly (e.g., "fix the bug in backend")
2. **Path reference** - User references a project path
3. **CWD matching** - Current working directory matches a project path
4. **Fallback** - Uses first registered project if no match

### PromptTemplateEngine

Generates complete system prompts with:
- **Base template** - Core agent identity and capabilities
- **Project context** - List of all registered projects
- **Active project context** - Detailed info about the detected active project
- **Tool recommendations** - Priority tools and suggested actions for the project type
- **Custom instructions** - Project-specific instructions from metadata

### Integration Points

```
User Input → ProjectDetector → Active Project
                                    ↓
                    PromptTemplateEngine
                                    ↓
                    Dynamic System Prompt → Agent
```

## Implementation Details

### File: `project_manager/prompt_engine.py`

**Classes:**
- `ProjectDetector` - Detects active project from user input
- `PromptTemplateEngine` - Generates dynamic system prompts

**Key Methods:**
- `generate_prompt(user_input, force_project, custom_instructions)` - Main entry point
- `detect_from_input(user_input)` - Detect project from user text
- `preview_prompt(user_input, force_project)` - Preview generated prompt with metadata

### Template Structure

```python
DEFAULT_SYSTEM_PROMPT_TEMPLATE = """
You are Torvalds, a technical AI assistant...

{project_context}          # All registered projects
{active_project_context}   # Detailed active project info
{tool_recommendations}     # Recommended tools for project type
{custom_instructions}      # Project-specific instructions
"""
```

### Detection Strategies

```python
# Strategy 1: Explicit project name mention
pattern = r'\b' + re.escape(name) + r'\b'
if re.search(pattern, user_input, re.IGNORECASE):
    return project

# Strategy 2: Path reference in input
if path in user_input:
    return project

# Strategy 3: Current working directory match
if str(project_path) in cwd or cwd.startswith(str(project_path)):
    return project

# Strategy 4: Fallback to first project
return projects[0]
```

## Integration with Agent

### Current State

```python
# agent-torvalds.py - Current implementation
_SYSTEM_PROMPT_TEMPLATE = (
    "You are Torvalds..."
    "{project_context}"  # Just lists projects
)

def build_system_prompt(project_context: str = "") -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(project_context=project_context)
```

### Target State

```python
# agent-torvalds.py - After integration
from project_manager.prompt_engine import PromptTemplateEngine

# Initialize prompt engine
prompt_engine = PromptTemplateEngine(workspace_path=".")

# Generate dynamic prompt per query
def build_system_prompt(user_input: str = "") -> str:
    return prompt_engine.generate_prompt(user_input)
```

## Benefits

1. **Contextual Awareness** - Agent knows which project you're working on
2. **Smart Tool Recommendations** - Suggests relevant tools for the project type
3. **Custom Instructions** - Project-specific guidance can be injected
4. **Dynamic Adaptation** - Prompt changes based on user intent
5. **Better Responses** - More relevant and accurate assistance

## Configuration

### Environment Variables

```bash
# Enable/disable prompt injection
TORVALDS_PROMPT_INJECTION=true

# Custom template path
TORVALDS_PROMPT_TEMPLATE=/path/to/template.txt

# Include tool recommendations
TORVALDS_INCLUDE_RECOMMENDATIONS=true
```

### Project Metadata

Projects can include custom instructions in their metadata:

```json
{
  "name": "backend-api",
  "type": "Python",
  "metadata": {
    "agent_instructions": "This is a FastAPI backend. Always use pytest for testing."
  }
}
```

## Testing Strategy

1. **Unit Tests** - Test ProjectDetector with various inputs
2. **Integration Tests** - Test prompt generation with different project configs
3. **End-to-End Tests** - Test full agent flow with prompt injection

## Future Enhancements

1. **Multi-Project Awareness** - Support for multiple active projects
2. **Context Window Management** - Smart truncation for large project lists
3. **Template Customization** - User-defined prompt templates
4. **Learning from Feedback** - Adapt recommendations based on user corrections
5. **Project-Specific LLM Settings** - Different models/parameters per project type

## References

- `project_manager/prompt_engine.py` - Implementation
- `project_manager/recommender.py` - Tool recommendations
- `project_manager/config.py` - Workspace configuration
- `agent-torvalds.py` - Main agent integration point
