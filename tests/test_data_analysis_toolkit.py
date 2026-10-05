"""
Unit tests for agent_data_analysis_toolkit.

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
import os
import sys
from unittest.mock import patch, MagicMock

# Add the parent directory to the path so we can import agent_data_analysis_toolkit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_data_analysis_toolkit import (
    read_excel_to_df,
    read_csv_to_df,
    describe_data,
    filter_data,
    aggregate_data,
    pivot_table,
    detect_missing_data,
    correlation_matrix,
    export_dataframe,
    get_unique_values,
    sort_data,
    compute_statistics,
    get_dataframe_info,
    get_all_tools,
)


class TestReadExcelToDf(unittest.TestCase):
    """Tests for read_excel_to_df function."""
    
    def test_read_excel_file_not_found(self):
        """Test reading a non-existent Excel file returns error."""
        result = read_excel_to_df("/nonexistent/path/file.xlsx")
        self.assertIn("Error: File not found", result)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    @patch('os.path.exists')
    def test_read_excel_success(self, mock_exists, mock_read_excel):
        """Test successful Excel file reading."""
        mock_exists.return_value = True
        
        # Mock DataFrame.to_dict to return records
        mock_df = MagicMock()
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
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    @patch('os.path.exists')
    def test_read_excel_with_sheet_name(self, mock_exists, mock_read_excel):
        """Test reading a specific sheet by name."""
        mock_exists.return_value = True
        mock_df = MagicMock()
        mock_df.to_dict.return_value = [{'Col': 'Value'}]
        mock_read_excel.return_value = mock_df
        
        read_excel_to_df("sales.xlsx", sheet_name="Q1")
        mock_read_excel.assert_called_with("sales.xlsx", sheet_name="Q1")
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    @patch('os.path.exists')
    def test_read_excel_handles_exception(self, mock_exists, mock_read_excel):
        """Test that exceptions are caught."""
        mock_exists.return_value = True
        mock_read_excel.side_effect = Exception("Invalid file format")
        
        result = read_excel_to_df("broken.xlsx")
        self.assertIn("Error reading Excel file", result)


class TestReadCsvToDf(unittest.TestCase):
    """Tests for read_csv_to_df function."""
    
    def test_read_csv_file_not_found(self):
        """Test reading a non-existent CSV file returns error."""
        result = read_csv_to_df("/nonexistent/data.csv")
        self.assertIn("Error: File not found", result)
    
    @patch('agent_data_analysis_toolkit.pd.read_csv')
    @patch('os.path.exists')
    def test_read_csv_success(self, mock_exists, mock_read_csv):
        """Test successful CSV file reading."""
        mock_exists.return_value = True
        mock_df = MagicMock()
        mock_df.to_dict.return_value = [{'Name': 'Alice', 'Score': 95}]
        mock_read_csv.return_value = mock_df
        
        result = read_csv_to_df("data.csv")
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]['Name'], 'Alice')
        mock_read_csv.assert_called_with("data.csv")
    
    @patch('agent_data_analysis_toolkit.pd.read_csv')
    @patch('os.path.exists')
    def test_read_csv_handles_exception(self, mock_exists, mock_read_csv):
        """Test that CSV read exceptions are caught."""
        mock_exists.return_value = True
        mock_read_csv.side_effect = Exception("Permission denied")
        
        result = read_csv_to_df("data.csv")
        self.assertIn("Error reading CSV file", result)


class TestDescribeData(unittest.TestCase):
    """Tests for describe_data function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_describe_data_success(self, mock_read_excel):
        """Test successful descriptive statistics generation."""
        mock_df = MagicMock()
        mock_df.describe.return_value.to_dict.return_value = {
            'Revenue': {'count': 100.0, 'mean': 5000.0, 'std': 1000.0}
        }
        mock_read_excel.return_value = mock_df
        
        result = describe_data("sales.xlsx")
        self.assertIsInstance(result, dict)
        self.assertIn('Revenue', result)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_describe_data_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("No numeric columns")
        
        result = describe_data("non_numeric.xlsx")
        self.assertIn("Error describing data", result)


