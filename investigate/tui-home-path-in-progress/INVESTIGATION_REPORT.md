# The home of the operator on the screen of the progress pane

**Status:** implemented, covered by tests and by a probe that fail without it.
**Reported by:** the operator, on 2026-11-20 — *"the agent internally uses user home directory which is
file but in the 'Workflow & Tool Progress' window it must be shown as a '~/' … the path to user home
folder can be used internally but should be hidden in TUI view"*.

**Probe:** [`probe_home_path.py`](probe_home_path.py) — read-only.  It renders the real panel, with the
real state, and reports what the screen carries.  It writes nothing and talks to no service.

---

## 1. The report

The *Workflow & Tool Progress* pane shows the tool that runs and, under its name, the line that says
what it works on.  That line carried the home directory of the operator **in full** — on every path
the agent touched below the home.

The home is private: it names the account of the operator and the machine he works on.  The rule of the
repository says so for the **public** repository — the home must never reach the source, the
documentation, a commit message or the body of a pull request.  The pane is not the repository — it is
the screen of the operator — but the same reasoning holds there: the screen does not need the account
of the operator to tell him what the agent is doing, and `~/notes/todo.md` says it as well as
`/home/<account>/notes/todo.md`.

## 2. What the pane was doing

`components/tui/state_bridge.py` — `update_tool_start()` builds the line under the name of the tool:

```python
details = ""
if tool_name == "execute_shell_command":
    details = tool_kwargs.get("command", "")[:40]
elif "file_path" in tool_kwargs:
    details = tool_kwargs.get("file_path", "")[:40]
```

`components/tui/progress_view.py` — the pane renders the line as it is:

```python
if task.details:
    row_markup += f"\n   [dim]└ {task.details}[/dim]"
```

Nothing between the two touched the path, so the pane showed what the tool was given.

**Before** — the pane, rendered by the probe:

```
│  ⠋ read_file (0.0s)                                      │
│    └ /home/user/notes/todo.md                           │
│  ⠋ execute_shell_command (0.0s)                          │
│    └ cat /home/user/notes/todo.md                       │
│  ⠋ execute_shell_command (0.0s)                          │
│    └ python -m pytest --rootdir=/home/user/p            │
```

## 3. Where the change belongs

The operator asked for the decision to be made.  It is made here:

| | |
| --- | --- |
| **The rule** | `components/tui/path_display.py` — the only place that knows how to hide a home. |
| **The use** | `components/tui/progress_view.py` — the **view** hides it. |
| **The state** | `components/tui/state_bridge.py` — the state keeps the **truth**. |

The split follows from what each of the two needs:

* the **agent** works with the path of the machine — the tools read the files the paths name.  A path
  of `~` is not a path a tool can open.  So the state keeps the real path, and nothing is lost.
* the **screen** is for the operator, and the screen does not need his account in it.

So the hiding is a **view** concern, and the view is where it happens.  The rule itself is a module of
its own, because a rule that is written twice is a rule that is written wrong twice — and because it
has to be testable without a terminal.

### The cut comes after the hiding

The line was cut to forty characters **in the state**, before the view ever saw it.  A cut that lands
inside the home leaves half of it on the screen — `python -m pytest --rootdir=/home/user/p` above
carries the first six characters of the home of the operator, and it is the cut that put them there.

The cut is a decision of the **screen** — how much of the line fits — so it belongs in the view, and
it belongs *after* the hiding.  The state keeps the whole path; the view hides the home and then cuts
what is left.

## 4. The rule

`hide_home(text, home=None)` replaces the home with `~`:

* **the home is a whole path component** — the home is hidden, and a folder whose name only *starts*
  with the home is another folder and is left alone.  Every character that cannot be a part of a name
  ends the name of the home: a separator ends it, a **quote** ends it, a space ends it, and the end of
  the text ends it — so `cat "/home/<user>/notes/todo.md"` is hidden as well;
* **the separator behind the home stays** — the path keeps the spelling of its own system: `~/notes`
  on Linux, `~\Documents` on Windows.  Only the home is hidden; the path is not rewritten;
* **a Windows home is hidden the same way** — the spelling of the home travels with the home, so the
  behaviour is the same on every machine, and the check does not need a Windows machine to run;
* **the home is computed, never written down** — the home of the machine is found at run time, and the
  rule is told which home to hide.

## 5. After

```
│  ⠋ read_file (0.0s)                                      │
│    └ ~/notes/todo.md                                     │
│  ⠋ execute_shell_command (0.0s)                          │
│    └ cat ~/notes/todo.md                                 │
│  ⠋ execute_shell_command (0.0s)                          │
│    └ python -m pytest --rootdir=~/project                │
```

The state still carries the real path — the agent opens the file the path names.

## 6. What is not in the change

* **The log file is not touched.**  The log of the agent is written for the operator, in his own home,
  and it carries the real paths: a log that hides the paths cannot be read with a tool.
* **The chat view is not touched.**  It does not render the arguments of the tools — the progress pane
  was the only window of the TUI that showed a path.
* **The path is not rewritten.**  A tool that is given `~/notes/todo.md` opens the wrong file — the
  tools are given the path of the machine, and they keep it.
