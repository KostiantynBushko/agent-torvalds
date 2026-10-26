"""
Test-time preparation for the database toolkit's own suite.

The library half reads ``db_toolkit_config.yaml`` from the **working
directory** when it is imported, and the root ``conftest.py`` puts that
file in place for a session started at the repository root.  This file
covers the other case: a session started **inside** the toolkit
directory, where the root conftest is not loaded at all.

Both files do the same thing, and both are idempotent: the first one to
run creates the file, the other one finds it and leaves it alone.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The name of the configuration file the toolkit reads at import time.
CONFIG_NAME = "db_toolkit_config.yaml"

#: The smallest configuration the toolkit can be imported with.
MINIMAL_CONFIG = """\
postgres:
  host: 127.0.0.1
  port: 5432
  user: postgres
  password: postgres

mysql:
  host: 127.0.0.1
  port: 3306
  user: root
  password: root
"""


def _ensure_config_in_working_directory() -> bool:
    """Put the configuration file in place, and report whether it was new."""
    path = Path(os.getcwd()) / CONFIG_NAME
    if path.is_file():
        return False

    path.write_text(MINIMAL_CONFIG, encoding="utf-8")
    return True


#: Whether this session created the configuration file.
CREATED_CONFIG = _ensure_config_in_working_directory()


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    """Remove the configuration file again, if this session created it."""
    if CREATED_CONFIG:
        path = Path(os.getcwd()) / CONFIG_NAME
        try:
            path.unlink()
        except OSError:  # pragma: no cover - the file is already gone
            pass
