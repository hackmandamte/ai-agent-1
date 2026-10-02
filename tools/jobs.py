"""Persistent background-job management for Agent 1."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .files import WORKSPACE_ROOT

JOB_ROOT = WORKSPACE_ROOT / ".agent_state" / "jobs"
REGISTRY = JOB_ROOT / "registry.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_root() -> None:
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    if not REGISTRY.exists():
        REGISTRY.write_text("{}", encoding="utf-8")


def _load() -> dict:
    _ensure_root()
    try:
        value = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    _ensure_root()
    temp = REGISTRY.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(REGISTRY)


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False
def _refresh(record: dict) -> dict:
    if record.get("status") != "running":
        return record
    exit_file = Path(record["exit_file"])
    if exit_file.exists():
        try:
            code = int(exit_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            code = None
        record["exit_code"] = code
        record["status"] = "completed" if code == 0 else "failed"
        record["updated_at"] = _now()
        return record
    if not _pid_running(int(record["pid"])):
        record["status"] = "failed"
        record["exit_code"] = None
        record["updated_at"] = _now()
    return record


def start_job(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        return "ERROR: empty job command"
    _ensure_root()
    job_id = uuid.uuid4().hex
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    stdout_file = job_dir / "stdout.log"
    stderr_file = job_dir / "stderr.log"
    exit_file = job_dir / "exit_code.txt"
    stdout = stdout_file.open("w", encoding="utf-8")
    stderr = stderr_file.open("w", encoding="utf-8")
    try:
        if os.name == "nt":
            script_file = job_dir / "run.cmd"
            script_file.write_text(
                "@echo off\n"
                + command
                + "\nset RC=%ERRORLEVEL%\necho %RC% > \""
                + str(exit_file)
                + "\"\n",
                encoding="utf-8",
            )
            process = subprocess.Popen(
                ["cmd.exe", "/d", "/c", str(script_file)],
                cwd=WORKSPACE_ROOT,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
        else:
            wrapper = (
                "import pathlib,subprocess,sys; "
                "rc=subprocess.run(sys.argv[1],shell=True).returncode; "
                "pathlib.Path(sys.argv[2]).write_text(str(rc),encoding='utf-8'); "
                "raise SystemExit(rc)"
            )
            process = subprocess.Popen(
                [sys.executable, "-c", wrapper, command, str(exit_file)],
                cwd=WORKSPACE_ROOT,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
    except Exception:
        stdout.close()
        stderr.close()
        raise
    finally:
        stdout.close()
        stderr.close()
    data = _load()
    data[job_id] = {
        "job_id": job_id,
        "pid": process.pid,
        "command": command,
        "status": "running",
        "exit_code": None,
        "started_at": _now(),
        "updated_at": _now(),
        "stdout_file": str(stdout_file),
        "stderr_file": str(stderr_file),
        "exit_file": str(exit_file),
    }
    _save(data)
    return f"JOB ID: {job_id}\nPID: {process.pid}"


def get_job(job_id: str) -> dict | None:
    data = _load()
    record = data.get(str(job_id))
    if not isinstance(record, dict):
        return None
    refreshed = _refresh(record)
    data[str(job_id)] = refreshed
    _save(data)
    return refreshed


def list_jobs() -> str:
    data = _load()
    records = []
    changed = False
    for job_id, record in data.items():
        if isinstance(record, dict):
            refreshed = _refresh(record)
            changed = changed or refreshed != record
            records.append(refreshed)
    if changed:
        _save(data)
    return json.dumps(sorted(records, key=lambda item: item.get("started_at", ""), reverse=True), indent=2)


def job_output(job_id: str, limit: int = 8000) -> str:
    record = get_job(job_id)
    if record is None:
        return f"ERROR: unknown job: {job_id}"
    limit = max(100, min(int(limit), 20000))
    sections = []
    for label, key in (("STDOUT", "stdout_file"), ("STDERR", "stderr_file")):
        try:
            content = Path(record[key]).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            content = f"ERROR: {exc}"
        sections.append(f"[{label}]\n{content[-limit:]}")
    return "\n".join(sections)
def stop_job(job_id: str) -> str:
    record = get_job(job_id)
    if record is None:
        return f"ERROR: unknown job: {job_id}"
    if record["status"] != "running":
        return f"JOB NOT RUNNING: {job_id} status={record['status']}"
    pid = int(record["pid"])
    try:
        if os.name == "nt":
            result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return f"ERROR: {result.stderr.strip() or result.stdout.strip()}"
        else:
            os.kill(pid, 15)
    except (OSError, ValueError) as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
    data = _load()
    record = data[job_id]
    record["status"] = "stopped"
    record["updated_at"] = _now()
    _save(data)
    return f"JOB STOPPED: {job_id}"


def restart_job(job_id: str) -> str:
    record = get_job(job_id)
    if record is None:
        return f"ERROR: unknown job: {job_id}"
    if record["status"] == "running":
        stopped = stop_job(job_id)
        if not stopped.startswith("JOB STOPPED:"):
            return stopped
    return start_job(record["command"])
