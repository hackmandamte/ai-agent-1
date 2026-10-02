import unittest
from unittest.mock import patch

import llm
from tools.mcp import is_mcp_tool
from tools.web import web_fetch_definition


class LocalOnlyRoutingTests(unittest.TestCase):
    def test_only_local_provider_is_enabled(self):
        self.assertEqual(llm.enabled_providers(), ("local_llama",))

    def test_current_tools_include_internet_capability(self):
        names = [
            item["function"]["name"]
            for item in llm._current_tools()
        ]
        self.assertIn("web_fetch", names)

    def test_mcp_tool_names_are_namespaced(self):
        self.assertTrue(is_mcp_tool("mcp__obscura__navigate"))
        self.assertFalse(is_mcp_tool("navigate"))


class LocalQwenRoutingTests(unittest.TestCase):
    def test_ask_uses_local_provider_and_dynamic_tools(self):
        response = {"role": "assistant", "content": "LOCAL_OK"}
        fake_result = {
            "status": "response",
            "response": type(
                "Response",
                (),
                {"json": lambda self: {"choices": [{"message": response}]}},
            )(),
        }

        with patch.object(llm._PROVIDER, "call_model", return_value=fake_result) as call:
            result = llm.ask([{"role": "user", "content": "test"}])

        self.assertEqual(result, response)
        call.assert_called_once()
        self.assertIn(
            "web_fetch",
            [item["function"]["name"] for item in llm._PROVIDER.tools],
        )


class InternetToolSchemaTests(unittest.TestCase):
    def test_web_fetch_definition_is_openai_compatible(self):
        definition = web_fetch_definition()
        self.assertEqual(definition["type"], "function")
        self.assertEqual(definition["function"]["name"], "web_fetch")
        self.assertEqual(
            definition["function"]["parameters"]["required"],
            ["url"],
        )


if __name__ == "__main__":
    unittest.main()
