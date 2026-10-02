import json
from llm import UNKNOWN_TOOL_CALL_ID, ask
from tools.shell import run
from tools.files import read_file, write_file, list_files, create_directory, copy_path, move_path, delete_path
from tools.git import git_status, git_diff, git_log, git_commit
from tools.approval import ask_approval
from tools.policy import policy_result
from tools.runtime import get_runtime_context
from tools.web import web_fetch
from tools.mcp import execute_mcp_tool, is_mcp_tool, close_all
from tools.task_manager import TaskManager
from tools.verify import verify_path_exists, verify_file_contains, verify_command, verify_process_state, verify_job_state
from tools.pc import (
    system_info, list_processes, process_info, process_tree, terminate_process,
    launch_app, start_background_job, job_status,
)
from tools.jobs import start_job, get_job, list_jobs, job_output, stop_job, restart_job
from tools.apps import discover_apps, launch_app_id
from tools.system import disk_usage, network_state, listening_ports, environment_info

UNKNOWN_TOOL_NAME = "unknown_tool"
_ACTIVE_TASK_MANAGER = None
MAX_MODEL_MESSAGES = 8
MAX_TOOL_RESULT_CHARS = 1200
MAX_ASSISTANT_CHARS = 1200


def compact_messages(messages):
    """Keep the model context bounded while preserving the active tool turn."""
    if not isinstance(messages, list) or len(messages) <= MAX_MODEL_MESSAGES + 2:
        return messages

    prefix = messages[:2]
    tail = messages[-MAX_MODEL_MESSAGES:]
    while tail and tail[0].get("role") == "tool":
        tail.pop(0)

    compacted = prefix + tail
    output = []
    for message in compacted:
        item = dict(message)
        role = item.get("role")
        if role == "tool":
            item["content"] = str(item.get("content", ""))[:MAX_TOOL_RESULT_CHARS]
        elif role == "assistant":
            item["content"] = str(item.get("content", ""))[:MAX_ASSISTANT_CHARS]
        output.append(item)
    return output


def describe_tool_call(call):
    """Best-effort (name, tool_call_id) extraction that never raises.

    A malformed tool call must still be reportable back to the model, so the
    name/id are resolved defensively before argument parsing is attempted.
    """
    name = UNKNOWN_TOOL_NAME
    tool_call_id = UNKNOWN_TOOL_CALL_ID

    if isinstance(call, dict):
        tool_call_id = call.get("id", UNKNOWN_TOOL_CALL_ID)
        function = call.get("function")

        if isinstance(function, dict):
            name = function.get("name", UNKNOWN_TOOL_NAME)

    return name, tool_call_id


def parse_tool_arguments(function):
    """Decode model tool arguments strictly as a JSON object."""
    raw_arguments = function.get("arguments")

    if raw_arguments is None:
        raw_arguments = "{}"

    if not isinstance(raw_arguments, str):
        raise ValueError(
            "Tool arguments must be a JSON string, "
            f"got {type(raw_arguments).__name__}"
        )

    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError as json_error:
        raise json_error

    if not isinstance(arguments, dict):
        raise ValueError(
            "Tool arguments must decode to a JSON object, "
            f"got {type(arguments).__name__}"
        )

    return arguments


