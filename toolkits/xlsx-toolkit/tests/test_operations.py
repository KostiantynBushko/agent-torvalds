"""
Unit tests for the Excel toolkit's library half.

The suite moved here together with the toolkit: it used to live at
``tests/test_xlsx_toolkit.py`` and import the single module
``agent_xlsx_toolkit`` from the project root.  It now imports the
library half of the package through a **relative** import, so it
belongs to the package it tests.

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
import unittest.mock as mock

# The operations are imported with a *relative* import - the only form
# that resolves inside the hyphenated package directory.  The module
# itself is imported as well, because the tests patch the openpyxl
# entry points on it.
from .. import operations
from ..operations import (
    apply_style,
    copy_sheet,
    create_empty_workbook,
    get_cell_value,
    get_dimensions,
    get_sheet_names,
    read_xlsx_file,
    set_cell_value,
    write_xlsx_file,
)

# ``get_all_tools`` is the one name that did **not** move into the
# library half: it is the adapter's, and the adapter is the one module
# of the toolkit that knows about LlamaIndex.
from ..agent_xlsx_toolkit import get_all_tools


class TestReadXlsxFile(unittest.TestCase):
    """Tests for read_xlsx_file function."""

    def test_read_xlsx_file_not_found(self):
        """Test reading a non-existent file returns error."""
        result = read_xlsx_file("/nonexistent/path/file.xlsx")
        self.assertIn("Error: File not found", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_read_xlsx_file_success(self, mock_load_workbook, mock_exists):
        """Test successful file reading."""
        # Mock workbook and worksheet
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
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

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_read_xlsx_with_specific_sheet(self, mock_load_workbook, mock_exists):
        """Test reading a specific sheet by name."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_wb.__getitem__.return_value = mock_ws
        mock_wb.active = mock_ws
        mock_load_workbook.return_value = mock_wb

        result = read_xlsx_file("test.xlsx", sheet_name="Sheet2")
        mock_wb.__getitem__.assert_called_with("Sheet2")

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_read_xlsx_reads_the_workbook_read_only(self, mock_load_workbook, mock_exists):
        """The workbook is opened read-only and with the cached values.

        ``data_only=True`` is what makes a cell that holds a formula
        read as its last computed value, and ``read_only=True`` keeps a
        large workbook out of memory.  Both are behaviour.
        """
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_wb.active = mock_ws
        mock_ws.iter_rows.return_value = [('Name',)]
        mock_load_workbook.return_value = mock_wb

        read_xlsx_file("test.xlsx")

        mock_load_workbook.assert_called_once_with(
            filename="test.xlsx", read_only=True, data_only=True
        )

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_read_xlsx_closes_the_workbook(self, mock_load_workbook, mock_exists):
        """A closed workbook releases the file handle."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_wb.active = mock_ws
        mock_ws.iter_rows.return_value = [('Name',)]
        mock_load_workbook.return_value = mock_wb

        read_xlsx_file("test.xlsx")

        mock_wb.close.assert_called_once()


class TestWriteXlsxFile(unittest.TestCase):
    """Tests for write_xlsx_file function."""

    @mock.patch.object(operations, "Workbook")
    def test_write_xlsx_file_success(self, mock_workbook):
        """Test successful file writing."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws

        data = [{'Name': 'Alice', 'Age': 30}, {'Name': 'Bob', 'Age': 25}]
        result = write_xlsx_file("output.xlsx", data)

        self.assertIn("File saved to", result)
        mock_ws.append.assert_called()

    @mock.patch.object(operations, "Workbook")
    @mock.patch.object(operations.os, "makedirs")
    def test_write_xlsx_creates_directory(self, mock_makedirs, mock_workbook):
        """Test that directory is created if it doesn't exist."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws

        data = [{'Col': 'Value'}]
        write_xlsx_file("/some/deep/path/output.xlsx", data)

        mock_makedirs.assert_called_with("/some/deep/path", exist_ok=True)

    @mock.patch.object(operations, "Workbook")
    def test_write_xlsx_empty_data(self, mock_workbook):
        """Test writing with empty data."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws

        result = write_xlsx_file("empty.xlsx", [])
        self.assertIn("File saved to", result)

    @mock.patch.object(operations, "Workbook")
    def test_write_xlsx_writes_the_headers_first(self, mock_workbook):
        """The header row comes from the keys of the first record."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws

        write_xlsx_file("output.xlsx", [{'Name': 'Alice', 'Age': 30}])

        mock_ws.append.assert_any_call(['Name', 'Age'])
        mock_ws.append.assert_any_call(['Alice', 30])

    @mock.patch.object(operations, "Workbook")
    def test_write_xlsx_uses_the_requested_sheet_name(self, mock_workbook):
        """The sheet is renamed to the one that was asked for."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws

        write_xlsx_file("output.xlsx", [{'Col': 1}], sheet_name="Data")

        self.assertEqual(mock_ws.title, "Data")

    @mock.patch.object(operations, "Workbook")
    def test_write_xlsx_saves_the_file(self, mock_workbook):
        """The workbook is saved to the requested path."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws

        write_xlsx_file("output.xlsx", [{'Col': 1}])

        mock_wb.save.assert_called_once_with("output.xlsx")

    @mock.patch.object(operations, "Workbook")
    def test_write_xlsx_writes_no_data_for_an_empty_list(self, mock_workbook):
        """An empty list is written as the single cell ``No data``."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.active = mock_ws

        write_xlsx_file("empty.xlsx", [])

        mock_ws.append.assert_called_once_with(["No data"])


