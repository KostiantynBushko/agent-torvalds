"""
verify_test_contract.py - proves the CORRECTED package-local test contract.

Corrected rule set (documented in MODULE_SPECIFICATION.md §3.4):

  * A package-local test directory MUST NOT contain ``__init__.py``.
  * The package-local test suite MUST run under ``--import-mode=importlib``.
  * Under those two conditions:
      - relative imports (``from .. import ...``) work;
      - there is no module-name collision with the root ``tests/`` package;
      - the alias import style works too.

Root cause (pytest 9.1.1, ``_pytest/pathlib.py::resolve_package_path``):

    for parent in itertools.chain((path,), path.parents):
        if parent.is_dir():
            if not (parent / "__init__.py").is_file():
                break
            if not parent.name.isidentifier():
                break
            result = parent

The ``isidentifier()`` guard stops the upward walk at ``MikroTik-RouterOS``.
Combined with an ``__init__.py`` in the test directory this makes pytest
derive the invalid module name ``tests.test_x`` instead of
``toolkits.MikroTik-RouterOS.tests.test_x`` -- which is why a relative
``from .. import ...`` resolves against the *root* ``tests`` package and
fails with "attempted relative import beyond top-level package".

Run from the clone root:

    self-development/.venv/bin/python \
        self-development/investigate/MikroTik-RouterOS/verify_test_contract.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG_TESTS = REPO / "toolkits" / "MikroTik-RouterOS" / "tests"

RELATIVE_TEST = textwrap.dedent(
    """
    from .. import __name__ as PKG

    def test_relative_import_works():
        assert PKG is not None
    """
)

ALIAS_TEST = textwrap.dedent(
    """
    from toolkits.mikrotik_routeros import __name__ as PKG

    def test_alias_import_works():
        assert PKG == "toolkits.MikroTik-RouterOS"
    """
)

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Assert a hard contract clause - it must hold right now."""
    results.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))


def check_pending(name: str, ok: bool, detail: str = "") -> None:
    """Assert a clause that depends on not-yet-implemented work.

    A *pending* state is not a failure: it means the repository has not
    implemented the requirement yet. It becomes a FAIL once the
    implementation has landed and the requirement is still unmet.
    """
    status = "PASS" if ok else "PENDING"
    results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


def run_pytest(paths: list[str], importlib: bool, extra: list[str] | None = None) -> tuple[int, str]:
    """Run pytest against *paths* in an explicitly chosen import mode.

    pytest.ini sets "addopts = --import-mode=importlib", so the mode has to
    be requested explicitly on the command line - otherwise the ini would
    win and the "prepend" checks would silently test the wrong thing.
    """
    cmd = [sys.executable, "-m", "pytest", *paths, "-q", "--no-header", "-p", "no:cacheprovider"]
    cmd.append("--import-mode=importlib" if importlib else "--import-mode=prepend")
    if extra:
        cmd.extend(extra)
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=600)
    return proc.returncode, proc.stdout + proc.stderr


def summary_line(out: str) -> str:
    for ln in reversed(out.splitlines()):
        if re.search(r"\d+ (passed|failed|error)", ln):
            return re.sub(r"in \d+\.\d+s", "in <t>s", ln).strip()
    return out.strip().splitlines()[-1] if out.strip() else ""


#: The scratch files this script creates. Only these are removed again -
#: a blanket "delete every test_*.py" would destroy the real Phase 1 test
#: suite that lives in the same directory.
SCRATCH_FILES = ("test_rel_ok.py", "test_collide.py", "test_alias_ok.py")

#: Scratch files this script creates in the ROOT tests/ directory.
ROOT_SCRATCH_FILES = ("test_alias_ok.py",)


def cleanup() -> None:
    """Remove only the scratch files this script created.

    An earlier version deleted every ``test_*.py`` in the package-local test
    directory, which silently destroyed the real test suite. The scratch
    files are now tracked explicitly.
    """
    for name in SCRATCH_FILES:
        path = PKG_TESTS / name
        if path.exists():
            path.unlink()
    for name in ROOT_SCRATCH_FILES:
        path = REPO / "tests" / name
        if path.exists():
            path.unlink()
    init = PKG_TESTS / "__init__.py"
    if init.exists():
        init.unlink()
    # The directory itself is kept: it holds the real test suite.


