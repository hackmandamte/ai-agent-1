"""Centralized tool risk classification and approval policy."""
from __future__ import annotations

import shlex

READ = "READ"
WRITE = "WRITE"
DESTRUCTIVE = "DESTRUCTIVE"
HIGH_RISK = "HIGH_RISK"

READ_TOOLS = {
    "list_files", "read_file", "git_status", "git_diff", "git_log",
    "get_runtime_info", "web_fetch", "verify_path_exists",
    "verify_file_contains", "system_info", "list_processes",
    "process_info", "process_tree", "job_status", "list_jobs", "job_output", "discover_apps", "disk_usage", "network_state", "listening_ports", "environment_info", "verify_process_state", "verify_job_state",
}

WRITE_TOOLS = {"write_file", "create_directory", "copy_path", "move_path"}

HIGH_RISK_TOOLS = {"git_commit", "launch_app", "launch_app_id", "start_background_job", "start_job", "restart_job"}
DESTRUCTIVE_TOOLS = {"terminate_process", "stop_job", "delete_path"}

MCP_BROWSER_READ_TOOLS = {
    "browser_navigate", "browser_snapshot", "browser_wait_for",
    "browser_network_requests", "browser_console_messages", "browser_close",
}

DESTRUCTIVE_COMMANDS = {
    "rm", "rmdir", "del", "erase", "format", "mkfs", "dd", "shutdown",
    "reboot", "poweroff", "taskkill", "kill", "stop-process", "remove-item",
}

APPROVAL_COMMANDS = {"python", "python3", "sh", "bash", "curl", "wget", "git"}


def classify_shell_command(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return HIGH_RISK
    if not parts:
        return READ
    executable = parts[0].lower().split("\\\\")[-1].split("/")[-1]
    if executable.endswith(".exe"):
        executable = executable[:-4]
    tokens = {part.lower().lstrip("-/") for part in parts[1:]}
    if executable in DESTRUCTIVE_COMMANDS or tokens.intersection(DESTRUCTIVE_COMMANDS):
        return DESTRUCTIVE
    if executable in APPROVAL_COMMANDS or executable in {"powershell", "cmd"}:
        return HIGH_RISK
    return READ


def classify_tool(name: str, arguments: dict | None = None) -> str:
    arguments = arguments or {}
    if name == "shell":
        return classify_shell_command(str(arguments.get("command", "")))
    if name == "verify_command":
        return HIGH_RISK
    if name in DESTRUCTIVE_TOOLS:
        return DESTRUCTIVE
    if name in HIGH_RISK_TOOLS:
        return HIGH_RISK
    if name in WRITE_TOOLS:
        return WRITE
    if name in READ_TOOLS:
        return READ
    if name == "set_task_plan":
        return READ
    if name.startswith("mcp__"):
        mcp_tool = name.rsplit("__", 1)[-1]
        if mcp_tool in MCP_BROWSER_READ_TOOLS:
            return READ
        return HIGH_RISK
    return HIGH_RISK


def requires_approval(risk: str) -> bool:
    return risk in {WRITE, DESTRUCTIVE, HIGH_RISK}


def approval_message(name: str, arguments: dict, risk: str) -> str:
    if name == "write_file":
        return f"Write file: {arguments.get('path', '<unknown path>')}"
    if name == "verify_command":
        return f"Run verification command [{risk}]: {arguments.get('command', '')}"
    if name == "shell":
        return f"Shell command [{risk}]: {arguments.get('command', '')}"
    if name == "set_task_plan":
        return "Modify persisted task plan"
    return f"{risk} action: {name}"
def policy_result(name: str, arguments: dict | None = None) -> tuple[str, bool, str]:
    """Return (risk, approval_required, human-readable approval message)."""
    risk = classify_tool(name, arguments)
    return risk, requires_approval(risk), approval_message(name, arguments or {}, risk)
