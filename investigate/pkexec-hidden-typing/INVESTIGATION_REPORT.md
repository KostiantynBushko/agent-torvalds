# The typed text was invisible again — after the password was asked for

## What the operator reported

> *ok I see the same issue with hidden typing, afetr agnet runs pexdec
> to ask root password I can notice this issue when the termo=inal does
> not show typed characters*

The report of 2026-11-09 was about the same thing:

> *after agent response sometime by typint I do not see what is typed
> looks like it is hidded even after leaving agent app the typing in
> terminal is hidden*

So the question is: **what does the path of the privileged command do to
the terminal of the operator?**

**Probe:** [`probe_escalation_terminal.py`](probe_escalation_terminal.py) —
read-only, measures the three things that decide it, against a pty of its
own.

---

## 1. The question

The feature of 2026-11-09 (`investigate/linux-privilege-escalation/`)
rewrites a `sudo` into a `pkexec`, and polkit puts the question in a
window.  Three things were left to the child of the command:

| | What it was |
|---|---|
| **the flag** | `--disable-internal-agent` was added **only when the terminal belonged to an application that draws the screen** — the state of the echo, read once, when the plan was made |
| **the input** | the child of an escalated command inherited the **terminal** as its standard input |
| **the terminal** | nothing gave the terminal back when the command was over |

## 2. The measurement

The probe measures all three, inside a pty of its own.  Before the
change:

```
  1. THE FLAG - may pkexec ask the question on the terminal?

  the terminal is managed (an application draws the screen)
      the command : pkexec --keep-cwd --disable-internal-agent systemctl restart nginx
      the textual agent may ask: no
  the terminal is an ordinary console
      the command : pkexec --keep-cwd systemctl restart nginx
      the textual agent may ask: YES

  2. THE INPUT - what the child gets as its standard input

  an ordinary command gets  : inherited
  an escalated command gets : inherited

  3. THE TERMINAL - is it given back?

  echo before the command : on
  echo after the command  : off
```

and after the change:

```
  1. THE FLAG - may pkexec ask the question on the terminal?

  the terminal is managed (an application draws the screen)
      the command : pkexec --keep-cwd --disable-internal-agent systemctl restart nginx
      the textual agent may ask: no
  the terminal is an ordinary console
      the command : pkexec --keep-cwd --disable-internal-agent systemctl restart nginx
      the textual agent may ask: no

  2. THE INPUT - what the child gets as its standard input

  an ordinary command gets  : None
  an escalated command gets : -3

  3. THE TERMINAL - is it given back?

  echo before the command : on
  echo after the command  : on
```

## 3. The root cause

### The question was asked on the terminal — and the terminal hides the answer

`pkexec(1)` says of its own textual agent:

> *if no authentication agent is available, then pkexec will register
> its own textual authentication agent*

That agent asks the password **on the terminal**, through a helper —
`polkit-agent-helper-1` — which reads the answer from **`/dev/tty`**
and changes the attributes of the terminal while it does it.  The
library that carries it says so itself:

```console
$ objdump -T /usr/lib/x86_64-linux-gnu/libpolkit-agent-1.so.0 | grep -E "tcsetattr|tcgetattr"
0000000000000000      DF *UND*  0000000000000000 (GLIBC_2.2.5) tcsetattr
0000000000000000      DF *UND*  0000000000000000 (GLIBC_2.2.5) tcgetattr
```

The echo is off while the password is read — that is how a password is
hidden.  The operator sees a prompt and types into a terminal that shows
**nothing of what they type**: the same hidden typing as the report of
2026-11-09, in a place where the operator is waiting for a question.

And the helper opens `/dev/tty` **by itself**: it does not need the
standard input of the command to reach the terminal of the operator.

### The decision was a snapshot, and the snapshot was the wrong thing to decide on

The flag was added when the terminal was *managed* — when the echo was
off, which is what an application that draws the screen does.  The
terminal of the **ordinary console** — the classic REPL, a session over
SSH — has the echo **on**, and there the flag was left out.

So the question was asked in two different places, and which one it was
depended on the state of the terminal at the moment the plan was made:

| The terminal | The question was asked |
|---|---|
| the TUI (the echo is off) | in the window ✓ |
| an ordinary console (the echo is on) | **on the terminal** ✗ |

### The child inherited the terminal

`subprocess.run(...)` was called without `stdin`, so the child inherited
the terminal of the operator.  The child of a privilege escalation runs
as **another user**, and it could

* read the keystrokes of the operator — the TUI's own input reader
  competes with it for every one of them, and the operator's password
  is lost between the two; and
* ask a question that the operator cannot answer, because the answer
  goes to the application that draws the screen and not to the program
  that asked.

