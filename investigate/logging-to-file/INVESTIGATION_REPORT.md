# Logging into a file, with a rotation and a symlink to the current log

## What the operator asked for

> I want be able to redirect logging into file, this solution must have a
> posibility to rotare log when reaching current log file predefined size.
> Inside directory we must have soft link to current log file the files

Three requirements, one directory:

1. the logging goes into a **file**;
2. the file is **rotated** when it reaches a **predefined size**;
3. the directory holds a **symlink to the current log file**, next to the
   rotated ones.

This folder is the investigation: the current state, the design, the
alternatives that were considered and rejected, the **working
prototype**, and the invariants that keep the design honest.

| Path | What it is |
|---|---|
| `prototype_file_logging.py` | The **working prototype** — the handler, the size parser, and a demonstration that writes, rotates and checks the symlink. |
| `verify_logging_to_file.py` | The **harness** — seven invariants, written against the public behaviour. |
| `verify_harness_catches_regressions.py` | The **drift proof** — seven deliberate breaks, each caught by the invariant it attacks. |

---

## The current state

There is **half** of this feature in the tree already, and it is
unreachable.

`agent-torvalds-mw.py` has had a `to_file` parameter on
`configure_logging()` since the multi-window work:

```python
def configure_logging(level_name: str = DEFAULT_LOG_LEVEL, to_file: Optional[str] = None) -> None:
    """Configure logging format and destination."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stderr)]
    if to_file:
        handlers.append(logging.FileHandler(to_file, encoding="utf-8"))
```

**No caller ever passes `to_file`.** Every call site is
`configure_logging(args.log_level)` — the parameter is dead code. The
classic orchestrator, `agent-torvalds.py`, has no file support at all:
its `configure_logging()` builds a `StreamHandler` and nothing else.

So the state is:

| | Classic (`agent-torvalds.py`) | Multi-window (`agent-torvalds-mw.py`) |
|---|---|---|
| Log to stderr | yes | yes |
| Log to a file | no | a `to_file` parameter that nothing reaches |
| Rotation | no | no |
| Symlink | no | no |
| A size limit | no | no |

Three things follow from that, and they shape the design:

* **The file handler is the wrong shape.** A plain `logging.FileHandler`
  never rotates. It writes until the disk is full, and a log that fills
  the disk takes the machine with it.
* **The rotation must be a size limit**, not a time limit — that is what
  the operator asked for, and it is also what a tool-using agent needs:
  a busy session writes megabytes in an afternoon and nothing at all
  overnight.
* **The stderr handler stays.** The file is a **tee**, not a
  replacement. The operator still sees the output in the terminal, and
  the file carries the history.

### Where the log is going today

The operator's current workaround is a shell redirect
(`python agent-torvalds.py >> agent.log 2>&1`). It has three problems
that this feature removes:

| The shell redirect | What this feature does instead |
|---|---|
| The file grows without a limit | It is rotated at a size the operator chooses |
| There is no "the current log" — the shell holds the file open and the path is the only name | There is a symlink to the current log file, next to the rotated ones |
| The log is created with the umask of the shell — `0664` here, readable by every account on the box | The log file is `0600`, always |

The third row is not a detail. A log of this agent carries the system
prompt, the user's requests, the tool output and the model's answers.

---

## The design

### The directory

```
~/.torvalds/logs/
├── agent.log                    the current log file — a real file
├── agent-current.log -> agent.log  the symlink to the current log file
├── agent.log.1                  the previous generation
├── agent.log.2
└── agent.log.3
```

The location follows the convention the project already uses:
`~/.torvalds/chat_manager.db` for the chat history, and
`~/.cache/torvalds/agent_cache.json` for the cache. The log belongs
next to the chat history, and **not** in the working tree — the agent
runs from wherever it is started, and a `logs/` directory in the
project would be a file that must be git-ignored.

The whole directory is created on demand, with the mode the operator's
umask gives it; the *log file* inside it is `0600` (see **L6**).

### The symlink

The symlink points at the **path** of the live log file, not at its
inode. That single decision is what makes the whole thing work, and it
is worth spelling out:

`RotatingFileHandler.doRollover()` renames `agent.log` to
`agent.log.1` and then reopens `agent.log`. **The path does not change
— the file at it does.** A symlink to `agent.log` is therefore valid at
every moment, before and after every rotation, and it never has to be
re-pointed. A symlink to an *inode* would have been dangling for an
instant at every rotation, and would have needed the atomic
re-point dance.

