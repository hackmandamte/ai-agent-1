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
    def discover_models(self): return [self.model]
    def call_model(self, model, messages):
        payload = {"model": model, "messages": messages, "tools": self.tools, "temperature": 0.2, "max_tokens": 128, "chat_template_kwargs": {"enable_thinking": False}}
        try:
            encoded = json.dumps(payload, ensure_ascii=False)
            # Keep the request body out of the PowerShell command line. Windows has
            # a command-line length limit, and large tool schemas/history can exceed it.
            command = "$body=[Console]::In.ReadToEnd(); Invoke-RestMethod -Uri '" + self.base_url + "/chat/completions' -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 30 -Compress"
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                input=encoded,
                capture_output=True,
                text=True,
                timeout=305,
                check=False,
            )
            if result.returncode != 0: return {"status":"error", "error":result.stderr.strip() or result.stdout.strip()}
            return {"status":"response", "response":_LocalResponse(json.loads(result.stdout))}
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            return {"status":"error", "error":str(exc)}
