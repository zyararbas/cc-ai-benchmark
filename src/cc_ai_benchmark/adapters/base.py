"""The system-under-test interface.

An adapter is the only thing that knows how to reach a system. Everything else
in the harness -- prompting, scoring, concurrency, reporting -- is identical
whether the system is a hosted model, an HTTP endpoint, an MCP server, or a
local function. Transport is configuration, not code.
"""

from __future__ import annotations

import random
import re
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
    #: How many calls it took. >1 means the provider was throttling; a run with
    #: a high total is a run whose latency figures describe the queue, not the
    #: model.
    attempts: int = 1
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Adapter(Protocol):
    name: str

    def describe(self) -> dict[str, Any]:
        """Everything that makes a run reproducible. Copied into the report."""
        ...

    def answer(self, query: Query) -> Response: ...

    def close(self) -> None: ...


#: Provider-agnostic signatures of a failure that is worth trying again: the
#: request was fine, the endpoint was busy. Matched against the exception text
#: because every SDK spells its own exception hierarchy differently and the
#: harness deliberately does not import them.
_RETRYABLE = re.compile(
    r"\b(429|500|502|503|504)\b"
    r"|RESOURCE_EXHAUSTED|UNAVAILABLE|DEADLINE_EXCEEDED|INTERNAL"
    r"|rate.?limit|overloaded|timed?.?out|too many requests"
    r"|connection (reset|error|aborted)|temporarily unavailable",
    re.IGNORECASE,
)

#: An account with no money does not recover inside a sweep, and retrying it
#: just burns the wall clock. Distinguished from a per-minute throttle, which is
#: exactly what retrying is for. Every term here has to name the funding state
#: specifically: Gemini's ordinary per-minute 429 says "check your plan and
#: billing details", so a bare "billing" would classify the most common
#: retryable error in this harness as permanent.
_TERMINAL = re.compile(
    r"insufficient_quota|credit_balance_exhausted|no credits remaining"
    r"|billing_not_active|account_deactivated",
    re.IGNORECASE,
)

#: Providers say how long to wait, and the answer is often far longer than any
#: backoff schedule would guess -- Gemini's token-per-minute quota returns a
#: 38-second delay against a 4th-attempt backoff of 16. Honour the server.
_RETRY_AFTER = re.compile(
    r"retryDelay['\"]?[:=]\s*['\"]?(\d+(?:\.\d+)?)s"
    r"|Please retry in (\d+(?:\.\d+)?)s"
    r"|Retry-After['\"]?[:=]\s*['\"]?(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def retryable(error: str) -> bool:
    """Whether an error is a transient throttle rather than a real answer."""
    return bool(_RETRYABLE.search(error)) and not _TERMINAL.search(error)


def retry_after(error: str, cap: float = 90.0) -> float | None:
    """The delay the provider asked for, if it named one. Capped for sanity."""
    match = _RETRY_AFTER.search(error)
    if not match:
        return None
    value = next((g for g in match.groups() if g), None)
    return min(float(value), cap) if value else None


class BaseAdapter:
    """Shared plumbing: timing, retry, error capture, cost, and concurrency."""

    name = "base"
    #: Safe number of in-flight requests. Overridden per adapter or by config.
    concurrency = 4
    #: Attempts per item before an error is recorded as the answer. A 429 is
    #: not a wrong answer, and scoring it as one silently depresses accuracy by
    #: however much the provider happened to be throttling that afternoon.
    max_attempts = 6
    #: Base seconds for exponential backoff between attempts.
    backoff_base = 2.0
    #: The condition this system is always in, whatever the sweep asked for.
    #: A baseline honours the sweep's condition and leaves this None; a system
    #: that brings its own material is at C3 no matter what flag was typed, and
    #: saying so keeps a mixed sweep from labelling half its rows wrongly.
    fixed_condition: str | None = None

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "kind": type(self).__name__}

    def _invoke(self, query: Query) -> Response:  # pragma: no cover - abstract
        raise NotImplementedError

    def answer(self, query: Query) -> Response:
        """Time the call, retry a throttle, convert any exception into a Response.

        A system that fails on one item must not abort the run. But surviving a
        failure is not the same as scoring it: a 429 recorded as an answer is an
        answer the model never gave, and it counts against accuracy exactly like
        a wrong one. So a transient failure is retried with exponential backoff
        and jitter, and only a failure that outlives the retries is recorded --
        at which point it is a real property of the run and belongs in the
        report. A quota that is out of money is not retried, because it will not
        recover before the sweep ends.
        """
        started = time.perf_counter()
        last: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._invoke(query)
            except Exception as exc:
                last = f"{type(exc).__name__}: {exc}"
                if attempt < self.max_attempts and retryable(last):
                    asked = retry_after(last)
                    if asked is not None:
                        # The provider named a delay; guessing a shorter one just
                        # spends an attempt to be told the same thing again.
                        time.sleep(asked * (1.0 + 0.25 * random.random()))
                    else:
                        # Jitter: without it, every worker that got throttled at
                        # the same moment comes back at the same moment.
                        delay = self.backoff_base * 2 ** (attempt - 1)
                        time.sleep(delay * (0.5 + random.random()))
                    continue
                return Response(
                    text="",
                    error=last,
                    attempts=attempt,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                )
            # A wrapping adapter (grounded) delegates to an inner adapter that
            # has already retried; add its count rather than resetting to 1.
            response.attempts = attempt + max(response.attempts - 1, 0)
            if not response.latency_ms:
                response.latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return response
        return Response(  # pragma: no cover - loop always returns
            text="",
            error=last,
            attempts=self.max_attempts,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

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
