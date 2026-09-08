# Torvald AI Agent Toolkit

A general-purpose AI agent toolkit designed for engineering scientists, mathematicians, and technical professionals. This project provides specialized capabilities for mathematical calculations, system operations, and technical problem-solving with full access to underlying OS functionality.

## Overview

Torvald is an AI assistant that can directly interact with the host operating system and a wide range of technical tools. The toolkit is designed to support engineering scientists, mathematicians, and other technical professionals with comprehensive computational and operational capabilities, including full access to underlying OS functionality.

## Agents Included

### 1. Math Toolkit Agent
- Performs mathematical operations including addition, multiplication, and division
- Provides precise numerical calculations

### 2. System Operations Agent
- Browses file systems
- Runs shell commands
- Manages processes and files
- Works with network shares, containers, and VMs
- Full access to underlying OS functionality

### 3. Git Repository Agent
- Interacts with Git repositories
- Retrieves commit information and repository status

### 4. Technical Problem-Solving Agent
- Supports engineering calculations
- Handles scientific computations
- Provides technical analysis capabilities

## Key Features

- **Mathematical Operations**: Precise numerical calculations and mathematical problem solving
- **System-Level Access**: Direct interaction with operating system resources with full OS functionality access
- **Technical Computing**: Support for engineering and scientific computations
- **Development Environment**: File management and system operations capabilities

## Installation

1. Clone the repository
2. Create a virtual environment: `python -m venv .venv`
3. Activate the virtual environment:
   - Linux/macOS: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`

## Usage

Each agent can be imported and used independently based on your specific technical needs:

```python
# Example usage of different agents
from agent_math_toolkit import add, multiply, divide
from agent_os_toolkit import ls, pwd, mkdir
```

## Project Structure

- `agent_math_toolkit.py` - Mathematical operations agent
- `agent_os_toolkit.py` - System-level operations agent
- `agent_git_toolkit.py` - Git repository management agent
- `agent-torvalds.py` - Main orchestrator script
- `requirements.txt` - Project dependencies

## Contributing

Contributions are welcome! Please follow the existing code style and add appropriate tests for new features.

## License

This project is licensed under the MIT License.