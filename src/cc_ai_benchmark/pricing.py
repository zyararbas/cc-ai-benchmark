"""Per-model token prices, so cost per correct answer is a measured number.

Prices move. They live in `config/pricing.json` rather than in code, the file is
hashed into every report, and a model with no price entry reports `cost_usd:
null` -- an unknown cost is recorded as unknown, never as zero.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRICING_PATH = REPO_ROOT / "config" / "pricing.json"

_CACHE: dict[str, dict] | None = None


def load(path: Path = PRICING_PATH) -> dict[str, dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _CACHE


def cost(model_id: str | None, usage: dict[str, int]) -> float | None:
    """Dollars for one call, or None when the model has no published price here."""
    if not model_id:
        return None
    table = load()
    entry = table.get(model_id)
    if entry is None:
        # Allow a prefix entry so dated snapshots inherit their family's price.
        for key, value in table.items():
            if model_id.startswith(key):
                entry = value
                break
    if entry is None or entry.get("input_per_mtok") is None:
        return None
    cached = usage.get("cache_read_input_tokens", 0)
    fresh = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cache_rate = entry.get("cache_read_per_mtok")
    if cache_rate is None:
        cache_rate = entry["input_per_mtok"] * 0.1
    total = (
        fresh * entry["input_per_mtok"]
        + cached * cache_rate
        + out * entry.get("output_per_mtok", 0.0)
    ) / 1_000_000
    return round(total, 8)
