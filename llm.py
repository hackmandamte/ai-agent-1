"""LLM orchestration layer: provider-neutral routing and request sanitization."""
import copy
import json
from providers.local_llama_provider import LocalLlamaProvider
from tools.mcp import get_mcp_tool_definitions
from tools.web import web_fetch_definition

LOCAL_LLAMA = "local_llama"
UNKNOWN_TOOL_CALL_ID = "unknown"

TOOLS = [
    {"type":"function","function":{"name":"set_task_plan","description":"Create an ordered task plan with dependency relationships before complex work.","parameters":{"type":"object","properties":{"steps":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"goal":{"type":"string"},"depends_on":{"type":"array","items":{"type":"string"}}},"required":["id","goal"]}}},"required":["steps"]}}},
    {"type":"function","function":{"name":"list_files","description":"List files and directories.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"read_file","description":"Read a text file.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"write_file","description":"Write complete text content to a file. Requires user approval.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    {"type":"function","function":{"name":"create_directory","description":"Create a workspace directory. Requires user approval.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"copy_path","description":"Copy a workspace file or directory. Requires user approval.","parameters":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"]}}},
    {"type":"function","function":{"name":"move_path","description":"Move or rename a workspace file or directory. Requires user approval.","parameters":{"type":"object","properties":{"source":{"type":"string"},"destination":{"type":"string"}},"required":["source","destination"]}}},
    {"type":"function","function":{"name":"delete_path","description":"Delete a workspace file or directory. Requires user approval.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"shell","description":"Run a shell command.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
    {"type":"function","function":{"name":"git_log","description":"Show recent Git commit history.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"git_commit","description":"Create a Git commit with all current changes. This is a high-impact action and requires user approval.","parameters":{"type":"object","properties":{"message":{"type":"string"}},"required":["message"]}}},
    {"type":"function","function":{"name":"git_status","description":"Show git working tree status.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"git_diff","description":"Show current git changes.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"get_runtime_info","description":"Return runtime environment information.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"verify_path_exists","description":"Verify that a workspace path exists.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"verify_file_contains","description":"Verify that a workspace text file contains exact text.","parameters":{"type":"object","properties":{"path":{"type":"string"},"text":{"type":"string"}},"required":["path","text"]}}},
    {"type":"function","function":{"name":"verify_command","description":"Run a verification command and report its exit code. Requires user approval.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
    {"type":"function","function":{"name":"verify_process_state","description":"Verify whether a process is currently running.","parameters":{"type":"object","properties":{"pid":{"type":"integer"},"expected_running":{"type":"boolean"}},"required":["pid"]}}},
    {"type":"function","function":{"name":"verify_job_state","description":"Verify the persisted status and exit code of a background job.","parameters":{"type":"object","properties":{"job_id":{"type":"string"},"expected_status":{"type":"string"}},"required":["job_id"]}}},
    {"type":"function","function":{"name":"system_info","description":"Inspect basic PC runtime information.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"disk_usage","description":"Inspect disk capacity and free space for a workspace path.","parameters":{"type":"object","properties":{"path":{"type":"string"}}}}},
    {"type":"function","function":{"name":"network_state","description":"Inspect Windows network interface configuration without changing it.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"listening_ports","description":"List TCP listening ports and owning process IDs.","parameters":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":500}}}}},
    {"type":"function","function":{"name":"environment_info","description":"Return sanitized non-secret runtime environment metadata.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"list_processes","description":"List running processes for inspection.","parameters":{"type":"object","properties":{"limit":{"type":"integer","minimum":1,"maximum":200}}}}},
    {"type":"function","function":{"name":"process_info","description":"Inspect one running process with parent, executable, command-line, and start metadata.","parameters":{"type":"object","properties":{"pid":{"type":"integer"}},"required":["pid"]}}},
    {"type":"function","function":{"name":"process_tree","description":"Inspect the parent/child process tree rooted at a PID.","parameters":{"type":"object","properties":{"pid":{"type":"integer"},"max_depth":{"type":"integer","minimum":1,"maximum":8}},"required":["pid"]}}},
    {"type":"function","function":{"name":"terminate_process","description":"Terminate a process. Requires user approval.","parameters":{"type":"object","properties":{"pid":{"type":"integer"},"force":{"type":"boolean"}},"required":["pid"]}}},
    {"type":"function","function":{"name":"launch_app","description":"Legacy arbitrary application launch. Requires user approval.","parameters":{"type":"object","properties":{"command":{"type":"string"},"wait":{"type":"boolean"}},"required":["command"]}}},
    {"type":"function","function":{"name":"discover_apps","description":"Discover installed Windows Start-menu applications without launching them.","parameters":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":500}}}}},
    {"type":"function","function":{"name":"launch_app_id","description":"Launch a discovered Windows application by exact AppID. Requires user approval.","parameters":{"type":"object","properties":{"app_id":{"type":"string"}},"required":["app_id"]}}},
    {"type":"function","function":{"name":"start_background_job","description":"Start a long-running PC command in the background. Requires user approval.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
    {"type":"function","function":{"name":"job_status","description":"Inspect a legacy background job by PID.","parameters":{"type":"object","properties":{"pid":{"type":"integer"}},"required":["pid"]}}},
    {"type":"function","function":{"name":"start_job","description":"Start a persistent background job and return a stable job ID. Requires user approval.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
    {"type":"function","function":{"name":"get_job","description":"Get persistent background job metadata by stable job ID.","parameters":{"type":"object","properties":{"job_id":{"type":"string"}},"required":["job_id"]}}},
    {"type":"function","function":{"name":"list_jobs","description":"List persistent background jobs and their current status.","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"job_output","description":"Read captured stdout and stderr for a persistent job.","parameters":{"type":"object","properties":{"job_id":{"type":"string"},"limit":{"type":"integer","minimum":100,"maximum":20000}},"required":["job_id"]}}},
    {"type":"function","function":{"name":"stop_job","description":"Stop a persistent background job by stable job ID. Requires user approval.","parameters":{"type":"object","properties":{"job_id":{"type":"string"}},"required":["job_id"]}}},
    {"type":"function","function":{"name":"restart_job","description":"Restart a persistent background job by stable job ID. Requires user approval.","parameters":{"type":"object","properties":{"job_id":{"type":"string"}},"required":["job_id"]}}},
]

_PROVIDER = LocalLlamaProvider()


def _current_tools():
    return TOOLS + [web_fetch_definition()] + get_mcp_tool_definitions()


def reset_session_state():
    return None


def enabled_providers():
    return (LOCAL_LLAMA,)


def model_on_cooldown(model):
    return False


def set_model_cooldown(model, delay):
    return None


def sanitize_tool_arguments(raw):
    if not isinstance(raw, str) or not raw.strip():
        return "{}"
    # Tool-call arguments are strings in the OpenAI-compatible schema. Preserve
    # malformed JSON verbatim so the agent can show the model exactly what failed
    # and request a corrected regeneration on the next turn.
    return raw


def normalize_tool_call(call, default_id=UNKNOWN_TOOL_CALL_ID, used_ids=None):
    result = {
        "id": default_id,
        "type": "function",
        "function": {"name": "unknown_tool", "arguments": "{}"},
    }
    if isinstance(call, dict):
        raw_id = call.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            result["id"] = raw_id
        function = call.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name:
                result["function"]["name"] = name
            result["function"]["arguments"] = sanitize_tool_arguments(function.get("arguments"))
    if used_ids is not None:
        original = result["id"]
        candidate = original
        counter = 2
        while candidate in used_ids:
            candidate = f"{original}_{counter}"
            counter += 1
        result["id"] = candidate
        used_ids.add(candidate)
    return result


def _tool_content(content):
    if isinstance(content, str):
        return content if content.strip() else "(empty tool result)"
    if content is None:
        return "(empty tool result)"
    try:
        encoded = json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        encoded = str(content)
    return encoded if encoded.strip() else "(empty tool result)"
def sanitize_messages_for_request(history):
    output = []
    pending_calls = {}
    used_ids = set()

    for message in history if isinstance(history, list) else []:
        if not isinstance(message, dict):
            continue

        role = message.get("role")

        if role == "assistant":
            clean = {"role": "assistant", "content": message.get("content") or ""}
            calls = message.get("tool_calls")
            pending_calls = {}

            if isinstance(calls, list) and calls:
                normalized = []
                turn_ids = set()

                for call in calls:
                    item = normalize_tool_call(call, UNKNOWN_TOOL_CALL_ID, turn_ids)
                    if item["id"] in used_ids:
                        base_id = item["id"]
                        n = 2
                        while f"{base_id}_{n}" in used_ids:
                            n += 1
                        item["id"] = f"{base_id}_{n}"
                    used_ids.add(item["id"])
                    normalized.append(item)
                    pending_calls[item["id"]] = item

                clean["tool_calls"] = normalized

            output.append(clean)
            continue

        if role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id.strip():
                continue
            if call_id not in pending_calls:
                continue

            clean = {
                "role": "tool",
                "tool_call_id": call_id,
                "content": _tool_content(message.get("content")),
            }

            name = message.get("name")
            if isinstance(name, str) and name:
                clean["name"] = name

            output.append(clean)
            pending_calls.pop(call_id, None)
            continue

        if isinstance(role, str) and role:
            output.append({
                "role": role,
                "content": message.get("content") or "",
            })

    return copy.deepcopy(output)
def redact_secrets(value, limit=4000):
    if not value:
        return ""
    text = str(value).replace("\\r", " ").replace("\\n", " ")
    parts = text.split()
    cleaned = []
    for part in parts:
        lower = part.lower()
        if lower.startswith("bearer") and len(part) > 7:
            cleaned.append(part[:6] + "<redacted>")
        elif lower.startswith("sk-") or lower.startswith("sk_") or lower.startswith("or-v1-") or lower.startswith("or_"):
            cleaned.append("<redacted>")
        else:
            cleaned.append(part)
    return " ".join(cleaned)[:limit].rstrip()


def describe_provider_error(body):
    if not isinstance(body, str) or not body:
        return {}
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return {}
    error = payload["error"]
    metadata = error.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    result = {}
    if isinstance(metadata.get("provider_name"), str):
        result["provider"] = metadata["provider_name"]
    if isinstance(error.get("code"), int):
        result["code"] = error["code"]
    if isinstance(error.get("message"), str):
        result["message"] = redact_secrets(error["message"])
    return result


def format_http_error(model, status, body):
    details = describe_provider_error(body)
    provider = details.get("provider", "unknown")
    message = details.get("message") or redact_secrets(body) or "no response body"
    return f"provider={provider} model={model} status={status} {message}"

# provider result helpers

def _message_from_result(provider, name, result):
    if result.get('status') != 'response':
        return None, result.get('error') or 'provider failure'
    response = result['response']
    try:
        data = response.json()
    except ValueError:
        return None, 'invalid JSON response'
    choices = data.get('choices') if isinstance(data, dict) else None
    if choices and isinstance(choices[0].get('message'), dict):
        return choices[0]['message'], None
    return None, 'response contained no choices'

def ask(messages):
    request_messages = sanitize_messages_for_request(messages)
    _PROVIDER.tools = _current_tools()
    model = _PROVIDER.model
    try:
        result = _PROVIDER.call_model(model, request_messages)
    except Exception as exc:
        return {"role": "assistant", "content": "Local Qwen failed: " + redact_secrets(f"{type(exc).__name__}: {exc}")}
    message, error = _message_from_result(_PROVIDER, model, result)
    if message is not None:
        return message
    return {"role": "assistant", "content": "Local Qwen failed: " + redact_secrets(error or "unknown error")}
