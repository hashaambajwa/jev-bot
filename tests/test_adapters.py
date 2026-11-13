import json
import tempfile
import unittest
from pathlib import Path

from jev.adapters import AdapterError, import_openai_chat
from jev.__main__ import main
from jev.trace import read_trace


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "openai-chat.json"


class AdapterTests(unittest.TestCase):
    def test_openai_style_transcript(self):
        result = import_openai_chat(json.loads(EXAMPLE.read_text()), run_id="fixture")
        self.assertEqual([x["event"] for x in result], ["tool_call", "tool_result", "final"])
        self.assertEqual(result[0]["arguments"], {"query": "structured outputs"})
        self.assertEqual(result[0]["cost_usd"], 0.004)
        self.assertEqual(result[2]["answer"], "Found sources about structured outputs.")

    def test_untrusted_missing_metrics_rejected(self):
        data = json.loads(EXAMPLE.read_text())
        del data["call_metrics"]
        with self.assertRaises(AdapterError):
            import_openai_chat(data, run_id="missing")

    def test_duplicate_call_id_rejected(self):
        data = json.loads(EXAMPLE.read_text())
        data["messages"][1]["tool_calls"].append(data["messages"][1]["tool_calls"][0])
        with self.assertRaises(AdapterError):
            import_openai_chat(data, run_id="duplicate")

    def test_nonstandard_argument_json_rejected(self):
        data = json.loads(EXAMPLE.read_text())
        data["messages"][1]["tool_calls"][0]["function"]["arguments"] = '{"amount": NaN}'
        with self.assertRaises(AdapterError):
            import_openai_chat(data, run_id="invalid")

    def test_cli_import_produces_readable_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "imported.jsonl"
            result = main([
                "import-chat", str(EXAMPLE), "--run-id", "imported",
                "--output", str(path),
            ])
            self.assertEqual(result, 0)
            self.assertEqual(read_trace(path).tools, ["search"])

    def test_missing_result_rejected(self):
        data = json.loads(EXAMPLE.read_text())
        data["messages"].pop(2)
        with self.assertRaises(AdapterError):
            import_openai_chat(data, run_id="missing-result")


if __name__ == "__main__":
    unittest.main()
