"""
Unit tests for agent_xlsx_toolkit.

Tests all Excel XLSX operations including:
- Reading/writing Excel files
- Sheet management (list, copy, dimensions)
- Cell operations (get/set values)
- Styling/formatting
- Workbook creation
- Tool registry (get_all_tools)

Uses unittest.mock to avoid creating actual Excel files during testing.
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock, mock_open

# Add the parent directory to the path so we can import agent_xlsx_toolkit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_xlsx_toolkit import (
    read_xlsx_file,
    write_xlsx_file,
    get_sheet_names,
    get_cell_value,
    set_cell_value,
    get_dimensions,
    copy_sheet,
    apply_style,
    create_empty_workbook,
    get_all_tools,
)


class TestReadXlsxFile(unittest.TestCase):
    """Tests for read_xlsx_file function."""
    
    def test_read_xlsx_file_not_found(self):
        """Test reading a non-existent file returns error."""
        result = read_xlsx_file("/nonexistent/path/file.xlsx")
        self.assertIn("Error: File not found", result)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_read_xlsx_file_success(self, mock_exists, mock_load_workbook):
        """Test successful file reading."""
        mock_exists.return_value = True
        
        # Mock workbook and worksheet
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_wb.__getitem__.return_value = mock_ws
        mock_wb.active = mock_ws
        mock_wb.iter_rows.return_value = [
            ('Name', 'Age', 'City'),  # headers
            ('Alice', 30, 'NYC'),
            ('Bob', 25, 'LA'),
        ]
        mock_load_workbook.return_value = mock_wb
        
        # Setup iter_rows on worksheet
        mock_ws.iter_rows.return_value = [
            ('Name', 'Age', 'City'),  # headers
            ('Alice', 30, 'NYC'),
            ('Bob', 25, 'LA'),
        ]
        
        result = read_xlsx_file("test.xlsx")
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['Name'], 'Alice')
        self.assertEqual(result[0]['Age'], 30)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_read_xlsx_with_specific_sheet(self, mock_exists, mock_load_workbook):
        """Test reading a specific sheet by name."""
        mock_exists.return_value = True
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb
        
        result = read_xlsx_file("test.xlsx", sheet_name="Sheet2")
        mock_wb.__getitem__.assert_called_with("Sheet2")


class TestWriteXlsxFile(unittest.TestCase):
    """Tests for write_xlsx_file function."""
    
    @patch('agent_xlsx_toolkit.Workbook')
    def test_write_xlsx_file_success(self, mock_workbook):
        """Test successful file writing."""
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws
        
        data = [{'Name': 'Alice', 'Age': 30}, {'Name': 'Bob', 'Age': 25}]
        result = write_xlsx_file("output.xlsx", data)
        
        self.assertIn("File saved to", result)
        mock_ws.append.assert_called()
    
    @patch('agent_xlsx_toolkit.Workbook')
    @patch('os.makedirs')
    def test_write_xlsx_creates_directory(self, mock_makedirs, mock_workbook):
        """Test that directory is created if it doesn't exist."""
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws
        
        data = [{'Col': 'Value'}]
        write_xlsx_file("/some/deep/path/output.xlsx", data)
        
        mock_makedirs.assert_called_with("/some/deep/path", exist_ok=True)
    
    @patch('agent_xlsx_toolkit.Workbook')
    def test_write_xlsx_empty_data(self, mock_workbook):
        """Test writing with empty data."""
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws
        
        result = write_xlsx_file("empty.xlsx", [])
        self.assertIn("File saved to", result)


class TestGetSheetNames(unittest.TestCase):
    """Tests for get_sheet_names function."""
    
    def test_sheet_names_file_not_found(self):
        """Test getting sheet names from non-existent file."""
        result = get_sheet_names("/nonexistent.xlsx")
        self.assertIn("Error: File not found", result)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_sheet_names_success(self, mock_exists, mock_load_workbook):
        """Test successful retrieval of sheet names."""
        mock_exists.return_value = True
        mock_wb = MagicMock()
        mock_wb.sheetnames = ['Summary', 'Data', 'Charts']
        mock_load_workbook.return_value = mock_wb
        
        result = get_sheet_names("report.xlsx")
        self.assertEqual(result, ['Summary', 'Data', 'Charts'])


class TestGetCellValue(unittest.TestCase):
    """Tests for get_cell_value function."""
    
    def test_get_cell_file_not_found(self):
        """Test getting cell value from non-existent file."""
        result = get_cell_value("/nonexistent.xlsx", "Sheet1", "A1")
        self.assertIn("Error: File not found", result)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_get_cell_success(self, mock_exists, mock_load_workbook):
        """Test successful cell value retrieval."""
        mock_exists.return_value = True
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.__getitem__.return_value.value = "Test Value"
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb
        
        result = get_cell_value("test.xlsx", "Sheet1", "A1")
        self.assertEqual(result, "Test Value")


