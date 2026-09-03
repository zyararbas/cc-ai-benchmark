"""The system-under-test interface.

An adapter is the only thing that knows how to reach a system. Everything else
in the harness -- prompting, scoring, concurrency, reporting -- is identical
whether the system is a hosted model, an HTTP endpoint, an MCP server, or a
local function. Transport is configuration, not code.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from cc_ai_benchmark.bank import Item


@dataclass(frozen=True)
class Query:
    """One question, rendered for one condition."""

    item: Item
    condition: str
    prompt: str
    system: str | None = None
    context: str | None = None
    seed: int | None = None


@dataclass
class Response:
    """What a system returned, plus everything needed to price and audit it.

    `usage`, `latency_ms` and `cost_usd` are part of the contract rather than an
    afterthought: cost per correct answer cannot be reconstructed after a run.
    """

    text: str
    model_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Adapter(Protocol):
    name: str

    def describe(self) -> dict[str, Any]:
        """Everything that makes a run reproducible. Copied into the report."""
        ...

    def answer(self, query: Query) -> Response: ...

    def close(self) -> None: ...


class BaseAdapter:
    """Shared plumbing: timing, error capture, cost, and concurrency declaration."""

    name = "base"
    #: Safe number of in-flight requests. Overridden per adapter or by config.
    concurrency = 4

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "kind": type(self).__name__}

    def _invoke(self, query: Query) -> Response:  # pragma: no cover - abstract
        raise NotImplementedError

    def answer(self, query: Query) -> Response:
        """Time the call and convert any exception into a Response, never a raise.

        A system that fails on one item must not abort the run -- that property
        is what lets a 679-item sweep survive a transient 500.
        """
        started = time.perf_counter()
        try:
            response = self._invoke(query)
        except Exception as exc:
            return Response(
                text="",
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        if not response.latency_ms:
            response.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return response

    def close(self) -> None:
        return None


_REGISTRY: dict[str, Any] = {}


def register(name: str):
    """Register an adapter factory under `name`, selectable as `--system <name>`."""

    def decorator(factory):
        if name in _REGISTRY:
            raise ValueError(f"adapter {name!r} is already registered")
        _REGISTRY[name] = factory
        return factory

    return decorator


def get_adapter(name: str, **kwargs: Any):
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown system {name!r} (available: {', '.join(available())})") from None
    return factory(**kwargs)


def available() -> list[str]:
    return sorted(_REGISTRY)
