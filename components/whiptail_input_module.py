"""
Whiptail Input Module for HITL (Human-in-the-Loop)

Extends the existing WhiptailPasswordPrompter for general HITL input.
Provides dialog-based interaction with timeout support.  Falls back to
default values when whiptail is unavailable or an error occurs.

Usage:
    from components.whiptail_input_module import WhiptailInputModule

    wt_input = WhiptailInputModule()

    # Text prompt
    name = await wt_input.prompt("What is your name?", default="Anonymous", timeout=30)

    # Yes/No confirmation
    ok = await wt_input.confirm("Proceed?", default_yes=True, timeout=30)

    # Menu selection
    choice = await wt_input.menu("Choose:", ["vim", "nano", "emacs"], timeout=30)

See: investigate/whiptail/INVESTIGATION_REPORT.md for details
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class WhiptailInputModule:
    """Whiptail-based input module for HITL interactions.

    Extends the existing ``WhiptailPasswordPrompter`` patterns for general
    input.  Provides dialog-based interaction with timeout support.

    Attributes:
        title: Default dialog title.
        backtitle: Default dialog backtitle.
        height: Dialog height in rows.
        width: Dialog width in columns.
    """

    def __init__(
        self,
        title: str = "Agent Question",
        backtitle: str = "AI Agent requires your input",
        height: int = 10,
        width: int = 60,
    ) -> None:
        self.title = title
        self.backtitle = backtitle
        self.height = height
        self.width = width

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        """Check if whiptail is available on the system.

        Returns:
            ``True`` when both the whiptail binary and the Python package
            are present.
        """
        from components.whiptail_password import WhiptailPasswordPrompter

        info = WhiptailPasswordPrompter.is_available()
        return info.get("available", False)

    # ------------------------------------------------------------------
    # Public input methods
    # ------------------------------------------------------------------

    async def prompt(
        self,
        message: str,
        default: str = "",
        timeout: int = 30,
        title: Optional[str] = None,
    ) -> str:
        """Prompt user for input via whiptail dialog with timeout.

        Args:
            message: Question to display.
            default: Value returned on timeout or error.
            timeout: Seconds to wait for a response.
            title: Optional dialog title override.

        Returns:
            User's response or *default* on timeout / error / unavailable.
        """
        if not self.is_available():
            logger.debug("Whiptail not available, returning default")
            return default

        try:
            from whiptail import Whiptail

            wt = Whiptail(
                title=title or self.title,
                backtitle=self.backtitle,
                height=self.height,
                width=self.width,
                auto_exit=False,
            )

            def _ask() -> str:
                return wt.prompt(msg=message, default=default, password=False)

            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=timeout,
            )
            return response if response.strip() else default

        except asyncio.TimeoutError:
            logger.debug("Whiptail prompt timed out")
            return default
        except Exception as e:
            logger.error(f"Whiptail prompt error: {e}")
            return default

    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = 30,
        title: Optional[str] = None,
    ) -> bool:
        """Ask for yes / no confirmation via whiptail dialog.

        Args:
            message: Question to display.
            default_yes: Default value on timeout / error.
            timeout: Seconds to wait.
            title: Optional dialog title override.

        Returns:
            ``True`` if confirmed, ``False`` otherwise.
        """
        if not self.is_available():
            logger.debug("Whiptail not available, returning default")
            return default_yes

        try:
            from whiptail import Whiptail

            wt = Whiptail(
                title=title or self.title,
                backtitle=self.backtitle,
                height=self.height,
                width=self.width,
                auto_exit=False,
            )

            def _ask() -> bool:
                extra = ["--defaultno"] if not default_yes else []
                result = wt.run(
                    control="yesno",
                    msg=message,
                    extra=extra,
                    exit_on=(1, 255),
                )
                return result.returncode == 0

            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            logger.debug("Whiptail confirm timed out")
            return default_yes
        except Exception as e:
            logger.error(f"Whiptail confirm error: {e}")
            return default_yes

    async def menu(
        self,
        message: str,
        options: List[str],
        timeout: int = 30,
        title: Optional[str] = None,
    ) -> str:
        """Display a numbered menu via whiptail dialog.

        Args:
            message: Menu title / question.
            options: List of choice descriptions.
            timeout: Seconds to wait.
            title: Optional dialog title override.

        Returns:
            The selected option string, or the first option on timeout
            / error / unavailable.
        """
        if not self.is_available():
            logger.debug("Whiptail not available, returning first option")
            return options[0] if options else ""

        try:
            from whiptail import Whiptail

            wt = Whiptail(
                title=title or self.title,
                backtitle=self.backtitle,
                height=15,
                width=self.width,
                auto_exit=False,
            )

            # Format items as (tag, description) tuples
            items = [(str(i), opt) for i, opt in enumerate(options, 1)]

            def _ask() -> str:
                return wt.menu(msg=message, items=items)

            loop = asyncio.get_event_loop()
            tag = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=timeout,
            )

            try:
                idx = int(tag) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            except ValueError:
                pass

            return options[0]

        except asyncio.TimeoutError:
            logger.debug("Whiptail menu timed out")
            return options[0] if options else ""
        except Exception as e:
            logger.error(f"Whiptail menu error: {e}")
            return options[0] if options else ""
