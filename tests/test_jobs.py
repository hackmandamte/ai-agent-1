import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import jobs


class PersistentJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patchers = [
            patch.object(jobs, "JOB_ROOT", root / "jobs"),
            patch.object(jobs, "REGISTRY", root / "jobs" / "registry.json"),
            patch.object(jobs, "WORKSPACE_ROOT", root),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def test_job_persists_and_captures_output(self):
        fake = type("FakeProcess", (), {"pid": os.getpid()})()
        with patch.object(jobs.subprocess, "Popen", return_value=fake):
            result = jobs.start_job("echo JOB_TEST_OK")
        job_id = result.splitlines()[0].split(": ", 1)[1]
        record = jobs.get_job(job_id)
        self.assertIsNotNone(record)
        self.assertEqual(record["job_id"], job_id)

        Path(record["stdout_file"]).write_text("JOB_TEST_OK\n", encoding="utf-8")
        Path(record["exit_file"]).write_text("0", encoding="utf-8")
        record = jobs.get_job(job_id)
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["exit_code"], 0)
        self.assertIn("JOB_TEST_OK", jobs.job_output(job_id))

    def test_unknown_job_is_handled(self):
        self.assertIsNone(jobs.get_job("missing"))
        self.assertIn("unknown job", jobs.job_output("missing"))


if __name__ == "__main__":
    unittest.main()
