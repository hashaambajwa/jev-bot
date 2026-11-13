"""Load, bound and validate JSONL trajectories without executing them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .policy import PolicyError, _number


class TraceError(ValueError):
    """Trace was incomplete or internally inconsistent."""


@dataclass(frozen=True)
class Trace:
    run_id: str
    events: tuple[dict[str, Any], ...]
    calls: tuple[dict[str, Any], ...]
    results: tuple[dict[str, Any], ...]
    final_answer: str
    cost_usd: float
    latency_ms: float

    @property
    def tools(self) -> list[str]:
        return [event["tool"] for event in self.calls]


def read_trace(path: str | Path, *, max_bytes: int = 2_000_000, max_events: int = 10_000) -> Trace:
    path = Path(path)
    try:
        if path.stat().st_size > max_bytes:
            raise TraceError(f"trace exceeds {max_bytes} byte limit")
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise TraceError(f"cannot read trace: {exc}") from exc
    if not lines:
        raise TraceError("trace is empty")
    if len(lines) > max_events:
        raise TraceError(f"trace exceeds {max_events} event limit")

    events: list[dict[str, Any]] = []
    calls: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}
    run_id: str | None = None
    final: dict[str, Any] | None = None
    total_cost = 0.0
    total_latency = 0.0

    for index, line in enumerate(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceError(f"line {index+1}: invalid JSON: {exc.msg}") from exc
        if not isinstance(event, dict):
            raise TraceError(f"line {index+1}: event must be an object")
        if event.get("step") != index or isinstance(event.get("step"), bool):
            raise TraceError(f"line {index+1}: step must be {index}")
        current_run = event.get("run_id")
        if not isinstance(current_run, str) or not current_run:
            raise TraceError(f"line {index+1}: run_id must be a non-empty string")
        if run_id is None:
            run_id = current_run
        if run_id != current_run:
            raise TraceError(f"line {index+1}: mixed run_id values")
        kind = event.get("event")
        if kind not in {"tool_call", "tool_result", "final"}:
            raise TraceError(f"line {index+1}: unsupported event type")
        if final is not None:
            raise TraceError(f"line {index+1}: event after final")
        if kind == "tool_call":
            cid = event.get("call_id")
            if not isinstance(cid, str) or not cid or cid in calls:
                raise TraceError(f"line {index+1}: duplicate or invalid call_id")
            if not isinstance(event.get("tool"), str) or not event["tool"]:
                raise TraceError(f"line {index+1}: missing tool")
            if not isinstance(event.get("arguments", {}), dict):
                raise TraceError(f"line {index+1}: arguments must be an object")
            if not isinstance(event.get("approved", False), bool):
                raise TraceError(f"line {index+1}: approved must be boolean")
            try:
                total_cost += _number(event.get("cost_usd", 0), "cost_usd")
                total_latency += _number(event.get("latency_ms", 0), "latency_ms")
            except PolicyError as exc:
                raise TraceError(f"line {index+1}: {exc}") from exc
            calls[cid] = event
        elif kind == "tool_result":
            cid = event.get("call_id")
            if not isinstance(cid, str) or cid not in calls:
                raise TraceError(f"line {index+1}: result without prior call")
            if cid in results:
                raise TraceError(f"line {index+1}: duplicate result")
            if not isinstance(event.get("success"), bool):
                raise TraceError(f"line {index+1}: success must be boolean")
            results[cid] = event
        elif kind == "final":
            if not isinstance(event.get("answer"), str):
                raise TraceError(f"line {index+1}: final.answer must be string")
            final = event
        events.append(event)
    if final is None:
        raise TraceError("trace missing final event")
    if calls.keys() != results.keys():
        raise TraceError("one or more tool calls have no result")
    return Trace(
        run_id=run_id or "",
        events=tuple(events),
        calls=tuple(calls.values()),
        results=tuple(results.values()),
        final_answer=final["answer"],
        cost_usd=round(total_cost, 8),
        latency_ms=round(total_latency, 3),
    )
