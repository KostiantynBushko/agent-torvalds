# The terminal is given back after a privileged command

## What is proposed

Four changes in the privilege path of the Linux toolkit, and one rule
that carries them:

> **Whoever changes the state of the terminal gives it back — and the
> give-back runs even when the process is interrupted.**

The evidence is in [`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md);
the probe is [`probe_privilege_terminal.py`](probe_privilege_terminal.py).

## The problem, exactly

A command that needs root is escalated: the `sudo` is rewritten into a
`pkexec`, and polkit asks the operator for the password in a window.

Two of the paths do **not** ask in a window:

| Path | When | What it does to the terminal |
|---|---|---|
| the `sudo` fallback | the gate of `pkexec` is closed (no `pkexec`, no display, no polkit agent) | `sudo` switches the **echo off** to read the password |
| pkexec's textual agent | no window answers, and `--disable-internal-agent` was not passed | polkit switches the **echo off** (`polkitagenttextlistener.c`) |

The agent then kills the child when the timeout fires — with **SIGKILL**,
which cannot be caught — and it kills only the **shell** that
`subprocess.run(shell=True)` started, not the `sudo` behind it.  The
terminal keeps the echo-off state, and the operator is left typing into a
terminal that shows nothing.

The other two places in this repository that switch the terminal off
(`components/console_input_module.py`, `components/tui/input_reader.py`)
both give it back in a `finally`, with an `atexit` hook behind it.  The
privilege path has neither.

## The change

### 1. The agent takes the terminal around a command

A small helper in the Linux toolkit — `toolkits/linux-toolkit/terminal.py`
— with two functions:

```python
def hold_terminal() -> Optional[list]:
    """The attributes of the terminal, or None when there is none."""

def restore_terminal(attributes) -> None:
    """Give the terminal back the way it was found."""
```

`execute_shell_command()` and `run_command_with_env()` use them around
the child:

```python
attributes = hold_terminal()
try:
    result = subprocess.run(...)
finally:
    restore_terminal(attributes)
```

The restore is in a `finally`, so it runs when the command succeeds,
when it fails, when it times out, and when the agent is interrupted.

**What was implemented.**  The helper did not become a module of its
own: it landed in `privilege.py`, next to the code it protects, as the
context manager `preserved_terminal()`:

```python
with preserved_terminal():
    result = _run_command(...)
```

The restore uses `TCSANOW` and not `TCSADRAIN`: a restore must not wait
for the output of the terminal to be drained, and a terminal nobody
reads has a queue that never empties.  It runs in a **thread of its
own**, and the caller waits for it for two seconds at most - a terminal
that refuses to give its attributes back cannot hold the agent.

### 2. The child is killed in a way it can answer

The timeout is handled by the agent, not by `subprocess.run()`:

1. **SIGTERM** to the **process group** of the child — the shell, the
   `sudo` and everything behind it.  A child that can catch it gives the
   terminal back itself.
2. A short grace period (a second or two).
3. **SIGKILL** to the same group, for a child that does not care.

The process group is used because the process that holds the terminal is
not the process that `subprocess.run()` starts.  The child is started
with `start_new_session=True`, so the group is the agent's own and the
signal cannot reach the agent itself.

**What was implemented.**  The tree is walked from `/proc` instead of
being taken from a process group.  A group would have to be made with
`start_new_session=True`, and that detaches the child from the
controlling terminal - a `sudo` that has no `/dev/tty` to read the
password from cannot ask at all, and the toolkit must not change *how*
a command asks on a terminal the operator chose.  The tree is read from
`/proc` as it is at that moment: the children are ended first and the
shell is ended last, so it cannot start anything new while the tree is
being ended, and the grace period covers the whole tree.

### 3. The question never lands on the terminal

`--disable-internal-agent` is added **always** — not only when the
terminal belongs to an application.  While a command runs, the agent is
not a console that can answer a question:

* in the TUI the reader of the keyboard eats the keystrokes, and
* at a console the agent is blocked in `subprocess.run`, and the line
  editing of the operator is gone.

The question belongs in a window, and the window is the only place where
it can be answered.

### 4. The `sudo` fallback goes

When the gate of `pkexec` is closed, the command is **refused with the
reason**:

```
The command needs root and pkexec cannot ask for it: no polkit
authentication agent is running
```

instead of being run as a `sudo` that asks for the password on a
terminal that the agent cannot give back.  The mode `sudo` stays — it is
the operator's own choice, and it is documented as "the command runs
exactly as it was written" — but the *fallback* of the mode `auto` goes.

## What is deliberately **not** in this change

* **The whiptail dialog of the APT toolkit.**  It has the same defect,
  and it needs the screen as well as the echo — another component,
  another contract, another change.
* **The cbreak mode of the TUI.**  The TUI draws the screen itself; the
  echo is off on purpose.
* **A `kill -9` of the agent.**  SIGKILL cannot be caught, and no program
  can answer for it.
* **The polkit textual agent.**  It is upstream's code.  The toolkit's
  job is to stop it from being used.

## The evidence

| File | What it is |
|---|---|
| `INVESTIGATION_REPORT.md` | the report — the question, the measurement, the root cause |
| `probe_privilege_terminal.py` | the probe — five measurements, in a pty of its own |

Run the probe:

```bash
.venv/bin/python investigate/privilege-terminal-echo/probe_privilege_terminal.py
```

Before the change it exits **1** — *"the terminal was left mute"*.  After
the change it exits **0**.
