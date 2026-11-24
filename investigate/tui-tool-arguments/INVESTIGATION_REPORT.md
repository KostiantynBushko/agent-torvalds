# Every tool call shows its arguments in the progress pane

**The operator asked on 2026-11-23.**  The *Workflow & Tool Progress*
pane shows the tool that runs and, under its name, the line that says
what it works on:

> currently only execute shell command shows a list of arguments in
> Workflow & Tool Progress window, I think the same must be applied to
> all tools call

The line under the name of the tool was the **arguments of one tool**:
the command of the shell, and the `file_path` of a tool that has one.
Every other call was a name with nothing under it.

The answer to that request was to show **every** argument of **every**
call.  The operator read the answer, found that the second half of it
was too much, and said so on the same day:

> not every tool must show everything it takes as an argument, for
> example write_file, it would be nice to see the path to the file but
> I'm not sure it is ok to print the content it writes

So the pane knows **two** kinds of argument now: a **target** is shown
whole, and a **payload** is measured and never printed.

**Status:** implemented, covered by tests and by a probe that fail
without it.

**Probe:** [`probe_tool_arguments.py`](probe_tool_arguments.py) —
read-only.  It renders the real panel, with the real state, and reports
what the screen carries.  It writes nothing and talks to no service.

---

## 1. What was measured

The state built the line under the name of the tool out of **two hard
coded names**:

```python
# components/tui/state_bridge.py — update_tool_start()
details = ""
if tool_name == "execute_shell_command":
    details = tool_kwargs.get("command", "")
elif "file_path" in tool_kwargs:
    details = tool_kwargs.get("file_path", "")
```

The arguments of the call were there — the event carries all of them —
and everything but two of them was thrown away.

**Before** — the pane, rendered by the probe:

```
│  ⠋ execute_shell_command (0.0s)        │
│    └ ls -la                            │
│  ✔ write_file (0ms)                    │
│  ✔ read_file (0ms)                     │
│  ✔ execute_shell_command (0ms)         │
│    └ cd ~/projects && git status       │
│      --short                           │
```

The operator sees `✔ write_file (0ms)` and does not see the file that
was written, the folder it was written in, or the text that was
written in it.  The same is true of every tool of the repository:
`ls`, `read_file`, `mkdir`, `cp`, `mv`, `rm`, `write_file` — none of
them shows what it works on.

## 2. What was wrong

### 1. The rule was written for one tool

The rule was a list of two names.  A tool that is called with an
argument that is not on that list shows nothing, and a tool that is
called with **several** arguments shows one of them — the one the rule
happens to know.

The arguments of a call are not a property of the tool: they are a
property of the **call**.  The pane shows the calls, and it has to
show what every one of them was given.

### 2. The state threw the arguments away

The record of a task carried a `details` — a **string** that was built
out of the two names above.  The arguments of the call were not kept,
so the view had nothing to show but the string, and the string could
not say which argument was which.

## 3. The change

### The rule is a module of its own

`components/tui/tool_arguments.py` is the rule that turns the arguments
of a call into the text of the line — the way `path_display.py` is the
rule that hides the home, and the way the rule is written down once
and used by the view.

* **One argument: the value alone.**  The name of the only argument
  would only add noise, and the command of the operator keeps the look
  it has had since it is shown whole.
* **Several arguments: they are named.**  `name=value`, one argument
  per line, so that each of them is read on its own and the operator
  can tell which argument is which.  The names are shown when the call
  **has** several arguments — an argument that was not given
  (`path=None`) is not shown, and the argument beside it keeps its
  name.
* **A value that is longer than the pane is folded.**  The head of the
  value is shown, and a marker says how many lines were left out:
  `… 294 more lines …`.  The body of a script is not a line of the pane,
  and a pane that carries it whole is a pane that carries nothing
  else.
* **An argument that carries a payload is measured, and never printed.**
  The head of it is not shown either.  The pane says how much of it
  there is — `300 lines, 2.5 KB` — and not what is in it.

### A payload is a target of its own

The second request of the operator is a rule of its own, and it has two
halves: a **target** and a **payload**.

* A **target** — a path, a name, a flag, the command of the shell — is
  shown **whole**.  It is where the work happens, and the operator
  reads it at a glance.
* A **payload** — the body of a file, the message of a commit, the rows
  of a table, the environment of a command, a password — is **measured**
  and never printed.

A payload is measured for two reasons.  It is where the **secrets** are:
a key that is written in a file was on the screen of the pane with the
text of the file, and the pane is the thing that is shared, that is
scrolled past, and that is read over the shoulder of the operator.  And
it is where the **bulk** is: a file of three hundred lines took eight
lines of the pane away from the log of everything else.

Nothing is lost.  The payload is at the **path** that is shown beside
it, and the agent says what it wrote in the document pane.  The measure
is honest in the way the marker of a folded value is honest, and it is
more exact than the marker: the operator knows how many lines there
are and how big they are, and not only that there is more.

**The command of the shell is not a payload.**  It is the act, and the
operator has to see every character of what runs.  A secret that is
carried *inside* a command is on the screen — the pane does not hide
that, and it does not pretend otherwise.

The names of the payloads are the names the **tools of the agent use**,
taken from the toolkits themselves:

