"""Structured Windows application discovery and launch."""
from __future__ import annotations

import json
import os
import subprocess


def discover_apps(query: str = "", limit: int = 100) -> str:
    if os.name != "nt":
        return "ERROR: application discovery is currently supported on Windows only"
    limit = max(1, min(int(limit), 500))
    command = (
        "Get-StartApps | Select-Object Name,AppID | "
        "ConvertTo-Json -Depth 3 -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        return f"ERROR: application discovery failed: {result.stderr.strip()}"
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        return f"ERROR: invalid application catalog response: {exc}"
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return "ERROR: application catalog response was not a list"
    query = str(query or "").strip().lower()
    apps = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("Name", ""))
        app_id = str(item.get("AppID", ""))
        if not name or not app_id:
            continue
        if query and query not in name.lower() and query not in app_id.lower():
            continue
        apps.append({"name": name, "app_id": app_id})
    apps.sort(key=lambda item: (item["name"].lower(), item["app_id"].lower()))
    return json.dumps(apps[:limit], indent=2)
def launch_app_id(app_id: str) -> str:
    if os.name != "nt":
        return "ERROR: structured application launch is currently supported on Windows only"
    if not isinstance(app_id, str) or not app_id.strip():
        return "ERROR: empty application ID"

    catalog = discover_apps(limit=500)
    if catalog.startswith("ERROR:"):
        return catalog
    try:
        apps = json.loads(catalog)
    except json.JSONDecodeError:
        return "ERROR: application catalog could not be parsed"
    match = next((item for item in apps if item.get("app_id") == app_id), None)
    if match is None:
        return f"ERROR: application ID not found: {app_id}"

    try:
        process = subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            close_fds=True,
        )
    except OSError as exc:
        return f"ERROR: application launch failed: {exc}"
    return f"APPLICATION LAUNCHED: {match['name']}\nAPP ID: {app_id}\nPID: {process.pid}"
