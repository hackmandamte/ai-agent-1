import json
import unittest
from unittest.mock import patch

from providers.local_llama_provider import LocalLlamaProvider
from llm import _message_from_result


class LocalLlamaPromptToolModeTests(unittest.TestCase):
    def setUp(self):
        self.tools = [{
            "type": "function",
            "function": {
                "name": "system_info",
                "description": "Inspect PC information.",
                "parameters": {"type": "object", "properties": {}},
            },
        }]

    def test_prompt_json_mode_does_not_send_native_tools(self):
        provider = LocalLlamaProvider(self.tools)
        captured = {}

        class Result:
            returncode = 0
            stdout = json.dumps({"choices": [{"message": {"role": "assistant", "content": "OK"}}]})
            stderr = ""

        def fake_run(args, **kwargs):
            captured["body"] = json.loads(kwargs["input"])
            return Result()

        with patch("providers.local_llama_provider.subprocess.run", fake_run):
            result = provider.call_model(provider.model, [{"role": "system", "content": "agent"}, {"role": "user", "content": "hello"}])

        self.assertEqual(result["status"], "response")
        self.assertNotIn("tools", captured["body"])
        self.assertIn("AVAILABLE_TOOLS=", captured["body"]["messages"][0]["content"])
        self.assertIn("system_info", captured["body"]["messages"][0]["content"])

    def test_tool_result_is_serialized_for_next_model_turn(self):
        provider = LocalLlamaProvider(self.tools)
        messages = [
            {"role": "system", "content": "agent"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "system_info", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "system_info", "content": "HOST=DESKTOP-OUSKRT"},
        ]
        converted = provider._prompt_mode_messages(messages)
        self.assertEqual(converted[-1]["role"], "user")
        self.assertIn("TOOL_RESULT system_info", converted[-1]["content"])

    def test_native_mode_remains_available_explicitly(self):
        with patch.dict("os.environ", {"LLAMA_TOOL_MODE": "native"}):
            provider = LocalLlamaProvider(self.tools)
        self.assertEqual(provider.tool_mode, "native")


class LlmPromptToolParsingTests(unittest.TestCase):
    def test_json_tool_request_is_normalized_to_openai_shape(self):
        provider = LocalLlamaProvider([])
        payload = {"choices": [{"message": {"role": "assistant", "content": json.dumps({"tool": "system_info", "arguments": {}})}}]}
        response = type("Response", (), {"json": lambda self: payload})()
        message, error = _message_from_result(provider, provider.model, {"status": "response", "response": response})
        self.assertIsNone(error)
        self.assertEqual(message["tool_calls"][0]["function"]["name"], "system_info")
        self.assertEqual(message["tool_calls"][0]["function"]["arguments"], "{}")

    def test_normal_text_remains_normal_text(self):
        provider = LocalLlamaProvider([])
        payload = {"choices": [{"message": {"role": "assistant", "content": "No tool needed."}}]}
        response = type("Response", (), {"json": lambda self: payload})()
        message, error = _message_from_result(provider, provider.model, {"status": "response", "response": response})
        self.assertIsNone(error)
        self.assertEqual(message["content"], "No tool needed.")


if __name__ == "__main__":
    unittest.main()
