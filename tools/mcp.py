"""Minimal MCP client for local stdio servers.

The agent owns MCP sessions and exposes discovered MCP tools to local Qwen.
Configuration lives in mcp_servers.json at the workspace root.
"""
import json
import os
import queue
import subprocess
import threading
from pathlib import Path

WORKSPACE_ROOT = Path.cwd().resolve()
CONFIG_PATH = WORKSPACE_ROOT / "mcp_servers.json"
PROTOCOL_VERSION = "2024-11-05"
_REQUEST_TIMEOUT = 15


class MCPServer:
    def __init__(self, name, config):
        self.name = name
        self.config = config
        self.process = None
        self.messages = queue.Queue()
        self.next_id = 1
        self.reader = None
        self.tools = []
    def start(self):
        if self.process and self.process.poll() is None:
            return

        command = self.config.get("command")
        args = self.config.get("args", [])
        if not isinstance(command, str) or not command:
            raise ValueError(f"MCP server {self.name!r} has no command")
        if not isinstance(args, list):
            raise ValueError(f"MCP server {self.name!r} args must be a list")

        env = os.environ.copy()
        configured_env = self.config.get("env", {})
        if isinstance(configured_env, dict):
            env.update({str(k): str(v) for k, v in configured_env.items()})

        self.process = subprocess.Popen(
            [command, *[str(a) for a in args]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
            cwd=str(WORKSPACE_ROOT),
        )
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()
        self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "Agent 1", "version": "1.0"},
        })
        self._notify("notifications/initialized", {})
    def _read_loop(self):
        try:
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except (OSError, ValueError):
            return

    def _notify(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def _request(self, method, params):
        request_id = self.next_id
        self.next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

        deadline = __import__("time").time() + _REQUEST_TIMEOUT
        while __import__("time").time() < deadline:
            try:
                message = self.messages.get(timeout=0.5)
            except queue.Empty:
                continue
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message.get("result", {})
        raise TimeoutError(f"MCP server {self.name!r} timed out on {method}")
    def discover_tools(self):
        self.start()
        result = self._request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        self.tools = [tool for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)]
        return self.tools

    def call_tool(self, name, arguments):
        self.start()
        result = self._request("tools/call", {
            "name": name,
            "arguments": arguments if isinstance(arguments, dict) else {},
        })
        content = result.get("content", []) if isinstance(result, dict) else []
        if not content:
            return "(empty MCP tool result)"

        parts = []
        for item in content:
            if not isinstance(item, dict):
                parts.append(str(item))
            elif item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(parts)

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.process = None
_SERVERS = {}
_TOOL_INDEX = {}


def _load_config():
    configs = [CONFIG_PATH, WORKSPACE_ROOT / "mcp_servers.local.json"]
    merged = {}
    for path in configs:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        servers = payload.get("servers", {}) if isinstance(payload, dict) else {}
        if isinstance(servers, dict):
            merged.update(servers)
    return merged


def _refresh():
    _TOOL_INDEX.clear()
    for name, config in _load_config().items():
        if not isinstance(config, dict):
            continue
        server = _SERVERS.setdefault(name, MCPServer(name, config))
        try:
            for tool in server.discover_tools():
                qualified = f"mcp__{name}__{tool['name']}"
                _TOOL_INDEX[qualified] = (server, tool["name"], tool)
        except Exception:
            continue


def get_mcp_tool_definitions():
    """Return OpenAI-compatible tool schemas for configured MCP servers."""
    _refresh()
    definitions = []
    for qualified, (_, _, tool) in _TOOL_INDEX.items():
        definitions.append({
            "type": "function",
            "function": {
                "name": qualified,
                "description": tool.get("description", f"MCP tool {qualified}"),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        })
    return definitions


def execute_mcp_tool(qualified_name, arguments):
    """Execute a previously discovered qualified MCP tool."""
    entry = _TOOL_INDEX.get(qualified_name)
    if entry is None:
        _refresh()
        entry = _TOOL_INDEX.get(qualified_name)
    if entry is None:
        return f"ERROR: Unknown MCP tool: {qualified_name}"
    server, tool_name, _ = entry
    try:
        return server.call_tool(tool_name, arguments)
    except Exception as exc:
        return f"ERROR: MCP tool failed: {type(exc).__name__}: {exc}"
def is_mcp_tool(name):
    return isinstance(name, str) and name.startswith("mcp__")


def close_all():
    for server in _SERVERS.values():
        server.close()
    _SERVERS.clear()
    _TOOL_INDEX.clear()
