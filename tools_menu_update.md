# The startup tool menu

The tool menu is what `--select` shows at startup, and what `\tools` and
`\tool-select` show in the TUI.  The tools are grouped by the
`Category:` tag in their description, and **each category gets its own
number**, so a whole group can be loaded or skipped at once.

This file is the human-readable map of that menu.  It is regenerated from
the live menu, not written by hand — a category that does not exist, or a
count that is wrong, is worse than no file at all.

**155 tools in 12 categories.**

| # | Category | Tools | What the category does |
|---:|---|---:|---|
| 1 | **Mathematics** | 14 | arithmetic, compute, trigonometry, logarithms |
| 2 | **Version Control** | 40 | get, repository, staging, commit, inspect, changelog, remote, branching, cleanup, merge, config, collaborate, update |
| 3 | **Operating System** | 11 | inspect, create, delete, move/copy, read/write |
| 4 | **Database** | 2 | query |
| 5 | **System / Package Management** | 10 | discover, inspect, install, auth, reset, config |
| 6 | **Infrastructure** | 11 | cache, reset, inspect, update, track, session |
| 7 | **Data / Excel** | 9 | read/write, inspect, modify, move/copy, format, create |
| 8 | **Project Management** | 19 | scan, inspect, load, update, delete, rename, config, get, check, prompt |
| 9 | **Data / Analysis** | 13 | load, compute, filter, group, aggregate, inspect, export, transform |
| 10 | **Network** | 8 | discover, diagnose, execute, inspect, backup |
| 11 | **Security** | 12 | discover, inspect, diagnose, execute |
| 12 | **System** | 6 | execute, parse, inspect |

## Regenerating it

The menu is behaviour: the retriever matches against the tool
descriptions, the model reads them, and the startup menu groups them by
the category in their description.  A change to a description is a change
to the menu.

The categories are pinned by the menu's own suite:

```bash
python -m pytest tests/test_tool_selection_menu.py -q
```

It holds the **Network** and **Security** categories to their exact
membership, checks that every tool is in exactly one category and that
no tool is uncategorised, and checks that the menu and the retriever
agree.

The whole menu can be dumped with
`investigate/data-analysis-toolkit-module/dump_tool_menu.py` — one line
per tool, the name, the category and the description, tab-separated, in
the order of the menu.  Diffing two dumps is how a refactoring proves it
did not change the menu by a single character.

## A note on the history

This file used to describe a menu of **six** categories — "Development"
and "Networking" among them — with counts of 18, 10, 6, 7, 12 and 4.
None of that matched the agent: there is no *Development* category and no
*Networking* one, and the counts were wrong.  The file had gone stale
and nothing noticed, because a hand-written menu table is not checked
against anything.

The table above was generated from the live menu on 2026-10-28, with
**155 tools**.  The per-toolkit counts are pinned by each toolkit's own
layout contract (`toolkits/*/tests/test_package_layout.py`); the
categories are pinned by `tests/test_tool_selection_menu.py`.
