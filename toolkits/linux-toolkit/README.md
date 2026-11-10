# Linux Toolkit

Shell command execution and system inspection, exposed as tools for a
LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/linux-toolkit/
├── __init__.py              # the public API surface
├── operations.py            # the shell and system operations — the library half
├── privilege.py             # the privilege escalation — a sudo becomes a pkexec
├── agent_linux_toolkit.py   # the LlamaIndex adapter
├── py.typed                 # PEP 561 marker
└── tests/                   # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the shell and system operations | **no** | **none** |
| `privilege.py` | the privilege escalation — a `sudo` becomes a `pkexec` | **no** | **none** |
| `agent_linux_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the shell operations stay usable — and testable — as a plain Python
library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

Like the OS toolkit, this toolkit's **library half has no third-party
dependency at all**. It is built on `subprocess`, `os`, `logging`,
`shutil`, `re`, `shlex`, `termios`, `threading`, `signal`, `time` and
`typing` — the standard library. The operations are usable in any Python
that exists.

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
from toolkits.linux_toolkit import execute_shell_command, get_system_info
```

The adapter is a submodule of the package, imported on demand:

```python
from toolkits.linux_toolkit.agent_linux_toolkit import get_all_tools
```

The adapter re-exports the operations, so a star import keeps working the
way it did when the toolkit was a single module:

```python
from toolkits.linux_toolkit.agent_linux_toolkit import *
```

## The operations

| Operation | What it does | Returns |
|-----------|--------------|---------|
| `execute_shell_command(command, timeout=30, cwd=None, shell=True)` | run a shell command | `dict` |
| `execute_multiple_commands(commands, timeout=30)` | run commands in sequence | `list[dict]` |
| `parse_command_output(output)` | split output into lines and metadata | `dict` |
| `get_system_info()` | OS, CPU, memory and disk, via shell | `dict` |
| `check_file_permissions(filepath)` | permissions, owner and group | `dict` |
| `check_privilege_backend()` | how a command that needs root would be run | `dict` |
| `run_command_with_env(command, env_vars)` | run a command with extra environment | `dict` |

## The error contract

Every operation **reports** a failure; none of them raises. A command that
exits non-zero comes back with `success: False` and the error text in
`stderr`; a command that times out comes back with `returncode: -1` and a
message in `stderr`.

```python
>>> execute_shell_command("ls /nonexistent")
{'stdout': '', 'stderr': 'ls: cannot access ...', 'returncode': 2, 'success': False}
>>> execute_shell_command("sleep 5", timeout=1)
{'stdout': '', 'stderr': 'Command timed out after 1 seconds: sleep 5', 'returncode': -1, 'success': False}
```

This is the contract the toolkit has always had, and the move preserved it
exactly.

## A command that needs root

A `sudo` in a command is **escalated through `pkexec`**.  `sudo` reads the
password from the terminal, and the terminal of the agent belongs to the TUI
— which draws the screen itself and therefore puts the terminal into cbreak
mode, with the echo off.  A prompt written into that terminal is painted
over, and the keystrokes are read by the TUI, never by `sudo`.  The command
hangs until the timeout kills it, and the operator is never asked anything.

`pkexec` asks **polkit** instead, and polkit puts the question in a
**window**: the operator types the password there, and the password never
touches the terminal the agent is drawing on.

```console
$ sudo systemctl restart nginx
# becomes
$ pkexec --keep-cwd systemctl restart nginx
```

The rewrite is narrow on purpose:

| Rule | Why |
|---|---|
| only a `sudo` **in command position** is rewritten | `grep sudo /etc/sudoers` is not an escalation |
| `--keep-cwd` is always added | `pkexec` runs a program in the home of the target user, `sudo` does not |
| `--disable-internal-agent` is **always** added | it stops `pkexec` from asking the password **on the terminal** — the question belongs in the window, and only in the window |
| `--user` carries `sudo -u` over | `pkexec --user www-data cmd` runs the program as `www-data` |
| the flags `pkexec` cannot express are dropped, and the drop is reported | `sudo -E` keeps the environment; `pkexec` sanitises it anyway |
| `sudo -l`, `sudo -v` and `sudo -e` are left alone | they do not run a program, and `pkexec` cannot do them |
| everything else is left byte for byte | the redirections, the quotes and the spacing survive |

