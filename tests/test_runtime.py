import unittest
from pathlib import Path
from unittest.mock import patch

from tools import runtime


class RuntimeDetectionTests(unittest.TestCase):
    @staticmethod
    def _context(system, environment):
        with patch.object(runtime.platform, "system", return_value=system):
            with patch.dict(runtime.os.environ, environment, clear=True):
                return runtime.get_runtime_context()

    def test_windows_powershell_detection(self):
        context = self._context(
            "Windows",
            {
                "COMSPEC": r"C:\Windows\System32\cmd.exe",
                "PSModulePath": r"C:\Program Files\WindowsPowerShell\Modules",
            },
        )

        self.assertEqual(context["shell"], "PowerShell")

    def test_windows_command_prompt_detection(self):
        context = self._context(
            "Windows",
            {"COMSPEC": r"C:\Windows\System32\cmd.exe"},
        )

        self.assertEqual(context["shell"], "Command Prompt")

    def test_unix_bash_detection(self):
        context = self._context("Linux", {"SHELL": "/bin/bash"})

        self.assertEqual(context["shell"], "bash")

    def test_runtime_context_contains_required_fields(self):
        context = runtime.get_runtime_context()

        for field in ("os", "shell", "python_version", "architecture", "workspace_path"):
            self.assertIn(field, context)
            self.assertTrue(context[field])

        workspace_path = Path(context["workspace_path"])
        self.assertTrue(workspace_path.is_absolute())
        self.assertEqual(workspace_path, Path.cwd().resolve())


if __name__ == "__main__":
    unittest.main()