def execute_tool(name, arguments):
    try:
        required_args = {
            "set_task_plan": ("steps",), "list_files": ("path",),
            "read_file": ("path",), "write_file": ("path", "content"),
            "create_directory": ("path",), "copy_path": ("source", "destination"),
            "move_path": ("source", "destination"), "delete_path": ("path",),
            "shell": ("command",), "git_commit": ("message",),
            "web_fetch": ("url",), "verify_path_exists": ("path",),
            "verify_file_contains": ("path", "text"), "verify_command": ("command",),
            "process_info": ("pid",), "process_tree": ("pid",), "terminate_process": ("pid",),
            "launch_app": ("command",), "launch_app_id": ("app_id",), "start_background_job": ("command",),
            "job_status": ("pid",), "start_job": ("command",),
            "get_job": ("job_id",), "job_output": ("job_id",),
            "verify_job_state": ("job_id",),
            "stop_job": ("job_id",), "restart_job": ("job_id",),
        }
        if name not in required_args and not is_mcp_tool(name) and name not in {
            "git_status", "git_diff", "git_log", "get_runtime_info",
            "system_info", "list_processes", "list_jobs", "discover_apps", "disk_usage", "network_state", "listening_ports", "environment_info", "verify_process_state",
        }:
            return f"ERROR: Unknown tool: {name}"
        missing = [key for key in required_args.get(name, ()) if key not in arguments]
        if missing:
            return f"ERROR: Missing required argument(s) for {name}: {', '.join(missing)}"

        risk, approval_required, approval_message = policy_result(name, arguments)
        if approval_required and not ask_approval(approval_message):
            return f"APPROVAL DENIED: {name} was not executed."

        if name == "set_task_plan":
            task_manager = _ACTIVE_TASK_MANAGER
            if task_manager is None:
                return "ERROR: task manager unavailable"
            steps = arguments["steps"]
            if not isinstance(steps, list) or not steps:
                return "ERROR: task plan must contain at least one step"
            normalized = []
            ids = set()
            for index, item in enumerate(steps, 1):
                if not isinstance(item, dict) or not item.get("id") or not item.get("goal"):
                    return "ERROR: each plan step needs id and goal"
                step_id = str(item["id"])
                if step_id in ids:
                    return f"ERROR: duplicate plan step id: {step_id}"
                ids.add(step_id)
                deps = item.get("depends_on", [])
                if not isinstance(deps, list) or any(dep == step_id for dep in deps):
                    return f"ERROR: invalid dependencies for plan step: {step_id}"
                normalized.append({"id": step_id, "goal": str(item["goal"]), "depends_on": deps, "status": "pending"})
            unknown = [dep for item in normalized for dep in item["depends_on"] if dep not in ids]
            if unknown:
                return f"ERROR: unknown plan dependency: {unknown[0]}"
            task_manager.set_plan(normalized)
            return f"PLAN SET: {len(normalized)} steps"

        if name == "list_files":
            return list_files(arguments["path"])

        if name == "read_file":
            return read_file(arguments["path"])

        if name == "write_file":
            return write_file(arguments["path"], arguments["content"])

        if name == "create_directory":
            return create_directory(arguments["path"])

        if name == "copy_path":
            return copy_path(arguments["source"], arguments["destination"])

        if name == "move_path":
            return move_path(arguments["source"], arguments["destination"])

        if name == "delete_path":
            return delete_path(arguments["path"])

        if name == "shell":
            return run(arguments["command"])

        if name == "git_status":
            return git_status()

        if name == "git_diff":
            return git_diff()

        if name == "git_log":
            return git_log()

        if name == "git_commit":
            message = arguments["message"]

            return git_commit(message)

        if name == "get_runtime_info":
            return get_runtime_context()

        if name == "web_fetch":
            return web_fetch(arguments["url"])

        if name == "verify_path_exists":
            return verify_path_exists(arguments["path"])

        if name == "verify_file_contains":
            return verify_file_contains(arguments["path"], arguments["text"])

        if name == "verify_command":
            return verify_command(arguments["command"])

        if name == "verify_process_state":
            return verify_process_state(arguments["pid"], arguments.get("expected_running", True))

        if name == "verify_job_state":
            return verify_job_state(arguments["job_id"], arguments.get("expected_status"))

        if name == "system_info":
            return system_info()

        if name == "disk_usage":
            return disk_usage(arguments.get("path", "."))

        if name == "network_state":
            return network_state()

        if name == "listening_ports":
            return listening_ports(arguments.get("limit", 100))

        if name == "environment_info":
            return environment_info()

        if name == "list_processes":
            return list_processes(arguments.get("limit", 50))

        if name == "process_info":
            return process_info(arguments["pid"])

        if name == "process_tree":
            return process_tree(arguments["pid"], arguments.get("max_depth", 4))

        if name == "terminate_process":
            return terminate_process(arguments["pid"], arguments.get("force", False))

        if name == "launch_app":
            return launch_app(arguments["command"], arguments.get("wait", False))

        if name == "discover_apps":
            return discover_apps(arguments.get("query", ""), arguments.get("limit", 100))

        if name == "launch_app_id":
            return launch_app_id(arguments["app_id"])

        if name == "start_background_job":
            return start_background_job(arguments["command"])

        if name == "job_status":
            return job_status(arguments["pid"])

        if name == "start_job":
            return start_job(arguments["command"])

        if name == "get_job":
            record = get_job(arguments["job_id"])
            return record if record is not None else f"ERROR: unknown job: {arguments['job_id']}"

        if name == "list_jobs":
            return list_jobs()

        if name == "job_output":
            return job_output(arguments["job_id"], arguments.get("limit", 8000))

        if name == "stop_job":
            return stop_job(arguments["job_id"])

        if name == "restart_job":
            return restart_job(arguments["job_id"])

        if is_mcp_tool(name):
            return execute_mcp_tool(name, arguments)

        return f"ERROR: Unknown tool: {name}"

    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def agent(goal, max_steps=30, resume_task_id=None):
    # The task manager persists orchestration state independently of the LLM.
    global _ACTIVE_TASK_MANAGER
    task_manager = TaskManager()
    _ACTIVE_TASK_MANAGER = task_manager
    resume_words = ("continue", "resume", "already started", "active task", "started a task")
    wants_resume = any(word in goal.lower() for word in resume_words)
    if resume_task_id:
        task = task_manager.resume(resume_task_id)
        goal = task.goal
        messages = task.messages
    elif wants_resume and task_manager.find_resumable(goal) is not None:
        resumable = task_manager.find_resumable(goal)
        task = task_manager.resume(resumable.task_id)
        goal = task.goal
        messages = task.messages
    else:
        task = task_manager.start(goal, max_steps=max_steps)
        messages = None

    # Get runtime context at startup
    runtime_context = get_runtime_context()

    # Create system message with runtime information
    system_message = {
        "role": "system",
        "content": f"""You are a software development agent.

You work toward the user's goal by inspecting files, using shell commands,
understanding the repository, making changes when requested, testing them,
and inspecting Git changes.

Use tools whenever necessary. You have read-only internet access through web_fetch.
You may also have MCP tools. MCP tool names begin with mcp__ and are external services;
use them when they are relevant to the user's goal.

Treat the goal as a multi-step task. For complex work, create a task plan with
set_task_plan before execution. Respect dependencies, inspect every result, recover
from errors with a changed approach, and use a verification tool before claiming success.
Task state is checkpointed and can be resumed. Do not claim something is done unless
you actually performed and verified it.

=== RUNTIME ENVIRONMENT CONTEXT ===
Operating System: {runtime_context['os']}
Shell/Environment: {runtime_context['shell']}
Python Version: {runtime_context['python_version']}
CPU Architecture: {runtime_context['architecture']}
Workspace Path: {runtime_context['workspace_path']}

This runtime context is automatically detected at each agent run.
"""
    }

    if messages is None:
        messages = [system_message, {"role": "user", "content": goal}]
        task_manager.save_messages(messages)

    invalid_attempts = {}

    for step in range(max_steps):
        print(f"\n===== STEP {step + 1} =====")
        task_manager.begin_step(step + 1)

        model_messages = compact_messages(messages)
        message = ask(model_messages)

        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            final_content = message.get("content", "")
            print("\nAGENT:")
            print(final_content)
            if isinstance(final_content, str) and final_content.startswith("Local Qwen failed:"):
                task_manager.fail(final_content)
            else:
                task_manager.complete(final_content)
            return

        messages.append(message)
        task_manager.save_messages(messages)

        for call in tool_calls:
            name, tool_call_id = describe_tool_call(call)

            function = None
            try:
                if not isinstance(call, dict):
                    raise TypeError("Tool call must be an object")

                function = call["function"]

                if not isinstance(function, dict):
                    raise TypeError("Tool call function must be an object")

                name = function["name"]

                if not isinstance(name, str) or not name:
                    raise ValueError("Tool call is missing a tool name")

                arguments = parse_tool_arguments(function)

            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as e:
                print(f"\n[TOOL ERROR] {name}")
                print(f"[RESULT] Invalid tool arguments: {type(e).__name__}: {e}")

                raw_args = function.get("arguments") if isinstance(function, dict) else None
                expected = {
                    "read_file": '{"path":"<file path>"}',
                    "list_files": '{"path":"<directory path>"}',
                    "write_file": '{"path":"<file path>","content":"<text>"}',
                    "shell": '{"command":"<command>"}',
                }.get(name, '{"...":"..."}')
                error_content = (
                    "ERROR: Invalid JSON tool arguments. Do not execute this tool call. Regenerate the tool call with valid JSON. "
                    f"Tool: {name}. Parser error: {type(e).__name__}: {e}. "
                    f"Malformed arguments: {raw_args!r}. Expected shape: {expected}. "
                    "REGENERATE THE SAME TOOL CALL NOW. Return ONLY the JSON arguments object, "
                    "with double-quoted keys and string values; no markdown and no explanation."
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": error_content,
                })
                task_manager.record_tool_result(name, error_content)
                # Give Qwen an explicit corrective user turn. The tool result records
                # the failure; this message tells the model to regenerate rather than
                # repeating the malformed call verbatim.
                messages.append({
                    "role": "user",
                    "content": (
                        f"Correct the previous {name} tool call. "
                        f"Return ONLY valid JSON arguments matching this shape: {expected}. "
                        "Use double quotes for every JSON key and string value. "
                        "Do not include markdown, prose, or a code fence."
                    ),
                })
                task_manager.save_messages(messages)

                signature = (name, str(raw_args))
                invalid_attempts[signature] = invalid_attempts.get(signature, 0) + 1
                if invalid_attempts[signature] >= 3:
                    failure = f"Tool call recovery exhausted for {name} after 3 identical invalid attempts."
                    task_manager.fail(failure)
                    print(f"\nAGENT: {failure}")
                    return

                continue

            print(f"\n[TOOL] {name}")
            print(f"[ARGS] {arguments}")

            result = execute_tool(name, arguments)
            result = result if isinstance(result, str) else str(result)

            print("[RESULT]")
            print(result)
            task_manager.record_tool_result(name, result)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": result
            })
            task_manager.save_messages(messages)

    task_manager.fail(f"Maximum steps reached: {max_steps}")
    print("\nAgent reached maximum steps.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI coding agent")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="Maximum number of agent steps (default: 30)",
    )
    parser.add_argument(
        "goal",
        nargs="*",
        help="Goal for the coding agent",
    )
    parser.add_argument(
        "--resume",
        help="Resume a persisted task by task ID",
    )

    args = parser.parse_args()

    goal = " ".join(args.goal).strip() or (
        "Inspect this repository and tell me what I should work on first."
    )

    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1")

    agent(goal, max_steps=args.max_steps, resume_task_id=args.resume)