The prototype measured it:

```
[OK] the symlink resolves to the live log file
[OK] the symlink and the live file are the same inode
[OK] rotated=True inode 53882449->53882458 link still live=True
```

The inode changed (the file was rotated) and the symlink still resolved
to the live file.

The one thing that *does* need maintenance is a symlink somebody
deleted while the agent was running. The handler re-asserts it after
every rollover, so it comes back (**L3**).

The symlink is created **atomically**: the new link is built beside the
old one and moved into place with `os.replace()`, so a reader never sees
a half-written link.

### The rotation

`logging.handlers.RotatingFileHandler` does the size-based rotation
already, and it is the **standard library** — no new dependency, no
third-party rotating handler, and a behaviour that is tested upstream.
The implementation is a subclass that adds two things: the symlink, and
the file mode.

| | The stdlib handler | The subclass |
|---|---|---|
| Rotates at `maxBytes` | yes | yes |
| Keeps `backupCount` generations | yes | yes |
| The file is `0600` | no — `0666 & ~umask` | yes |
| A symlink to the live file | no | yes |
| The symlink heals itself | no | yes |

**The size limit is soft, and it has to be.** The handler checks the
size *before* it writes a record, so the live file can exceed the limit
by the size of the record that crossed it. A hard limit would mean
truncating a record in half, and a log that ends in the middle of a
line is worse than a log that is 200 bytes over.

**`backupCount = 0` disables the rotation** — the stdlib handler then
reopens the same file in append mode and it grows forever. The minimum
useful value is `1`, and the implementation refuses `0`.

### The size limit is written the way an operator writes it

`--log-max-size 10MB`, not `--log-max-size 10485760`. The parser
accepts `B`, `KB`, `MB` and `GB` (and the bare one-letter forms), and a
unit nobody knows is a **typo that is reported**:

```
ValueError: unknown size unit 'MBB' in '10MBB' — use B, KB, MB or GB
```

A log that never rotates because the size was not understood is the
exact failure this feature exists to prevent, so a size that cannot be
read stops the agent with a message, the way a bad `--log-level` does
today.

### The configuration

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `--log-file PATH` | `TORVALDS_LOG_FILE` | *off* | The log file. A bare name goes into the log directory. Without it, the agent logs to stderr exactly as it does today. |
| `--log-dir DIR` | `TORVALDS_LOG_DIR` | `~/.torvalds/logs` | The directory that holds the log, the symlink and the rotated files. |
| `--log-max-size SIZE` | `TORVALDS_LOG_MAX_SIZE` | `10MB` | The size at which the log is rotated. |
| `--log-max-files N` | `TORVALDS_LOG_MAX_FILES` | `5` | How many generations are kept. `0` is refused. |
| `--log-symlink NAME` | `TORVALDS_LOG_SYMLINK` | `<stem>-current.log` | The name of the symlink. |

The file logging is **off by default**. The agent's behaviour does not
change until the operator asks for it, and a file that nobody asked for
is a file nobody cleans up.

The environment variables matter for the runs the agent does not start
itself — a `systemd` unit, a `supervisord` program, a shell profile.

The flags follow the pattern the project already uses: the
environment variable first, the flag second, the flag wins. The
`TORVALDS_OLLAMA_HOST` resolution in `components/ollama_config.py` is
the model.

### What happens when it cannot work

The project's rule is that a missing feature **degrades**, it does not
take the agent down. The same applies here:

| Failure | What happens |
|---|---|
| The log directory cannot be created | A warning on the console, the stderr logging continues, the agent boots. |
| The symlink cannot be created (Windows without the symlink privilege, a filesystem without symlinks) | A warning, the file logging continues. The symlink is a convenience, not the log. |
| The log file cannot be opened | A warning, the stderr logging continues. |
| The size cannot be parsed | The agent stops with the message. A typo is not a degradation. |

---

## The alternatives that were considered

