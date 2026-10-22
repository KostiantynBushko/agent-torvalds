# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

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
