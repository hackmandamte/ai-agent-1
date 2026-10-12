"""Thin client for the remote Supervisor Agent 2.

Agent 1 never loads or runs the supervisor model. It sends a sanitized action
proposal to the remote supervisor service and receives only a verdict.
Local policy and the local human approval gate remain authoritative.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any

from supervisor_policy import SupervisorDecision, local_supervisor_floor
from task_authorization import TaskAuthorization

def _load_local_env() -> None:
    """Load optional local Agent 1 supervisor settings without a dependency."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except OSError:
        return


_load_local_env()

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
]


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text[:5000]


def _remote_review(goal: str, tool_name: str, arguments: dict, risk: str, authorization: TaskAuthorization | None = None, task_context: dict | None = None) -> SupervisorDecision:
    """Call the independent online Agent 2 service."""
    url = os.getenv("SUPERVISOR_URL", "https://supervisorservice.vercel.app/api").strip()
    token = os.getenv("SUPERVISOR_CLIENT_TOKEN", "").strip()

    if not url:
        return SupervisorDecision("UNAVAILABLE", "Remote Supervisor Agent 2 is not configured.")

    payload = {
        "goal": str(goal)[:4000],
        "tool": str(tool_name)[:200],
        "risk": str(risk)[:100],
        "arguments": _redact(arguments),
        "task_authorization": authorization.snapshot() if authorization else None,
        "task_context": _redact(task_context) if task_context else None,
    }

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return SupervisorDecision("UNAVAILABLE", f"Remote supervisor request failed: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return SupervisorDecision("UNAVAILABLE", f"Remote supervisor request failed: {type(exc).__name__}")

    verdict = str(body.get("verdict", "")).upper()
    reason = str(body.get("reason", "No reason supplied."))[:1000]

    if verdict not in {"ALLOW", "APPROVAL_REQUIRED", "BLOCK"}:
        return SupervisorDecision("UNAVAILABLE", "Remote supervisor returned an invalid verdict.")

    return SupervisorDecision(verdict, reason)


def review_action(goal: str, tool_name: str, arguments: dict, risk: str, authorization: TaskAuthorization | None = None, task_context: dict | None = None) -> SupervisorDecision:
    """Apply local hard stops, then let remote Agent 2 govern the authorized task."""
    floor = local_supervisor_floor(tool_name, risk, arguments)
    if floor.verdict == "BLOCK":
        return floor

    if authorization is not None:
        permitted, reason = authorization.permits(tool_name, arguments, risk)
        if not permitted:
            return SupervisorDecision("BLOCK", reason)

    remote = (
        _remote_review(goal, tool_name, arguments, risk, authorization, task_context)
        if authorization is not None
        else _remote_review(goal, tool_name, arguments, risk, task_context=task_context)
    )

    if remote.verdict == "BLOCK":
        return remote

    if remote.verdict == "UNAVAILABLE":
        if risk in {"WRITE", "DESTRUCTIVE", "HIGH_RISK"}:
            return SupervisorDecision(
                "BLOCK",
                "Remote Supervisor Agent 2 unavailable; refusing a side-effecting action.",
            )
        return floor

    if authorization is not None and authorization.auto_approve:
        return SupervisorDecision("ALLOW", remote.reason)

    if floor.verdict == "APPROVAL_REQUIRED" or remote.verdict == "APPROVAL_REQUIRED":
        return SupervisorDecision("APPROVAL_REQUIRED", f"{floor.reason} Supervisor: {remote.reason}"[:1500])

    return SupervisorDecision("ALLOW", remote.reason)
