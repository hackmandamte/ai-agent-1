import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.task_manager import TaskManager, TaskStore
from tools.pc import system_info, list_processes
from tools.verify import verify_path_exists, verify_file_contains


class TaskPersistenceTests(unittest.TestCase):
    def test_plan_messages_and_resume_survive_reload(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        manager = TaskManager(TaskStore(Path(temp.name)))
        task = manager.start("resume me")
        manager.set_plan([{"id": "one", "status": "pending"}])
        manager.save_messages([{"role": "user", "content": "resume me"}])
        resumed = TaskManager(manager.store).resume(task.task_id)
        self.assertEqual(resumed.plan[0]["id"], "one")
        self.assertEqual(resumed.messages[0]["content"], "resume me")


class VerificationTests(unittest.TestCase):
    def test_path_and_content_verification(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        path = root / "x.txt"
        path.write_text("hello world", encoding="utf-8")
        with patch("tools.files.WORKSPACE_ROOT", root):
            self.assertIn("exists=True", verify_path_exists("x.txt"))
            self.assertIn("contains=True", verify_file_contains("x.txt", "world"))


class PcInspectionTests(unittest.TestCase):
    def test_system_info_is_structured(self):
        info = system_info()
        self.assertIn("os", info)
        self.assertIn("hostname", info)
        self.assertIn("pid", info)

    def test_process_listing_returns_data(self):
        fake_process = type(
            "FakeProcess",
            (),
            {
                "stdout": io.StringIO('"python.exe","123","Console","1","10 K"\n'),
                "stderr": io.StringIO(""),
                "wait": lambda self, timeout=None: 0,
            },
        )()
        with patch("tools.pc.subprocess.Popen", return_value=fake_process):
            result = list_processes(3)
        self.assertFalse(result.startswith("ERROR:"))
        self.assertIn("python.exe", result)


if __name__ == "__main__":
    unittest.main()
