"""Typed PC-control tools used by Agent 1.

These tools deliberately separate inspection from state-changing actions.
Destructive process termination and application launching require approval.
"""
from __future__ import annotations

import os
import platform
import signal
import subprocess
import time
from pathlib import Path

from .approval import ask_approval


def system_info() -> dict:
    return {
        "os": platform.platform(),
        "hostname": platform.node(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "cwd": str(Path.cwd().resolve()),
        "pid": os.getpid(),
    }


def list_processes(limit: int = 50) -> str:
    limit = max(1, min(int(limit), 200))
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-Command",
                   "Get-Process | Select-Object Id,ProcessName,CPU,WS | Sort-Object ProcessName | ConvertTo-Csv -NoTypeInformation"]
    else:
        command = ["ps", "-eo", "pid,comm,%cpu,%mem"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return f"ERROR: process listing failed: {result.stderr.strip()}"
    return "\n".join(result.stdout.splitlines()[: limit + 1])


def process_info(pid: int) -> str:
    pid = int(pid)
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-Command",
                   f"Get-Process -Id {pid} | Select-Object Id,ProcessName,CPU,WS,StartTime,Path | ConvertTo-Json -Compress"]
    else:
        command = ["ps", "-p", str(pid), "-o", "pid,ppid,comm,%cpu,%mem,etime"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return f"ERROR: process {pid} not found"
    return result.stdout.strip()


def terminate_process(pid: int, force: bool = False) -> str:
    pid = int(pid)
    if pid <= 0 or pid == os.getpid():
        return "ERROR: refusing to terminate the agent process or invalid PID"
    if not ask_approval(f"Terminate process {pid} (force={force})"):
        return "APPROVAL DENIED: process was not terminated."
    try:
        if os.name == "nt":
            command = ["taskkill", "/PID", str(pid)] + (["/F"] if force else [])
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return f"ERROR: {result.stderr.strip() or result.stdout.strip()}"
            return result.stdout.strip()
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        return f"Terminated process {pid}"
    except (OSError, ValueError) as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def launch_app(command: str, wait: bool = False) -> str:
    if not isinstance(command, str) or not command.strip():
        return "ERROR: empty application command"
    if not ask_approval(f"Launch application: {command}"):
        return "APPROVAL DENIED: application was not launched."
    try:
        process = subprocess.Popen(command, shell=True, cwd=Path.cwd())
        if wait:
            code = process.wait(timeout=120)
            return f"Application exited with code {code}"
        return f"Application launched with PID {process.pid}"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def start_background_job(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        return "ERROR: empty job command"
    if not ask_approval(f"Start background job: {command}"):
        return "APPROVAL DENIED: background job was not started."
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=Path.cwd(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return f"JOB PID: {process.pid}"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def job_status(pid: int) -> str:
    pid = int(pid)
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-Command",
                   f"Get-Process -Id {pid} | Select-Object Id,ProcessName,HasExited | ConvertTo-Json -Compress"]
    else:
        command = ["ps", "-p", str(pid), "-o", "pid,comm,stat,etime"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else f"JOB NOT RUNNING: {pid}"
