"""
Console Input Module for HITL (Human-in-the-Loop)

Provides async terminal input methods with timeout support.  All methods
return sensible defaults when the user does not respond within the
specified timeout period.

Usage:
    from components.console_input_module import ConsoleInputModule

    console_input = ConsoleInputModule()

    # Text prompt
    name = await console_input.prompt("What is your name?", default="Anonymous", timeout=30)

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
        timeout: int = 30,
    ) -> str:
        """Prompt user for text input via console with timeout.

        Args:
            message: Question / prompt to display.
            default: Value returned when the user times out or submits
                     an empty response.
            timeout: Seconds to wait for input.

        Returns:
            User's response or *default* on timeout / empty input.
        """
        loop = asyncio.get_event_loop()

        def _ask() -> str:
            try:
                result = input(message)
                return result if isinstance(result, str) else default
            except (EOFError, KeyboardInterrupt):
                return default

        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=timeout,
            )
            if isinstance(response, str):
                return response if response.strip() else default
            return default
        except asyncio.TimeoutError:
            return default

    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = 30,
    ) -> bool:
        """Ask for yes / no confirmation via console.

        Args:
            message: Question to display.
            default_yes: Default when the user times out or submits
                         an empty response.
            timeout: Seconds to wait.

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
        timeout: int = 30,
    ) -> str:
        """Display a numbered menu and return the selected option.

        Args:
            message: Menu title / question.
            options: List of choice strings.
            timeout: Seconds to wait.

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
        timeout: int = 60,
    ) -> str:
        """Prompt for password input (hidden) with timeout.

        Args:
            message: Prompt text shown to the user.
            timeout: Seconds to wait.

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
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=timeout,
            )
            return response if isinstance(response, str) else ""
        except asyncio.TimeoutError:
            return ""
