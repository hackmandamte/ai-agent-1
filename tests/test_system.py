import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import system


class SystemInspectionTests(unittest.TestCase):
    def test_disk_usage_is_structured(self):
        with tempfile.TemporaryDirectory() as temp:
            result = system.disk_usage(temp)
        self.assertIsInstance(result, dict)
        self.assertGreater(result["total_bytes"], 0)
        self.assertIn("free_percent", result)

    def test_network_state_uses_read_only_powershell(self):
        payload = json.dumps([{"InterfaceAlias": "Ethernet"}])
        result = type("Result", (), {"returncode": 0, "stdout": payload, "stderr": ""})()
        with patch.object(system.os, "name", "nt"), patch.object(system.subprocess, "run", return_value=result) as run:
            output = system.network_state()
        self.assertIn("Ethernet", output)
        self.assertEqual(run.call_args.args[0][0], "powershell.exe")

    def test_listening_ports_limits_results(self):
        payload = json.dumps([{"LocalPort": i, "OwningProcess": i} for i in range(10)])
        result = type("Result", (), {"returncode": 0, "stdout": payload, "stderr": ""})()
        with patch.object(system.os, "name", "nt"), patch.object(system.subprocess, "run", return_value=result):
            data = json.loads(system.listening_ports(3))
        self.assertEqual(len(data), 3)

    def test_environment_info_contains_no_secret_values(self):
        data = system.environment_info()
        self.assertIn("os", data)
        self.assertIn("cwd", data)
        self.assertNotIn("OPENAI_API_KEY", data)


if __name__ == "__main__":
    unittest.main()
