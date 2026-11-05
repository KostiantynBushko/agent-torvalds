# Investigation Report: what the Agent Skills feature costs in the prompt

**Status:** measured, designed, implemented and verified.
**Branch:** `feature/agent-skills`
**Probe:** [`probe_skill_costs.py`](probe_skill_costs.py) — read-only, prints the
numbers below.
**Model of the operator:** `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (local,
Ollama), an 8192-token context window.

---

## 1. The question

The **Agent Skills** format is progressive disclosure in three tiers:

1. the **catalog** — the names and the descriptions of the skills, in the prompt;
2. the **activation tool** — the schema the model calls to ask for one of them;
3. the **body** — the procedure itself, loaded when the skill is activated.

Tiers 2 and 3 are paid only by the runs that use them.  **Tier 1 is paid by
every request**, whether the run touches a skill or not, and it grows with every
skill the operator writes.

The question this report answers is therefore not "can the feature be built" —
it can — but:

> What does the feature cost the agent on the window it actually has, and what
> is the cheapest way to build it that keeps the cost off the prompt?

---

## 2. The measurement

`probe_skill_costs.py` measures the three quantities with the tokenizer the
agent itself uses (`components.tokens.get_tokenizer`), so the numbers are
the numbers the token limit is enforced with.

### 2.1 The catalog — 45 tokens per skill

```
  skills   tokens    per skill
       1       53           53
       5      233           46
      10      458           45
      20      908           45
      50     2258           45
```

The catalog is a **list**, so it costs what a list costs: 45 tokens per skill,
every request, forever.  The XML shape of the specification is not the reason —
the tags are about ten tokens of the forty-five.  The descriptions are long
because a description has to tell the model *when* to use the skill, and that
takes a sentence.

### 2.2 The activation tool — an enum that grows

```
 names in the enum   tokens
                 1       80
                 5      100
                10      125
                20      175
                50      325
```

The schema of the activation tool carries the names of the skills as an enum.
The schema is sent with every request, so the enum is paid by every request
too — about six tokens per skill.

### 2.3 Against the budget

The budget is the one the context guard leaves (`components/context_guard.py`):

```
context window                : 8192
budget (context_budget)       : 6554      (the window minus 20% for the answer)
tool schemas of the 27 tools  : 3211      (measured — see the loop investigation)
left for the conversation     : 3343
```

With the catalog of twenty skills in the prompt:

```
catalog of 20 skills          : 908
activation tool schema        : 175
the fixed cost of the feature : 1083
share of the budget           : 16.5%
left for the conversation     : 2260
```

**A third of the room the conversation had left is gone**, for a feature that
most requests never touch.  And the number grows: fifty skills cost 2583 tokens,
which is 39% of the budget.

---

## 3. The root cause

There is no bug in the arithmetic.  The design is the defect.

The catalog is put in the **system prompt** because that is where a catalog
belongs — for a model that reads the prompt once per session.  This agent sends
the prompt **with every request**, and on a local model every request costs
minutes.  The catalog is therefore paid 50 times for a request that needs one
skill, and 50 times for the requests that need none.

The same pattern is already solved in this repository for the **tools**: the
tool retriever (`agent_tool_retriever.py`) loads the schemas of eight tools per
query instead of all twenty-seven, because the schemas cost 3211 tokens.  The
skills are the same problem one level up — a skill is a tool whose schema is a
procedure.

---

## 4. The fix

**The catalog is fetched on demand.  The prompt carries one line.**

| | before | after |
|---|---|---|
| the prompt | the whole catalog | one line (50 tokens) |
| the activation tool | an enum of the names | a free string |
| the catalog | in the prompt | a tool *result* |
| the fixed cost | 45 tokens **per skill** | 220 tokens, **whatever the number** |

Three parts:

1. **The catalog is a tool result.**  `list_skills` returns the catalog when
   the model asks for it.  It costs the runs that use a skill, and it lands in
   the conversation, where the context guard drops it once it grows old — the
   guard already knows how to drop the oldest turns.

2. **The activation tool takes a free string.**  The names are not an enum:
   an enum is paid on every request and grows with every skill.  The model
   gets the names from `list_skills`.

3. **The prompt carries one line, and only when there is a skill.**  The line
   is what makes the feature reachable for a model that would otherwise never
   call `list_skills`.  It costs the same whether there are two skills or two
   hundred.

The measured result:

```
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

