import json
import tempfile
import unittest
from pathlib import Path

from tools.task_manager import TaskManager, TaskStore


class TaskManagerTests(unittest.TestCase):
    def make_manager(self):
        temp = tempfile.TemporaryDirectory()
        store = TaskStore(Path(temp.name))
        return temp, TaskManager(store)

    def test_start_persists_running_task(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        task = manager.start("do several things", max_steps=7)
        loaded = manager.store.load(task.task_id)

        self.assertEqual(loaded.goal, "do several things")
        self.assertEqual(loaded.status, "running")
        self.assertEqual(loaded.max_steps, 7)

    def test_step_and_tool_result_are_persisted(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        task = manager.start("test")
        manager.begin_step(2)
        self.assertTrue(manager.record_tool_result("read_file", "hello"))

        loaded = manager.store.load(task.task_id)
        self.assertEqual(loaded.current_step, 2)
        self.assertEqual(loaded.status, "running")
        self.assertEqual(loaded.history[-1]["tool"], "read_file")
        self.assertTrue(loaded.history[-1]["ok"])

    def test_failures_use_retry_budget(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        task = manager.start("recover", retry_budget=1)
        manager.begin_step(1)

        self.assertTrue(manager.record_tool_result("shell", "ERROR: first"))
        self.assertEqual(manager.store.load(task.task_id).status, "waiting")

        self.assertFalse(manager.record_tool_result("shell", "ERROR: second"))
        loaded = manager.store.load(task.task_id)
        self.assertEqual(loaded.status, "failed")
        self.assertEqual(loaded.retries, 2)
        self.assertIn("ERROR: second", loaded.last_error)

    def test_approval_denial_is_a_recoverable_failure(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        task = manager.start("approval", retry_budget=1)
        manager.begin_step(1)
        self.assertTrue(manager.record_tool_result("git_commit", "APPROVAL DENIED: no"))

        loaded = manager.store.load(task.task_id)
        self.assertEqual(loaded.status, "waiting")
        self.assertFalse(loaded.history[-1]["ok"])

    def test_negative_verification_does_not_mark_task_verified(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        task = manager.start("verify something")
        manager.begin_step(1)
        manager.record_tool_result("verify_path_exists", "VERIFIED: exists=False path=missing.txt")
        self.assertFalse(manager.store.load(task.task_id).verified)

        manager.record_tool_result("verify_file_contains", "VERIFIED: contains=False path=file.txt")
        self.assertFalse(manager.store.load(task.task_id).verified)

    def test_positive_verification_marks_task_verified(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        task = manager.start("verify something")
        manager.begin_step(1)
        manager.record_tool_result("verify_process_state", "VERIFIED: pid=123 running=True expected=True match=True")
        self.assertTrue(manager.store.load(task.task_id).verified)

    def test_completion_is_terminal(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        task = manager.start("finish")
        manager.complete("finished")
        loaded = manager.store.load(task.task_id)

        self.assertEqual(loaded.status, "completed")
        self.assertIsNone(loaded.last_error)
        self.assertEqual(loaded.history[-1]["event"], "completed")

    def test_store_lists_tasks(self):
        temp, manager = self.make_manager()
        self.addCleanup(temp.cleanup)

        first = manager.start("one")
        manager.complete("one done")
        second = manager.start("two")

        ids = {task.task_id for task in manager.store.list()}
        self.assertEqual(ids, {first.task_id, second.task_id})


if __name__ == "__main__":
    unittest.main()
