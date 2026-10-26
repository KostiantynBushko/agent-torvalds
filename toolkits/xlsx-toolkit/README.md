# Excel XLSX Toolkit

Read, write, and modify Microsoft Excel (`.xlsx`) files, exposed as tools
for a LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/xlsx-toolkit/
├── __init__.py            # the public API surface
├── operations.py           # the Excel operations — the library half
├── agent_xlsx_toolkit.py    # the LlamaIndex adapter
├── py.typed                # PEP 561 marker
└── tests/                  # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 9 Excel operations | **no** | `openpyxl` |
| `agent_xlsx_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the Excel operations stay usable — and testable — as a plain Python
library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

## Installing

Standalone:

```bash
pip install .            # the library half
pip install '.[agent]'   # and the LlamaIndex adapter
```

The library half depends on `openpyxl` (the Excel file format is the file
format) and on the standard library, and on nothing else.

## Importing

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.xlsx_toolkit import read_xlsx_file, write_xlsx_file
from toolkits.xlsx_toolkit.agent_xlsx_toolkit import get_all_tools
```

The adapter pulls the library in with a *relative* import, so the adapter
and the library share one set of module objects — there is never a second
copy of `operations.py` in memory.

## Using the tools

```python
from toolkits.xlsx_toolkit.agent_xlsx_toolkit import get_all_tools

tools = get_all_tools()   # 9 FunctionTool objects
```

The 9 tools carry the **Data / Excel** category, so the startup tool
selection menu (`--select`, and `\tools` / `\tool-select` in the TUI) can
load the whole category on its own.

## The tool surface

**Reading and writing**

| Tool | Purpose |
|------|---------|
| `read_xlsx_file` | read a sheet as a list of dicts, keyed by the header row |
| `write_xlsx_file` | write a list of dicts to a new workbook |

**Sheets**

| Tool | Purpose |
|------|---------|
| `get_sheet_names` | every sheet in a workbook |
| `copy_sheet` | copy one sheet into a new file |
| `get_dimensions` | the used range of a sheet, e.g. `A1:D50` |

**Cells**

| Tool | Purpose |
|------|---------|
| `get_cell_value` | the value of one cell, e.g. `A1` |
| `set_cell_value` | write one cell and save the file |

**Formatting and workbooks**

| Tool | Purpose |
|------|---------|
| `apply_style` | bold, colour, alignment, border and fill over a range |
| `create_empty_workbook` | a new workbook, optionally with named sheets |

## The error contract

A tool never raises. Every failure is reported as a value:

* a missing file is `"Error: File not found: <path>"`
* a failed read is `"Error reading Excel file: ..."`
* a failed write is `"Error writing Excel file: ..."`
* and so on for the remaining operations

The one thing that is *not* an error string is a cell that holds nothing:
`get_cell_value` returns `None`, because that is the value of an empty
cell.

## Tests

```bash
pytest toolkits/xlsx-toolkit/tests
```

The suite covers the operations themselves and the **layout contract** —
the rules that keep the toolkit a module: the flat directory, the relative
imports, the alias, and the LlamaIndex-free library half.
