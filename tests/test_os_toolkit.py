"""
Unit tests for agent_os_toolkit.

Tests file and directory operations including:
- pwd, ls, touch, mkdir, rm, cp, mv
- check_path_exists, read_file, write_file
- get_system_info
"""
import unittest
import os
import tempfile
import shutil
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_os_toolkit import (
    pwd, ls, touch, check_path_exists, mkdir, rm, cp, mv,
    read_file, write_file, get_system_info,
)


class TestPwd(unittest.TestCase):
    def test_pwd_returns_absolute_path(self):
        result = pwd()
        self.assertTrue(os.path.isabs(result))
        self.assertEqual(result, os.getcwd())


class TestLs(unittest.TestCase):
    def test_ls_current_dir(self):
        result = ls(".")
        self.assertIsInstance(result, list)
        self.assertIn("README.md", result)

    def test_ls_nonexistent_dir(self):
        result = ls("/nonexistent/directory/that/does/not/exist")
        self.assertIsInstance(result, str)
        self.assertIn("not found", result.lower())


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


class TestGetSystemInfo(unittest.TestCase):
    def test_returns_dict(self):
        result = get_system_info()
        self.assertIsInstance(result, dict)

    def test_has_system_key(self):
        result = get_system_info()
        self.assertIn("system", result)


if __name__ == "__main__":
    unittest.main()
