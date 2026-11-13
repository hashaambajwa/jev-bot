"""Deterministic trajectory grading and paired regression comparisons."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .policy import PolicyError, evaluate_proposal, validate_policy
from .jsonutil import strict_loads
from .trace import Trace, TraceError, read_trace


class SuiteError(ValueError):
    """Invalid benchmark configuration."""


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise SuiteError(f"{name} must be a list of non-empty strings")
    return value


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * pct
    low = math.floor(pos)
    high = math.ceil(pos)
    return round(ordered[low] * (high - pos) + ordered[high] * (pos - low), 3) if high != low else round(ordered[low], 3)


def _expectations(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SuiteError("expect must be an object")
    valid = {
        "must_call", "must_not_call", "tool_sequence", "final_contains",
        "max_tool_calls", "max_cost_usd", "max_latency_ms",
        "require_successful_tools",
    }
    if set(data) - valid:
        raise SuiteError(f"unknown assertion(s): {sorted(set(data) - valid)}")
    result = {}
    for key in ("must_call", "must_not_call", "tool_sequence", "final_contains"):
        if key in data:
            result[key] = _string_list(data[key], key)
    for key in ("max_tool_calls", "max_cost_usd", "max_latency_ms"):
        if key in data:
            val = data[key]
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(float(val)) or val < 0:
                raise SuiteError(f"{key} must be a finite non-negative number")
            if key == "max_tool_calls" and not isinstance(val, int):
                raise SuiteError("max_tool_calls must be an integer")
            result[key] = val
    if "require_successful_tools" in data:
        if not isinstance(data["require_successful_tools"], bool):
            raise SuiteError("require_successful_tools must be boolean")
        result["require_successful_tools"] = data["require_successful_tools"]
    if not result:
        raise SuiteError("at least one assertion is required per case")
    return result


def grade_trace(trace: Trace, expect: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    assertions = _expectations(expect)
    failures: list[str] = []
    called = trace.tools
    for tool in assertions.get("must_call", []):
        if tool not in called:
            failures.append(f"missing_tool:{tool}")
    for tool in assertions.get("must_not_call", []):
        if tool in called:
            failures.append(f"forbidden_tool:{tool}")
    if "tool_sequence" in assertions and called != assertions["tool_sequence"]:
        failures.append("tool_sequence_mismatch")
    for phrase in assertions.get("final_contains", []):
        if phrase.casefold() not in trace.final_answer.casefold():
            failures.append(f"final_missing:{phrase}")
    if len(called) > assertions.get("max_tool_calls", float("inf")):
        failures.append("max_tool_calls_exceeded")
    if trace.cost_usd > assertions.get("max_cost_usd", float("inf")) + 1e-10:
        failures.append("max_cost_usd_exceeded")
    if trace.latency_ms > assertions.get("max_latency_ms", float("inf")) + 1e-10:
        failures.append("max_latency_ms_exceeded")
    if assertions.get("require_successful_tools", False) and any(
        not result["success"] for result in trace.results
    ):
        failures.append("tool_failed")

    if policy is not None:
        prior_cost = 0.0
        for index, call in enumerate(trace.calls):
            decision = evaluate_proposal(
                policy,
                {
                    "tool": call["tool"],
                    "arguments": call.get("arguments", {}),
                    "approved": call.get("approved", False),
                    "cost_estimate_usd": call.get("cost_usd", 0.0),
                },
                previous_calls=index,
                previous_cost_usd=prior_cost,
            )
            failures.extend(f"policy:{reason}:call_{index}" for reason in decision.reasons)
            prior_cost += call.get("cost_usd", 0.0)
    return {
        "passed": not failures,
        "failures": failures,
        "tool_calls": len(called),
        "cost_usd": trace.cost_usd,
        "latency_ms": trace.latency_ms,
    }


def _resolve_trace(root: Path, relpath: str) -> Path:
    candidate = Path(relpath)
    if candidate.is_absolute() or not candidate.parts:
        raise SuiteError("trace paths must be non-empty and relative")
    full = (root / candidate).resolve()
    if not full.is_relative_to(root.resolve()):
        raise SuiteError("trace path escapes suite directory")
    if full.suffix != ".jsonl":
        raise SuiteError("trace path must end in .jsonl")
    return full


def evaluate_suite(suite_path: str | Path) -> dict[str, Any]:
    suite_path = Path(suite_path).resolve()
    try:
        suite = strict_loads(suite_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SuiteError(f"cannot read suite: {exc}") from exc
    if not isinstance(suite, dict) or suite.get("version") != 1:
        raise SuiteError("suite must be an object with version 1")
    if set(suite) - {"version", "policy", "cases"}:
        raise SuiteError("unknown suite fields")
    policy = validate_policy(suite["policy"]) if "policy" in suite else None
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SuiteError("suite.cases must be a non-empty list")
    if len(cases) > 500:
        raise SuiteError("suite supports at most 500 cases")
    ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "trace", "expect"}:
            raise SuiteError("each case must contain id, trace, expect")
        cid = case["id"]
        if not isinstance(cid, str) or not cid or cid in ids:
            raise SuiteError("case ids must be unique, non-empty strings")
        ids.add(cid)
        expectations = _expectations(case["expect"])
        if not isinstance(case["trace"], str):
            raise SuiteError(f"{cid}: trace must be a string")
        trace_path = _resolve_trace(suite_path.parent, case["trace"])
        try:
            trace = read_trace(trace_path)
            grade = grade_trace(trace, expectations, policy)
        except (TraceError, PolicyError) as exc:
            grade = {
                "passed": False, "failures": [f"invalid_trace:{exc}"],
                "tool_calls": 0, "cost_usd": 0.0, "latency_ms": 0.0,
            }
        rows.append({"id": cid, **grade})
    costs = [row["cost_usd"] for row in rows]
    durations = [row["latency_ms"] for row in rows]
    passed = sum(row["passed"] for row in rows)
    return {
        "version": 1,
        "summary": {
            "cases": len(rows),
            "passed": passed,
            "pass_rate": round(passed / len(rows), 4),
            "total_cost_usd": round(sum(costs), 8),
            "p50_latency_ms": _percentile(durations, 0.50),
            "p95_latency_ms": _percentile(durations, 0.95),
        },
        "cases": rows,
    }


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    def index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if not isinstance(report, dict) or report.get("version") != 1:
            raise SuiteError("report version must equal 1")
        cases = report.get("cases")
        if not isinstance(cases, list) or not cases:
            raise SuiteError("report must contain cases")
        indexed: dict[str, dict[str, Any]] = {}
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not isinstance(case.get("passed"), bool):
                raise SuiteError("invalid report case")
            if case["id"] in indexed:
                raise SuiteError("duplicate report case")
            indexed[case["id"]] = case
        return indexed

    a = index(baseline)
    b = index(candidate)
    if set(a) != set(b):
        raise SuiteError("baseline and candidate must have identical case ids")
    regressions = sorted(k for k in a if a[k]["passed"] and not b[k]["passed"])
    improvements = sorted(k for k in a if not a[k]["passed"] and b[k]["passed"])
    before = sum(row["passed"] for row in a.values()) / len(a)
    after = sum(row["passed"] for row in b.values()) / len(b)
    return {
        "version": 1,
        "cases": len(a),
        "baseline_pass_rate": round(before, 4),
        "candidate_pass_rate": round(after, 4),
        "pass_rate_delta": round(after - before, 4),
        "regressions": regressions,
        "improvements": improvements,
        "passed_regression_gate": len(regressions) == 0,
        "note": "Deterministic paired comparison only; not evidence of statistical significance.",
    }
