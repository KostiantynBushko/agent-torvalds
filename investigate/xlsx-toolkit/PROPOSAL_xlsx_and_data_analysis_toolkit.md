# Proposal: Microsoft Excel XLSX & Data Analysis Toolkit

**Date:** 2026-01-28  
**Author:** Torvalds Agent  
**Repository:** `KostiantynBushko/agent-torvalds`  
**Branch:** `self-development/master`  
**Based on:** `investigation_xlsx_support.md`

---

## 1. Overview

This proposal introduces a new **Excel XLSX Toolkit** and integrates a **Data Analysis Library (pandas)** into the agent. This enables the agent to read, write, modify, and perform statistical analysis on Microsoft Excel files — a critical capability for business data workflows, reporting, and automation tasks.

---

## 2. Goals

1. Enable the agent to **read and write `.xlsx` files** directly.
2. Provide **data analysis capabilities** using `pandas` for tabular data operations.
3. Maintain **consistent toolkit architecture** aligned with existing agent modules.
4. Ensure **safety**: no formula evaluation risks, memory-aware processing, and file validation.

---

## 3. Scope

### In Scope
- Install `openpyxl` and `pandas` in the Python environment.
- Create `agent_xlsx_toolkit.py` for Excel file operations.
- Create `agent_data_analysis_toolkit.py` for pandas-powered data analysis.
- Register new toolkits in `agent_tool_retriever.py`.
- Update `requirements.txt` with new dependencies.
- Write unit tests for both toolkits.
- Generate documentation and changelog entries.

### Out of Scope
- Support for `.xlsm` (macro-enabled) files.
- Real-time Excel server integration.
- Native formula evaluation engine (deferred to future work).

---

## 4. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `openpyxl` | 3.1.5 | Read/write `.xlsx` files |
| `pandas` | latest | Data analysis, DataFrame operations |
| `numpy` | latest | (pandas dependency) Numerical computing |
| `et-xmlfile` | latest | (openpyxl dependency) XML handling |

> **Note:** All dependencies are pure-Python packages. No system-level installs required.

---

## 5. Implementation Details

### 5.1. Excel XLSX Toolkit (`agent_xlsx_toolkit.py`)

**Category:** `Data / Excel`

| Function | Description | Parameters |
|----------|-------------|------------|
| `read_xlsx_file(path, sheet_name)` | Read cell data from an Excel file | `path`, `sheet_name` (optional) |
| `write_xlsx_file(path, data, sheet_name)` | Write data to a new/updated Excel file | `path`, `data` (list/dict), `sheet_name` |
| `get_sheet_names(path)` | List all sheet names in a workbook | `path` |
| `get_cell_value(path, sheet_name, cell)` | Get value of a specific cell | `path`, `sheet_name`, `cell` (e.g. "A1") |
| `set_cell_value(path, sheet_name, cell, value)` | Set a cell value and save | `path`, `sheet_name`, `cell`, `value` |
| `get_dimensions(path, sheet_name)` | Get used range dimensions | `path`, `sheet_name` |
| `copy_sheet(source_path, dest_path)` | Copy a sheet to a new workbook | `source_path`, `dest_path` |
| `apply_style(path, sheet_name, range, style)` | Apply formatting to a cell range | `path`, `sheet_name`, `range`, `style` dict |

### 5.2. Data Analysis Toolkit (`agent_data_analysis_toolkit.py`)

**Category:** `Data / Analysis`

| Function | Description | Parameters |
|----------|-------------|------------|
| `read_excel_to_df(path, sheet_name)` | Load Excel into pandas DataFrame | `path`, `sheet_name` (optional) |
| `describe_data(path, sheet_name)` | Summary statistics of a sheet | `path`, `sheet_name` |
| `filter_data(path, sheet_name, column, condition)` | Filter rows by condition | `path`, `sheet_name`, `column`, `condition` |
| `aggregate_data(path, sheet_name, group_col, agg_col, agg_func)` | Group and aggregate data | `path`, `sheet_name`, `group_col`, `agg_col`, `agg_func` |
| `export_dataframe(df, path, sheet_name)` | Export DataFrame to Excel | `df`, `path`, `sheet_name` |
| `pivot_table(path, sheet_name, index, columns, values)` | Create a pivot table | `path`, `sheet_name`, `index`, `columns`, `values` |
| `detect_missing_data(path, sheet_name)` | Identify null/empty cells | `path`, `sheet_name` |
| `correlation_matrix(path, sheet_name)` | Compute numeric column correlations | `path`, `sheet_name` |

