"""Local, deterministic safety policy for Supervisor Agent 2.

The online model is advisory only. This module remains the final local authority.
"""
from __future__ import annotations

from dataclasses import dataclass

BLOCKED_TOOLS = {
    "unknown_tool",
}

ALWAYS_APPROVAL_RISKS = {"WRITE", "DESTRUCTIVE", "HIGH_RISK"}

@dataclass(frozen=True)
class SupervisorDecision:
    verdict: str
    reason: str

def local_supervisor_floor(tool_name: str, risk: str, arguments: dict) -> SupervisorDecision:
    """Apply deterministic rules that an online model cannot override."""
    if tool_name in BLOCKED_TOOLS:
        return SupervisorDecision("BLOCK", f"Tool '{tool_name}' is not permitted.")

    if risk == "DESTRUCTIVE":
        return SupervisorDecision(
            "APPROVAL_REQUIRED",
            "Destructive actions always require explicit human approval.",
        )

    if risk == "HIGH_RISK":
        return SupervisorDecision(
            "APPROVAL_REQUIRED",
            "High-risk actions always require explicit human approval.",
        )

    if risk == "WRITE":
        return SupervisorDecision(
            "APPROVAL_REQUIRED",
            "Changes to local state require explicit human approval.",
        )

    return SupervisorDecision("ALLOW", "Read-only action.")
