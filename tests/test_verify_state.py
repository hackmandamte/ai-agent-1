import os
import unittest
from unittest.mock import patch

from tools import verify


class VerificationStateTests(unittest.TestCase):
    def test_running_process_is_verified(self):
        result = verify.verify_process_state(os.getpid(), True)
        self.assertIn("running=True", result)
        self.assertIn("match=True", result)

    def test_missing_process_is_reported(self):
        with patch("os.kill", side_effect=OSError):
            result = verify.verify_process_state(999999, False)
        self.assertIn("expected=False", result)
        self.assertIn("match=True", result)

    def test_job_status_is_verified(self):
        with patch("tools.jobs.get_job", return_value={"status": "completed", "exit_code": 0}):
            result = verify.verify_job_state("job1", "completed")
        self.assertIn("status=completed", result)
        self.assertIn("match=True", result)


if __name__ == "__main__":
    unittest.main()
