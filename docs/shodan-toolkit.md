# Shodan Toolkit

The Shodan toolkit lets the agent query the [Shodan](https://www.shodan.io)
internet-exposure database: which hosts are reachable, what software they
run, which ports are open and which of them are honeypots. It is the
repository's only *reconnaissance* toolkit, and the only one whose data
comes from an external service rather than from the local host.

The toolkit was developed as a standalone project and was moved into this
repository under `toolkits/shodan-toolkit/`. Its commit history was
preserved when it was moved - see
[§ 9. Architecture](#9-architecture).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [The tools](#4-the-tools)
5. [The read-only / write split](#5-the-read-only--write-split)
6. [Limitations](#6-limitations)
7. [Security](#7-security)
8. [Troubleshooting](#8-troubleshooting)
9. [Architecture](#9-architecture)

---

## 1. Overview

The feature has two halves:

```
toolkits/shodan-toolkit/       the reusable library - the Shodan CLI wrapper
        │
        ▼
agent_shodan_toolkit.py        the LlamaIndex adapter - the sixteen tools
        │
        ▼
agent-torvalds.py / -mw.py     the orchestrators
```

The core package can be used as a plain library by any Python application:

```python
from shodan_toolkit import ShodanClient

client = ShodanClient()
results = client.search("product:nginx country:DE", limit=10)
for record in results:
    print(record["ip_str"], record["port"], record["data"])
```

The library itself is documented in
[toolkits/shodan-toolkit/README.md](../toolkits/shodan-toolkit/README.md);
this page covers the *integration* into the agent.

> The directory name contains a hyphen, which is not a valid Python
> identifier. Import the package through the alias
> `toolkits.shodan_toolkit`, which `toolkits/__init__.py` registers.

### Why a CLI wrapper?

The `shodan` CLI already exists, is well tested, and is what most people
script against. Wrapping it - rather than reimplementing the API client -
means the toolkit inherits Shodan's own rate limiting, account handling and
output formats, and stays maintainable.

The wrapper's job is to make the CLI's output *safe to hand to an LLM*:
stable JSON instead of ANSI-coloured tables, structured records instead of
prose, and errors returned as data instead of exceptions.

---

## 2. Installation

The toolkit drives the `shodan` command line binary, which is an **optional**
dependency. The agent boots without it, and the toolkit simply reports that
it is unavailable.

```bash
pip install "shodan>=1.31" "setuptools<81"
```

> **Note on `setuptools`**
> The Shodan CLI (1.31.0) imports `pkg_resources`, which was removed in
> setuptools 81+. The `cli` extra pins `setuptools<81` to keep `shodan`
> importable. If `shodan --help` fails with
> `ModuleNotFoundError: No module named 'pkg_resources'`, install
> `pip install "setuptools<81"`.

The library itself needs `llama-index-core` and `pydantic`, both of which
the agent already requires. The in-repository copy is importable without
installation, because the adapter loads it through the
`toolkits.shodan_toolkit` alias.

### Verifying the installation

```bash
python -c "from agent_shodan_toolkit import get_toolkit_status; print(get_toolkit_status())"
```

```python
{'available': True, 'cli_available': True, 'has_api_key': True, 'error': None}
```

A free Shodan API key is required for everything except `shodan_myip`.

---

## 3. Configuration

The toolkit resolves settings in this order (highest priority first):

1. Explicit arguments passed to `ShodanConfig` / `ShodanClient`
2. Environment variables
3. The JSON config file
4. Built-in defaults

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SHODAN_TOOLKIT_API_KEY` | - | API key (also accepts `SHODAN_API_KEY`) |
| `SHODAN_TOOLKIT_EXECUTABLE` | `shodan` | Path to the Shodan CLI |
| `SHODAN_TOOLKIT_TIMEOUT` | `120` | Per-command timeout in seconds |
| `SHODAN_TOOLKIT_MAX_RESULTS` | `100` | Default result cap for searches |
| `SHODAN_TOOLKIT_SHODAN_CONFIG_DIR` | `~/.config/shodan` | Where the API key is stored |
| `SHODAN_TOOLKIT_CONFIG` | `~/.config/shodan-toolkit/config.json` | Toolkit config file |
| `TORVALDS_SHODAN_ALLOW_MUTATING` | unset | Expose the write-capable tools (see §5) |

### Storing the API key

```bash
shodan-toolkit init <your-api-key>     # writes ~/.config/shodan/api_key (mode 0600)
shodan-toolkit init --from-env          # reads $SHODAN_API_KEY
```

Verify the setup at any time:

```bash
shodan-toolkit doctor
```

---

## 4. The tools

The adapter exposes the toolkit's tools under the **Security** category of
the startup tool selection menu, so they can be loaded on their own with
`--select` (or `\tools` / `\tool-select` in the TUI).

| Tool | Purpose |
|---|---|
| `shodan_search` | Search the database for hosts matching a query |
| `shodan_count` | Count the hosts matching a query |
| `shodan_host` | Everything known about a single IP address |
| `shodan_stats` | Facet breakdown (country, org, port, product) for a query |
| `shodan_trends` | Query the historical database for trends over time |
| `shodan_domain_info` | DNS records for a domain name |
| `shodan_honeyscore` | Check whether an IP address is a honeypot |
| `shodan_myip` | The public IP address Shodan sees for this machine |
| `shodan_account_info` | Account information and remaining credits |
| `shodan_list_alerts` | The network alerts configured on the account |
| `shodan_list_scans` | Recently launched on-demand scans |
| `shodan_raw` | Raw CLI output, for commands without a dedicated tool |
| `shodan_create_alert` | Create a network alert monitoring netblocks *(write)* |
| `shodan_delete_alert` | Delete a network alert *(write)* |
| `shodan_submit_scan` | Submit an on-demand scan for netblocks *(write)* |
| `shodan_download` | Download search results into a compressed JSON file *(write)* |

### A typical investigation

```
1. shodan_count("product:nginx country:DE")     -> how big is the result set?
2. shodan_stats("product:nginx country:DE")     -> which orgs and ports dominate?
3. shodan_search("product:nginx country:DE", limit=10, fields=["ip_str","port","data"])
4. shodan_host("<ip>")                           -> the full record for one host
5. shodan_honeyscore("<ip>")                     -> is it a decoy?
```

The model is instructed (in the toolkit's own system prompt) to start with
`shodan_count` rather than with an expensive `shodan_search`, and to quote
exact IPs, hostnames and banner data instead of inventing findings.

### The error convention

A tool never raises. It returns a JSON payload:

```json
{
  "success": false,
  "error": "shodan_raw only runs read-only commands; 'alert create' changes account state or consumes credits. Use the dedicated tool instead."
}
```

The same convention is used by the other toolkits in this repository, so a
failure is something the model can reason about instead of a Python
traceback in the transcript.

---

## 5. The read-only / write split

The upstream toolkit splits its registry into a `read` and a `write`
category. The adapter keeps that split:

* **read-only** (12 tools) - exposed by default;
* **write** (4 tools) - create/delete alerts, submit scans, download
  results. These change account state and consume Shodan credits, so they
  are **not** exposed unless the operator opts in.

The opt-in is a single environment variable, read by the adapter itself, so
every load path (retriever, `--select` menu, both orchestrators) behaves
identically:

```bash
export TORVALDS_SHODAN_ALLOW_MUTATING=1
```

The value may also be forced per call site:

```python
from agent_shodan_toolkit import get_all_tools, get_mutating_tools

get_all_tools(include_mutating=True)   # read + write
get_mutating_tools()                   # write only
```

### The raw-command guard

`shodan_raw` can run any CLI subcommand, so it is the one read-only tool
that could escape the split. The toolkit therefore screens the subcommand
before running it and refuses the ones that change state, consume credits
or write files:

```
shodan_raw(["alert", "create", "x", "1.2.3.4/32"])
-> {"success": false, "error": "shodan_raw only runs read-only commands; ..."}
```

The guard is covered by the toolkit's own test suite
(`toolkits/shodan-toolkit/tests/test_raw_guard.py`).

---

## 6. Limitations

* The `shodan` CLI must be installed and on `PATH`. Without it the tools
  return an error payload - the agent does not crash.
* A Shodan API key is required for everything except `shodan_myip`.
* Shodan's free tier limits the query rate and the number of credits for
  on-demand scans. A rate-limited query returns an error payload.
* The data is a snapshot of what Shodan scanned. A host that is open today
  may be closed tomorrow, and Shodan never sees hosts behind a firewall.
* The CLI output format is what the parsers expect. A future Shodan release
  that changes its table format will need a parser update - the toolkit's
  own test suite is the contract that catches this.

---

## 7. Security

* **Read-only by default.** The write-capable tools are opt-in (§5).
* **The raw-command guard** keeps `shodan_raw` read-only (§5).
* **No secret in the transcript.** The API key is read from the
  environment or from `~/.config/shodan/api_key` (mode 0600) and is never
  passed to the CLI on the command line, so it cannot leak into a log line
  or an error message.
* **No shell.** The CLI is executed as an argument vector, never through a
  shell, so a query string cannot become a shell command.
* **Bounded output.** The runner strips ANSI colour and paging, and the
  result caps keep a hostile response from flooding the context window.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pkg_resources'` | setuptools 81+ removed `pkg_resources`, which the Shodan CLI imports | `pip install "setuptools<81"` |
| `"error": "shodan command failed (exit 127)"` | the `shodan` binary is not on `PATH` | `pip install "shodan>=1.31"`, or set `SHODAN_TOOLKIT_EXECUTABLE` |
| `"error": "No API key configured"` | no key stored | `shodan-toolkit init <key>` or export `SHODAN_API_KEY` |
| The tools are missing from the menu | the toolkit is not installed | check `get_toolkit_status()`; the agent still boots without it |
| The write tools are missing | that is the default | `export TORVALDS_SHODAN_ALLOW_MUTATING=1` |

---

## 9. Architecture

### Where the code lives

| Path | Role |
|---|---|
| `toolkits/shodan-toolkit/` | The core package. The upstream project, verbatim. |
| `toolkits/shodan-toolkit/src/shodan_toolkit/` | The importable package (`runner`, `parsers`, `client`, `tools`, `agent`, `config`, `cli`). |
| `toolkits/shodan-toolkit/tests/` | The upstream test suite - 133 tests. |
| `agent_shodan_toolkit.py` | The LlamaIndex adapter - the sixteen tools. |
| `docs/shodan-toolkit.md` | This page. |

### How the move was done

The project was developed standalone and then moved into this repository.
The move used `git subtree`, so **the original commits are still in the
history** of the `feature/shodan-toolkit` branch, grafted under the
`toolkits/shodan-toolkit/` prefix:

```
*   Add 'toolkits/shodan-toolkit/' from commit '26b1fb2...'
|\
| * 26b1fb2 chore: remove project-root RULES.md
| * 72b3239 fix: correct Shodan CLI argument vectors and harden library packaging
| * 6d33069 Initial commit: shodan-toolkit
* b068337 fix: make the HITL timeout default to "no timeout" (wait for the user) (#23)
```

The content is byte-identical to the upstream project - every file has the
same blob hash. The upstream repository therefore stays the source of
truth, and `git subtree pull` can bring in later upstream work.

### The import alias

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.shodan_toolkit import ShodanClient, get_all_tools
```

The alias is registered only if the package is importable, so
`import toolkits` never fails when the toolkit is absent.

### The upstream test suite

The toolkit's own tests are part of the repository's test run:

```bash
self-development/.venv/bin/python -m pytest toolkits/shodan-toolkit/tests -q
```

`pytest.ini` puts `toolkits/shodan-toolkit/src` on the path, so the suite
tests the in-repository copy - the same code the agent adapter loads.
