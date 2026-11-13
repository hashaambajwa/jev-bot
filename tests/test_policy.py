import unittest

from jev.policy import PolicyError, evaluate_proposal, validate_policy


POLICY = {
    "version": 1,
    "allowed_tools": ["search", "summarize"],
    "approval_required": ["summarize"],
    "forbidden_argument_keys": ["api_key", "password"],
    "max_tool_calls": 2,
    "max_total_cost_usd": 0.05,
}


class PolicyTests(unittest.TestCase):
    def decide(self, **kwargs):
        proposal = {"tool": "search", "arguments": {"query": "hello"}, "cost_estimate_usd": 0.01}
        proposal.update(kwargs)
        return evaluate_proposal(POLICY, proposal)

    def test_safe_tool_allowed(self):
        self.assertTrue(self.decide().allowed)

    def test_unknown_tool_denied(self):
        self.assertEqual(self.decide(tool="delete").reasons, ("tool_not_allowed",))

    def test_requires_explicit_approval(self):
        self.assertEqual(self.decide(tool="summarize").reasons, ("approval_required",))
        self.assertTrue(self.decide(tool="summarize", approved=True).allowed)

    def test_nested_sensitive_keys_denied(self):
        d = self.decide(arguments={"body": [{"api_KEY": "secret"}]})
        self.assertEqual(d.reasons, ("forbidden_argument_key",))

    def test_call_budget(self):
        d = evaluate_proposal(POLICY, {"tool": "search"}, previous_calls=2)
        self.assertIn("tool_call_budget_exceeded", d.reasons)

    def test_cost_budget(self):
        d = evaluate_proposal(
            POLICY, {"tool": "search", "cost_estimate_usd": 0.03},
            previous_cost_usd=0.03
        )
        self.assertIn("cost_budget_exceeded", d.reasons)

    def test_invalid_approval_is_rejected(self):
        with self.assertRaises(PolicyError):
            self.decide(approved="yes")

    def test_invalid_cost_denied_fail_closed(self):
        with self.assertRaises(PolicyError):
            self.decide(cost_estimate_usd=float("nan"))

    def test_invalid_policy_rejected(self):
        with self.assertRaises(PolicyError):
            validate_policy({**POLICY, "unknown_setting": True})
        with self.assertRaises(PolicyError):
            validate_policy({**POLICY, "allowed_tools": [] if False else "search"})

    def test_missing_approval_tool_rejected(self):
        with self.assertRaises(PolicyError):
            validate_policy({**POLICY, "approval_required": ["drop_database"]})


if __name__ == "__main__":
    unittest.main()
