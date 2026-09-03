"""Adapters that cost nothing, for testing the harness rather than a model.

`oracle` is the ceiling and proves scoring is wired up; `refuser` is the
abstention floor; `stub` is a seeded pseudo-system whose accuracy is a knob, so
the metrics, concurrency, and reporting paths can be exercised end to end
without a network or an API key.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from cc_ai_benchmark.adapters.base import BaseAdapter, Query, Response, register


@register("oracle")
class OracleAdapter(BaseAdapter):
    """Always right. The ceiling, and a check that grading works."""

    name = "oracle"
    concurrency = 16

    def _invoke(self, query: Query) -> Response:
        return Response(
            text=f'{{"answer": "{query.item.answer}", "confidence": 1.0}}',
            model_id="oracle",
            usage={"input_tokens": 0, "output_tokens": 0},
        )


@register("refuser")
class RefuserAdapter(BaseAdapter):
    """Always declines. The abstention floor: 0.0 accuracy, 0.0 risk-weighted."""

    name = "refuser"
    concurrency = 16

    def _invoke(self, query: Query) -> Response:
        return Response(
            text='{"answer": null, "confidence": 0.0}',
            model_id="refuser",
            usage={"input_tokens": 0, "output_tokens": 0},
        )


@register("stub")
class StubAdapter(BaseAdapter):
    """A seeded pseudo-system with tunable accuracy and abstention.

    Deterministic per (seed, item), so a harness change that shifts the numbers
    is a harness bug and shows up immediately in tests.
    """

    name = "stub"
    concurrency = 8

    def __init__(
        self,
        accuracy: float = 0.7,
        abstain: float = 0.05,
        garble: float = 0.0,
        seed: int = 0,
        label: str = "stub",
        **_: Any,
    ):
        self.accuracy = accuracy
        self.abstain = abstain
        self.garble = garble
        self.seed = seed
        self.name = label

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": "StubAdapter",
            "accuracy": self.accuracy,
            "abstain": self.abstain,
            "garble": self.garble,
            "seed": self.seed,
        }

    def _invoke(self, query: Query) -> Response:
        digest = hashlib.sha256(f"{self.seed}:{query.item.id}".encode()).hexdigest()
        rng = random.Random(int(digest[:16], 16))
        roll = rng.random()
        item = query.item
        if roll < self.garble:
            text = "It depends on the specific policy language involved."
        elif roll < self.garble + self.abstain:
            text = '{"answer": null, "confidence": 0.0}'
        elif rng.random() < self.accuracy:
            text = f'{{"answer": "{item.answer}", "confidence": 0.9}}'
        else:
            wrong = [x for x in item.letters if x != item.answer]
            text = f'{{"answer": "{rng.choice(wrong)}", "confidence": 0.6}}'
        prompt_tokens = len(query.prompt) // 4
        return Response(
            text=text,
            model_id=self.name,
            usage={"input_tokens": prompt_tokens, "output_tokens": 12},
        )
