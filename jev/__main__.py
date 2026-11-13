"""Command line entry point: python -m jev and jev."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .evaluation import SuiteError, compare_reports, evaluate_suite
from .jsonutil import strict_loads
from .policy import PolicyError, evaluate_proposal, load_policy
from .trace import TraceError


def _json_file(path: str) -> dict[str, Any]:
    try:
        value = strict_loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON file {path} must contain an object")
    return value


def _write_report(report: dict[str, Any], path: str | None) -> None:
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(data, end="")
    else:
        Path(path).write_text(data, encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jev", description="Agent policy gates and trajectory regression tests"
    )
    subs = parser.add_subparsers(dest="command", required=True)
    gate = subs.add_parser("gate", help="decide if a proposed action is permitted")
    gate.add_argument("proposal", help="JSON tool proposal")
    gate.add_argument("--policy", required=True, help="JSON policy contract")
    gate.add_argument("--previous-calls", type=int, default=0)
    gate.add_argument("--previous-cost", type=float, default=0.0)
    ev = subs.add_parser("eval", help="evaluate a fixture suite of JSONL traces")
    ev.add_argument("suite")
    ev.add_argument("--output", help="write a JSON report")
    cmp_ = subs.add_parser("compare", help="compare matched evaluation reports")
    cmp_.add_argument("baseline")
    cmp_.add_argument("candidate")
    cmp_.add_argument("--output", help="write a JSON report")
    args = parser.parse_args(argv)
    try:
        if args.command == "gate":
            decision = evaluate_proposal(
                load_policy(args.policy),
                _json_file(args.proposal),
                previous_calls=args.previous_calls,
                previous_cost_usd=args.previous_cost,
            )
            _write_report(decision.as_dict(), None)
            return 0 if decision.allowed else 1
        if args.command == "eval":
            report = evaluate_suite(args.suite)
            _write_report(report, args.output)
            return 0 if report["summary"]["passed"] == report["summary"]["cases"] else 1
        if args.command == "compare":
            report = compare_reports(_json_file(args.baseline), _json_file(args.candidate))
            _write_report(report, args.output)
            return 0 if report["passed_regression_gate"] else 1
    except (OSError, ValueError, PolicyError, TraceError, SuiteError) as exc:
        print(f"jev: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
