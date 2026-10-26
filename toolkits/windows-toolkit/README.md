# Windows PowerShell Toolkit

PowerShell command execution and system inspection, exposed as tools for a
LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/windows-toolkit/
├── __init__.py              # the public API surface
├── operations.py            # the PowerShell and system operations — the library half
├── agent_windows_toolkit.py # the LlamaIndex adapter
├── py.typed                 # PEP 561 marker
└── tests/                   # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 6 PowerShell and system operations | **no** | **none** |
| `agent_windows_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the PowerShell operations stay usable — and testable — as a plain
Python library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

Like the OS and the Linux toolkits, this toolkit's **library half has no
third-party dependency at all**. It is built on `subprocess`, `logging`
and `typing` — the standard library. The operations are usable in any
Python that exists.

## Installing

Standalone:

```bash
pip install .            # the library half
pip install '.[agent]'   # and the LlamaIndex adapter
```

The library half depends on nothing outside the standard library. The
adapter needs `llama-index-core`.

## Importing

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.windows_toolkit import execute_shell_command, get_system_info
```

The adapter is a submodule of the package, imported on demand:

```python
from toolkits.windows_toolkit.agent_windows_toolkit import get_all_tools
```

The adapter re-exports the operations, so a star import keeps working the
way it did when the toolkit was a single module:

```python
from toolkits.windows_toolkit.agent_windows_toolkit import *
```

## The operations

| Operation | What it does | Returns |
|-----------|--------------|---------|
| `execute_shell_command(command, timeout=30, cwd=None, shell=True)` | run a PowerShell command | `dict` |
| `execute_multiple_commands(commands, timeout=30)` | run commands in sequence | `list[dict]` |
| `parse_command_output(output)` | split output into lines and metadata | `dict` |
| `get_system_info()` | OS, CPU, memory and disk, via PowerShell cmdlets | `dict` |
| `check_file_permissions(filepath)` | owner and access rules | `dict` |
| `run_command_with_env(command, env_vars)` | run a command with extra environment | `dict` |

The private helper `_get_powershell_command()` picks the executable: it
prefers `pwsh` (PowerShell Core 7+) and falls back to `powershell.exe`
(Windows PowerShell 5.1+).

## The error contract

Every operation **reports** a failure; none of them raises. A command that
exits non-zero comes back with `success: False` and the error text in
`stderr`; a command that times out comes back with `returncode: -1` and a
message in `stderr`.

```python
>>> execute_shell_command("Get-Item /nonexistent")
{'stdout': '', 'stderr': 'Get-Item: Cannot find path...', 'returncode': 1, 'success': False}
>>> execute_shell_command("Start-Sleep 5", timeout=1)
{'stdout': '', 'stderr': 'Command timed out after 1 seconds: Start-Sleep 5', 'returncode': -1, 'success': False}
```

This is the contract the toolkit has always had, and the move preserved it
exactly.

## A note on `get_system_info`

The **OS toolkit** and the **Linux toolkit** have a `get_system_info` as
well, and the three are different functions with different shapes:

| | Windows toolkit | Linux toolkit | OS toolkit |
|---|---|---|---|
| how | shells out to PowerShell cmdlets | shells out to `uname`, `lscpu`, `free`, `df` | reads `platform` directly |
| returns | the output of those commands, as strings | the output of those commands, as strings | a dictionary of structured fields |

Only one of the three is ever loaded on a given platform: the Windows
toolkit on Windows, the Linux one on Linux, the OS one everywhere. The
duplicate in the tool menu on Linux is **pre-existing** — it is on `master`
too, and the move neither creates nor changes it.

## Safety

These operations run **arbitrary PowerShell commands** as the user the
agent runs as. `execute_shell_command` and `run_command_with_env` are as
powerful as the shell itself; there is no allow-list and no sandbox.

## Testing

```bash
pytest toolkits/windows-toolkit/tests
```

The suite is offline and platform-independent: it drives the operations
through a stubbed `subprocess.run`, so it neither needs Windows nor shells
out to anything.

## See also

- `toolkits/os-toolkit` — the cross-platform file-system operations
- `toolkits/linux-toolkit` — the counterpart of this toolkit on Linux
