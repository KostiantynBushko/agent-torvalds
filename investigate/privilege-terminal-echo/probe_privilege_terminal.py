"""
The terminal after a privileged command.

The question
------------
Does the privilege escalation leave the operator's terminal **without
echo** - the defect of `pyinvoke/invoke#303`, where the process that
changed the terminal settings died in the middle of the question and
never gave them back?

The measurements
----------------
1. **The question in a window** - a command that is escalated through
   ``pkexec``: the polkit agent asks in a window.  Does the terminal
   survive it?
2. **The question on the terminal** - a command that asks for the
   password on the terminal (``sudo -v``): the agent's timeout kills the
   child while the question is on the screen.  Is the terminal given
   back?
3. **The mechanism** - the same, with a child that only switches the
   echo off: is the *agent* responsible, or the child?
4. **The kill** - is the child killed with a signal it can catch?
5. **The baseline** - the reader of the TUI captures the terminal state
   when it starts and restores *that* when it stops: what does it
   restore when the terminal was already mute?

The method
----------
Everything runs in a pty of the probe's own.  The terminal of the
operator is never touched - a probe that leaves a mute terminal behind
is not a probe.

The echo is measured on the **slave** side of the pty, from inside the
child: on Linux the master and the slave of a pty have their own
termios, and only the slave is the terminal the child sees.

The probe cleans up after itself: the processes that the timeout left
behind in the session of the pty are killed when the measurement ends.

Usage
-----
    python investigate/privilege-terminal-echo/probe_privilege_terminal.py

The exit code is 0 when the terminal was given back in every
measurement, and 1 when a measurement left it mute.
"""
from __future__ import annotations

import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parent.parent.parent

#: A marker that is put into the command line of the helper of
#: measurement 3, so that the leftover process can be found.
MARKER = "privilege-terminal-echo-marker"

#: The helper of measurement 3: it does what ``sudo`` and polkit's
#: textual agent do - it switches the echo off on the terminal, reads a
#: line, and would switch the echo back on.  It never gets that far.
HELPER = (
    "import termios,sys;"
    "fd=sys.stdin.fileno();"
    "a=termios.tcgetattr(fd);b=list(a);"
    "b[3]&=~termios.ECHO;"
    "termios.tcsetattr(fd,termios.TCSADRAIN,b);"
    "sys.stdin.readline()"
)

