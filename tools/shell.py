import shlex
import subprocess

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

    result = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
    )

    output = result.stdout + result.stderr
    return f"EXIT CODE: {result.returncode}\n{output}"
