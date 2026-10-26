"""
Entry point for ``python -m toolkits.apt_toolkit``.

Having a module-level entry point means the toolkit can be used as a
standalone app without installing anything::

    python -m toolkits.apt_toolkit --show-method
    python -m toolkits.apt_toolkit --prompt-method whiptail
"""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
