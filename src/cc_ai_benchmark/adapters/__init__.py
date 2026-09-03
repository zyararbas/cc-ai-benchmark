"""Adapter registry.

Provider adapters import their SDK lazily, so importing this package never
requires a key or an optional dependency: an adapter you are not running costs
nothing to have registered.
"""

from __future__ import annotations

import importlib

from cc_ai_benchmark.adapters.base import (
    Adapter,
    BaseAdapter,
    Query,
    Response,
    available,
    get_adapter,
    register,
)

_MODULES = ("mock", "anthropic_adapter", "gemini", "openai_adapter", "grounded")
_LOADED = False


def load_all() -> None:
    """Import every adapter module so the registry is populated."""
    global _LOADED
    if _LOADED:
        return
    for name in _MODULES:
        importlib.import_module(f"cc_ai_benchmark.adapters.{name}")
    _LOADED = True


__all__ = [
    "Adapter",
    "BaseAdapter",
    "Query",
    "Response",
    "available",
    "get_adapter",
    "load_all",
    "register",
]
