"""
Unit tests for the OS toolkit's library half.

Tests file and directory operations including:
- pwd, ls, touch, mkdir, rm, cp, mv
- check_path_exists, read_file, write_file
- get_system_info

The suite moved here together with the toolkit: it used to live at
``tests/test_os_toolkit.py`` and import the single module
``agent_os_toolkit`` from the project root.  It now imports the library
half of the package through a **relative** import, so it belongs to the
package it tests.

The tests are offline and hermetic: every one of them works inside a
temporary directory, and none of them touches anything outside it.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from ..operations import (
    check_path_exists,
    cp,
    get_system_info,
    ls,
    mkdir,
    mv,
    pwd,
    read_file,
    rm,
    touch,
    write_file,
)

#: The repository root - three levels up from this file:
#: <root>/toolkits/os-toolkit/tests/test_operations.py
REPO_ROOT = Path(__file__).resolve().parents[3]


class TestPwd(unittest.TestCase):
    def test_pwd_returns_absolute_path(self):
        result = pwd()
        self.assertTrue(os.path.isabs(result))
        self.assertEqual(result, os.getcwd())


class TestLs(unittest.TestCase):
    def test_ls_current_dir(self):
        result = ls(".")
        self.assertIsInstance(result, list)
        self.assertEqual(sorted(result), sorted(os.listdir(".")))

    def test_ls_repo_root_lists_the_readme(self):
        """The repository root holds the README.

        The path is computed from ``__file__`` rather than assumed to be
        the current directory, so the test holds wherever pytest is
        started from.
        """
        result = ls(str(REPO_ROOT))
        self.assertIn("README.md", result)

    def test_ls_nonexistent_dir(self):
        result = ls("/nonexistent/directory/that/does/not/exist")
        self.assertIsInstance(result, str)
        self.assertIn("not found", result.lower())

    def test_ls_returns_a_list_of_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.txt").touch()
            Path(tmp, "b.txt").touch()
            result = ls(tmp)
        self.assertEqual(sorted(result), ["a.txt", "b.txt"])


class TestTouch(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_touch_creates_file(self):
        filepath = os.path.join(self.test_dir, "test_file.txt")
        result = touch(filepath)
        self.assertTrue(os.path.exists(filepath))
        self.assertEqual(result, filepath)

    def test_touch_existing_file(self):
        filepath = os.path.join(self.test_dir, "existing.txt")
        Path(filepath).touch()
        result = touch(filepath)
        self.assertTrue(os.path.exists(filepath))

    def test_touch_creates_missing_parents(self):
        """The parent directories are created on the way."""
        filepath = os.path.join(self.test_dir, "deep", "nested", "file.txt")
        touch(filepath)
        self.assertTrue(os.path.exists(filepath))

    def test_touch_leaves_an_existing_file_alone(self):
        """An existing file keeps its content."""
        filepath = os.path.join(self.test_dir, "keep.txt")
        write_file(filepath, "content")
        touch(filepath)
        self.assertEqual(read_file(filepath), "content")


class TestCheckPathExists(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "test.txt")
        Path(self.test_file).touch()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_existing_file(self):
        result = check_path_exists(self.test_file)
        self.assertTrue(result["exists"])
        self.assertTrue(result["is_file"])
        self.assertFalse(result["is_dir"])

    def test_existing_dir(self):
        result = check_path_exists(self.test_dir)
        self.assertTrue(result["exists"])
        self.assertFalse(result["is_file"])
        self.assertTrue(result["is_dir"])

    def test_nonexistent_path(self):
        result = check_path_exists("/nonexistent/path")
        self.assertFalse(result["exists"])

    def test_the_result_carries_the_resolved_path(self):
        result = check_path_exists(self.test_file)
        self.assertEqual(result["path"], self.test_file)

    def test_the_result_has_the_four_documented_keys(self):
        result = check_path_exists(self.test_file)
        for key in ("exists", "is_file", "is_dir", "path"):
            self.assertIn(key, result)


class TestMkdir(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_create_directory(self):
        new_dir = os.path.join(self.test_dir, "new_dir", "sub_dir")
        result = mkdir(new_dir)
        self.assertTrue(os.path.isdir(new_dir))
        self.assertIn("Directory created", result)

    def test_an_existing_directory_is_not_an_error(self):
        """``exist_ok=True`` - the second call succeeds."""
        new_dir = os.path.join(self.test_dir, "again")
        mkdir(new_dir)
        result = mkdir(new_dir)
        self.assertIn("Directory created", result)
        self.assertTrue(os.path.isdir(new_dir))


class TestWriteAndReadFile(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "test.txt")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_write_and_read(self):
        content = "Hello, Torvalds!"
        write_file(self.test_file, content)
        result = read_file(self.test_file)
        self.assertEqual(result, content)

    def test_read_nonexistent_file(self):
        result = read_file("/nonexistent/file.txt")
        self.assertIn("Error", result)

    def test_write_overwrites(self):
        write_file(self.test_file, "first")
        write_file(self.test_file, "second")
        self.assertEqual(read_file(self.test_file), "second")

    def test_read_returns_the_whole_file(self):
        content = "line one\nline two\n"
        write_file(self.test_file, content)
        self.assertEqual(read_file(self.test_file), content)


class TestRm(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "delete_me.txt")
        Path(self.test_file).touch()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_remove_file(self):
        result = rm(self.test_file)
        self.assertFalse(os.path.exists(self.test_file))
        self.assertIn("removed", result.lower())

    def test_remove_directory(self):
        result = rm(self.test_dir)
        self.assertFalse(os.path.exists(self.test_dir))

    def test_remove_a_directory_removes_its_contents(self):
        """The removal is recursive."""
        nested = os.path.join(self.test_dir, "nested")
        os.makedirs(nested)
        Path(nested, "inner.txt").touch()

        rm(self.test_dir)

        self.assertFalse(os.path.exists(self.test_dir))

    def test_remove_a_nonexistent_path_is_reported(self):
        result = rm("/nonexistent/path/that/is/not/there")
        self.assertIn("not found", result.lower())


class TestCp(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.src_file = os.path.join(self.test_dir, "source.txt")
        self.dst_file = os.path.join(self.test_dir, "dest.txt")
        with open(self.src_file, "w") as f:
            f.write("copy me")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_copy_file(self):
        result = cp(self.src_file, self.dst_file)
        self.assertTrue(os.path.exists(self.dst_file))
        with open(self.dst_file) as f:
            self.assertEqual(f.read(), "copy me")

    def test_copy_leaves_the_source_alone(self):
        cp(self.src_file, self.dst_file)
        self.assertTrue(os.path.exists(self.src_file))

    def test_copy_a_directory_tree(self):
        src_dir = os.path.join(self.test_dir, "tree")
        os.makedirs(os.path.join(src_dir, "inner"))
        Path(src_dir, "inner", "leaf.txt").touch()

        dst_dir = os.path.join(self.test_dir, "tree_copy")
        result = cp(src_dir, dst_dir)

        self.assertIn("Directory copied", result)
        self.assertTrue(Path(dst_dir, "inner", "leaf.txt").is_file())

    def test_copy_a_nonexistent_source_is_reported(self):
        result = cp("/nonexistent/source", self.dst_file)
        self.assertIn("not found", result.lower())


class TestMv(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.src_file = os.path.join(self.test_dir, "original.txt")
        self.dst_file = os.path.join(self.test_dir, "renamed.txt")
        with open(self.src_file, "w") as f:
            f.write("move me")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_move_file(self):
        result = mv(self.src_file, self.dst_file)
        self.assertFalse(os.path.exists(self.src_file))
        self.assertTrue(os.path.exists(self.dst_file))

    def test_move_keeps_the_content(self):
        mv(self.src_file, self.dst_file)
        with open(self.dst_file) as f:
            self.assertEqual(f.read(), "move me")

    def test_move_a_nonexistent_source_is_reported(self):
        result = mv("/nonexistent/source", self.dst_file)
        self.assertIn("Error", result)


class TestGetSystemInfo(unittest.TestCase):
    def test_returns_dict(self):
        result = get_system_info()
        self.assertIsInstance(result, dict)

    def test_has_system_key(self):
        result = get_system_info()
        self.assertIn("system", result)

    def test_carries_the_documented_keys(self):
        """The docstring promises these keys - they are part of the contract."""
        result = get_system_info()
        for key in (
            "system",
            "node",
            "release",
            "version",
            "machine",
            "processor",
            "architecture",
            "platform",
            "uname",
            "env_user",
        ):
            self.assertIn(key, result)


# ---------------------------------------------------------------------------
# The error contract
# ---------------------------------------------------------------------------


class TestErrorContract(unittest.TestCase):
    """A failure is *reported*, never raised.

    Every operation of the toolkit catches its own exceptions and returns
    a message (or a dict with an ``error`` key) instead of propagating
    them.  That is the contract the agent relies on: a tool that raises
    breaks the turn, a tool that reports lets the model recover.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_ls_reports_a_missing_directory(self):
        result = ls("/nonexistent/directory")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Directory not found"))

    def test_read_file_reports_a_missing_file(self):
        result = read_file("/nonexistent/file.txt")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Error reading file"))

    def test_write_file_reports_a_failure(self):
        """A path that cannot be written to is reported, not raised."""
        result = write_file("/nonexistent/directory/file.txt", "content")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Error writing file"))

    def test_rm_reports_a_missing_path(self):
        result = rm("/nonexistent/path")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Path not found"))

    def test_cp_reports_a_missing_source(self):
        result = cp("/nonexistent/source", "/tmp/whatever")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Source not found"))

    def test_mv_reports_a_failure(self):
        result = mv("/nonexistent/source", "/tmp/whatever")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Error moving path"))

    def test_no_operation_raises_on_a_bad_path(self):
        """The whole surface, called with nonsense, returns rather than raises."""
        calls = (
            lambda: ls("/nonexistent/x"),
            lambda: touch("/nonexistent/x/y.txt"),
            lambda: check_path_exists("/nonexistent/x"),
            lambda: mkdir("/nonexistent/x/y"),
            lambda: rm("/nonexistent/x"),
            lambda: cp("/nonexistent/x", "/tmp/y"),
            lambda: mv("/nonexistent/x", "/tmp/y"),
            lambda: read_file("/nonexistent/x"),
            lambda: write_file("/nonexistent/x/y", "c"),
            lambda: get_system_info(),
            lambda: pwd(),
        )
        for call in calls:
            with self.subTest(call=call):
                self.assertIsNotNone(call())


if __name__ == "__main__":
    unittest.main()
