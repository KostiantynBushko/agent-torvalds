"""
Unit tests for the data analysis toolkit's library half.

The suite moved here together with the toolkit: it used to live at
``tests/test_data_analysis_toolkit.py`` and import the single module
``agent_data_analysis_toolkit`` from the project root.  It now imports
the library half of the package through a **relative** import, so it
belongs to the package it tests.

Tests all data analysis operations including:
- Reading Excel/CSV files into DataFrames
- Descriptive statistics and summaries
- Filtering and querying data
- Aggregation (groupby operations)
- Pivot tables
- Missing data detection
- Correlation analysis
- Data export
- Unique values, sorting, statistics
- DataFrame info/metadata
- Tool registry (get_all_tools)

Uses unittest.mock to avoid creating actual files during testing.
"""

import unittest
import unittest.mock as mock

# The operations are imported with a *relative* import - the only form
# that resolves inside the hyphenated package directory.  The module
# itself is imported as well, because the tests patch the pandas entry
# points on it.
from .. import operations
from ..operations import (
    aggregate_data,
    compute_statistics,
    correlation_matrix,
    describe_data,
    detect_missing_data,
    export_dataframe,
    filter_data,
    get_dataframe_info,
    get_unique_values,
    pivot_table,
    read_csv_to_df,
    read_excel_to_df,
    sort_data,
)

# ``get_all_tools`` is the one name that did **not** move into the
# library half: it is the adapter's, and the adapter is the one module
# of the toolkit that knows about LlamaIndex.
from ..agent_data_analysis_toolkit import get_all_tools


class TestReadExcelToDf(unittest.TestCase):
    """Tests for read_excel_to_df function."""

    def test_read_excel_file_not_found(self):
        """Test reading a non-existent Excel file returns error."""
        result = read_excel_to_df("/nonexistent/path/file.xlsx")
        self.assertIn("Error: File not found", result)

    @mock.patch.object(operations.pd, "read_excel")
    @mock.patch.object(operations.os.path, "exists", return_value=True)
    def test_read_excel_success(self, mock_exists, mock_read_excel):
        """Test successful Excel file reading."""
        # Mock DataFrame.to_dict to return records
        mock_df = mock.MagicMock()
        mock_df.to_dict.return_value = [
            {'Region': 'North', 'Revenue': 1000},
            {'Region': 'South', 'Revenue': 1500},
        ]
        mock_read_excel.return_value = mock_df

        result = read_excel_to_df("sales.xlsx")

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['Region'], 'North')
        mock_read_excel.assert_called_with("sales.xlsx", sheet_name=None)

    @mock.patch.object(operations.pd, "read_excel")
    @mock.patch.object(operations.os.path, "exists", return_value=True)
    def test_read_excel_with_sheet_name(self, mock_exists, mock_read_excel):
        """Test reading a specific sheet by name."""
        mock_df = mock.MagicMock()
        mock_df.to_dict.return_value = [{'Col': 'Value'}]
        mock_read_excel.return_value = mock_df

        read_excel_to_df("sales.xlsx", sheet_name="Q1")
        mock_read_excel.assert_called_with("sales.xlsx", sheet_name="Q1")

    @mock.patch.object(operations.pd, "read_excel")
    @mock.patch.object(operations.os.path, "exists", return_value=True)
    def test_read_excel_handles_exception(self, mock_exists, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("Invalid file format")

        result = read_excel_to_df("broken.xlsx")
        self.assertIn("Error reading Excel file", result)


class TestReadCsvToDf(unittest.TestCase):
    """Tests for read_csv_to_df function."""

    def test_read_csv_file_not_found(self):
        """Test reading a non-existent CSV file returns error."""
        result = read_csv_to_df("/nonexistent/data.csv")
        self.assertIn("Error: File not found", result)

    @mock.patch.object(operations.pd, "read_csv")
    @mock.patch.object(operations.os.path, "exists", return_value=True)
    def test_read_csv_success(self, mock_exists, mock_read_csv):
        """Test successful CSV file reading."""
        mock_df = mock.MagicMock()
        mock_df.to_dict.return_value = [{'Name': 'Alice', 'Score': 95}]
        mock_read_csv.return_value = mock_df

        result = read_csv_to_df("data.csv")
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]['Name'], 'Alice')
        mock_read_csv.assert_called_with("data.csv")

    @mock.patch.object(operations.pd, "read_csv")
    @mock.patch.object(operations.os.path, "exists", return_value=True)
    def test_read_csv_handles_exception(self, mock_exists, mock_read_csv):
        """Test that CSV read exceptions are caught."""
        mock_read_csv.side_effect = Exception("Permission denied")

        result = read_csv_to_df("data.csv")
        self.assertIn("Error reading CSV file", result)