```python
# components/tui/tool_arguments.py
PAYLOAD_ARGUMENTS = frozenset({
    "body", "comment", "commit_message", "content", "data",
    "env_vars", "message", "password", "payload", "sudo_password",
    "text",
})
```

The list is the whole contract between the tools and the pane: a tool
that hands over a body under another name is a tool whose body is
printed, and the name of that argument belongs on this list.

### The state keeps the truth

The record of a task carries the **arguments** of the call now, as they
were given, and not a string that was built out of two hard coded
names:

```python
# components/tui/state_bridge.py — ToolExecutionRecord
arguments: Dict[str, Any] = field(default_factory=dict)
```

The state keeps them **whole**.  The pane decides how much of them is
shown, and how — the way it decides where the home of the operator is
hidden.  The home is hidden on the screen and not in the state, and the
arguments are not cut in the state either.

### The view uses the rule

```python
# components/tui/progress_view.py — _task_lines()
details = format_arguments(task.arguments)
if not details:
    continue

detail = display_detail(details, text_width)
```

The rest of the way to the screen did not change: the home is hidden,
the text is escaped — a command carries square brackets of its own, and
Rich reads them as markup — and the detail is split to the width the
layout really gives the pane.

## 4. The evidence that it works

The pane, at a terminal of 160 columns:

```
│  ⠋ execute_shell_command (0.0s)                      │
│    └ ls -la                                          │
│  ⠋ read_file (0.0s)                                  │
│    └ /tmp/notes.md                                   │
│  ⠋ write_file (0.0s)                                 │
│    └ path=/tmp/notes.md                              │
│      content=300 lines, 2.5 KB                       │
│  ⠋ mkdir (0.0s)                                      │
│    └ /tmp/folder                                     │
│  ⠋ cp (0.0s)                                         │
│    └ src=/tmp/a.md                                   │
│      dst=/tmp/b.md                                   │
```

Every call shows what it was called with.  The command of the shell is
still shown the way it has been shown — the value alone, whole, split
to the width of the pane.  The body of the file is **measured**: the
path is on the screen, and the text of the file is not.

A secret that is written in a file is not on the screen either:

```
│  ⠋ write_file (0.0s)                                 │
│    └ path=/tmp/.env                                  │
│      content=2 lines, 45 B                           │
```

The check of the change: `tests/test_tui_tool_arguments.py` — 41
tests — and `investigate/tui-tool-arguments/probe_tool_arguments.py`,
which drives the real panel from the real state:

```
  PASS  every tool shows its arguments
  PASS  the body of a file is off the screen
  PASS  the command of the shell is still whole
  PASS  the home of the operator is off the screen
  PASS  a long value is folded honestly
  PASS  every line fits the pane
  PASS  the arguments of the call of the workflow reach the pane
```

The rule was broken on purpose — the payload is printed again — and
the check *the body of a file is off the screen* and the check of the
seam fail, while the other checks keep passing.  A check that cannot
fail is not a check.

### The seam between the workflow and the pane

The checks above feed the state directly — the state is the door of
the pane, and the rule is proven behind it.  The **seam** is the road
between the workflow and that door: the workflow publishes the event
of the call, the consumer of the events hands it over, the adapter
puts it into the state, and the pane draws it.  The arguments could be
lost on that road, and nothing would notice.

The last check of the probe and the three last tests of the suite walk
that road with the **real** parts of it: the `ToolCall` event of the
framework, the real `EventConsumer`, the real `TuiEventAdapter`, and
the real panel.  The event is broken on purpose — the arguments of
the event are dropped on the way — and the check and the three tests
fail, while the other checks keep passing.  A check that cannot fail
is not a check.

The gate of the repository stays green: 40 known failures, 0 new, 0
fixed.

## 5. What is **not** in the change

* **The classic console is not touched.**  It prints the command of the
  shell under `🔧 Calling tool: …` as well — and it does it for the
  interactive tools only.  That is a different window and a different
  line; the operator named the pane of the TUI.

* **The document pane is not touched.**  It shows the answer of the
  agent, and the result of a tool is not the answer of the agent.

* **The name of the tool is not changed.**  The line under the name of
  the tool says what the tool works on; the name of the tool is above
  it.

* **A value is not cut in the middle of a word.**  A value that is
  longer than the pane is split by the rule of the pane — a path is cut
  at the separator that fits — and a value that carries more lines than
  the pane shows is folded at a line break, with a marker that says how
  many lines were left out.

* **The result of the call is not on that line.**  The pane shows what
  the tool was given, and not what it answered; the answer is in the
  document pane.

## 6. The files

| file | what changed |
|---|---|
| `components/tui/tool_arguments.py` | the rule — the arguments of a call become the text of the line |
| `components/tui/state_bridge.py` | the record keeps the arguments of the call, whole |
| `components/tui/progress_view.py` | the view uses the rule, and the home is hidden in every argument |
| `tests/test_tui_tool_arguments.py` | the check of the change — 41 tests |
| `investigate/tui-tool-arguments/` | this report and the probe |
| `investigate/tui-home-path-in-progress/probe_home_path.py` | the probe read the field that was renamed — it reads the arguments now |
| `investigate/tui-autoscroll/probe_autoscroll.py` | the probe read the field that was renamed — it reads the arguments now |
| `investigate/tui-running-task-order/probe_running_task_order.py` | the probe read the field that was renamed — it reads the arguments now |
