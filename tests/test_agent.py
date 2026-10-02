import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import agent


def tool_call(call_id, name, arguments=..., include_arguments=True):
    """Build a tool call payload, mirroring the OpenAI chat-completions shape."""
    call = {"id": call_id, "type": "function", "function": {"name": name}}

    if include_arguments:
        call["function"]["arguments"] = arguments

    return call


def assistant_tool_call_message(*calls, content="Working on it."):
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": list(calls),
    }


def final_message(content="All done."):
    return {"role": "assistant", "content": content}


def tool_messages(messages):
    return [message for message in messages if message.get("role") == "tool"]


class ToolCallRecoveryTestCase(unittest.TestCase):
    """Drives agent() with a scripted LLM so recovery is fully deterministic."""

    def run_agent(self, responses=(), max_steps=3):
        queued = list(responses)
        live_message_lists = []
        seen_snapshots = []
        execute_calls = []

        def fake_ask(messages):
            # Keep the live list (agent mutates it) plus an immutable snapshot.
            live_message_lists.append(messages)
            seen_snapshots.append([dict(message) for message in messages])

            if queued:
                return queued.pop(0)

            return final_message()

        def fake_execute_tool(name, arguments):
            execute_calls.append((name, arguments))
            return f"RESULT for {name}"

        buffer = io.StringIO()

        with patch.object(agent, "ask", fake_ask), \
                patch.object(agent, "execute_tool", fake_execute_tool), \
                redirect_stdout(buffer):
            agent.agent("Do the thing", max_steps=max_steps)

        return SimpleNamespace(
            messages=live_message_lists[-1],
            snapshots=seen_snapshots,
            execute_calls=execute_calls,
            output=buffer.getvalue(),
        )

    def assertToolMessage(self, messages, tool_call_id, name):
        matching = [
            message
            for message in tool_messages(messages)
            if message.get("tool_call_id") == tool_call_id
        ]

        self.assertEqual(
            len(matching), 1, f"expected exactly one tool message for {tool_call_id}"
        )
        self.assertEqual(matching[0]["role"], "tool")
        self.assertEqual(matching[0]["name"], name)
        return matching[0]


class MalformedArgumentsDoNotCrashAgentTests(ToolCallRecoveryTestCase):
    """Requirement 1: malformed JSON tool arguments cannot crash the agent."""

    def test_truncated_json_arguments_do_not_crash_the_agent(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "read_file", '{"path": ')),
            final_message(),
        ])

        self.assertIn("[TOOL ERROR] read_file", result.output)
        self.assertIn("All done.", result.output)
        self.assertEqual(len(result.snapshots), 2)

    def test_unquoted_key_arguments_do_not_crash_the_agent(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "list_files", "{path: '.'}")),
        ])

        self.assertIn("[TOOL ERROR] list_files", result.output)
        self.assertIn("JSONDecodeError", result.output)

    def test_trailing_garbage_arguments_do_not_crash_the_agent(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "shell", '{"command": "ls"} oops')),
        ])

        self.assertIn("[TOOL ERROR] shell", result.output)

    def test_empty_string_arguments_do_not_crash_the_agent(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "shell", "")),
        ])

        self.assertIn("[TOOL ERROR] shell", result.output)

    def test_error_output_uses_real_newline_not_literal_backslash_n(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "shell", "{oops")),
        ])

        self.assertIn("\n[TOOL ERROR] shell", result.output)
        self.assertNotIn("\\n[TOOL ERROR]", result.output)


