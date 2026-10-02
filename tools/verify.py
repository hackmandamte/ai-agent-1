"""Read-only verification tools for completed tasks."""
from pathlib import Path
import subprocess

from .files import safe_path


def verify_path_exists(path: str) -> str:
    try:
        target = safe_path(path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    return f"VERIFIED: exists={target.exists()} path={path}"


def verify_file_contains(path: str, text: str) -> str:
    try:
        target = safe_path(path)
        if not target.is_file():
            return f"ERROR: file does not exist: {path}"
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
    return f"VERIFIED: contains={text in content} path={path}"


def verify_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        return "ERROR: empty verification command"
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
    return (
        f"VERIFIED: exit_code={result.returncode}\n"
        f"{result.stdout}{result.stderr}"
    )


def verify_process_state(pid: int, expected_running: bool = True) -> str:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return "ERROR: invalid process PID"
    if pid <= 0:
        return "ERROR: invalid process PID"
    try:
        __import__("os").kill(pid, 0)
        running = True
    except OSError:
        running = False
    return f"VERIFIED: pid={pid} running={running} expected={expected_running} match={running == expected_running}"


def verify_job_state(job_id: str, expected_status: str | None = None) -> str:
    from .jobs import get_job
    record = get_job(job_id)
    if record is None:
        return f"ERROR: unknown job: {job_id}"
    status = record.get("status")
    match = expected_status is None or status == expected_status
    return f"VERIFIED: job_id={job_id} status={status} expected={expected_status} match={match} exit_code={record.get('exit_code')}"
