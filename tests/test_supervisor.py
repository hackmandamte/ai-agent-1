import os
import unittest
from unittest.mock import patch

from supervisor import review_action
from supervisor_policy import local_supervisor_floor


class SupervisorPolicyTests(unittest.TestCase):
    def test_read_action_allowed_by_local_floor(self):
        decision = local_supervisor_floor("read_file", "READ", {"path": "C:\\Users\\Admin\\Desktop\\x.txt"})
        self.assertEqual(decision.verdict, "ALLOW")

    def test_delete_requires_approval(self):
        decision = local_supervisor_floor("delete_path", "DESTRUCTIVE", {"path": "C:\\Users\\Admin\\Desktop\\x.txt"})
        self.assertEqual(decision.verdict, "APPROVAL_REQUIRED")


class SupervisorIntegrationTests(unittest.TestCase):
    @patch("supervisor._remote_review")
    def test_remote_block_wins(self, remote):
        remote.return_value = type("D", (), {"verdict": "BLOCK", "reason": "Suspicious"})()
        decision = review_action("clean project", "shell", {"command": "powershell something"}, "HIGH_RISK")
        self.assertEqual(decision.verdict, "BLOCK")

    @patch("supervisor._remote_review")
    def test_local_approval_cannot_be_removed(self, remote):
        remote.return_value = type("D", (), {"verdict": "ALLOW", "reason": "Looks fine"})()
        decision = review_action("modify project", "write_file", {"path": "x", "content": "x"}, "WRITE")
        self.assertEqual(decision.verdict, "APPROVAL_REQUIRED")

    @patch("supervisor._remote_review")
    def test_unavailable_blocks_side_effect(self, remote):
        remote.return_value = type("D", (), {"verdict": "UNAVAILABLE", "reason": "offline"})()
        decision = review_action("modify project", "write_file", {"path": "x", "content": "x"}, "WRITE")
        self.assertEqual(decision.verdict, "BLOCK")


if __name__ == "__main__":
    unittest.main()