class TestDescribeData(unittest.TestCase):
    """Tests for describe_data function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_describe_data_success(self, mock_read_excel):
        """Test successful descriptive statistics generation."""
        mock_df = mock.MagicMock()
        mock_df.describe.return_value.to_dict.return_value = {
            'Revenue': {'count': 100.0, 'mean': 5000.0, 'std': 1000.0}
        }
        mock_read_excel.return_value = mock_df

        result = describe_data("sales.xlsx")
        self.assertIsInstance(result, dict)
        self.assertIn('Revenue', result)

    @mock.patch.object(operations.pd, "read_excel")
    def test_describe_data_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("No numeric columns")

        result = describe_data("non_numeric.xlsx")
        self.assertIn("Error describing data", result)


class TestFilterData(unittest.TestCase):
    """Tests for filter_data function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_filter_data_success(self, mock_read_excel):
        """Test successful data filtering."""
        mock_df = mock.MagicMock()
        mock_df.query.return_value.to_dict.return_value = [
            {'Product': 'A', 'Price': 150},
        ]
        mock_read_excel.return_value = mock_df

        result = filter_data("products.xlsx", "Price", "> 100")
        self.assertIsInstance(result, list)
        mock_df.query.assert_called_with("Price > 100")

    @mock.patch.object(operations.pd, "read_excel")
    def test_filter_data_exception(self, mock_read_excel):
        """Test that filter exceptions are caught."""
        mock_read_excel.side_effect = Exception("Column not found")

        result = filter_data("data.xlsx", "MissingCol", "== 5")
        self.assertIn("Error filtering data", result)


class TestAggregateData(unittest.TestCase):
    """Tests for aggregate_data function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_aggregate_data_success(self, mock_read_excel):
        """Test successful data aggregation."""
        mock_df = mock.MagicMock()
        # The code path: df.groupby(group_col)[agg_col].agg(agg_func).reset_index()
        mock_grouped = mock_df.groupby.return_value.__getitem__.return_value
        mock_grouped.agg.return_value.reset_index.return_value.to_dict.return_value = [
            {'Region': 'North', 'Revenue': 50000},
            {'Region': 'South', 'Revenue': 30000},
        ]
        mock_read_excel.return_value = mock_df

        result = aggregate_data("sales.xlsx", "Region", "Revenue", "sum")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    @mock.patch.object(operations.pd, "read_excel")
    def test_aggregate_with_different_functions(self, mock_read_excel):
        """Test aggregation with different functions."""
        mock_df = mock.MagicMock()
        mock_grouped = mock_df.groupby.return_value.__getitem__.return_value
        mock_grouped.agg.return_value.reset_index.return_value.to_dict.return_value = [{'Region': 'A'}]
        mock_read_excel.return_value = mock_df

        for func in ["mean", "count", "min", "max", "std"]:
            aggregate_data("data.xlsx", "Region", "Value", func)
            mock_grouped.agg.assert_called_with(func)

    @mock.patch.object(operations.pd, "read_excel")
    def test_aggregate_exception(self, mock_read_excel):
        """Test that aggregation exceptions are caught."""
        mock_read_excel.side_effect = Exception("Invalid column")

        result = aggregate_data("data.xlsx", "Bad", "Col", "sum")
        self.assertIn("Error aggregating data", result)


class TestPivotTable(unittest.TestCase):
    """Tests for pivot_table function."""

    @mock.patch.object(operations.pd, "pivot_table")
    @mock.patch.object(operations.pd, "read_excel")
    def test_pivot_table_success(self, mock_read_excel, mock_pivot):
        """Test successful pivot table creation."""
        mock_df = mock.MagicMock()
        mock_df.select_dtypes.return_value.columns = ['Revenue', 'Profit']
        mock_read_excel.return_value = mock_df
        mock_pivot.return_value.to_dict.return_value = {'A': {'B': 100}}
        mock_pivot.return_value.columns = ['Revenue']

        result = pivot_table("sales.xlsx", "Region", values="Revenue")
        self.assertIsInstance(result, dict)

    @mock.patch.object(operations.pd, "read_excel")
    def test_pivot_table_exception(self, mock_read_excel):
        """Test that pivot table exceptions are caught."""
        mock_read_excel.side_effect = Exception("Invalid index")

        result = pivot_table("data.xlsx", "Bad", values="Value")
        self.assertIn("Error creating pivot table", result)


class TestDetectMissingData(unittest.TestCase):
    """Tests for detect_missing_data function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_detect_missing_data_success(self, mock_read_excel):
        """Test successful missing data detection."""
        mock_df = mock.MagicMock()
        mock_df.isnull.return_value.sum.return_value.to_dict.return_value = {
            'Name': 0, 'Age': 5, 'Email': 2
        }
        mock_df.__len__.return_value = 100
        mock_read_excel.return_value = mock_df

        result = detect_missing_data("data.xlsx")

        self.assertIsInstance(result, dict)
        self.assertIn('missing_counts', result)
        self.assertIn('missing_percentages', result)
        self.assertIn('total_rows', result)
        self.assertEqual(result['total_rows'], 100)

    @mock.patch.object(operations.pd, "read_excel")
    def test_detect_missing_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("File corrupted")

        result = detect_missing_data("bad.xlsx")
        self.assertIn("Error detecting missing data", result)


