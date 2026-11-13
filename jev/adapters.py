"""Lossless-ish import of OpenAI-style chat tool-call transcripts.

This adapter imports recorded messages. It does not call a model, execute tools,
or infer provider billing. Per-call metrics must be supplied by trusted host code.
"""

from __future__ import annotations

from typing import Any

from .jsonutil import strict_loads
from .policy import PolicyError, _number


class AdapterError(ValueError):
    """Recorded chat messages cannot be safely normalized."""


def import_openai_chat(data: dict[str, Any], *, run_id: str) -> list[dict[str, Any]]:
    """Convert a recorded Chat Completions-style exchange to event contract v1.

    Input: {"messages": [...], "call_metrics": {call_id: {
      "success": bool, "approved": bool, "cost_usd": number,
      "latency_ms": number
    }}}.
    Metrics must come from trusted runtime instrumentation, not a model reply.
    """
    if not isinstance(run_id, str) or not run_id:
        raise AdapterError("run_id must be a non-empty string")
    if not isinstance(data, dict):
        raise AdapterError("input must be an object")
    messages = data.get("messages")
    metrics = data.get("call_metrics")
    if not isinstance(messages, list) or not isinstance(metrics, dict):
        raise AdapterError("messages array and call_metrics object are required")
    if len(messages) > 10_000:
        raise AdapterError("message count exceeds maximum")
    events: list[dict[str, Any]] = []
    calls: set[str] = set()
    results: set[str] = set()
    answer: str | None = None
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise AdapterError(f"message {index}: must be an object")
        role = message.get("role")
        if role == "assistant":
            tool_calls = message.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                raise AdapterError(f"message {index}: tool_calls must be an array")
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("type") != "function":
                    raise AdapterError("only function tool calls are supported")
                cid = call.get("id")
                func = call.get("function")
                if not isinstance(cid, str) or not cid or cid in calls:
                    raise AdapterError("invalid or duplicate tool call id")
                if not isinstance(func, dict) or not isinstance(func.get("name"), str) or not func["name"]:
                    raise AdapterError(f"tool call {cid}: missing function name")
                arguments = func.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = strict_loads(arguments)
                    except ValueError as exc:
                        raise AdapterError(f"tool call {cid}: invalid arguments: {exc}") from exc
                if not isinstance(arguments, dict):
                    raise AdapterError(f"tool call {cid}: arguments must be a JSON object")
                metric = metrics.get(cid)
                if not isinstance(metric, dict) or set(metric) != {"success", "approved", "cost_usd", "latency_ms"}:
                    raise AdapterError(f"tool call {cid}: requires explicit trusted metrics")
                if not isinstance(metric["success"], bool) or not isinstance(metric["approved"], bool):
                    raise AdapterError(f"tool call {cid}: success and approved must be booleans")
                try:
                    cost = _number(metric["cost_usd"], "cost_usd")
                    latency = _number(metric["latency_ms"], "latency_ms")
                except PolicyError as exc:
                    raise AdapterError(f"tool call {cid}: {exc}") from exc
                events.append({
                    "run_id": run_id, "step": len(events), "event": "tool_call",
                    "call_id": cid, "tool": func["name"], "arguments": arguments,
                    "approved": metric["approved"], "cost_usd": cost,
                    "latency_ms": latency,
                })
                calls.add(cid)
            content = message.get("content")
            if not tool_calls and isinstance(content, str):
                answer = content
        elif role == "tool":
            cid = message.get("tool_call_id")
            if not isinstance(cid, str) or cid not in calls or cid in results:
                raise AdapterError(f"message {index}: unmatched/duplicate tool result")
            events.append({
                "run_id": run_id, "step": len(events), "event": "tool_result",
                "call_id": cid, "success": metrics[cid]["success"],
                "output": message.get("content"),
            })
            results.add(cid)
        elif role in {"system", "developer", "user"}:
            continue
        else:
            raise AdapterError(f"message {index}: unsupported role {role!r}")
    if calls != results:
        raise AdapterError("some tool calls have no recorded results")
    if answer is None:
        raise AdapterError("missing final assistant message")
    events.append({
        "run_id": run_id, "step": len(events), "event": "final",
        "answer": answer,
    })
    return events
