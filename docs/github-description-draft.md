# GitHub "About" description — applied

**Target repository:** `KostiantynBushko/agent-torvalds`
**Previous description:** `AI Agent` (8 chars) — generic, says nothing about the project.
**GitHub limit:** 350 characters for the About description.
**Status:** **APPLIED** — live on GitHub, verified by `GET /repos/KostiantynBushko/agent-torvalds`
(342 chars) and by the rendered `og:description` meta tag. The repository **topics** were applied
as well (see *Related metadata*).

## Applied description (342 characters, plain text)

```
Torvalds agent is kind of a Swiss knife for engineers: one AI agent with a full toolbox — OS & files, Linux shell, Windows PowerShell, Git/GitHub PRs, PostgreSQL & MySQL, APT packages, MikroTik RouterOS, math & data analysis, project workflows, chat history, human-in-the-loop and a multi-window TUI. Tool-first: it never fabricates a result.
```

| Property | Value |
|---|---|
| Characters | **342** (limit 350) |
| UTF-8 bytes | 344 (one em dash `—` = 3 bytes) |
| Newlines | none |
| Markdown / HTML | none — GitHub renders it literally |
| Non-ASCII | one em dash (U+2014) |

## Key idea

> "Torvalds agent is kind of a Swiss knife…"

One general-purpose AI agent that carries a whole toolbox, and that actually
touches the real system instead of pretending. The "Swiss knife" metaphor
covers the breadth of the toolkits: OS/files, Linux shell, Windows PowerShell,
Git/GitHub, databases, APT packages, MikroTik routers, project workflows,
chat history, human-in-the-loop and the multi-window TUI.

The closing line carries the project's actual philosophy, taken from the
README: **tool-first — never simulate a result**.

The applied text is candidate **A** (below, 304 chars) extended to exactly 342
chars: `math & data analysis` added to the toolbox list, `HITL` expanded to
`human-in-the-loop`, `project manager` reworded to `project workflows`, and the
closing `it never simulates a result` reworded to `it never fabricates a result`.

## Candidates (evaluated)

### A — full toolbox (304 chars) — *basis of the applied text*

```
Torvalds agent is kind of a Swiss knife for engineers: one AI agent with a full toolbox — OS & files, Linux shell, Windows PowerShell, Git/GitHub PRs, PostgreSQL & MySQL, APT packages, MikroTik RouterOS, project manager, chat history, HITL and a multi-window TUI. Tool-first: it never simulates a result.
```

### B — compact (242 chars)

```
Torvalds agent is kind of a Swiss knife for technical work: one AI agent, many tools — files, Linux shell, Windows PowerShell, Git & GitHub PRs, PostgreSQL/MySQL, APT, MikroTik routers, project manager, HITL, TUI. Tool-first, never simulated.
```

### C — engineering/ops tone (311 chars)

```
Torvalds agent is kind of a Swiss knife for engineering and ops work: a general-purpose AI agent that reaches the real system — files, Linux shell, Windows PowerShell, Git/GitHub, PostgreSQL & MySQL, APT packages, MikroTik RouterOS, project workflows and human-in-the-loop. Tool-first: never simulates a result.
```

### D — "one agent, one toolbox" (301 chars)

```
Torvalds agent is kind of a Swiss knife for engineers — one AI agent, one toolbox: OS/files, Linux shell, Windows PowerShell, Git & GitHub PRs, PostgreSQL & MySQL, APT packages, MikroTik RouterOS, project manager, chat history, human-in-the-loop, multi-window TUI. Tool-first: it never fakes a result.
```

## Related metadata (optional, same GitHub API call)

| Field | Current | Proposed |
|---|---|---|
| `description` | `AI Agent` (8 chars) | **applied — 342 chars, see above** |
| `homepage` | *(empty)* | *(left empty — no public docs site yet)* |
| `topics` | *(empty)* | **applied** — `ai-agent`, `llm`, `llama-index`, `tool-calling`, `agents`, `automation`, `devops` |

> `homepage` was **not** changed — there is no public docs site to point at.
> `topics` were applied on operator approval.

### The topics endpoint

`PATCH /repos/{owner}/{repo}` accepts a `topics` key, but it returned an empty
list — the dedicated endpoint is the reliable one:

```bash
curl -sS -X PUT \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/KostiantynBushko/agent-torvalds/topics \
  -d '{"names": ["ai-agent", "llm", "llama-index", "tool-calling", "agents", "automation", "devops"]}'
```

GitHub normalises and sorts the topic list, so it comes back as:
`agents`, `ai-agent`, `automation`, `devops`, `llama-index`, `llm`, `tool-calling`.

## How it was applied

```bash
curl -sS -X PATCH \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/KostiantynBushko/agent-torvalds \
  -d '{"description": "<chosen text>"}'
```

Requires the `repo` scope on the token. Verified available: the token in the
environment authenticates as `KostiantynBushko` and `PATCH /repos/{owner}/{repo}`
is the only call needed — no file in the repository is touched.

### Rollback

```bash
curl -sS -X PATCH -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/KostiantynBushko/agent-torvalds \
  -d '{"description": "AI Agent"}'
```
