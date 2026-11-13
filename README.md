# Jev

**Decision-time contracts and offline evaluation for tool-using AI agents.**

Jev is a small, dependency-free Python toolkit for validating agent tool calls *before execution* and grading completed trajectories *after execution*. It provides explainable policy decisions, trace integrity checks, and repeatable regression gates.

> Status: early developer release. The engine evaluates structured tool/agent events; it does not claim to independently measure an LLM's reasoning quality or prevent all prompt injection.

## Quick start

    python -m pip install -e .
    python -m unittest discover -s tests -v
    jev gate examples/proposal.json --policy examples/policy.json
    jev eval examples/suite.json --output results.json
    jev compare examples/reference-results.json results.json

## Why Jev?

Real agent incidents rarely look like a model failing a trivia question. They look like actions being taken without approval, malformed tool calls, unobserved failures, excessive tool spending, or a regression between versions. Jev isolates those cases as deterministic, code-reviewable contracts.

Features:
- Deny-by-default decision gate for proposed tool invocations
- Configurable tool allowlists, approval requirements, argument rules and budgets
- Structured JSONL trace validation with call/result correlation
- Task-specific assertions, failure categories and aggregate p50/p95 metrics
- Machine-readable reports and CI-friendly exit codes
- Standard-library runtime; no model credentials or external network calls

## Repository layout

- jev/ — schema validation, policy engine, trace reader, graders and CLI
- examples/ — synthetic decisions and trace suites
- tests/ — regression tests covering both expected and adversarial behavior
- docs/ — architecture, security boundaries and integration guides

See docs/architecture.md and docs/integration.md for details.

## Scope and limitations

Jev operates on trace data supplied by an application. It does not execute tool calls, verify the truth of untrusted tool outputs, or replace runtime authorization on external systems. A real agent must wire the decision gate into its tool dispatcher, and must not permit bypass paths. The shipped fixtures are illustrative, not an empirical model benchmark.

## License

MIT.