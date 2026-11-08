# How the agent carries a skill

[`docs/skills.md`](skills.md) says how to **write** a skill and where the
settings of the feature live.  This page says what the agent does with a skill
once it has one: where the tools sit, what the body of a skill costs, and when
it is paid.

Everything here was measured, not assumed.  The probe is
[`investigate/skills-in-function-agent/probe_skills_in_function_agent.py`](../investigate/skills-in-function-agent/probe_skills_in_function_agent.py)
— read-only, prints the numbers below.

---

## The two tools are always there

The agent of this project has a **tool retriever**: the tools are picked on
demand, by the meaning of the question — eight of them, out of twenty-seven.
The skill tools (`list_skills` and `activate_skill`) are **not** picked that
way.  They are always there, and the two lists are merged.

That is not a preference.  The retriever is asked **twice** per turn, with two
different questions:

| when | what it is asked |
|---|---|
| the agent starts the turn | the question of the **user** — this is where the eight tools are picked |
| the agent **calls** a tool | the **name of the tool** — this is where the tool has to be found |

The second question is the one that decides.  A retriever that matches on
meaning does not match on a name, so a tool that is only in the retriever is
**not found when it is called**.  A skill cannot be picked that way either: the
model cannot ask for a skill it cannot see.

> A skill tool has to be in `agent.tools`, not in the retriever.

That is how the agent is built — `tools = list(tools) + skill_tools` in both
orchestrators, and `create_agent_with_retriever(..., tools=skill_tools)` on
the retriever path, where the skill tools are the ones that are always there
and the retriever adds its own on top.

The cost of that is small and constant: the two schemas are sent with every
request, and the context guard counts them with the other tools.

---

## What the body of a skill costs

The body is the procedure itself.  When the model calls `activate_skill`, the
body comes back as the **result of the tool**, and the result of a tool is a
tool message in the scratchpad of the run.

The same procedure, delivered four ways — 103 tokens, on an 8192-token window:

| channel | tokens | paid |
|---|---|---|
| in the system prompt | 128 | every request, whether the run touches a skill or not |
| in the schema of a tool | 120 | every request, whether the run touches a skill or not |
| as the result of the tool | 103 | once, by the run that asks for the skill |
| in the memory | 103 | **every request after that** |

The first two are avoided by design — the catalog is not in the prompt, and the
activation tool takes a free string rather than an enum of the names.

The fourth is the one that is easy to forget.  The body is not a special kind
of message: `finalize()` writes the whole scratchpad into the memory of the
session, so the body is carried by every request that follows.

On the request that follows the activation, the body was **85% of the prompt**:

```
  the budget of the model      : 6554 tokens (window 8192, reserve 20%)
  the prompt                   : 120 tokens
  the share of the body        : 103 tokens (85%)
```

It leaves the prompt when the **context guard** drops it — as the oldest turn
of a conversation that has grown.  On the synthetic growth of the probe, that
was round 18.  It is dropped for being old, not for being a skill body.

---

## The transient channel — what it would buy

A body could be dropped as soon as the model has read it, instead of waiting
for the guard.  The probe measures that design, and it comes with a condition:

| the run | the body is in the memory of the next request |
|---|---|
| **ends** with the body — the model reads the procedure and answers | **1 time** — the same as without the channel |
| **continues** past the body — the agent keeps working | **0 times** — the body is gone |

The drop happens in the iteration *after* the model has read the body.  A run
that ends there never reaches it.

So the channel is not a free win: it pays off only when the agent keeps
working after the skill has been read, and the price of that is that the model
has to be told again what the procedure was if it is asked again.

**It is not shipped.**  It is measured, not implemented — the reasoning is in
[the report](../investigate/skills-in-function-agent/INVESTIGATION_REPORT.md).

---

## What this means for the skill you write

* **Write the body for one turn.**  It is read once, by the run that asked for
  it, and it is paid again by every request that follows until the guard drops
  it.  A body that is written to be read once is the right shape; a body that
  is written to be re-read is a document, not a skill.
* **Keep the body under the limit.**  `skills.body_token_limit` cuts it to a
  token limit and marks the cut, so the model knows it is reading a part of
  the procedure.
* **The description is the line that is read every time.**  The description is
  in the catalog, and the catalog is paid by every request — when it is in the
  prompt at all.

---

## See also

* [`docs/skills.md`](skills.md) — how to write a skill, and the four settings
* [`investigate/skills-in-function-agent/INVESTIGATION_REPORT.md`](../investigate/skills-in-function-agent/INVESTIGATION_REPORT.md) —
  the investigation, with the probe output
* [`components/skills_tools.py`](../components/skills_tools.py) — the two tools
* [`components/hitl_agent.py`](../components/hitl_agent.py) — the agent that
  assembles the prompt and trims the scratchpad
