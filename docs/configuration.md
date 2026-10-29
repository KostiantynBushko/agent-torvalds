# The configuration file

The agent had **forty-five environment variables** and no file. A shell
profile is a poor home for forty-five settings: it is loaded into every
shell, it is shared with every other program, and it cannot hold a comment
that explains what a value is for.

This document is about the configuration file — `~/.config/torvalds/config.toml` —
what it holds, where it sits in the order of things, and what it does
when it is broken.

---

## Table of Contents

1. [The quick start](#1-the-quick-start)
2. [The location](#2-the-location)
3. [The order of things](#3-the-order-of-things)
4. [What the file holds](#4-what-the-file-holds)
5. [The template](#5-the-template)
6. [`\config` — where every value came from](#6-config--where-every-value-came-from)
7. [What the file must not hold](#7-what-the-file-must-not-hold)
8. [The toolkit configuration files](#8-the-toolkit-configuration-files)
9. [What happens when the file is broken](#9-what-happens-when-the-file-is-broken)
10. [The environment variables](#10-the-environment-variables)
11. [Verifying the installation](#11-verifying-the-installation)

---

## 1. The quick start

```console
$ python agent-torvalds.py --write-default-config
The configuration template was written to /home/kbush/.config/torvalds/config.toml
Uncomment a line and change the value to make it yours.

$ $EDITOR ~/.config/torvalds/config.toml

$ python agent-torvalds.py
```

The agent announces what it found at startup:

```
Logging: INFO
Config file: /home/kbush/.config/torvalds/config.toml
```

---

## 2. The location

```
~/.config/torvalds/config.toml
```

That is the **XDG Base Directory** standard — `$XDG_CONFIG_HOME` when it is
set, `~/.config` otherwise. It completes the triad the project already
keeps:

| | |
|---|---|
| `~/.config/torvalds/config.toml` | the operator's **intent** — this file |
| `~/.torvalds/chat_manager.db` | what the agent **produced** |
| `~/.torvalds/logs/` | what the agent **produced** |
| `~/.cache/torvalds/agent_cache.json` | what the agent **produced** |

The data does not move. A database and a rotating log are not
configuration — they are what the agent wrote — and moving the chat
history would break the sessions of everybody who already has one.

`TORVALDS_CONFIG` points the agent at another file. It exists for the
tests, for a second installation, and for the operator who keeps the
configuration of several machines in one place.

```console
$ TORVALDS_CONFIG=~/work/torvalds.toml python agent-torvalds.py
```

---

## 3. The order of things

Four layers decide what the agent does:

```
flag  >  environment variable  >  config file  >  built-in default
```

**The file sits below the environment variables**, and that is the
important part of the decision.

Every operator who has been running this agent has environment variables
in their shell profile. A configuration file that outranked them would
change the behaviour of every one of them the moment they upgraded — a
different model, a different host, silently. With the file underneath:

- an operator with **no file** sees **no change at all**;
- an operator with **both** keeps the environment variables winning;
- the file becomes the *"set it once, in one place"* layer.

The flag is still the strongest — it is what the operator types on the
command line, and it is what the command line is for.

---

## 4. What the file holds

```toml
[llm]
model = "minimax-m3.1-flash:cloud"
host = "http://localhost:11434"
context_length = 8192
max_iterations = 2000
request_timeout = 99999

[agent]
top_k = 8
event_streaming = true
verbose_events = false
prompt_injection = true
tool_recommendations = true
prompt_template = "~/prompts/torvalds.md"
context_guard = false

[hitl]
enabled = true
method = "console"
timeout = -1
default_answer = ""
runtime_toggle = true

[stats]
enabled = true
format = "compact"
verbose = false
persist = true
max_history = 500

[logging]
level = "INFO"
file = "agent.log"
dir = "~/.torvalds/logs"
max_size = "10MB"
max_files = 5
symlink = "agent-current.log"
```

Five sections: **`llm`**, **`agent`**, **`hitl`**, **`stats`** and
**`logging`**. Every setting is documented in `--write-default-config`,
with the environment variable that overrides it.

The names are the dotted names the `\config` command prints: `llm.model`
is `[llm] model = ...`, and `hitl.timeout` is `[hitl] timeout = ...`.

Every setting keeps the **environment variable it already had** — the
file did not rename them, because a variable that existed before the
file did must not change its meaning. `TORVALDS_MODEL` still wins over
`[llm] model`, and `TORVALDS_HITL_TIMEOUT` still wins over
`[hitl] timeout`.

---

## 5. The template

### The agent writes it for itself

The agent creates the file **when it starts**, if it is not there yet:

```console
$ python agent-torvalds.py
Config file: /home/kbush/.config/torvalds/config.toml
The configuration template was created at /home/kbush/.config/torvalds/config.toml — every setting in it is commented out, so the defaults are used
```

The template carries **no settings** — every one of its lines is a
comment — so the file changes **nothing** about the way the agent runs.
It is a starting point to edit, not a change of behaviour.

Three rules about it:

| | |
|---|---|
| **Only the default location.** | A file the operator named with `TORVALDS_CONFIG` is theirs: they pointed at it on purpose, and the agent does not create it. |
| **Never an overwrite.** | If the file is there, it is left exactly as it is — the operator's own settings are worth more than a fresh copy of the defaults. |
| **Never fatal.** | A home directory that cannot be written to is a warning, and the agent boots with the defaults. |

The creation belongs to the **startup**, not to the import: a module that
wrote into the home directory when it was imported would litter every
process that imports it.

### Writing it by hand

```console
$ python agent-torvalds.py --write-default-config
```

writes the same **commented** file: every setting, its default, the
environment variable that overrides it and one line of explanation.
Uncomment a line, change the value, and it is yours.

Three things about the write are deliberate:

| | |
|---|---|
| **The file is created with the mode `0600`.** | Not chmod'ed afterwards — created that way. A file that is briefly readable by every account on the box is a file that was exposed. |
| **An existing file is not overwritten.** | The template is a starting point, and the settings the operator wrote into it are worth more than a fresh copy of the defaults. Running the command twice does not throw away what was written in between — the agent says so and stops. |
| **A symbolic link is never written through.** | The link and the file it points at are two different things, and only the operator knows which one they meant. |

---

## 6. `\config` — where every value came from

Four layers without provenance is a debugging nightmare. When a setting is
not what the operator expected, the only useful question is *"which layer
won?"* — and it has to have an answer.

```
>>> \config
                              The effective configuration
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ setting                    ┃ value                  ┃ source                                       ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ llm.model                  │ from-the-file:q4       │ config file /home/kbush/.config/torvalds/…    │
│ llm.max_iterations         │ 2000                   │ environment variable TORVALDS_MAX_ITERATIONS │
│ llm.host                   │ http://localhost:11434 │ default                                      │
│ hitl.timeout               │ 99                     │ config file /home/kbush/.config/torvalds/…    │
└────────────────────────────┴────────────────────────┴──────────────────────────────────────────────┘
The configuration file: /home/kbush/.config/torvalds/config.toml
```

The command works in the classic REPL and in the multi-window TUI — the
TUI renders it into the document pane.

---

## 7. What the file must not hold

**Secrets.** The database password is an environment variable today, and
that is the right call: a file is easier to copy around, and `0600` on a
config file is a promise, not a guarantee. Put the secret in the
environment.

**Anything that changes per run** — a session id, a project path, a
scratch file. The configuration is read once, when the agent starts.

---

## 8. The toolkit configuration files

Two toolkits read a YAML file of their own:

| Toolkit | File | Found in the config directory? |
|---|---|---|
| the MikroTik toolkit | `mikrotik_targets.yaml` | **yes** |
| the database toolkit | `db_toolkit_config.yaml` | **no** — see below |

The MikroTik file used to be found in the **working directory only**,
which meant it was found when the agent was started from the repository
root and nowhere else. The agent's configuration directory is now the
second place to look:

```
1. the working directory   — the developer keeps working as before
2. ~/.config/torvalds/     — the operator's own configuration
```

The **database toolkit keeps its behaviour**, and that is deliberate.
Its own verification — `toolkits/db-toolkit/tests/test_split_verification.py`
— proves that the library half is **behaviour-neutral**: it compares it,
line by line, with the original script the package was split out of, and
a second search path is a difference the proof cannot accept. Relaxing
that proof to accommodate a convenience is the wrong trade, so the
database file is still found in the working directory.

Both files keep their own format — YAML — because that is what they have
always been, and migrating them is a separate piece of work.

---

## 9. What happens when the file is broken

**Nothing stops.** A missing file is not an error — it is the normal
state of a fresh installation. A broken file is a **warning**, and the
agent boots with the defaults.

| Problem | What happens |
|---|---|
| The file is absent | The defaults are used. Nothing is printed but the announcement. |
| The file is not valid TOML | A warning with the line and the column. The defaults are used. |
| A section the agent does not know | A warning. The section is ignored. |
| A setting the agent does not know | A warning. The setting is ignored. |
| A value of the wrong type | A warning. The default of that setting is used. |
| A value outside the choices of the setting | A warning. The default is used. |

A typo must be **visible**. A setting the agent silently ignores is a
setting the operator believes in and that does nothing.

The problems are printed by `\config`, and they are reported **once** —
not again every time the setting is resolved.

---

## 10. The environment variables

The file did not replace them. They are still the layer above the file,
and they are still the right place for a secret.

| Section | The variables |
|---|---|
| `llm` | `TORVALDS_MODEL`, `TORVALDS_OLLAMA_HOST`, `OLLAMA_HOST`, `TORVALDS_CONTEXT_LENGTH`, `TORVALDS_MAX_ITERATIONS`, `TORVALDS_REQUEST_TIMEOUT` |
| `agent` | `TORVALDS_SIMILARITY_TOP_K`, `TORVALDS_EVENT_STREAMING`, `TORVALDS_VERBOSE_EVENTS`, `TORVALDS_PROMPT_INJECTION`, `TORVALDS_INCLUDE_RECOMMENDATIONS`, `TORVALDS_PROMPT_TEMPLATE`, `TORVALDS_CONTEXT_GUARD` |
| `hitl` | `TORVALDS_HITL_ENABLED`, `TORVALDS_HITL_METHOD`, `TORVALDS_HITL_TIMEOUT`, `TORVALDS_HITL_DEFAULT_ANSWER`, `TORVALDS_HITL_RUNTIME_TOGGLE` |
| `stats` | `TORVALDS_STATS_ENABLED`, `TORVALDS_STATS_FORMAT`, `TORVALDS_STATS_VERBOSE`, `TORVALDS_STATS_PERSIST`, `TORVALDS_STATS_MAX_HISTORY` |
| `logging` | `TORVALDS_LOG_FILE`, `TORVALDS_LOG_DIR`, `TORVALDS_LOG_MAX_SIZE`, `TORVALDS_LOG_MAX_FILES`, `TORVALDS_LOG_SYMLINK` |

---

## 11. Verifying the installation

```bash
# The unit tests.
self-development/.venv/bin/python -m pytest self-development/tests/test_config.py -v

# The CI gate — a new failure breaks the build, a known one does not.
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

The module is `components/config.py`, and the rendering of the effective
configuration is `components/config_view.py`.