#: The program that runs inside the pty.  It does the measurement and
#: prints what it saw; the parent reads the output.
_CHILD = r'''
import glob, os, sys, termios, time

REPO = os.environ["PROBE_REPO"]
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from toolkits import linux_toolkit
from components.tui.input_reader import NonBlockingInputReader

FD = sys.stdin.fileno()


def echo_state():
    """The echo state of the terminal - the slave side of the pty."""
    try:
        attrs = termios.tcgetattr(FD)
    except Exception as exc:
        return "unknown (%s)" % exc
    return "on" if (attrs[3] & termios.ECHO) else "OFF"


def session_processes(session):
    """The processes that are still in the session of the pty."""
    names = []
    for entry in glob.glob("/proc/[0-9]*/stat"):
        try:
            with open(entry, "rb") as handle:
                stat = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        # The fields after the command name: state, ppid, pgrp, session
        tail = stat[stat.rfind(")") + 2:].split()
        if len(tail) < 4:
            continue
        try:
            if int(tail[3]) == int(session):
                names.append(stat[stat.find("(") + 1:stat.rfind(")")])
        except ValueError:
            continue
    return names


measurement = sys.argv[1]
timeout = int(sys.argv[2])
# The child of pty.fork() is the leader of a new session, so its own
# session id is its pid.  The processes that the timeout leaves behind
# are found through it.
session = os.getsid(0)

print("   echo at the start   : %s" % echo_state(), flush=True)

if measurement == "window":
    # A command that is escalated through pkexec: the question is asked
    # in a window, by the polkit agent.
    from toolkits.linux_toolkit import privilege as privilege_module
    plan = privilege_module.plan_privilege("sudo id", "auto")
    print("   the plan            : %s" % plan.command, flush=True)
    print("   the backend         : %s" % plan.backend, flush=True)
    result = linux_toolkit.execute_shell_command(
        "sudo id", timeout=timeout, privilege="auto")
    print("   the answer          : %s"
          % (result.get("stderr") or result.get("stdout") or "")[:100],
          flush=True)

elif measurement == "ask":
    # A command that asks for the password on the terminal.  `sudo -v`
    # validates the credential and runs nothing.
    result = linux_toolkit.execute_shell_command(
        "sudo -v", timeout=timeout, privilege="sudo")
    print("   the answer          : %s"
          % (result.get("stderr") or result.get("stdout") or "")[:100],
          flush=True)
    time.sleep(0.5)
    print("   the child is alive  : %s" % session_processes(session), flush=True)

elif measurement == "mechanism":
    # The same, with a child that only switches the echo off.
    helper = os.environ["PROBE_HELPER"]
    marker = os.environ["PROBE_MARKER"]
    command = "python3 -c %r %s" % (helper, marker)
    result = linux_toolkit.execute_shell_command(
        command, timeout=timeout, privilege="auto")
    print("   the answer          : %s"
          % (result.get("stderr") or result.get("stdout") or "")[:100],
          flush=True)
    time.sleep(0.5)
    print("   the child is alive  : %s" % session_processes(session), flush=True)

elif measurement == "baseline":
    # The reader of the TUI: it captures the terminal state when it
    # starts and restores that state when it stops.
    hidden = termios.tcgetattr(FD)
    hidden[3] &= ~termios.ECHO
    termios.tcsetattr(FD, termios.TCSADRAIN, hidden)
    print("   echo before the reader: %s" % echo_state(), flush=True)
    reader = NonBlockingInputReader()
    reader.start()
    print("   echo while the TUI runs: %s" % echo_state(), flush=True)
    reader.stop()
    print("   echo after the reader : %s" % echo_state(), flush=True)

print("   echo at the end     : %s" % echo_state(), flush=True)
'''


def _run_in_pty(measurement: str, timeout: int) -> str:
    """Run one measurement in a pty of the probe's own.

    Args:
        measurement: The name of the measurement.
        timeout: The timeout the command under test gets.

    Returns:
        The output the child printed.
    """
    environment = dict(os.environ)
    environment["PROBE_REPO"] = str(REPO)
    environment["PYTHONPATH"] = str(REPO)
    environment["PROBE_HELPER"] = HELPER
    environment["PROBE_MARKER"] = MARKER

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child
        os.environ.update(environment)
        try:
            os.execv(sys.executable,
                     [sys.executable, "-c", _CHILD, measurement, str(timeout)])
        finally:
            os._exit(127)

    output: List[str] = []
    deadline = time.time() + timeout + 30
    while time.time() < deadline:
        try:
            ready, _, _ = select.select([fd], [], [], 0.5)
        except OSError:
            break
        if not ready:
            if _reaped(pid):
                break
            continue
        try:
            data = os.read(fd, 4096)
        except OSError:
            break
        if not data:
            break
        output.append(data.decode("utf-8", "replace"))

    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    os.close(fd)

    _kill_the_leftovers(pid)

    return "".join(output)


def _reaped(pid: int) -> bool:
    """Whether the child is gone already.

    Args:
        pid: The pid of the child.

    Returns:
        ``True`` when the child is gone.
    """
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True
    return done == pid


def _kill_the_leftovers(session: int) -> None:
    """Kill the processes the timeout left behind in the session.

    The timeout of the command under test kills the direct child only.
    The process that holds the terminal - the ``sudo``, the helper - is
    a grandchild, and it survives.  The probe leaves nothing behind.

    Args:
        session: The id of the session of the pty.
    """
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8",
                      errors="replace") as handle:
                stat = handle.read()
        except OSError:
            continue
        tail = stat[stat.rfind(")") + 2:].split()
        if len(tail) < 4:
            continue
        try:
            if int(tail[3]) != session:
                continue
            pid = int(entry)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            continue