class TestCorrelationMatrix(unittest.TestCase):
    """Tests for correlation_matrix function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_correlation_matrix_success(self, mock_read_excel):
        """Test successful correlation matrix computation."""
        mock_df = mock.MagicMock()
        mock_df.corr.return_value.to_dict.return_value = {
            'A': {'A': 1.0, 'B': 0.5},
            'B': {'A': 0.5, 'B': 1.0},
        }
        mock_read_excel.return_value = mock_df

        result = correlation_matrix("data.xlsx")
        self.assertIsInstance(result, dict)

    @mock.patch.object(operations.pd, "read_excel")
    def test_correlation_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("No numeric data")

        result = correlation_matrix("text.xlsx")
        self.assertIn("Error computing correlation", result)


class TestExportDataframe(unittest.TestCase):
    """Tests for export_dataframe function."""

    @mock.patch.object(operations.pd, "DataFrame")
    @mock.patch.object(operations.os, "makedirs")
    def test_export_xlsx_success(self, mock_makedirs, mock_df):
        """Test successful export to Excel."""
        mock_df_instance = mock.MagicMock()
        mock_df.return_value = mock_df_instance

        result = export_dataframe("output.xlsx", [{'A': 1}], file_type="xlsx")
        self.assertIn("Data exported to", result)
        mock_df_instance.to_excel.assert_called()

    @mock.patch.object(operations.pd, "DataFrame")
    @mock.patch.object(operations.os, "makedirs")
    def test_export_csv_success(self, mock_makedirs, mock_df):
        """Test successful export to CSV."""
        mock_df_instance = mock.MagicMock()
        mock_df.return_value = mock_df_instance

        result = export_dataframe("output.csv", [{'A': 1}], file_type="csv")
        self.assertIn("Data exported to", result)
        mock_df_instance.to_csv.assert_called()

    @mock.patch.object(operations.pd, "DataFrame")
    def test_export_unsupported_type(self, mock_df):
        """Test error for unsupported file type."""
        mock_df.return_value = mock.MagicMock()

        result = export_dataframe("output.txt", [{'A': 1}], file_type="txt")
        self.assertIn("Unsupported file type", result)

    @mock.patch.object(operations.pd, "DataFrame")
    def test_export_exception(self, mock_df):
        """Test that export exceptions are caught."""
        mock_df.side_effect = Exception("Disk full")

        result = export_dataframe("out.xlsx", [{'A': 1}])
        self.assertIn("Error exporting data", result)


class TestGetUniqueValues(unittest.TestCase):
    """Tests for get_unique_values function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_get_unique_values_success(self, mock_read_excel):
        """Test successful unique values retrieval."""
        mock_df = mock.MagicMock()
        mock_df.__getitem__.return_value.dropna.return_value.unique.return_value.tolist.return_value = [
            'North', 'South', 'East', 'West'
        ]
        mock_read_excel.return_value = mock_df

        result = get_unique_values("sales.xlsx", "Region")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 4)

    @mock.patch.object(operations.pd, "read_excel")
    def test_get_unique_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("Column missing")

        result = get_unique_values("data.xlsx", "Bad")
        self.assertIn("Error getting unique values", result)


