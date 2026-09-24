import os
import time
import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [
    "cohere/north-mini-code:free",
    "poolside/laguna-s-2.1:free",
    "qwen/qwen3.8-27b:free",
    "nex-agi/nex-n2.5-pro:free",
    "dots-studio/dots-3-note-preview:free",
    "openrouter/free",
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write complete text content to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent Git commit history.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create a Git commit with all current changes. This is a high-impact action and requires user approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                },
                "required": ["message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git working tree status.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show current git changes.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]


def ask(messages):
    key = os.environ["OPENROUTER_API_KEY"]

    last_error = None

    for index, model in enumerate(MODELS, start=1):
        print(f"[LLM] Trying model {index}/{len(MODELS)}: {model}")

        try:
            response = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                },
                timeout=120,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")

                try:
                    delay = min(float(retry_after), 10.0) if retry_after else 2.0
                except ValueError:
                    delay = 2.0

                last_error = f"{model}: HTTP 429"
                print(f"[LLM] {last_error} — waiting {delay:.1f}s before fallback")
                time.sleep(delay)
                continue

            if response.status_code == 404 or response.status_code >= 500:
                last_error = f"{model}: HTTP {response.status_code}"
                print(f"[LLM] {last_error} — trying fallback")
                continue

            if response.status_code in {401, 403}:
                return {
                    "role": "assistant",
                    "content": (
                        f"LLM authentication/access failure: "
                        f"HTTP {response.status_code}"
                    )
                }

            response.raise_for_status()

            data = response.json()

            if not data.get("choices"):
                last_error = f"{model}: response contained no choices"
                print(f"[LLM] {last_error} — trying fallback")
                continue

            print(f"[LLM] Using: {model}")
            return data["choices"][0]["message"]

        except requests.RequestException as e:
            last_error = f"{model}: {type(e).__name__}: {e}"
            print(f"[LLM] {last_error} — trying fallback")

    return {
        "role": "assistant",
        "content": (
            "All configured LLM models failed. "
            f"Last error: {last_error}"
        )
    }
