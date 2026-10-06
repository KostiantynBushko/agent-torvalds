Here’s the full consolidated description of the task in Markdown format, combining the taxonomy, requirements, and workflow into one specification file.

# AI Agent Project Management Task

## 🎯 Objective
Design and implement an AI agent capable of managing **any type of project** (software, hardware, configuration).  
The agent must recognize the project type when starting from the folder, so the agent treats a current working directory as a project, configure itself accordingly, and persist this knowledge for future sessions.

---

## 🛠️ Core Requirements

### Project Recognition
- Agent scans the current working folder to detect **project types**:
  - Software: Python, Node.js, Java, C/C++, Rust, Go
  - Embedded: ESP32/FreeRTOS, PX4, FPGA
  - System Software: Linux Kernel, U‑Boot
  - Yocto projects
  - Hardware/Configuration: Motorola TRBO, device flashing
  - Documentation, Data Science, Config projects
- Multiple projects may exist in one folder → agent treats folder as a **workspace**.

### Configuration Persistence
- Store metadata in `.agentworkspace.json`:
  - Project name, path, type
  - Build/run/test/flash commands
  - Git repository status

- Example:
  ```json
  {
    "projects": [
      {
        "name": "backend",
        "path": "api/",
        "type": "Python",
        "run_command": "uvicorn main:app"
      },
      {
        "name": "radio_config",
        "path": "motorola_dp4400/",
        "type": "Motorola TRBO",
        "actions": {
          "configure": "trbo_config_tool --file config.json",
          "flash": "trbo_flash --device DP4400 --firmware fw.bin"
        }
      }
    ]
  }
```

### Git Version Control
- Every project must be under Git.
- On entering a folder:
    - If .git/ is missing → agent runs git init, git add ., git commit -m "Initial commit by AI agent".
    - Updates workspace config with git_repo: true.

### Human-in-the-Loop
- If recognition is ambiguous, agent asks user:
    - Input via console or whiptail (dedicated module).
    - Timeout → fallback to default guess.
- Example: “This folder has both requirements.txt and package.json. Should I treat it as Python or Node.js?”

⚙️  Tooling Layer:
    - PythonTool → build/run/test with pip/pytest.
    - NodeTool → npm/yarn build/test.
    - CppTool → gcc/make/cmake.
    - TRBOTool → configure, generate keys, flash radios.
    - YoctoTool → bitbake, devtool.
    - SystemSoftwareTool → kernel config, cross‑compile, bootloader build.
    - FPGA Tool → synthesis, bitstream flashing.

📂 Project Types Taxonomy:
[Project Types Taxonomy](Project-Type-Taxonomi.md)


📌 Workflow Example:
    1. Agent enters `/home/user/Projects/.`
    2. Scanner detects api/ (Python), motorola_dp4400/ (TRBO).
    3. Agent generates .agentworkspace.json with both projects.
    4. nitializes Git repos if missing.
    5. Injects runtime context into prompt:
    ```text
        Current workspace: /home/user/Projects
        Projects: backend (Python), radio_config (Motorola TRBO)
    ```
    6. User runs: `agent.flash("radio_config")` → agent executes TRBO flash command.


🚀 Benefits
    - Unified handling of diverse project types.
    - Automatic Git version control for safety and rollback.
    - Workspace‑level awareness of multiple projects.
    - Extensible plugin system for new domains.
    - Human‑in‑the‑loop ensures correctness when auto‑detection is uncertain.