class TestFilterData(unittest.TestCase):
    """Tests for filter_data function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_filter_data_success(self, mock_read_excel):
        """Test successful data filtering."""
        mock_df = MagicMock()
        mock_df.query.return_value.to_dict.return_value = [
            {'Product': 'A', 'Price': 150},
        ]
        mock_read_excel.return_value = mock_df
        
        result = filter_data("products.xlsx", "Price", "> 100")
        self.assertIsInstance(result, list)
        mock_df.query.assert_called_with("Price > 100")
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_filter_data_exception(self, mock_read_excel):
        """Test that filter exceptions are caught."""
        mock_read_excel.side_effect = Exception("Column not found")
        
        result = filter_data("data.xlsx", "MissingCol", "== 5")
        self.assertIn("Error filtering data", result)


class TestAggregateData(unittest.TestCase):
    """Tests for aggregate_data function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_aggregate_data_success(self, mock_read_excel):
        """Test successful data aggregation."""
        mock_df = MagicMock()
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
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_aggregate_with_different_functions(self, mock_read_excel):
        """Test aggregation with different functions."""
        mock_df = MagicMock()
        mock_grouped = mock_df.groupby.return_value.__getitem__.return_value
        mock_grouped.agg.return_value.reset_index.return_value.to_dict.return_value = [{'Region': 'A'}]
        mock_read_excel.return_value = mock_df
        
        for func in ["mean", "count", "min", "max", "std"]:
            aggregate_data("data.xlsx", "Region", "Value", func)
            mock_grouped.agg.assert_called_with(func)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_aggregate_exception(self, mock_read_excel):
        """Test that aggregation exceptions are caught."""
        mock_read_excel.side_effect = Exception("Invalid column")
        
        result = aggregate_data("data.xlsx", "Bad", "Col", "sum")
        self.assertIn("Error aggregating data", result)


class TestPivotTable(unittest.TestCase):
    """Tests for pivot_table function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    @patch('agent_data_analysis_toolkit.pd.pivot_table')
    def test_pivot_table_success(self, mock_pivot, mock_read_excel):
        """Test successful pivot table creation."""
        mock_df = MagicMock()
        mock_df.select_dtypes.return_value.columns = ['Revenue', 'Profit']
        mock_read_excel.return_value = mock_df
        mock_pivot.return_value.to_dict.return_value = {'A': {'B': 100}}
        mock_pivot.return_value.columns = ['Revenue']
        
        result = pivot_table("sales.xlsx", "Region", values="Revenue")
        self.assertIsInstance(result, dict)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_pivot_table_exception(self, mock_read_excel):
        """Test that pivot table exceptions are caught."""
        mock_read_excel.side_effect = Exception("Invalid index")
        
        result = pivot_table("data.xlsx", "Bad", values="Value")
        self.assertIn("Error creating pivot table", result)


class TestDetectMissingData(unittest.TestCase):
    """Tests for detect_missing_data function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_detect_missing_data_success(self, mock_read_excel):
        """Test successful missing data detection."""
        mock_df = MagicMock()
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
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_detect_missing_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("File corrupted")
        
        result = detect_missing_data("bad.xlsx")
        self.assertIn("Error detecting missing data", result)


class TestCorrelationMatrix(unittest.TestCase):
    """Tests for correlation_matrix function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_correlation_matrix_success(self, mock_read_excel):
        """Test successful correlation matrix computation."""
        mock_df = MagicMock()
        mock_df.corr.return_value.to_dict.return_value = {
            'A': {'A': 1.0, 'B': 0.5},
            'B': {'A': 0.5, 'B': 1.0},
        }
        mock_read_excel.return_value = mock_df
        
        result = correlation_matrix("data.xlsx")
        self.assertIsInstance(result, dict)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_correlation_exception(self, mock_read_excel):
        """Test that correlation exceptions are caught."""
        mock_read_excel.side_effect = Exception("No numeric data")
        
        result = correlation_matrix("text.xlsx")
        self.assertIn("Error computing correlation", result)


class TestExportDataframe(unittest.TestCase):
    """Tests for export_dataframe function."""
    
    @patch('agent_data_analysis_toolkit.pd.DataFrame')
    @patch('os.makedirs')
    def test_export_xlsx_success(self, mock_makedirs, mock_df):
        """Test successful export to Excel."""
        mock_df_instance = MagicMock()
        mock_df.return_value = mock_df_instance
        
        result = export_dataframe("output.xlsx", [{'A': 1}], file_type="xlsx")
        self.assertIn("Data exported to", result)
        mock_df_instance.to_excel.assert_called()
    
    @patch('agent_data_analysis_toolkit.pd.DataFrame')
    @patch('os.makedirs')
    def test_export_csv_success(self, mock_makedirs, mock_df):
        """Test successful export to CSV."""
        mock_df_instance = MagicMock()
        mock_df.return_value = mock_df_instance
        
        result = export_dataframe("output.csv", [{'A': 1}], file_type="csv")
        self.assertIn("Data exported to", result)
        mock_df_instance.to_csv.assert_called()
    
    @patch('agent_data_analysis_toolkit.pd.DataFrame')
    def test_export_unsupported_type(self, mock_df):
        """Test error for unsupported file type."""
        mock_df.return_value = MagicMock()
        
        result = export_dataframe("output.txt", [{'A': 1}], file_type="txt")
        self.assertIn("Unsupported file type", result)
    
    @patch('agent_data_analysis_toolkit.pd.DataFrame')
    def test_export_exception(self, mock_df):
        """Test that export exceptions are caught."""
        mock_df.side_effect = Exception("Disk full")
        
        result = export_dataframe("out.xlsx", [{'A': 1}])
        self.assertIn("Error exporting data", result)


class TestGetUniqueValues(unittest.TestCase):
    """Tests for get_unique_values function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_get_unique_values_success(self, mock_read_excel):
        """Test successful unique values retrieval."""
        mock_df = MagicMock()
        mock_df.__getitem__.return_value.dropna.return_value.unique.return_value.tolist.return_value = [
            'North', 'South', 'East', 'West'
        ]
        mock_read_excel.return_value = mock_df
        
        result = get_unique_values("sales.xlsx", "Region")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 4)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_get_unique_exception(self, mock_read_excel):
        """Test that exceptions are caught."""
        mock_read_excel.side_effect = Exception("Column missing")
        
        result = get_unique_values("data.xlsx", "Bad")
        self.assertIn("Error getting unique values", result)