| Option | Why it was not chosen |
|---|---|
| **The symlink *is* the log file name** — `agent.log` is a link to `agent.log.0`, and the real file is `agent.log.0` | The path the operator names would be a symlink. An editor that saves it replaces the link with a regular file and the rotation breaks; `du` and the log shippers see a link. The *file* stays a real file in this design, and the symlink is a pointer beside it. |
| **`logrotate`, the system tool** | It cannot rotate a file that a process holds open — the agent would have to be reloaded, or the copytruncate method used, which loses the records written during the copy. It is the right answer for a service that is restarted on a schedule, not for this agent. |
| **`logging.handlers.WatchedFileHandler`** | It reopens the file when it is *replaced* — the opposite of what is wanted here. It does not rotate and it does not count bytes. |
| **`logging.handlers.TimedRotatingFileHandler`** | The operator asked for a size limit. It can be added later by running a second handler, at the cost of two rotation schedules on one file. |
| **A plain `logging.FileHandler`** | No rotation and no limit: the file grows until the disk is full. This is the `to_file` parameter that is in the tree today, and it is why the parameter was never used. |
| **A third-party rotating handler** (`python-logging-rotation` and friends) | The standard library does the whole job. A new dependency is a new thing to audit, to pin in `requirements-ci.lock`, and to keep working. |
| **Writing the log through the shell** (`>> agent.log 2>&1`) | The status quo. No rotation, no symlink, and the file is created with the umask of the shell. |

---

## The plan

| Path | Change |
|---|---|
| `components/file_logging.py` | **New.** The handler, the size parser, the symlink maintenance, the wiring. The standard library only — `logging`, `logging.handlers`, `os`, `pathlib`. |
| `agent-torvalds.py` | The five flags; `configure_logging()` gains the file handler. |
| `agent-torvalds-mw.py` | The same — and the dead `to_file` parameter becomes the real thing. |
| `tests/test_file_logging.py` | **New.** The tests below. |
| `tests/test_logging_cli.py` | The new flags are pinned here, next to `--log-level`. |
| `README.md`, `CHANGELOG.md`, `docs/logging.md` | The documentation. |

`components/` is where it belongs: `components/ollama_config.py` and
`components/hitl_timeout.py` are the same kind of thing — a single
source of truth for one concern, shared by the two orchestrators.

### One thing the implementation must get right

`configure_logging()` is called **twice** in each orchestrator: once at
module level, and once after the command line is parsed:

```python
configure_logging(DEFAULT_LOG_LEVEL)   # at import
...
configure_logging(args.log_level)       # after the arguments are parsed
```

The second call uses `force=True`, which **removes and closes** the
handlers of the first. So the file handler must be added by the second
call — the one that knows the flags — and the module-level call stays
stderr-only. If the file handler were added at import time, `force=True`
would close it and the file would be written to a closed handle.

The configuration is therefore resolved **once**, after the arguments are
parsed, and handed to `configure_logging()` as one object.

### The tests

| Test | What it pins |
|---|---|
| The file is created and receives the records | The feature works |
| The file is not truncated when the logging is reconfigured | The second `configure_logging()` does not lose the first run's records |
| The file is `0600` | The log is private |
| The rotation happens at the size limit | The rotation is real |
| No more than `--log-max-files` generations are kept | The disk use is bounded |
| The symlink exists and resolves to the live file | The requirement of the operator |
| The symlink survives a rotation | The rotation does not break the pointer |
| The symlink comes back after it was deleted | The handler heals it |
| A symlink that cannot be created does not stop the logging | The degradation |
| A log directory that cannot be created does not stop the boot | The degradation |
| The size parser: the units, and the typos | `10MB` works, `10MBB` is reported |
| The flags, the defaults, the environment variables | The surface |
| The stderr handler is still there | The tee |
| The file logging is off by default | The agent does not change until it is asked to |

The CI gate (`scripts/ci_test_gate.py`) must report **0 new failures**.

---

## The invariants

The harness is written against the **public behaviour** — the files on
disk and the records they carry — and not against private helpers, so
it stays valid when the implementation is refactored.

| | Invariant | Caught by |
|---|---|---|
| **L1** | Every record reaches the log file. | a record that is swallowed |
| **L2** | The log file is rotated when it reaches the size limit. | the rotation being disabled |
| **L3** | The symlink points at the file that is being written *now* — and it comes back after it was deleted. | the symlink pointing at the rotated file, or not being refreshed |
| **L4** | The number of retained generations is bounded. | the retention being ignored |
| **L5** | A symlink that cannot be created degrades the pointer, never the logging. | the failure being raised |
| **L6** | The log file is appended to, is private (`0600`), and is not truncated when the logging is reconfigured. | the truncation, and the missing mode |
| **L7** | The size limit is written the way an operator writes it, and an unknown unit is reported. | the typo being ignored |

