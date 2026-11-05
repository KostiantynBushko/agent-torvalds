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

The roots can be changed with the setting `skills.dirs` — a list of
directories separated by a colon:

```toml
[skills]
dirs = "~/.config/torvalds/skills:./skills:/opt/shared/skills"
```

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

## The settings

| setting | default | what it does |
|---|---|---|
| `skills.enabled` | `true` | the feature as a whole |
| `skills.dirs` | *(the defaults)* | where the skills are looked for |
| `skills.catalog_in_prompt` | `false` | put the catalog in the prompt after all |
| `skills.body_token_limit` | `2000` | how many tokens the body of a skill may take |

Every setting has an environment variable:

```bash
export TORVALDS_SKILLS_ENABLED=true
export TORVALDS_SKILLS_DIRS="$HOME/.config/torvalds/skills:./skills"
export TORVALDS_SKILLS_CATALOG_IN_PROMPT=false
export TORVALDS_SKILLS_BODY_TOKEN_LIMIT=2000
```

### `skills.catalog_in_prompt`

Off by default, and the reason is the measurement above: the catalog is paid
by **every** request, whether the run touches a skill or not.

Turn it on when you would rather have the discoverability than the room —
a model that has the catalog in front of it does not have to ask for it.  The
catalog is then in the **compact** form (one line per skill, 26 tokens per
skill instead of the 45 of the XML shape), and the cost is still paid by every
request.

### `skills.body_token_limit`

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

---

## See also

* [`investigate/agent-skills/INVESTIGATION_REPORT.md`](../investigate/agent-skills/INVESTIGATION_REPORT.md) — the measurement, and the design
* [`investigate/agent-skills/PROPOSAL.md`](../investigate/agent-skills/PROPOSAL.md) — what the change does
* [`components/skills.py`](../components/skills.py) — the library half
* [`components/skills_tools.py`](../components/skills_tools.py) — the two tools
