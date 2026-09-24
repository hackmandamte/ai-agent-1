import os
import time
import requests

MODEL_COOLDOWNS = {}

def model_on_cooldown(model):
    return MODEL_COOLDOWNS.get(model, 0) > time.time()

def set_model_cooldown(model, delay):
    MODEL_COOLDOWNS[model] = time.time() + delay

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_CATALOG_URL = "https://openrouter.ai/api/v1/models"

EXCLUDED_MODELS = {
    "inclusionai/ling-3.0-flash-sante:free",
    "inclusionai/ling-3.0-flash-fin:free",
    "liquid/lfm-2.5-2.6b:free",
}

PREFERRED_MODELS = {
    "cohere/north-mini-code:free": 100,
    "poolside/laguna-s-2.1:free": 98,
    "poolside/laguna-xs-2.1:free": 94,
    "nex-agi/nex-n2.5-pro:free": 96,
    "nex-agi/nex-n2.5-mini:free": 90,
    "qwen/qwen3.8-27b:free": 92,
    "dots-studio/dots-3-note-preview:free": 88,
    "nvidia/nemotron-3-super-120b-a12b:free": 86,
    "nvidia/nemotron-3-ultra-550b-a55b:free": 85,
    "google/gemma-4-31b-it:free": 82,
    "google/gemma-4-26b-a4b-it:free": 80,
    "nvidia/nemotron-3.5-lightning:free": 75,
    "stealth/space-bunny-alpha": 78,
    "openrouter/free": 1,
}

def discover_models(key):
    response = requests.get(
        MODEL_CATALOG_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    response.raise_for_status()

    models = response.json().get("data", [])
    discovered = []

    for model in models:
        model_id = model.get("id", "")

        if model_id in EXCLUDED_MODELS:
            continue

        pricing = model.get("pricing", {})
        supported = model.get("supported_parameters", [])
        architecture = model.get("architecture", {})

        try:
            prompt_price = float(pricing.get("prompt", "-1"))
            completion_price = float(pricing.get("completion", "-1"))
        except (TypeError, ValueError):
            continue

        if prompt_price != 0 or completion_price != 0:
            continue

        if "tools" not in supported or "tool_choice" not in supported:
            continue

        if "text" not in architecture.get("output_modalities", []):
            continue

        if model.get("expiration_date"):
            continue

        score = PREFERRED_MODELS.get(model_id, 50)

        discovered.append((score, model_id))

    discovered.sort(reverse=True)

    return [model_id for score, model_id in discovered]

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

    try:
        models = discover_models(key)
    except requests.RequestException as e:
        print(f"[LLM] Model discovery failed: {type(e).__name__}: {e}")
        models = ["openrouter/free"]

    if not models:
        models = ["openrouter/free"]

    print(f"[LLM] Discovered {len(models)} eligible models")

    for index, model in enumerate(models, start=1):
        if model_on_cooldown(model):
            print(f"[LLM] Skipping {model} — still on cooldown")
            continue

        print(f"[LLM] Trying model {index}/{len(models)}: {model}")

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
                set_model_cooldown(model, delay)
                print(f"[LLM] {last_error} — cooling down for {delay:.1f}s")
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
