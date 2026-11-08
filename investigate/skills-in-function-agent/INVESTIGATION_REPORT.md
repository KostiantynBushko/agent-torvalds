# Investigation Report: where a skill has to live in the agent, and what its body costs

**Status:** measured. The design of the shipped agent is confirmed; nothing in it had
to change.
**Branch:** `feature/agent-skills`
**Probe:** [`probe_skills_in_function_agent.py`](probe_skills_in_function_agent.py) —
read-only, prints the numbers below.
**Model of the operator:** local, Ollama, an 8192-token context window.

---

## 1. The question

A skill is loaded by a tool.  The agent of this project also has a **tool
retriever**: the tools are picked on demand, eight out of twenty-seven, by the
meaning of the question of the user.  The skill tools are not picked that way —
they are always there, and the two lists are merged.

That decision was written down in a commit message, and the reasoning behind it
was never measured.  Two questions came out of it:

> **Where does a skill tool have to live** — in `agent.tools`, or in the
> retriever?  The retriever picks tools by meaning; a skill is chosen by name.
> Does the retriever find a tool when the tool is *called*?

> **What does the body of a skill cost** once it is loaded?  It is a tool result,
> it lands in the scratchpad, and the scratchpad is written into the memory.  Is
> the body paid again by every request that follows?

---

## 2. The measurement

`probe_skills_in_function_agent.py` measures both against the installed
`llama-index-core` (`0.14.25`) and the tokenizer of the agent itself
(`components.tokens.get_tokenizer`), so the numbers are the numbers the token
limit is enforced with.

### 2.1 The question the retriever is asked

The retriever is asked **twice**, with two different questions:

```
The retriever was asked:
  1. 'deploy the service to the remote host'
  2. 'activate_skill'
  3. 'deploy the service to the remote host'

  run_agent_step() asks with the question of the user:
      get_tools(user_msg_str)
  call_tool() asks with the NAME OF THE TOOL:
      get_tools(ev.tool_name)
```

`run_agent_step()` asks the retriever with the question of the user — that is
where the eight tools are picked.  But `call_tool()` asks it **again**, with the
name of the tool that is being called, and that is the question that decides
whether the tool is found at all.

A retriever that matches on meaning does not match on a name.

> **=> a skill tool has to be in `agent.tools`, not in the retriever.**

### 2.2 Where the body of a skill ends up

The lifecycle of one turn that activates a skill:

```
-- the scratchpad at every iteration --
  iteration 1:
      (empty)
  iteration 2:
      assistant       0 chars  ''  [calls: activate_skill]
      tool          353 chars  'Skill: deploy  # Deploy  1. Check that the tests pass: `.venv/bin...'  [tool_call_id=call-1]

-- the memory after the turn (what the next request carries) --
      user           37 chars  'deploy the service to the remote host'
      assistant       0 chars  ''  [calls: activate_skill]
      tool          353 chars  'Skill: deploy  # Deploy  1. Check that the tests pass: `.venv/bin...'  [tool_call_id=call-1]
      assistant      24 chars  'The service is deployed.'

  the body of the skill      : 103 tokens
  the memory after the turn  : 4 messages
```

The tool result is a **tool message** in the scratchpad, and `finalize()` puts
the whole scratchpad into the memory:

```
    await memory.aput_messages(scratchpad)
```

So the body of the skill is in the memory of the next request, and it is paid
again by every request that follows.

```
-- the prompt of the next request --
  the budget of the model      : 6554 tokens (window 8192, reserve 20%)
  the prompt                   : 120 tokens
  the share of the body        : 103 tokens (85%)

-- the guard, on a conversation that grows --
  the body of the skill is dropped at round 18 (the window keeps 36 of 40 messages)
```

The body is **85% of the prompt** of the request that follows the activation.
It leaves the prompt only when the context guard drops it as the *oldest* turn
of a conversation that has grown — round 18, on the synthetic growth of the
probe.  It is not dropped because it is a skill body; it is dropped because it
got old.

### 2.3 The price of each channel

The same procedure, delivered four ways:

```
  the procedure is 103 tokens long

  in the system prompt (every request)                128 tokens
  in the schema of a tool (every request)             120 tokens
  as the result of the tool (this request)            103 tokens
  in the memory (every request after)                 103 tokens
```

The first two are paid by every request, whether the run touches a skill or
not.  The third is paid once, by the run that asks for the skill.  The fourth
is the one that is easy to forget.

### 2.4 The transient channel — a candidate, and its condition

The probe also measures a **transient** channel: the body is marked when the
tool result lands in the scratchpad, and it is dropped from the scratchpad as
soon as the model has read it, so that `finalize()` never writes it into the
memory.

```
-- the persistent channel (the tool result stays) --
  the body is in the memory of the next request : 1 times
  the memory holds 4 messages

