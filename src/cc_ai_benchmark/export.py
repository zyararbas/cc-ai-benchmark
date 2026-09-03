"""Flattening a sweep report to one row per question, per system.

The report JSON already records usage for every item; it is just nested three
levels down where nothing can pivot on it. This writes the same numbers as CSV
so per-question token counts, latency and cost can be sorted, filtered and
charted in whatever the reader already uses.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

COLUMNS = [
    "system",
    "condition",
    "model",
    "item_id",
    "scope",
    "outcome",
    "expected",
    "parsed_answer",
    "confidence",
    "prompt_tokens",
    "cached_prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "latency_ms",
    "cost_usd",
    "error",
]


def rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for system in report.get("systems", []):
        model = system.get("adapter", {}).get("model_requested", "")
        for result in system.get("results", []):
            usage = result.get("usage") or {}
            fresh = usage.get("input_tokens", 0) or 0
            cached = usage.get("cache_read_input_tokens", 0) or 0
            completion = usage.get("output_tokens", 0) or 0
            out.append(
                {
                    "system": system["system"],
                    "condition": system["condition"],
                    "model": model,
                    "item_id": result["item_id"],
                    "scope": result["scope"],
                    "outcome": result["outcome"],
                    "expected": result["expected"],
                    "parsed_answer": result.get("parsed_answer") or "",
                    "confidence": result.get("confidence"),
                    "prompt_tokens": fresh,
                    "cached_prompt_tokens": cached,
                    "completion_tokens": completion,
                    "total_tokens": fresh + cached + completion,
                    "latency_ms": round(result.get("latency_ms", 0.0), 1),
                    "cost_usd": result.get("cost_usd"),
                    "error": result.get("error") or "",
                }
            )
    return out


def write_csv(report: dict[str, Any], path: Path) -> tuple[Path, int]:
    data = rows(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(data)
    return path, len(data)
