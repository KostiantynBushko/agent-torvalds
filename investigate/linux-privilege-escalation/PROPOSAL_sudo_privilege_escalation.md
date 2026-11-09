# The `sudo` in a command, and the window that asks for the password

## What the operator asked for

> *ok please use the same branch I want to implement sudo password typing, in the
> linux toolkit we can run a command so we need a solution to handle 'sudo' in
> the command please consider "pkexec" it must run UI window with a request to
> user to type sudo password*

Three things in it:

| The words | What they mean for the code |
|---|---|
| *in the linux toolkit we can run a command* | the place to fix it is `toolkits/linux-toolkit/` — the operation that runs a shell command |
| *handle 'sudo' in the command* | the toolkit has to **recognise** a `sudo` in a command line and take it over |
| *it must run UI window with a request to user to type sudo password* | the password is asked for in a **window**, not in the terminal |

---

## The problem, exactly

`sudo` reads the password **from the terminal**:

```console
$ sudo systemctl restart nginx
[sudo] password for the-operator:
```

The Linux toolkit runs its commands with `subprocess.run(...)` — the child
inherits the terminal of the agent.  Two things make that prompt unusable
from inside the agent:

1. **The TUI draws the screen itself.**  `components/tui/input_reader.py`
   puts the terminal into cbreak mode (`tty.setcbreak`), which switches the
   **echo off** — the application draws the typed text.  A `sudo` prompt
   written into that terminal is painted over by the next frame, and the
   keystrokes are read by the TUI's own input reader, which never gives them
   to `sudo`.  The command hangs until the timeout kills it, and the operator
   is never asked anything.

2. **There may be no terminal at all.**  A window that is not focused, a
   `nohup` run, a cron job — `sudo` then fails with
   `sudo: a terminal is required to read the password; either use the -S
   option to read from standard input or configure an askpass helper`.

`pkexec` is the way out.  It asks **polkit** for the authorisation, and
polkit puts the question in a **window** — the window the operator is
already looking at.  The password never touches the terminal the agent is
drawing on.

---

## What was measured

The measurements were made on the machine of the operator, with the
polkit version that is installed there (`pkexec version 127`, `polkitd`
running, `gnome-shell` acting as the authentication agent).

### `pkexec` exit codes

From `pkexec(1)`:

| Code | Meaning |
|---|---|
| the program's own code | the program ran |
| `126` | the operator **dismissed** the dialog |
| `127` | the operator was **not authorised**, or no authorisation could be obtained |

`127` is also the exit code of "the program was not found", so the two have
to be told apart by the text of the error.

### `--keep-cwd`

`pkexec` runs the program **in the home directory of the target user**.
`sudo` runs it in the current directory.  The difference is visible:

```console
$ pkexec --keep-cwd /bin/pwd
/home/the-operator/projects/the-project     # ← with --keep-cwd
$ pkexec /bin/pwd
/root                                       # ← without it
```

So the rewrite **always** carries `--keep-cwd`.  Without it, `sudo make
install` would install into the wrong place.

### `--user`

`sudo -u www-data cmd` becomes `pkexec --user www-data cmd`:

```console
$ pkexec --keep-cwd --user nobody /usr/bin/id
uid=65534(nobody) gid=65534(nogroup) groups=65534(nogroup)
```

`--user` works, and it needs `--keep-cwd` as well — without it `pkexec`
tries to change into the home directory of the target user, and fails for a
user whose home does not exist (`Error changing to home directory
/nonexistent`).

### `--disable-internal-agent` — the important one

> *if no authentication agent is available, then pkexec will register its own
> textual authentication agent*

That textual agent asks **on the terminal** — the very thing this change is
about.  With `--disable-internal-agent` the question can only be asked in a
window.

The cost of the flag is that `pkexec` **waits** when no agent is registered:

```console
$ env -u DISPLAY -u WAYLAND_DISPLAY pkexec --disable-internal-agent /bin/true
   (nothing happens — the command is still running after 8 seconds)
$ echo $?
124        # 124 = killed by `timeout`
```

The same command with a display works:

```console
$ pkexec --keep-cwd --disable-internal-agent /bin/true ; echo $?
0
```

**So the decision to use `pkexec` needs a display *and* a running
authentication agent.**  Both are checked before the command runs — see
*The gate* below.

### The terminal the agent is drawing on

`sudo`'s prompt and `pkexec`'s textual agent both read the terminal.  The
toolkit can tell whether the terminal belongs to an application:

```python
termios.tcgetattr(fd).lflag & termios.ECHO
```

The echo is **off** when an application draws the screen itself — that is
the TUI (`tty.setcbreak`).  When the echo is on, the terminal is an
ordinary console, and `pkexec` may use its textual agent as a fallback:
the operator is at a console, and a prompt on the console is the right
place for it.