-- the transient channel, in a run that ENDS with the body --
  the iterations that carried the body : [False, True]
  the bodies dropped from the scratchpad : 0
  the body is in the memory of the next request : 1 times
  the memory holds 4 messages

-- the transient channel, in a run that CONTINUES past the body --
  the iterations that carried the body : [False, True, False]
  the bodies dropped from the scratchpad : 2
  the body is in the memory of the next request : 0 times
  the memory holds 4 messages
```

The condition is the whole result:

* a run that **ends** with the body — the model reads the procedure and
  answers — is exactly as expensive as the persistent channel.  The drop
  happens in the *next* iteration, and there is no next iteration.
* a run that **continues** past the body drops it, and the memory of the next
  request does not carry it at all.

So the transient channel is not a free win: it pays off only when the agent
keeps working after the skill has been read.  The price of that is that the
model has to be told again what the procedure was if it is asked again.

---

## 3. The root cause

Two properties of `FunctionAgent` decide everything above.

**The retriever is asked with the name of the tool.**  `call_tool()` calls
`get_tools(ev.tool_name)`, and `get_tools()` asks the retriever before it adds
the tools of the agent itself.  A tool that is only in the retriever is found
by *meaning*, and the question it is asked with the second time is a *name*.
The two do not meet.

**`finalize()` writes the scratchpad into the memory.**  Every message of the
run — the tool results among them — becomes part of the history of the
session.  A tool result is not special: it is a tool message, and it is paid
by every request that follows, until the context guard drops it for being
old.

---

## 4. The fix

**Nothing in the shipped agent had to change.**  The two orchestrators already
place the skill tools where the measurement says they belong:

* `agent-torvalds.py` — `tools = list(tools) + skill_tools`, then
  `HITLFunctionAgent(tools=tools, ...)`;
* `agent-torvalds-mw.py` — the same;
* the retriever path — `create_agent_with_retriever(..., tools=skill_tools)`,
  and inside it `tools=list(tools) if tools else []`: the skill tools are the
  tools that are **always** there, and the retriever adds its own on top.

The investigation confirmed a decision that was already made, and turned a
sentence in a commit message into a measurement that can be repeated.

The transient channel is **not** shipped.  It is measured, not implemented —
section 2.4 is the evidence for the decision *not* to implement it yet.

---

## 5. Verification

The probe is read-only and runs in a second:

```console
$ .venv/bin/python investigate/skills-in-function-agent/probe_skills_in_function_agent.py
end of the probe
```

Its five sections are, in order: the integration points of the installed
`FunctionAgent`; the question the retriever is asked; where the body of a
skill ends up; the price of each channel; the transient channel.

The numbers in this report are the numbers the probe printed.  They are
reproduced by running it — the probe computes the paths it prints at run time,
and it writes nothing.

---

## 6. What is *not* in this change, and why

* **The transient channel is not implemented.**  It would have to be a
  `take_step()` override that drops the marked messages from the scratchpad,
  and the payoff is conditional (section 2.4): a run that ends with the body
  pays the same either way.  The implementation belongs to a change of its own,
  on its own branch, with its own measurements of the runs it would help.

* **The body is not marked in the shipped agent.**  The marking is what makes
  the transient channel possible, and it costs a key in `additional_kwargs` of
  every tool message.  Without a decision to ship the transient channel, the
  marking is a cost with no benefit.

* **The context guard was not changed.**  It already drops the body, as the
  oldest turn, once the conversation grows.  Dropping it *because* it is a
  skill body is the transient channel, and that is the change above.

---

## 7. The recommendation to the operator

Nothing to do.  The agent behaves as it should: the skill tools are always
there, and the body of a skill costs one turn plus the requests that follow,
until the guard drops it.

If the conversations of this machine are long enough that the body of a skill is
paid for too many requests, the transient channel is the change that removes
that cost — and the condition it needs (a run that continues past the body) is
worth knowing before it is asked for.

---

## See also

* [`docs/skills-in-the-agent.md`](../../docs/skills-in-the-agent.md) — the
  documentation of the same findings, for the reader of the project
* [`docs/skills.md`](../../docs/skills.md) — how to write a skill, and what the
  settings do
* [`investigate/agent-skills/INVESTIGATION_REPORT.md`](../agent-skills/INVESTIGATION_REPORT.md) —
  what the skills feature costs in the prompt
