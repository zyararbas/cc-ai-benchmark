"""Runners: the pluggable thing under test.

A runner is any callable that takes a `Task` and returns the system's answer as
a string. Register one with `@register("my-runner")` and it becomes selectable
from the CLI via `--runner my-runner`.

The two runners here are baselines, not real systems: `echo` establishes the
plumbing works, `oracle` establishes the maximum score a suite can award.
"""

from __future__ import annotations

from collections.abc import Callable

from cc_ai_benchmark.models import Task

Runner = Callable[[Task], str]

_REGISTRY: dict[str, Runner] = {}


def register(name: str) -> Callable[[Runner], Runner]:
    """Register a runner under `name`."""

    def decorator(func: Runner) -> Runner:
        if name in _REGISTRY:
            raise ValueError(f"runner {name!r} is already registered")
        _REGISTRY[name] = func
        return func

    return decorator


def get_runner(name: str) -> Runner:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown runner {name!r} (available: {', '.join(available())})") from None


def available() -> list[str]:
    return sorted(_REGISTRY)


@register("echo")
def echo_runner(task: Task) -> str:
    """Return the prompt unchanged — a floor to measure real runners against."""
    return task.prompt


@register("oracle")
def oracle_runner(task: Task) -> str:
    """Return the expected answer — the ceiling, and a check that scoring works."""
    return task.expected if task.expected is not None else ""
