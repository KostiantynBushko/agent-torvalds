"""
Whiptail Password Module - Terminal dialog-based password prompting.

This module provides a whiptail-based password prompter that can be used
as an alternative to stdin/console password input. It wraps the 'whiptail'
Python package to display interactive terminal dialogs for password entry.

Category: System / Terminal UI
Retriever Keywords: whiptail, password, dialog, terminal, ui, prompt, sudo

Prerequisites:
    - /usr/bin/whiptail installed (newt package on Debian/Ubuntu)
    - whiptail Python package installed (pip install whiptail)

Usage:
    from whiptail_password import WhiptailPasswordPrompter

    prompter = WhiptailPasswordPrompter()
    password = prompter.prompt_password(title="My App", max_attempts=3)
"""

import subprocess
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WhiptailPasswordPrompter:
    """
    Password prompter using whiptail terminal dialogs.

    This class wraps the whiptail Python package to provide a terminal-based
    password entry dialog. It can be used as a drop-in replacement for console
    password input in environments where whiptail is available and preferred.

    Attributes:
        title (str): Dialog title
        backtitle (str): Dialog backtitle
        height (int): Dialog height
        width (int): Dialog width
    """

    def __init__(
        self,
        title: str = "Sudo Password",
        backtitle: str = "Enter your sudo password",
        height: int = 10,
        width: int = 50,
    ):
        """
        Initialize the whiptail password prompter.

        Args:
            title (str): Dialog title (default: "Sudo Password")
            backtitle (str): Dialog backtitle (default: "Enter your sudo password")
            height (int): Dialog height (default: 10)
            width (int): Dialog width (default: 50)
        """
        self.title = title
        self.backtitle = backtitle
        self.height = height
        self.width = width

    def prompt_password(
        self,
        message: str = "Please enter your sudo password:",
        max_attempts: int = 3,
        test_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Prompt for a password using whiptail dialog.

        Args:
            message (str): Message to display in the dialog
            max_attempts (int): Maximum number of password attempts
            test_callback (callable, optional): Function to validate the password.
                Should accept a string and return True/False. If None, no validation
                is performed and the first non-empty input is accepted.

        Returns:
            Dictionary with:
                - 'success': bool
                - 'password': str or None
                - 'attempts': int
                - 'method': 'whiptail'
                - 'error': str (if failed)

        Example:
            >>> prompter = WhiptailPasswordPrompter()
            >>> result = prompter.prompt_password(test_callback=lambda p: p == "correct")
            {'success': True, 'password': 'correct', 'attempts': 1, 'method': 'whiptail'}
        """
        logger.info(f"WhiptailPasswordPrompter.prompt_password called with max_attempts: {max_attempts}")

        result: Dict[str, Any] = {
            "success": False,
            "password": None,
            "attempts": 0,
            "method": "whiptail",
        }

        try:
            from whiptail import Whiptail

            wt = Whiptail(
                title=self.title,
                backtitle=self.backtitle,
                height=self.height,
                width=self.width,
                auto_exit=False,
            )

            for attempt in range(1, max_attempts + 1):
                result["attempts"] = attempt
                logger.info(f"Whiptail password attempt {attempt}/{max_attempts}")

                try:
                    # Use whiptail passwordbox for masked input
                    password = wt.prompt(
                        msg=f"{message} (attempt {attempt}/{max_attempts})",
                        default="",
                        password=True,
                    )

                    if not password:
                        # Show info dialog for empty password
                        wt.alert("Empty password. Please try again.")
                        continue

                    # Validate if callback provided
                    if test_callback:
                        if test_callback(password):
                            result.update({
                                "success": True,
                                "password": password,
                            })
                            return result
                        else:
                            wt.alert("Invalid password. Please try again.")
                    else:
                        # No validation, accept first non-empty input
                        result.update({
                            "success": True,
                            "password": password,
                        })
                        return result

                except Exception as e:
                    logger.error(f"Error during whiptail prompt: {e}")
                    result["error"] = f"Whiptail prompt failed: {e}"
                    return result

            # Max attempts reached
            result["error"] = f"Failed after {max_attempts} attempts"
            return result

        except ImportError:
            logger.error("whiptail Python package not installed")
            result["error"] = "whiptail Python package not available"
            return result
        except Exception as e:
            logger.error(f"Whiptail password prompt failed: {e}")
            result["error"] = f"Whiptail failed: {e}"
            return result

    def show_message(
        self,
        message: str,
        title: Optional[str] = None,
    ) -> bool:
        """
        Display a message dialog using whiptail.

        Args:
            message (str): Message to display
            title (str, optional): Override title for this dialog

        Returns:
            bool: True if dialog was shown successfully
        """
        try:
            from whiptail import Whiptail

            wt = Whiptail(
                title=title or self.title,
                backtitle=self.backtitle,
                height=self.height,
                width=self.width,
                auto_exit=False,
            )
            wt.alert(message)
            return True
        except Exception as e:
            logger.error(f"Failed to show message: {e}")
            return False

    def confirm(
        self,
        message: str,
        title: Optional[str] = None,
        default_yes: bool = True,
    ) -> bool:
        """
        Ask for yes/no confirmation using whiptail.

        Args:
            message (str): Question to ask
            title (str, optional): Override title for this dialog
            default_yes (bool): Whether Yes is the default

        Returns:
            bool: True if user confirmed, False otherwise
        """
        try:
            from whiptail import Whiptail

            wt = Whiptail(
                title=title or self.title,
                backtitle=self.backtitle,
                height=self.height,
                width=self.width,
                auto_exit=False,
            )
            return wt.confirm(message)
        except Exception as e:
            logger.error(f"Failed to show confirmation: {e}")
            return False

    @staticmethod
    def is_available() -> Dict[str, Any]:
        """
        Check if whiptail is available on the system.

        Returns:
            Dictionary with:
                - 'available': bool
                - 'binary_path': str or None
                - 'python_package': bool
                - 'details': str
        """
        result: Dict[str, Any] = {
            "available": False,
            "binary_path": None,
            "python_package": False,
            "details": "",
        }

        # Check for whiptail binary
        try:
            proc = subprocess.run(
                ["which", "whiptail"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                result["binary_path"] = proc.stdout.strip()
                result["details"] += "Binary found. "
            else:
                result["details"] += "Binary not found. "
        except Exception as e:
            result["details"] += f"Binary check failed: {e}. "

        # Check for Python package
        try:
            import whiptail
            result["python_package"] = True
            result["details"] += "Python package available. "
        except ImportError:
            result["details"] += "Python package not available. "

        result["available"] = bool(result["binary_path"] and result["python_package"])
        return result


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_default_prompter: Optional[WhiptailPasswordPrompter] = None


def get_prompter(
    title: str = "Sudo Password",
    backtitle: str = "Enter your sudo password",
    height: int = 10,
    width: int = 50,
) -> WhiptailPasswordPrompter:
    """
    Get or create the default whiptail password prompter.

    This is a convenience function that returns a singleton prompter instance.

    Args:
        title (str): Dialog title
        backtitle (str): Dialog backtitle
        height (int): Dialog height
        width (int): Dialog width

    Returns:
        WhiptailPasswordPrompter instance
    """
    global _default_prompter
    if _default_prompter is None:
        _default_prompter = WhiptailPasswordPrompter(
            title=title,
            backtitle=backtitle,
            height=height,
            width=width,
        )
    return _default_prompter


def prompt_sudo_password_whiptail(
    max_attempts: int = 3,
    test_callback: Optional[callable] = None,
    title: str = "Sudo Password",
    backtitle: str = "Enter your sudo password",
) -> Dict[str, Any]:
    """
    Convenience function to prompt for sudo password using whiptail.

    Args:
        max_attempts (int): Maximum password attempts
        test_callback (callable, optional): Password validation function
        title (str): Dialog title
        backtitle (str): Dialog backtitle

    Returns:
        Dictionary with password result

    Example:
        >>> from whiptail_password import prompt_sudo_password_whiptail
        >>> result = prompt_sudo_password_whiptail(test_callback=lambda p: len(p) > 0)
    """
    prompter = WhiptailPasswordPrompter(
        title=title,
        backtitle=backtitle,
    )
    return prompter.prompt_password(max_attempts=max_attempts, test_callback=test_callback)


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=" * 50)
    print("  Whiptail Password Module Test")
    print("=" * 50)
    print()

    # Check availability
    print("[1] Checking whiptail availability...")
    avail = WhiptailPasswordPrompter.is_available()
    print(f"  Available: {avail['available']}")
    print(f"  Binary: {avail['binary_path']}")
    print(f"  Python package: {avail['python_package']}")
    print(f"  Details: {avail['details']}")
    print()

    if not avail["available"]:
        print("Whiptail not fully available. Exiting.")
        sys.exit(1)

    # Test password prompt
    print("[2] Testing password prompt...")
    print("  (Enter any password to continue)")
    print()

    prompter = WhiptailPasswordPrompter(
        title="Test Password",
        backtitle="Whiptail Password Module",
    )

    def dummy_test(password: str) -> bool:
        """Accept any non-empty password for testing."""
        return len(password) > 0

    result = prompter.prompt_password(
        message="Enter test password:",
        max_attempts=3,
        test_callback=dummy_test,
    )

    print()
    print(f"  Result: {result}")
    print()

    # Test message dialog
    print("[3] Testing message dialog...")
    prompter.show_message("This is a test message from whiptail!")
    print("  Message dialog shown.")
    print()

    # Test confirmation
    print("[4] Testing confirmation dialog...")
    confirmed = prompter.confirm("Continue with the test?", default_yes=True)
    print(f"  Confirmed: {confirmed}")
    print()

    print("=" * 50)
    print("  Test Complete!")
    print("=" * 50)