class MalformedToolCallsAreNotExecutedTests(ToolCallRecoveryTestCase):
    """Requirement 2: malformed tool calls are never executed."""

    def test_malformed_json_call_is_not_executed(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_bad", "shell", "{'command': 'ls'}")),
            final_message(),
        ])

        self.assertEqual(result.execute_calls, [])

    def test_arguments_decoding_to_non_object_are_not_executed(self):
        for raw in ("[]", '"a string"', "null", "42", "true"):
            with self.subTest(raw=raw):
                result = self.run_agent([
                    assistant_tool_call_message(tool_call("call_bad", "shell", raw)),
                ])

                self.assertEqual(result.execute_calls, [])

    def test_non_string_arguments_are_not_executed(self):
        for raw in ([], {"command": "ls"}, 7, True):
            with self.subTest(raw=raw):
                result = self.run_agent([
                    assistant_tool_call_message(tool_call("call_bad", "shell", raw)),
                ])

                self.assertEqual(result.execute_calls, [])

    def test_call_missing_function_is_not_executed(self):
        result = self.run_agent([
            {
                "role": "assistant",
                "content": "Broken call.",
                "tool_calls": [{"id": "call_no_fn", "type": "function"}],
            },
        ])

        self.assertEqual(result.execute_calls, [])
        self.assertIn("[TOOL ERROR] unknown_tool", result.output)

    def test_call_missing_name_is_not_executed(self):
        result = self.run_agent([
            {
                "role": "assistant",
                "content": "Broken call.",
                "tool_calls": [
                    {"id": "call_no_name", "function": {"arguments": "{}"}}
                ],
            },
        ])

        self.assertEqual(result.execute_calls, [])
        self.assertIn("[TOOL ERROR] unknown_tool", result.output)

    def test_function_that_is_not_an_object_is_not_executed(self):
        result = self.run_agent([
            {
                "role": "assistant",
                "content": "Broken call.",
                "tool_calls": [
                    {"id": "call_str_fn", "function": "shell"}
                ],
            },
        ])

        self.assertEqual(result.execute_calls, [])
        self.assertIn("[TOOL ERROR] unknown_tool", result.output)

    def test_call_that_is_not_an_object_is_not_executed(self):
        result = self.run_agent([
            {
                "role": "assistant",
                "content": "Broken call.",
                "tool_calls": ["not-a-dict"],
            },
        ])

        self.assertEqual(result.execute_calls, [])

    def test_malformed_call_never_reaches_underlying_tool_functions(self):
        assistant_message = assistant_tool_call_message(
            tool_call("call_1", "shell", "{oops"),
            tool_call("call_2", "write_file", '{"path": "a.txt", "content": "x"'),
            tool_call("call_3", "git_commit", "nope"),
        )

        with patch.object(agent, "run") as run_mock, \
                patch.object(agent, "write_file") as write_mock, \
                patch.object(agent, "git_commit") as commit_mock, \
                patch.object(agent, "ask_approval") as approval_mock, \
                patch.object(agent, "execute_tool") as execute_mock, \
                patch.object(agent, "ask", return_value=assistant_message), \
                redirect_stdout(io.StringIO()):
            agent.agent("Do the thing", max_steps=1)

            run_mock.assert_not_called()
            write_mock.assert_not_called()
            commit_mock.assert_not_called()
            approval_mock.assert_not_called()
            execute_mock.assert_not_called()


class ToolErrorMessageShapeTests(ToolCallRecoveryTestCase):
    """Requirement 3: a tool error is appended with role/id/name."""

    def test_tool_error_has_role_tool_matching_id_and_name(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_err", "read_file", "{'path'")),
        ])

        error = self.assertToolMessage(result.messages, "call_err", "read_file")

        self.assertTrue(error["content"].startswith("ERROR:"))
        self.assertIn("Invalid JSON tool arguments", error["content"])
        self.assertIn("JSONDecodeError", error["content"])

    def test_tool_error_tells_the_model_not_to_execute_and_to_retry(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_err", "read_file", "{'path'")),
        ])

        content = self.assertToolMessage(
            result.messages, "call_err", "read_file"
        )["content"]

        self.assertIn("Do not execute this tool call.", content)
        self.assertIn("Regenerate the tool call with valid JSON.", content)

    def test_one_tool_error_is_appended_per_malformed_call(self):
        result = self.run_agent([
            assistant_tool_call_message(
                tool_call("call_1", "shell", "{bad"),
                tool_call("call_2", "list_files", "[]"),
                tool_call("call_3", "read_file", "{also bad"),
            ),
        ])

        errors = tool_messages(result.messages)

        self.assertEqual(len(errors), 3)
        self.assertEqual(
            [message["tool_call_id"] for message in errors],
            ["call_1", "call_2", "call_3"],
        )
        self.assertEqual(
            [message["name"] for message in errors],
            ["shell", "list_files", "read_file"],
        )

    def test_missing_tool_call_id_falls_back_to_unknown(self):
        assistant_message = assistant_tool_call_message({
            "type": "function",
            "function": {"name": "shell", "arguments": "{bad"},
        })

        result = self.run_agent([assistant_message])

        error = self.assertToolMessage(result.messages, "unknown", "shell")

        self.assertIn("Invalid JSON tool arguments", error["content"])
        self.assertEqual(result.execute_calls, [])


