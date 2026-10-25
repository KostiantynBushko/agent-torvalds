#!/usr/bin/env python3
"""
Interactive HITL test — the Human-in-the-Loop path, driven by a human.

What it tests
-------------
The full HITL round trip, with the *real* components and no LLM in the loop:

1. ``components.hitl_question.split_question`` splits the assistant message
   into *question*, *context* and *options*;
2. ``components.hitl_question.detect_input_type`` decides what kind of
   answer the question wants (``text`` / ``yesno`` / ``menu`` / ``password``);
3. the question is rendered the way ``EventConsumer._render_question`` does;
4. the answer is collected the way ``EventConsumer._collect_answer`` does,
   through ``components.console_input_module.ConsoleInputModule``;
5. the answer is validated against what the question asked for, and recorded
   in the HITL history of ``components.human_loop_handler.HumanLoopHandler``.

The commands below are typed *at a prompt* — the harness intercepts
``input()`` / ``read_masked()``, so a command works in every prompt type,
including the masked password prompt.

Usage::

    python scripts/hitl_interactive_test.py             # the whole bank
    python scripts/hitl_interactive_test.py menu-01-three-options
    python scripts/hitl_interactive_test.py --list

Commands available at any prompt
---------------------------------

============ ==============================================================
``help``     show the commands
``list``     show the cases and their expected input type
``skip``     skip the current case
``stop``     stop the run
``timeout N`` set the timeout of the current case (0 = expire immediately)
``toggle``   flip the HITL runtime toggle (off = no prompt, default answer)
``add TEXT`` ask an ad-hoc question of your own
============ ==============================================================

Category: HITL / Testing
Retriever Keywords: hitl, interactive test, question bank, human in the loop
"""

from __future__ import annotations

import asyncio
import builtins
import contextlib
import os
import sys
from typing import List, Optional, Tuple

# The self-development clone is the working copy for every self-modification.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

from components.console_input_module import ConsoleInputModule
from components.console_markdown import render_markdown, render_options
from components.hitl_question import detect_input_type, split_question, strip_marker
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.human_loop_handler import HumanLoopHandler
from scripts.hitl_question_bank import QUESTION_BANK, QuestionCase, case_by_id

console = Console()

#: The commands the harness understands at a prompt.
COMMANDS = ("help", "list", "skip", "stop", "toggle", "timeout", "add")


# ---------------------------------------------------------------------------
# Control-flow signals
# ---------------------------------------------------------------------------

class _CommandHandled(Exception):
    """Raised when a typed command was handled and the prompt must repeat."""


class _Skip(Exception):
    """Raised by the ``skip`` command."""


class _Stop(Exception):
    """Raised by the ``stop`` command."""


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------

