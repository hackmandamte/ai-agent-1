import json
import unittest
from unittest.mock import patch

from tools import apps


class AppDiscoveryTests(unittest.TestCase):
    def test_discovery_filters_and_sorts_catalog(self):
        payload = json.dumps([
            {"Name": "Zulu", "AppID": "z"},
            {"Name": "Alpha", "AppID": "a"},
            {"Name": "Other", "AppID": "o"},
        ])
        result = type("Result", (), {"returncode": 0, "stdout": payload, "stderr": ""})()
        with patch.object(apps.os, "name", "nt"), patch.object(apps.subprocess, "run", return_value=result):
            data = json.loads(apps.discover_apps("a"))

        self.assertEqual(data, [{"name": "Alpha", "app_id": "a"}])

    def test_launch_requires_discovered_exact_app_id(self):
        catalog = json.dumps([{"name": "Alpha", "app_id": "alpha-id"}])
        with patch.object(apps.os, "name", "nt"), \
                patch.object(apps, "discover_apps", return_value=catalog), \
                patch.object(apps.subprocess, "Popen") as popen:
            result = apps.launch_app_id("alpha-id")

        self.assertIn("APPLICATION LAUNCHED: Alpha", result)
        popen.assert_called_once_with(
            ["explorer.exe", "shell:AppsFolder\\alpha-id"], close_fds=True
        )

    def test_unknown_app_id_is_rejected(self):
        with patch.object(apps.os, "name", "nt"), \
                patch.object(apps, "discover_apps", return_value="[]"), \
                patch.object(apps.subprocess, "Popen") as popen:
            result = apps.launch_app_id("missing")

        self.assertTrue(result.startswith("ERROR:"))
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
