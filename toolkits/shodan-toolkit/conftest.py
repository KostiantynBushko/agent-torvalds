"""Make the in-repository copy of the package importable during the tests.

The toolkit keeps its upstream ``src/`` layout, so the importable package
lives in ``src/shodan_toolkit/`` rather than at the top level.  When the
toolkit is consumed as an installed distribution that does not matter, but
inside this repository the tests must exercise *this* copy - the same code
the agent adapter loads - without requiring ``pip install -e .`` first.

pytest picks the nearest configuration file when it is pointed at a path
inside this directory, and ``pyproject.toml`` is the one it finds.  Adding
the source directory to ``sys.path`` here keeps the suite runnable no
matter which configuration file is in play::

    pytest toolkits/shodan-toolkit/tests      # from the repository root
    pytest toolkits/shodan-toolkit            # from inside the toolkit

This file is an addition to the upstream project; the upstream files
themselves are untouched, so ``git subtree pull`` keeps working.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The directory that holds the importable ``shodan_toolkit`` package.
SRC_DIR = Path(__file__).resolve().parent / "src"

if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
