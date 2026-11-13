"""Strict JSON parsing: reject duplicate keys and non-standard numeric values."""

from __future__ import annotations

import json
from typing import Any


def strict_loads(content: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-standard JSON constant: {value}")

    return json.loads(
        content, object_pairs_hook=object_pairs, parse_constant=reject_constant
    )
