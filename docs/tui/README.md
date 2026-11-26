# The Torvalds TUI — the documentation of the multi-window console

`agent-torvalds-mw.py` is the multi-window console agent: a persistent
terminal interface with a document pane, a progress pane, a telemetry
pane and a command bar.

This folder holds the documentation of that interface.

| Document | What it is |
| :--- | :--- |
| **[hotkeys.md](hotkeys.md)** | The hot-keys of the TUI — the panes that scroll, the panes that hide, and how the operator changes a binding.  **Part 1** is the operator's guide, **Part 2** is the design and the implementation. |

## The interface at a glance

```
┌──────────────────────────────────────────────────────────────────────┐
│ ⚡ TORVALDS AGENT   Model: …   Mem: … msgs   HITL: ON   Uptime: …    │  header
├──────────────────────────────────────┬───────────────────────────────┤
│                                      │ ⚡ Workflow & Tool Progress    │
│                                      │                               │
│         Markdown Document Viewer     │   Workflow Iteration: [███] 3/8│
│                                      │                               │
│         (the answer of the agent,    │   Recent Tool Tasks:          │
│          the documents, the logs)    │    ⠹ execute_shell_command     │
│                                      │      └ python scripts/ci.py   │
│                                      │    ✔ execute_shell_command     │
│                                      │      └ pytest tests/ -x       │
│                                      │                               │
├──────────────────────────────────────┤                               │
│                                      │ ⚡ Agent Telemetry & State     │
│                                      │                               │
│                                      │   Mode      On-Demand         │
│                                      │   Cache     12/40 (30%)       │
│                                      │   Prompt    8,240 tok         │
├──────────────────────────────────────┴───────────────────────────────┤
│ >>> [Enter to send]              [\stats | \tools | \keys | \exit]  │  command bar
└──────────────────────────────────────────────────────────────────────┘
```

## The document pane

The *Markdown Document Viewer* carries the answer of the agent, the
documents and the output of the commands.

**The answer is written while the operator watches it** — the workflow
streams it token by token — and **the window of the pane holds its
place** while it is written: the text the operator reads does not slide
away under him.  The subtitle of the pane says that the answer is being
written.

The operator may move the window himself — `Up`, `Down`, `Home`, `End` —
and the answer that grows does not move it back.

**When the answer is complete, the window goes to the end of it**: the
operator reads the last lines of the answer without scrolling for them.
The answer that is complete does not take him away from a paragraph he
is reading.

A **new** document — the output of `\help`, `\tools`, `\projects` —
opens at its beginning, because the operator has never seen it.

## The progress pane

The *Workflow & Tool Progress* pane carries the iteration of the run and
the **recent tool tasks** — the task that runs now is pinned on top of
the pane, and the tasks that are done are below it, the newest one
first.

Under the name of every tool is the **arguments of the call** — the
command of the shell, the path of the file, the text that is written in
it.  Every tool call shows them, and not only the call of the shell.

| the call | what the pane shows |
| :--- | :--- |
| `ls(path="/tmp")` | `/tmp` |
| `write_file(path="/tmp/a.md", content="hello")` | `path=/tmp/a.md` and `content=hello`, one argument per line |
| `execute_shell_command(command="git status")` | `git status` |

A call with **one** argument shows the value alone — the name of the
only argument would only add noise.  A call with **several** names them,
so that the operator can tell which argument is which.

A value that carries more lines than the pane shows is **folded**: the
head of it is shown, and the marker says how many lines were left out —
`… 294 more lines …`.  A body of a file is not a line of the pane, and a
pane that carries it whole is a pane that carries nothing else.

The home of the operator is hidden in every argument of every tool — the
path is shown the way a shell writes it, as `~/notes/todo.md`.

## The commands of the TUI

The TUI is a command-driven interface: every command of the classic
console works in it, and it has commands of its own.

| Command | What it does |
| :--- | :--- |
| `\help` | Every command of this session |
| `\keys` | Every key of the TUI — the keys of the command bar and the hot-keys of the panes |
| `\stats` | The request statistics — the tokens, the calls, the errors |
| `\config` | The effective configuration, and where every value came from |
| `\tools` / `\tool-list` / `\tool-select` | The tool selection |
| `\projects` / `\project-info` / `\project-status` / `\project-summary` | The projects of the workspace |
| `\chat-sessions` / `\chat-select` / `\chat-info` / `\chat-export` | The chat history |
| `\clear` | Clear the document pane |
| `\exit` | Leave the agent |

The commands are described in the
[command registry](../command_registry.py), and the `\help` screen is
rendered from it — so the screen can never name a command that does not
exist.

## Where the rest of the documentation lives

| | |
| :--- | :--- |
| The configuration file | [../configuration.md](../configuration.md) |
| The logging | [../logging.md](../logging.md) |
| The skills | [../skills.md](../skills.md) |
| The design proposals | [../proposals/](../proposals/) |