### 5.3. Registration in Tool Retriever

Update `agent_tool_retriever.py`:
```python
from agent_xlsx_toolkit import *
from agent_data_analysis_toolkit import *

# Register under categories:
# "Data / Excel" → xlsx toolkit functions
# "Data / Analysis" → pandas toolkit functions
```

### 5.4. Requirements Update

```txt
# Excel & Data Analysis
openpyxl==3.1.5
pandas>=2.0.0
```

---

## 6. Architecture Diagram

```
┌─────────────────────────────────────────────┐
│           Agent Toolkit Registry            │
├─────────────────────────────────────────────┤
│                                             │
│  "Data / Excel"       "Data / Analysis"     │
│       │                      │              │
│       ▼                      ▼              │
│  agent_xlsx_toolkit   agent_data_analysis   │
│       │                  │_toolkit          │
│       │                      │              │
│       ▼                      ▼              │
│   openpyxl (3.1.5)     pandas (latest)     │
│       │                      │              │
│       └──────────────────────┼──────────────┘
│                              │              │
│              ┌───────────────┼──────────────┐│
│              ▼               ▼               ││
│         .xlsx Files      DataFrames (in-mem) │
└─────────────────────────────────────────────┘
```

---

## 7. Safety & Security

1. **File Validation:** Check magic bytes and extension before processing.
2. **Memory Protection:** Limit row/column counts for large files; stream when possible.
3. **Path Sanitization:** Prevent directory traversal in file paths.
4. **No Macro Execution:** `.xlsm` files explicitly unsupported.
5. **Write Safety:** Confirm overwrites; support backup before modification.

---

## 8. Testing Plan

| Test File | Coverage |
|-----------|----------|
| `tests/test_xlsx_toolkit.py` | Read/write, cell operations, sheet management, styles |
| `tests/test_data_analysis_toolkit.py` | DataFrame ops, filtering, aggregation, pivots, missing data |

**Test fixtures:** Include sample `.xlsx` files with:
- Basic data table
- Multiple sheets
- Formatted cells
- Mixed data types
- Empty/missing values

---

## 9. Implementation Steps

| Step | Task | Status |
|------|------|--------|
| 1 | Install `openpyxl` and `pandas` | ⬜ |
| 2 | Create `agent_xlsx_toolkit.py` | ⬜ |
| 3 | Create `agent_data_analysis_toolkit.py` | ⬜ |
| 4 | Register toolkits in `agent_tool_retriever.py` | ⬜ |
| 5 | Update `requirements.txt` | ⬜ |
| 6 | Write unit tests | ⬜ |
| 7 | Run tests and verify | ⬜ |
| 8 | Update changelog | ⬜ |
| 9 | Commit and prepare PR | ⬜ |

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Large files consume memory | High | Implement chunked reading; add size limits |
| Incompatible Excel features | Medium | Document unsupported features clearly |
| pandas version conflicts | Low | Pin minimum version, test compatibility |
| Formula evaluation gaps | Low | Use `openpyxl` read-only mode; note limitation |

---

## 11. Acceptance Criteria

- [ ] `openpyxl` and `pandas` installed and importable
- [ ] `agent_xlsx_toolkit.py` created with ≥8 functions
- [ ] `agent_data_analysis_toolkit.py` created with ≥8 functions
- [ ] Both toolkits registered in `agent_tool_retriever.py`
- [ ] `requirements.txt` updated
- [ ] All unit tests pass (coverage ≥ 80%)
- [ ] No regressions in existing toolkits
- [ ] Changelog entry added

---

## 12. Timeline Estimate

| Phase | Duration |
|-------|----------|
| Dependency installation & setup | 5 min |
| Toolkit implementation | 2 hrs |
| Testing & fixtures | 1 hr |
| Registration & integration | 30 min |
| Documentation & changelog | 30 min |
| **Total** | **~4 hours** |

---

*Proposal based on investigation: `investigate/investigation_xlsx_support.md`*  
*Created in: `/home/agent/ai-agent-investigate/agent-torvalds/self-development`*