def check_the_window(timeout: int = 5) -> bool:
    """Whether the question in a window leaves the terminal alone.

    The question is asked in a window by the polkit agent; the terminal
    of the operator is not involved.

    Returns:
        ``True`` when the terminal still echoes.
    """
    print("--- 1. the question in a window (pkexec + polkit) ---")
    output = _run_in_pty("window", timeout)
    print(output.rstrip())
    print()
    return "echo at the end     : on" in output


def check_the_ask(timeout: int = 5) -> bool:
    """Whether the question on the terminal gives the terminal back.

    The child asks for the password on the terminal; the agent's timeout
    kills it while the question is on the screen.

    Returns:
        ``True`` when the terminal still echoes.
    """
    print("--- 2. the question on the terminal (sudo -v) ---")
    if os.geteuid() == 0:
        print("   the operator is root - sudo does not ask for a password")
        print("   on this machine, so the measurement says nothing.")
        print()
        return True
    output = _run_in_pty("ask", timeout)
    print(output.rstrip())
    print()
    return "echo at the end     : on" in output


def check_the_mechanism(timeout: int = 5) -> bool:
    """Whether the agent itself gives the terminal back.

    The child only switches the echo off - it does not ask anything.
    The agent kills it with the timeout.

    Returns:
        ``True`` when the terminal still echoes.
    """
    print("--- 3. the mechanism: a child that switches the echo off ---")
    output = _run_in_pty("mechanism", timeout)
    print(output.rstrip())
    print()
    return "echo at the end     : on" in output


def check_the_kill() -> bool:
    """Whether the child is killed with a signal it can catch.

    ``SIGKILL`` cannot be caught: the child has no chance to give the
    terminal back.

    Returns:
        ``True`` when the child died from ``SIGKILL``.
    """
    print("--- 4. the kill: which signal ends the child? ---")
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        # This is what subprocess.run() does on a timeout.
        process.kill()
        process.wait()

    returncode = process.returncode
    print("   the return code    : %d" % returncode)
    print("   the signal         : %s" % (-returncode if returncode < 0 else "none"))
    print("   SIGKILL            : %d" % int(signal.SIGKILL))
    print()
    return returncode == -int(signal.SIGKILL)


def check_the_baseline() -> bool:
    """Whether the reader of the TUI restores the terminal it found.

    The reader captures the state when it starts and restores that state
    when it stops.  A terminal that was already mute stays mute - the
    state belongs to the terminal, not to the process.

    Returns:
        ``True`` when the reader gave the terminal back.
    """
    print("--- 5. the baseline of the reader of the TUI ---")
    output = _run_in_pty("baseline", 1)
    print(output.rstrip())
    print()
    return "echo after the reader : on" in output


def main() -> int:
    """Run every measurement.

    Returns:
        The exit code: 0 when the terminal was given back everywhere,
        1 when a measurement left it mute.
    """
    print("The terminal after a privileged command")
    print("the repository of the project")
    print()

    window = check_the_window()
    ask = check_the_ask()
    mechanism = check_the_mechanism()
    kill = check_the_kill()
    baseline = check_the_baseline()

    print("--- the result ---")
    print("   %-52s : %s"
          % ("the question in a window leaves the terminal alone",
             "yes" if window else "NO"))
    print("   %-52s : %s"
          % ("the question on the terminal gives the terminal back",
             "yes" if ask else "NO"))
    print("   %-52s : %s"
          % ("the agent gives the terminal back",
             "yes" if mechanism else "NO"))
    print()
    print("   the facts behind it:")
    print("   %-52s : %s"
          % ("the child is killed with SIGKILL, which it cannot catch",
             "yes" if kill else "NO"))
    print("   %-52s : %s"
          % ("the reader of the TUI restores the state it found",
             "yes" if baseline else "NO"))

    print()
    if window and ask and mechanism:
        print("the terminal was given back in every measurement")
        return 0

    print("the terminal was left mute - the operator types into a "
          "terminal that shows nothing")
    return 1


if __name__ == "__main__":
    sys.exit(main())
