"""Rendering a bank item into a prompt, versioned so runs stay comparable.

One template per condition. The template text is hashed into every report: two
runs are only comparable if the hash matches.
"""

from __future__ import annotations

import hashlib

from cc_ai_benchmark.bank import Item

TEMPLATE_VERSION = "1.0.0"

SYSTEM = (
    "You are answering multiple-choice questions from a Property & Casualty "
    "insurance licensing examination.\n"
    "Answer with a single JSON object and nothing else:\n"
    '{"answer": "<A|B|C|D>", "confidence": <0.0-1.0>}\n'
    'If you do not know, return {"answer": null, "confidence": 0.0} rather than '
    "guessing. A confident wrong answer is worse than declining."
)

_QUESTION = "Question:\n{question}\n\nOptions:\n{options}\n"

_CONTEXT = (
    "Reference material:\n<material>\n{context}\n</material>\n\n"
    "Answer using the reference material above. If it does not settle the "
    "question, say so by declining rather than guessing.\n\n"
)


def render_options(item: Item) -> str:
    return "\n".join(f"{letter}. {item.choices[letter]}" for letter in item.letters)


def render(item: Item, condition: str, context: str | None = None) -> tuple[str, str]:
    """Return (system, user) for one item under one condition."""
    body = _QUESTION.format(question=item.question.strip(), options=render_options(item))
    if condition == "C0" or not context:
        return SYSTEM, body
    return SYSTEM, _CONTEXT.format(context=context) + body


def template_hash() -> str:
    payload = "\x00".join([TEMPLATE_VERSION, SYSTEM, _QUESTION, _CONTEXT])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
