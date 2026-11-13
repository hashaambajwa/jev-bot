import json
import tempfile
import unittest
from pathlib import Path

from jev.trace import TraceError, read_trace


ROOT = Path(__file__).resolve().parents[1] / "examples" / "traces"


class TraceTests(unittest.TestCase):
    def test_example_trace(self):
        trace = read_trace(ROOT / "search.jsonl")
        self.assertEqual(trace.run_id, "search-001")
        self.assertEqual(trace.tools, ["search"])
        self.assertEqual(trace.cost_usd, 0.008)
        self.assertEqual(trace.latency_ms, 120)
        self.assertIn("sources", trace.final_answer)

    def mutate_trace(self, change):
        data = [json.loads(x) for x in (ROOT / "search.jsonl").read_text().splitlines()]
        change(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_text("\n".join(json.dumps(x) for x in data) + "\n")
            with self.assertRaises(TraceError):
                read_trace(path)

    def test_result_without_call(self):
        self.mutate_trace(lambda events: events[1].update(call_id="unknown"))

    def test_unmatched_call(self):
        self.mutate_trace(lambda events: events[1].update(event="tool_call", call_id="c2", tool="summarize"))

    def test_invalid_step(self):
        self.mutate_trace(lambda events: events[1].update(step=10))

    def test_duplicate_result(self):
        def transform(events):
            events[2] = {**events[1], "step": 2}
        self.mutate_trace(transform)

    def test_non_finite_cost(self):
        self.mutate_trace(lambda events: events[0].update(cost_usd=float("inf")))

    def test_mixed_run_ids(self):
        self.mutate_trace(lambda events: events[1].update(run_id="different"))

    def test_bytes_limit(self):
        with self.assertRaises(TraceError):
            read_trace(ROOT / "search.jsonl", max_bytes=20)


if __name__ == "__main__":
    unittest.main()
