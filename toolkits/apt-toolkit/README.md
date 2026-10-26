# APT Toolkit

Package resolution and installation on Debian-family systems, exposed as
tools for a LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/apt-toolkit/
├── __init__.py              # the public API surface
├── operations.py            # the operations — the library half
├── agent_apt_toolkit.py     # the LlamaIndex adapter
├── cli.py                   # the command-line interface
├── __main__.py              # `python -m toolkits.apt_toolkit`
├── py.typed                 # PEP 561 marker
└── tests/                   # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 10 package, sudo and install operations | **no** | `rich` |
| `agent_apt_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the operations stay usable — and testable — as a plain Python library.
The adapter is the one module that knows about the agent framework, and it
is imported on demand. Importing the toolkit therefore never pulls
LlamaIndex into the process.

Unlike the OS and the Linux toolkit, this toolkit's library half is **not**
dependency-free: it needs `rich` for the console password prompt, which
is the default prompt method. The import is deferred to the call, so the
module still imports without it.

## Installing

Standalone:

```bash
pip install .            # the library half
pip install '.[agent]'   # and the LlamaIndex adapter
```

## Importing

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.apt_toolkit import install_package, find_package_for_command
```

The adapter is a submodule of the package, imported on demand:

```python
from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools
```

The adapter re-exports the operations, so a star import keeps working the
way it did when the toolkit was a single module:

```python
from toolkits.apt_toolkit.agent_apt_toolkit import *
```

## The operations

| Operation | What it does | Returns |
|-----------|--------------|---------|
| `find_package_for_command(command)` | resolve a command to the package that provides it | `dict` |
| `check_command_exists(command)` | is the command on the `PATH`? | `dict` |
| `install_package(package_name, update_first=False, sudo_password=None, password_method="auto")` | install one package | `dict` |
| `install_multiple_packages(package_names, ...)` | install several, in order | `list[dict]` |
| `interactive_install_missing_command(command, ...)` | detect, resolve and install, end to end | `dict` |
| `prompt_sudo_password(method="auto", ...)` | obtain the sudo password | `dict` |
| `test_sudo_password(password)` | is the password valid? | `bool` |
| `clear_sudo_cache()` | forget the cached password | `dict` |
| `set_default_prompt_method(method)` | choose the default prompt method | `dict` |
| `get_default_prompt_method()` | the current default prompt method | `str` |

## The error contract

Every operation **reports** a failure; none of them raises. A package
that cannot be resolved comes back with `success: False` and the reason in
`error`; a command that is not on the `PATH` comes back with
`exists: False`.

```python
>>> find_package_for_command("no-such-command")
{'package_name': None, 'method': 'none', 'success': False, 'candidates': []}
>>> check_command_exists("no-such-command")
{'exists': False, 'path': None, 'success': False}
```

This is the contract the toolkit has always had, and the move preserved it
exactly.

## How the sudo password is obtained

`prompt_sudo_password()` tries the strategies in this order:

1. the `password` parameter,
2. the `TORVALDS_SUDO_PASSWORD` environment variable,
3. the session cache,
4. the prompt method — `console` (stdin) or `whiptail` (a terminal dialog).

In `auto` mode, a failing prompt method falls back to the other one. The
password is **never logged**.

The `whiptail` method needs `components.whiptail_password`, a module of
**this** repository. The import is deferred and guarded: without it — which
is the case in a standalone installation — the whiptail prompt falls back
to the console one.

## The command-line interface

```bash
python -m toolkits.apt_toolkit --show-method
python -m toolkits.apt_toolkit --prompt-method whiptail
```

`--show-method` prints the default password prompt method and exits.
`--prompt-method` changes it for the session. With no arguments at all,
the help is printed.

## Safety

These operations **install system packages** and **run `sudo`**. The
package name is interpolated into a shell command, so it is an
operator-supplied string and not a validated one. The toolkit installs
Debian-family packages and needs root for it; the password never reaches
the log, but it does reach the `sudo` command line.

## Testing

```bash
pytest toolkits/apt-toolkit/tests
```

The suite is offline: every `subprocess` call is mocked, so nothing is
installed and no password is ever requested.

## See also

- `toolkits/linux-toolkit` — shell command execution
- `toolkits/os-toolkit` — the cross-platform file-system operations
