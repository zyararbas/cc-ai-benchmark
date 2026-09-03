"""Scorers: how an output is turned into a number in [0.0, 1.0]."""

from __future__ import annotations

from collections.abc import Callable

from cc_ai_benchmark.models import Task

Scorer = Callable[[Task, str], float]

_REGISTRY: dict[str, Scorer] = {}


def register(name: str) -> Callable[[Scorer], Scorer]:
    def decorator(func: Scorer) -> Scorer:
        if name in _REGISTRY:
            raise ValueError(f"scorer {name!r} is already registered")
        _REGISTRY[name] = func
        return func

    return decorator


def get_scorer(name: str) -> Scorer:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown scorer {name!r} (available: {', '.join(available())})") from None


def available() -> list[str]:
    return sorted(_REGISTRY)


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


@register("exact_match")
def exact_match(task: Task, output: str) -> float:
    """1.0 when the output equals `expected` ignoring case and surrounding space."""
    if task.expected is None:
        return 0.0
    return 1.0 if _normalize(output) == _normalize(task.expected) else 0.0


@register("contains")
def contains(task: Task, output: str) -> float:
    """1.0 when `expected` appears anywhere in the output. Useful for prose answers."""
    if task.expected is None:
        return 0.0
    return 1.0 if _normalize(task.expected) in _normalize(output) else 0.0
