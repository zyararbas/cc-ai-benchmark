"""Our approach: the source material, plus a model underneath.

This is the one adapter meant to be edited. The baselines exist to be left
alone -- they represent a general-purpose model asked a question -- whereas this
file is where the actual product idea lives, and `answer_with_material` is a
plain function so that changing the approach means changing a function body
rather than the harness.

Three grounding strategies ship, differing by about two orders of magnitude in
cost:

  oracle     the item's own source document       ~6k tokens/item   ceiling
  retrieval  the shared retriever's top hit       ~6k tokens/item   honest
  full       the entire 23-document corpus        ~141k tokens/item strongest

`full` is only affordable because the corpus is small enough to cache: the
prefix is byte-identical on every call, so it is written once and read back at a
fraction of the price. Without caching it is roughly 10x the cost for the same
answers, which is why the cache is on by default and its hit rate is reported.
"""

from __future__ import annotations

from typing import Any

from cc_ai_benchmark.adapters.base import BaseAdapter, Query, Response, register
from cc_ai_benchmark.corpus import full_corpus, oracle_context, retrieve
from cc_ai_benchmark.evalprompt import render_options

STRATEGIES = ("oracle", "retrieval", "full")

INSTRUCTION = (
    "You are a Property & Casualty insurance expert answering an examination "
    "question. Reference material from the licensing curriculum is provided.\n\n"
    "Work from the material. If the material does not settle the question, say so "
    "by answering null rather than guessing from general knowledge.\n\n"
    "Reply with a single JSON object and nothing else:\n"
    '{"answer": "<A|B|C|D>", "confidence": <0.0-1.0>, "basis": "<short quote or '
    'section reference from the material>"}'
)


def gather_material(item, strategy: str, k: int = 2, max_chars: int | None = None) -> str:
    """The material this approach puts in front of the model for one item."""
    if strategy == "oracle":
        text = oracle_context(item.ref) or ""
    elif strategy == "retrieval":
        sections = retrieve(item.question, item.choices, k=k)
        text = "\n\n".join(f"### {s.ref}\n\n{s.text}" for s in sections)
    elif strategy == "full":
        text = full_corpus()
    else:
        raise ValueError(f"unknown grounding strategy {strategy!r} (use one of {STRATEGIES})")
    return text[:max_chars] if max_chars else text


def answer_with_material(item, material: str) -> tuple[str, str]:
    """Build the (system, user) pair for a grounded answer.

    Edit this to change what "our approach" means. The material goes in the
    system prefix rather than the user turn so it stays byte-identical across
    items and stays cacheable; only the question varies.
    """
    system = f"{INSTRUCTION}\n\nReference material:\n<material>\n{material}\n</material>"
    user = f"Question:\n{item.question.strip()}\n\nOptions:\n{render_options(item)}"
    return system, user


@register("grounded")
class GroundedAdapter(BaseAdapter):
    """Wraps any base adapter and feeds it the source material.

    The model underneath is a parameter, so the same approach can be re-measured
    on a different model without touching the approach itself -- which is the
    comparison worth having: how much of the result is the material, and how
    much is the model.
    """

    name = "grounded"

    def __init__(
        self,
        base: Any = None,
        base_system: str = "gemini",
        base_kwargs: dict[str, Any] | None = None,
        strategy: str = "full",
        k: int = 2,
        max_chars: int | None = None,
        label: str = "our-approach",
        **_: Any,
    ):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown grounding strategy {strategy!r} (use one of {STRATEGIES})")
        if base is None:
            from cc_ai_benchmark.adapters.base import get_adapter

            base = get_adapter(base_system, **(base_kwargs or {}))
        self.base = base
        self.strategy = strategy
        self.k = k
        self.max_chars = max_chars
        self.name = label
        self.concurrency = getattr(base, "concurrency", 4)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": "GroundedAdapter",
            "approach": "source material + model",
            "strategy": self.strategy,
            "retrieval_k": self.k if self.strategy == "retrieval" else None,
            "max_chars": self.max_chars,
            "underlying": self.base.describe(),
        }

    def _invoke(self, query: Query) -> Response:
        material = gather_material(query.item, self.strategy, self.k, self.max_chars)
        system, user = answer_with_material(query.item, material)
        grounded_query = Query(
            item=query.item,
            condition=query.condition,
            prompt=user,
            system=system,
            context=material,
            seed=query.seed,
        )
        response = self.base.answer(grounded_query)
        response.raw = dict(response.raw or {})
        response.raw["grounding"] = {
            "strategy": self.strategy,
            "material_chars": len(material),
        }
        return response

    def close(self) -> None:
        self.base.close()
