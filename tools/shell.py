import shlex
import subprocess
from pathlib import Path

from .approval import ask_approval

WORKSPACE_ROOT = Path.cwd().resolve()

BLOCKED_COMMANDS = {
    "rm",
    "rmdir",
    "mkfs",
    "dd",
    "shutdown",
    "reboot",
    "poweroff",
    "su",
    "sudo",
}

APPROVAL_COMMANDS = {
    "python",
    "python3",
    "sh",
    "bash",
    "curl",
    "wget",
    "git",
}


def run(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"ERROR: Invalid command syntax: {e}"

    if not parts:
        return "ERROR: Empty command"

    executable = parts[0]

    if executable in BLOCKED_COMMANDS:
        return f"ERROR: Command blocked for safety: {executable}"

    normalized = " ".join(parts)

    if normalized in {"python agent.py", "python3 agent.py"}:
        return "ERROR: Recursive agent execution blocked."

    if executable in APPROVAL_COMMANDS:
        if not ask_approval(f"Shell command: {command}"):
            return "APPROVAL DENIED: Shell command was not executed."

    result = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
        cwd=WORKSPACE_ROOT,
    )

    output = result.stdout + result.stderr
    return f"EXIT CODE: {result.returncode}\n{output}"
