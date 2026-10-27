# Data Analysis Toolkit

Pandas-powered analysis of tabular data — reading, summarising, filtering,
aggregating and pivoting — exposed as tools for a LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/data-analysis-toolkit/
├── __init__.py                    # the public API surface
├── operations.py                   # the analysis operations — the library half
├── agent_data_analysis_toolkit.py  # the LlamaIndex adapter
├── py.typed                        # PEP 561 marker
└── tests/                          # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 13 analysis operations | **no** | `pandas`, `numpy` |
| `agent_data_analysis_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the analysis operations stay usable — and testable — as a plain Python
library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

## Installing

Standalone:

```bash
pip install .            # the library half
pip install '.[agent]'   # and the LlamaIndex adapter
```

The library half depends on `pandas` (the DataFrame is the data model)
and on `numpy` (the numeric-column inference of the pivot table), and on
the standard library, and on nothing else.

`openpyxl` is needed at **run time**, not at import time: pandas reaches
for it when a workbook is actually read or written. A missing `openpyxl`
therefore breaks the Excel operations and nothing else.

## Importing

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.data_analysis_toolkit import read_excel_to_df, filter_data
from toolkits.data_analysis_toolkit.agent_data_analysis_toolkit import get_all_tools
```

The adapter pulls the library in with a *relative* import, so the adapter
and the library share one set of module objects — there is never a second
copy of `operations.py` in memory.

## Using the tools

```python
from toolkits.data_analysis_toolkit.agent_data_analysis_toolkit import get_all_tools

tools = get_all_tools()   # 13 FunctionTool objects
```

The 13 tools carry the **Data / Analysis** category, so the startup tool
selection menu (`--select`, and `\tools` / `\tool-select` in the TUI) can
load the whole category on its own.

## The tool surface

**Loading**

| Tool | Purpose |
|------|---------|
| `read_excel_to_df` | read a workbook as a list of dicts, keyed by the header row |
| `read_csv_to_df` | read a CSV file as a list of dicts |

**Summaries**

| Tool | Purpose |
|------|---------|
| `describe_data` | descriptive statistics for every numeric column |
| `get_dataframe_info` | shape, columns, dtypes and memory usage |
| `compute_statistics` | mean, median, std, min, max, count and the quartiles of one column |

**Selecting and reshaping**

| Tool | Purpose |
|------|---------|
| `filter_data` | the rows that match a condition, e.g. `"> 100"` |
| `sort_data` | the rows, sorted by one column |
| `get_unique_values` | the distinct values of one column |

**Aggregating**

| Tool | Purpose |
|------|---------|
| `aggregate_data` | group by one column and aggregate another |
| `pivot_table` | a cross-tab of the data |
| `correlation_matrix` | the correlation matrix of the numeric columns |
| `detect_missing_data` | the missing counts and percentages per column |

**Exporting**

| Tool | Purpose |
|------|---------|
| `export_dataframe` | write a list of dicts to a new `.xlsx` or `.csv` file |

## The error contract

A tool never raises. Every failure is reported as a value:

* a missing file is `"Error: File not found: <path>"`
* a failed read is `"Error reading Excel file: ..."` or `"Error reading CSV file: ..."`
* a failed filter is `"Error filtering data: ..."`
* an unsupported export format is `"Error: Unsupported file type '<type>'. Use 'xlsx' or 'csv'."`
* and so on for the remaining operations

## Tests

```bash
pytest toolkits/data-analysis-toolkit/tests
```

The suite covers the operations themselves and the **layout contract** —
the rules that keep the toolkit a module: the flat directory, the relative
imports, the alias, and the LlamaIndex-free library half.
