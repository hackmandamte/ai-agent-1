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
