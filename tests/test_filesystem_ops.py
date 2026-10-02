import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import files
from tools.policy import DESTRUCTIVE, WRITE, policy_result


class FilesystemOperationTests(unittest.TestCase):
    def test_copy_move_delete_stay_inside_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "source.txt").write_text("hello", encoding="utf-8")
            with patch.object(files, "WORKSPACE_ROOT", root):
                self.assertIn("DIRECTORY CREATED", files.create_directory("nested"))
                self.assertIn("COPIED", files.copy_path("source.txt", "nested/copy.txt"))
                self.assertTrue((root / "nested/copy.txt").exists())
                self.assertIn("MOVED", files.move_path("nested/copy.txt", "moved.txt"))
                self.assertTrue((root / "moved.txt").exists())
                self.assertIn("DELETED", files.delete_path("moved.txt"))
                self.assertFalse((root / "moved.txt").exists())

    def test_workspace_root_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(files, "WORKSPACE_ROOT", root):
                self.assertIn("refusing", files.delete_path("."))

    def test_filesystem_writes_require_approval(self):
        self.assertEqual(policy_result("copy_path", {})[0], WRITE)
        self.assertEqual(policy_result("move_path", {})[0], WRITE)
        self.assertEqual(policy_result("delete_path", {})[0], DESTRUCTIVE)


if __name__ == "__main__":
    unittest.main()
