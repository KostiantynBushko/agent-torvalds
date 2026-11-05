---
name: add-toolkit
description: Add a new toolkit to this project. Use it when the user asks for a new group of tools, a new integration, or a new module of tools that the agent should be able to call.
---

# Add a toolkit

A toolkit is a **reusable library plus a thin adapter** for the agent.  The
library half knows nothing about LlamaIndex; the adapter half is the only
module that does.

## The folder

```
toolkits/<name>/
├── __init__.py
├── operations.py            # the library half — plain Python, no LlamaIndex
├── agent_<name>_toolkit.py  # the adapter — the only module that imports LlamaIndex
├── cli.py                   # the command line interface
├── __main__.py              # so that `python -m toolkits.<name>_toolkit` works
├── py.typed
├── pyproject.toml
├── README.md
└── tests/
```

The directory name may carry a hyphen — every toolkit does — and the import
name then uses underscores.  `toolkits/apt-toolkit/` is imported as
`toolkits.apt_toolkit`.

## The four steps nobody skips

### 1. The alias in `toolkits/__init__.py`

A hyphen is not a valid Python identifier, so the directory can never be
reached with a plain import.  `toolkits/__init__.py` registers an alias that
points at the very same package object.

Add three things:

* the name to `_ALIAS_NAMES`,
* the adapter module to `_ADAPTER_MODULES` — it is **never** published
  eagerly, because it imports LlamaIndex and the library half has to stay
  usable without it,
* the registration itself, at the bottom, in the shape of the others:

  ```python
  _<NAME>_PACKAGE = "toolkits.<name-with-hyphen>"
  _<NAME>_ALIAS = "toolkits.<name_with_underscores>"

  _<name> = _register_alias(_<NAME>_PACKAGE, _<NAME>_ALIAS)
  if _<name> is not None:
      <name_with_underscores> = _<name>
  ```

The alias paths are **literals**, on purpose: a computed alias is invisible
to every static reader, and a tool that cannot resolve the name reports it as
missing.  The whole file documents this in its docstring — read it before
you touch it.

### 2. The tests in `pytest.ini`

pytest collects the directories listed in `testpaths` and **nothing else**.
A toolkit whose test directory is not listed there is never run, and the CI
gate cannot see a break in it.

Add `toolkits/<name>/tests` to the `testpaths` line of `pytest.ini`.

### 3. The `pyproject.toml`

The toolkit directory *is* the package, so the mapping is spelled out:

```toml
[tool.setuptools]
packages = ["<name_with_underscores>"]
package-dir = { "<name_with_underscores>" = "." }
```

It also carries the pytest options the hyphenated package needs:

```toml
[tool.pytest.ini_options]
addopts = "-v --tb=short --import-mode=importlib"
consider_namespace_packages = true
```

`--import-mode=importlib` is an **addopts** entry, not an ini option —
pytest 9 ignores the ini spelling and the package-local tests then fail to
import.

### 4. The registration in `agent_tool_retriever.py`

The adapter is imported behind a guard, so that a missing toolkit degrades
gracefully instead of breaking the boot of the agent:

```python
if include_<name>_tools:
    try:
        from toolkits.<name_with_underscores>.agent_<name>_toolkit import (
            get_all_tools as _get_<name>,
        )
        all_tools.extend(_get_<name>())
    except ImportError:
        pass
```

The adapter exposes one function, `get_all_tools()`, which returns the
`FunctionTool` list of the toolkit.

## The checks

```bash
.venv/bin/python -m pytest toolkits/<name>/tests -q
.venv/bin/python -c "from toolkits.<name_with_underscores> import <something>"
.venv/bin/python -c "from toolkits.<name_with_underscores>.agent_<name>_toolkit import get_all_tools; print(len(get_all_tools()))"
.venv/bin/python -m toolkits.<name_with_underscores> --help
.venv/bin/python scripts/ci_test_gate.py
```

The last one is the one that decides: `new failures` must be `0`.

## The rules

* **The library half imports no LlamaIndex.**  That is what makes the
  toolkit usable on its own, and what keeps `import toolkits` from pulling
  the framework into the process.
* **The tools are documented in `README.md`** — what each tool does, and
  what it needs.
* **The configuration is read at import time only if it must be**, and a
  missing configuration file degrades the toolkit instead of breaking it.
* **The changelog entry carries the reason**, not only the list of the tools.
