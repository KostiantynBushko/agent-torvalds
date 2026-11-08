# Skills — procedures the agent loads on demand

A **skill** is a procedure that is too long to keep in the prompt and too rare
to be worth a tool: *how this project is deployed*, *the checklist before a
release*, *the way this database is migrated*.  The agent reads the skill when
the task calls for it, and does not carry it in the prompt the rest of the
time.

The agent starts with no skill at all.  The feature costs **nothing** until
you write one.

---

## The format

A skill is a directory with one file in it:

```
<root>/<name>/SKILL.md
```

The file opens with a **frontmatter** block and carries the procedure in its
body:

```markdown
---
name: deploy
description: Deploy this project to the remote host over SSH.
---

# Deploy

1. Check that the tests pass: `pytest -q`.
2. Build the image: `docker build -t app .`.
3. Push it and restart the service on the host.
```

| field | what it is |
|---|---|
| `name` | the name the model uses to ask for the skill.  It defaults to the name of the directory |
| `description` | one line, telling the model **when** the skill is worth loading.  This is the line the model reads first — write it for that |

The body is the procedure itself.  Write it as instructions to the agent, not
as a document for a human.

---

## Where the skills live

Two roots, in this order:

| root | what it holds |
|---|---|
| `~/.config/torvalds/skills` | your own skills, next to the configuration file |
| `<project>/skills` | the skills of the project the agent works in |

A skill of the project **overrides** a skill of yours with the same name: the
project is the more specific context, and a procedure that is part of the
project is the one that describes it.

The roots can be changed with the **option** `skills.dirs` of the
`[skills]` section of the configuration file — a list of directories
separated by a colon:

```toml
[skills]
dirs = "~/.config/torvalds/skills:./skills:/opt/shared/skills"
```

---

## The skills of this project

This repository carries four skills of its own, under `skills/`.  They are
the procedures of this project — the ones that are too long to keep in the
prompt and too rare to be worth a tool:

| skill | what it is for |
|---|---|
| `run-tests` | how to run the suite, and how to read a run that ends in "39 failed" |
| `release` | the release checklist, and the two files that declare the version |
| `investigate` | the shape of an investigation folder, and the rule that the probe is read-only |
| `add-toolkit` | the layout of a toolkit, and the four steps nobody skips |

They are found by the second default root, so they are loaded whenever the
agent works in this repository.  A skill of the operator with the same name
is overridden by them: the procedure of the project is the one that
describes the project.

`tests/test_project_skills.py` guards them.  The feature skips a skill that
cannot be read — the right behaviour for a skill the operator writes on the
machine, but it makes a broken skill in the **repository** invisible.  The
tests are the eyes for that case.

---

## Managing the skills

A skill is a **file**, not a command: nothing registers it and nothing
enables it.  It is there, and the agent finds it when it starts.

| | what |
|---|---|
| **add** | a folder with a `SKILL.md` in it, under one of the roots |
| **change** | edit the `SKILL.md` — it is read again at the next start |
| **remove** | delete the folder |
| **override** | a skill of the project replaces a skill of the operator with the same name |

**What the agent found** is announced when it starts:

```
Skills: 4 available (the catalog is loaded on demand): add-toolkit, investigate, release, run-tests
```

A skill that is missing from that line is not under a root the agent
reads — check the roots with the `\config` command:
`\config skills.dirs`.

**A broken skill is skipped, not fatal.**  A `SKILL.md` that cannot be
read, or one without a name, is left out and the agent boots anyway.  The
reason is in the log.

**Without the agent**, the skills of this machine can be listed from a
shell — the same discovery, the same roots, without a model and without a
token:

```console
$ .venv/bin/python -c "from components.skills import discover_skills, default_skill_roots; print([s.name for s in discover_skills(default_skill_roots())])"
['add-toolkit', 'investigate', 'release', 'run-tests']
```

The second root is the `skills` folder of the directory the command runs
in, so the command belongs to the root of the project.

---

## How the agent uses them

