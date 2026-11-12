#!/usr/bin/env python3
"""
The manual test of the two questions the operator is asked:
the question of the agent, and the password of root.

Why this script exists
----------------------
The operator reported two symptoms that look like one:

* the question of the agent does not reach the operator — what is typed
  is invisible, and the terminal shows nothing of it;
* the password of root — asked by ``pkexec`` through the polkit window
  — leaves the terminal in the same state.

The probes of the repository answer that *for* the operator: they render
the TUI into a buffer of their own and measure it there
(``investigate/tui-hidden-input/probe_hidden_input.py``,
``investigate/privilege-terminal-echo/probe_privilege_terminal.py``).
What they cannot do is put the operator in front of the thing and ask
*do you see it?*

This script does that.  It drives the **real** components, in the
terminal of the operator:

1. **the question of the agent** — the real layout, the real panels,
   the real reader and the real input module of the TUI.  The operator
   types an answer into the footer of the TUI, and *sees* it;
2. **the password of root** — the real ``execute_shell_command`` of the
   Linux toolkit, behind the real privilege gate.  The polkit window
   opens, the operator types the password *there*, and the terminal of
   the operator is measured before and after;
3. **the relation** — the summary that says whether the two are the
   same defect, and what they share.

What is measured
----------------
============================================ ==========================================
the answer of the operator                   the round trip: what was typed reaches the
                                             question that is waiting
the text on the screen                       the footer is rendered into a buffer and
                                             searched for the typed text — a panel that
                                             is taller than its partition is cropped
                                             from the bottom, and the answer line is
                                             the last line of the panel
the echo of the terminal                     off while the TUI draws the screen (the TUI
                                             draws the text itself), on again when
                                             the question is answered
the window of polkit                         the operator says whether the
                                             *Authentication Required* window opened
the echo of the terminal                     on again after the window closed
============================================ ==========================================

The script gives the terminal back whatever it does: the reader is
stopped in a ``finally``, and the toolkit gives the terminal back after
every command it runs.

Usage::

    python scripts/manual_hitl_privilege_test.py                  # both parts
    python scripts/manual_hitl_privilege_test.py hitl             # only the question
    python scripts/manual_hitl_privilege_test.py privilege        # only the password
    python scripts/manual_hitl_privilege_test.py --all            # add the secret question
    python scripts/manual_hitl_privilege_test.py --list           # the questions of the bank
    python scripts/manual_hitl_privilege_test.py --command "sudo id"
    python scripts/manual_hitl_privilege_test.py --privilege-mode sudo

``--privilege-mode sudo`` runs the command **as it was written**: the
password is then asked on the terminal, and the terminal hides what is
typed while it is read.  That is the path the hidden typing was
reported on; the default (``auto``) is the window.

The exit code is 0 when every check holds, and 1 when one of them does
not.

Category: HITL / Testing
Retriever Keywords: manual test, hitl, question, privilege, sudo, pkexec,
polkit, password, hidden input, echo, terminal
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import termios
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# The repository root is on the path, so the modules import from the
# working copy.  The path is computed, never written down.
REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402
from rich.live import Live  # noqa: E402

# The normalisation of a yes/no answer is the one of the consumer:
# the script mirrors the production path, so it uses the production
# function — a copy of it would drift.
from components.event_consumer import _normalise_yes_no  # noqa: E402
from components.hitl_question_command import (  # noqa: E402
    PREDEFINED_QUESTIONS,
    PredefinedQuestion,
)
from components.hitl_timeout import NO_TIMEOUT  # noqa: E402
from components.tui.input_reader import NonBlockingInputReader  # noqa: E402
from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    fit_footer,
    footer_height,
    render_footer,
    render_header,
)
from components.tui.state_bridge import TuiInputModule, TuiState  # noqa: E402
from toolkits.linux_toolkit import privilege as privilege_module  # noqa: E402
from toolkits.linux_toolkit.operations import execute_shell_command  # noqa: E402


#: The command the privilege part runs by default.  It asks for root and
#: does nothing else.
DEFAULT_COMMAND = "sudo id"

#: The questions of the bank the script asks by default.  The secret
#: question is left out: it is asked with ``--all``.
DEFAULT_QUESTIONS = ("text-01", "yesno-01", "menu-01")


# ---------------------------------------------------------------------------
# The terminal
# ---------------------------------------------------------------------------


def echo_is_on() -> bool:
    """Whether the controlling terminal echoes what is typed.

    The echo is the state the hidden typing is about: an application
    that draws the screen itself switches it off, and the state belongs
    to the **terminal**, not to the process — so it outlives the agent.

    Returns:
        ``True`` when the terminal echoes.  A machine without a
        terminal to ask on reports ``True``: there is nothing to hide.
    """
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return True

    try:
        attributes = termios.tcgetattr(fd)
    except Exception:  # pragma: no cover - defensive
        return True
    finally:
        os.close(fd)

    return bool(attributes[3] & termios.ECHO)


def describe_the_echo(state: bool) -> str:
    """Return the state of the echo, as it is shown."""
    return "on" if state else "off"


# ---------------------------------------------------------------------------
# The question of the agent
# ---------------------------------------------------------------------------


def normalise_yes_no(response: str) -> str:
    """Normalise a yes/no answer the way the consumer normalises it.

    The consumer keeps the words of the operator: "yes, go ahead"
    reaches the agent as it was typed, and only the canonical "y" and
    "n" are normalised.

    Args:
        response: The raw answer.

    Returns:
        The answer, normalised.
    """
    return _normalise_yes_no(response or "")


def handle_key(state: TuiState, key: str) -> None:
    """Apply one key to the buffer of the command bar.

    The rules are the ones of ``TuiApp._handle_key`` — the harness
    drives the same buffer the TUI drives, so the answer of the
    operator travels the same road.

    Args:
        state: The state of the TUI.
        key: The normalised key.
    """
    with state._lock:
        buffer = state.input_buffer
        position = state.cursor_pos

        if key == "BACKSPACE":
            if position > 0:
                state.input_buffer = buffer[: position - 1] + buffer[position:]
                state.cursor_pos = position - 1
            return

        if key == "DELETE":
            if position < len(buffer):
                state.input_buffer = buffer[:position] + buffer[position + 1 :]
            return

        if key == "LEFT":
            state.cursor_pos = max(0, position - 1)
            return

        if key == "RIGHT":
            state.cursor_pos = min(len(buffer), position + 1)
            return

        if key == "HOME":
            state.cursor_pos = 0
            return

        if key == "END":
            state.cursor_pos = len(buffer)
            return

        if len(key) == 1 and key.isprintable():
            state.input_buffer = buffer[:position] + key + buffer[position:]
            state.cursor_pos = position + 1


class TuiHarness:
    """The TUI of the agent, driven by hand.

    Every part is the real one: the layout, the panels, the reader and
    the input module of the TUI.  Only the loop is the harness'.

    Attributes:
        console: The console of the operator.
        state: The state of the TUI.
        module: The input module of the TUI — the one that asks the
            question in the footer.
        reader: The reader of the keyboard.
        layout: The layout of the TUI.
    """

    def __init__(self, console: Console) -> None:
        self.console = console
        self.state = TuiState()
        self.module = TuiInputModule(self.state)
        self.reader = NonBlockingInputReader()
        self.layout = build_torvalds_layout()
        self.typed: str = ""

    # -- the frame --------------------------------------------------------

    def render_frame(self) -> None:
        """Draw one frame of the TUI — the header and the footer.

        The panels are the ones of ``TuiApp._update_layout_panes``: the
        header of the application, and the footer that carries the
        question of the agent *and* the line the answer is typed on.
        """
        state = self.state

        self.layout["header"].update(
            render_header(
                model_name=state.model_name or "manual test",
                memory_count=state.memory_msg_count,
                hitl_enabled=state.hitl_enabled,
                session_start_time=state.session_start_time,
                is_busy=state.is_busy,
            )
        )

        footer = render_footer(
            input_buffer=state.input_buffer,
            cursor_pos=state.cursor_pos,
            hitl_active=state.hitl_active,
            hitl_prompt=state.hitl_prompt,
            hitl_time_remaining=state.get_hitl_time_remaining(),
            hitl_default_answer=state.hitl_default_answer,
            is_busy=state.is_busy,
            hitl_input_type=state.hitl_input_type,
        )
        # The HITL panel is taller than the command bar: it carries the
        # question *and* the line the answer is typed on.  The partition
        # is given the room the panel needs, or the answer is cropped
        # away and the operator types into the void.
        fit_footer(self.layout, self.console, footer, state.hitl_active)
        self.layout["footer"].update(footer)

    # -- the question -----------------------------------------------------

    async def ask(self, question: PredefinedQuestion) -> str:
        """Ask one question in the TUI and return the answer.

        The question travels the road of a question of the agent: the
        module of the TUI is asked, the module puts the question into
        the footer and waits for the answer, and the answer arrives
        through the future the command bar resolves with Enter.

        Args:
            question: The question to ask.

        Returns:
            The answer of the operator — the empty string when nobody
            answered.
        """
        self.module.set_input_type(question.input_type)

        if question.input_type == "yesno":
            # The consumer asks the module for the **raw** answer and
            # normalises it itself, so that "yes, go ahead" reaches the
            # agent as the operator typed it.
            task = asyncio.ensure_future(
                self.module.prompt_with_status(
                    message=f"{question.question} [y/N]",
                    default="",
                    timeout=NO_TIMEOUT,
                )
            )
        elif question.input_type == "menu":
            task = asyncio.ensure_future(
                self.module.menu_with_status(
                    message=question.question,
                    options=list(question.options),
                    timeout=NO_TIMEOUT,
                )
            )
        elif question.input_type == "password":
            # The consumer asks the module for the secret, and the
            # module never shows it: the TUI draws what is typed, so a
            # secret typed in the footer is on the screen.
            task = asyncio.ensure_future(
                self.module.password(
                    message=f"{question.question} Enter password: ",
                    timeout=NO_TIMEOUT,
                )
            )
        else:
            task = asyncio.ensure_future(
                self.module.prompt_with_status(
                    message=f"{question.question} Your response: ",
                    default="",
                    timeout=NO_TIMEOUT,
                )
            )

        # The reader is started **before** the screen is drawn.  A
        # terminal in canonical mode holds the line that was typed into
        # it, and the switch to cbreak throws that line away: a
        # keystroke that arrives before the reader exists is lost
        # silently.  The operator must not lose the first word of the
        # answer to a race.
        self.reader.start()
        try:
            with Live(
                self.layout,
                console=self.console,
                screen=True,
                auto_refresh=False,
                redirect_stdout=False,
                redirect_stderr=False,
            ) as live:
                try:
                    while not task.done():
                        while self.reader.is_available():
                            key = self.reader.poll_key()
                            if not key:
                                break
                            if key == "ENTER":
                                # The text is kept before the answer is
                                # delivered: the submission empties the
                                # buffer of the command bar.
                                self.typed = self.state.input_buffer
                                self.submit()
                            elif key in ("CTRL_C", "CTRL_D"):
                                self.cancel()
                            else:
                                handle_key(self.state, key)
                        if self.state.input_buffer:
                            # The buffer of the command bar is emptied by
                            # the submission — the text that was typed is
                            # kept here.
                            self.typed = self.state.input_buffer
                        self.render_frame()
                        live.update(self.layout, refresh=True)
                        await asyncio.sleep(0.02)
                finally:
                    if self.state.input_buffer:
                        self.typed = self.state.input_buffer
        finally:
            # The terminal is given back before the screen is left: an
            # operator whose terminal is mute types into the void.
            self.reader.stop()
            if not task.done():
                task.cancel()

        answer = ""
        if task.done() and not task.cancelled():
            try:
                answer = task.result()
            except asyncio.CancelledError:
                # The operator gave the question up with Ctrl-C.
                answer = ""
        if isinstance(answer, tuple):
            # The module reports ``(answer, was_timeout)``.
            answer = answer[0]
        if question.input_type == "yesno":
            answer = normalise_yes_no(answer)
        return answer

    def submit(self) -> None:
        """Deliver the typed answer to the question that is waiting."""
        state = self.state
        if state.hitl_active and state.hitl_future and not state.hitl_future.done():
            state.hitl_future.set_result(state.input_buffer.strip())
        state.input_buffer = ""
        state.cursor_pos = 0

    def cancel(self) -> None:
        """Give the question up — the operator pressed Ctrl-C."""
        state = self.state
        if state.hitl_active and state.hitl_future and not state.hitl_future.done():
            state.hitl_future.cancel()
        state.input_buffer = ""
        state.cursor_pos = 0


def render_the_screen(
    typed: str,
    prompt: str,
    width: int = 120,
    height: int = 24,
) -> str:
    """Render the TUI with a question waiting, and return the screen.

    The rendering is the one of the probe of the hidden input
    (``investigate/tui-hidden-input/probe_hidden_input.py``): the real
    layout, the real panel, and the real measurement of the room the
    panel needs.

    Args:
        typed: The text the operator typed.
        prompt: The question of the agent.
        width: The width of the screen.
        height: The height of the screen.

    Returns:
        The text of the screen.
    """
    console = Console(width=width, height=height, file=io.StringIO())
    layout = build_torvalds_layout()
    panel = render_footer(
        input_buffer=typed,
        cursor_pos=len(typed),
        hitl_active=True,
        hitl_prompt=prompt,
    )
    fit_footer(layout, console, panel, True)
    layout["footer"].update(panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


def measure_the_screen(
    typed: str,
    prompt: str,
    width: int = 120,
    height: int = 24,
) -> Dict[str, object]:
    """Measure what the operator saw while they typed.

    Args:
        typed: The text the operator typed.
        prompt: The question of the agent.
        width: The width of the terminal of the operator.
        height: The height of the terminal of the operator.

    Returns:
        A dictionary with:
            - 'visible': whether the typed text is on the screen;
            - 'needed': the number of lines the panel needs;
            - 'given': the number of lines the partition was given;
            - 'cropped': whether the panel was taller than its
              partition — and the answer line, the last line of the
              panel, was cut off.
    """
    screen = render_the_screen(typed, prompt, width=width, height=height)

    console = Console(width=width, height=height, file=io.StringIO())
    panel = render_footer(
        input_buffer=typed,
        cursor_pos=len(typed),
        hitl_active=True,
        hitl_prompt=prompt,
    )
    needed = footer_height(console, panel)

    layout = build_torvalds_layout()
    given = fit_footer(layout, console, panel, True)

    return {
        "visible": typed in screen if typed else True,
        "needed": needed,
        "given": given,
        "cropped": given < needed,
    }


def run_the_hitl_part(console: Console, questions: Sequence[PredefinedQuestion]) -> List[Dict]:
    """Ask every question of the bank in the TUI, and measure it.

    Args:
        console: The console of the operator.
        questions: The questions to ask.

    Returns:
        One record per question.
    """
    records: List[Dict] = []

    for question in questions:
        console.rule(f"[bold cyan]{question.id} — {question.input_type}[/bold cyan]")
        console.print(
            f"[dim]{question.question}[/dim]\n"
            "[dim]Type the answer in the footer and press Enter.[/dim]\n"
        )

        harness = TuiHarness(console)

        echo_before = echo_is_on()
        try:
            answer = asyncio.run(harness.ask(question))
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]■ interrupted[/yellow]")
            break
        finally:
            harness.reader.stop()

        echo_after = echo_is_on()
        typed = harness.typed
        measurement = measure_the_screen(
            typed,
            question.question,
            width=console.width,
            height=console.height,
        )

        secret = question.input_type == "password"

        console.print()
        if secret:
            # A secret is never echoed — not into the report, not into
            # the log.  The rule is the one of the ``\question``
            # command: a secret does not belong in a report.
            console.print("  the answer          : [bold](not shown)[/bold]")
            console.print("  what was typed      : [bold](not shown)[/bold]")
        else:
            console.print(f"  the answer          : [bold]{answer!r}[/bold]")
            console.print(f"  what was typed      : [bold]{typed!r}[/bold]")
        console.print(
            "  the typed text is on the screen: [bold]%s[/bold]"
            % ("yes" if measurement["visible"] else "NO")
        )
        console.print(
            "  the answer line was cropped     : [bold]%s[/bold]"
            % ("yes" if measurement["cropped"] else "no")
        )
        console.print(
            "  the echo before / after         : %s / %s"
            % (describe_the_echo(echo_before), describe_the_echo(echo_after))
        )

        if secret and measurement["visible"]:
            console.print(
                "  [yellow]note:[/yellow] the TUI draws what is typed, and a "
                "secret is typed like\n"
                "         everything else — the passphrase is on the screen "
                "while it is typed."
            )

        seen = ask_the_operator(
            console,
            "  did you see the text you typed, while you typed it?",
        )
        console.print()

        records.append(
            {
                "question": question,
                "answered": bool(answer),
                "answer": "" if secret else answer,
                "typed": "" if secret else typed,
                "visible": measurement["visible"],
                "cropped": measurement["cropped"],
                "echo_before": echo_before,
                "echo_after": echo_after,
                "seen_by_the_operator": seen,
            }
        )

    return records


# ---------------------------------------------------------------------------
# The password of root
# ---------------------------------------------------------------------------


def run_the_privilege_part(
    console: Console,
    command: str,
    mode: str,
) -> Dict[str, object]:
    """Ask for root the way the agent does, and measure the terminal.

    The gate of the toolkit decides whether the question may be asked
    in a window at all; the status is shown first, so the operator
    knows what to expect before the window opens.

    Args:
        console: The console of the operator.
        command: The command to run.
        mode: ``"auto"`` (the window), ``"pkexec"`` or ``"sudo"`` (the
            terminal).

    Returns:
        The record of the measurement.
    """
    status = privilege_module.privilege_status()
    plan = privilege_module.plan_privilege(command, mode)

    console.rule("[bold cyan]the gate of the privilege escalation[/bold cyan]")
    console.print(f"  the command            : [bold]{command}[/bold]")
    console.print(f"  the mode               : [bold]{mode}[/bold]")
    console.print(f"  pkexec                 : {status['pkexec_path'] or 'not installed'}")
    console.print(f"  a graphical session    : {'yes' if status['gui_session'] else 'no'}")
    console.print(f"  the polkit agent       : {status['polkit_agent'] or 'none'}")
    console.print(
        "  the terminal is drawn by an application: %s"
        % ("yes" if status["terminal_managed"] else "no")
    )
    if status["reason"]:
        console.print(f"  the reason             : [yellow]{status['reason']}[/yellow]")

    console.print()
    if plan.error:
        console.print(f"  [yellow]the command is refused:[/yellow] {plan.error}")
        console.print(
            "  the question of a privilege escalation belongs in a window, "
            "and there is none here."
        )
        return {
            "command": command,
            "mode": mode,
            "planned": plan.command,
            "refused": True,
            "reason": plan.error,
            "question": "the password of root was asked in a window",
            "asked": False,
            "succeeded": False,
            "echo_before": echo_is_on(),
            "echo_after": echo_is_on(),
        }

    console.print(f"  the command that runs  : [bold]{plan.command}[/bold]")
    for note in plan.notes:
        console.print(f"  [dim]note: {note}[/dim]")
    console.print()
    if mode == "sudo":
        console.print(
            "  [bold]Watch this terminal:[/bold] the password of root is "
            "asked **here**, and the terminal"
        )
        console.print(
            "  [dim]hides what is typed while it is read.  That is what sudo "
            "does — and it is the path[/dim]"
        )
        console.print(
            "  [dim]the hidden typing was reported on.[/dim]\n"
        )
    else:
        console.print(
            "  [bold]Watch the screen:[/bold] a window of the desktop asks "
            "for the password of root."
        )
        console.print(
            "  [dim]The password is typed into that window, never into this "
            "terminal.[/dim]\n"
        )

    echo_before = echo_is_on()
    result = execute_shell_command(command, privilege=mode)
    echo_after = echo_is_on()

    console.print()
    console.print(f"  the backend            : [bold]{result.get('privilege')}[/bold]")
    console.print(f"  the return code        : {result.get('returncode')}")
    output = (result.get("stdout") or result.get("stderr") or "").strip()
    if output:
        console.print(f"  the output             : {output[:200]}")
    console.print(
        "  the echo before / after : %s / %s"
        % (describe_the_echo(echo_before), describe_the_echo(echo_after))
    )

    if mode == "sudo":
        # The command runs as it was written: the password is asked on
        # the terminal of the operator, and the terminal hides what is
        # typed while it is read.
        asked = ask_the_operator(
            console,
            "  was the password asked on THIS terminal?",
        )
        question = "the password of root was asked on the terminal"
    else:
        asked = ask_the_operator(
            console,
            "  did the Authentication Required window open?",
        )
        question = "the password of root was asked in a window"
    console.print()

    return {
        "command": command,
        "mode": mode,
        "planned": plan.command,
        "refused": False,
        "question": question,
        "asked": asked,
        "succeeded": bool(result.get("success")),
        "returncode": result.get("returncode"),
        "echo_before": echo_before,
        "echo_after": echo_after,
    }


# ---------------------------------------------------------------------------
# The operator
# ---------------------------------------------------------------------------


def ask_the_operator(console: Console, question: str) -> bool:
    """Ask the operator a yes/no question, in the plain terminal.

    The terminal is back to normal when this is called: the reader of
    the TUI has been stopped, and the toolkit has given the terminal
    back.

    Args:
        console: The console of the operator.
        question: The question to ask.

    Returns:
        ``True`` when the operator answered yes.
    """
    try:
        answer = input(f"{question} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return False
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def report(
    console: Console,
    hitl: Sequence[Dict],
    privilege: Optional[Dict],
) -> bool:
    """Print the summary and say whether every check holds.

    Args:
        console: The console of the operator.
        hitl: The records of the questions.
        privilege: The record of the privilege part.

    Returns:
        ``True`` when every check holds.
    """
    console.rule("[bold cyan]the result[/bold cyan]")

    checks: List[Tuple[str, bool]] = []

    if not checks and privilege is None:
        console.print(
            "  [yellow]nothing was measured[/yellow] — the run was "
            "interrupted before a question was asked."
        )
        console.print()
        return False

    for record in hitl:
        question = record["question"]
        identifier = f"the question {question.id}"
        checks.append(
            (f"{identifier} reached the operator", bool(record["answered"]))
        )
        checks.append(
            (f"{identifier} was on the screen while it was typed",
             bool(record["visible"]))
        )
        checks.append(
            (f"{identifier} was not cropped away", not record["cropped"])
        )
        checks.append(
            (f"the terminal echoed again after {identifier}",
             bool(record["echo_after"]))
        )

    if privilege is not None:
        checks.append(
            (privilege["question"], bool(privilege["asked"]))
        )
        checks.append(
            ("the terminal echoed again after the password of root",
             bool(privilege["echo_after"]))
        )

    for text, held in checks:
        console.print("  %-58s : %s" % (text, "yes" if held else "NO"))

    console.print()
    console.print("  the facts behind it:")
    console.print(
        "  %-58s : %s"
        % (
            "the echo is off while the TUI draws the screen",
            "yes — by design: the TUI draws the typed text itself",
        )
    )
    console.print(
        "  %-58s : %s"
        % (
            "the echo is off while a password is read on the terminal",
            "yes — that is how a password is hidden (sudo, polkit's own agent)",
        )
    )
    console.print(
        "  %-58s : %s"
        % (
            "the echo belongs to the terminal, not to the process",
            "yes — so it outlives the agent when it is not given back",
        )
    )

    console.print()
    console.print(
        "  [bold]the two are not the same thing:[/bold]\n"
        "  the question of the agent is asked in the terminal of the "
        "operator, and the TUI draws\n"
        "  what they type — so the text has to be on the screen, or the "
        "operator types into the void;\n"
        "  the password of root is asked in a window of the desktop, and "
        "the terminal of the operator\n"
        "  is not involved in it at all.\n"
        "  what they share is the state of the terminal: an application "
        "that owns the screen switches\n"
        "  the echo off, and that state belongs to the terminal — so it "
        "has to be given back."
    )

    held = all(ok for _, ok in checks)
    console.print()
    if held:
        console.print("  [bold green]every check holds[/bold green]")
    else:
        console.print("  [bold red]a check does not hold[/bold red]")

    return held


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse the arguments of the script."""
    parser = argparse.ArgumentParser(
        description="The manual test of the question of the agent and of "
        "the password of root.",
    )
    parser.add_argument(
        "part",
        nargs="?",
        default="all",
        choices=("all", "hitl", "privilege"),
        help="the part to run (default: all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="ask the secret question as well",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the questions of the bank and stop",
    )
    parser.add_argument(
        "--command",
        default=DEFAULT_COMMAND,
        help=f"the command of the privilege part (default: {DEFAULT_COMMAND})",
    )
    parser.add_argument(
        "--privilege-mode",
        default="auto",
        choices=("auto", "pkexec", "sudo"),
        help="how the command is escalated (default: auto — the window)",
    )
    return parser.parse_args(argv)