class AssistantMessagePreservationTests(ToolCallRecoveryTestCase):
    """Requirement 4: the assistant message holding tool_calls stays in messages."""

    def test_assistant_message_with_tool_calls_is_preserved(self):
        assistant_message = assistant_tool_call_message(
            tool_call("call_1", "read_file", "{'path'"),
        )

        result = self.run_agent([assistant_message])

        self.assertTrue(
            any(message is assistant_message for message in result.messages)
        )
        self.assertEqual(result.messages[2], assistant_message)

    def test_assistant_message_is_preserved_before_the_tool_error(self):
        assistant_message = assistant_tool_call_message(
            tool_call("call_1", "read_file", "{'path'"),
        )

        result = self.run_agent([assistant_message])

        assistant_index = result.messages.index(assistant_message)
        error_index = result.messages.index(
            self.assertToolMessage(result.messages, "call_1", "read_file")
        )

        self.assertLess(assistant_index, error_index)
        self.assertEqual(assistant_index + 1, error_index)

    def test_assistant_message_keeps_its_tool_calls_intact(self):
        assistant_message = assistant_tool_call_message(
            tool_call("call_1", "read_file", "{'path'"),
        )

        result = self.run_agent([assistant_message])

        preserved = result.messages[2]

        self.assertEqual(preserved["role"], "assistant")
        self.assertEqual(preserved["content"], "Working on it.")
        self.assertEqual(preserved["tool_calls"][0]["id"], "call_1")
        self.assertEqual(
            preserved["tool_calls"][0]["function"]["arguments"], "{'path'"
        )

    def test_each_tool_message_follows_its_assistant_message(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "read_file", "{'path'")),
            assistant_tool_call_message(
                tool_call("call_2", "shell", "{bad"),
                tool_call("call_3", "list_files", '{"path": "."}'),
            ),
        ])

        seen_ids = set()
        pending_ids = set()

        for message in result.messages:
            role = message.get("role")

            if role == "assistant" and message.get("tool_calls"):
                # Tool results already in the transcript must belong to a call
                # the assistant has actually made.
                self.assertTrue(pending_ids.issubset(
                    {call["id"] for call in message["tool_calls"]}
                ))
                pending_ids = {call["id"] for call in message["tool_calls"]}
            elif role == "tool":
                self.assertTrue(pending_ids, "tool message before any assistant tool call")
                self.assertIn(message["tool_call_id"], pending_ids)
                pending_ids.discard(message["tool_call_id"])
                seen_ids.add(message["tool_call_id"])

        self.assertEqual(seen_ids, {"call_1", "call_2", "call_3"})
        self.assertEqual(pending_ids, set())


class ValidArgumentsExecuteNormallyTests(ToolCallRecoveryTestCase):
    """Requirement 5: valid arguments still execute normally."""

    def test_valid_arguments_are_executed_with_parsed_values(self):
        result = self.run_agent([
            assistant_tool_call_message(
                tool_call("call_ok", "write_file", json.dumps({
                    "path": "notes.txt",
                    "content": "hello",
                })),
            ),
        ])

        self.assertEqual(
            result.execute_calls,
            [("write_file", {"path": "notes.txt", "content": "hello"})],
        )

    def test_valid_call_appends_tool_result_with_matching_id_and_name(self):
        result = self.run_agent([
            assistant_tool_call_message(
                tool_call("call_ok", "git_status", json.dumps({})),
            ),
        ])

        self.assertToolMessage(result.messages, "call_ok", "git_status")

        self.assertEqual(
            tool_messages(result.messages)[0]["content"], "RESULT for git_status"
        )

    def test_malformed_and_valid_calls_in_one_message(self):
        result = self.run_agent([
            assistant_tool_call_message(
                tool_call("call_bad", "shell", "{oops"),
                tool_call("call_ok", "read_file", '{"path": "agent.py"}'),
            ),
        ])

        self.assertEqual(
            result.execute_calls, [("read_file", {"path": "agent.py"})]
        )
        self.assertEqual(
            [message["tool_call_id"] for message in tool_messages(result.messages)],
            ["call_bad", "call_ok"],
        )

    def test_real_execute_tool_still_runs_valid_arguments(self):
        with patch.object(agent, "run", return_value="shell-output") as run_mock, \
                redirect_stdout(io.StringIO()):
            result = agent.execute_tool("shell", {"command": "echo hi"})

        self.assertEqual(result, "shell-output")
        run_mock.assert_called_once_with("echo hi")

    def test_missing_required_key_is_reported_by_execute_tool(self):
        with patch.object(agent, "write_file") as write_mock, \
                redirect_stdout(io.StringIO()):
            result = agent.execute_tool("write_file", {})

        write_mock.assert_not_called()
        self.assertTrue(result.startswith("ERROR:"))


