"""Turning config/models.json into live adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cc_ai_benchmark.adapters.base import get_adapter

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = REPO_ROOT / "config" / "models.json"

PLACEHOLDER = "FILL-IN"


def load_config(path: Path = MODELS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"systems": {}}


def placeholders(config: dict[str, Any]) -> list[str]:
    """System keys still carrying an unset model id."""
    unset = []
    for key, spec in config.get("systems", {}).items():
        blob = json.dumps(spec)
        if PLACEHOLDER in blob:
            unset.append(key)
    return sorted(unset)


def build(name: str, config: dict[str, Any] | None = None):
    config = config or load_config()
    spec = dict(config.get("systems", {}).get(name) or {})
    if not spec:
        known = ", ".join(sorted(config.get("systems", {}))) or "none"
        raise KeyError(f"unknown system {name!r} in config/models.json (defined: {known})")
    if PLACEHOLDER in json.dumps(spec):
        raise ValueError(
            f"system {name!r} still has a placeholder model id in config/models.json -- "
            "set the exact provider snapshot id first"
        )
    adapter_name = spec.pop("adapter")
    return get_adapter(adapter_name, **spec)