class TestGetSheetNames(unittest.TestCase):
    """Tests for get_sheet_names function."""

    def test_sheet_names_file_not_found(self):
        """Test getting sheet names from non-existent file."""
        result = get_sheet_names("/nonexistent.xlsx")
        self.assertIn("Error: File not found", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_sheet_names_success(self, mock_load_workbook, mock_exists):
        """Test successful retrieval of sheet names."""
        mock_wb = mock.MagicMock()
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

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_get_cell_success(self, mock_load_workbook, mock_exists):
        """Test successful cell value retrieval."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_ws.__getitem__.return_value.value = "Test Value"
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb

        result = get_cell_value("test.xlsx", "Sheet1", "A1")
        self.assertEqual(result, "Test Value")

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_get_cell_empty_cell_is_none(self, mock_load_workbook, mock_exists):
        """An empty cell reads as ``None``.

        That is the value of the cell, not an error - the operation
        succeeded and found nothing there.
        """
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_ws.__getitem__.return_value.value = None
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb

        result = get_cell_value("test.xlsx", "Sheet1", "A1")
        self.assertIsNone(result)


class TestSetCellValue(unittest.TestCase):
    """Tests for set_cell_value function."""

    def test_set_cell_file_not_found(self):
        """Test setting cell value in non-existent file."""
        result = set_cell_value("/nonexistent.xlsx", "Sheet1", "A1", "Value")
        self.assertIn("Error: File not found", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_set_cell_success(self, mock_load_workbook, mock_exists):
        """Test successful cell value update."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb

        result = set_cell_value("test.xlsx", "Sheet1", "A1", "New Value")
        self.assertIn("updated successfully", result)
        mock_ws.__setitem__.assert_called_with("A1", "New Value")

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_set_cell_saves_the_workbook(self, mock_load_workbook, mock_exists):
        """The workbook is written back to the file it came from."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb

        set_cell_value("test.xlsx", "Sheet1", "A1", "New Value")

        mock_wb.save.assert_called_once_with("test.xlsx")


class TestGetDimensions(unittest.TestCase):
    """Tests for get_dimensions function."""

    def test_dimensions_file_not_found(self):
        """Test getting dimensions of non-existent file."""
        result = get_dimensions("/nonexistent.xlsx")
        self.assertIn("Error: File not found", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_dimensions_success(self, mock_load_workbook, mock_exists):
        """Test successful dimension retrieval."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
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

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    @mock.patch.object(operations, "Workbook")
    def test_copy_sheet_success(self, mock_workbook, mock_load_workbook, mock_exists):
        """Test successful sheet copying."""
        mock_src_wb = mock.MagicMock()
        mock_src_ws = mock.MagicMock()
        mock_src_ws.title = "Original"
        mock_src_ws.iter_rows.return_value = [('A', 'B'), ('1', '2')]
        mock_src_wb.active = mock_src_ws
        mock_load_workbook.return_value = mock_src_wb

        mock_dest_wb = mock.MagicMock()
        mock_dest_ws = mock.MagicMock()
        mock_workbook.return_value = mock_dest_wb
        mock_dest_wb.active = mock_dest_ws

        result = copy_sheet("source.xlsx", "dest.xlsx")
        self.assertIn("copied to", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    @mock.patch.object(operations, "Workbook")
    def test_copy_sheet_copies_the_rows(self, mock_workbook, mock_load_workbook, mock_exists):
        """Every row of the source sheet is written to the new one."""
        mock_src_wb = mock.MagicMock()
        mock_src_ws = mock.MagicMock()
        mock_src_ws.title = "Original"
        mock_src_ws.iter_rows.return_value = [('A', 'B'), ('1', '2')]
        mock_src_wb.active = mock_src_ws
        mock_load_workbook.return_value = mock_src_wb

        mock_dest_wb = mock.MagicMock()
        mock_dest_ws = mock.MagicMock()
        mock_workbook.return_value = mock_dest_wb
        mock_dest_wb.active = mock_dest_ws

        copy_sheet("source.xlsx", "dest.xlsx")

        mock_dest_ws.append.assert_any_call(('A', 'B'))
        mock_dest_ws.append.assert_any_call(('1', '2'))


class TestApplyStyle(unittest.TestCase):
    """Tests for apply_style function."""

    def test_apply_style_file_not_found(self):
        """Test applying style to non-existent file."""
        result = apply_style("/nonexistent.xlsx", "Sheet1", "A1:C1", {"font_bold": True})
        self.assertIn("Error: File not found", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_apply_style_success(self, mock_load_workbook, mock_exists):
        """Test successful style application."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_ws.__getitem__.return_value = []  # Empty cell range
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb

        result = apply_style("test.xlsx", "Sheet1", "A1:D1", {"font_bold": True})
        self.assertIn("Style applied to", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_apply_style_sets_the_font(self, mock_load_workbook, mock_exists):
        """A bold font is written on every cell of the range."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        cell = mock.MagicMock()
        mock_ws.__getitem__.return_value = [(cell,)]
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb

        apply_style("test.xlsx", "Sheet1", "A1:D1", {"font_bold": True})

        self.assertTrue(cell.font.bold)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_apply_style_saves_the_workbook(self, mock_load_workbook, mock_exists):
        """The styled workbook is written back."""
        mock_wb = mock.MagicMock()
        mock_ws = mock.MagicMock()
        mock_ws.__getitem__.return_value = []
        mock_wb.__getitem__.return_value = mock_ws
        mock_load_workbook.return_value = mock_wb

        apply_style("test.xlsx", "Sheet1", "A1:D1", {"font_bold": True})

        mock_wb.save.assert_called_once_with("test.xlsx")


class TestCreateEmptyWorkbook(unittest.TestCase):
    """Tests for create_empty_workbook function."""

    @mock.patch.object(operations, "Workbook")
    def test_create_empty_workbook_success(self, mock_workbook):
        """Test creating a new empty workbook."""
        mock_wb = mock.MagicMock()
        mock_workbook.return_value = mock_wb

        result = create_empty_workbook("new.xlsx")
        self.assertIn("Empty workbook created at", result)

    @mock.patch.object(operations, "Workbook")
    def test_create_workbook_with_sheets(self, mock_workbook):
        """Test creating workbook with custom sheet names."""
        mock_wb = mock.MagicMock()
        mock_workbook.return_value = mock_wb

        result = create_empty_workbook("multi.xlsx", sheet_names=['Sheet1', 'Sheet2'])
        self.assertIn("Empty workbook created at", result)
        mock_wb.remove.assert_called()
        mock_wb.create_sheet.assert_called()

    @mock.patch.object(operations, "Workbook")
    def test_create_workbook_creates_every_named_sheet(self, mock_workbook):
        """One sheet is created per name that was asked for."""
        mock_wb = mock.MagicMock()
        mock_workbook.return_value = mock_wb

        create_empty_workbook("multi.xlsx", sheet_names=['Data', 'Summary'])

        mock_wb.create_sheet.assert_any_call(title='Data')
        mock_wb.create_sheet.assert_any_call(title='Summary')


class TestGetAllTools(unittest.TestCase):
    """Tests for the adapter's get_all_tools function."""

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

    def test_the_tool_names_are_stable(self):
        """The order of the tools is part of what the model sees."""
        tools = get_all_tools()
        self.assertEqual(
            [tool.metadata.name for tool in tools],
            [
                'read_xlsx_file',
                'write_xlsx_file',
                'get_sheet_names',
                'get_cell_value',
                'set_cell_value',
                'get_dimensions',
                'copy_sheet',
                'apply_style',
                'create_empty_workbook',
            ],
        )

    def test_every_tool_carries_the_category(self):
        """The category is what the startup menu groups by."""
        for tool in get_all_tools():
            self.assertIn("Category: Data / Excel", tool.metadata.description)


class TestErrorHandling(unittest.TestCase):
    """Tests for error handling in various functions."""

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_read_xlsx_handles_exception(self, mock_load_workbook, mock_exists):
        """Test that exceptions are caught and return error messages."""
        mock_load_workbook.side_effect = Exception("Test error")

        result = read_xlsx_file("test.xlsx")
        self.assertIn("Error reading Excel file", result)

    @mock.patch.object(operations, "Workbook")
    def test_write_xlsx_handles_exception(self, mock_workbook):
        """Test that write exceptions are handled."""
        mock_workbook.side_effect = Exception("Disk full")

        result = write_xlsx_file("output.xlsx", [{'a': 1}])
        self.assertIn("Error writing Excel file", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_sheet_names_handles_exception(self, mock_load_workbook, mock_exists):
        """A workbook that cannot be opened is reported, not raised."""
        mock_load_workbook.side_effect = Exception("Test error")

        result = get_sheet_names("report.xlsx")
        self.assertIn("Error getting sheet names", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_get_cell_handles_exception(self, mock_load_workbook, mock_exists):
        """A cell that cannot be read is reported, not raised."""
        mock_load_workbook.side_effect = Exception("Test error")

        result = get_cell_value("test.xlsx", "Sheet1", "A1")
        self.assertIn("Error getting cell value", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_set_cell_handles_exception(self, mock_load_workbook, mock_exists):
        """A cell that cannot be written is reported, not raised."""
        mock_load_workbook.side_effect = Exception("Test error")

        result = set_cell_value("test.xlsx", "Sheet1", "A1", "Value")
        self.assertIn("Error setting cell value", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_get_dimensions_handles_exception(self, mock_load_workbook, mock_exists):
        """A sheet whose extent cannot be read is reported, not raised."""
        mock_load_workbook.side_effect = Exception("Test error")

        result = get_dimensions("test.xlsx")
        self.assertIn("Error getting dimensions", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_copy_sheet_handles_exception(self, mock_load_workbook, mock_exists):
        """A sheet that cannot be copied is reported, not raised."""
        mock_load_workbook.side_effect = Exception("Test error")

        result = copy_sheet("source.xlsx", "dest.xlsx")
        self.assertIn("Error copying sheet", result)

    @mock.patch.object(operations.os.path, "exists", return_value=True)
    @mock.patch.object(operations, "load_workbook")
    def test_apply_style_handles_exception(self, mock_load_workbook, mock_exists):
        """A style that cannot be applied is reported, not raised."""
        mock_load_workbook.side_effect = Exception("Test error")

        result = apply_style("test.xlsx", "Sheet1", "A1:D1", {"font_bold": True})
        self.assertIn("Error applying style", result)

    @mock.patch.object(operations, "Workbook")
    def test_create_workbook_handles_exception(self, mock_workbook):
        """A workbook that cannot be created is reported, not raised."""
        mock_workbook.side_effect = Exception("Disk full")

        result = create_empty_workbook("new.xlsx")
        self.assertIn("Error creating workbook", result)


if __name__ == "__main__":
    unittest.main()
