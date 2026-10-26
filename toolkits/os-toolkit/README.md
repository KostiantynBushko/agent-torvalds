# OS Toolkit

File-system operations and system information, exposed as tools for a
LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/os-toolkit/
├── __init__.py              # the public API surface
├── operations.py            # the file-system operations — the library half
├── agent_os_toolkit.py      # the LlamaIndex adapter
├── py.typed                 # PEP 561 marker
└── tests/                   # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 11 file-system operations | **no** | **none** |
| `agent_os_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the file-system operations stay usable — and testable — as a plain
Python library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

This toolkit is the odd one out in the series in a good way: **its library
half has no third-party dependency at all**. It is built on `os`,
`shutil`, `pathlib` and `platform` — the standard library. The file-system
operations are usable in any Python that exists.

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
from toolkits.os_toolkit import pwd, ls, mkdir, read_file, write_file
```

The adapter is a submodule of the package, imported on demand:

```python
from toolkits.os_toolkit.agent_os_toolkit import get_all_tools
```

The adapter re-exports the operations, so a star import keeps working the
way it did when the toolkit was a single module:

```python
from toolkits.os_toolkit.agent_os_toolkit import *
```

## The operations

| Operation | What it does | Returns |
|-----------|--------------|---------|
| `pwd()` | the current working directory | `str` |
| `ls(path='.')` | the entries of a directory | `list` |
| `touch(abs_path)` | create an empty file, or update its timestamp | `str` |
| `check_path_exists(abs_path)` | whether a path exists, and what it is | `dict` |
| `mkdir(path)` | create a directory, parents included | `str` |
| `rm(path)` | remove a file or a directory tree | `str` |
| `cp(src, dst)` | copy a file or a directory tree | `str` |
| `mv(src, dst)` | move or rename a file or a directory | `str` |
| `read_file(path)` | the contents of a text file | `str` |
| `write_file(path, content)` | write a file, overwriting it | `str` |
| `get_system_info()` | OS, hardware and user details | `dict` |

## The error contract

Every operation **reports** a failure; none of them raises. A missing
directory comes back as a message string, a failed copy as a message
string, a failed system query as `{"error": "..."}`.

```python
>>> ls("/nonexistent")
'Directory not found: /nonexistent'
>>> rm("/nonexistent")
'Path not found: /nonexistent'
```

This is the contract the toolkit has always had, and the move preserved it
exactly.

## Safety

`rm` is **destructive and irreversible** — for a directory it removes the
whole tree. The tool description says so, and so does the docstring, so
the model sees the warning before it calls the tool.

## Testing

```bash
pytest toolkits/os-toolkit/tests
```

The suite is offline: it works in a temporary directory and never touches
anything outside it.

## See also

- `toolkits/linux-toolkit` — the Linux-specific system calls
- `toolkits/windows-toolkit` — the Windows counterpart