class TestSortData(unittest.TestCase):
    """Tests for sort_data function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_sort_data_success(self, mock_read_excel):
        """Test successful data sorting."""
        mock_df = MagicMock()
        mock_df.sort_values.return_value.reset_index.return_value.to_dict.return_value = [
            {'Name': 'A', 'Value': 1},
            {'Name': 'B', 'Value': 2},
        ]
        mock_read_excel.return_value = mock_df
        
        result = sort_data("data.xlsx", "Value", ascending=True)
        self.assertIsInstance(result, list)
        mock_df.sort_values.assert_called_with(by="Value", ascending=True)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_sort_descending(self, mock_read_excel):
        """Test sorting in descending order."""
        mock_df = MagicMock()
        mock_df.sort_values.return_value.reset_index.return_value.to_dict.return_value = [{'A': 1}]
        mock_read_excel.return_value = mock_df
        
        sort_data("data.xlsx", "Col", ascending=False)
        mock_df.sort_values.assert_called_with(by="Col", ascending=False)
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_sort_exception(self, mock_read_excel):
        """Test that sort exceptions are caught."""
        mock_read_excel.side_effect = Exception("Invalid column")
        
        result = sort_data("data.xlsx", "Bad")
        self.assertIn("Error sorting data", result)


class TestComputeStatistics(unittest.TestCase):
    """Tests for compute_statistics function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_compute_statistics_success(self, mock_read_excel):
        """Test successful statistics computation."""
        mock_df = MagicMock()
        mock_series = MagicMock()
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
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_compute_statistics_exception(self, mock_read_excel):
        """Test that statistics exceptions are caught."""
        mock_read_excel.side_effect = Exception("Column not numeric")
        
        result = compute_statistics("data.xlsx", "TextCol")
        self.assertIn("Error computing statistics", result)


class TestGetDataframeInfo(unittest.TestCase):
    """Tests for get_dataframe_info function."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_get_dataframe_info_success(self, mock_read_excel):
        """Test successful DataFrame info retrieval."""
        mock_df = MagicMock()
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
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_get_dataframe_info_exception(self, mock_read_excel):
        """Test that info exceptions are caught."""
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


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and special scenarios."""
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    @patch('os.path.exists')
    def test_empty_dataframe_operations(self, mock_exists, mock_read_excel):
        """Test operations on empty data."""
        mock_exists.return_value = True
        mock_df = MagicMock()
        mock_df.to_dict.return_value = []
        mock_read_excel.return_value = mock_df
        
        result = read_excel_to_df("empty.xlsx")
        self.assertEqual(result, [])
    
    @patch('agent_data_analysis_toolkit.pd.read_excel')
    def test_filter_with_string_condition(self, mock_read_excel):
        """Test filtering with string comparison."""
        mock_df = MagicMock()
        mock_df.query.return_value.to_dict.return_value = [{'Status': 'Active'}]
        mock_read_excel.return_value = mock_df
        
        result = filter_data("users.xlsx", "Status", "== 'Active'")
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