def the_questions(include_secret: bool) -> List[PredefinedQuestion]:
    """The questions of the bank the script asks.

    Args:
        include_secret: Whether the secret question is asked as well.

    Returns:
        The questions, in the order of the bank.
    """
    wanted = list(DEFAULT_QUESTIONS)
    if include_secret:
        wanted.append("password-01")

    chosen = []
    for identifier in wanted:
        for question in PREDEFINED_QUESTIONS:
            if question.id == identifier:
                chosen.append(question)
    return chosen


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the manual test.

    Returns:
        The exit code: 0 when every check holds, 1 when one does not.
    """
    args = parse_arguments(argv)
    console = Console()

    if args.list:
        for question in PREDEFINED_QUESTIONS:
            console.print(
                f"  {question.id:<12} {question.input_type:<9} {question.question}"
            )
        return 0

    if not sys.stdin.isatty():
        console.print(
            "[red]The manual test needs a terminal: the operator is the "
            "one who sees the question and types the password.[/red]"
        )
        return 2

    console.print("[bold cyan]=== The manual test of the HITL question "
                  "and of the password of root ===[/bold cyan]")
    console.print(
        f"[dim]the terminal echoes now: {describe_the_echo(echo_is_on())}[/dim]\n"
    )

    hitl: List[Dict] = []
    privilege: Optional[Dict] = None

    if args.part in ("all", "hitl"):
        hitl = run_the_hitl_part(console, the_questions(args.all))

    if args.part in ("all", "privilege"):
        privilege = run_the_privilege_part(
            console, args.command, args.privilege_mode
        )

    held = report(console, hitl, privilege)

    console.print(
        "\n[dim]the terminal echoes at the end: %s[/dim]"
        % describe_the_echo(echo_is_on())
    )

    return 0 if held else 1


if __name__ == "__main__":
    raise SystemExit(main())
