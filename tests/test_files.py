import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import files


class FileToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_directory.name).resolve()
        self.workspace_patch = patch.object(files, "WORKSPACE_ROOT", self.workspace)
        self.workspace_patch.start()

    def tearDown(self):
        self.workspace_patch.stop()
        self.temp_directory.cleanup()

    def test_relative_workspace_path_handling(self):
        target = self.workspace / "nested" / "example.txt"
        target.parent.mkdir(parents=True)
        target.write_text("hello", encoding="utf-8")

        self.assertEqual(files.safe_path("nested/example.txt"), target)
        self.assertEqual(files.read_file("nested/example.txt"), "hello")

    def test_absolute_path_inside_workspace_is_accepted(self):
        target = self.workspace / "inside.txt"
        target.write_text("inside", encoding="utf-8")

        absolute_path = str(target)
        self.assertEqual(files.safe_path(absolute_path), target)
        self.assertEqual(files.read_file(absolute_path), "inside")

    def test_absolute_path_outside_workspace_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside_directory:
            outside_path = Path(outside_directory) / "secret.txt"
            with self.assertRaises(ValueError):
                files.safe_path(str(outside_path))

    def test_read_file_on_directory_returns_controlled_error(self):
        directory = self.workspace / "directory"
        directory.mkdir()

        result = files.read_file(str(directory))

        self.assertTrue(result.startswith("ERROR:"))
        self.assertIn("directory", result.casefold())


if __name__ == "__main__":
    unittest.main()