---

## The design

### The gate — when is `pkexec` used?

`pkexec` is used when **all** of the following hold:

| Condition | Why |
|---|---|
| `pkexec` is on the `PATH` | it is the program that asks polkit |
| a graphical session exists (`DISPLAY` or `WAYLAND_DISPLAY`) | otherwise there is no window to show |
| a polkit authentication agent is running | otherwise `pkexec` waits forever (§ *--disable-internal-agent*) |
| the command really contains a `sudo` in **command position** | see below |

### Recognising the `sudo`

Only a `sudo` that **starts a command** is a privilege escalation:

| Command | Escalation? |
|---|---|
| `sudo systemctl restart nginx` | **yes** — `sudo` starts the command |
| `ls \| sudo tee out` | **yes** — after the pipe |
| `a && sudo b` | **yes** — after `&&` |
| `echo $(sudo id)` | **yes** — inside a command substitution |
| `grep sudo /etc/sudoers` | **no** — `sudo` is an argument |
| `echo sudo` | **no** — `sudo` is an argument |
| `cat sudoers` | **no** — a different program |

The command line is **scanned**, not matched with a regular expression: the
scanner knows where a command may start (the beginning of the line, after
`;`, `&&`, `||`, `|`, `&`, a newline, a parenthesis) and where it may not.

### The rewrite

```
sudo [-u user] [-E] program [args...]
   ↓
pkexec --keep-cwd [--disable-internal-agent] [--user user] program [args...]
```

* The **flags `pkexec` cannot express are dropped**, and the drop is
  reported: `-E` (keep the environment — `pkexec` sanitises it anyway),
  `-H`/`-h` (set `HOME` — `pkexec` does it anyway), `-i`/`-s` (login shell),
  `-b` (background), `-k`/`-K` (drop the cached credential),
  `-A` (askpass helper), `-p` (prompt), `-g` (group — `pkexec` has no
  equivalent).
* The flags that mean *something else entirely* — `-l`/`--list`,
  `-v`/`--validate`, `-e`/`--edit` — **stop the rewrite**: they do not run
  a program, and `pkexec` cannot do them.  The command is left as it was
  written, and the reason is reported.
* **`sudo` without a program** (`sudo` on its own, `sudo -v`) is left as it
  was written, for the same reason.
* `sudo VAR=value cmd` becomes `pkexec ... /usr/bin/env VAR=value cmd` —
  the same rule the APT toolkit already follows for `sudo env VAR=value cmd`
  (see the changelog, *the variable is set for the wrong process*).
* A program that is not on the `PATH` (a shell builtin) is run through a
  shell: `pkexec ... /bin/sh -c 'cd /tmp'`.
* **Everything that is not the `sudo` is left byte for byte.**  The rewrite
  replaces the `sudo` and its flags, and nothing else — the redirections,
  the quotes and the spacing of the command survive untouched.

### The modes

| Mode | What it does |
|---|---|
| `auto` (the default) | use `pkexec` when the gate is open; otherwise leave the `sudo` alone and say so |
| `pkexec` | use `pkexec`; **refuse the command** when the gate is closed, with the reason |
| `sudo` | never rewrite — the command runs exactly as it was written |

### The timeout

A command that waits for a human in a window needs more than the thirty
seconds a command gets by default.  An escalated command gets
**300 seconds** instead — unless the caller asked for a timeout of their
own.

---

## What is deliberately **not** in this change

* **The password is never handled by the toolkit.**  `pkexec` asks polkit,
  polkit asks the operator, and the toolkit only ever sees the exit code.
  Nothing is read, stored, logged or cached — the toolkit cannot leak a
  password it never had.
* **The APT toolkit is not touched.**  It has its own password handling
  (`prompt_sudo_password`, the whiptail dialog, the session cache).  That
  is a *different* mechanism, and it stays.
* **No new dependency.**  The library half of the toolkit is built on the
  standard library alone, and it stays that way: `subprocess`, `os`,
  `shutil`, `re`, `dataclasses`, `termios`.
* **No polkit policy is written.**  The authorisation is the one polkit
  already gives for `org.freedesktop.policykit.exec` — the same action
  every `pkexec` on the system uses.

---

## The evidence

| File | What it is |
|---|---|
| `toolkits/linux-toolkit/privilege.py` | the implementation — the scan, the rewrite, the gate |
| `toolkits/linux-toolkit/tests/test_privilege.py` | the tests: the scan, the rewrite, the gate |
| `toolkits/linux-toolkit/operations.py` | the operations that use the plan |
| `probe_privilege_escalation.py` | the probe — it shows the scan, the rewrite, the gate and the terminal check.  It never runs `pkexec` and never opens a window |

Run the probe:

```bash
.venv/bin/python investigate/linux-privilege-escalation/probe_privilege_escalation.py
```
