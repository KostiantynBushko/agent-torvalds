# Investigation Report: Does the privilege escalation leave the operator's terminal without echo?

The operator reported that the terminal goes mute after a command that
asked for the sudo password in a window, and pointed at
[pyinvoke/invoke#303](https://github.com/pyinvoke/invoke/issues/303) —
"Terminal input hidden after quiting subprocess started with
`invoke.run`".  The report asks whether this repository has the same
defect, and where.

**Probe:** [`probe_privilege_terminal.py`](probe_privilege_terminal.py) —
read-only; every measurement runs in a pty of the probe's own, so the
terminal of the operator is never touched.

---

## 1. The question

When the agent runs a command that needs root, the command is escalated:
the `sudo` is rewritten into a `pkexec`, and polkit asks the operator for
the password **in a window**.  The question is what that leaves behind on
the terminal the agent is running in.

There is a second question behind it, and it is the one that decides
whether the operator sees anything at all:

> The state of a terminal belongs to the **terminal**, not to the process.
> A terminal that is left without echo shows nothing of what is typed —
> and it stays that way after the agent is gone.

That is the whole of invoke#303.  Invoke switched the terminal into
cbreak mode to mirror stdin, and the restore that was supposed to put it
back **did not run** when the process was interrupted — the operator was
left with a terminal that showed nothing until `stty sane`.

## 2. The measurement

The probe runs five measurements.  The echo is read from the **slave**
side of the pty, from inside the child: on Linux the master and the
slave of a pty have their own termios, and only the slave is the
terminal the child sees.

```
--- 1. the question in a window (pkexec + polkit) ---
   echo at the start   : on
   the plan            : pkexec --keep-cwd id
   the backend         : pkexec
Command timed out after 5 seconds: sudo id
   the answer          : Command timed out after 5 seconds: sudo id
   echo at the end     : on

--- 2. the question on the terminal (sudo -v) ---
   echo at the start   : on
[sudo: authenticate] Password: Command timed out after 5 seconds: sudo -v
   the answer          : Command timed out after 5 seconds: sudo -v
   the child is alive  : ['python', 'sudo']
   echo at the end     : OFF

--- 3. the mechanism: a child that switches the echo off ---
   echo at the start   : on
Command timed out after 5 seconds: python3 -c 'import termios,sys;...'
   the child is alive  : ['python', 'python3']
   echo at the end     : OFF

--- 4. the kill: which signal ends the child? ---
   the return code    : -9
   the signal         : 9
   SIGKILL            : 9

--- 5. the baseline of the reader of the TUI ---
   echo at the start   : on
   echo before the reader: OFF
   echo while the TUI runs: OFF
   echo after the reader : OFF
   echo at the end     : OFF

--- the result ---
   the question in a window leaves the terminal alone   : yes
   the question on the terminal gives the terminal back : NO
   the agent gives the terminal back                    : NO

   the facts behind it:
   the child is killed with SIGKILL, which it cannot catch : yes
   the reader of the TUI restores the state it found    : NO
```

The exit code of the probe is **1**: the terminal was left mute.

| Measurement | The echo afterwards | What it says |
|---|---|---|
| 1. the question in a window | **on** | the polkit window does not touch the terminal |
| 2. the question on the terminal | **OFF** | the terminal is left mute — the operator's symptom |
| 3. the mechanism | **OFF** | it is the **agent**, not `sudo`, that leaves the terminal mute |
| 4. the kill | SIGKILL | the child cannot catch it, so it cannot give the terminal back |
| 5. the baseline | OFF | the reader of the TUI gives back the state it found — a mute terminal stays mute |

Two facts in that output deserve a second look:

* **`the child is alive: ['python', 'sudo']`** — after the timeout fired,
  the `sudo` that was holding the terminal was **still running** (the
  `python` in that list is the measurement itself).  The kill went to the
  shell that `subprocess.run(shell=True)` started, and the `sudo` is its
  grandchild.  The process that holds the terminal is not the process
  that is killed.
* **Measurement 3 does not use `sudo` at all.**  The child only switches
  the echo off and reads a line.  The terminal is still left mute.  The
  defect is in the code of the agent, not in the program that asked the
  question.

### The window path, measured separately

The plan the toolkit builds depends on the state of the terminal:

```
--- at a console (the echo is on) ---
terminal_is_managed() : False
the plan              : pkexec --keep-cwd id

--- in the TUI (the terminal is in cbreak, the echo is off) ---
terminal_is_managed() : True
the plan              : pkexec --keep-cwd --disable-internal-agent id
```

`--disable-internal-agent` is the flag that stops `pkexec` from asking
the password on the terminal when no window answers.  **The TUI adds it;
a console does not.**

### The same defect in the other "UI for the sudo password"

The APT toolkit asks for the password in a **whiptail** dialog — a box
drawn in the terminal.  Measured, in a pty of its own:

```
output so far : <ESC>[?1049h...            ← the alternate screen buffer
echo while the dialog is up      : OFF
echo after the dialog was killed : OFF
```

The dialog switches the terminal into the alternate screen buffer and
switches the **echo off**; when it is killed, the echo stays off.  The
`whiptail` package runs the binary with `Popen(...).communicate()` and
without a timeout, so an interrupt in the middle of the dialog leaves
the terminal mute in the same way.

## 3. The root cause

Three things line up, and each of them is enough on its own.

### 3.1 The question is asked on the operator's terminal

Two of the paths put the password prompt **on the terminal** the agent is
running in:

* the **`sudo` fallback** — when the gate of `pkexec` is closed (no
  `pkexec`, no display, no polkit agent), the toolkit leaves the `sudo`
  as it was written, and `sudo` asks on the terminal.  The mode `sudo`
  does the same on purpose.
* **pkexec's own textual agent** — `pkexec` registers an internal agent
  when no window answers, and that agent asks on the terminal.  It is
  only stopped by `--disable-internal-agent`, and the flag is only added
  when the terminal belongs to an application (§2).  At a console it is
  not added.

Both switch the **echo off** while the question is on the screen.  That
is what a password prompt does — and it is why the terminal has to be
given back afterwards.

polkit's own source says so, in the agent that does it
(`polkitagenttextlistener.c`):

```c
  tcgetattr (fileno (listener->tty), &ts);
  ots = ts;
  ts.c_lflag &= ~(ECHO | ECHOE | ECHOK | ECHONL);
  tcsetattr (fileno (listener->tty), TCSAFLUSH, &ts);
```

and, right above it, the comment of the people who wrote it:

> *We really ought to block SIGINT and SIGSTP (and probably other
> signals too) so we can restore the terminal (since we turn off
> echoing).*

### 3.2 The agent kills the child in a way it cannot answer

`execute_shell_command()` runs the command with

```python
result = subprocess.run(effective_command, shell=True, timeout=effective_timeout, ...)
```

On a timeout, CPython calls `process.kill()` — **SIGKILL** (measurement
4: the return code is `-9`).  SIGKILL cannot be caught, so the child
that holds the echo-off state has no chance to give the terminal back.

And it is not enough to kill the child anyway: the direct child of
`subprocess.run(shell=True)` is the **shell**, and the process that holds
the terminal is its grandchild.  Measurement 2 shows the `sudo` still
alive after the timeout.

### 3.3 The agent never owns the terminal state

The other two places in this repository that switch the terminal off
both give it back:

| Place | How it gives the terminal back |
|---|---|
| `components/console_input_module.py` — the masked password | `finally` **and** an `atexit` hook |
| `components/tui/input_reader.py` — the reader of the TUI | `stop()` **and** an `atexit` hook |

The privilege path has **neither**.  The agent never takes the terminal,
so it cannot give it back: the restore has to happen inside the child,
and the child is killed with a signal it cannot catch.

That is the difference between this repository and invoke#303.  Invoke
had the restore — in a `finally` — and the `finally` **did not run**,
because the main thread was interrupted and the IO threads were daemons.
The fix upstream (0.12.2) was to tie the threads off *before* the
exception is re-raised:

```python
exception = None
try:
    self.wait()
except BaseException as e:      # Make sure we nab ^C etc
    exception = e
self.program_finished.set()
for t in threads:
    t.join()
...
if exception is not None:
    raise exception
```

The rule is the same one, and it is the rule this report proposes for
the privilege path: **whoever changes the state gives it back, and the
give-back runs even when the process is interrupted.**

### 3.4 The baseline is captured, not the truth

The reader of the TUI captures the state of the terminal when it starts
and restores *that* state when it stops.  Measurement 5: a terminal that
was already mute stays mute.  So the damage is not only "the terminal is
mute now" — it is also "**the agent bakes the mute state into its
baseline**, and hands it back when it exits".  The state belongs to the
terminal, not to the process.

## 4. The fix

The fix is a change of its own, with its own branch and its own pull
request.  This report says what it has to do; the proposal is in
[`PROPOSAL.md`](PROPOSAL.md).

1. **The agent takes the terminal around a command, and gives it back.**
   The attributes of the terminal are read before the child starts and
   written back in a `finally` — whatever happened to the child.  This
   is the same contract the masked password and the reader of the TUI
   already keep.
2. **The child is killed in a way it can answer.**  On a timeout:
   SIGTERM first, a short grace period, then SIGKILL — and the whole
   **process group**, so that the `sudo` behind the shell is killed too.
   A child that can catch SIGTERM gives the terminal back itself.
3. **The question never lands on the terminal.**  `--disable-internal-agent`
   is added **always**, not only when the terminal belongs to an
   application: while a command runs, the agent is not a console that
   can answer a question — in the TUI the reader of the keyboard eats
   the keystrokes, and at a console the agent is blocked in
   `subprocess.run` and the line editing of the operator is gone.
4. **The `sudo` fallback goes.**  When the gate of `pkexec` is closed,
   the command is **refused with the reason** ("pkexec cannot ask for it:
   no polkit authentication agent is running") instead of being run as a
   `sudo` that asks on a terminal the agent cannot give back.

## 5. Verification

| Check | Before | After |
|---|---|---|
| `probe_privilege_terminal.py` | exit 1 — *"the terminal was left mute"* | exit 0 — *"the terminal was given back in every measurement"* |
| measurement 2 (the question on the terminal) | the echo is **OFF** | the echo is **on** |
| measurement 3 (the mechanism) | the echo is **OFF** | the echo is **on** |
| measurement 5 (the baseline) | the mute state is baked in | the terminal is given back as it was found |

The probe runs against the **real** code of the repository — the real
`execute_shell_command()`, the real timeout, the real reader of the TUI —
and only the pty is its own.

## 6. What is *not* in this change, and why

* **The code change itself.**  It is a separate change, with its own
  branch and its own pull request.  This folder is the evidence for it.
* **The whiptail dialog of the APT toolkit.**  It has the same defect
  (§2) and it lives in another component with another contract — the
  dialog is drawn *in* the terminal, so it needs the screen as well as
  the echo.  It deserves its own change.
* **The cbreak mode of the TUI.**  The TUI draws the screen itself, so it
  switches the echo off on purpose.  That is not a defect; the defect is
  that a terminal which is mute for another reason is baked into the
  baseline (§3.4).
* **A `kill -9` of the agent.**  SIGKILL cannot be caught, and no
  program can answer for it — the same limit that invoke#303 has.  The
  agent can only be as good as the exits it can handle.
* **polkit's textual agent.**  It is upstream's code, and it documents
  the defect itself.  The toolkit's job is to stop it from being used,
  not to repair it.

## 7. The recommendation to the operator

**What to do now.**  A mute terminal is given back with

```console
$ stty sane
```

(`stty echo` is enough for the echo alone.)  It is worth running it after
a command that needed root and did not get an answer.

**What to expect.**  The path that asks in a **window** — the one the
operator reported — **does not damage the terminal** (measurement 1), and
the TUI adds `--disable-internal-agent`, so `pkexec` cannot fall back to
asking on the terminal there either.  The paths that do damage it are the
ones where the password is asked **on the terminal**: the `sudo` fallback
(when there is no polkit agent to ask), `pkexec`'s own textual agent (at
a console, when no window answers), and the whiptail dialog of the APT
toolkit.

If the terminal goes mute after a command that **did** show a window, the
window was probably not the one that asked — the question may have fallen
back to the terminal, and the mute state is now baked into the baseline
of the next run of the agent.  `stty sane` gives the terminal back, and
the next run of the agent starts from a terminal that is whole.

**What it costs to accept.**  Until the fix lands, a command that needs
root can leave the operator with a terminal that shows nothing of what
they type.  The cost of the fix is a save and a restore of the terminal
attributes around every command, a kill that gives the child a chance to
clean up, and the end of the `sudo` fallback — which means that a
command that needs root **fails with a reason** on a machine without a
polkit agent, instead of hanging for five minutes and asking for a
password on a terminal the agent cannot give back.
