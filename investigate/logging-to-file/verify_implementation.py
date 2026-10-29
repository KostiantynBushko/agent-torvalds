"""
Run the file-logging invariants against the **shipped implementation**.

The harness in ``verify_logging_to_file.py`` is the evidence the
investigation rests on, and it checks the **prototype**.  The code that
actually runs is ``components/file_logging.py``, and a set of invariants
that has only ever been checked against a prototype proves nothing about
the implementation.

This script runs the very same thirteen checks — the same functions, the
same assertions — against ``components/file_logging.py``.

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/logging-to-file/verify_implementation.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The harness reads this before it picks the module under test.
os.environ["TORVALDS_FILE_LOGGING_TARGET"] = "implementation"

import verify_logging_to_file  # noqa: E402


def main() -> int:
    return verify_logging_to_file.main()


if __name__ == "__main__":
    sys.exit(main())
