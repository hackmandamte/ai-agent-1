"""Typed PC-control tools used by Agent 1.

These tools deliberately separate inspection from state-changing actions.
Destructive process termination and application launching require approval.
"""
from __future__ import annotations

import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path



def system_info() -> dict:
    return {
        "os": os.name,
        "hostname": os.environ.get("COMPUTERNAME", ""),
        "architecture": os.environ.get("PROCESSOR_ARCHITECTURE", ""),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "cwd": str(Path.cwd().resolve()),
        "pid": os.getpid(),
    }


def list_processes(limit: int = 50) -> str:
    limit = max(1, min(int(limit), 200))
    if os.name == "nt":
        command = ["tasklist", "/FO", "CSV", "/NH"]
    else:
        command = ["ps", "-eo", "pid,comm,%cpu,%mem"]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout = process.stdout.read() if process.stdout else ""
        stderr = process.stderr.read() if process.stderr else ""
        returncode = process.wait(timeout=15)
    except Exception as exc:
        return f"ERROR: process listing failed: {type(exc).__name__}: {exc}"
    if returncode != 0:
        return f"ERROR: process listing failed: {stderr.strip()}"
    return "\n".join(stdout.splitlines()[:limit])


def process_info(pid: int) -> str:
    pid = int(pid)
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-Command",
                   f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
                   "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,CreationDate | "
                   "ConvertTo-Json -Compress"]
    else:
        command = ["ps", "-p", str(pid), "-o", "pid,ppid,comm,%cpu,%mem,etime,args"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode != 0 or not result.stdout.strip():
        return f"ERROR: process {pid} not found"
    return result.stdout.strip()


def process_tree(pid: int, max_depth: int = 4) -> str:
    pid = int(pid)
    max_depth = max(1, min(int(max_depth), 8))
    if os.name != "nt":
        return process_info(pid)
    command = (
        "$all=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name; "
        f"$root={pid}; $depth=@{{ $root=0 }}; "
        "$changed=$true; while($changed){$changed=$false; foreach($p in $all){"
        "if($depth.ContainsKey([int]$p.ParentProcessId) -and -not $depth.ContainsKey([int]$p.ProcessId)){"
        "$d=$depth[[int]$p.ParentProcessId]+1; if($d -le " + str(max_depth) + "){$depth[[int]$p.ProcessId]=$d;$changed=$true}}}}; "
        "$all | Where-Object {$depth.ContainsKey([int]$_.ProcessId)} | "
        "Sort-Object {$depth[[int]$_.ProcessId]},ProcessId | ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=20)
    if result.returncode != 0 or not result.stdout.strip():
        return f"ERROR: process tree unavailable for {pid}"
    return result.stdout.strip()


def terminate_process(pid: int, force: bool = False) -> str:
    pid = int(pid)
    if pid <= 0 or pid == os.getpid():
        return "ERROR: refusing to terminate the agent process or invalid PID"
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
