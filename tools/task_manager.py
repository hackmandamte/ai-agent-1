"""Persistent task orchestration primitives for Agent 1.

The manager tracks one user goal across multiple model/tool steps. It does not
make tool decisions itself; the LLM remains the planner while this layer owns
state, retries, verification signals, and recovery metadata.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import uuid

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = WORKSPACE_ROOT / ".agent_state" / "tasks"

TERMINAL_STATES = {"completed", "failed"}
ACTIVE_STATES = {"pending", "running", "waiting"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    task_id: str
    goal: str
    status: str = "pending"
    current_step: int = 0
    max_steps: int = 30
    retry_budget: int = 2
    retries: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    last_error: str | None = None
    verified: bool = False
    plan: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)

    def snapshot(self) -> dict:
        return asdict(self)


class TaskStore:
    """JSON-backed task state store, scoped to the current workspace."""

    def __init__(self, root: Path = TASK_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        return self.root / f"{task_id}.json"

    def save(self, task: TaskRecord) -> None:
        task.updated_at = _now()
        target = self.path_for(task.task_id)
        target.write_text(
            json.dumps(task.snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, task_id: str) -> TaskRecord:
        data = json.loads(self.path_for(task_id).read_text(encoding="utf-8"))
        return TaskRecord(**data)

    def list(self) -> list[TaskRecord]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            try:
                records.append(self.load(path.stem))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return records

    def active(self) -> list[TaskRecord]:
        """Return non-terminal tasks, newest first."""
        return sorted(
            [task for task in self.list() if task.status in ACTIVE_STATES],
            key=lambda task: task.updated_at,
            reverse=True,
        )


class TaskManager:
    """Owns lifecycle transitions for a single multi-step agent task."""

    def __init__(self, store: TaskStore | None = None):
        self.store = store or TaskStore()
        self.task: TaskRecord | None = None

    def resume(self, task_id: str) -> TaskRecord:
        task = self.store.load(task_id)
        recoverable_completion = (
            task.status == "completed"
            and task.retries > 0
            and not task.verified
        )
        if task.status in TERMINAL_STATES and not recoverable_completion:
            raise ValueError(f"Task {task_id} is already {task.status}")
        task.status = "running"
        self.task = task
        self.store.save(task)
        return task

    def latest_active(self) -> TaskRecord | None:
        """Return the newest resumable task, including recoverable false completions."""
        candidates = self.store.active() + [
            task for task in self.store.list()
            if task.status == "completed" and task.retries > 0 and not task.verified
        ]
        return max(candidates, key=lambda task: task.updated_at) if candidates else None

    def find_resumable(self, goal: str) -> TaskRecord | None:
        """Prefer an exact goal match, then fall back to the newest resumable task."""
        candidates = self.store.active() + [
            task for task in self.store.list()
            if task.status == "completed" and task.retries > 0 and not task.verified
        ]
        if not candidates:
            return None
        for task in sorted(candidates, key=lambda item: item.updated_at, reverse=True):
            if task.goal.strip() == goal.strip():
                return task
        return max(candidates, key=lambda task: task.updated_at)

    def start(self, goal: str, max_steps: int = 30, retry_budget: int = 2) -> TaskRecord:
        task = TaskRecord(
            task_id=uuid.uuid4().hex,
            goal=goal,
            max_steps=max_steps,
            retry_budget=max(0, retry_budget),
            status="running",
        )
        self.task = task
        self.store.save(task)
        return task

    def set_plan(self, steps: list[dict]) -> None:
        task = self._require_task()
        task.plan = steps
        task.history.append({"event": "plan_set", "count": len(steps), "at": _now()})
        self.store.save(task)

    def update_plan_step(self, step_id: str, status: str) -> None:
        task = self._require_task()
        for item in task.plan:
            if item.get("id") == step_id:
                item["status"] = status
                break
        self.store.save(task)

    def save_messages(self, messages: list[dict]) -> None:
        task = self._require_task()
        task.messages = messages
        self.store.save(task)

    def mark_verified(self) -> None:
        task = self._require_task()
        task.verified = True
        task.history.append({"event": "verified", "at": _now()})
        self.store.save(task)

    def begin_step(self, step: int) -> None:
        task = self._require_task()
        task.current_step = step
        task.status = "running"
        task.history.append({"event": "step_started", "step": step, "at": _now()})
        self.store.save(task)

    def record_tool_result(self, name: str, result: str) -> bool:
        task = self._require_task()
        failed = isinstance(result, str) and (result.startswith("ERROR:") or result.startswith("APPROVAL DENIED:"))
        if name.startswith("verify_") and isinstance(result, str) and result.startswith("VERIFIED:"):
            task.verified = True
        if failed:
            task.retries += 1
            task.last_error = result[:2000]
            task.status = "waiting" if task.retries <= task.retry_budget else "failed"
        task.history.append({
            "event": "tool_result",
            "step": task.current_step,
            "tool": name,
            "ok": not failed,
            "result_preview": str(result)[:2000],
            "at": _now(),
        })
        self.store.save(task)
        return not failed or task.retries <= task.retry_budget

    def complete(self, message: str = "") -> None:
        task = self._require_task()
        task.status = "completed"
        task.last_error = None
        task.history.append({"event": "completed", "message": message[:2000], "at": _now()})
        self.store.save(task)

    def fail(self, error: str) -> None:
        task = self._require_task()
        task.status = "failed"
        task.last_error = str(error)[:2000]
        task.history.append({"event": "failed", "error": task.last_error, "at": _now()})
        self.store.save(task)

    def can_retry(self) -> bool:
        task = self._require_task()
        return task.retries <= task.retry_budget

    def _require_task(self) -> TaskRecord:
        if self.task is None:
            raise RuntimeError("No active task")
        return self.task