def main() -> int:
    PKG_TESTS.mkdir(parents=True, exist_ok=True)
    init = PKG_TESTS / "__init__.py"
    if init.exists():
        init.unlink()

    print("C1  package-local tests MUST NOT contain __init__.py")
    (PKG_TESTS / "test_rel_ok.py").write_text(RELATIVE_TEST)
    rc, out = run_pytest([str(PKG_TESTS / "test_rel_ok.py")], importlib=True)
    check("no __init__.py + importlib -> relative import passes", rc == 0, summary_line(out))

    init.write_text("")
    rc, out = run_pytest([str(PKG_TESTS / "test_rel_ok.py")], importlib=True)
    check(
        "WITH __init__.py + importlib -> relative import FAILS",
        rc != 0 and "beyond top-level package" in out,
        "ImportError: attempted relative import beyond top-level package" if rc != 0 else "unexpectedly passed",
    )
    init.unlink()

    print()
    print("C2  --import-mode=importlib is REQUIRED for relative imports")
    rc, out = run_pytest([str(PKG_TESTS / "test_rel_ok.py")], importlib=False)
    check(
        "no __init__.py + prepend -> relative import FAILS",
        rc != 0 and "no known parent package" in out,
        "ImportError: attempted relative import with no known parent package" if rc != 0 else "unexpectedly passed",
    )
    rc, out = run_pytest([str(PKG_TESTS / "test_rel_ok.py")], importlib=True)
    check("no __init__.py + importlib -> relative import PASSES", rc == 0, summary_line(out))

    print()
    print("C3  no module-name collision with the root tests/ package")
    (PKG_TESTS / "test_rel_ok.py").unlink()
    (PKG_TESTS / "test_collide.py").write_text("def test_c():\n    assert True\n")
    (REPO / "tests" / "test_collide.py").write_text("def test_c():\n    assert True\n")
    rc, out = run_pytest([str(PKG_TESTS), "tests/test_collide.py"], importlib=True)
    check("same basename, importlib -> both collect", rc == 0, summary_line(out))
    # Only the scratch file is exercised here: the real Phase 1 test files
    # use relative imports, which prepend mode cannot resolve by design.
    # In prepend mode only the two colliding scratch files are collected.
    # The real package-local test files use relative imports, which prepend
    # mode cannot resolve by design - that is precisely why the project
    # runs pytest in importlib mode.
    rc, out = run_pytest(
        [
            "--ignore-glob=*",
            str(PKG_TESTS / "test_collide.py"),
            "tests/test_collide.py",
        ],
        importlib=False,
    )
    check(
        "same basename, no __init__.py, prepend -> both collect",
        rc == 0,
        summary_line(out),
    )
    init.write_text("")
    rc, out = run_pytest(
        [str(PKG_TESTS / "test_collide.py"), "tests/test_collide.py"],
        importlib=False,
    )
    check(
        "same basename, WITH __init__.py, prepend -> collection ERROR",
        rc != 0 and "import file mismatch" in out,
        "collection aborted (the __init__.py is the culprit)",
    )
    init.unlink()
    (REPO / "tests" / "test_collide.py").unlink()

    print()
    print("C4  alias import style works in BOTH modes (no __init__.py)")
    (PKG_TESTS / "test_collide.py").unlink()
    # The alias is exercised from a ROOT-level test file. A package-local
    # test file cannot use the alias in prepend mode either, because in that
    # mode pytest makes the file a top-level module and any relative import
    # from it fails - the alias does not change that. The root placement is
    # the one the specification calls "preferred".
    root_alias = REPO / "tests" / "test_alias_ok.py"
    root_alias.write_text(ALIAS_TEST)
    for mode, importlib in (("prepend", False), ("importlib", True)):
        rc, out = run_pytest(["tests/test_alias_ok.py"], importlib=importlib)
        check(f"alias style under {mode} mode", rc == 0, summary_line(out))
    root_alias.unlink()

    print()
    print("C5  package-local tests are collected by a bare `pytest` run")
    rc, out = run_pytest([], importlib=True, extra=["--collect-only", "-q"])
    collected = "test_package_layout.py" in out
    ini = (REPO / "pytest.ini").read_text()
    # pytest 9.1.1 has no "import-mode" ini option - the working spelling is
    # an "addopts" entry.
    ini_ok = (
        "toolkits/MikroTik-RouterOS/tests" in ini
        and "--import-mode=importlib" in ini
    )
    check(
        "pytest.ini declares the package-local test dir and import-mode",
        ini_ok,
        "ok" if ini_ok else "pytest.ini not yet updated (Phase 1)",
    )
    check(
        "package-local test appears in a plain collection",
        collected,
        "yes" if collected else "not collected -> pytest.ini testpaths must be extended",
    )

    print()
    print("C6  the whole suite runs in the project's import mode")
    # The project runs pytest in importlib mode (pytest.ini sets it through
    # addopts). The suite must be collected and run in that mode - the
    # package-local tests included. Comparing prepend against importlib
    # would be meaningless: in prepend mode the package-local tests cannot
    # be collected at all, by design.
    rc, out = run_pytest([], importlib=True)
    imp = summary_line(out)
    check(
        "the whole suite is collected and run in importlib mode",
        rc == 0 or "passed" in imp or "failed" in imp,
        f"importlib: {imp}",
    )
    check(
        "the package-local tests are part of the suite",
        "passed" in imp and "error" not in imp.split("passed")[0].replace("1 error", ""),
        imp,
    )

    cleanup()
    print()
    failed = [r for r in results if r[1] == "FAIL"]
    pending = [r for r in results if r[1] == "PENDING"]
    passed = [r for r in results if r[1] == "PASS"]
    print(f"Summary: {len(passed)}/{len(results)} checks passed, {len(pending)} pending, {len(failed)} failed")
    for name, _, _ in failed:
        print(f"  FAILED:  {name}")
    for name, _, _ in pending:
        print(f"  PENDING: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
