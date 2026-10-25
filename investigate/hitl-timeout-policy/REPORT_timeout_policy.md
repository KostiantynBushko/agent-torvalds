# The timeout policy — what the operator asked for, and what the code does

**Date:** 2026-10-22
**Branch:** `fix/hitl-question-detection`
**Status:** the policy is implemented and verified end to end — **11/11** checks
pass.  Defect **D16** (the timeout was invisible to the model) is **fixed**.

---

## 1. The policy

The operator, asked *"How do you want me to work when a change is still
uncertain — stop and ask before every step, or proceed on my own judgement
and report afterwards?"*, answered:

> "if timeout is -1 you have to stop and wait; if timeout is set you have to
> wait and timeout expires you can act on your own judgement"

Read as a contract, that is two branches:

| Timeout | The agent must | The operator may |
|---|---|---|
| `-1` (no timeout) | **stop and wait** — never decide alone | answer whenever they can |
| `N > 0` | **wait up to N seconds**; when it expires, **act on your own judgement** | answer within N seconds, or stay silent and let the agent decide |

The second branch is the interesting one: the operator keeps the right to be
absent, and the agent is expected to carry on without them.

---

## 2. What was verified

`investigate/hitl-timeout-policy/verify_timeout_policy.py` runs the **real
stack** — the real `HITLFunctionAgent`, the real `EventConsumer`, the real
`ConsoleInputModule`.  Only the *human* is a double: the builtin `input` is
replaced by a function that answers late, or never.

```
.venv/bin/python investigate/hitl-timeout-policy/verify_timeout_policy.py
```

| # | Check | Result |
|---|---|---|
| R1a | a slow human (1.2 s) is still waited for with `timeout = -1` | **pass** |
| R1b | the human's own answer reaches the model | **pass** |
| R1c | a silent human makes the agent wait — it does not decide on its own | **pass** |
| R1d | no answer is recorded while the agent is waiting | **pass** |
| R2a | the run continues after the timeout expires | **pass** |
| R2b | the agent did not wait for the slow human (finished after 1.0 s) | **pass** |
| R2c | the timeout is recorded in the HITL log | **pass** |
| R2d | the fallback answer was used | **pass** |
| R2e | **the model is told the human did not answer** | **FAIL → pass** |
| R3a | the run continues with the shipped default (no fallback answer) | **pass** |
| R3b | **the model can tell that nobody answered** | **FAIL → pass** |

**9/11 before the fix, 11/11 after.**  The two failures were the same defect.

After the fix the model is told:

```
[No human response — the 1s wait ended without an answer.
 The question was not answered; act on your own judgement.]
```

---

## 3. The plumbing implements the policy

**`components/hitl_agent.py`** — the step that waits:

```python
timeout = self.hitl_default_timeout          # -1 by default
...
timeout=(
    None
    if is_no_timeout(timeout)                 # -1  -> wait forever
    else normalize_timeout(timeout) + 5       # N    -> N seconds + grace
),
```

`None` is what `ctx.wait_for_event()` reads as *"wait indefinitely"*, so with
`-1` the agent cannot proceed without the human.  With a finite timeout the
step catches `asyncio.TimeoutError` and continues:

```python
except asyncio.TimeoutError:
    answer_event = AgentAnswerEvent(
        question_id=question_id,
        answer=default_answer,
        was_timeout=True,
    )
```

The step then returns `AgentInput` — the agent **does** carry on.  The
operator's second branch is honoured by the machinery.

**`components/console_input_module.py`** — the prompt that waits:

```python
response = await asyncio.wait_for(
    loop.run_in_executor(None, _ask),
    timeout=normalize_timeout(timeout),       # -1 -> None -> waits forever
)
```

The same convention on both sides, and the two are wired to one value
(`agent-torvalds.py`: `hitl_timeout` → the agent, the consumer *and* the
handler), so the prompt and the step never disagree about when to give up.

---

