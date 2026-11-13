import json
import tempfile
import unittest
from pathlib import Path

from jev.__main__ import main
from jev.evaluation import SuiteError, compare_reports, evaluate_suite


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class EvaluationTests(unittest.TestCase):
    def test_reference_suite(self):
        report = evaluate_suite(EXAMPLES / "suite.json")
        self.assertEqual(report["summary"]["cases"], 2)
        self.assertEqual(report["summary"]["passed"], 2)
        self.assertEqual(report["summary"]["pass_rate"], 1.0)
        self.assertEqual(report["summary"]["p50_latency_ms"], 200)
        self.assertEqual(report["summary"]["p95_latency_ms"], 272)

    def test_adversarial_case_detected(self):
        report = evaluate_suite(EXAMPLES / "adversarial-suite.json")
        row = report["cases"][0]
        self.assertFalse(row["passed"])
        self.assertIn("policy:tool_not_allowed:call_0", row["failures"])
        self.assertIn("policy:forbidden_argument_key:call_0", row["failures"])
        self.assertIn("policy:cost_budget_exceeded:call_0", row["failures"])

    def test_matching_reports_have_no_regressions(self):
        report = evaluate_suite(EXAMPLES / "suite.json")
        compared = compare_reports(report, report)
        self.assertTrue(compared["passed_regression_gate"])
        self.assertEqual(compared["pass_rate_delta"], 0)

    def test_regressions_are_detected(self):
        report = evaluate_suite(EXAMPLES / "suite.json")
        candidate = json.loads(json.dumps(report))
        candidate["cases"][0]["passed"] = False
        compared = compare_reports(report, candidate)
        self.assertEqual(compared["regressions"], ["search-citation"])

    def test_different_cases_cannot_be_compared(self):
        report = evaluate_suite(EXAMPLES / "suite.json")
        candidate = json.loads(json.dumps(report))
        candidate["cases"].pop()
        with self.assertRaises(SuiteError):
            compare_reports(report, candidate)

    def test_rejects_path_traversal(self):
        suite = json.loads((EXAMPLES / "suite.json").read_text())
        suite["cases"][0]["trace"] = "../outside.jsonl"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(suite))
            with self.assertRaises(SuiteError):
                evaluate_suite(path)

    def test_cli_gate(self):
        self.assertEqual(main(["gate", str(EXAMPLES / "proposal.json"), "--policy", str(EXAMPLES / "policy.json")]), 0)

    def test_cli_evaluation_report(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            self.assertEqual(main(["eval", str(EXAMPLES / "suite.json"), "--output", str(destination)]), 0)
            self.assertEqual(json.loads(destination.read_text())["summary"]["passed"], 2)

    def test_cli_adversarial_exit_code(self):
        self.assertEqual(main(["eval", str(EXAMPLES / "adversarial-suite.json")]), 1)


if __name__ == "__main__":
    unittest.main()
