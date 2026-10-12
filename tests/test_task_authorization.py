import tempfile
import unittest
from pathlib import Path

from task_authorization import TaskAuthorization
from tools.task_manager import TaskManager, TaskStore


class TaskAuthorizationTests(unittest.TestCase):
    def test_workspace_write_is_permitted(self):
        with tempfile.TemporaryDirectory() as root:
            auth = TaskAuthorization(workspace=root)
            allowed, reason = auth.permits(
                "write_file",
                {"path": str(Path(root) / "src" / "app.py"), "content": "print('ok')"},
                "WRITE",
            )
            self.assertTrue(allowed, reason)

    def test_outside_workspace_is_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            auth = TaskAuthorization(workspace=root)
            allowed, reason = auth.permits(
                "write_file",
                {"path": str(Path(root).parent / "outside.txt"), "content": "no"},
                "WRITE",
            )
            self.assertFalse(allowed)
            self.assertIn("outside", reason.lower())

    def test_task_manager_persists_unattended_authorization(self):
        with tempfile.TemporaryDirectory() as root:
            store = TaskStore(Path(root) / "tasks")
            manager = TaskManager(store)
            task = manager.start("build website", max_steps=100)
            self.assertEqual(task.authorization["mode"], "unattended")
            self.assertTrue(task.authorization["auto_approve"])
            self.assertEqual(manager.get_authorization().workspace, str(Path(__file__).resolve().parents[1]))


if __name__ == "__main__":
    unittest.main()
