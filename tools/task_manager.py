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


class TaskManager:
    """Owns lifecycle transitions for a single multi-step agent task."""

    def __init__(self, store: TaskStore | None = None):
        self.store = store or TaskStore()
        self.task: TaskRecord | None = None

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

    def begin_step(self, step: int) -> None:
        task = self._require_task()
        task.current_step = step
        task.status = "running"
        task.history.append({"event": "step_started", "step": step, "at": _now()})
        self.store.save(task)

    def record_tool_result(self, name: str, result: str) -> bool:
        task = self._require_task()
        failed = isinstance(result, str) and (result.startswith("ERROR:") or result.startswith("APPROVAL DENIED:"))
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
