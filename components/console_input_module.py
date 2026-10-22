"""
Console Input Module for HITL (Human-in-the-Loop)

Provides async terminal input methods with timeout support.  All methods
return sensible defaults when the user does not respond within the
specified timeout period.

The default timeout is ``-1``, which means *no timeout*: the prompt waits
for the human indefinitely.  See ``components.hitl_timeout.py``.

Usage:
    from components.console_input_module import ConsoleInputModule

    console_input = ConsoleInputModule()

    # Text prompt
    name = await console_input.prompt("What is your name?", default="Anonymous", timeout=30)

    # Wait forever for the answer
    name = await console_input.prompt("What is your name?", default="Anonymous")

    # Yes/No confirmation
    ok = await console_input.confirm("Proceed with installation?", default_yes=True, timeout=30)

    # Menu selection
    choice = await console_input.menu("Choose a tool:", ["vim", "nano", "emacs"], timeout=30)

    # Password
    pwd = await console_input.password(timeout=60)
"""

from __future__ import annotations

import asyncio
import getpass
from typing import List, Optional

from rich.console import Console

from components.hitl_timeout import NO_TIMEOUT, normalize_timeout


class ConsoleInputModule:
    """Console-based input module for HITL interactions.

    Provides async input methods with timeout support.  All methods return
    default values on timeout, EOF, or keyboard interrupt.

    Attributes:
        console: Rich Console instance used for coloured output.
    """

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()

    # ------------------------------------------------------------------
    # Public input methods
    # ------------------------------------------------------------------

    @staticmethod
    async def prompt(
        message: str,
        default: str = "",
        timeout: int = NO_TIMEOUT,
    ) -> str:
        """Prompt user for text input via console with timeout.

        Args:
            message: Question / prompt to display.
            default: Value returned when the user times out or submits
                     an empty response.
            timeout: Seconds to wait for input.  ``-1`` (the default) means
                     *no timeout*: wait for the human indefinitely.

        Returns:
            User's response or *default* on timeout / empty input.
        """
        response, _ = await ConsoleInputModule.prompt_with_status(
            message=message, default=default, timeout=timeout
        )
        return response

    @staticmethod
    async def prompt_with_status(
        message: str,
        default: str = "",
        timeout: int = NO_TIMEOUT,
    ) -> tuple[str, bool]:
        """Prompt the user and report whether the prompt timed out.

        ``prompt()`` cannot distinguish "the user typed the default answer"
        from "the user did not answer at all" — both return *default*.  The
        HITL consumer needs that distinction to log timeouts correctly.

        Args:
            message: Question / prompt to display.
            default: Value returned when the user times out or submits
                     an empty response.
            timeout: Seconds to wait for input.  ``-1`` (the default) means
                     *no timeout*: wait for the human indefinitely.

        Returns:
            ``(response, was_timeout)`` tuple.
        """
        loop = asyncio.get_event_loop()

        def _ask() -> str:
            try:
                result = input(message)
                return result if isinstance(result, str) else default
            except (EOFError, KeyboardInterrupt):
                return default

        try:
            # ``None`` means "wait forever" for asyncio — that is what the
            # no-timeout convention (-1) translates to.
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=normalize_timeout(timeout),
            )
            if isinstance(response, str):
                if response.strip():
                    return response, False
                # An empty answer is treated as "no answer given".
                return default, True
            return default, True
        except asyncio.TimeoutError:
            return default, True

    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = NO_TIMEOUT,
    ) -> bool:
        """Ask for yes / no confirmation via console.

        Args:
            message: Question to display.
            default_yes: Default when the user times out or submits
                         an empty response.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            ``True`` for yes, ``False`` otherwise.
        """
        suffix = " [Y/n]" if default_yes else " [y/N]"
        full_message = f"{message}{suffix}"
        response = await self.__class__.prompt(full_message, timeout=timeout)

        if not response:
            return default_yes

        return response.lower() in ("y", "yes")

    async def menu(
        self,
        message: str,
        options: List[str],
        timeout: int = NO_TIMEOUT,
    ) -> str:
        """Display a numbered menu and return the selected option.

        Args:
            message: Menu title / question.
            options: List of choice strings.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            The selected option string, or the first option on timeout
            / invalid input.
        """
        self.console.print(f"\n{message}")
        for i, opt in enumerate(options, 1):
            self.console.print(f"  [bold]{i}[/bold]. {opt}")

        response = await self.__class__.prompt(
            "Select option [1]: ", default="1", timeout=timeout
        )

        try:
            idx = int(response) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass

        return options[0]

    async def password(
        self,
        message: str = "Enter password: ",
        timeout: int = NO_TIMEOUT,
    ) -> str:
        """Prompt for password input (hidden) with timeout.

        Args:
            message: Prompt text shown to the user.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            Entered password or ``""`` on timeout.
        """
        loop = asyncio.get_event_loop()

        def _ask() -> str:
            try:
                result = getpass.getpass(message)
                return result if isinstance(result, str) else ""
            except (EOFError, KeyboardInterrupt):
                return ""

        try:
            # ``None`` means "wait forever" for asyncio.
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=normalize_timeout(timeout),
            )
            return response if isinstance(response, str) else ""
        except asyncio.TimeoutError:
            return ""
