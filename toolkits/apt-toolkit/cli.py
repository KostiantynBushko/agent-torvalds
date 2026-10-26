"""
APT Toolkit - the command-line interface.

The toolkit used to carry its command-line interface as a
``if __name__ == "__main__":`` block at the bottom of the single module
``agent_apt_toolkit.py``.  It lives here now, next to the operations it
drives, so the library half stays a library.

The interface is unchanged: the same two options, the same output, the
same exit codes.  The only difference is where it is invoked from::

    python -m toolkits.apt_toolkit --show-method
    python -m toolkits.apt_toolkit --prompt-method whiptail

The ``--show-method`` option prints the default password prompt method and
exits; ``--prompt-method`` changes it for the session.  With no arguments
at all, the help is printed.

Category: System / Package Management
Retriever Keywords: apt, package, install, debian, ubuntu, sudo, prompt, method, cli
"""

from __future__ import annotations

import argparse
import sys

# The operations are imported with a *relative* import.  That is the only
# form that resolves both inside this repository (where the directory name
# carries a hyphen) and in a standalone installation of the package.
from .operations import get_default_prompt_method, set_default_prompt_method

__all__ = ["main", "build_parser"]


# ---------------------------------------------------------------------------
# 6. Command-Line Interface
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of the toolkit's command-line interface.

    Returns:
        argparse.ArgumentParser: The parser, with the two options of the
        original command-line interface.
    """
    parser = argparse.ArgumentParser(
        description="APT Package Toolkit - Manage APT packages and sudo password handling",
        epilog="Example: python -m toolkits.apt_toolkit --prompt-method whiptail",
    )
    parser.add_argument(
        "--prompt-method",
        type=str,
        choices=["console", "whiptail", "env_var", "parameter"],
        default=None,
        help="Set the default password prompt method (console, whiptail, env_var, parameter)",
    )
    parser.add_argument(
        "--show-method",
        action="store_true",
        help="Show the current default prompt method and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface.

    Args:
        argv (list[str], optional): The arguments to parse.  ``None`` -
            the default - reads them from the command line.

    Returns:
        int: The exit code.  ``1`` when the requested prompt method is
        invalid, ``0`` in every other case.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Apply --prompt-method first if provided
    if args.prompt_method:
        result = set_default_prompt_method(args.prompt_method)
        if not result["success"]:
            print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
            return 1

    # Then show the current method if requested
    if args.show_method:
        print(f"Current default prompt method: {get_default_prompt_method()}")
        return 0

    # If --prompt-method was set without --show-method, confirm the change
    if args.prompt_method:
        print(f"Default prompt method set to: {result['method']}")
        return 0

    # If no arguments provided, show help
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
