"""
Session-wide test preparation.

The database toolkit reads its configuration - ``db_toolkit_config.yaml`` -
from the **working directory** when it is imported.  That is the behaviour
it had as a loose module at the project root, and the move preserved it:
the configuration is loaded once, at import time, and the operations use
the loaded values.

The consequence for the test suite: the file has to be in the working
directory *before* anything imports the toolkit.  The alias shim
(``toolkits/__init__.py``) imports every toolkit eagerly, so that is
before the first test module is even collected - which is why this file
lives at the repository root and not inside the toolkit's own tests.

The configuration file is committed at the repository root, and every run
of the suite happens there, so this is normally a no-op.  A run from
another directory would otherwise fail to collect the toolkit's tests, so
the file is put in place here and removed again when the session ends.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The name of the configuration file the toolkit reads at import time.
CONFIG_NAME = "db_toolkit_config.yaml"

#: The smallest configuration the toolkit can be imported with.  The
#: operations are driven through stubbed drivers, so the values never
#: reach a database server; the file only has to exist.
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
    """Put the configuration file in place, and report whether it was new.

    Returns:
        True when the file was created here and has to be removed again
        when the session ends; False when it was already there.
    """
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
