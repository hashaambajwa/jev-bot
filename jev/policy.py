"""Fail-closed, deterministic tool-call policy checks.

This is an application-layer policy gate, not a substitute for service-side
authorization. The caller must enforce a denied decision before tool execution.
"""

from __future__ import annotations

import json

from .jsonutil import strict_loads
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class PolicyError(ValueError):
    """Malformed policy or proposal; callers should deny on this error."""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reasons": list(self.reasons)}


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{name} must be a finite non-negative number")
    num = float(value)
    if not math.isfinite(num) or num < 0:
        raise PolicyError(f"{name} must be a finite non-negative number")
    return num


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise PolicyError(f"{name} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise PolicyError(f"{name} must not contain duplicates")
    return value


def validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise PolicyError("policy must be a JSON object")
    permitted = {
        "version", "allowed_tools", "approval_required",
        "forbidden_argument_keys", "max_tool_calls", "max_total_cost_usd",
    }
    extra = set(policy) - permitted
    if extra:
        raise PolicyError(f"unknown policy field(s): {', '.join(sorted(extra))}")
    if policy.get("version") != 1 or isinstance(policy.get("version"), bool):
        raise PolicyError("policy.version must equal 1")
    allowed = _strings(policy.get("allowed_tools"), "allowed_tools")
    approved = _strings(policy.get("approval_required", []), "approval_required")
    forbidden = _strings(
        policy.get("forbidden_argument_keys", []), "forbidden_argument_keys"
    )
    if not set(approved).issubset(allowed):
        raise PolicyError("approval_required tools must be in allowed_tools")
    if "max_tool_calls" in policy:
        count = policy["max_tool_calls"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise PolicyError("max_tool_calls must be a non-negative integer")
    if "max_total_cost_usd" in policy:
        _number(policy["max_total_cost_usd"], "max_total_cost_usd")
    return {
        "version": 1,
        "allowed_tools": allowed,
        "approval_required": approved,
        "forbidden_argument_keys": forbidden,
        "max_tool_calls": policy.get("max_tool_calls"),
        "max_total_cost_usd": policy.get("max_total_cost_usd"),
    }


def load_policy(path: str | Path) -> dict[str, Any]:
    try:
        data = strict_loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyError(f"cannot read policy: {exc}") from exc
    return validate_policy(data)


def _nested_keys(value: Any, *, depth: int = 0) -> set[str]:
    # JSON cannot contain cyclic references, but programmatic callers could.
    if depth > 32:
        raise PolicyError("arguments exceed maximum nesting depth")
    if isinstance(value, dict):
        keys: set[str] = set()
        for key, child in value.items():
            if not isinstance(key, str):
                raise PolicyError("argument keys must be strings")
            keys.add(key.casefold())
            keys.update(_nested_keys(child, depth=depth + 1))
        return keys
    if isinstance(value, list):
        keys = set()
        for child in value:
            keys.update(_nested_keys(child, depth=depth + 1))
        return keys
    return set()


def evaluate_proposal(
    policy: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    previous_calls: int = 0,
    previous_cost_usd: float = 0.0,
) -> Decision:
    rules = validate_policy(policy)
    if not isinstance(proposal, dict):
        raise PolicyError("proposal must be an object")
    tool = proposal.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        raise PolicyError("proposal.tool must be a non-empty string")
    arguments = proposal.get("arguments", {})
    if not isinstance(arguments, dict):
        raise PolicyError("proposal.arguments must be an object")
    approved = proposal.get("approved", False)
    if not isinstance(approved, bool):
        raise PolicyError("proposal.approved must be boolean")
    cost = _number(proposal.get("cost_estimate_usd", 0), "cost_estimate_usd")
    spent = _number(previous_cost_usd, "previous_cost_usd")
    if isinstance(previous_calls, bool) or not isinstance(previous_calls, int) or previous_calls < 0:
        raise PolicyError("previous_calls must be a non-negative integer")

    reasons: list[str] = []
    if tool not in rules["allowed_tools"]:
        reasons.append("tool_not_allowed")
    if tool in rules["approval_required"] and not approved:
        reasons.append("approval_required")
    keys = _nested_keys(arguments)
    if keys & {key.casefold() for key in rules["forbidden_argument_keys"]}:
        reasons.append("forbidden_argument_key")
    max_calls = rules["max_tool_calls"]
    if max_calls is not None and previous_calls + 1 > max_calls:
        reasons.append("tool_call_budget_exceeded")
    max_cost = rules["max_total_cost_usd"]
    if max_cost is not None and spent + cost > float(max_cost) + 1e-10:
        reasons.append("cost_budget_exceeded")
    return Decision(allowed=not reasons, reasons=tuple(reasons))
