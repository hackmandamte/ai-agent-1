import json
from llm import UNKNOWN_TOOL_CALL_ID, ask
from tools.shell import run
from tools.files import read_file, write_file, list_files
from tools.git import git_status, git_diff, git_log, git_commit
from tools.approval import ask_approval
from tools.runtime import get_runtime_context
from tools.web import web_fetch
from tools.mcp import execute_mcp_tool, is_mcp_tool, close_all
from tools.task_manager import TaskManager

UNKNOWN_TOOL_NAME = "unknown_tool"


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
    """Return the decoded arguments dict for a tool call's function payload.

    Missing/None arguments default to an empty object (so no-argument tools
    such as git_status still work). Raises TypeError/ValueError --
    json.JSONDecodeError being a ValueError -- when the arguments are not a
    JSON string or do not decode to a JSON object.
    """
    raw_arguments = function.get("arguments")

    if raw_arguments is None:
        raw_arguments = "{}"

    if not isinstance(raw_arguments, str):
        raise ValueError(
            "Tool arguments must be a JSON string, "
            f"got {type(raw_arguments).__name__}"
        )

    arguments = json.loads(raw_arguments)

    if not isinstance(arguments, dict):
        raise ValueError(
            "Tool arguments must decode to a JSON object, "
            f"got {type(arguments).__name__}"
        )

    return arguments


def execute_tool(name, arguments):
    try:
        if name == "list_files":
            return list_files(arguments["path"])

        if name == "read_file":
            return read_file(arguments["path"])

        if name == "write_file":
            return write_file(
                arguments["path"],
                arguments["content"]
            )

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

            if not ask_approval(f"Git commit: {message}"):
                return "APPROVAL DENIED: Git commit was not executed."

            return git_commit(message)

        if name == "get_runtime_info":
            return get_runtime_context()

        if name == "web_fetch":
            return web_fetch(arguments["url"])

        if is_mcp_tool(name):
            return execute_mcp_tool(name, arguments)

        return f"ERROR: Unknown tool: {name}"

    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def agent(goal, max_steps=30):
    # The task manager persists orchestration state independently of the LLM.
    task_manager = TaskManager()
    task = task_manager.start(goal, max_steps=max_steps)

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

Treat the goal as a multi-step task. Break work into concrete tool actions, inspect each
result, recover from errors when possible, and verify the requested outcome before
finishing. Do not claim something is done unless you actually performed and verified it.

=== RUNTIME ENVIRONMENT CONTEXT ===
Operating System: {runtime_context['os']}
Shell/Environment: {runtime_context['shell']}
Python Version: {runtime_context['python_version']}
CPU Architecture: {runtime_context['architecture']}
Workspace Path: {runtime_context['workspace_path']}

This runtime context is automatically detected at each agent run.
"""
    }

    messages = [system_message, {"role": "user", "content": goal}]

    for step in range(max_steps):
        print(f"\n===== STEP {step + 1} =====")
        task_manager.begin_step(step + 1)

        message = ask(messages)

        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            final_content = message.get("content", "")
            print("\nAGENT:")
            print(final_content)
            task_manager.complete(final_content)
            return

        messages.append(message)

        for call in tool_calls:
            name, tool_call_id = describe_tool_call(call)

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

                error_content = (
                    "ERROR: Invalid JSON tool arguments. "
                    "Do not execute this tool call. "
                    "Regenerate the tool call with valid JSON. "
                    f"Parser error: {type(e).__name__}: {e}"
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": name,
                    "content": error_content,
                })
                task_manager.record_tool_result(name, error_content)

                continue

            print(f"\n[TOOL] {name}")
            print(f"[ARGS] {arguments}")

            result = execute_tool(name, arguments)

            print("[RESULT]")
            print(result)
            task_manager.record_tool_result(name, result)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": result
            })

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

    args = parser.parse_args()

    goal = " ".join(args.goal).strip() or (
        "Inspect this repository and tell me what I should work on first."
    )

    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1")

    agent(goal, max_steps=args.max_steps)
