# Proposal: the Agent Skills feature, without the prompt tax

**Branch:** `feature/agent-skills`
**Investigation:** [`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md)
**Probe:** [`probe_skill_costs.py`](probe_skill_costs.py)

---

## The problem in one paragraph

The **Agent Skills** format is progressive disclosure: the prompt carries a
catalog of the skills, the model asks for the body of the one it needs, and the
body is loaded at that moment.  On the window of the operator's model
(8192 tokens) the catalog of twenty skills costs **908 tokens** and the
activation schema another **175** — a fixed **1083 tokens, 16.5% of the prompt
budget**, paid on *every* request whether the run touches a skill or not, and
growing by 45 tokens for every skill the operator writes.  A third of the room
the conversation had left (3343 → 2260 tokens) was gone for a feature most
requests never use.

## The fix in one paragraph

The catalog is **fetched on demand**.  The prompt carries **one line** — and
only when there is at least one skill — the activation tool takes a **free
string** instead of an enum of the names, and the catalog comes back as a
*tool result* when the model calls `list_skills`.  The fixed cost of the
feature is therefore **220 tokens, whatever the number of skills** (3.4% of the
budget), and the conversation gets 3123 tokens instead of 2260.  The body of a
skill is cut to a token limit, so that one long procedure cannot fill the
window on its own.

---

## What changes

### 1. `components/skills.py` (new)

The library half — what a skill is, where it lives, how it is read.

| change | why |
|---|---|
| `Skill` — name, description, path, body, scope | the skill of the file, in one value |
| `parse_frontmatter()` | the subset of YAML the skill format needs; a folded description is joined |
| `discover_skills()` | reads the roots; a **later root wins**, so the skill of the project overrides the one of the operator |
| `default_skill_roots()` | `~/.config/torvalds/skills` and `<project>/skills` |
| `parse_skill_dirs()` | the `skills.dirs` setting, split on the separator of the platform |
| `render_catalog()` | **one line per skill** — the XML shape of the specification costs ten tokens per skill in tags alone |
| `render_prompt_section()` | the whole of the tier 1: **one line**, plus the catalog when the operator asks for it |
| `truncate_to_tokens()` | the cut, by binary search over the character length |
| `cap_body()` | the cut **with the marker attached** — the count of the result is not the sum of the counts of its parts |

### 2. `components/skills_tools.py` (new)

The agent-facing half — the two tools.

| change | why |
|---|---|
| `list_skills` | the catalog, as a tool result: it costs the runs that ask for it, and the guard drops it when it grows old |
| `activate_skill` | the body of one skill, cut to the limit |
| the name is a **free string** | an enum is paid on every request and grows with every skill |
| **no tools at all** when there is no skill | the feature costs nothing on a machine that does not use it |
| `build_skills()` | the one call the orchestrators make: the tools, the text for the prompt, and the skills |

### 3. `components/config.py`

| setting | default | what it does |
|---|---|---|
| `skills.enabled` | `true` | the feature as a whole |
| `skills.dirs` | *(the defaults)* | where the skills are looked for |
| `skills.catalog_in_prompt` | `false` | the catalog in the prompt, in the compact form |
| `skills.body_token_limit` | `2000` | how many tokens the body of a skill may take |

### 4. `agent-torvalds.py` and `agent-torvalds-mw.py`

| change | why |
|---|---|
| the skills are built in `create_agent()` | one place, both orchestrators |
| the prompt section is appended to the system prompt | the one line that makes the feature reachable |
| the skill tools are **always** there | the model cannot ask for a skill it cannot see |
| `create_agent_with_retriever()` takes `tools` | the retriever adds its tools on top of the ones that are always there |

### 5. `agent_tool_retriever.py`

`create_agent_with_retriever()` gained a `tools` argument.  The base agent
merges the static tools with the retrieved ones, so the skill tools survive the
retrieval.

### 6. Tests

* `tests/test_skills.py` — 40 tests: the frontmatter, the discovery, the
  catalog, the prompt section, the cut of the body, the two tools, the wiring,
  and **the cost invariant**.

---

## Verification

```console
$ .venv/bin/python -m pytest tests/test_skills.py -q
40 passed

$ .venv/bin/python investigate/agent-skills/probe_skill_costs.py
...
4. The fix — the catalog is fetched on demand, not in the prompt

  skills   prompt   schemas    fixed
       1       50       170      220
       5       50       170      220
      10       50       170      220
      20       50       170      220
      50       50       170      220

the fixed cost, 20 skills      : 220
the fixed cost before the fix  : 1083
what the fix saves             : 863
share of the budget            : 3.4%
left for the conversation      : 3123
```

The full suite, base commit `547e8ed` against this branch:

| | failed | error | passed |
|---|---|---|---|
| base | 39 | 1 | 2768 |
| branch | 39 | 1 | 2807 |

The **failure sets are identical** — the CI gate reports *no new failure*, and
the 40 known failures (39 and 1 error) are the ones in `tests/ci_baseline.txt`.

The invariant the tests guard is the one this proposal is about:

```python
def test_the_fixed_cost_is_the_same_for_one_and_for_fifty_skills(self):
    costs = [self._fixed_cost(count) for count in (1, 5, 20, 50)]
    self.assertEqual(len(set(costs)), 1)
```

---

## What is *not* in this change, and why

* **The catalog is not in the prompt by default.**  It can be put there with
  `skills.catalog_in_prompt = true`, in the compact form (26 tokens per skill
  instead of 45).  It is off by default because it is paid by every request.
* **The bodies are not in the budget.**  A body is a turn of the conversation;
  the context guard trims it like any other.
* **The skills are not retrieved semantically.**  The catalog fits in one tool
  result, and a semantic search would cost a round-trip to the embedding
  server for it.  A skill is chosen by name, and the model chooses the name.
* **The skills are not tools of the retriever.**  They are always present; the
  retriever adds its own on top.

---

## How a skill is written

```markdown
---
name: deploy
description: Deploy this project to the remote host over SSH.
---

# Deploy

1. Check that the tests pass.
2. Build the image.
3. Push it, then restart the service.
```

It goes into `~/.config/torvalds/skills/deploy/SKILL.md` (the skills of the
operator) or into `<project>/skills/deploy/SKILL.md` (the skills of the
project).

---

## Next step

The work is on the branch `feature/agent-skills`.  It is not committed: the
operator approves the commit and the pull request.
