"""The deployment folder's contract, under pytest.

The harness itself is ``verify_deploy_layout.py``, in the same
directory.  It is loaded by path rather than by import, because the
``deploy/`` folder is a folder of shell scripts and not a Python
package - there is nothing to import it *as*.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

#: The repository root, two levels up from this file.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: The harness.
HARNESS_PATH = Path(__file__).resolve().with_name("verify_deploy_layout.py")


def _load_harness():
    """Load the harness module from its path."""
    spec = importlib.util.spec_from_file_location("verify_deploy_layout", HARNESS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the harness from {HARNESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HARNESS = _load_harness()


@pytest.mark.parametrize(
    ("name", "description", "check"),
    HARNESS.CHECKS,
    ids=[name for name, _description, _check in HARNESS.CHECKS],
)
def test_the_invariant_holds(name: str, description: str, check) -> None:
    """Every invariant of the deploy/ folder holds."""
    result = HARNESS.Result(name)
    check(result, REPO_ROOT)
    assert result.ok, f"{name} ({description}):\n" + "\n".join(result.failures)
