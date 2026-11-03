# Deployment

The scripts that put Agent Torvalds on a machine.

| Path | What it is |
|---|---|
| `deploy-torvalds.sh` | The deployment script. One pass: system packages, the Python virtual environment, Ollama with the models, PostgreSQL (optional), and a starter `.env`. |
| `deploy-torvalds.sh.example.env` | An example environment file. |
| `tests/` | The folder's contract harness, and the proof that the harness catches deliberate breakage. |

## Why this folder exists

The script used to live in `investigate/deployment-script/`, next to the
report that described it. That is the wrong home for it: `investigate/`
holds the *record* of a piece of work, and the implementations that came
out of it live in their own place — the toolkits under `toolkits/`, the
chat manager under `chat_manager/`, the deployment scripts here.

The investigation documents stayed where they were:
`investigate/deployment-script/` still holds the report, the requirements
and the plan.

## Running it

```bash
./deploy/deploy-torvalds.sh --help
```

The script needs **no Python of its own** — it installs one. A machine
without a usable interpreter is exactly what it exists to fix.

It looks for `requirements.txt` and `setup_postgres_db.sql` in the
deployment directory, which defaults to the current one. Point it
elsewhere with `--deploy-dir`:

```bash
./deploy/deploy-torvalds.sh --deploy-dir /srv/agent-torvalds --non-interactive
```

### The options

| Option | Purpose |
|---|---|
| `-n, --non-interactive` | Run without prompts, using every default |
| `-m, --model MODEL` | Chat model to pull and to write into `.env` |
| `-e, --embedding-model MODEL` | Embedding model to pull |
| `-s, --skip-ollama` | Do not install or pull models |
| `-p, --skip-pip` | Do not create the virtual environment |
| `-w, --with-postgres` | Also install and configure PostgreSQL |
| `-l, --log-file PATH` | Log file (default `/var/log/torvalds-deploy.log`) |
| `-d, --deploy-dir PATH` | Where to deploy (default: the current directory) |
| `-h, --help` | The full help, on stdout |
| `-v, --version` | The version, on stdout |

`--help` and `--version` are **queries** and write to stdout. Everything
else — the banner, the progress, the errors — goes to **stderr**, so a
run can be piped without the log lines ending up in the output. An
unknown option exits **2**, not 0.

### Unattended runs

`sudo` keys its cached timestamp on the terminal, so a cache created by
the calling shell is not visible to a script. The script therefore
establishes its own, and in `--non-interactive` mode it needs the
password up front:

```bash
export SUDO_PASSWORD='...'
./deploy/deploy-torvalds.sh --non-interactive
```

`SUDO_PASSWORD_FILE` points at a file that holds the password on its
first line, which keeps the secret out of the environment. Alternatively,
run the script as root, or prime the sudo cache with `sudo -v` first.

### The log file

The log goes to `/var/log/torvalds-deploy.log`, which only root may
create. A deployment run as an ordinary user falls back to
`~/.torvalds/logs/torvalds-deploy.log` and says so — because an
unwritable log file is not a cosmetic problem: every
`2>>"$LOG_FILE"` in the script is a redirection, and a redirection that
cannot be opened means the command does not run at all.

### The generated `.env`

The script writes a `.env` with the variables the agent actually reads.
The example that ships next to it, `deploy-torvalds.sh.example.env`,
carries the same names — it says "copy this file to .env", so a name
the agent ignores in it would configure nothing:

| Variable | Read by |
|---|---|
| `TORVALDS_MODEL` | `agent-torvalds.py` — the chat model |
| `TORVALDS_OLLAMA_HOST` | `components/ollama_config.py` — the endpoint |
| `TORVALDS_PG_*` | `chat_manager` — the PostgreSQL connection |

Load it before starting the agent:

```bash
set -a; . ./.env; set +a
python agent-torvalds.py
```

> The embedding model is **not** configurable through the environment: the
> retriever hard-codes `nomic-embed-text` in `agent_tool_retriever.py`.

## The contract

The folder is guarded by a harness with eleven invariants, and the
harness is guarded by a proof: twelve deliberate breakages, at least one
per invariant, each caught.

```bash
python3 deploy/tests/verify_deploy_layout.py
python3 deploy/tests/verify_harness_catches_regressions.py
```

The first answers *does the folder hold what it should, and does the
script still behave the way the documentation says*. The second answers
*would we notice if it stopped*.

Both are also run by pytest:

```bash
python3 -m pytest deploy/tests -q
```

| Invariant | What it holds |
|---|---|
| **D1** | The script lives in `deploy/` and nowhere else. |
| **D2** | It is executable, it is bash, and it parses. |
| **D3** | `--help` is a query: stdout, exit 0, every option listed. |
| **D4** | `--version` is a query: stdout, exit 0. |
| **D5** | An unknown option fails instead of reporting success. |
| **D6** | The script bootstraps its own sudo timestamp. |
| **D7** | No `sudo VAR=value` form, which the sudoers policy may refuse. |
| **D8** | Every `.env` — the one the script writes and the example that ships with it — names the variables the agent actually reads. |
| **D9** | No document still points at the old path. |
| **D10** | The log file is made writable before anything is redirected to it. |
| **D11** | A query is not reported as a deployment. |

### A copy of the repository is not part of the contract

The contract is about **this** repository.  A copy of the repository
inside it is not: the copy holds its own copy of the script, and its own
copy of the harness, and neither is a breach.

A copy is recognised by the `.git` it carries, so the rule holds whatever
the copy is called — and there is no name to remember.  The harness does
not scan a copy, and it does not report the script inside one.

The proof shows that case too, and it is the only one the contract must
*not* report: the twelve breakages must be caught, and the copy of the
repository must stay quiet.

## Two things worth knowing about the script

**`sudo env VAR=value cmd`, never `sudo VAR=value cmd`.** sudo only
honours a variable set on the command line when the `setenv` option is
set in sudoers, or when the variable survives `env_reset`. Neither is
guaranteed — `/etc/sudoers` is root-only and distro dependent — and when
the variable is refused, sudo aborts the whole command with *"sorry, you
are not allowed to set the following environment variables"*. `sudo env
VAR=value cmd` always works, because `env` runs *as root*, after sudo
has already reset the environment.

**`dpkg-query`, not `dpkg -l`.** `dpkg -l <name>` exits **0** for a
package that dpkg knows about but that is not installed, so it cannot be
used to test for installation. `dpkg-query -f '${Status}'` reports the
real state.
