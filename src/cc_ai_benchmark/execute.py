"""Running systems over the bank, concurrently.

Two levels of parallelism. Systems run side by side -- one worker per system,
each independent, so a rate-limited provider never stalls the others. Within a
system, items run on that adapter's own bounded pool, because the safe in-flight
count is a property of the endpoint, not of the harness.

A budget ceiling is checked as spend accumulates: the run stops and reports what
it has rather than overrunning silently.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from cc_ai_benchmark.adapters.base import Query, Response
from cc_ai_benchmark.bank import Item
from cc_ai_benchmark.corpus import context_for
from cc_ai_benchmark.evalprompt import render, template_hash
from cc_ai_benchmark.grading import Grade, Outcome, grade
from cc_ai_benchmark.models import utcnow_iso


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ItemResult:
    item_id: str
    scope: str
    outcome: Outcome
    expected: str
    parsed_answer: str | None
    confidence: float | None
    latency_ms: float
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None
    error: str | None = None
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["outcome"] = str(self.outcome)
        data["text"] = self.text[:600]
        return data


@dataclass
class SystemRun:
    system: str
    condition: str
    adapter_describe: dict[str, Any]
    started_at: str
    finished_at: str
    results: list[ItemResult]
    template_hash: str
    stopped_early: str | None = None


class _Budget:
    """Thread-safe running total with a hard ceiling."""

    def __init__(self, limit_usd: float | None):
        self.limit = limit_usd
        self.spent = 0.0
        self._lock = threading.Lock()

    def add(self, amount: float | None) -> None:
        if amount is None:
            return
        with self._lock:
            self.spent += amount

    def exhausted(self) -> bool:
        if self.limit is None:
            return False
        with self._lock:
            return self.spent >= self.limit


def _grade_response(item: Item, response: Response) -> tuple[Grade, ItemResult]:
    verdict = grade(item, response.text, response.error)
    return verdict, ItemResult(
        item_id=item.id,
        scope=item.scope,
        outcome=verdict.outcome,
        expected=item.answer,
        parsed_answer=verdict.parsed,
        confidence=verdict.confidence,
        latency_ms=response.latency_ms,
        usage=dict(response.usage),
        cost_usd=response.cost_usd,
        error=response.error,
        text=response.text,
    )


def run_system(
    adapter: Any,
    items: list[Item],
    condition: str,
    budget: _Budget | None = None,
    progress: Any = None,
) -> SystemRun:
    """Run one system over the bank on its own bounded pool."""
    started_at = utcnow_iso()
    budget = budget or _Budget(None)
    results: list[ItemResult] = []
    stopped: str | None = None
    workers = max(1, int(getattr(adapter, "concurrency", 4)))

    def one(item: Item) -> ItemResult | None:
        # Checked here rather than at submit time: submission runs far ahead of
        # execution, so a submit-time check lets the whole sweep through before
        # the first cost is even recorded.
        if budget.exhausted():
            return None
        context = context_for(item, condition)
        system_prompt, user_prompt = render(item, condition, context)
        query = Query(
            item=item,
            condition=condition,
            prompt=user_prompt,
            system=system_prompt,
            context=context,
        )
        response = adapter.answer(query)
        budget.add(response.cost_usd)
        _, result = _grade_response(item, response)
        return result

    skipped = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=adapter.name) as pool:
        futures = {pool.submit(one, item): item for item in items}
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                skipped += 1
                continue
            results.append(result)
            if progress:
                progress(adapter.name, len(results), len(futures))
    if skipped:
        stopped = f"budget ceiling reached: {skipped} of {len(items)} items not attempted"

    order = {item.id: n for n, item in enumerate(items)}
    results.sort(key=lambda r: order.get(r.item_id, 0))
    return SystemRun(
        system=adapter.name,
        condition=condition,
        adapter_describe=adapter.describe(),
        started_at=started_at,
        finished_at=utcnow_iso(),
        results=results,
        template_hash=template_hash(),
        stopped_early=stopped,
    )


def run_matrix(
    adapters: list[Any],
    items: list[Item],
    condition: str,
    budget_usd: float | None = None,
    progress: Any = None,
) -> list[SystemRun]:
    """Run every system over the same items at the same time.

    Systems share one budget: the ceiling is on the run, not on each model, so a
    single expensive system cannot quietly spend the whole allowance.
    """
    budget = _Budget(budget_usd)
    runs: list[SystemRun] = []
    with ThreadPoolExecutor(max_workers=max(1, len(adapters)), thread_name_prefix="system") as pool:
        futures = {
            pool.submit(run_system, adapter, items, condition, budget, progress): adapter
            for adapter in adapters
        }
        for future in as_completed(futures):
            adapter = futures[future]
            try:
                runs.append(future.result())
            except Exception as exc:
                runs.append(
                    SystemRun(
                        system=adapter.name,
                        condition=condition,
                        adapter_describe=adapter.describe(),
                        started_at=utcnow_iso(),
                        finished_at=utcnow_iso(),
                        results=[],
                        template_hash=template_hash(),
                        stopped_early=f"{type(exc).__name__}: {exc}",
                    )
                )
    runs.sort(key=lambda r: r.system)
    return runs
