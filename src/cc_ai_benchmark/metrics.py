"""Turning graded items into the numbers a run reports.

Three accuracy figures, always, because one hides the thing that matters most in
insurance: whether a system declines when it does not know.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from typing import Any

from cc_ai_benchmark.grading import Outcome


@dataclass(frozen=True)
class Metrics:
    n: int
    correct: int
    incorrect: int
    abstained: int
    parse_failures: int
    errors: int
    accuracy: float
    coverage_accuracy: float
    risk_weighted: float
    abstention_rate: float
    accuracy_ci95: tuple[float, float]
    cost_usd: float | None
    cost_per_correct: float | None
    tokens_in: int
    tokens_out: int
    latency_p50_ms: float
    latency_p95_ms: float

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["accuracy_ci95"] = list(self.accuracy_ci95)
        return data


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval: behaves at the extremes where the normal approximation does not."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return (round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return round(ordered[index], 2)


def compute(results: list[Any]) -> Metrics:
    """`results` are ItemResult records; only the fields used here are required."""
    counts = collections.Counter(r.outcome for r in results)
    n = len(results)
    correct = counts[Outcome.CORRECT]
    incorrect = counts[Outcome.INCORRECT]
    answered = correct + incorrect
    costs = [r.cost_usd for r in results if r.cost_usd is not None]
    total_cost = round(sum(costs), 6) if costs else None
    latencies = [r.latency_ms for r in results]

    return Metrics(
        n=n,
        correct=correct,
        incorrect=incorrect,
        abstained=counts[Outcome.ABSTAINED],
        parse_failures=counts[Outcome.PARSE_FAILURE],
        errors=counts[Outcome.ERROR],
        accuracy=round(correct / n, 4) if n else 0.0,
        coverage_accuracy=round(correct / answered, 4) if answered else 0.0,
        risk_weighted=round((correct - incorrect) / n, 4) if n else 0.0,
        abstention_rate=round(counts[Outcome.ABSTAINED] / n, 4) if n else 0.0,
        accuracy_ci95=_wilson(correct, n),
        cost_usd=total_cost,
        cost_per_correct=round(total_cost / correct, 6) if total_cost and correct else None,
        tokens_in=sum(r.usage.get("input_tokens", 0) for r in results),
        tokens_out=sum(r.usage.get("output_tokens", 0) for r in results),
        latency_p50_ms=_percentile(latencies, 50),
        latency_p95_ms=_percentile(latencies, 95),
    )


def by_scope(results: list[Any], min_n: int = 20) -> list[dict[str, Any]]:
    """Per-scope accuracy. Scopes below `min_n` are reported but marked unreliable."""
    grouped: dict[str, list[Any]] = collections.defaultdict(list)
    for result in results:
        grouped[result.scope].append(result)
    rows = []
    for scope, group in sorted(grouped.items()):
        metrics = compute(group)
        rows.append(
            {
                "scope": scope,
                "n": metrics.n,
                "accuracy": metrics.accuracy,
                "ci95": list(metrics.accuracy_ci95),
                "abstention_rate": metrics.abstention_rate,
                "reliable": metrics.n >= min_n,
            }
        )
    return sorted(rows, key=lambda r: -r["accuracy"])


def mcnemar(a: list[Any], b: list[Any]) -> dict[str, Any]:
    """Paired comparison over items both systems attempted.

    Two systems answering the same items are not two independent samples, and
    treating them as such throws away most of the power. Discordant pairs are
    the whole signal.
    """
    index_a = {r.item_id: r for r in a}
    index_b = {r.item_id: r for r in b}
    shared = sorted(set(index_a) & set(index_b))
    a_only = sum(
        1
        for i in shared
        if index_a[i].outcome == Outcome.CORRECT and index_b[i].outcome != Outcome.CORRECT
    )
    b_only = sum(
        1
        for i in shared
        if index_b[i].outcome == Outcome.CORRECT and index_a[i].outcome != Outcome.CORRECT
    )
    n = a_only + b_only
    # Exact binomial two-sided p under H0: discordant pairs split 50/50.
    if n == 0:
        p = 1.0
    else:
        k = min(a_only, b_only)
        tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
        p = min(1.0, 2 * tail)
    return {
        "paired_items": len(shared),
        "a_correct_b_wrong": a_only,
        "b_correct_a_wrong": b_only,
        "discordant": n,
        "p_value": round(p, 6),
        "significant_at_05": p < 0.05,
    }
