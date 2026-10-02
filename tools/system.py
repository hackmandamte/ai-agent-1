"""Read-only system inspection helpers."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def disk_usage(path: str = ".") -> dict | str:
    try:
        usage = shutil.disk_usage(Path(path).resolve())
    except OSError as exc:
        return f"ERROR: disk usage failed: {exc}"
    return {
        "path": str(Path(path).resolve()),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free_percent": round((usage.free / usage.total) * 100, 2) if usage.total else 0,
    }


def _powershell_json(command: str) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr.strip() or 'PowerShell command failed'}"
    return result.stdout.strip()


def network_state() -> str:
    if os.name != "nt":
        return "ERROR: network inspection is currently implemented for Windows only"
    return _powershell_json(
        "Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv6Address,DNSServer | "
        "ConvertTo-Json -Depth 5 -Compress"
    )


def listening_ports(limit: int = 100) -> str:
    if os.name != "nt":
        return "ERROR: port inspection is currently implemented for Windows only"
    limit = max(1, min(int(limit), 500))
    output = _powershell_json(
        "Get-NetTCPConnection -State Listen | "
        "Select-Object LocalAddress,LocalPort,OwningProcess | "
        "Sort-Object LocalPort | ConvertTo-Json -Compress"
    )
    if output.startswith("ERROR:"):
        return output
    try:
        payload = json.loads(output or "[]")
    except json.JSONDecodeError:
        return output
    if isinstance(payload, dict):
        payload = [payload]
    return json.dumps(payload[:limit], indent=2)
def environment_info() -> dict:
    """Return non-secret runtime/environment metadata only."""
    return {
        "os": os.name,
        "hostname": os.environ.get("COMPUTERNAME", ""),
        "architecture": os.environ.get("PROCESSOR_ARCHITECTURE", ""),
        "python": sys.version.split()[0],
        "cwd": str(Path.cwd().resolve()),
        "cpu_count": os.cpu_count(),
    }
