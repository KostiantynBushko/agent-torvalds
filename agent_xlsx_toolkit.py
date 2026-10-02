"""
Excel XLSX Toolkit - Read, write, and modify Microsoft Excel (.xlsx) files.

This module provides functions to interact with Excel files using openpyxl.
Supports reading, writing, cell operations, sheet management, and styling.

Category: Data / Excel
Retriever Keywords: excel, xlsx, spreadsheet, workbook, worksheet, cells, read, write

Prerequisites:
    - openpyxl>=3.1.5 must be installed
"""
import os
import logging
from typing import Any
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


def read_xlsx_file(path: str, sheet_name: str = None) -> list:
    """
    Read data from an Excel file and return as a list of dictionaries.
    
    Each row is represented as a dictionary where keys are column headers
    (from the first row) and values are the cell contents.
    
    Args:
        path (str): Path to the .xlsx file
        sheet_name (str, optional): Name of the sheet to read. Defaults to active sheet.
        
    Returns:
        list: List of dictionaries representing rows of data
        
    Example:
        >>> read_xlsx_file("data.xlsx")
        [{'Name': 'Alice', 'Age': 30}, {'Name': 'Bob', 'Age': 25}]
        
    Keywords: read, import, load, data, rows, columns
    """
    logger.info(f"read_xlsx_file called with path={path}, sheet_name={sheet_name}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        wb = load_workbook(filename=path, read_only=True, data_only=True)
        ws = wb[sheet_name] if sheet_name else wb.active
        
        rows = []
        headers = None
        for row in ws.iter_rows(values_only=True):
            if headers is None:
                headers = list(row)
            else:
                rows.append(dict(zip(headers, row)))
        
        wb.close()
        return rows
    except Exception as e:
        return f"Error reading Excel file: {str(e)}"


def write_xlsx_file(path: str, data: list, sheet_name: str = "Sheet1") -> str:
    """
    Write data to a new or updated Excel file.
    
    Args:
        path (str): Path where the .xlsx file should be saved
        data (list): List of dictionaries where keys are column headers
        sheet_name (str, optional): Name of the sheet. Defaults to "Sheet1"
        
    Returns:
        str: Success message or error description
        
    Example:
        >>> write_xlsx_file("output.xlsx", [{'Name': 'Alice', 'Age': 30}])
        'File saved to output.xlsx'
        
    Keywords: write, export, save, create
    """
    logger.info(f"write_xlsx_file called with path={path}")
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name
        
        if data and isinstance(data[0], dict):
            # Write headers
            headers = list(data[0].keys())
            ws.append(headers)
            
            # Write data rows
            for row_data in data:
                ws.append([row_data.get(h) for h in headers])
        else:
            ws.append(["No data"])
        
        # Ensure directory exists
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        wb.save(path)
        wb.close()
        return f"File saved to {path}"
    except Exception as e:
        return f"Error writing Excel file: {str(e)}"


def get_sheet_names(path: str) -> list:
    """
    List all sheet names in an Excel workbook.
    
    Args:
        path (str): Path to the .xlsx file
        
    Returns:
        list: List of sheet name strings
        
    Example:
        >>> get_sheet_names("report.xlsx")
        ['Summary', 'Data', 'Charts']
        
    Keywords: sheets, tabs, list, workbook
    """
    logger.info(f"get_sheet_names called with path={path}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        wb = load_workbook(filename=path, read_only=True)
        names = wb.sheetnames
        wb.close()
        return names
    except Exception as e:
        return f"Error getting sheet names: {str(e)}"


def get_cell_value(path: str, sheet_name: str, cell: str) -> Any:
    """
    Get the value of a specific cell in an Excel file.
    
    Args:
        path (str): Path to the .xlsx file
        sheet_name (str): Name of the sheet
        cell (str): Cell reference (e.g., "A1", "B3")
        
    Returns:
        Any: The cell value, or error message
        
    Example:
        >>> get_cell_value("data.xlsx", "Sheet1", "A1")
        'Header Name'
        
    Keywords: cell, value, read, specific
    """
    logger.info(f"get_cell_value called with path={path}, sheet={sheet_name}, cell={cell}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        wb = load_workbook(filename=path, data_only=True)
        ws = wb[sheet_name]
        value = ws[cell].value
        wb.close()
        return value
    except Exception as e:
        return f"Error getting cell value: {str(e)}"


def set_cell_value(path: str, sheet_name: str, cell: str, value: Any) -> str:
    """
    Set the value of a specific cell and save the file.
    
    Args:
        path (str): Path to the .xlsx file
        sheet_name (str): Name of the sheet
        cell (str): Cell reference (e.g., "A1", "B3")
        value (Any): Value to set in the cell
        
    Returns:
        str: Success message or error description
        
    Example:
        >>> set_cell_value("data.xlsx", "Sheet1", "A1", "New Value")
        'Cell A1 updated successfully'
        
    Keywords: set, update, modify, write, cell
    """
    logger.info(f"set_cell_value called with path={path}, sheet={sheet_name}, cell={cell}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        wb = load_workbook(filename=path)
        ws = wb[sheet_name]
        ws[cell] = value
        wb.save(path)
        wb.close()
        return f"Cell {cell} updated successfully"
    except Exception as e:
        return f"Error setting cell value: {str(e)}"


def get_dimensions(path: str, sheet_name: str = None) -> str:
    """
    Get the used range dimensions of a sheet.
    
    Args:
        path (str): Path to the .xlsx file
        sheet_name (str, optional): Sheet name. Defaults to active sheet.
        
    Returns:
        str: Dimension string (e.g., "A1:D10")
        
    Example:
        >>> get_dimensions("data.xlsx")
        'A1:D50'
        
    Keywords: dimensions, range, size, extent
    """
    logger.info(f"get_dimensions called with path={path}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        wb = load_workbook(filename=path, read_only=True)
        ws = wb[sheet_name] if sheet_name else wb.active
        dims = ws.dimensions
        wb.close()
        return dims
    except Exception as e:
        return f"Error getting dimensions: {str(e)}"


def copy_sheet(source_path: str, dest_path: str, sheet_name: str = None) -> str:
    """
    Copy a sheet from one workbook to a new file.
    
    Args:
        source_path (str): Path to the source .xlsx file
        dest_path (str): Path where the new file should be saved
        sheet_name (str, optional): Sheet to copy. Defaults to active sheet.
        
    Returns:
        str: Success message or error description
        
    Keywords: copy, duplicate, clone, sheet
    """
    logger.info(f"copy_sheet called with source={source_path}, dest={dest_path}")
    try:
        if not os.path.exists(source_path):
            return f"Error: Source file not found: {source_path}"
        
        wb = load_workbook(filename=source_path, data_only=True)
        ws = wb[sheet_name] if sheet_name else wb.active
        
        new_wb = Workbook()
        new_ws = new_wb.active
        new_ws.title = ws.title
        
        for row in ws.iter_rows(values_only=True):
            new_ws.append(row)
        
        dir_path = os.path.dirname(dest_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        new_wb.save(dest_path)
        wb.close()
        new_wb.close()
        return f"Sheet copied to {dest_path}"
    except Exception as e:
        return f"Error copying sheet: {str(e)}"


def apply_style(path: str, sheet_name: str, cell_range: str, style: dict) -> str:
    """
    Apply formatting style to a cell range in an Excel file.
    
    Args:
        path (str): Path to the .xlsx file
        sheet_name (str): Name of the sheet
        cell_range (str): Range string (e.g., "A1:C1", "B2")
        style (dict): Style dictionary with optional keys:
            - font_color: Hex color code (e.g., "FF0000")
            - font_bold: Boolean
            - alignment: "left", "center", or "right"
            - border: Boolean
            - fill_color: Hex background color code
        
    Returns:
        str: Success message or error description
        
    Example:
        >>> apply_style("report.xlsx", "Summary", "A1:D1", {"font_bold": True, "fill_color": "FFFF00"})
        'Style applied to A1:D1'
        
    Keywords: style, format, bold, color, alignment, border, fill
    """
    logger.info(f"apply_style called with path={path}, range={cell_range}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        wb = load_workbook(filename=path)
        ws = wb[sheet_name]
        
        for row in ws[cell_range]:
            for cell in row:
                if style.get("font_color"):
                    cell.font = Font(color=style["font_color"])
                if style.get("font_bold"):
                    cell.font = Font(bold=True)
                if style.get("alignment"):
                    cell.alignment = Alignment(horizontal=style["alignment"])
                if style.get("border"):
                    cell.border = Border(
                        left=Side(), right=Side(), top=Side(), bottom=Side()
                    )
                if style.get("fill_color"):
                    cell.fill = PatternFill("solid", fgColor=style["fill_color"])
        
        wb.save(path)
        wb.close()
        return f"Style applied to {cell_range}"
    except Exception as e:
        return f"Error applying style: {str(e)}"


def create_empty_workbook(path: str, sheet_names: list = None) -> str:
    """
    Create a new empty Excel workbook with optional named sheets.
    
    Args:
        path (str): Path where the new .xlsx file should be saved
        sheet_names (list, optional): List of sheet names to create.
        
    Returns:
        str: Success message or error description
        
    Keywords: create, new, empty, workbook, sheets
    """
    logger.info(f"create_empty_workbook called with path={path}")
    try:
        wb = Workbook()
        
        # Remove default sheet if custom names provided
        if sheet_names:
            default = wb.active
            wb.remove(default)
            for name in sheet_names:
                wb.create_sheet(title=name)
        elif not sheet_names:
            pass  # Keep default sheet
        
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        wb.save(path)
        wb.close()
        return f"Empty workbook created at {path}"
    except Exception as e:
        return f"Error creating workbook: {str(e)}"


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def get_all_tools() -> list[FunctionTool]:
    """
    Return all Excel/XLSX tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Excel FunctionTool objects
    """
    logger.info("get_all_tools called for Excel/XLSX toolkit")
    return [
        FunctionTool.from_defaults(
            fn=read_xlsx_file,
            description="Read data from an Excel .xlsx file. Returns list of dicts with column headers as keys. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=write_xlsx_file,
            description="Write data to a new Excel .xlsx file. Accepts list of dictionaries. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=get_sheet_names,
            description="List all sheet names in an Excel workbook. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=get_cell_value,
            description="Get the value of a specific cell (e.g., A1) in an Excel file. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=set_cell_value,
            description="Set the value of a specific cell and save the file. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=get_dimensions,
            description="Get the used range dimensions of an Excel sheet. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=copy_sheet,
            description="Copy a sheet from one workbook to a new file. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=apply_style,
            description="Apply formatting style (bold, color, alignment, border, fill) to a cell range. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=create_empty_workbook,
            description="Create a new empty Excel workbook with optional named sheets. Category: Data / Excel",
        ),
    ]
