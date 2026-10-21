"""
Entry point for ``python -m shodan_toolkit``.

Having a module-level entry point means the toolkit can be used as a
standalone app without installing the console script::

    python -m shodan_toolkit doctor
    python -m shodan_toolkit search "nginx" --limit 5
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
