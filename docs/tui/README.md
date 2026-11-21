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
│          the documents, the logs)    │    ✔ execute_shell_command     │
│                                      │      └ python scripts/ci.py   │
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
