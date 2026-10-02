# Investigation: Tools Required for Microsoft XLSX File Support

**Date:** 2026-01-28  
**Environment:** Python 3.14.4, Linux (Debian-based)  
**Location:** `/home/agent/ai-agent-investigate/agent-torvalds/self-development`

---

## Executive Summary

To enable the agent to work with Microsoft Excel `.xlsx` files, the primary Python library needed is **`openpyxl`** (version 3.1.5). For advanced data analysis workflows, **`pandas`** is also recommended as it provides high-level DataFrame operations with built-in XLSX support (which depends on `openpyxl`).

---

## Current Status

```bash
python3 -c "import openpyxl"  # ❌ ModuleNotFoundError
python3 -c "import pandas"     # ❌ ModuleNotFoundError
```

**No XLSX-related Python packages are currently installed** in the self-development environment.

---

## Recommended Python Packages

| Package | Version | Purpose | Required? |
|---------|---------|---------|-----------|
| **openpyxl** | 3.1.5 | Read/write `.xlsx` files (Excel 2007+) | ✅ Yes |
| **pandas** | latest | DataFrame operations, data analysis, built-in XLSX I/O | ✅ Recommended |
| xlrd | 2.0.2 | Read `.xls` (legacy Excel format) | ⚠️ Optional |
| xlwt | 1.3.0 | Write `.xls` (legacy format) | ⚠️ Optional |
| pyxlsb | 1.0.10 | Read binary Excel 2007 (`.xlsb`) | ⚠️ Optional |

### Primary Recommendation: `openpyxl`
- **Lightweight** and purpose-built for `.xlsx` format
- Supports reading, writing, and modifying `.xlsx` files
- Full support for:
  - Cell values, styles, formulas, comments
  - Charts, images, and drawings
  - Data validation, conditional formatting
  - Multiple worksheets
  - Rich text and cell comments

### Secondary Recommendation: `pandas`
- High-level data analysis library
- Provides `pd.read_excel()` and `df.to_excel()` methods
- Depends on `openpyxl` for `.xlsx` support
- Essential if data analysis/aggregation is needed

---

## Installation Commands

### Minimal Setup (Read/Write XLSX only)
```bash
pip install openpyxl
```

### Full Data Analysis Setup
```bash
pip install pandas openpyxl
```

### Legacy Format Support (Optional)
```bash
pip install xlrd xlwt pyxlsb
```

---

## System-Level Dependencies

The following system packages were found available via `apt-cache`:

| Package | Description |
|---------|-------------|
| `liborcus-0.21-0` | Library for processing spreadsheet documents (C++) |
| `libfreexl1` | Library for direct reading of Microsoft Excel spreadsheets |
| `golang-github-tealeg-xlsx-dev` | Go library for XLSX |
| `libapache-poi-java` | Java API for Microsoft Documents |
| `libexcel-writer-xlsx-perl` | Perl module for XLSX creation |

> **Note:** For Python-based agent work, these system libraries are **not required**. Pure Python packages (`openpyxl`, `pandas`) are sufficient.

---

## Implementation Plan

### Step 1: Install openpyxl
```bash
pip install openpyxl==3.1.5
```

### Step 2: Create XLSX Toolkit Module
Create a new toolkit file: `agent_xlsx_toolkit.py` with functions for:
- Reading XLSX files (data, formulas, metadata)
- Writing XLSX files (creating new, modifying existing)
- Extracting sheet names, cell ranges, cell values
- Applying styles, conditional formatting
- Handling charts and images

### Step 3: Integration
- Add `agent_xlsx_toolkit.py` to the agent toolkit registry
- Register in `agent_tool_retriever.py`
- Add to `requirements.txt`

### Step 4: Testing
- Create test cases in `tests/test_xlsx_toolkit.py`
- Test read/write operations on sample files
- Verify style and formula preservation

---

## Example Usage

### Basic Reading
```python
from openpyxl import load_workbook

wb = load_workbook('data.xlsx')
ws = wb.active

for row in ws.iter_rows(values_only=True):
    print(row)
```

### Basic Writing
```python
from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws['A1'] = 'Hello'
ws['B1'] = 'World'
wb.save('output.xlsx')
```

### With Pandas
```python
import pandas as pd

df = pd.read_excel('data.xlsx', sheet_name='Sheet1')
print(df.head())
df.to_excel('output.xlsx', index=False)
```

---

## Security & Safety Considerations

1. **File Validation:** Always validate file extension and magic bytes before processing
2. **Memory Limits:** Large XLSX files can consume significant memory; consider row-by-row iteration
3. **Formula Evaluation:** `openpyxl` does **not** evaluate formulas; consider `pyxlsb` or Excel for formula computation
4. **Malicious Content:** XLSX files can contain macros (`.xlsm`); treat as potentially unsafe
5. **Path Traversal:** Sanitize file paths before reading/writing

---

## Conclusion

**To enable XLSX support in the agent, install `openpyxl` as the primary library.** Add `pandas` if data analysis capabilities are needed. Both are pure-Python packages with no system-level dependencies, making installation straightforward and safe.

---

*Investigation conducted in: `/home/agent/ai-agent-investigate/agent-torvalds/self-development`*
