"""Task-level authorization for unattended Agent 1 runs.

The user authorizes a task once. Agent 2 still makes the remote decision; this
module only defines the local scope inside which an approved task may proceed
without an interactive human prompt.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class TaskAuthorization:
    mode: str = "unattended"
    workspace: str = ""
    auto_approve: bool = True
    allow_read: bool = True
    allow_write: bool = True
    allow_high_risk: bool = True
    allow_destructive: bool = True
    allow_external: bool = False

    def snapshot(self) -> dict:
        return asdict(self)

    def permits(self, tool_name: str, arguments: dict, risk: str) -> tuple[bool, str]:
        if self.mode != "unattended" or not self.auto_approve:
            return False, "Interactive approval mode is active."

        if risk == "READ" and self.allow_read:
            return True, "Read action is within task scope."

        if risk == "WRITE" and not self.allow_write:
            return False, "Write actions are outside the task authorization."

        if risk == "HIGH_RISK" and not self.allow_high_risk:
            return False, "High-risk actions are outside the task authorization."

        if risk == "DESTRUCTIVE" and not self.allow_destructive:
            return False, "Destructive actions are outside the task authorization."

        if tool_name.startswith("mcp__") and not self.allow_external:
            return False, "External MCP actions are not authorized by this task."

        if risk not in {"READ", "WRITE", "HIGH_RISK", "DESTRUCTIVE"}:
            return False, f"Unknown risk class: {risk}"

        if risk in {"WRITE", "DESTRUCTIVE"}:
            reason = self._workspace_reason(arguments)
            if reason:
                return False, reason

        return True, "Action is within the task authorization."

    def _workspace_reason(self, arguments: dict) -> str | None:
        if not self.workspace:
            return "No authorized workspace is configured."

        root = Path(self.workspace).resolve(strict=False)
        for key in ("path", "source", "destination"):
            if key not in arguments:
                continue
            try:
                target = Path(str(arguments[key])).expanduser().resolve(strict=False)
                if target != root and root not in target.parents:
                    return f"Path is outside the authorized workspace: {target}"
            except (OSError, RuntimeError, ValueError):
                return f"Invalid filesystem path: {arguments[key]}"
        return None
