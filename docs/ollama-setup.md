# Local LLM Setup (Ollama)

Torvalds has no cloud fallback. Every request is served by a local
[Ollama](https://ollama.com) instance, and the agent needs **two** models:

| Purpose | Model | Required for | Download |
|---|---|---|---|
| Chat & tool calling | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` (default) | every run | ~16 GB |
| Embeddings | `nomic-embed-text` | the default tool-retrieval mode | ~274 MB |

The embedding model is only needed in the **default (retriever) mode**. With
`--full` or `--select` the agent loads the tools directly and never builds the
vector index, so `nomic-embed-text` can be skipped.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Install Ollama](#2-install-ollama)
3. [Run and verify the server](#3-run-and-verify-the-server)
4. [Pull the models](#4-pull-the-models)
5. [Configure the agent](#5-configure-the-agent)
6. [Run the agent](#6-run-the-agent)
7. [Verify the whole chain](#7-verify-the-whole-chain)
8. [Model catalogue and hardware sizing](#8-model-catalogue-and-hardware-sizing)
9. [Troubleshooting](#9-troubleshooting)
10. [Housekeeping](#10-housekeeping)

---

## 1. Overview

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

- `llama_index.llms.ollama.Ollama` - the chat model
- `llama_index.embeddings.ollama.OllamaEmbedding` - the embedding model,
  configured globally in `agent_tool_retriever.py` through
  `Settings.embed_model`

Both clients are pointed at the same endpoint by
`components/ollama_config.py`.

---

## 2. Install Ollama

### Linux

The install script downloads the binary into `/usr/local/bin/ollama` and, on
systems with `systemd`, registers and starts an `ollama.service`:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Check the service:

```bash
sudo systemctl status ollama
sudo systemctl start ollama     # if it is not running yet
```

To make Ollama reachable from other machines in the network, bind it to all
interfaces by putting this into the service environment:

```bash
sudo systemctl edit ollama
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

### macOS

```bash
brew install ollama
```

Or download `Ollama-darwin.zip` from <https://ollama.com/download> and open
the app - the app starts the server for you. On a headless machine run
`ollama serve` yourself.

### Windows

Download `OllamaSetup.exe` from <https://ollama.com/download> and run it. The
tray app starts the server automatically; the binary lands in
`%LOCALAPPDATA%\Programs\Ollama`.

### Docker

```bash
docker run -d \
  -v ollama:/root/.ollama \
  -p 11434:11434 \
  --name ollama \
  ollama/ollama
```

The named volume keeps the pulled models across container restarts. Models are
pulled from inside the container:

```bash
docker exec -it ollama ollama pull nomic-embed-text
```

### Arch Linux / Fedora

```bash
sudo pacman -S ollama       # Arch
sudo dnf install ollama      # Fedora
sudo systemctl enable --now ollama
```

---

## 3. Run and verify the server

Ollama listens on `http://localhost:11434` by default.

```bash
curl http://localhost:11434/api/version
# {"version":"0.33.2"}
```

The models that are installed locally:

```bash
ollama list
```

```
NAME                                                     ID              SIZE      MODIFIED
richardyoung/qwen3.6-27b-abliterated:Q4_K_M              331499cb5960   16 GB     5 weeks ago
nomic-embed-text:latest                                  0a109f422b47   274 MB    6 weeks ago
```

An empty table means no model has been pulled yet.

If the server was started by hand (not as a service), it runs in the
foreground:

```bash
ollama serve
```

---

## 4. Pull the models

```bash
# Chat model - the default the agent expects (~16 GB)
ollama pull richardyoung/qwen3.6-27b-abliterated:Q4_K_M

# Embedding model - required by the default tool-retrieval mode (~274 MB)
ollama pull nomic-embed-text

# Confirm
ollama list
```

A model name is only accepted when it matches `ollama list` **exactly**,
including the tag. `richardyoung/qwen3.6-27b-abliterated` and
`richardyoung/qwen3.6-27b-abliterated:Q4_K_M` are the same model, but only
the second one is a valid `ollama pull` target if that is the tag that is
installed.

The first pull downloads several gigabytes; the progress is printed per
layer. Re-running the command on an already pulled model is a no-op.

---

## 5. Configure the agent

| Variable | Default | Description |
|---|---|---|
| `TORVALDS_MODEL` | `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | Chat model served by Ollama |
| `TORVALDS_OLLAMA_HOST` | `http://localhost:11434` | Endpoint of the Ollama server |
| `OLLAMA_HOST` | - | Fallback for `TORVALDS_OLLAMA_HOST` |
| `TORVALDS_REQUEST_TIMEOUT` | `99999` | LLM request timeout in seconds |
| `TORVALDS_MAX_ITERATIONS` | `50` | Maximum tool-calling iterations per request |
| `TORVALDS_SIMILARITY_TOP_K` | `8` | Number of tools retrieved per query |

The default model is the one pulled in step 4, so in the common case nothing
has to be configured:

```bash
python agent-torvalds.py
```

A different model:

```bash
export TORVALDS_MODEL="qwen2.5-coder:7b-instruct-q4_K_M"
python agent-torvalds.py
```

or inline, for a single run:

```bash
TORVALDS_MODEL=qwen2.5-coder:7b-instruct-q4_K_M python agent-torvalds.py
```

A non-default endpoint:

```bash
export TORVALDS_OLLAMA_HOST="http://192.168.1.10:11434"
```

A bare `host:port` is accepted - the `http://` scheme is added automatically.
`TORVALDS_OLLAMA_HOST` takes precedence over `OLLAMA_HOST`, so a server that
binds to `0.0.0.0:11434` (which is what `OLLAMA_HOST` usually holds) does not
accidentally break the client configuration.

---

## 6. Run the agent

```bash
source .venv/bin/activate

# Classic linear REPL
python agent-torvalds.py

# Multi-window TUI
python agent-torvalds-mw.py
```

Startup modes:

| Command | Behaviour |
|---|---|
| `python agent-torvalds.py` | Default: on-demand tool retrieval, top-8 tools per query. **Needs `nomic-embed-text`.** |
| `python agent-torvalds.py --full` | All tools are loaded upfront. No embedding model needed. |
| `python agent-torvalds.py --select` | Interactive tool picker. No embedding model needed. |
| `python agent-torvalds.py --top-k 12` | Retrieve 12 tools per query instead of 8. |

The **first** request is slow: Ollama loads the model into RAM/VRAM on the
first call. A 16 GB model on CPU-only hardware can take a minute or more.
Subsequent requests reuse the resident model.

Useful flags while you get comfortable:

```bash
python agent-torvalds.py --log-level DEBUG     # verbose logging on stderr
python agent-torvalds.py --no-stats            # hide the per-request statistics
python agent-torvalds.py --project-path .      # load the current directory as a project
```

---

## 7. Verify the whole chain

Before blaming the agent, check Ollama directly.

**Chat model:**

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
  "prompt": "Reply with exactly: OK",
  "stream": false
}'
```

**Embedding model:**

```bash
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "hello world"
}'
```

**Through the agent's own client** (uses the same code path as the agent):

```bash
source .venv/bin/activate
python - <<'PY'
from llama_index.llms.ollama import Ollama
from llama_index.core.base.llms.types import ChatMessage
from components.ollama_config import get_ollama_base_url

