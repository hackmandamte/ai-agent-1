import json
from llm import ask
from tools.shell import run
from tools.files import read_file, write_file, list_files
from tools.git import git_status, git_diff, git_log, git_commit
from tools.approval import ask_approval


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

        return f"ERROR: Unknown tool: {name}"

    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def agent(goal, max_steps=15):
    messages = [
        {
            "role": "system",
            "content": """You are a software development agent.

You work toward the user's goal by inspecting files, using shell commands,
understanding the repository, making changes when requested, testing them,
and inspecting Git changes.

Use tools whenever necessary.

Do not claim something was done unless you actually performed it.
"""
        },
        {
            "role": "user",
            "content": goal
        }
    ]

    for step in range(max_steps):
        print(f"\n===== STEP {step + 1} =====")

        message = ask(messages)

        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            print("\nAGENT:")
            print(message.get("content", ""))
            return

        messages.append(message)

        for call in tool_calls:
            name = call["function"]["name"]
            arguments = json.loads(call["function"]["arguments"])

            print(f"\n[TOOL] {name}")
            print(f"[ARGS] {arguments}")

            result = execute_tool(name, arguments)

            print("[RESULT]")
            print(result)

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": name,
                "content": result
            })

    print("\nAgent reached maximum steps.")


if __name__ == "__main__":
    import sys
    goal = " ".join(sys.argv[1:]).strip() or "Inspect this repository and tell me what I should work on first."
    agent(goal)
