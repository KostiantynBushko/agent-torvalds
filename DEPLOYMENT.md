# Deployment Guide — Torvalds AI Agent

Complete reference for installing, configuring, and deploying the Torvalds AI agent with a local Ollama backend.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Install Ollama](#3-install-ollama)
4. [Verify the Ollama Server](#4-verify-the-ollama-server)
5. [Pull the Models](#5-pull-the-models)
6. [Clone and Install the Agent](#6-clone-and-install-the-agent)
7. [Configure the Agent](#7-configure-the-agent)
8. [Run the Agent](#8-run-the-agent)
9. [Verify the Full Chain](#9-verify-the-full-chain)
10. [Model Catalogue and Hardware Sizing](#10-model-catalogue-and-hardware-sizing)
11. [Startup Modes](#11-startup-modes)
12. [Configuration Reference](#12-configuration-reference)
13. [Database Configuration](#13-database-configuration)
14. [Optional Toolkit Configuration](#14-optional-toolkit-configuration)
15. [Troubleshooting](#15-troubleshooting)
16. [Housekeeping](#16-housekeeping)
17. [Automated Deployment Script](#17-automated-deployment-script)

---

## 1. Architecture Overview

```
        ┌──────────────────────────────┐
        │  agent-torvalds.py           │
        │  (classic REPL)              │
        │  agent-torvalds-mw.py        │
        │  (multi-window TUI)          │
        └───────────┬──────────────────┘
                    │  HTTP
                    ▼
        ┌──────────────────────────────┐
        │  Ollama  (localhost:11434)   │
        │  ├─ chat model               │
        │  └─ nomic-embed-text         │
        └──────────────────────────────┘
```

The agent talks to Ollama over plain HTTP:

- **Chat model** — `llama_index.llms.ollama.Ollama` for chat & tool calling
- **Embedding model** — `llama_index.embeddings.ollama.OllamaEmbedding` for semantic tool retrieval

Both clients are pointed at the same endpoint by `components/ollama_config.py`.

> **Key principle**: Torvalds has **no cloud fallback**. Every request is served by a local Ollama instance. Nothing leaves the machine.

---

## 2. Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.8+ |
| **Ollama** | Local instance running on `localhost:11434` (or custom endpoint) |
| **Git** | Installed on the system |
| **PostgreSQL** | Optional — for database toolkit and Chat History Manager |
| **MySQL** | Optional — for database toolkit |
| **Debian/Ubuntu** | Optional — for APT package management toolkit |

### Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 24+ GB (for the default 27B model) |
| Disk | 5 GB | 20+ GB (models + dependencies) |
| GPU | Not required | NVIDIA GPU with 8+ GB VRAM for faster inference |

---

## 3. Install Ollama

### Linux (Debian/Ubuntu/Fedora/Arch)

The install script downloads the binary into `/usr/local/bin/ollama` and registers a `systemd` service:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Check and start the service:

```bash
sudo systemctl status ollama
sudo systemctl start ollama
sudo systemctl enable ollama   # start on boot
```

To make Ollama reachable from other machines on the network:

```bash
sudo systemctl edit ollama
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

**Package managers:**

```bash
sudo pacman -S ollama       # Arch Linux
sudo dnf install ollama     # Fedora
sudo systemctl enable --now ollama
```

### macOS

```bash
brew install ollama
```

Or download `Ollama-darwin.zip` from <https://ollama.com/download> and open the app. The app starts the server automatically. On a headless machine, run `ollama serve` manually.

### Windows

Download `OllamaSetup.exe` from <https://ollama.com/download> and run it. The tray app starts the server automatically; the binary lands in `%LOCALAPPDATA%\Programs\Ollama`.

### Docker

```bash
docker run -d \
  -v ollama:/root/.ollama \
  -p 11434:11434 \
  --name ollama \
  ollama/ollama
```

The named volume keeps pulled models across container restarts. Pull models from inside the container:

```bash
docker exec -it ollama ollama pull nomic-embed-text
```

---

## 4. Verify the Ollama Server

Ollama listens on `http://localhost:11434` by default:

```bash
curl http://localhost:11434/api/version
# {"version":"0.33.2"}
```

List installed models:

```bash
ollama list
```

An empty table means no model has been pulled yet.

If the server was started manually (not as a service), it runs in the foreground:

```bash
ollama serve
```

---

## 5. Pull the Models

The agent needs **two** models:

| Purpose | Model | Required for | Download Size |
|---|---|---|---|
| Chat & tool calling | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (default) | every run | ~16 GB |
| Embeddings | `nomic-embed-text` | default tool-retrieval mode | ~274 MB |

> The embedding model is **only** needed in the default (retriever) mode. With `--full` or `--select` the agent loads tools directly and never builds the vector index, so `nomic-embed-text` can be skipped.

> **Check the model against your RAM before pulling it.** The 27B default needs
> roughly 20 GB to run. On a smaller machine the Ollama server is killed by the
> kernel while it loads the model, and the request fails with
> `curl: (52) Empty reply from server` rather than with a clear error. Check
> `free -g` and pick a model from the catalogue in section 10 that fits — the
> 8B variant needs about 7 GB.

```bash
# Chat model — the default the agent expects (~16 GB)
ollama pull richardyoung/qwen3.6-27b-abliterated:Q4_K_M

# Embedding model — required by the default tool-retrieval mode (~274 MB)
ollama pull nomic-embed-text

# Confirm both are present
ollama list
```

### Alternative (Smaller) Chat Models

If the 16 GB default model does not fit your machine:

```bash
ollama pull qwen2.5-coder:7b-instruct-q4_K_M                                # ~4.7 GB
ollama pull richardyoung/qwen3-8b-abliterated:Q4_K_M                         # ~5.0 GB
ollama pull richardyoung/qwen2.5-coder-14b-instruct-abliterated:Q4_K_M      # ~9.0 GB
```

---

## 6. Clone and Install the Agent

```bash
# 1. Clone the repository
git clone git@github.com:KostiantynBushko/agent-torvalds.git
cd agent-torvalds
```

The repository is public, so an account and an SSH key are not required — use
the HTTPS URL instead when the machine has no GitHub key:

```bash
git clone https://github.com/KostiantynBushko/agent-torvalds.git
cd agent-torvalds
```

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt
```

### Optional Toolkit Dependencies

| Toolkit | Install Command |
|---|---|
| MikroTik RouterOS | `pip install asyncssh` |
| Shodan | `pip install "shodan>=1.31" "setuptools<81"` then `shodan init <api-key>` |

The agent boots without optional dependencies and reports them as unavailable.

---

## 7. Configure the Agent

### Ollama / LLM Configuration

All settings are environment variables. They can also be given inline:

```bash
TORVALDS_MODEL=qwen2.5-coder:7b python agent-torvalds.py
```

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_MODEL` | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | Chat model served by Ollama. Must be pulled first |
| `TORVALDS_OLLAMA_HOST` | `http://localhost:11434` | Ollama server endpoint. Bare `host:port` accepted |
| `OLLAMA_HOST` | — | Fallback for `TORVALDS_OLLAMA_HOST` |
| `TORVALDS_REQUEST_TIMEOUT` | `99999` | LLM request timeout in seconds |
| `TORVALDS_MAX_ITERATIONS` | `50` | Maximum tool-calling iterations per request |
| `TORVALDS_SIMILARITY_TOP_K` | `8` | Tools retrieved per query in retriever mode |

**Using a different model:**

```bash
export TORVALDS_MODEL="qwen2.5-coder:7b-instruct-q4_K_M"
python agent-torvalds.py
```

**Pointing at a remote Ollama instance:**

```bash
export TORVALDS_OLLAMA_HOST="http://192.168.1.10:11434"
```

A bare `host:port` is accepted — the `http://` scheme is added automatically. `TORVALDS_OLLAMA_HOST` takes precedence over `OLLAMA_HOST`.

### Statistics Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_STATS_ENABLED` | `true` | Enable/disable stats collection |
| `TORVALDS_STATS_VERBOSE` | `false` | Show detailed per-tool timing |
| `TORVALDS_STATS_PERSIST` | `true` | Save stats to cache for history |
| `TORVALDS_STATS_MAX_HISTORY` | `500` | Max number of requests to retain |
| `TORVALDS_STATS_FORMAT` | `compact` | Output format: `compact`, `detailed`, `json` |

### Cache Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_CACHE_PATH` | `~/.cache/torvalds/agent_cache.json` | Custom cache file location |

### Human-in-the-Loop Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_HITL_ENABLED` | `true` | Enable/disable HITL interactions |
| `TORVALDS_HITL_METHOD` | `console` | Input method: `console` or `whiptail` |
| `TORVALDS_HITL_TIMEOUT` | `-1` | Timeout in seconds. `-1` = **no timeout** (wait indefinitely) |
| `TORVALDS_HITL_DEFAULT_ANSWER` | `""` | Default fallback answer on timeout |
| `TORVALDS_HITL_RUNTIME_TOGGLE` | `true` | Enable/disable runtime toggle commands |

### APT Package Management Configuration

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_SUDO_PASSWORD` | — | Pre-set sudo password for APT operations |
| `TORVALDS_DEFAULT_PROMPT_METHOD` | `console` | Password prompt method: `console`, `whiptail`, `env_var`, `parameter` |

---

## 8. Run the Agent

```bash
source .venv/bin/activate

# Classic linear REPL
python agent-torvalds.py

# Multi-window TUI
python agent-torvalds-mw.py
```

### Useful CLI Flags

```bash
python agent-torvalds.py --log-level DEBUG     # verbose logging on stderr
python agent-torvalds.py --no-stats            # hide per-request statistics
python agent-torvalds.py --project-path .      # load current directory as a project
python agent-torvalds.py --full                # load all tools upfront (no embedding model needed)
python agent-torvalds.py --select              # interactive tool picker (no embedding model needed)
python agent-torvalds.py --top-k 12            # retrieve 12 tools per query instead of 8
python agent-torvalds.py --no-chat-history     # disable ChatHistoryManager
python agent-torvalds.py --no-session-select   # skip startup session selection
python agent-torvalds.py --no-tui              # force classic REPL (multi-window variant)
```

> **Note**: The **first** request is slow — Ollama loads the model into RAM/VRAM on the first call. A 16 GB model on CPU-only hardware can take a minute or more. Subsequent requests reuse the resident model.

---

## 9. Verify the Full Chain

### Chat Model

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
  "prompt": "Reply with exactly: OK",
  "stream": false
}'
```

### Embedding Model

```bash
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "hello world"
}'
```

### Through the Agent's Own Client

```bash
source .venv/bin/activate
python - <<'PY'
from llama_index.llms.ollama import Ollama
from llama_index.core.base.llms.types import ChatMessage
from components.ollama_config import get_ollama_base_url

print("endpoint:", get_ollama_base_url())
llm = Ollama(
    model="richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
    base_url=get_ollama_base_url(),
    request_timeout=300
)
print(llm.chat([ChatMessage(role="user", content="Reply with exactly: OK")]).message.content)
PY
```

Both endpoints must respond before starting the agent.

---

## 10. Model Catalogue and Hardware Sizing

| Model | Disk | RAM/VRAM (Q4) | Notes |
|---|---|---|---|
| `qwen2.5-coder:7b-instruct-q4_K_M` | 4.7 GB | ~6 GB | Fastest, smallest machines |
| `richardyoung/qwen3-8b-abliterated:Q4_K_M` | 5.0 GB | ~7 GB | — |
| `richardyoung/qwen2.5-coder-14b-instruct-abliterated:Q4_K_M` | 9.0 GB | ~12 GB | Good balance |
| `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | 16 GB | ~20 GB | Default, best quality |
| `richardyoung/qwen3.6-27b-abliterated:latest` | 16 GB | ~20 GB | Same model, different tag |
| `north-mini-code-1.0:latest` | 18 GB | ~22 GB | — |
| `qwen3-coder:latest` | 18 GB | ~22 GB | — |
| `nomic-embed-text:latest` | 274 MB | ~0.3 GB | Embeddings only |

The RAM/VRAM figure includes the model size plus KV cache and runtime overhead.

---

## 11. Startup Modes

| Command | Behaviour |
|---|---|
| `python agent-torvalds.py` | **Default**: on-demand tool retrieval, top-8 tools per query. **Needs `nomic-embed-text`.** |
| `python agent-torvalds.py --full` | All tools loaded upfront. No embedding model needed. |
| `python agent-torvalds.py --select` | Interactive tool picker. No embedding model needed. |
| `python agent-torvalds.py --top-k 12` | Retrieve 12 tools per query instead of 8. |

---

## 12. Configuration Reference

### Chat History Manager

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_STORAGE_URI` | derived from `TORVALDS_PG_*` | SQLAlchemy URI for `users` / `chat_sessions` tables |
| `TORVALDS_STORAGE_FALLBACK_URI` | `sqlite:///~/.torvalds/chat_manager.db` | Local DB when primary is unreachable |
| `TORVALDS_STORAGE_FALLBACK` | *(enabled)* | Set to `off` to disable local fallback |
| `TORVALDS_LLAMA_URI` | `postgres+asyncpg://…/llama_index_db` | LlamaIndex chat-store URI for message bodies |
| `TORVALDS_PG_HOST` | `127.0.0.1` | PostgreSQL host |
| `TORVALDS_PG_PORT` | `5432` | PostgreSQL port |
| `TORVALDS_PG_USER` | `postgres` | PostgreSQL user |
| `TORVALDS_PG_PASSWORD` | `postgres` | PostgreSQL password |
| `TORVALDS_PG_DATABASE` | `llama_index_db` | PostgreSQL database name |
| `TORVALDS_CHAT_KEY` | — | Legacy single chat key (reused as General session's `chat_key`) |

---

## 13. Database Configuration

### PostgreSQL

Edit `db_toolkit_config.yaml`:

```yaml
postgres:
  host: 127.0.0.1
  port: 5432
  user: postgres
  password: your_password
  database: your_database
```

### MySQL

```yaml
mysql:
  host: 127.0.0.1
  port: 3306
  user: root
  password: your_password
  database: your_database
```

---

## 14. Optional Toolkit Configuration

### MikroTik RouterOS

Copy the example and fill in real targets:

```bash
cp mikrotik_targets.yaml.example mikrotik_targets.yaml
```

`mikrotik_targets.yaml` is in `.gitignore` — real credentials never reach the repository.

| Variable | Default | Description |
|---|---|---|
| `MIKROTIK_TARGETS` | `mikrotik_targets.yaml` | Path of the target configuration file |
| `MIKROTIK_PASSWORD` | — | Fallback password for targets without one |
| `MIKROTIK_KEY` | — | Fallback private-key path |
| `MIKROTIK_SKIP_APPROVAL` | `false` | Skip human approval for HIGH/CRITICAL commands |

### Shodan Toolkit

```bash
pip install "shodan>=1.31" "setuptools<81"
shodan init <your-api-key>     # writes ~/.config/shodan/api_key (mode 0600)
```

| Variable | Default | Description |
|---|---|---|
| `SHODAN_TOOLKIT_API_KEY` | — | API key (also accepts `SHODAN_API_KEY`) |
| `SHODAN_TOOLKIT_EXECUTABLE` | `shodan` | Path to the Shodan CLI |
| `SHODAN_TOOLKIT_TIMEOUT` | `120` | Per-command timeout in seconds |
| `SHODAN_TOOLKIT_MAX_RESULTS` | `100` | Default result cap for searches |
| `SHODAN_TOOLKIT_CONFIG` | `~/.config/shodan-toolkit/config.json` | Toolkit config file |
| `TORVALDS_SHODAN_ALLOW_MUTATING` | unset | Expose write-capable tools. **Off by default.** |

---

## 15. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` / `Could not reach Ollama` | Server not running | `ollama serve` or `sudo systemctl start ollama` |
| `model '...' not found` (404) | Model never pulled or wrong tag | `ollama pull <model>` — tag must match `ollama list` exactly |
| `nomic-embed-text` not found | Embedding model missing | `ollama pull nomic-embed-text` |
| `address already in use ... 11434` | Ollama instance already listening | It is already running — check `ollama list` |
| First answer takes minutes | Model loading into memory | Expected on first call; `ollama ps` shows what is resident |
| Process killed / out of memory | Model does not fit | Use a smaller model, or `ollama stop <model>` to unload |
| Answers are slow | Running on CPU only | Use a smaller model, or give Ollama GPU acceleration |
| Agent starts but every request fails | Wrong endpoint | Check `TORVALDS_OLLAMA_HOST` and `curl http://localhost:11434/api/version` |
| Agent hangs on first query | Model loading or timeout too low | Raise `TORVALDS_REQUEST_TIMEOUT` |
| Agent cannot import `agent_tool_retriever` | Embedding client missing | `pip install -r requirements.txt` |

Check what the agent actually uses:

```bash
python -c "from components.ollama_config import get_ollama_base_url; print(get_ollama_base_url())"
```

---

## 16. Housekeeping

```bash
ollama ps                  # models currently loaded into memory
ollama stop <model>        # unload a model and free RAM/VRAM
ollama rm <model>          # delete a model from disk
ollama list                # models installed on disk
```

The agent's operational cache (`~/.cache/torvalds/agent_cache.json`, overridable with `TORVALDS_CACHE_PATH`) is unrelated to the Ollama models and is not affected by `ollama rm`.

---

## 17. Automated Deployment Script

`deploy/deploy-torvalds.sh` performs the steps in sections 3, 5 and 6 in
one pass: system packages, the Python virtual environment, Ollama with the
models, and a starter `.env`.

```bash
cd agent-torvalds
./deploy/deploy-torvalds.sh --non-interactive
```

**Run it from the project root** — it looks for `requirements.txt` and
`setup_postgres_db.sql` in the current directory. Use `--deploy-dir` to
point it somewhere else.

The script needs no Python of its own: it installs one. A machine without
a usable interpreter is exactly what it exists to fix.

### Choosing a model that fits the machine

The default chat model is the 27B one, which needs about 20 GB of RAM. Pass
`--model` to select a smaller one:

```bash
./deploy/deploy-torvalds.sh \
    --non-interactive \
    --model richardyoung/qwen3-8b-abliterated:Q4_K_M
```

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

### Unattended runs

In `--non-interactive` mode the script cannot answer a `sudo` prompt, so it
needs the password up front:

```bash
export SUDO_PASSWORD='...'
./deploy/deploy-torvalds.sh --non-interactive
```

`SUDO_PASSWORD_FILE` points at a file that holds the password on its first
line, which keeps the secret out of the environment. Alternatively, run the
script as root, or prime the sudo cache with `sudo -v` first.

> `sudo` keys its cached timestamp on the terminal, so a cache created by
> the calling shell is **not** visible to the script. The script therefore
> establishes its own timestamp, from `SUDO_PASSWORD` or
> `SUDO_PASSWORD_FILE`, when it needs one.

### The log file

The log goes to `/var/log/torvalds-deploy.log`, which only root may create.
A deployment run as an ordinary user therefore falls back to
`~/.torvalds/logs/torvalds-deploy.log` and says so. Pass `--log-file` to
choose the path yourself.

Every message the script emits goes to **stderr**, so a run can be piped
without the log lines ending up in the output. `--help` and `--version` are
the exception: they are queries, and they write to **stdout**.

### The generated `.env`

The script writes a `.env` with the variables the agent actually reads:

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

---

## Quick-Start Checklist

```
[ ] Install Ollama (curl script / brew / Docker / package manager)
[ ] Verify server: curl http://localhost:11434/api/version
[ ] Pull chat model: ollama pull richardyoung/qwen3.6-27b-abliterated:Q4_K_M
[ ] Pull embedding model: ollama pull nomic-embed-text
[ ] Clone repo: git clone git@github.com:KostiantynBushko/agent-torvalds.git
[ ] Create venv: python -m venv .venv && source .venv/bin/activate
[ ] Install deps: pip install -r requirements.txt
[ ] Run agent: python agent-torvalds.py
[ ] First request is slow (model loading) — this is normal
```