The conversation gets **3123 tokens instead of 2260** — 38% more room — and
the number does not change when the operator writes another skill.

### 4.1 The three defects that are fixed with it

| | defect | why it matters |
|---|---|---|
| **D1** | the catalog is in the prompt | 45 tokens per skill, paid on every request, growing forever |
| **D2** | the activation schema carries an enum | about six tokens per skill, paid on every request, growing forever |
| **D3** | the body of a skill is loaded without a limit | one long skill can fill the window on its own |

**D3** is fixed by `cap_body()`: the body is cut to
`skills.body_token_limit` tokens (2000 by default) and the cut is marked, so
that the model knows it is reading a part of the procedure.

The cut has a subtlety that the context guard had already learned
(`investigate/agent-loop-context-guard/`): **the count of the result is not the
sum of the counts of its parts.**  The seam between the body and the marker
may merge two tokens into one, and a body that fits exactly pushes the result
over the limit.  `cap_body()` therefore measures the *result* — the body with
the marker attached — and cuts until the whole thing fits.

---

## 5. Where the skills live

A skill is a directory with one file in it:

```
<root>/<name>/SKILL.md
```

```markdown
---
name: deploy
description: Deploy this project to the remote host over SSH.
---

# Deploy

1. Check that the tests pass.
2. Build the image.
```

Two roots, in this order:

1. `~/.config/torvalds/skills` — the skills of the operator, next to the
   configuration file;
2. `<project>/skills` — the skills of the project.

A skill of the project **overrides** a skill of the operator with the same name:
the project is the more specific context, and a procedure that is part of the
project is the one that describes the project.

---

## 6. Verification

```console
$ .venv/bin/python -m pytest tests/test_skills.py -q
40 passed

$ .venv/bin/python investigate/agent-skills/probe_skill_costs.py
...
the fixed cost, 20 skills      : 220
the fixed cost before the fix  : 1083
```

The full suite, against the committed CI baseline
(`scripts/ci_test_gate.py`):

| | failed | error | passed |
|---|---|---|---|
| base (`master`, `547e8ed`) | 39 | 1 | 2768 |
| this branch | 39 | 1 | 2807 |

**No new failure.**  The failures are the known ones (the git toolkit against
the current pygit2 API, the math toolkit's error contracts, the HITL runtime
toggle, …); they are listed in `tests/ci_baseline.txt`, and the gate counts
them as 40 (39 failures and 1 error) on both sides.  The branch adds 40
passing tests and breaks nothing.

The invariant the tests guard is the one this report is about:

```python
def test_the_fixed_cost_is_the_same_for_one_and_for_fifty_skills(self):
    costs = [self._fixed_cost(count) for count in (1, 5, 20, 50)]
    self.assertEqual(len(set(costs)), 1)
```

A test that has never failed proves nothing, so the test that measures the
rejected design sits next to it:

```python
def test_the_catalog_in_the_prompt_would_have_grown(self):
```

---

## 7. What is *not* in this change, and why

* **The catalog is not in the prompt by default.**  It can be put there with
  `skills.catalog_in_prompt = true`, and the compact form is 26 tokens per
  skill instead of 45.  It is off by default because the cost is paid by
  every request, and the operator can measure both (the probe prints both).

* **The bodies are not in the budget.**  A body is loaded when a skill is
  activated, and it costs its own tokens at that moment — it is a turn of the
  conversation, and the context guard trims it like any other.

* **The skills are not retrieved semantically.**  The tool retriever uses the
  embedding model to pick the tools of a query.  The catalog of the skills is
  small, and a semantic search over it would cost a round-trip to the
  embedding server for a list that fits in one tool result.  A skill is chosen
  by *name*, and the model chooses the name.

* **The tools of the skill are not the tools of the retriever.**  The skill
  tools are always present — the model has to be able to ask for a skill it
  cannot see otherwise — and the retriever adds its own on top.

---

## 8. The recommendation to the operator

The feature is off the prompt by default, and the room it gives back is worth
more than the round-trip it costs on the runs that use a skill.

If the operator prefers the discoverability of a catalog that is always in the
prompt, `skills.catalog_in_prompt = true` puts it there — in the compact form,
at 26 tokens per skill.  On the window of the operator's model that is 520
tokens for twenty skills, against the 908 of the XML shape: still a third of
the room, and still paid by every request.

The recommendation is to leave it off, and to let the model ask.