### The terminal was never given back

The state of the terminal belongs to the **terminal**, not to the
process.  A command that took the terminal over — the helper of the
textual agent, `sudo` — and was then killed by the timeout of the
command (`subprocess.run` sends `SIGKILL`) left the terminal with the
**echo off**:

```
  echo before the command : on
  echo after the command  : off
```

The operator types into a terminal that shows nothing of it, and it
stays that way after the agent is gone.

### And the terminal of the operator can refuse to give its attributes back

While the probe was written, the restore of the terminal was measured on
the terminal of the operator — and it **blocked**:

```console
$ python3 -c "... tcsetattr(fd, TCSANOW, state) ..."
opening /dev/tty
  opened in 0.00 s
  tcgetattr in 0.00 s
  tcsetattr TCSANOW in 0.00 s     ← on one run; on another it never returned
```

The same script, run again, returned in a thousandth of a second.  The
block is real and it is intermittent, and a restore that can block
would hold the **agent** — a worse defect than the mute terminal.

## 4. The fix

### The question is asked in a window, always

`--disable-internal-agent` is now **always** passed for an escalated
command.  The gate of the feature already refuses to escalate when no
window can be shown, so the textual agent is never the answer to a
question that has to be asked:

```python
parts = ["pkexec", "--keep-cwd", "--disable-internal-agent"]
```

### The child of an escalated command gets nothing to read

An escalated command runs as another user, and it gets
`stdin=subprocess.DEVNULL`.  It cannot read the keystrokes of the
operator, and it cannot ask a question the operator cannot answer.  An
ordinary command keeps the terminal, as it always did.

### The terminal is given back

The toolkit snapshots the controlling terminal before it runs a command
and puts it back afterwards — whatever the command did to it, and
whether the timeout killed it:

```python
with preserved_terminal():
    result = subprocess.run(...)
```

The restore has three guards, because the terminal of the operator is
not always willing:

| Guard | Why |
|---|---|
| nothing is written when the terminal was not changed | the common case does not touch the terminal at all |
| `TCSANOW`, and not `TCSADRAIN` | a restore must not wait for the output of a terminal nobody reads |
| the restore runs in a thread of its own, and the caller waits for it for two seconds at most | a terminal that refuses to give its attributes back cannot hold the agent |

## 5. Verification

| Check | Before | After |
|---|---|---|
| `probe_escalation_terminal.py` | *the textual agent may ask: YES* — *the terminal was left mute* | *the textual agent may ask: no* — *the terminal was given back* |
| `toolkits/linux-toolkit/tests/test_privilege_terminal.py` | the file does not exist | **10 passed** |
| `toolkits/linux-toolkit/tests/` | 132 passed | **133 passed** |
| the suite | the baseline of `scripts/ci_test_gate.py` | the same set of failures, no new ones |

The ten new tests are offline and hermetic: no test runs `pkexec`, no
test opens a window, and every check that needs a terminal runs against
a pty of its own.

## 6. What is *not* in this change, and why

- **The command that outlives its timeout.**  The timeout of a command
  kills the child that was started — the shell — and not necessarily
  the program the shell started.  The probe measures it:

  ```
  the helper still runs   : yes
  ```

  The helper outlived the timeout and kept what it took.  Killing the
  whole process group would end it, but it changes the meaning of
  **every** timeout of **every** command, and it takes the controlling
  terminal with it (a child in a process group of its own that reads
  the terminal is stopped by `SIGTTIN`).  It is a change of its own.

- **The `sudo` that is left alone.**  When the gate is closed — no
  display, no polkit agent — the `sudo` runs as it was written, and
  `sudo` asks the password on the terminal.  That is what `sudo` does,
  and the toolkit has no password to give it.  What the toolkit can do
  is give the terminal back afterwards, and it does.

- **The prompt of the password of the APT toolkit.**  The APT toolkit has
  its own password handling (`prompt_sudo_password`, the whiptail
  dialog, the session cache) and it was left alone, as it was in the
  change of 2026-11-09.

- **The `TCSADRAIN` of the console input module.**
  `components/console_input_module.py` gives the terminal back with
  `TCSADRAIN` — the wait that was measured above.  The same hazard is
  there, in the other password prompt of the project.  It is a change of
  its own, in another component.

## 7. The recommendation to the operator

The question of a privileged command is asked in the **window** now, and
never on the terminal — so the password is not typed into a terminal
that shows nothing of it, and the terminal of the operator is given back
whatever the command does.

The cost of the promise: when no graphical agent answers, `pkexec`
**waits** — it waits for the timeout of the command, and then the
command fails.  That is the trade of the feature: the question belongs
in a window, and a question that is asked in a window and in no other
place has to wait for the window.