print("endpoint:", get_ollama_base_url())
llm = Ollama(model="richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
             base_url=get_ollama_base_url(), request_timeout=300)
print(llm.chat([ChatMessage(role="user", content="Reply with exactly: OK")]).message.content)
PY
```

---

## 8. Model catalogue and hardware sizing

| Model | Disk | RAM/VRAM needed (Q4) | Notes |
|---|---|---|---|
| `qwen2.5-coder:7b-instruct-q4_K_M` | 4.7 GB | ~6 GB | fastest, smallest machines |
| `richardyoung/qwen3-8b-abliterated:Q4_K_M` | 5.0 GB | ~7 GB | |
| `richardyoung/qwen2.5-coder-14b-instruct-abliterated:Q4_K_M` | 9.0 GB | ~12 GB | good balance |
| `richardyoung/qwen3.6-27b-abliterated:Q4_K_M` | 16 GB | ~20 GB | default, best quality |
| `richardyoung/qwen3.6-27b-abliterated:latest` | 16 GB | ~20 GB | same model, different tag |
| `north-mini-code-1.0:latest` | 18 GB | ~22 GB | |
| `qwen3-coder:latest` | 18 GB | ~22 GB | |
| `nomic-embed-text:latest` | 274 MB | ~0.3 GB | embeddings only |

The numbers are the Q4_K_M sizes; the RAM/VRAM figure is the size of the
model plus the KV cache and the runtime overhead.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` / `Could not reach Ollama` | the server is not running | `ollama serve`, or `sudo systemctl start ollama` |
| `model '...' not found` (404) | the model was never pulled, or the tag is wrong | `ollama pull <model>` - the tag must match `ollama list` exactly |
| `nomic-embed-text` not found | the embedding model is missing | `ollama pull nomic-embed-text` |
| `address already in use ... 11434` | an Ollama instance is already listening | it is already running - check `ollama list` |
| The first answer takes minutes | the model is being loaded into memory | expected on the first call; `ollama ps` shows what is resident |
| The process is killed / out of memory | the model does not fit | use a smaller model, or `ollama stop <model>` to unload |
| Answers are slow | running on CPU only | smaller model, or give Ollama GPU acceleration |
| The agent starts but every request fails | wrong endpoint | check `TORVALDS_OLLAMA_HOST` and `curl http://localhost:11434/api/version` |
| The agent hangs on the first query | the model is loading, or the request timeout is too low | raise `TORVALDS_REQUEST_TIMEOUT` |
| The agent cannot import `agent_tool_retriever` | the embedding client is missing | `pip install -r requirements.txt` (pulls `llama-index-embeddings-ollama`) |

Check what the agent actually uses:

```bash
python -c "from components.ollama_config import get_ollama_base_url; print(get_ollama_base_url())"
```

---

## 10. Housekeeping

```bash
ollama ps                  # models currently loaded into memory
ollama stop <model>        # unload a model and free the RAM/VRAM
ollama rm <model>          # delete a model from disk
ollama list                # models installed on disk
```

The agent also keeps its own operational state in the cache file
(`~/.cache/torvalds/agent_cache.json` by default, overridable with
`TORVALDS_CACHE_PATH`). That cache is unrelated to the models and is not
affected by `ollama rm`.