class TestSetCellValue(unittest.TestCase):
    """Tests for set_cell_value function."""
    
    def test_set_cell_file_not_found(self):
        """Test setting cell value in non-existent file."""
        result = set_cell_value("/nonexistent.xlsx", "Sheet1", "A1", "Value")
        self.assertIn("Error: File not found", result)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_set_cell_success(self, mock_exists, mock_load_workbook):
        """Test successful cell value update."""
        mock_exists.return_value = True
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb
        
        result = set_cell_value("test.xlsx", "Sheet1", "A1", "New Value")
        self.assertIn("updated successfully", result)
        mock_ws.__setitem__.assert_called_with("A1", "New Value")


class TestGetDimensions(unittest.TestCase):
    """Tests for get_dimensions function."""
    
    def test_dimensions_file_not_found(self):
        """Test getting dimensions of non-existent file."""
        result = get_dimensions("/nonexistent.xlsx")
        self.assertIn("Error: File not found", result)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_dimensions_success(self, mock_exists, mock_load_workbook):
        """Test successful dimension retrieval."""
        mock_exists.return_value = True
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.dimensions = "A1:D50"
        mock_wb.active = mock_ws
        mock_load_workbook.return_value = mock_wb
        
        result = get_dimensions("test.xlsx")
        self.assertEqual(result, "A1:D50")


class TestCopySheet(unittest.TestCase):
    """Tests for copy_sheet function."""
    
    def test_copy_sheet_source_not_found(self):
        """Test copying sheet from non-existent file."""
        result = copy_sheet("/nonexistent.xlsx", "dest.xlsx")
        self.assertIn("Error: Source file not found", result)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('agent_xlsx_toolkit.Workbook')
    @patch('os.path.exists')
    def test_copy_sheet_success(self, mock_exists, mock_workbook, mock_load_workbook):
        """Test successful sheet copying."""
        mock_exists.return_value = True
        mock_src_wb = MagicMock()
        mock_src_ws = MagicMock()
        mock_src_ws.title = "Original"
        mock_src_ws.iter_rows.return_value = [('A', 'B'), ('1', '2')]
        mock_src_wb.active = mock_src_ws
        mock_load_workbook.return_value = mock_src_wb
        
        mock_dest_wb = MagicMock()
        mock_dest_ws = MagicMock()
        mock_workbook.return_value = mock_dest_wb
        mock_dest_wb.active = mock_dest_ws
        
        result = copy_sheet("source.xlsx", "dest.xlsx")
        self.assertIn("copied to", result)


class TestApplyStyle(unittest.TestCase):
    """Tests for apply_style function."""
    
    def test_apply_style_file_not_found(self):
        """Test applying style to non-existent file."""
        result = apply_style("/nonexistent.xlsx", "Sheet1", "A1:C1", {"font_bold": True})
        self.assertIn("Error: File not found", result)
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_apply_style_success(self, mock_exists, mock_load_workbook):
        """Test successful style application."""
        mock_exists.return_value = True
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.__getitem__.return_value = []  # Empty cell range
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb
        
        result = apply_style("test.xlsx", "Sheet1", "A1:D1", {"font_bold": True})
        self.assertIn("Style applied to", result)


class TestCreateEmptyWorkbook(unittest.TestCase):
    """Tests for create_empty_workbook function."""
    
    @patch('agent_xlsx_toolkit.Workbook')
    def test_create_empty_workbook_success(self, mock_workbook):
        """Test creating a new empty workbook."""
        mock_wb = MagicMock()
        mock_workbook.return_value = mock_wb
        
        result = create_empty_workbook("new.xlsx")
        self.assertIn("Empty workbook created at", result)
    
    @patch('agent_xlsx_toolkit.Workbook')
    def test_create_workbook_with_sheets(self, mock_workbook):
        """Test creating workbook with custom sheet names."""
        mock_wb = MagicMock()
        mock_workbook.return_value = mock_wb
        
        result = create_empty_workbook("multi.xlsx", sheet_names=['Sheet1', 'Sheet2'])
        self.assertIn("Empty workbook created at", result)
        mock_wb.remove.assert_called()
        mock_wb.create_sheet.assert_called()


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
        # We expect 9 tools from the xlsx toolkit
        self.assertEqual(len(tools), 9)
    
    def test_tools_have_descriptions(self):
        """Test that all tools have descriptions."""
        tools = get_all_tools()
        for tool in tools:
            # FunctionTool stores description in metadata
            self.assertIsNotNone(tool.metadata.description)
            self.assertGreater(len(tool.metadata.description), 0)


class TestErrorHandling(unittest.TestCase):
    """Tests for error handling in various functions."""
    
    @patch('agent_xlsx_toolkit.load_workbook')
    @patch('os.path.exists')
    def test_read_xlsx_handles_exception(self, mock_exists, mock_load_workbook):
        """Test that exceptions are caught and return error messages."""
        mock_exists.return_value = True
        mock_load_workbook.side_effect = Exception("Test error")
        
        result = read_xlsx_file("test.xlsx")
        self.assertIn("Error reading Excel file", result)
    
    @patch('agent_xlsx_toolkit.Workbook')
    def test_write_xlsx_handles_exception(self, mock_workbook):
        """Test that write exceptions are handled."""
        mock_workbook.side_effect = Exception("Disk full")
        
        result = write_xlsx_file("output.xlsx", [{'a': 1}])
        self.assertIn("Error writing Excel file", result)


if __name__ == "__main__":
    unittest.main()