The agent gets two tools:

| tool | what it does |
|---|---|
| `list_skills` | returns the catalog — the name of every skill and what it is for |
| `activate_skill` | returns the body of one skill, cut to the token limit |

The **catalog is not in the prompt**.  It is fetched when the model asks for
it, so the prompt does not grow with the number of skills you write.  The
prompt carries one line, and only when there is at least one skill:

```
### Skills

Procedures for tasks that need one are available on this machine.
Call `list_skills` to see what there is, and `activate_skill` to load the
instructions of the one you need, before you start the task it covers.
```

The measurement is in
[`investigate/agent-skills/INVESTIGATION_REPORT.md`](../investigate/agent-skills/INVESTIGATION_REPORT.md):
a catalog of twenty skills in the prompt costs **1083 tokens on every
request** — 16.5% of the prompt budget of an 8192-token window.  As it is
implemented, the feature costs **220 tokens**, whether you have one skill or
fifty.

---

## The settings — four options in the configuration file

The feature is steered by **four options**.  They live in the
**`[skills]` section** of the configuration file —
`~/.config/torvalds/config.toml`:

```toml
[skills]
enabled = true
dirs = "~/.config/torvalds/skills:./skills"
catalog_in_prompt = false
body_token_limit = 2000
```

**They are options in a file, not commands.**  There is no `skills`
command to type at a shell, no `skills enable` to run, and nothing to
register: the four names below are **lines in the `[skills]` section of
the configuration file**.

One option, four ways of naming it — only the last one is a command:

| | `body_token_limit` |
|---|---|
| **the option in the file** | `body_token_limit` — the line inside `[skills]` |
| **the dotted name** | `skills.body_token_limit` — `skills` is the section, `body_token_limit` is the option inside it |
| **the environment variable** | `TORVALDS_SKILLS_BODY_TOKEN_LIMIT` — the layer above the file |
| **the command** | `\config skills.body_token_limit 4000` — the agent's way of writing the option into the file |

The dotted name is the way the option is **named** everywhere else: it is
the name the `\config` command prints it under, and the name it writes it
with.  The command is a convenience — the file itself is what the agent
reads.

| option (the dotted name) | default | what it does |
|---|---|---|
| `skills.enabled` | `true` | the feature as a whole |
| `skills.dirs` | *(the defaults)* | where the skills are looked for |
| `skills.catalog_in_prompt` | `false` | put the catalog in the prompt after all |
| `skills.body_token_limit` | `2000` | how many tokens the body of a skill may take |

### How to change them

Three layers, and the one that is highest wins:

| layer | how | wins over |
|---|---|---|
| **the environment variable** | `export TORVALDS_SKILLS_BODY_TOKEN_LIMIT=4000` | the file |
| **the configuration file** | edit the option in the `[skills]` section of `~/.config/torvalds/config.toml` | the default |
| **the built-in default** | nothing to do | — |

Every option has its environment variable:

```bash
export TORVALDS_SKILLS_ENABLED=true
export TORVALDS_SKILLS_DIRS="$HOME/.config/torvalds/skills:./skills"
export TORVALDS_SKILLS_CATALOG_IN_PROMPT=false
export TORVALDS_SKILLS_BODY_TOKEN_LIMIT=2000
```

And there is **one command of the agent** that writes the file, from
inside the chat — `\config`.  It belongs to the agent, not to the skills,
and it writes **any** option of the configuration file, not only these
four:

```
>>> \config skills.body_token_limit 4000
skills.body_token_limit is now 4000
  written to ~/.config/torvalds/config.toml
```

`\config` on its own shows every setting with the value that won and the
layer it came from; `\config skills.body_token_limit` shows that one in
detail.  The command works in the classic REPL and in the multi-window
TUI.

### When a change takes effect

The options of the skills are read **when the agent starts**, together
with the model and the logging.  A change therefore applies on the **next
start** — the `\config` write is persistent, and the restart is what
picks it up.

### The four recipes

