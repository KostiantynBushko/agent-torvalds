"""
Linux Toolkit - privilege escalation for shell commands.

This module is the **privilege half** of the Linux toolkit: it decides
what happens when a command asks for root.

The problem it solves
---------------------
``sudo`` reads the password **from the terminal**::

    [sudo] password for the-operator:

The agent runs its commands with ``subprocess``, and the child inherits
the terminal of the agent.  In the TUI that terminal is in cbreak mode
- ``components/tui/input_reader.py`` puts it there with
``tty.setcbreak``, which switches the **echo off**, because the
application draws the screen itself.  A ``sudo`` prompt written into
that terminal is painted over by the next frame, and the keystrokes are
read by the input reader of the TUI, which never hands them to ``sudo``.
The command hangs until the timeout kills it, and the operator is never
asked anything.

``pkexec`` is the way out.  It asks **polkit** for the authorisation,
and polkit puts the question in a **window** - the window the operator
is already looking at.  The password never touches the terminal the
agent is drawing on.

What this module does
---------------------
It finds the ``sudo`` of a command line, rewrites it into the
``pkexec`` form that means the same thing, and reports what it did.

The rewriting is deliberately narrow:

* ``sudo`` is only recognised **in command position** - the place where
  a shell starts a program.  ``grep sudo /etc/sudoers`` is not a
  privilege escalation, and it is left alone.
* The flags that ``pkexec`` has no equivalent for are **dropped**, and
  the drop is reported.  ``sudo -E`` keeps the environment; ``pkexec``
  cannot, and the environment is sanitised either way.
* Everything that is not the ``sudo`` is left **byte for byte** as it
  was written.  The rewrite replaces the ``sudo`` and its flags, and
  nothing else.

The password itself is never seen here: polkit asks the operator, and
this module only ever sees the exit code.  There is nothing to leak,
because there is nothing to keep.

Category: System
Retriever Keywords: sudo, pkexec, polkit, privilege, root, password, dialog

Prerequisites:
    - Linux/Unix-like operating system
    - ``pkexec`` and a running polkit agent, for the window (optional -
      the toolkit falls back to ``sudo`` when they are missing)

See also:
    investigate/linux-privilege-escalation/PROPOSAL_sudo_privilege_escalation.md
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

try:  # pragma: no cover - the toolkit is POSIX only
    import termios
except ImportError:  # pragma: no cover - not POSIX
    termios = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------

#: The modes the privilege planner understands.
#:
#: ``auto``
#:     Use ``pkexec`` when it can put the question in a window; leave the
#:     ``sudo`` alone - and say so - when it cannot.
#: ``pkexec``
#:     Always use ``pkexec``; refuse the command when ``pkexec`` cannot
#:     ask the operator, and say why.
#: ``sudo``
#:     Never rewrite.  The command runs exactly as it was written.
PRIVILEGE_MODES = ("auto", "pkexec", "sudo")

#: The default timeout of a command, in seconds.
DEFAULT_TIMEOUT = 30

#: The timeout of a command that waits for a human in a window.
#:
#: The dialog stays open until somebody answers it.  Thirty seconds is
#: not enough time to read a question, type a password and press Enter,
#: so an escalated command gets this timeout instead - unless the caller
#: asked for one of their own.
PRIVILEGE_TIMEOUT = 300

#: The processes that are a polkit authentication agent.
#:
#: A graphical agent draws the dialog.  ``gnome-shell`` and
#: ``plasmashell`` are agents themselves; the others are the stand-alone
#: ones the desktops ship.
POLKIT_AGENTS = (
    "polkit-gnome",
    "polkit-kde-agent",
    "polkit-mate",
    "lxpolkit",
    "lxqt-policykit",
    "xfce-polkit",
    "hyprland-polkit",
    "deepin-polkit",
    "ukui-polkit",
    "gnome-shell",
    "plasmashell",
)


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------

#: The characters that end a word and start an operator.
_OPERATOR_CHARS = ";&|<>()\n"

#: The assignment of a shell: ``VAR=value``.
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

#: A program name that carries no shell meaning.
_PLAIN_PROGRAM_RE = re.compile(r"^[A-Za-z0-9_@%+=:,./-]+$")


@dataclass(frozen=True)
class Token:
    """One token of a command line.

    Attributes:
        kind: ``"word"`` or ``"operator"``.
        text: the token as it was written - the quotes are still in it.
        value: the token without the quoting - what the shell would
            hand to the program.
        start: the offset of the token in the command line.
        end: the offset just behind the token.
        is_command: whether the token starts a command.  It is the
            position a shell reads a program name in.
    """

    kind: str
    text: str
    value: str
    start: int
    end: int
    is_command: bool = False


def scan(command: str) -> List[Token]:
    """Split a command line into tokens.

    The scan is not a shell: it expands nothing and resolves nothing.
    It has to know two things - where a command may start, and where the
    text of a token begins and ends, so that the rewrite can replace a
    part of the command and leave the rest of it exactly as it was
    written.

    Args:
        command: The command line.

    Returns:
        The tokens of the command line, in the order they were written.
    """
    tokens: List[Token] = []
    _scan(command, tokens)
    return tokens


def _scan(text: str, tokens: List[Token]) -> None:
    """Scan *text* and append its tokens to *tokens*.

    The scanner walks the text once.  ``expect_command`` says whether
    the next word starts a command: it is true at the beginning of the
    line and after every operator, and false after a word.
    """
    index = 0
    length = len(text)
    expect_command = True

    while index < length:
        char = text[index]

        # Whitespace between two words is not a token.
        if char in " \t":
            index += 1
            continue

        # A newline ends a command.
        if char == "\n":
            tokens.append(Token("operator", "\n", "", index, index + 1))
            index += 1
            expect_command = True
            continue

        # An operator ends a command and starts the next one.
        if char in _OPERATOR_CHARS:
            start = index
            if char in "&|<":
                while index < length and text[index] == char:
                    index += 1
            elif char == ">":
                while index < length and text[index] == ">":
                    index += 1
            else:
                index += 1
            tokens.append(Token("operator", text[start:index], "", start, index))
            expect_command = True
            continue

        # A word.
        start = index
        value: List[str] = []
        while index < length:
            char = text[index]
            if char in " \t\n" or char in _OPERATOR_CHARS:
                break
            if char == "\\":
                if index + 1 < length:
                    value.append(text[index + 1])
                    index += 2
                    continue
                index += 1
                continue
            if char == "'":
                end = text.find("'", index + 1)
                if end == -1:
                    value.append(char)
                    index += 1
                    continue
                value.append(text[index + 1 : end])
                index = end + 1
                continue
            if char == '"':
                index += 1
                while index < length:
                    inner = text[index]
                    if inner == "\\" and index + 1 < length:
                        value.append(text[index + 1])
                        index += 2
                        continue
                    if inner == '"':
                        index += 1
                        break
                    value.append(inner)
                    index += 1
                continue
            if char == "`":
                # A command substitution in backticks.  The content is a
                # command of its own, and it is not scanned here: the
                # backticks keep it in one piece, and the text is kept
                # as it was written.
                end = text.find("`", index + 1)
                if end == -1:
                    value.append(char)
                    index += 1
                    continue
                value.append(text[index + 1 : end])
                index = end + 1
                continue
            value.append(char)
            index += 1

        word = "".join(value)
        # An assignment in front of a command (``VAR=1 cmd``) is not a
        # command itself - the command still starts after it.
        is_assignment = bool(_ASSIGNMENT_RE.match(word))
        tokens.append(
            Token(
                "word",
                text[start:index],
                word,
                start,
                index,
                is_command=expect_command and not is_assignment,
            )
        )
        if not is_assignment:
            expect_command = False


# ---------------------------------------------------------------------------
# The sudo
# ---------------------------------------------------------------------------

#: The flags of ``sudo`` that take a value.
_VALUE_FLAGS = frozenset(
    {
        "-u",
        "--user",
        "-g",
        "--group",
        "-p",
        "--prompt",
        "-C",
        "--close-from",
        "-D",
        "--chdir",
        "-T",
        "--command-timeout",
        "-R",
        "--chroot",
        "--role",
        "--type",
        "-U",
        "--other-user",
    }
)

#: The flags of ``sudo`` that mean something ``pkexec`` cannot do.
#:
#: They do not run a program at all - they list the rights of the
#: operator, or they validate a credential, or they open an editor.
#: There is nothing to rewrite them into, so the command is left as it
#: was written.
_BLOCKING_FLAGS = {
    "-l": "sudo -l lists the rights of the operator",
    "--list": "sudo --list lists the rights of the operator",
    "-v": "sudo -v validates a credential",
    "--validate": "sudo --validate validates a credential",
    "-e": "sudo -e opens an editor",
    "--edit": "sudo --edit opens an editor",
}

#: Why the flags that are dropped are dropped.
_DROP_REASONS = {
    "-E": "pkexec sanitises the environment as well",
    "--preserve-env": "pkexec sanitises the environment as well",
    "-H": "pkexec sets HOME to the target user anyway",
    "-h": "pkexec sets HOME to the target user anyway",
    "-b": "pkexec has no background mode",
    "-k": "pkexec has no cached credential to drop",
    "-K": "pkexec has no cached credential to drop",
    "-A": "pkexec asks the operator itself",
    "-i": "pkexec has no login shell",
    "-s": "pkexec has no login shell",
    "-n": "pkexec cannot be told not to ask",
    "-g": "pkexec cannot switch the group",
    "--group": "pkexec cannot switch the group",
    "-p": "pkexec writes the prompt itself",
    "--prompt": "pkexec writes the prompt itself",
    "--": "pkexec has no end-of-options marker",
}


@dataclass
class SudoInvocation:
    """One ``sudo`` of a command line, and what it asks for.

    Attributes:
        token: the ``sudo`` itself.
        flags: the flags that were written behind it.
        assignment: the ``VAR=value`` in front of the program, if there
            was one.
        program: the program the ``sudo`` runs.
        args: the arguments of that program.
        user: the user of ``sudo -u``, if there was one.
        dropped: the flags that were dropped, because ``pkexec`` has no
            equivalent for them.
        blocked: why the ``sudo`` cannot be rewritten, when it cannot.
    """

    token: Token
    flags: List[Token] = field(default_factory=list)
    assignment: Optional[Token] = None
    program: Optional[Token] = None
    args: List[Token] = field(default_factory=list)
    user: Optional[str] = None
    dropped: List[str] = field(default_factory=list)
    blocked: Optional[str] = None

    @property
    def end(self) -> int:
        """The offset just behind the last token of the ``sudo``."""
        last = self.args[-1] if self.args else self.program
        return last.end if last is not None else self.token.end


def _is_sudo(token: Token) -> bool:
    """Whether a token is the ``sudo`` program."""
    value = token.value
    if not value:
        return False
    if value == "sudo":
        return True
    # /usr/bin/sudo
    return value.endswith("/sudo") and "/" in value


def find_sudo(command: str) -> List[SudoInvocation]:
    """Find the ``sudo`` calls of a command line.

    Only a ``sudo`` that **starts a command** is a privilege
    escalation.  ``sudo`` as an argument - ``grep sudo /etc/sudoers`` -
    is not one, and it is left alone.

    Args:
        command: The command line.

    Returns:
        The ``sudo`` calls of the command line, in the order they were
        written.
    """
    tokens = scan(command)
    invocations: List[SudoInvocation] = []

    for index, token in enumerate(tokens):
        if token.kind != "word" or not token.is_command:
            continue
        if not _is_sudo(token):
            continue
        invocations.append(_read_invocation(tokens, index))

    return invocations


def _read_invocation(tokens: List[Token], index: int) -> SudoInvocation:
    """Read the ``sudo`` at *index* and everything that belongs to it."""
    token = tokens[index]
    invocation = SudoInvocation(token=token)
    position = index + 1

    # The flags.
    while position < len(tokens):
        candidate = tokens[position]
        if candidate.kind != "word" or candidate.is_command:
            break
        value = candidate.value

        if value in _BLOCKING_FLAGS:
            invocation.blocked = _BLOCKING_FLAGS[value]
            break

        if value == "--":
            invocation.dropped.append(value)
            invocation.flags.append(candidate)
            position += 1
            continue

        if value in ("-u", "--user"):
            following = _next_word(tokens, position + 1)
            if following is None:
                invocation.blocked = f"sudo {value} names no user"
                break
            invocation.user = following.value
            invocation.flags.extend([candidate, following])
            position += 2
            continue

        if value.startswith("--user="):
            invocation.user = value.split("=", 1)[1]
            invocation.flags.append(candidate)
            position += 1
            continue

        if value.startswith("-u") and len(value) > 2:
            invocation.user = value[2:]
            invocation.flags.append(candidate)
            position += 1
            continue

        if value in _VALUE_FLAGS:
            invocation.dropped.append(value)
            invocation.flags.append(candidate)
            following = _next_word(tokens, position + 1)
            if following is None:
                position += 1
                break
            invocation.flags.append(following)
            position += 2
            continue

        if value.startswith("-"):
            invocation.dropped.append(value)
            invocation.flags.append(candidate)
            position += 1
            continue

        break

    # The program.
    program = _next_word(tokens, position)
    if program is None:
        if invocation.blocked is None:
            invocation.blocked = "the sudo runs no program"
        return invocation

    if _ASSIGNMENT_RE.match(program.value):
        # sudo VAR=value cmd - the assignment belongs to the command,
        # and it has to survive the rewrite.
        invocation.assignment = program
        following = _next_word(tokens, position + 1)
        if following is None:
            invocation.blocked = "the sudo runs no program"
            return invocation
        invocation.program = following
    else:
        invocation.program = program

    # The arguments of the program.
    invocation.args = _words_after(tokens, position + 1, invocation.program)
    return invocation


def _next_word(tokens: List[Token], position: int) -> Optional[Token]:
    """The next word token behind *position*, if there is one."""
    for candidate in tokens[position:]:
        if candidate.kind != "word":
            return None
        if candidate.is_command:
            return None
        return candidate
    return None


def _words_after(tokens: List[Token], position: int, program: Token) -> List[Token]:
    """The words that follow the *program*, up to the next operator."""
    words: List[Token] = []
    for candidate in tokens[position:]:
        if candidate.kind == "operator":
            break
        if candidate.kind != "word":
            continue
        if candidate.start < program.end:
            continue
        words.append(candidate)
    return words


# ---------------------------------------------------------------------------
# The gate - may pkexec ask the operator?
# ---------------------------------------------------------------------------


def pkexec_path() -> Optional[str]:
    """The path of the ``pkexec`` program, if it is installed."""
    return shutil.which("pkexec")


def gui_session(env: Optional[Dict[str, str]] = None) -> bool:
    """Whether a graphical session is there to show a window in.

    Args:
        env: The environment to look at (the process environment by
            default).

    Returns:
        ``True`` when a display is there for the window.
    """
    environment = os.environ if env is None else env
    return bool(environment.get("DISPLAY") or environment.get("WAYLAND_DISPLAY"))


def running_processes() -> Set[str]:
    """The names of the processes that are running.

    Returns:
        The names of the running processes, read from ``/proc``.
    """
    names: Set[str] = set()
    try:
        entries = os.listdir("/proc")
    except OSError:  # pragma: no cover - /proc is always there on Linux
        return names

    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/comm", encoding="utf-8", errors="replace") as handle:
                names.add(handle.read().strip())
        except OSError:
            continue
    return names


def polkit_agent() -> Optional[str]:
    """The polkit authentication agent that is running, if there is one.

    A graphical agent is what draws the dialog.  Without one, ``pkexec``
    either asks on the terminal - the thing this module exists to
    prevent - or waits for an agent that never comes.
    """
    running = running_processes()
    for name in POLKIT_AGENTS:
        if name in running:
            return name
    return None


def terminal_is_managed() -> bool:
    """Whether the terminal belongs to an application that draws the screen.

    An application that draws the screen itself puts the terminal into
    cbreak mode, and cbreak switches the **echo** off.  A terminal with
    the echo on is an ordinary console: a question asked on it is read
    by the human in front of it.

    Returns:
        ``True`` when the terminal must not be used for a question.
    """
    if termios is None:  # pragma: no cover - not POSIX
        return True

    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        # There is no terminal to ask on.
        return True

    try:
        attributes = termios.tcgetattr(fd)
    except Exception:  # pragma: no cover - defensive
        return True
    finally:
        os.close(fd)

    lflag = attributes[3]
    return not bool(lflag & termios.ECHO)


def pkexec_usable(env: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """Whether ``pkexec`` can ask the operator for a password.

    Args:
        env: The environment to look at.

    Returns:
        A ``(usable, reason)`` pair.  The reason says what is missing
        when it is not usable.
    """
    path = pkexec_path()
    if path is None:
        return False, "pkexec is not installed"

    if not gui_session(env):
        return False, "there is no graphical session to show the window in"

    if polkit_agent() is None:
        return False, "no polkit authentication agent is running"

    return True, ""


def privilege_status(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Report how a privileged command would be run on this machine.

    Returns:
        A dictionary with:
            - 'backend': 'pkexec' or 'sudo' - what would be used.
            - 'usable': whether the window can be shown.
            - 'pkexec_path': the path of the ``pkexec`` program.
            - 'gui_session': whether a display is there.
            - 'polkit_agent': the agent that is running, if there is one.
            - 'terminal_managed': whether the terminal belongs to an
              application that draws the screen.
            - 'reason': what is missing, when the window cannot be shown.
    """
    usable, reason = pkexec_usable(env)
    agent = polkit_agent()
    return {
        "backend": "pkexec" if usable else "sudo",
        "usable": usable,
        "pkexec_path": pkexec_path(),
        "gui_session": gui_session(env),
        "polkit_agent": agent,
        "terminal_managed": terminal_is_managed(),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# The rewrite
# ---------------------------------------------------------------------------


@dataclass
class _Replacement:
    """A part of the command line that is going to be replaced.

    Attributes:
        start: the offset the replacement begins at.
        end: the offset the replacement ends at.
        prefix: the text that is put in front of the copy.
        program: the text of the program, when it is generated.
        copy_from: the offset the copy begins at.
        copy_to: the offset the copy ends at.
    """

    start: int
    end: int
    prefix: str
    program: str = ""
    copy_from: int = 0
    copy_to: int = 0

    def render(self, command: str) -> str:
        """The text that replaces the region, taken from *command*."""
        return self.prefix + self.program + command[self.copy_from : self.copy_to]


def _pkexec_prefix(user: Optional[str], disable_internal_agent: bool) -> str:
    """The text that replaces the ``sudo`` and its flags.

    ``--keep-cwd`` keeps the working directory: ``pkexec`` runs a program
    in the home directory of the target user, and ``sudo`` runs it where
    the operator stands.  Without the flag, ``sudo make install`` would
    install into the wrong place.

    ``--disable-internal-agent`` stops ``pkexec`` from falling back to
    its own textual agent when no graphical agent answers - that agent
    asks on the terminal, which is the thing this module exists to
    prevent.  It is only passed when the terminal must not be used.
    """
    parts = ["pkexec", "--keep-cwd"]
    if disable_internal_agent:
        parts.append("--disable-internal-agent")
    if user:
        parts.extend(["--user", shlex.quote(user)])
    return " ".join(parts) + " "


def _program_is_executable(value: str) -> bool:
    """Whether a program name is a program and not a shell builtin."""
    if not _PLAIN_PROGRAM_RE.match(value):
        return False
    if "/" in value:
        # A path is a path: if it is not there, the error is the
        # program's own.
        return True
    return shutil.which(value) is not None


def _replacement_for(
    command: str,
    invocation: SudoInvocation,
    disable_internal_agent: bool,
) -> Optional[_Replacement]:
    """Build the replacement of one ``sudo``, if it can be rewritten."""
    if invocation.blocked or invocation.program is None:
        return None

    program = invocation.program
    if not _PLAIN_PROGRAM_RE.match(program.value):
        # The program carries shell meaning (``sudo $(whoami)``), and
        # there is no honest way to rewrite that.
        return None

    prefix = _pkexec_prefix(invocation.user, disable_internal_agent)

    # sudo VAR=value cmd - the assignment has to be set for the program
    # itself, and the program has to be a program that sets it: env.
    if invocation.assignment is not None:
        env_path = shutil.which("env")
        if env_path:
            return _Replacement(
                start=invocation.token.start,
                end=invocation.end,
                prefix=prefix + env_path + " ",
                copy_from=invocation.assignment.start,
                copy_to=invocation.end,
            )

    # A program that is not on the PATH is a shell builtin: it is run
    # through a shell.
    if not _program_is_executable(program.value):
        words = [program.value] + [argument.value for argument in invocation.args]
        return _Replacement(
            start=invocation.token.start,
            end=invocation.end,
            prefix=prefix + "/bin/sh -c " + shlex.quote(" ".join(words)),
        )

    # The ordinary case: the program and its arguments are kept as they
    # were written.
    return _Replacement(
        start=invocation.token.start,
        end=invocation.end,
        prefix=prefix,
        copy_from=invocation.assignment.start if invocation.assignment else program.start,
        copy_to=invocation.end,
    )


def _apply(command: str, replacements: List[_Replacement]) -> str:
    """Put the replacements into the command line."""
    if not replacements:
        return command

    result: List[str] = []
    cursor = 0
    for replacement in sorted(replacements, key=lambda item: item.start):
        result.append(command[cursor : replacement.start])
        result.append(replacement.render(command))
        cursor = replacement.end
    result.append(command[cursor:])
    return "".join(result)


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


@dataclass
class PrivilegePlan:
    """What the toolkit is going to do with a command.

    Attributes:
        command: the command as it is going to be run.
        backend: 'none', 'pkexec' or 'sudo' - what runs it.
        escalated: whether a privilege escalation is involved.
        rewrites: one entry per rewritten ``sudo``.
        notes: what was changed, and what was left alone.
        error: why the command must not run, when it must not.
        timeout: the timeout the command needs, when it needs another one.
    """

    command: str
    backend: str = "none"
    escalated: bool = False
    rewrites: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None
    timeout: Optional[int] = None

    @property
    def success(self) -> bool:
        """Whether the command may run."""
        return self.error is None


def plan_privilege(
    command: str,
    mode: str = "auto",
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> PrivilegePlan:
    """Plan what to do with a command that asks for root.

    Args:
        command: The command line.
        mode: 'auto', 'pkexec' or 'sudo' - see :data:`PRIVILEGE_MODES`.
        env: The environment to look at (the process environment by
            default).
        timeout: The timeout the caller asked for.  An escalated
            command gets :data:`PRIVILEGE_TIMEOUT` instead, unless the
            caller asked for a timeout of their own.

    Returns:
        The plan.  It never raises: a mode that is not known, or a
        command that cannot be escalated, comes back as a plan with an
        error in it.
    """
    if mode not in PRIVILEGE_MODES:
        return PrivilegePlan(
            command=command,
            error=(
                f"Unknown privilege mode {mode!r}; "
                f"it has to be one of {', '.join(PRIVILEGE_MODES)}"
            ),
        )

    invocations = find_sudo(command)
    if not invocations:
        return PrivilegePlan(command=command, backend="none")

    if mode == "sudo":
        return PrivilegePlan(
            command=command,
            backend="sudo",
            escalated=True,
            notes=["the sudo is run as it was written"],
        )

    usable, reason = pkexec_usable(env)

    if not usable:
        if mode == "pkexec":
            return PrivilegePlan(
                command=command,
                backend="pkexec",
                escalated=True,
                error=f"The command needs root and pkexec cannot ask for it: {reason}",
            )
        return PrivilegePlan(
            command=command,
            backend="sudo",
            escalated=True,
            notes=[f"pkexec was not used: {reason}; the sudo is run as it was written"],
        )

    # The terminal must not be used for a question when an application
    # is drawing on it.
    disable_internal_agent = terminal_is_managed()

    replacements: List[_Replacement] = []
    rewrites: List[Dict[str, Any]] = []
    notes: List[str] = []

    for invocation in invocations:
        replacement = _replacement_for(command, invocation, disable_internal_agent)
        if replacement is None:
            notes.append(
                f"the sudo was left as it was written: {invocation.blocked or 'it cannot be rewritten'}"
            )
            continue

        replacements.append(replacement)
        rewrites.append(
            {
                "sudo": invocation.token.text,
                "program": invocation.program.text if invocation.program else "",
                "user": invocation.user,
                "dropped_flags": list(invocation.dropped),
            }
        )
        for flag in invocation.dropped:
            reason_text = _DROP_REASONS.get(flag, "pkexec has no equivalent for it")
            notes.append(f"the flag {flag} of sudo was dropped: {reason_text}")

    if not replacements:
        return PrivilegePlan(
            command=command,
            backend="sudo",
            escalated=True,
            notes=notes + ["no sudo of the command could be rewritten"],
        )

    rewritten = _apply(command, replacements)

    return PrivilegePlan(
        command=rewritten,
        backend="pkexec",
        escalated=True,
        rewrites=rewrites,
        notes=notes,
        timeout=(
            timeout
            if timeout is not None and timeout != DEFAULT_TIMEOUT
            else PRIVILEGE_TIMEOUT
        ),
    )


__all__ = [
    "DEFAULT_TIMEOUT",
    "PRIVILEGE_MODES",
    "PRIVILEGE_TIMEOUT",
    "PrivilegePlan",
    "SudoInvocation",
    "Token",
    "find_sudo",
    "gui_session",
    "pkexec_path",
    "pkexec_usable",
    "plan_privilege",
    "polkit_agent",
    "privilege_status",
    "running_processes",
    "scan",
    "terminal_is_managed",
]
