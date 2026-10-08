# Project Manager Implementation Plan

## 📦 Module Structure

**The project manager must be implemented as a Python module inside the `project-manager` folder.**

All source code, tests, and module files belong under:
```
agent-torvalds/
├── project_manager/          # Python package (module)
│   ├── __init__.py
│   ├── scanner.py            # Project type detection engine
│   ├── workspace_config.py   # Configuration persistence layer
│   ├── toolkit.py            # LlamaIndex FunctionTools integration
│   └── ...
├── tests/                    # Module tests
│   ├── __init__.py
│   ├── test_scanner.py
│   ├── test_workspace_config.py
│   └── ...
└── investigate/    
    ├── /project-manager/               # Module documentation
        ├── README.md                   # Module documentation 
        └──implementation-plan/         # Step-by-step implementation guide
```

> **Note:** Do **not** place `project_scanner.py`, `workspace_config.py`, or `agent_project_manager.py` in the self-development root. All project manager code lives inside the `project-manager` folder as a proper Python module.

---

## 📋 Implementation Steps

| Step | Document | Description |
|------|----------|-------------|
| 01 | [Project Scanner Module](step-01-project-scanner-module.md) | Core project type detection engine |
| 02 | [Workspace Config Module](step-02-workspace-config-module.md) | Configuration persistence layer |
| 03 | [Project Manager Toolkit](step-03-project-manager-toolkit.md) | LlamaIndex FunctionTools integration |
| 04 | [HITL Integration](step-04-hitl-integration.md) | Human-in-the-Loop for ambiguous detection |
| 05 | [Agent Integration](step-05-agent-integration.md) | Integration with main agent |
| 06 | [Testing & Validation](step-06-testing-validation.md) | Unit and integration tests |
| 07 | [Documentation & Deployment](step-07-documentation-deployment.md) | Final documentation |

---

## 🏗️ Architecture Overview

See [Current Architecture Analysis](01-current-architecture-analysis.md) for detailed gap analysis and integration points.
