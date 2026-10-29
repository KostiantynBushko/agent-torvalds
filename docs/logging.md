# Logging to a file

The agent logs to **stderr** by default, and that is all it does. This
document is about the second option: writing the log into a **file**, with
a **rotation** at a predefined size and a **symlink to the current log
file** next to the rotated ones.

The operator asked for it on 2026-10-27:

> *"I want be able to redirect logging into file, this solution must have a
> posibility to rotare log when reaching current log file predefined size.
> Inside directory we must have soft link to current log file the files"*

---

## Table of Contents

1. [Quick start](#1-quick-start)
2. [What the directory looks like](#2-what-the-directory-looks-like)
3. [The flags](#3-the-flags)
4. [The environment variables](#4-the-environment-variables)
5. [The size limit](#5-the-size-limit)
6. [The symlink](#6-the-symlink)
7. [The file mode](#7-the-file-mode)
8. [The tee](#8-the-tee)
9. [What degrades and what does not](#9-what-degrades-and-what-does-not)
10. [The known limitations](#10-the-known-limitations)
11. [Verifying the installation](#11-verifying-the-installation)

---

## 1. Quick start

```bash
# The log goes into ~/.torvalds/logs/agent.log, rotates at 10MB and
# keeps five generations.
python agent-torvalds.py --log-file agent.log

# A size, a number of generations and a directory of your own.
python agent-torvalds.py \
    --log-file agent.log \
    --log-dir /var/log/torvalds \
    --log-max-size 50MB \
    --log-max-files 10

# The same for the multi-window agent.
python agent-torvalds-mw.py --log-file agent.log
```

Without `--log-file` (and without `TORVALDS_LOG_FILE`) **nothing changes**:
the agent logs to stderr exactly as it always did. A file that nobody asked
for is a file nobody cleans up.

---

## 2. What the directory looks like

```
~/.torvalds/logs/
├── agent.log                    the current log file — a real file
├── agent-current.log -> agent.log  the symlink to the current log file
├── agent.log.1                  the previous generation
├── agent.log.2
├── agent.log.3
├── agent.log.4
└── agent.log.5
```

The directory follows the convention the project already uses:
`~/.torvalds/chat_manager.db` for the chat history and
`~/.cache/torvalds/agent_cache.json` for the cache. The log belongs next
to the chat history and **not** in the working tree — the agent runs from
wherever it is started, and a `logs/` directory in the project would be a
file that must be git-ignored.

The whole directory is created on demand; the *log file* inside it is
`0600` (see [§7](#7-the-file-mode)).

---

## 3. The flags

| Flag | Default | What it does |
|---|---|---|
| `--log-file PATH` | *off* | The log file. A bare name goes into the log directory. |
| `--log-dir DIR` | `~/.torvalds/logs` | The directory that holds the log, the symlink and the rotated files. |
| `--log-max-size SIZE` | `10MB` | The size at which the log is rotated. |
| `--log-max-files N` | `5` | How many generations are kept. `0` is refused. |
| `--log-symlink NAME` | `<stem>-current.log` | The name of the symlink.  The word `none` turns the pointer off. |

The flags exist in **both** orchestrators — `agent-torvalds.py` and
`agent-torvalds-mw.py` — and their defaults are pinned by the parity test.

A `--log-file` that carries a directory of its own (`/var/log/torvalds.log`)
is used as it is; a **bare name** goes into `--log-dir`.

---

## 4. The environment variables

| Variable | Flag | Default |
|---|---|---|
| `TORVALDS_LOG_FILE` | `--log-file` | *off* |
| `TORVALDS_LOG_DIR` | `--log-dir` | `~/.torvalds/logs` |
| `TORVALDS_LOG_MAX_SIZE` | `--log-max-size` | `10MB` |
| `TORVALDS_LOG_MAX_FILES` | `--log-max-files` | `5` |
| `TORVALDS_LOG_SYMLINK` | `--log-symlink` | `<stem>-current.log` |

The variables matter for the runs the agent does not start itself — a
`systemd` unit, a `supervisord` program, a shell profile.

The order is the one the project already uses for `TORVALDS_OLLAMA_HOST`
(see `components/ollama_config.py`): the **environment variable** first,
the **flag** second, and **the flag wins**.

```bash
# The environment turns it on ...
TORVALDS_LOG_FILE=agent.log python agent-torvalds.py

# ... and the flag overrides the environment.
TORVALDS_LOG_FILE=agent.log python agent-torvalds.py --log-file other.log
```

---

## 5. The size limit

The size is written the way an operator writes it: `--log-max-size 10MB`,
not `--log-max-size 10485760`.

| Unit | Bytes |
|---|---|
| `B` | 1 |
| `KB` | 1024 |
| `MB` | 1024² |
| `GB` | 1024³ |

The one-letter forms (`K`, `M`, `G`) work too, and so does a plain number
(it is a number of bytes).

A unit nobody knows is a **typo that is reported**:

```
$ python agent-torvalds.py --log-max-size 10MBB
agent-torvalds.py: error: argument --log-max-size: unknown size unit 'MBB'
in '10MBB' — use B, KB, MB or GB
```

The agent **stops**. A log that never rotates because the size was not
understood is the exact failure this feature exists to prevent, so a typo
is not a degradation.

**The limit is soft.** The handler checks the size *before* it writes a
record, so the live file can exceed the limit by the size of the record
that crossed it. A hard limit would mean truncating a record in half, and
a log that ends in the middle of a line is worse than a log that is 200
bytes over.

---

## 6. The symlink

The symlink points at the **path** of the live log file, not at its inode.
That single decision is what makes the whole thing work.

`RotatingFileHandler.doRollover()` renames `agent.log` to `agent.log.1`
and then reopens `agent.log`. **The path does not change — the file at it
does.** A symlink to `agent.log` is therefore valid at every moment,
before and after every rotation, and it never has to be re-pointed. A
symlink to an *inode* would have been dangling for an instant at every
rotation.

The symlink is created **atomically**: the new link is built beside the
old one and moved into place with `os.replace()`, so a reader never sees a
half-written link.

The one thing that does need maintenance is a symlink somebody deleted
while the agent was running. The handler re-asserts it after every
rollover, so it comes back.

```bash
# Follow the current log, whatever generation it is.
tail -f ~/.torvalds/logs/agent-current.log
```

---

## 7. The file mode

The log file is `0600` — owner only.

The standard library creates the file with `0666 & ~umask`, which is
`0664` on this machine. A log of this agent carries the system prompt, the
user's requests, the tool output and the model's answers, so it must not
be readable by every account on the box. The handler corrects the mode on
the first open and after every rollover.

---

## 8. The tee

The file **joins** the terminal; it does not replace it. The stderr
handler stays, so the operator still sees the output while the run, and
the file carries the history afterwards.

This was the operator's decision on 2026-10-29:

> *"no let him write to the stderr we can also redirect it into file under
> torvalds log directory"*

---

## 9. What degrades and what does not

The project's rule is that a missing feature **degrades** — it does not
take the agent down.

| Failure | What happens |
|---|---|
| The log directory cannot be created | A warning, the stderr logging continues, the agent boots. |
| The log file cannot be opened | A warning, the stderr logging continues, the agent boots. |
| The symlink cannot be created (Windows without the symlink privilege, a filesystem without symlinks) | A warning, the file logging continues. The symlink is a convenience, not the log. |
| The size cannot be parsed | The agent **stops** with the message. A typo is not a degradation. |
| `--log-max-files 0` | The agent **stops** with the message. Zero generations means no rotation at all, and the file grows until the disk is full. |

---

## 10. The known limitations

| Limitation | What it means |
|---|---|
| **Multi-process** | `RotatingFileHandler` has no cross-process lock. Two agents writing to the *same* log file can lose records at the moment of the rotation. Give every agent process its own `--log-file`, or a name that carries the PID. |
| **The size limit is soft** | The live file can exceed the limit by the record that crossed it. A record is never cut in half. |
| **No compression** | The rotated files are plain text. The disk use is already bounded by `size × (files + 1)`. |
| **No time-based rotation** | The rotation is by size only — that is what was asked for. |
| **The log is not redacted** | It carries the prompts, the tool output and the answers. The file is `0600` and it stays in the user's home directory. |

---

## 11. Verifying the installation

```bash
# The invariants of the design, against the shipped implementation.
self-development/.venv/bin/python \
    self-development/investigate/logging-to-file/verify_implementation.py

# The drift proof: seven deliberate breaks, each caught by the invariant
# it attacks.
self-development/.venv/bin/python \
    self-development/investigate/logging-to-file/verify_implementation_catches_regressions.py

# The unit tests.
self-development/.venv/bin/python -m pytest self-development/tests/test_file_logging.py -q
```

The investigation that started all of this — the report, the prototype and
the proofs — is in `investigate/logging-to-file/`.