class MissingOrNonStringArgumentTests(ToolCallRecoveryTestCase):
    """Requirement 6: missing / non-string arguments are handled safely."""

    def test_missing_arguments_default_to_empty_object(self):
        result = self.run_agent([
            assistant_tool_call_message(
                tool_call("call_no_args", "git_status", include_arguments=False),
            ),
        ])

        self.assertEqual(result.execute_calls, [("git_status", {})])

    def test_null_arguments_default_to_empty_object(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_null", "git_diff", None)),
        ])

        self.assertEqual(result.execute_calls, [("git_diff", {})])

    def test_empty_json_object_is_executed_normally(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_empty", "git_log", "{}")),
        ])

        self.assertEqual(result.execute_calls, [("git_log", {})])

    def test_missing_tool_call_id_on_valid_call_is_reported_as_unknown(self):
        assistant_message = assistant_tool_call_message({
            "type": "function",
            "function": {"name": "git_status", "arguments": "{}"},
        })

        result = self.run_agent([assistant_message])

        self.assertEqual(result.execute_calls, [("git_status", {})])
        self.assertToolMessage(result.messages, "unknown", "git_status")

    def test_non_string_arguments_are_rejected_with_clear_error(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_bad", "read_file", {"path": "a"})),
        ])

        error = self.assertToolMessage(result.messages, "call_bad", "read_file")

        self.assertIn("must be a JSON string", error["content"])
        self.assertIn("dict", error["content"])

    def test_arguments_decoding_to_non_object_are_rejected_with_clear_error(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_bad", "read_file", "[1, 2]")),
        ])

        error = self.assertToolMessage(result.messages, "call_bad", "read_file")

        self.assertIn("must decode to a JSON object", error["content"])
        self.assertIn("list", error["content"])

    def test_unicode_arguments_are_preserved(self):
        result = self.run_agent([
            assistant_tool_call_message(
                tool_call("call_ok", "write_file", json.dumps({
                    "path": "notes.txt",
                    "content": "caf\u00e9 \u2014 na\u00efve",
                })),
            ),
        ])

        self.assertEqual(
            result.execute_calls,
            [("write_file", {"path": "notes.txt", "content": "caf\u00e9 \u2014 na\u00efve"})],
        )


class RecoveryContinuesAfterMalformedCallTests(ToolCallRecoveryTestCase):
    def test_agent_continues_to_the_next_step_after_malformed_arguments(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "shell", "{oops")),
            final_message("Recovered."),
        ])

        self.assertEqual(len(result.snapshots), 2)
        self.assertIn("Recovered.", result.output)

    def test_tool_error_is_sent_back_to_the_model_on_the_next_step(self):
        result = self.run_agent([
            assistant_tool_call_message(tool_call("call_1", "shell", "{oops")),
            final_message("Recovered."),
        ])

        second_step = result.snapshots[1]

        self.assertEqual(second_step[-1]["role"], "tool")
        self.assertEqual(second_step[-1]["tool_call_id"], "call_1")
        self.assertEqual(second_step[-1]["name"], "shell")
        self.assertIn("Invalid JSON tool arguments", second_step[-1]["content"])

        # The assistant message carrying tool_calls is still there for the model.
        self.assertEqual(second_step[-2]["role"], "assistant")
        self.assertTrue(second_step[-2]["tool_calls"])

    def test_repeated_malformed_calls_do_not_crash_across_steps(self):
        result = self.run_agent(
            [
                assistant_tool_call_message(tool_call("call_1", "shell", "{a")),
                assistant_tool_call_message(tool_call("call_2", "list_files", "{b")),
                assistant_tool_call_message(tool_call("call_3", "read_file", "[]")),
            ],
            max_steps=3,
        )

        self.assertEqual(result.execute_calls, [])
        self.assertEqual(
            [message["tool_call_id"] for message in tool_messages(result.messages)],
            ["call_1", "call_2", "call_3"],
        )
        self.assertIn("Agent reached maximum steps.", result.output)


if __name__ == "__main__":
    unittest.main()
