import unittest
from unittest.mock import patch

from tools.policy import (
    READ, WRITE, DESTRUCTIVE, HIGH_RISK,
    classify_shell_command, classify_tool, policy_result,
)


class PolicyClassificationTests(unittest.TestCase):
    def test_read_tools_do_not_require_approval(self):
        risk, approval, _ = policy_result("read_file", {"path": "x.txt"})
        self.assertEqual(risk, READ)
        self.assertFalse(approval)

    def test_write_file_requires_approval(self):
        risk, approval, message = policy_result("write_file", {"path": "x.txt"})
        self.assertEqual(risk, WRITE)
        self.assertTrue(approval)
        self.assertIn("x.txt", message)

    def test_destructive_process_action_requires_approval(self):
        risk, approval, _ = policy_result("terminate_process", {"pid": 1234})
        self.assertEqual(risk, DESTRUCTIVE)
        self.assertTrue(approval)

    def test_high_risk_actions_require_approval(self):
        risk, approval, _ = policy_result("git_commit", {"message": "test"})
        self.assertEqual(risk, HIGH_RISK)
        self.assertTrue(approval)

    def test_shell_command_risk(self):
        self.assertEqual(classify_shell_command("echo hello"), READ)
        self.assertEqual(classify_shell_command("git status"), HIGH_RISK)
        self.assertEqual(classify_shell_command("Remove-Item x.txt"), DESTRUCTIVE)
        self.assertEqual(classify_shell_command("powershell -Command Remove-Item x.txt"), DESTRUCTIVE)
        self.assertEqual(classify_shell_command("cmd /c del x.txt"), DESTRUCTIVE)

    def test_verification_commands_are_not_trusted_as_read_only(self):
        risk, approval, _ = policy_result("verify_command", {"command": "echo test"})
        self.assertEqual(risk, HIGH_RISK)
        self.assertTrue(approval)

    def test_unknown_and_mcp_tools_fail_closed(self):
        self.assertEqual(classify_tool("unknown_tool"), HIGH_RISK)
        self.assertEqual(classify_tool("mcp__example__do_thing"), HIGH_RISK)



    def test_obscura_browser_reads_are_read_only(self):
        for tool in (
            "mcp__obscura__browser_snapshot",
            "mcp__obscura__browser_navigate",
            "mcp__obscura__browser_wait_for",
            "mcp__obscura__browser_network_requests",
        ):
            risk, approval, _ = policy_result(tool, {})
            self.assertEqual(risk, READ)
            self.assertFalse(approval)

    def test_obscura_browser_actions_require_approval(self):
        for tool in (
            "mcp__obscura__browser_click",
            "mcp__obscura__browser_fill",
            "mcp__obscura__browser_type",
            "mcp__obscura__browser_press_key",
            "mcp__obscura__browser_evaluate",
        ):
            risk, approval, _ = policy_result(tool, {})
            self.assertEqual(risk, HIGH_RISK)
            self.assertTrue(approval)


if __name__ == "__main__":
    unittest.main()


