# shodan-toolkit

A Python wrapper around the [Shodan](https://www.shodan.io) command-line
interface, built to expose Shodan's internet-exposure data to
[LlamaIndex](https://docs.llamaindex.ai) `FunctionAgent` instances.

The Shodan CLI is a text interface — it prints human-readable tables. This
package wraps it in two layers:

| Layer | Module | Purpose |
|-------|--------|---------|
| **Transport** | `runner.py` | Executes the `shodan` binary with a non-interactive, non-coloured, non-paging environment and returns structured results. |
| **Parsing** | `parsers.py` | Turns the CLI's text output into dictionaries and lists. |
| **Client** | `client.py` | A typed Python API (`ShodanClient`) over the parsers. |
| **Tools** | `tools.py` | LlamaIndex `FunctionTool` wrappers for the agent. |
| **Agent** | `agent.py` | Ready-made `FunctionAgent` factory and system prompt. |

---

## Why a CLI wrapper?

The `shodan` CLI already exists, is well tested, and is what most people
script against. Wrapping it — rather than reimplementing the API client —
means the toolkit inherits Shodan's own rate limiting, account handling and
output formats, and stays maintainable.

The wrapper's job is to make the CLI's output *safe to hand to an LLM*:
stable JSON instead of ANSI-coloured tables, structured records instead of
prose, and errors returned as data instead of exceptions.

---

## Installation

```bash
git clone <repo-url> shodan-toolkit
cd shodan-toolkit

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

> **Note on `setuptools`**
> The Shodan CLI (1.31.0) imports `pkg_resources`, which was removed in
> setuptools 81+. The `cli` extra pins `setuptools<81` to keep `shodan`
> importable. If `shodan --help` fails with
> `ModuleNotFoundError: No module named 'pkg_resources'`, install
> `pip install "setuptools<81"`.

### Requirements

- Python 3.10+
- The `shodan` CLI on `PATH` (installed automatically by the `cli` extra)
- A free Shodan API key

---

## Configuration

The toolkit resolves settings in this order (highest priority first):

1. Explicit arguments passed to `ShodanConfig` / `ShodanClient`
2. Environment variables
3. The JSON config file
4. Built-in defaults

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SHODAN_TOOLKIT_API_KEY` | — | API key (also accepts `SHODAN_API_KEY`) |
| `SHODAN_TOOLKIT_EXECUTABLE` | `shodan` | Path to the Shodan CLI |
| `SHODAN_TOOLKIT_TIMEOUT` | `120` | Per-command timeout in seconds |
| `SHODAN_TOOLKIT_MAX_RESULTS` | `100` | Default result cap for searches |
| `SHODAN_TOOLKIT_SHODAN_CONFIG_DIR` | `~/.config/shodan` | Where the API key is stored |
| `SHODAN_TOOLKIT_CONFIG` | `~/.config/shodan-toolkit/config.json` | Toolkit config file |

### Storing the API key

```bash
shodan-toolkit init <your-api-key>     # writes ~/.config/shodan/api_key (mode 0600)
shodan-toolkit init --from-env          # reads $SHODAN_API_KEY
```

Verify the setup at any time:

```bash
shodan-toolkit doctor
```

```
Shodan Toolkit — Diagnostics
============================================================
[OK  ] shodan_cli             shodan
[OK  ] shodan_cli_version     1.31.0
[OK  ] api_key                /home/user/.config/shodan/api_key
[OK  ] config                 /home/user/.config/shodan-toolkit/config.json
[OK  ] llama_index            installed
============================================================
Result: all checks passed
```

---

## Quick start

### Python API

```python
from shodan_toolkit import ShodanClient

client = ShodanClient()

results = client.search("product:nginx country:DE", limit=10)
for record in results:
    print(record["ip_str"], record["port"], record["data"])

host = client.host("8.8.8.8")
print(host["country"], host["org"], host["ports"])

facets = client.stats("apache port:443", facets=["country", "org"])
print(facets["country"][0])   # {'value': 'United States', 'count': 1234567}
```

### LlamaIndex agent

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.llms import OpenAI
from shodan_toolkit import get_all_tools, build_agent

# Option A — attach the tools to your own agent
agent = FunctionAgent(
    name="shodan_agent",
    llm=OpenAI(model="gpt-4o-mini"),
    tools=get_all_tools(),
    system_prompt="You are a security analyst with Shodan access.",
)

# Option B — use the pre-configured factory
agent = build_agent(llm=OpenAI(model="gpt-4o-mini"))
```

`build_agent` injects a status block into the system prompt so the model
knows whether the CLI and API key are configured.

---

## Using it as a library

The package is a normal Python distribution, so it can be consumed three
ways — all of them supported:

**1. As a standalone app** — install it and use the CLI:

```bash
pip install "shodan-toolkit[cli]"
shodan-toolkit doctor
shodan-toolkit search "nginx" --limit 5
python -m shodan_toolkit search "nginx" --limit 5   # no console script needed
```

**2. As a Python module** — import it in your own scripts:

```python
from shodan_toolkit import ShodanClient

client = ShodanClient()
results = client.search("product:nginx", limit=10)
```

**3. Integrated into another project** — install it into that project's
environment and mount the tools on your own agent:

```bash
pip install "shodan-toolkit[cli]"      # in the consuming project
```

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.llms import OpenAI
from shodan_toolkit import get_all_tools

agent = FunctionAgent(
    name="shodan_agent",
    llm=OpenAI(model="gpt-4o-mini"),
    tools=get_all_tools(),
)
```

The `llama-index-core` dependency is only needed for the *tool* and *agent*
helpers. The core API — `ShodanClient`, the config layer and the parsers —
has no LlamaIndex dependency at all, so it can be used in a project that
does not want the agent stack.

---

## Available tools

### Read-only (default — 12 tools)

| Tool | Purpose |
|------|---------|
| `shodan_search` | Search the Shodan database for hosts matching a query. |
| `shodan_count` | Count hosts matching a query. |
| `shodan_host` | Everything Shodan knows about a single IP. |
| `shodan_stats` | Facet breakdowns (country, org, port, product, os…). |
| `shodan_trends` | Historical database — how a query trended over time. |
| `shodan_domain_info` | DNS records for a domain. |
| `shodan_honeyscore` | Is this IP a honeypot? |
| `shodan_myip` | The public IP Shodan sees for this machine. |
| `shodan_account_info` | Remaining query/scan credits. |
| `shodan_list_alerts` | List configured network alerts. |
| `shodan_list_scans` | List recent on-demand scans. |
| `shodan_raw` | Escape hatch — run any *read-only* CLI command and get raw output. |

### Mutating (opt-in — 4 tools)

These change account state or consume credits, so they are **excluded by
default**. Enable them explicitly:

```python
from shodan_toolkit import get_all_tools

tools = get_all_tools(include_mutating=True)
```

| Tool | Purpose |
|------|---------|
| `shodan_create_alert` | Create a network alert over one or more netblocks. |
| `shodan_delete_alert` | Delete a network alert. |
| `shodan_submit_scan` | Submit an on-demand scan (consumes scan credits). |
| `shodan_download` | Download search results to a `.json.gz` file. |

You can also select tools individually:

```python
from shodan_toolkit import get_tools_by_name

tools = get_tools_by_name(["shodan_search", "shodan_host"])
```

---

## Tool response format

Every tool returns JSON with a consistent envelope. Success:

```json
{
  "success": true,
  "data": { "query": "nginx", "count": 2, "results": [ ... ] }
}
```

Failure — note that errors are **returned, not raised**, so an agent can read
the message and retry with a corrected query:

```json
{
  "success": false,
  "error": "Shodan API authentication failed. Run 'shodan init <api-key>' ..."
}
```

---

## Command-line interface

```bash
shodan-toolkit doctor                       # diagnose the setup
shodan-toolkit tools                        # list agent tools
shodan-toolkit tools --all --schemas        # list every tool with its JSON schema
shodan-toolkit search "nginx" --limit 5
shodan-toolkit search "nginx" --limit 5 --text
shodan-toolkit count "apache port:443"
shodan-toolkit host 8.8.8.8
shodan-toolkit stats "apache" --facets country,org
shodan-toolkit trends "apache" --facets os
shodan-toolkit domain example.com --details
shodan-toolkit honeyscore 1.1.1.1
shodan-toolkit myip
shodan-toolkit info
shodan-toolkit alerts
shodan-toolkit init <api-key>
```

The toolkit is also runnable as a module, which works even when the console
script is not on `PATH`:

```bash
python -m shodan_toolkit doctor
python -m shodan_toolkit search "nginx" --limit 5
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  LlamaIndex FunctionAgent                                │
└───────────────┬──────────────────────────────────────────┘
                │ calls
┌───────────────▼──────────────────────────────────────────┐
│  tools.py        16 FunctionTool wrappers                 │
│  agent.py        FunctionAgent factory + system prompt    │
└───────────────┬──────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────┐
│  client.py      ShodanClient — typed Python API           │
└───────────────┬──────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────┐
│  parsers.py     text  →  structured records               │
│  runner.py      subprocess execution + env control        │
└───────────────┬──────────────────────────────────────────┘
                │ subprocess
┌───────────────▼──────────────────────────────────────────┐
│  shodan CLI  (external binary)                            │
└──────────────────────────────────────────────────────────┘
```

### Environment control

The runner neutralises everything that would make the CLI's output
unparseable:

| Concern | Handling |
|---------|----------|
| ANSI colour codes | `NO_COLOR=1` + `TERM=dumb`; `--no-color` is passed only to `shodan search`, the one subcommand that accepts it |
| Pager | `PAGER=cat`, `LESS=` (the CLI uses `click.echo_via_pager`) |
| Interactive prompts | `SHODAN_CLI_NON_INTERACTIVE=1` |
| Warning noise | `pkg_resources` deprecation warnings stripped from stderr |

The runner also prefers the `shodan` console script belonging to the
*running* interpreter over whatever happens to be first on `PATH` — this
prevents a broken CLI from another virtualenv being picked up by mistake.

---

## Testing

```bash
pytest                               # 153 tests
python examples/verify_parsers.py    # 51 checks against real CLI output
python examples/verify_argv.py       # 17 argument vectors vs. the real binary
python examples/smoke_test.py        # end-to-end against the real binary
python examples/agent_demo.py        # agent integration, fully offline
```

The suite covers the library and the agent adapter alike, because both
live under `tests/`:

| File | Covers |
|---|---|
| `tests/test_client.py`, `tests/test_parsers.py`, `tests/test_config_cli.py` | the client, the parsers, the configuration |
| `tests/test_cli_contract.py`, `tests/test_runner_availability.py` | the CLI contract, the availability check |
| `tests/test_raw_guard.py`, `tests/test_tools.py` | the read-only guard, the tool registry |
| `tests/test_agent_adapter.py` | the agent adapter: the tool registration, the degradation contract, the load-path parity |

`tests/test_agent_adapter.py` reaches into the agent repository that
surrounds the toolkit, so it skips itself when the toolkit is used as a
standalone distribution.

The test suite never touches the network: the CLI is replaced with a
`FakeRunner` that records the argument vector and replays canned output.
This makes it possible to assert the *exact* command line that would be
executed — catching regressions in flag construction.

`examples/verify_parsers.py` is the counterpart: it feeds the parsers output
captured verbatim from the real `shodan` binary, so the parsing logic is
validated against reality rather than assumptions.

`examples/verify_argv.py` closes the remaining gap. It runs every argument
vector the client can build against the *installed* binary and reports any
that the CLI rejects. This matters because each Shodan subcommand declares
its own options: passing `--no-color` to `shodan host` aborts the command
with `No such option` before any API call happens. `tests/test_cli_contract.py`
pins the same expectations as unit tests, so a regression is caught without a
network or an installed CLI.

---

## Project layout

```
shodan-toolkit/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/shodan_toolkit/
│   ├── __init__.py       public API
│   ├── __main__.py       `python -m shodan_toolkit` entry point
│   ├── agent.py          FunctionAgent factory
│   ├── cli.py            command-line interface
│   ├── client.py         typed Python API
│   ├── config.py         configuration resolution
│   ├── parsers.py        text → structured records
│   ├── runner.py         subprocess execution
│   └── tools.py          LlamaIndex FunctionTool wrappers
├── tests/                153 tests
├── conftest.py           makes `src/` importable for the test run
└── examples/             verification and demo scripts
```

---

## Security notes

- The API key is stored with `0600` permissions, matching `shodan init`.
- Mutating tools are opt-in so an autonomous agent cannot silently create
  alerts or burn scan credits.
- `shodan_raw` is an escape hatch, but it only runs read-only subcommands.
  State-changing ones (`alert create`, `scan submit`, `download`, `init`,
  `org add`, …) are refused with an explanatory error, so the tool cannot
  bypass the read-only/mutating split that keeps autonomous agents safe.

## License

MIT
