"""Turning a system's raw text into a graded outcome.

The outcome is an enum, not a float. A parse failure is recorded as a parse
failure rather than silently scored zero -- otherwise the benchmark ends up
measuring its own regex.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from cc_ai_benchmark.bank import Item


class Outcome(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    ABSTAINED = "abstained"
    PARSE_FAILURE = "parse_failure"
    ERROR = "error"


@dataclass(frozen=True)
class Grade:
    outcome: Outcome
    parsed: str | None
    confidence: float | None


_JSON_BLOCK = re.compile(r"\{.*?\}", re.DOTALL)
_ABSTAIN = re.compile(
    r"\b(i (do not|don't) know|cannot determine|can't determine|unable to determine|"
    r"insufficient information|not enough information|abstain)\b",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    return " ".join(str(text).split()).casefold().strip(" .")


def _letters(item: Item) -> set[str]:
    return set(item.letters)


def _from_json(text: str, item: Item) -> Grade | None:
    for match in _JSON_BLOCK.finditer(text):
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or "answer" not in payload:
            continue
        raw = payload.get("answer")
        confidence = payload.get("confidence")
        confidence = float(confidence) if isinstance(confidence, int | float) else None
        if raw is None:
            return Grade(Outcome.ABSTAINED, None, confidence)
        candidate = str(raw).strip().upper()
        if candidate in _letters(item):
            return Grade(_verdict(candidate, item), candidate, confidence)
        matched = _match_choice_text(str(raw), item)
        if matched:
            return Grade(_verdict(matched, item), matched, confidence)
    return None


def _match_choice_text(text: str, item: Item) -> str | None:
    target = _norm(text)
    if not target:
        return None
    hits = [letter for letter, value in item.choices.items() if _norm(value) == target]
    return hits[0] if len(hits) == 1 else None


_LETTER_PATTERNS = [
    re.compile(r"\banswer\s*(?:is|:|=)\s*\(?([A-D])\)?", re.IGNORECASE),
    re.compile(r"^\s*\(?([A-D])\)?\s*[\.\):-]", re.IGNORECASE),
    re.compile(r"^\s*\(?([A-D])\)?\s*$", re.IGNORECASE),
]


def _from_text(text: str, item: Item) -> Grade | None:
    valid = _letters(item)
    for pattern in _LETTER_PATTERNS:
        found = {m.group(1).upper() for m in pattern.finditer(text)} & valid
        if len(found) == 1:
            letter = found.pop()
            return Grade(_verdict(letter, item), letter, None)
        if len(found) > 1:
            return Grade(Outcome.PARSE_FAILURE, None, None)
    matched = _match_choice_text(text, item)
    if matched:
        return Grade(_verdict(matched, item), matched, None)
    return None


def _verdict(letter: str, item: Item) -> Outcome:
    return Outcome.CORRECT if letter == item.answer else Outcome.INCORRECT


def grade(item: Item, text: str, error: str | None = None) -> Grade:
    """Grade one response. Order matters: JSON contract first, then a text ladder."""
    if error:
        return Grade(Outcome.ERROR, None, None)
    if not text or not text.strip():
        return Grade(Outcome.PARSE_FAILURE, None, None)

    from_json = _from_json(text, item)
    if from_json is not None:
        return from_json
    from_text = _from_text(text, item)
    if from_text is not None:
        return from_text
    if _ABSTAIN.search(text):
        return Grade(Outcome.ABSTAINED, None, None)
    return Grade(Outcome.PARSE_FAILURE, None, None)
