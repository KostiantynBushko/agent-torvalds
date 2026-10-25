"""
verify_layout_contract.py - empirical verification of MODULE_SPECIFICATION.md.

Validates every row of the behaviour matrix in
``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md`` §3.2 against the
actual repository state, using the project's own venv.

Run from the repository root of the clone:

    self-development/.venv/bin/python \
        self-development/investigate/MikroTik-RouterOS/verify_layout_contract.py
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The agent adapter.  It lives inside the package - it is a submodule of
#: it - and it is the one module of the feature that knows about
#: LlamaIndex.  The LlamaIndex-free rule therefore applies to the library
#: half of the package.
ADAPTER_FILE = "agent_mikrotik_toolkit.py"

PASS = "PASS"
FAIL = "FAIL"

results: list[tuple[str, str, str]] = []


def record(row: str, name: str, ok: bool, detail: str = "") -> None:
    results.append((row, name, PASS if ok else FAIL))
    print(f"  [{PASS if ok else FAIL}] row {row}: {name}" + (f" -- {detail}" if detail else ""))


def run_python(code: str, cwd: Path) -> tuple[int, str, str]:
    """Run a snippet in a subprocess with the repo root on sys.path."""
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def main() -> int:
    print(f"Repository root: {REPO}")
    print(f"Python: {sys.version.split()[0]}")
    print()

    # ------------------------------------------------------------------
    print("§3.2 behaviour matrix")
    # ------------------------------------------------------------------

    # Row 1 / 2 - a hyphen in an import statement is a SyntaxError.
    for row, stmt in (
        ("1", "from toolkits.MikroTik-RouterOS import MikroTikTarget"),
        ("2", "import toolkits.MikroTik-RouterOS"),
    ):
        rc, out, err = run_python(stmt, REPO)
        record(
            row,
            f"SyntaxError expected for `{stmt}`",
            rc != 0 and "SyntaxError" in err,
            err.splitlines()[-1] if err else "no error",
        )

    # Row 3 - importlib can reach the hyphenated package.
    rc, out, err = run_python(
        """
        import importlib
        m = importlib.import_module("toolkits.MikroTik-RouterOS")
        print("OK", m.__name__)
        """,
        REPO,
    )
    record("3", "importlib.import_module('toolkits.MikroTik-RouterOS')", rc == 0, out or err)

    # Row 4 - relative imports inside the package work.
    rc, out, err = run_python(
        """
        import importlib
        importlib.import_module("toolkits.MikroTik-RouterOS")
        print("OK")
        """,
        REPO,
    )
    record("4", "package with relative imports loads", rc == 0, out or err)

    # Row 5 - absolute imports inside the package are a SyntaxError.
    rc, out, err = run_python(
        """
        from toolkits.MikroTik-RouterOS.config import MikroTikTarget
        """,
        REPO,
    )
    record(
        "5",
        "absolute import inside package -> SyntaxError",
        rc != 0 and "SyntaxError" in err,
        err.splitlines()[-1] if err else "no error",
    )

    # Row 6 - test module at the repo root, default import mode.
    with tempfile.TemporaryDirectory() as tmp:
        test_file = Path(tmp) / "test_mikrotik_layout_root.py"
        test_file.write_text(
            textwrap.dedent(
                """
                def test_alias_resolves():
                    from toolkits.mikrotik_routeros import __name__ as pkg_name
                    assert pkg_name is not None
                """
            )
        )
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
        )
        record(
            "6",
            "root-level test module, default import mode",
            proc.returncode == 0,
            f"rc={proc.returncode}",
        )

    # Row 7 / 8 - a test module inside the hyphenated directory.
    # The corrected contract (see verify_test_contract.py):
    #   * no __init__.py in the package-local test dir
    #   * --import-mode=importlib
    pkg_tests = REPO / "toolkits" / "MikroTik-RouterOS" / "tests"
    created_pkg_tests = False
    try:
        pkg_tests.mkdir(parents=True, exist_ok=True)
        created_pkg_tests = True
        probe = pkg_tests / "test_layout_probe.py"
        probe.write_text(
            textwrap.dedent(
                """
                from .. import __name__ as PKG

                def test_relative_import_works():
                    assert PKG is not None
                """
            )
        )
        # Default (prepend) mode: relative import fails.
        #
        # pytest.ini sets "addopts = --import-mode=importlib", so the
        # default mode has to be requested explicitly with
        # "--import-mode=prepend" - otherwise the ini would win and the
        # check would be meaningless.
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(probe),
                "-q", "--no-header", "-p", "no:cacheprovider",
                "--import-mode=prepend",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
        )
        record(
            "7",
            "package-local relative import, default import mode -> ImportError",
            proc.returncode != 0 and "ImportError" in proc.stdout + proc.stderr,
            f"rc={proc.returncode}",
        )
        # importlib mode: relative import works.
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(probe), "-q", "--no-header",
                "-p", "no:cacheprovider", "--import-mode=importlib",
            ],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
        )
        record(
            "8",
            "package-local relative import, --import-mode=importlib -> passes",
            proc.returncode == 0,
            f"rc={proc.returncode}",
        )
    finally:
        for f in ("test_layout_probe.py", "__init__.py"):
            p2 = pkg_tests / f
            if p2.exists():
                p2.unlink()
        if created_pkg_tests and pkg_tests.exists() and not any(pkg_tests.iterdir()):
            pkg_tests.rmdir()

    # Row 9 - toolkits/ without __init__.py works as a namespace package.
    init_file = REPO / "toolkits" / "__init__.py"
    init_backup = init_file.read_text() if init_file.exists() else None
    try:
        if init_file.exists():
            init_file.unlink()
        rc, out, err = run_python(
            """
            import importlib
            m = importlib.import_module("toolkits.MikroTik-RouterOS")
            print("OK", m.__name__)
            """,
            REPO,
        )
        record("9", "toolkits/ as a namespace package (no __init__.py)", rc == 0, out or err)
    finally:
        if init_backup is not None:
            init_file.write_text(init_backup)

    # Row 10 - the sys.modules alias makes plain `import` statements work.
    rc, out, err = run_python(
        """
        from toolkits.mikrotik_routeros import __name__ as pkg_name
        import toolkits.mikrotik_routeros as mr
        assert mr is not None
        print("OK", pkg_name)
        """,
        REPO,
    )
    record("10", "alias allows plain `import toolkits.mikrotik_routeros`", rc == 0, out or err)

    # ------------------------------------------------------------------
    print()
    print("§3.3 alias semantics")
    # ------------------------------------------------------------------
    rc, out, err = run_python(
        """
        import sys
        import toolkits
        import importlib
        real = importlib.import_module("toolkits.MikroTik-RouterOS")
        alias = sys.modules["toolkits.mikrotik_routeros"]
        assert real is alias, "alias must be the same module object"
        print("OK")
        """,
        REPO,
    )
    record("3.3a", "alias is the same object (identity holds)", rc == 0, out or err)

    rc, out, err = run_python(
        """
        import toolkits
        print("OK", hasattr(toolkits, "mikrotik_routeros"))
        """,
        REPO,
    )
    record("3.3b", "`import toolkits` succeeds and exposes the alias", rc == 0, out or err)

    # `import toolkits` must never raise even if the package is broken.
    rc, out, err = run_python(
        """
        import sys, types
        # Simulate a package that explodes at import time.
        broken = types.ModuleType("toolkits.MikroTik-RouterOS")
        def boom():
            raise RuntimeError("boom")
        class BrokenFinder:
            def find_module(self, name, path=None):
                return None
        import importlib.abc, importlib.machinery
        class Loader(importlib.abc.Loader):
            def create_module(self, spec):
                return None
            def exec_module(self, module):
                boom()
        class Finder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "toolkits.MikroTik-RouterOS":
                    return importlib.machinery.ModuleSpec(fullname, Loader())
                return None
        sys.meta_path.insert(0, Finder())
        import toolkits
        print("OK", hasattr(toolkits, "mikrotik_routeros"))
        """,
        REPO,
    )
    record("3.3c", "`import toolkits` survives a package that raises on import", rc == 0, out or err)

    # ------------------------------------------------------------------
    print()
    print("§2.2 layout contract")
    # ------------------------------------------------------------------
    pkg_dir = REPO / "toolkits" / "MikroTik-RouterOS"
    record("2.2a", "toolkits/ exists at the repository root", (REPO / "toolkits").is_dir())
    record("2.2b", "toolkits/MikroTik-RouterOS/ exists (exact case)", pkg_dir.is_dir())
    record("2.2c", "toolkits/__init__.py exists", (REPO / "toolkits" / "__init__.py").is_file())
    record(
        "2.2d",
        "exact directory name is 'MikroTik-RouterOS'",
        pkg_dir.name == "MikroTik-RouterOS",
        pkg_dir.name,
    )

    # ------------------------------------------------------------------
    print()
    print("§4.2 binding rules")
    # ------------------------------------------------------------------
    llama_hits: list[str] = []
    abs_import_hits: list[str] = []
    adapter_hits: list[str] = []
    if pkg_dir.is_dir():
        for py in pkg_dir.rglob("*.py"):
            # The agent adapter is the one module of the package that knows
            # about LlamaIndex.  It lives inside the package now, so the
            # LlamaIndex-free rule is scoped to the library half - and the
            # exception is narrow: a LlamaIndex import in any other module
            # still fails.
            is_adapter = py.name == ADAPTER_FILE
            src = py.read_text()
            # AST-based: matches real import statements only, and ignores the
            # prose in docstrings that mentions the import path. A plain
            # grep would flag the layout test itself, which has to name
            # "llama_index" in order to assert that it is not imported.
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.split(".")[0] == "llama_index":
                            (adapter_hits if is_adapter else llama_hits).append(
                                f"{py}:{node.lineno} -> {a.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split(".")[0] == "llama_index":
                        (adapter_hits if is_adapter else llama_hits).append(
                            f"{py}:{node.lineno} -> {node.module}"
                        )
            # The alias "toolkits.mikrotik_routeros" is the sanctioned way
            # in, so it is not an absolute-import violation. The hyphenated
            # form cannot appear in valid source at all.
            alias_module = "toolkits.mikrotik_routeros"
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module and node.module.split(".")[0] == "toolkits" and node.module != alias_module:
                        abs_import_hits.append(f"{py}:{node.lineno} -> {node.module}")
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.split(".")[0] == "toolkits" and a.name != alias_module:
                            abs_import_hits.append(f"{py}:{node.lineno} -> {a.name}")
    record("R1", "no LlamaIndex import under the library half of the package", not llama_hits, ", ".join(llama_hits))
    record("R2", "no absolute `toolkits` import statement inside the package", not abs_import_hits, ", ".join(abs_import_hits))
    record(
        "R1b",
        "the agent adapter is the only LlamaIndex-dependent module",
        (pkg_dir / ADAPTER_FILE).is_file() and bool(adapter_hits),
        ", ".join(adapter_hits),
    )

    rc, out, err = run_python(
        """
        import sys
        import toolkits
        print("CLEAN" if "llama_index" not in sys.modules else "LEAK")
        """,
        REPO,
    )
    record(
        "R1c",
        "`import toolkits` does not pull in LlamaIndex",
        rc == 0 and "CLEAN" in out,
        out or err,
    )

    rc, out, err = run_python(
        """
        from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import get_all_tools
        print("OK" if callable(get_all_tools) else "BROKEN")
        """,
        REPO,
    )
    record(
        "R4",
        "the agent adapter is reachable through the alias",
        rc == 0 and "OK" in out,
        out or err,
    )

    rc, out, err = run_python(
        """
        import toolkits
        print("OK")
        """,
        REPO,
    )
    record("R5", "`import toolkits` never raises", rc == 0, out or err)

    # ------------------------------------------------------------------
    print()
    print("Summary")
    # ------------------------------------------------------------------
    failed = [r for r in results if r[2] == FAIL]
    print(f"  {len(results) - len(failed)}/{len(results)} checks passed")
    for row, name, _ in failed:
        print(f"  FAILED row {row}: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