class TestSortData(unittest.TestCase):
    """Tests for sort_data function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_sort_data_success(self, mock_read_excel):
        """Test successful data sorting."""
        mock_df = mock.MagicMock()
        mock_df.sort_values.return_value.reset_index.return_value.to_dict.return_value = [
            {'Name': 'A', 'Value': 1},
            {'Name': 'B', 'Value': 2},
        ]
        mock_read_excel.return_value = mock_df

        result = sort_data("data.xlsx", "Value", ascending=True)
        self.assertIsInstance(result, list)
        mock_df.sort_values.assert_called_with(by="Value", ascending=True)

    @mock.patch.object(operations.pd, "read_excel")
    def test_sort_descending(self, mock_read_excel):
        """Test sorting in descending order."""
        mock_df = mock.MagicMock()
        mock_df.sort_values.return_value.reset_index.return_value.to_dict.return_value = [{'A': 1}]
        mock_read_excel.return_value = mock_df

        sort_data("data.xlsx", "Col", ascending=False)
        mock_df.sort_values.assert_called_with(by="Col", ascending=False)

    @mock.patch.object(operations.pd, "read_excel")
    def test_sort_exception(self, mock_read_excel):
        """Test that sort exceptions are caught."""
        mock_read_excel.side_effect = Exception("Invalid column")

        result = sort_data("data.xlsx", "Bad")
        self.assertIn("Error sorting data", result)


class TestComputeStatistics(unittest.TestCase):
    """Tests for compute_statistics function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_compute_statistics_success(self, mock_read_excel):
        """Test successful statistics computation."""
        mock_df = mock.MagicMock()
        mock_series = mock.MagicMock()
        mock_series.dropna.return_value = mock_series
        mock_series.mean.return_value = 50.0
        mock_series.median.return_value = 48.0
        mock_series.std.return_value = 10.0
        mock_series.min.return_value = 20.0
        mock_series.max.return_value = 100.0
        mock_series.count.return_value = 100
        mock_series.quantile.side_effect = lambda q: 35.0 if q == 0.25 else 65.0
        mock_df.__getitem__.return_value = mock_series
        mock_read_excel.return_value = mock_df

        result = compute_statistics("data.xlsx", "Revenue")

        self.assertIsInstance(result, dict)
        self.assertEqual(result['mean'], 50.0)
        self.assertEqual(result['median'], 48.0)
        self.assertEqual(result['count'], 100)
        self.assertIn('std', result)
        self.assertIn('min', result)
        self.assertIn('max', result)

    @mock.patch.object(operations.pd, "read_excel")
    def test_compute_statistics_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("Column not numeric")

        result = compute_statistics("data.xlsx", "TextCol")
        self.assertIn("Error computing statistics", result)


class TestGetDataframeInfo(unittest.TestCase):
    """Tests for get_dataframe_info function."""

    @mock.patch.object(operations.pd, "read_excel")
    def test_get_dataframe_info_success(self, mock_read_excel):
        """Test successful DataFrame info retrieval."""
        mock_df = mock.MagicMock()
        mock_df.columns.tolist.return_value = ['A', 'B', 'C']
        mock_df.dtypes.items.return_value = [('A', 'int64'), ('B', 'float64')]
        mock_df.memory_usage.return_value.sum.return_value = 1024
        mock_df.__len__.return_value = 50
        mock_read_excel.return_value = mock_df

        result = get_dataframe_info("data.xlsx")

        self.assertIsInstance(result, dict)
        self.assertIn('shape', result)
        self.assertIn('columns', result)
        self.assertIn('dtypes', result)
        self.assertIn('memory_usage_bytes', result)
        self.assertEqual(result['columns'], ['A', 'B', 'C'])

    @mock.patch.object(operations.pd, "read_excel")
    def test_get_dataframe_info_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("Corrupted file")

        result = get_dataframe_info("bad.xlsx")
        self.assertIn("Error getting DataFrame info", result)