The password itself is never seen by the toolkit: polkit asks the operator,
and the toolkit only ever sees the exit code.  There is nothing to leak,
because there is nothing to keep.

The terminal of the operator is **not** part of the escalation:

| | |
|---|---|
| the question | is asked in the window, never on the terminal |
| the child of an escalated command | gets no standard input at all — it runs as another user, and it cannot read the keystrokes of the operator |
| the terminal | is given back after the command, whatever the command did to it and whether the timeout killed it |
| a command that outlives its timeout | takes its **whole tree** with it — the program behind the shell does not outlive the timeout |

The last one matters because the state of a terminal belongs to the
terminal, not to the process: a command that was killed while it held the
echo off would leave the operator with a terminal that shows nothing of
what they type, and that state outlives the agent.  The measurements are
in `investigate/pkexec-hidden-typing/` and in
`investigate/privilege-terminal-echo/`.

The timeout of a command ends the tree the way a program is meant to be
ended: a **SIGTERM** first — so a child that can catch it gives the
terminal back by itself — and a **SIGKILL** after the grace period, for
a child that does not care.  The shell alone is not enough: the program
behind the shell is the one that holds the terminal, and it is the
grandchild of the process the timeout used to kill.

The three modes:

| Mode | What it does |
|---|---|
| `auto` (the default) | use `pkexec` when it can show the window; otherwise **refuse the command with the reason** |
| `pkexec` | use `pkexec`; refuse the command when it cannot ask the operator, and say why |
| `sudo` | never rewrite — the command runs exactly as it was written |

The refusal of the mode `auto` is deliberate.  A `sudo` that is run as
it was written asks for the password **on the terminal of the agent**,
and the terminal of the agent cannot give it back — the operator is left
typing into a terminal that shows nothing of what they type.  The
question of a privilege escalation belongs in a window, and in nowhere
else.  The mode `sudo` still asks for it on the terminal: that is the
operator's own choice, and the terminal is given back afterwards.

`check_privilege_backend()` reports what the machine can do, so the agent
can tell the operator what to expect:

```python
>>> check_privilege_backend()
{'backend': 'pkexec', 'usable': True, 'pkexec_path': '/usr/bin/pkexec',
 'gui_session': True, 'polkit_agent': 'gnome-shell', 'terminal_managed': False,
 'reason': '', 'success': True}
```

An escalated command gets **300 seconds** instead of the usual thirty: the
window stays open until somebody answers it.  A timeout the caller asked for
is respected.

The backend of the status is `none` when the machine cannot show the
window — there is nothing to ask with, and the command that needs root is
refused with the reason.

The design, and the measurements behind it, are in
`investigate/linux-privilege-escalation/PROPOSAL_sudo_privilege_escalation.md`.

## A note on `get_system_info`

The **OS toolkit** has a `get_system_info` as well, and the two are
different functions with different shapes:

| | Linux toolkit | OS toolkit |
|---|---|---|
| how | shells out to `uname`, `lscpu`, `free`, `df` | reads `platform` directly |
| returns | the output of those commands, as strings | a dictionary of structured fields |

Both toolkits are loaded into the same process on Linux, so the tool menu
carries the name twice. That duplicate is **pre-existing** — it is on
`master` too, and the move neither creates nor changes it.

## Safety

These operations run **arbitrary shell commands** as the user the agent
runs as. `execute_shell_command` and `run_command_with_env` are as powerful
as the shell itself; there is no allow-list and no sandbox.

A command with a `sudo` in it is run **as root** — through `pkexec`, with
the authorisation of polkit.  The operator is asked in a window, and the
agent cannot answer that window on their behalf.

## Testing

```bash
pytest toolkits/linux-toolkit/tests
```

The suite is offline: it runs harmless commands (`echo`, `pwd`) and never
touches anything outside a temporary directory.

## See also

- `toolkits/os-toolkit` — the cross-platform file-system operations
- `toolkits/apt-toolkit` — package installation on Debian-family systems