class Result:
    """The outcome of one case."""

    def __init__(self, case: QuestionCase) -> None:
        self.case = case
        self.detected_type: str = ""
        self.answer: str = ""
        self.was_timeout: bool = False
        self.classification_ok: bool = False
        self.answer_ok: bool = False
        self.reason: str = ""
        self.skipped: bool = False
        self.not_a_question: bool = False

    @property
    def passed(self) -> bool:
        return self.classification_ok and self.answer_ok

    @property
    def known_defect(self) -> bool:
        """``True`` when the case guards a regression that came back."""
        return bool(self.case.regression) and not self.passed

    def status(self) -> str:
        if self.skipped:
            return "⏭  SKIP"
        if self.passed:
            return "✅ PASS"
        if self.known_defect:
            return "🐞 REGRESSION"
        return "❌ FAIL"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class InteractiveHITLTest:
    """Runs the question bank through the real HITL components."""

    def __init__(self) -> None:
        self.console = console
        self.input_module = ConsoleInputModule(self.console)
        self.toggle = HITLRuntimeToggle(initial_state=True, console=self.console)
        self.handler = HumanLoopHandler(
            input_method="console",
            default_timeout=-1,
            default_answer="",
            console=self.console,
            enable_hitl=True,
            runtime_toggle=self.toggle,
        )
        self.results: List[Result] = []
        self._adhoc: List[QuestionCase] = []
        self._current_case: Optional[QuestionCase] = None
        self._current_id: str = ""

    # -- rendering ---------------------------------------------------------

    def _render_question(
        self, question: str, context: str, options: Optional[List[str]] = None
    ) -> None:
        """Render the question exactly like ``EventConsumer`` does.

        The question and the report are rendered as **Markdown** — the
        agent writes Markdown, and showing its source verbatim is noise
        the operator has to read past.
        """
        question = strip_marker(question)
        self.console.print("\n[magenta]🤖 Agent asks:[/magenta]")
        if context:
            render_markdown(self.console, context, style="dim")
        if question:
            if context:
                self.console.print()
            render_markdown(self.console, question, style="magenta")
        if options and len(options) >= 2:
            render_options(self.console, options, style="magenta")

    # -- command interception ---------------------------------------------

    def _is_command(self, raw: str) -> bool:
        """Return ``True`` when *raw* is a harness command."""
        text = raw.strip().lower()
        if not text:
            return False
        head = text.split(" ", 1)[0]
        return head in COMMANDS

    def _run_command(self, raw: str, loop: asyncio.AbstractEventLoop) -> None:
        """Run a command typed at a prompt.

        The command runs in the executor thread that the input module
        uses, so the coroutine that flips the runtime toggle is scheduled
        on the event loop with ``run_coroutine_threadsafe``.
        """
        text = raw.strip()
        command, _, argument = text.partition(" ")
        command = command.lower()
        argument = argument.strip()

        if command == "help":
            self.console.print(
                "[cyan]commands:[/cyan] help, list, skip, stop, "
                "timeout N, toggle, add TEXT"
            )
        elif command == "list":
            for case in QUESTION_BANK + self._adhoc:
                marker = "▶" if case.id == self._current_id else " "
                self.console.print(
                    f"  {marker} [bold]{case.id}[/bold] — {case.title} "
                    f"[dim](expects {case.expected_type})[/dim]"
                )
        elif command == "skip":
            self.console.print("[yellow]⏭  skipped[/yellow]")
            raise _Skip()
        elif command == "stop":
            raise _Stop()
        elif command == "toggle":
            future = asyncio.run_coroutine_threadsafe(
                self.toggle.toggle(source="user"), loop
            )
            state = future.result(timeout=5)
            self.console.print(
                f"[yellow]🔁 HITL toggle → "
                f"{'ENABLED' if state else 'DISABLED'}[/yellow]"
            )
        elif command == "timeout":
            if argument.isdigit() and self._current_case is not None:
                self._current_case.timeout = int(argument)
                self.console.print(f"[yellow]⏱️  timeout → {argument}s[/yellow]")
            else:
                self.console.print("[red]timeout needs a number of seconds[/red]")
        elif command == "add":
            if argument:
                self._adhoc.append(
                    QuestionCase(
                        id=f"adhoc-{len(self._adhoc) + 1:02d}",
                        title="ad-hoc question",
                        message=argument,
                        expected_type="text",
                        default_answer="",
                        validator=lambda a: (bool(a.strip()), "ad-hoc answer"),
                    )
                )
                self.console.print("[green]➕ ad-hoc question queued[/green]")
            else:
                self.console.print("[red]add needs a question[/red]")

        raise _CommandHandled()

    @contextlib.contextmanager
    def _interceptor(self):
        """Intercept the commands typed at a prompt.

        ``ConsoleInputModule`` reads with ``input()`` and with
        ``read_masked()`` (the masked reader that replaces ``getpass``);
        patching both makes the commands work in every prompt type —
        including the masked password prompt.
        """
        import components.console_input_module as console_input_module

        original_input = builtins.input
        original_read_masked = console_input_module.read_masked
        loop = asyncio.get_event_loop()

        def patched_input(prompt: str = "") -> str:
            raw = original_input(prompt)
            if self._is_command(raw):
                self._run_command(raw, loop)
            return raw

        def patched_read_masked(prompt: str = "", deadline=None) -> str:
            raw = original_read_masked(prompt, deadline)
            if self._is_command(raw):
                self._run_command(raw, loop)
            return raw

        builtins.input = patched_input
        console_input_module.read_masked = patched_read_masked
        try:
            yield
        finally:
            builtins.input = original_input
            console_input_module.read_masked = original_read_masked

    # -- collecting --------------------------------------------------------

    async def _collect(
        self, case: QuestionCase, input_type: str, options: List[str]
    ) -> Tuple[str, bool]:
        """Collect the answer the way ``EventConsumer._collect_answer`` does."""
        timeout = case.timeout

        if input_type == "yesno":
            default_yes = case.default_answer.strip().lower() in (
                "yes", "y", "true", "1",
            )
            response, was_timeout = await self.input_module.prompt_with_status(
                message="[Y/n]" if default_yes else "[y/N]",
                default="",
                timeout=timeout,
            )
            if was_timeout or not response.strip():
                return case.default_answer, True
            return response.strip().lower(), False

        if input_type == "menu" and options:
            selected, was_timeout = await self.input_module.menu_with_status(
                message="Select option [1]: ",
                options=options,
                timeout=timeout,
            )
            if was_timeout:
                return options[0], True
            return selected, False

        if input_type == "password":
            secret = await self.input_module.password(
                message="Enter password: ", timeout=timeout
            )
            return secret, not secret

        response, was_timeout = await self.input_module.prompt_with_status(
            message="Your response: ",
            default=case.default_answer,
            timeout=timeout,
        )
        if was_timeout:
            response = case.default_answer
        return response, was_timeout

    # -- one case ----------------------------------------------------------

    async def run_case(self, case: QuestionCase) -> Result:
        """Run one case of the bank."""
        result = Result(case)
        self._current_case = case
        self._current_id = case.id

        split = split_question(case.message)
        if split is None:
            result.detected_type = "none"
            result.not_a_question = True
            result.reason = "the message was not recognised as a question"
            self.console.print(
                "[red]⚠️  not a question — the detection rules found nothing[/red]"
            )
            return result

        options = list(split.options) if split.options else list(case.options)
        detected = detect_input_type(split.question, options)
        result.detected_type = detected
        result.classification_ok = detected == case.expected_type

        self._render_question(split.question, split.context, options)

        if not result.classification_ok:
            self.console.print(
                f"[red]⚠️  detected type '{detected}', expected "
                f"'{case.expected_type}'[/red]"
            )

        # The runtime toggle: when HITL is off, the agent does not ask — it
        # takes the default answer and moves on.
        if not self.toggle.is_enabled:
            self.console.print(
                "[yellow]🔴 HITL disabled — using the default answer[/yellow]"
            )
            result.answer = case.default_answer
            result.was_timeout = True
            result.answer_ok, result.reason = case.validate(result.answer)
            self._record(case, result)
            return result

        while True:
            try:
                with self._interceptor():
                    answer, was_timeout = await self._collect(
                        case, detected, options
                    )
                break
            except _CommandHandled:
                # A command was handled — ask again.
                continue
            except _Skip:
                result.skipped = True
                return result
            except _Stop:
                raise
            except (EOFError, KeyboardInterrupt):
                raise _Stop()

        result.answer = answer
        result.was_timeout = was_timeout
        if was_timeout:
            self.console.print(
                "[yellow]⏱️  timeout — the default answer was used[/yellow]"
            )
        result.answer_ok, result.reason = case.validate(answer)
        self._record(case, result)
        return result

    def _record(self, case: QuestionCase, result: Result) -> None:
        """Record the answer in the HITL history."""
        self.handler.record_answer(
            question_id=case.id,
            answer=result.answer,
            was_timeout=result.was_timeout,
            question=case.message,
            timeout=case.timeout,
            default_answer=case.default_answer,
        )

    # -- the run -----------------------------------------------------------

    async def run(self, cases: List[QuestionCase]) -> int:
        """Run the given cases and print the report."""
        for index, case in enumerate(cases, 1):
            self.console.rule(
                f"[blue]{index}/{len(cases)} — {case.id}: {case.title}[/blue]"
            )
            try:
                result = await self.run_case(case)
            except _Stop:
                self.console.print("[yellow]■ stopped[/yellow]")
                break
            self.results.append(result)
            if not result.skipped:
                self.console.print(
                    f"  type=[bold]{result.detected_type}[/bold] "
                    f"expected=[bold]{case.expected_type}[/bold] "
                    f"answer=[bold]{self._mask(result)}[/bold] "
                    f"→ {result.status()} ({result.reason})"
                )
                if result.known_defect:
                    self.console.print(
                        f"  [yellow]🐞 regression: {case.regression}[/yellow]"
                    )

        return self._report()

    @staticmethod
    def _mask(result: Result) -> str:
        """Hide the answer of a password question."""
        if result.detected_type == "password":
            return "•" * 8
        return result.answer

    def _report(self) -> int:
        """Print the summary of the run and return the exit code."""
        self.console.rule("[green]report[/green]")
        for result in self.results:
            self.console.print(
                f"  {result.status()}  {result.case.id:<28} "
                f"detected={result.detected_type:<8} "
                f"expected={result.case.expected_type}"
            )

        passed = sum(1 for r in self.results if r.passed)
        known = sum(1 for r in self.results if r.known_defect)
        failed = sum(
            1 for r in self.results
            if not r.passed and not r.skipped and not r.known_defect
        )
        skipped = sum(1 for r in self.results if r.skipped)
        self.console.print(
            f"\n[bold]passed={passed} known_defects={known} "
            f"failed={failed} skipped={skipped}[/bold]"
        )
        self.console.print(
            f"[dim]questions in history: {self.handler.question_count}, "
            f"timeouts: {self.handler.timeout_count}[/dim]"
        )
        return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Parse the arguments and run the harness."""
    args = sys.argv[1:]

    if "--list" in args:
        for case in QUESTION_BANK:
            console.print(
                f"[bold]{case.id}[/bold] — {case.title} "
                f"[dim](expects {case.expected_type})[/dim]"
            )
        return 0

    ids = [a for a in args if not a.startswith("-")]
    if ids:
        cases = [case_by_id(i) for i in ids]
        missing = [i for i, c in zip(ids, cases) if c is None]
        if missing:
            console.print(f"[red]unknown case id(s): {', '.join(missing)}[/red]")
            return 2
        cases = [c for c in cases if c is not None]
    else:
        cases = list(QUESTION_BANK)

    console.print("[bold cyan]=== Interactive HITL test ===[/bold cyan]")
    console.print(
        "[dim]type 'help' at any prompt for the available commands[/dim]\n"
    )

    harness = InteractiveHITLTest()
    try:
        return asyncio.run(harness.run(cases))
    except KeyboardInterrupt:
        console.print("\n[yellow]■ interrupted[/yellow]")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