class TestGetAllTools(unittest.TestCase):
    """Tests for get_all_tools function."""

    def test_get_all_tools_returns_list(self):
        """Test that get_all_tools returns a list of tools."""
        tools = get_all_tools()
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)

    def test_get_all_tools_count(self):
        """Test that all expected tools are registered."""
        tools = get_all_tools()
        # We expect 13 tools from the data analysis toolkit
        self.assertEqual(len(tools), 13)

    def test_tools_have_descriptions(self):
        """Test that all tools have descriptions."""
        tools = get_all_tools()
        for tool in tools:
            # FunctionTool stores description in metadata
            self.assertIsNotNone(tool.metadata.description)
            self.assertGreater(len(tool.metadata.description), 0)

    def test_tools_include_category(self):
        """Test that tool descriptions include category metadata."""
        tools = get_all_tools()
        for tool in tools:
            self.assertIn("Category:", tool.metadata.description)

    def test_the_tool_names_are_the_operations(self):
        """The 13 tools are the 13 operations, by name.

        The name of a tool is what the model calls, so the set is pinned
        here: a renamed operation is a renamed tool.
        """
        tools = get_all_tools()
        names = [tool.metadata.name for tool in tools]
        self.assertEqual(
            names,
            [
                "read_excel_to_df",
                "read_csv_to_df",
                "describe_data",
                "filter_data",
                "aggregate_data",
                "pivot_table",
                "detect_missing_data",
                "correlation_matrix",
                "export_dataframe",
                "get_unique_values",
                "sort_data",
                "compute_statistics",
                "get_dataframe_info",
            ],
        )

    def test_the_tools_carry_the_analysis_category(self):
        """All 13 tools share the Data / Analysis category.

        The category is what the startup tool selection menu groups by,
        so a tool that lost it would silently drop out of the menu.
        """
        for tool in get_all_tools():
            self.assertIn("Category: Data / Analysis", tool.metadata.description)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and special scenarios."""

    @mock.patch.object(operations.pd, "read_excel")
    @mock.patch.object(operations.os.path, "exists", return_value=True)
    def test_empty_dataframe_operations(self, mock_exists, mock_read_excel):
        """Test operations on empty data."""
        mock_df = mock.MagicMock()
        mock_df.to_dict.return_value = []
        mock_read_excel.return_value = mock_df

        result = read_excel_to_df("empty.xlsx")
        self.assertEqual(result, [])

    @mock.patch.object(operations.pd, "read_excel")
    def test_filter_with_string_condition(self, mock_read_excel):
        """Test filtering with string comparison."""
        mock_df = mock.MagicMock()
        mock_df.query.return_value.to_dict.return_value = [{'Status': 'Active'}]
        mock_read_excel.return_value = mock_df

        result = filter_data("users.xlsx", "Status", "== 'Active'")
        self.assertIsInstance(result, list)


class TestErrorContract(unittest.TestCase):
    """A failure is *reported*, never raised.

    This is the whole point of the toolkit: an agent calls a tool, gets
    a message back and carries on.  Every operation catches its own
    failure and returns an error string, so an operation that lets an
    exception escape would take the agent down with it.
    """

    #: The operations that read a file, and the call that fails.
    _FAILING_CALLS = (
        (read_excel_to_df, ("missing.xlsx",)),
        (read_csv_to_df, ("missing.csv",)),
        (describe_data, ("missing.xlsx",)),
        (filter_data, ("missing.xlsx", "Col", "> 1")),
        (aggregate_data, ("missing.xlsx", "Group", "Value")),
        (pivot_table, ("missing.xlsx", "Index")),
        (detect_missing_data, ("missing.xlsx",)),
        (correlation_matrix, ("missing.xlsx",)),
        (get_unique_values, ("missing.xlsx", "Col")),
        (sort_data, ("missing.xlsx", "Col")),
        (compute_statistics, ("missing.xlsx", "Col")),
        (get_dataframe_info, ("missing.xlsx",)),
    )

    def test_no_operation_raises_when_the_file_is_missing(self):
        """A missing file is reported, not raised."""
        for operation, args in self._FAILING_CALLS:
            with self.subTest(operation=operation.__name__):
                try:
                    result = operation(*args)
                except Exception as exc:  # noqa: BLE001 - that is the failure
                    self.fail(f"{operation.__name__} raised {exc!r}")
                self.assertIsInstance(result, str, f"{operation.__name__} returned no message")
                self.assertTrue(result.startswith("Error"), result)

    def test_export_dataframe_reports_an_unsupported_type(self):
        """An unsupported export format is reported, not raised."""
        result = export_dataframe("out.txt", [{"A": 1}], file_type="txt")
        self.assertIsInstance(result, str)
        self.assertIn("Unsupported file type", result)

    def test_every_error_message_names_the_operation(self):
        """The message says which operation failed.

        The model reads the message, and an agent that cannot tell which
        of the thirteen operations failed has to guess.

        The two loaders are the exception: they look at the file system
        first, so an absent file is reported as "Error: File not found"
        rather than as a failed read.
        """
        expected = {
            read_excel_to_df: "Error: File not found",
            read_csv_to_df: "Error: File not found",
            describe_data: "Error describing data",
            filter_data: "Error filtering data",
            aggregate_data: "Error aggregating data",
            pivot_table: "Error creating pivot table",
            detect_missing_data: "Error detecting missing data",
            correlation_matrix: "Error computing correlation",
            get_unique_values: "Error getting unique values",
            sort_data: "Error sorting data",
            compute_statistics: "Error computing statistics",
            get_dataframe_info: "Error getting DataFrame info",
        }

        for operation, args in self._FAILING_CALLS:
            with self.subTest(operation=operation.__name__):
                result = operation(*args)
                self.assertIn(expected[operation], result)


if __name__ == "__main__":
    unittest.main()
