"""Local llama.cpp OpenAI-compatible provider."""
import json
import os
import subprocess

class _LocalResponse:
    def __init__(self, payload, status_code=200): self._payload, self.status_code = payload, status_code
    def json(self): return self._payload

class LocalLlamaProvider:
    name = "local_llama"
    def __init__(self, tools=None):
        self.tools = tools or []
        self.base_url = os.environ.get("LLAMA_BASE_URL", "http://127.0.0.1:8080/v1")
        self.model = os.environ.get("LLAMA_MODEL", "Qwen3.5-4B-Q5_K_M")
        self.tool_mode = os.environ.get("LLAMA_TOOL_MODE", "prompt_json").strip().lower()

    def discover_models(self): return [self.model]

    def _tool_prompt(self):
        definitions = []
        for item in self.tools:
            if not isinstance(item, dict):
                continue
            fn = item.get("function", {})
            if not isinstance(fn, dict) or not isinstance(fn.get("name"), str):
                continue
            params = fn.get("parameters", {"type": "object", "properties": {}})
            if isinstance(params, dict):
                properties = params.get("properties", {})
                properties = properties if isinstance(properties, dict) else {}
                definitions.append({
                    "name": fn["name"],
                    "required": params.get("required", []),
                    "arguments": sorted(properties.keys()),
                })
            else:
                definitions.append({"name": fn["name"], "required": [], "arguments": []})
        catalog = " ".join(
            f"{item['name']}({','.join(item['required'])})" for item in definitions
        )
        return (
            "You are controlling a software agent. Available tools are listed as name(required_args). "
            "When a tool is needed, output ONLY: {\"tool\":\"NAME\",\"arguments\":{}}. "
            "Arguments must be a JSON object. No markdown, XML, or explanation in a tool request. "
            "If no tool is needed, answer normally. AVAILABLE_TOOLS=" + catalog
        )

    def _prompt_mode_messages(self, messages):
        output = []
        instruction = self._tool_prompt()
        for index, message in enumerate(messages if isinstance(messages, list) else []):
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content") or ""
            if role == "system":
                content = str(content) + "\n\n" + instruction
                output.append({"role": "system", "content": content})
            elif role == "assistant" and message.get("tool_calls"):
                calls = []
                for call in message.get("tool_calls", []):
                    fn = call.get("function", {}) if isinstance(call, dict) else {}
                    if isinstance(fn, dict):
                        calls.append({"tool": fn.get("name"), "arguments": fn.get("arguments", "{}")})
                output.append({"role": "assistant", "content": json.dumps(calls, ensure_ascii=False)})
            elif role == "tool":
                name = message.get("name", "unknown_tool")
                output.append({"role": "user", "content": f"TOOL_RESULT {name}: {content}"})
            elif role in {"user", "assistant"}:
                output.append({"role": role, "content": str(content)})
        return output

    def call_model(self, model, messages):
        prompt_mode = self.tool_mode in {"prompt_json", "json", "compat"} and bool(self.tools)
        request_messages = self._prompt_mode_messages(messages) if prompt_mode else messages
        payload = {
            "model": model,
            "messages": request_messages,
            "temperature": 0.1,
            "max_tokens": 64 if prompt_mode else 128,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if not prompt_mode:
            payload["tools"] = self.tools
        try:
            encoded = json.dumps(payload, ensure_ascii=False)
            command = "$body=[Console]::In.ReadToEnd(); Invoke-RestMethod -Uri '" + self.base_url + "/chat/completions' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 30 -Compress"
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                input=encoded,
                capture_output=True,
                text=True,
                timeout=305,
                check=False,
            )
            if result.returncode != 0:
                return {"status":"error", "error":result.stderr.strip() or result.stdout.strip()}
            return {"status":"response", "response":_LocalResponse(json.loads(result.stdout))}
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            return {"status":"error", "error":str(exc)}
