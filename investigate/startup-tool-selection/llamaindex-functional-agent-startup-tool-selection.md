# LlamaIndex Functional Agent: Startup Tool Selection

## Brief Summary

Add a third startup mode that lets the user interactively select which tools are loaded before the agent starts. This complements the existing default **top-8 tools** mode and the `--full` mode that loads all available tools.
For more information see `agent-torvalds.py` file

The intended startup modes are:

1. **Default**: automatically load the top 8 tools.
2. **Full**: `--full` loads all available tools.
3. **Select**: `--select` displays the available tools and lets the user choose a subset before starting the agent.

Check all files `agent_*_toolkit.py` to see what tools are available.

## Goal

Give users explicit control over the tools placed into the Functional Agent context at startup. This is useful when the user already knows which capabilities will be needed and wants to avoid loading unnecessary tool schemas into the context window.

## Proposed CLI

```bash
# Existing behavior: load top 8 tools
python agent-torvalds.py

# Existing behavior: load every tool
python agent-torvalds.py --full

# New behavior: interactively select tools
python agent-torvalds.py --select
```

`--full` and `--select` should normally be mutually exclusive.

## Interactive Selection Flow

When `--select` is supplied, discover the available tools first and display them as a numbered list.

```text
Available tools example:

  [1] linux_shell
      Execute Linux shell commands.

  [2] github
      Search GitHub repositories, pull requests, and issues.

  [3] git
      Create a GitHub issue.

  [4] os
      Retrieve operating-system file information.

  [5] math
      Inspect operating-system processes.
etc.

Select tools [example: 1,2,5 or 1-3]: 1,2,5

Selected tools:
  - linux_shell
  - github_search
  - os_processes

Starting agent with 3 tools...
```

The agent is created only after the selection has been completed.

## Suggested Startup Architecture

```text
                       Agent startup
                            |
                            v
                  Discover available tools
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
       default           --full            --select
          |                 |                 |
       top 8             all tools       show tool list
          |                 |                 |
          |                 |             user selects
          |                 |                 |
          +-----------------+-----------------+
                            |
                            v
                        load tools
                            |
                            v
                     create/run agent
```

## Command-Line Parsing

One possible implementation with `argparse`:

```python
import argparse

parser = argparse.ArgumentParser()

mode = parser.add_mutually_exclusive_group()
mode.add_argument(
    "--full",
    action="store_true",
    help="Load all available tools",
)
mode.add_argument(
    "--select",
    action="store_true",
    help="Interactively select tools before starting the agent",
)

args = parser.parse_args()
```

## Tool Selection Function

Keep the selector independent from LlamaIndex so it can operate on the application's discovered tool definitions.

```python
def select_tools_interactively(available_tools):
    print("Available tools:\n")

    for index, tool in enumerate(available_tools, start=1):
        print(f"  [{index}] {tool.metadata.name}")
        print(f"      {tool.metadata.description}\n")

    raw_selection = input(
        "Select tools [example: 1,2,5 or 1-3]: "
    ).strip()

    selected_indexes = parse_tool_selection(
        raw_selection,
        maximum=len(available_tools),
    )

    return [available_tools[i - 1] for i in selected_indexes]
```

## Selection Parser

Support both individual indexes and ranges so selection remains convenient when many tools are available.

```python
def parse_tool_selection(value: str, maximum: int) -> list[int]:
    selected = set()

    for part in value.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)

            if start > end:
                raise ValueError(f"Invalid range: {part}")

            selected.update(range(start, end + 1))
        else:
            selected.add(int(part))

    invalid = [i for i in selected if i < 1 or i > maximum]
    if invalid:
        raise ValueError(f"Invalid tool indexes: {invalid}")

    return sorted(selected)
```

Examples:

```text
1,3,5       -> tools 1, 3, and 5
1-4         -> tools 1 through 4
1-3,7,10    -> tools 1, 2, 3, 7, and 10
```

## Startup Logic

Centralize the three modes in one startup decision:

```python
available_tools = load_available_tools()

if args.full:
    tools = available_tools

elif args.select:
    tools = select_tools_interactively(available_tools)

else:
    tools = select_top_tools(
        available_tools,
        limit=8,
    )

agent = create_agent(tools=tools)
run_agent(agent)
```

The exact implementation of `select_top_tools()` can remain whatever is currently used by the application.

## Recommended UX Behavior

### Show descriptions

Do not display only tool names. A short description helps the user understand what each tool does.

```text
[4] os_file_info
    Retrieve operating-system file information.
```

### Show the final selection

Before starting the agent, print the tools that will actually be loaded.

```text
Selected 3 of 24 tools:
  linux_shell
  github_search
  os_processes
```

### Handle invalid selections

Invalid input should not terminate startup immediately. Display the problem and let the user retry.

```text
Selection: 1,99

Tool 99 does not exist. Valid values are 1-24.
Please select again.
```

### Empty selection

An empty selection should be handled explicitly. Recommended behavior is to ask again instead of starting an agent with no tools.

## Optional Improvements

### Select by name

In addition to numeric selection, allow exact tool names:

```text
--select-tools linux_shell,github_search,os_processes
```

This is particularly useful for scripts and repeatable configurations because it does not require interactive input.

Example:

```bash
python agent.py --select-tools linux_shell,github_search,os_processes
```

### Tool groups / skills

When the number of tools becomes large, selection can occur at the skill level rather than the individual function level.

For example:

```text
Available skills:

[1] linux shell
    - shell_execute
    - shell_status

[2] github
    - github_search
    - github_create_issue
    - github_get_pull_request

[3] os
    - os_file_info
    - os_processes
```

The user can then select:

```text
Select skills: 1,3
```

and the application expands those skills into their corresponding tools.

This fits naturally with the separate on-demand skills design.

## Relationship to On-Demand Skills

Startup tool selection and runtime skill loading solve related but different problems:

- **Startup selection** lets the user explicitly choose a known set of tools before the agent starts.
- **Top-8 selection** automatically chooses a small initial tool set.
- **`--full`** prioritizes maximum availability over context size.
- **On-demand skills** allow the agent to discover and load additional capabilities while it is already running.

A future implementation could combine them:

```text
Start agent
   |
   +-- default top 8
   +-- --full
   +-- --select
          |
          v
   initial selected tools
          |
          v
       agent runs
          |
          v
   on-demand skill loader
          |
          v
   additional tools if needed
```

## Suggested Final CLI Contract

```text
agent.py
    Load the automatically selected top 8 tools.

agent.py --full
    Load all available tools.

agent.py --select
    Display available tools and interactively choose which ones to load.

agent.py --select-tools TOOL1,TOOL2,...
    Optional future/non-interactive mode for explicitly specifying tool names.
```

## Acceptance Criteria

The feature is complete when:

1. Running without flags preserves the current top-8 behavior.
2. `--full` preserves the current load-all behavior.
3. `--select` lists all available tools before the agent is created.
4. Each listed tool includes at least its name and short description.
5. The user can select multiple tools.
6. Individual indexes and index ranges are supported.
7. Invalid input can be corrected without restarting the application.
8. Only the selected tools are passed to the Functional Agent.
9. The final selected tool set is shown before the agent starts.
10. `--full` and `--select` cannot be used together.