Every recipe is **an option in the `[skills]` section** of the
configuration file.  The last column is the `\config` command that writes
it — the same change, typed into the chat.

| I want to… | the option | the line in the file | the command |
|---|---|---|---|
| turn the feature off | `skills.enabled` | `enabled = false` | `\config skills.enabled false` |
| look in my own folder only | `skills.dirs` | `dirs = "~/.config/torvalds/skills"` | `\config skills.dirs ~/.config/torvalds/skills` |
| let the model see the catalog without a tool call | `skills.catalog_in_prompt` | `catalog_in_prompt = true` | `\config skills.catalog_in_prompt true` |
| let a long procedure through | `skills.body_token_limit` | `body_token_limit = 6000` | `\config skills.body_token_limit 6000` |

The value of `skills.dirs` is a list of folders separated by a colon —
`~/.config/torvalds/skills:./skills` — and the **last** one wins when two
roots carry a skill with the same name.

### `skills.catalog_in_prompt`

An option of the `[skills]` section — a line in the configuration file:

```toml
[skills]
catalog_in_prompt = false
```

Off by default, and the reason is the measurement above: the catalog is paid
by **every** request, whether the run touches a skill or not.

Turn it on when you would rather have the discoverability than the room —
a model that has the catalog in front of it does not have to ask for it.  The
catalog is then in the **compact** form (one line per skill, 26 tokens per
skill instead of the 45 of the XML shape), and the cost is still paid by every
request.

### `skills.body_token_limit`

An option of the `[skills]` section — a line in the configuration file:

```toml
[skills]
body_token_limit = 2000
```

The body of a skill is loaded into the conversation, so it has to have a
limit: one long procedure would otherwise fill the window on its own.  A body
that is too long is cut, and the cut is marked, so the model knows it is
reading a part of the procedure:

```
[the skill was cut here — it is longer than the limit; the full text is in
the file named above]
```

The full text is always on disk, and the path of the file is in the message
the model receives.

---

## Writing a skill that works

The description is what the model reads when it decides.  Say **when** the
skill applies, not only what it does:

| weak | strong |
|---|---|
| `description: Deployment` | `description: Deploy this project to the remote host over SSH. Use it when the user asks to publish, release or ship.` |

The body is instructions to the agent.  Short steps, the commands to run, and
the things that must not be skipped:

```markdown
---
name: release
description: Prepare and publish a release of this project. Use it when the
  user asks to release, publish or ship a version.
---

# Release

1. Run the tests: `pytest -q`.  Do not go on when they fail.
2. Update the version in `pyproject.toml` and in `CHANGELOG.md`.
3. Commit: `git commit -am "release <version>"`.  **Never push** — the
   operator pushes.
```

---

## The tools of the agent, and the skills

The skills are **not** the tool retriever.  The retriever picks the tools
that match the query (eight of them, out of twenty-seven); the skills are
always there, because the model cannot ask for a skill it cannot see.  The two
lists are merged, and the cost of the skill tools is counted with the other
tool schemas by the context guard.

Why the skill tools cannot be picked by the retriever, and what the body of a
skill costs once it is loaded, are in
[`docs/skills-in-the-agent.md`](skills-in-the-agent.md).

---

## See also

* [`docs/skills-in-the-agent.md`](skills-in-the-agent.md) — how the agent carries a skill, and what its body costs
* [`investigate/agent-skills/INVESTIGATION_REPORT.md`](../investigate/agent-skills/INVESTIGATION_REPORT.md) — the measurement, and the design
* [`investigate/agent-skills/PROPOSAL.md`](../investigate/agent-skills/PROPOSAL.md) — what the change does
* [`investigate/skills-in-function-agent/INVESTIGATION_REPORT.md`](../investigate/skills-in-function-agent/INVESTIGATION_REPORT.md) — where a skill has to live, and what it costs
* [`components/skills.py`](../components/skills.py) — the library half
* [`components/skills_tools.py`](../components/skills_tools.py) — the two tools
