"""
Data Analysis Toolkit - Pandas-powered data operations and analysis.

This module provides high-level data analysis functions using pandas,
enabling filtering, aggregation, pivot tables, statistical summaries,
and more on tabular data from Excel and CSV files.

Category: Data / Analysis
Retriever Keywords: pandas, dataframe, analysis, statistics, aggregate, pivot, filter

Prerequisites:
    - pandas>=2.0.0 must be installed
    - openpyxl>=3.1.5 must be installed (for Excel I/O)
"""
import os
import pandas as pd
import numpy as np
import json
import logging
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


def read_excel_to_df(path: str, sheet_name: str = None) -> list:
    """
    Load an Excel file and return data as a list of dictionaries.
    
    Args:
        path (str): Path to the .xlsx file
        sheet_name (str, optional): Name or index of the sheet. Defaults to first sheet.
        
    Returns:
        list: List of dictionaries where each dict represents a row
        
    Example:
        >>> read_excel_to_df("sales.xlsx", "Q1")
        [{'Region': 'North', 'Revenue': 1000}, ...]
        
    Keywords: load, import, dataframe, excel
    """
    logger.info(f"read_excel_to_df called with path={path}, sheet={sheet_name}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        df = pd.read_excel(path, sheet_name=sheet_name)
        return df.to_dict(orient="records")
    except Exception as e:
        return f"Error reading Excel file: {str(e)}"


def read_csv_to_df(path: str) -> list:
    """
    Load a CSV file and return data as a list of dictionaries.
    
    Args:
        path (str): Path to the CSV file
        
    Returns:
        list: List of dictionaries where each dict represents a row
        
    Keywords: load, import, csv, dataframe
    """
    logger.info(f"read_csv_to_df called with path={path}")
    try:
        if not os.path.exists(path):
            return f"Error: File not found: {path}"
        
        df = pd.read_csv(path)
        return df.to_dict(orient="records")
    except Exception as e:
        return f"Error reading CSV file: {str(e)}"


def describe_data(df_or_path: str, sheet_name: str = None) -> dict:
    """
    Generate descriptive statistics for numeric columns.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        dict: Summary statistics for each numeric column
        
    Example:
        >>> describe_data("sales.xlsx")
        {'Revenue': {'count': 100, 'mean': 500.5, ...}, ...}
        
    Keywords: summary, statistics, describe, stats, overview
    """
    logger.info(f"describe_data called with path={df_or_path}")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        desc = df.describe()
        return desc.to_dict()
    except Exception as e:
        return f"Error describing data: {str(e)}"


def filter_data(df_or_path: str, column: str, condition: str, sheet_name: str = None) -> list:
    """
    Filter rows based on a condition.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        column (str): Column name to filter on
        condition (str): Condition string, e.g., "> 100", "== 'Active'", "!= None"
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        list: List of dictionaries matching the filter condition
        
    Example:
        >>> filter_data("sales.xlsx", "Revenue", "> 1000")
        
    Keywords: filter, query, condition, where, subset
    """
    logger.info(f"filter_data called with column={column}, condition={condition}")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        
        # Build query string safely
        query_str = f"{column} {condition}"
        result = df.query(query_str)
        return result.to_dict(orient="records")
    except Exception as e:
        return f"Error filtering data: {str(e)}"


def aggregate_data(df_or_path: str, group_col: str, agg_col: str, agg_func: str = "sum", sheet_name: str = None) -> list:
    """
    Group data and apply an aggregation function.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        group_col (str): Column to group by
        agg_col (str): Column to aggregate
        agg_func (str): Aggregation function: "sum", "mean", "count", "min", "max", "std"
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        list: List of dictionaries with aggregated results
        
    Example:
        >>> aggregate_data("sales.xlsx", "Region", "Revenue", "sum")
        [{'Region': 'North', 'Revenue': 50000}, ...]
        
    Keywords: groupby, aggregate, sum, mean, count, average, total
    """
    logger.info(f"aggregate_data called with group={group_col}, agg={agg_col}, func={agg_func}")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        result = df.groupby(group_col)[agg_col].agg(agg_func).reset_index()
        return result.to_dict(orient="records")
    except Exception as e:
        return f"Error aggregating data: {str(e)}"


def pivot_table(df_or_path: str, index: str, columns: str = None, values: str = None, aggfunc: str = "sum", sheet_name: str = None) -> dict:
    """
    Create a pivot table from the data.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        index (str): Column to use as row index
        columns (str, optional): Column to use as columns
        values (str, optional): Column to aggregate
        aggfunc (str): Aggregation function
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        dict: Pivot table result as nested dictionary
        
    Keywords: pivot, table, cross-tab, crosstab, summary
    """
    logger.info(f"pivot_table called with index={index}, values={values}")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        
        if values is None:
            # Infer numeric columns
            values = [col for col in df.select_dtypes(include=[np.number]).columns]
        
        result = pd.pivot_table(df, index=index, columns=columns, values=values, aggfunc=aggfunc)
        return result.to_dict()
    except Exception as e:
        return f"Error creating pivot table: {str(e)}"


def detect_missing_data(df_or_path: str, sheet_name: str = None) -> dict:
    """
    Detect and report missing/null values in the data.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        dict: Dictionary with missing counts and percentages per column
        
    Example:
        >>> detect_missing_data("data.xlsx")
        {'missing_counts': {'Column1': 5, 'Column2': 0}, 'missing_percentages': {...}, 'total_rows': 100}
        
    Keywords: missing, null, nan, empty, incomplete
    """
    logger.info("detect_missing_data called")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        
        missing = df.isnull().sum().to_dict()
        # Also compute percentage
        total = len(df)
        missing_pct = {col: f"{(count/total*100):.2f}%" for col, count in missing.items()}
        
        return {
            "missing_counts": missing,
            "missing_percentages": missing_pct,
            "total_rows": total
        }
    except Exception as e:
        return f"Error detecting missing data: {str(e)}"


def correlation_matrix(df_or_path: str, sheet_name: str = None) -> dict:
    """
    Compute the correlation matrix for numeric columns.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        dict: Correlation matrix as nested dictionary
        
    Keywords: correlation, matrix, relationship, pearson
    """
    logger.info("correlation_matrix called")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        return df.corr(numeric_only=True).to_dict()
    except Exception as e:
        return f"Error computing correlation: {str(e)}"


def export_dataframe(path: str, data: list, sheet_name: str = "Sheet1", file_type: str = "xlsx") -> str:
    """
    Export a list of dictionaries to an Excel or CSV file.
    
    Args:
        path (str): Output file path
        data (list): List of dictionaries to export
        sheet_name (str): Sheet name for Excel files (default: "Sheet1")
        file_type (str): "xlsx" or "csv" (default: "xlsx")
        
    Returns:
        str: Success message or error description
        
    Keywords: export, save, write, output
    """
    logger.info(f"export_dataframe called with path={path}, type={file_type}")
    try:
        # Ensure directory exists
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        df = pd.DataFrame(data)
        
        if file_type.lower() == "xlsx":
            df.to_excel(path, sheet_name=sheet_name, index=False)
        elif file_type.lower() == "csv":
            df.to_csv(path, index=False)
        else:
            return f"Error: Unsupported file type '{file_type}'. Use 'xlsx' or 'csv'."
        
        return f"Data exported to {path}"
    except Exception as e:
        return f"Error exporting data: {str(e)}"


def get_unique_values(df_or_path: str, column: str, sheet_name: str = None) -> list:
    """
    Get unique values in a column.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        column (str): Column name
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        list: List of unique values
        
    Keywords: unique, distinct, values, list, categories
    """
    logger.info(f"get_unique_values called with column={column}")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        return df[column].dropna().unique().tolist()
    except Exception as e:
        return f"Error getting unique values: {str(e)}"


def sort_data(df_or_path: str, by: str, ascending: bool = True, sheet_name: str = None) -> list:
    """
    Sort data by a column and return as list of dictionaries.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        by (str): Column to sort by
        ascending (bool): Sort order (default: True for ascending)
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        list: List of dictionaries sorted by the specified column
        
    Keywords: sort, order, arrange
    """
    logger.info(f"sort_data called with by={by}, ascending={ascending}")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        result = df.sort_values(by=by, ascending=ascending).reset_index(drop=True)
        return result.to_dict(orient="records")
    except Exception as e:
        return f"Error sorting data: {str(e)}"


def compute_statistics(df_or_path: str, column: str, sheet_name: str = None) -> dict:
    """
    Compute detailed statistics for a single column.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        column (str): Column name
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        dict: Dictionary with statistical measures
        
    Keywords: statistics, mean, median, std, variance, quartile
    """
    logger.info(f"compute_statistics called with column={column}")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        series = df[column].dropna()
        
        return {
            "mean": float(series.mean()),
            "median": float(series.median()),
            "std": float(series.std()),
            "min": float(series.min()),
            "max": float(series.max()),
            "count": int(series.count()),
            "25%": float(series.quantile(0.25)),
            "75%": float(series.quantile(0.75)),
        }
    except Exception as e:
        return f"Error computing statistics: {str(e)}"


def get_dataframe_info(df_or_path: str, sheet_name: str = None) -> dict:
    """
    Get information about the DataFrame including shape, columns, and data types.
    
    Args:
        df_or_path (str): Path to the .xlsx file
        sheet_name (str, optional): Sheet name if path is provided
        
    Returns:
        dict: Dictionary with DataFrame information
        
    Keywords: info, shape, columns, types, metadata
    """
    logger.info("get_dataframe_info called")
    try:
        df = pd.read_excel(df_or_path, sheet_name=sheet_name)
        
        return {
            "shape": [len(df), len(df.columns)],
            "columns": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "memory_usage_bytes": int(df.memory_usage(deep=True).sum()),
        }
    except Exception as e:
        return f"Error getting DataFrame info: {str(e)}"


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def get_all_tools() -> list[FunctionTool]:
    """
    Return all data analysis tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of data analysis FunctionTool objects
    """
    logger.info("get_all_tools called for data analysis toolkit")
    return [
        FunctionTool.from_defaults(
            fn=read_excel_to_df,
            description="Load an Excel file and return data as a list of dictionaries. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=read_csv_to_df,
            description="Load a CSV file and return data as a list of dictionaries. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=describe_data,
            description="Generate descriptive statistics summary for all numeric columns. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=filter_data,
            description="Filter rows based on a condition (e.g., '> 100'). Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=aggregate_data,
            description="Group data and apply aggregation (sum, mean, count, etc.). Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=pivot_table,
            description="Create a pivot table from tabular data. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=detect_missing_data,
            description="Detect and report missing/null values in the data. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=correlation_matrix,
            description="Compute correlation matrix for numeric columns. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=export_dataframe,
            description="Export a list of dictionaries to Excel or CSV file. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=get_unique_values,
            description="Get unique/distinct values in a column. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=sort_data,
            description="Sort data by a specified column. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=compute_statistics,
            description="Compute detailed statistics (mean, median, std, etc.) for a single column. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=get_dataframe_info,
            description="Get DataFrame information including shape, columns, and data types. Category: Data / Analysis",
        ),
    ]
