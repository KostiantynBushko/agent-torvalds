# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed

- **The package moved out of `src/` - and out of its own directory.**
  The importable `shodan_toolkit` package used to sit in
  `src/shodan_toolkit/`, following the upstream src-layout. It now sits
  **directly in the toolkit folder**: the directory *is* the package, and
  the modules sit next to `tests/` and `examples/`, so the toolkit has the
  same shape as the MikroTik one - a folder that holds the package, the
  tests and the documentation side by side.

  There is no `src/` level and no nested `shodan_toolkit/` directory:

  ```
  toolkits/shodan-toolkit/
  |-- __init__.py            public API
  |-- __main__.py            `python -m shodan_toolkit` entry point
  |-- agent.py               FunctionAgent factory
  |-- agent_shodan_toolkit.py  LlamaIndex adapter - the agent tools
  |-- cli.py                 command-line interface
  |-- client.py              typed Python API
  |-- config.py              configuration resolution
  |-- parsers.py             text -> structured records
  |-- runner.py              subprocess execution
  |-- tools.py               LlamaIndex FunctionTool wrappers
  |-- tests/                 the test suite
  `-- examples/              verification and demo scripts
  ```

  **The import path does not change.** The package is still imported as
  `shodan_toolkit`::

      from shodan_toolkit import ShodanClient, get_all_tools

  and inside this repository it is still reached through the alias that
  `toolkits/__init__.py` registers::

      from toolkits.shodan_toolkit import ShodanClient

  Only the directory it lives in changed - two levels shallower.

- **The distribution is flat now.** `pyproject.toml` no longer sets
  `package-dir = { "" = "src" }`; the package directory name contains a
  hyphen, which is not a valid Python identifier, so the mapping is
  spelled out (`packages = ["shodan_toolkit"]`,
  `package-dir = { "shodan_toolkit" = "." }`). `pip install .` and
  `pip install -e .` produce exactly the same import name as before, and
  the wheel contains the ten modules of the package and nothing else. The
  console script (`shodan-toolkit`) and the module entry point
  (`python -m shodan_toolkit`) are unaffected.

- **The modules of the package import each other with relative imports.**
  They always did; what changed is that the package is now the toolkit
  directory, so the absolute form (`from shodan_toolkit.client import ...`)
  is not available inside this repository - the directory name contains a
  hyphen.  The tests use the same form (`from ..client import ...`).

- **The test suite runs against the package, not against a copy.**
  `tests/conftest.py` and the test modules reach the library through
  relative imports, so the suite always exercises the in-repository
  copy - the same code the agent adapter loads.

- **The agent adapter moved into the package.** `agent_shodan_toolkit.py` used
  to live at the repository root; it is now a submodule of the toolkit
  package, at `shodan_toolkit/agent_shodan_toolkit.py`, so the whole
  feature is one folder. Inside this repository it is reached through the
  alias that `toolkits/__init__.py` registers:

  ```python
  from toolkits.shodan_toolkit.agent_shodan_toolkit import get_all_tools
  ```

  The adapter pulls the core package in with a **relative** import
  (`from . import ...`), so it also works when the toolkit is installed as a
  standalone distribution, where no `toolkits` package exists at all.

### Fixed

- **`--no-color` was passed to subcommands that reject it.** `shodan stats`,
  `shodan trends`, `shodan host` and `shodan domain` do not declare a
  `--no-color` option, so `click` aborted every one of those commands with
  `Error: No such option '--no-color'` before any API call. Only
  `shodan search` accepts the flag; the others now omit it. Colour is still
  suppressed through `NO_COLOR=1` and `TERM=dumb` in the runner's
  environment.
- **`--ipv6` was passed to the wrong command level.** `shodan --ipv6 myip`
  is invalid — `--ipv6` belongs to the `myip` subcommand. The client now
  builds `shodan myip --ipv6`.
- **`is_available()` reported a broken CLI as healthy.** It only checked
  that a file named `shodan` existed. The Shodan CLI 1.31.0 imports
  `pkg_resources`, which setuptools 81+ removed, so such an installation
  exists on disk but aborts on startup. The check now runs the binary and
  reports it as unavailable when it cannot start.
- **`shodan_raw` could run state-changing commands.** It is registered in
  the read-only category and handed to autonomous agents, so it now refuses
  `alert create`, `alert remove`, `alert clear`, `alert import`,
  `scan submit`, `scan internet`, `download`, `data download`, `org add`,
  `org remove` and `init` with an explanatory error.

### Added

- **`python -m shodan_toolkit` entry point.** The toolkit can now be run as
  a module, which works even when the console script is not on `PATH`.
- **`examples/verify_argv.py`.** Runs every argument vector the client can
  build against the installed binary and reports the ones the CLI rejects.
- **`tests/test_cli_contract.py`.** Pins the option set of shodan 1.31.0 so
  an invalid flag is caught without a network or an installed CLI.
- **`tests/test_runner_availability.py`.** Covers the availability check
  against missing, healthy and broken CLI installations.
- **`tests/test_raw_guard.py`.** Covers the `shodan_raw` read-only guard.
- **`tests/test_agent_adapter.py`.** Covers the agent adapter: the tool
  registration, the degradation contract and the load-path parity. It skips
  itself when the toolkit is used as a standalone distribution.
- **`tests/test_package_layout.py`.** Pins the layout contract: the
  package is the toolkit directory itself, there is no `src/` level and no
  nested package directory, the modules use relative imports, and the
  import alias resolves to this very package.
- **`shodan_cli_env` check in `doctor`.** Warns when the resolved `shodan`
  belongs to a different virtualenv than the one running the toolkit — a
  common source of confusing failures when the toolkit is used as a library.
- **`LICENSE` file** and an SPDX `license` expression.

### Changed

- **Python floor raised to 3.10.** `pydantic>=2.0` and
  `llama-index-core>=0.12` both require 3.10+, so the previous `>=3.9`
  claim was not satisfiable.
- **Packaging metadata modernised.** The deprecated `license = {text = ...}`
  table and the deprecated license classifier were replaced with the SPDX
  `license = "MIT"` field; the 3.9 classifier was dropped. Builds are now
  warning-free.
- **`ruff` and `mypy` targets moved to 3.10** to match the new floor.

## [0.1.0] - 2026-10-21

### Features

- Initial release: `ShodanClient` Python API, LlamaIndex `FunctionTool`
  wrappers, `FunctionAgent` factory, and the `shodan-toolkit` CLI.
- 79 unit tests, parser verification against real CLI output, and an
  end-to-end smoke test.
