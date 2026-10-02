"""Authenticated Agent 1 HTTP control plane for remote clients."""
from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from agent import agent
from tools.task_manager import TaskManager

MAX_GOAL_LENGTH = 12000
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
_AGENT_THREADS = {}
_AGENT_THREADS_LOCK = threading.Lock()


def _token():
    value = os.environ.get("AGENT_API_TOKEN", "").strip()
    if not value:
        raise RuntimeError("AGENT_API_TOKEN is required")
    return value


def _authorized(headers):
    raw = headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        return False
    supplied = raw[7:].strip()
    return bool(supplied) and secrets.compare_digest(supplied, _token())


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _task_payload(task):
    return {
        "task_id": task.task_id,
        "goal": task.goal,
        "status": task.status,
        "current_step": task.current_step,
        "max_steps": task.max_steps,
        "verified": task.verified,
        "last_error": task.last_error,
        "history": task.history[-20:],
    }


def _start_task(goal, max_steps):
    manager = TaskManager()
    task = manager.start(goal, max_steps=max_steps)
    task_id = task.task_id

    def worker():
        try:
            agent(goal, max_steps=max_steps, resume_task_id=task_id)
        finally:
            with _AGENT_THREADS_LOCK:
                _AGENT_THREADS.pop(task_id, None)

    thread = threading.Thread(target=worker, name=f"agent-{task_id}", daemon=True)
    with _AGENT_THREADS_LOCK:
        _AGENT_THREADS[task_id] = thread
    thread.start()
    return task_id
class AgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "Agent1HTTP/1.0"

    def log_message(self, format, *args):
        return

    def _send(self, status, payload):
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 256 * 1024:
                return None
            raw = self.rfile.read(length)
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else None
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, {"status": "ok", "service": "agent1"})
            return

        if not _authorized(self.headers):
            self._send(401, {"error": "unauthorized"})
            return

        if path.startswith("/tasks/"):
            task_id = path[len("/tasks/"):].strip()
            if not task_id or "/" in task_id:
                self._send(400, {"error": "invalid task id"})
                return
            try:
                task = TaskManager().store.load(task_id)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                self._send(404, {"error": "task not found"})
                return
            self._send(200, _task_payload(task))
            return

        self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not _authorized(self.headers):
            self._send(401, {"error": "unauthorized"})
            return

        if path != "/tasks":
            self._send(404, {"error": "not found"})
            return

        payload = self._read_json()
        if payload is None:
            self._send(400, {"error": "invalid JSON body"})
            return

        goal = payload.get("goal")
        max_steps = payload.get("max_steps", 30)
        if not isinstance(goal, str) or not goal.strip():
            self._send(400, {"error": "goal must be a non-empty string"})
            return
        if len(goal) > MAX_GOAL_LENGTH:
            self._send(400, {"error": "goal is too long"})
            return
        if not isinstance(max_steps, int) or isinstance(max_steps, bool) or not 1 <= max_steps <= 100:
            self._send(400, {"error": "max_steps must be an integer from 1 to 100"})
            return

        try:
            task_id = _start_task(goal.strip(), max_steps)
        except Exception as exc:
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._send(202, {"task_id": task_id, "status": "running"})


def serve(host=None, port=None):
    bind_host = host or os.environ.get("AGENT_API_HOST", DEFAULT_HOST)
    bind_port = int(port or os.environ.get("AGENT_API_PORT", DEFAULT_PORT))
    _token()
    server = ThreadingHTTPServer((bind_host, bind_port), AgentRequestHandler)
    print(f"Agent 1 API listening on http://{bind_host}:{bind_port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