### Running it

```bash
self-development/.venv/bin/python \\
    self-development/investigate/logging-to-file/prototype_file_logging.py
self-development/.venv/bin/python \\
    self-development/investigate/logging-to-file/verify_logging_to_file.py
self-development/.venv/bin/python \\
    self-development/investigate/logging-to-file/verify_harness_catches_regressions.py
```

**13 checks hold**, and **7 of 7 deliberate drifts are caught**:

```
[OK  ] D1 — the symlink points at the rotated file, not at the live one
       caught by L3 (failed: L3; only that one)
[OK  ] D2 — the symlink is not refreshed after a rollover
       caught by L3 (failed: L3; only that one)
[OK  ] D3 — the rotation is disabled
       caught by L2 (failed: L2, L3; also that one)
[OK  ] D4 — the log file is truncated instead of appended to
       caught by L6 (failed: L6; only that one)
[OK  ] D5 — a symlink that cannot be created takes the agent down
       caught by L5 (failed: L5; only that one)
[OK  ] D6 — the log file is left readable by every account
       caught by L6 (failed: L6; only that one)
[OK  ] D7 — the records are swallowed and never reach the file
       caught by L1 (failed: L1, L2, L3, L5, L6; also that one)
```

### What the drifts found

**The file mode was wrong, and only the harness noticed.** The stdlib
handler creates the file with `0666 & ~umask` — `0664` on this machine,
so a log with the prompts in it was readable by every account on the
box. The first run of the harness failed on it:

```
[FAIL] L6  the file mode is 0o664
```

The prototype now corrects the mode on the first open and after every
rollover.

**The symlink needs no maintenance at all — and that was a surprise.**
The first version of drift D2 removed the "refresh the symlink after a
rollover" call, and **the harness passed**. The drift was not a defect:
because the symlink points at a *path* and the path does not change when
the file is rotated, the symlink survives the rotation untouched. The
refresh is only load-bearing for the one case where the symlink is
deleted while the agent runs, and that case is now a check of its own
(**L3**, "the symlink comes back after it was deleted").

The lesson is the one the project keeps learning: *a check that has
never failed proves nothing.* The first version of the harness had a
check that could not fail, and finding it is what turned the check into
a real one.

---

## The known limitations

| | Limitation | What it means |
|---|---|---|
| **Multi-process** | `RotatingFileHandler` has no cross-process lock. Two agents writing to the *same* log file can lose records at the moment of the rotation. | One log file per agent process. If several agents run at once, give them their own `--log-file`, or a name that carries the PID. A `fcntl` lock on a `.lock` file would close the hole, and is a small addition if it is ever needed. |
| **The size limit is soft** | The live file can exceed the limit by the record that crossed it. | A log that is a few kilobytes over the limit is the price of a record that is not cut in half. |
| **No compression** | The rotated files are plain text. | `gzip` on the rotated generations is a small addition, and the disk use is already bounded by `size × (files + 1)`. |
| **No time-based rotation** | The rotation is by size only. | What was asked for. A time-based schedule can be added with a second handler. |
| **The log is not redacted** | The log carries the prompts, the tool output and the answers. | The file is `0600` and it stays in the user's home directory. The MikroTik toolkit scrubs its secrets from its own output; the agent's log is not scrubbed. |

## The open questions for the operator

1. **The name of the symlink.** The default is `agent-current.log`,
   next to `agent.log`. `current.log` is another way to spell it, and
   `--log-symlink` chooses.
2. **The default size.** `10MB` with `5` generations is `60MB` of disk
   use at the most, and it is the default that is never seen unless the
   operator looks.
3. **Whether the file replaces the terminal or joins it.** The design
   here is a **tee** — the operator still sees the output. A file-only
   mode is one line, if it is wanted.
4. **Whether the TUI should stop writing to stderr.** The multi-window
   agent's `Live` display and the stderr handler do not always get
   along. The file logging is half of the answer; the other half is
   turning the stderr handler off in the TUI.