## 4. D16 — the timeout was invisible to the model (fixed)

The agent continues on its own judgement, but the **model never learns that
the human did not answer**.  The answer is fed back into the scratchpad as
if the human had said it:

```python
scratchpad.append(
    ChatMessage(role="user", content=f"[Human response] {answer}")
)
```

With a configured fallback:

```
the model was told: 'pick one Which one should I use? [Human response] 1'
```

The model reads that as *"the human chose 1"*.  It is not "the human was not
there and the default was used" — the model acts on a fabricated answer
instead of on its own judgement.

With the **shipped default** (`TORVALDS_HITL_DEFAULT_ANSWER` is empty) it is
worse, because the fallback is empty too:

```
the model was told: 'pick one Shall I delete the database? [Human response] '
```

An empty human turn.  For a yes/no question that is indistinguishable from
*"no"*, and the natural reading of `[Human response] ` is a human who declined
to answer — so the agent refuses to act, which is the exact opposite of
*"timeout expires you can act on your own judgement"*.

The audit trail is correct: `HumanLoopHandler` records `was_timeout=True` and
writes the timeout log.  Only the **model's** view of the event is wrong.

### The fix

The scratchpad message must carry the fact that nobody answered.  The answer
event already knows it (`was_timeout=True`), and the step already has it.

`components/hitl_agent.py` — the message the model receives:

```python
@staticmethod
def _answer_message(answer: str, was_timeout: bool, timeout: int) -> str:
    if not was_timeout:
        return f"[Human response] {answer}"

    limit = "unlimited" if is_no_timeout(timeout) else describe_timeout(timeout)
    return (
        f"[No human response — the {limit} wait ended without an answer. "
        f"The question was not answered; act on your own judgement.]"
    )
```

The fallback answer stays in the record (the timeout log keeps it), but the
model is told the truth and is asked to decide — which is what the
operator's rule says it may do.

The regression tests are in `tests/test_hitl_timeout_policy.py` (6 tests).
They drive the real stack; only the human is a double.

| test | fails without the fix |
|---|---|
| `test_the_model_is_told_that_nobody_answered` | **yes** — the model saw the fallback answer as the human's |
| `test_the_model_is_told_even_without_a_fallback_answer` | **yes** — the model saw an empty turn, read as a "no" |
| `test_no_timeout_waits_for_a_slow_human` | no — guards the contract that was already right |
| `test_no_timeout_waits_for_a_silent_human` | no — guards the contract that was already right |
| `test_a_finite_timeout_expires_and_the_agent_carries_on` | no — guards the contract that was already right |
| `test_a_real_answer_is_still_reported_as_an_answer` | no — guards the normal path against the fix |

Two of the six fail without the fix; the other four are the contract that was
already honoured and must stay honoured.

---

## 5. What is *not* broken

* The timeout value is validated (`validate_timeout` rejects anything below
  `-1`), and `-1` is the orchestrator's default.
* The prompt and the step use the same value, so the operator is never
  abandoned while the agent still waits, and vice versa.
* The re-ask guard (`_was_answered`) is unaffected: a timed-out question is
  marked as answered, so the agent does not ask the same thing again after a
  timeout.

---

## 6. The state of it

D16 is **fixed** in `components/hitl_agent.py`, with the regression tests in
`tests/test_hitl_timeout_policy.py` and the harness in
`verify_timeout_policy.py` (11/11).

The CI gate reports **40 known failures, 0 new** — the change breaks nothing
that was not already broken.

The change is in the working tree; the commit needs the operator's approval
(rule 4).

### A note on the wording

The message is deliberately *not* phrased as an answer.  It does not carry
the fallback answer, because the fallback is a canned reply and not a
decision: if the model read "the default answer was 'no'", it would act on a
fabricated "no" — the very thing the rule forbids.  The timeout log keeps the
fallback for the audit trail; the model is told the question went unanswered
and is asked to decide.
