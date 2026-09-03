#!/usr/bin/env python3
"""Duplicate audit for the scoped question bank.

Clusters items by normalized stem (exact, then fuzzy) and classifies each cluster
so that Phase 0 dedup is a review of a manifest rather than a judgement call per
item. Writes data/audit/duplicates.json and exits non-zero if any cluster needs
human adjudication.

Only mechanical duplicates are retired automatically. Anything whose resolution
depends on reading the insurance content is routed to a human: a synonym gap
("the customer" vs "the bailor (customer)") is invisible to string similarity,
so an identical stem over different choices is never auto-resolved.

Classes:
  IDENTICAL   same stem, same choices, same key    -> retire one, automatic
  SHUFFLED    same stem, same choices, key moved   -> retire one, automatic
  CONFLICT    same stem, same choices, keys differ -> ADJUDICATE (ground-truth bug)
  REVIEW      same question, different choices     -> human call: duplicate or two valid items
  DISTINCT    fuzzy stem match, different answers  -> keep both, no action
"""

from __future__ import annotations

import collections
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BANK_GLOB = "scoped_questions_*.json"
STEM_THRESHOLD = 0.93
ANSWER_THRESHOLD = 0.75

_PUNCT_TAIL = re.compile(r"[\.\?:;,!\-\s]+$")
_SUBS = [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-"), ("…", "...")]


def norm(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    for old, new in _SUBS:
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return _PUNCT_TAIL.sub("", text)


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def load(directory: Path) -> list[dict]:
    items = []
    paths = sorted(
        directory.glob(BANK_GLOB), key=lambda p: int(re.search(r"_(\d+)\.json$", p.name).group(1))
    )
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            choices = raw.get("choices") or {}
            answer = raw.get("answer")
            items.append(
                {
                    "file": path.name,
                    "id": raw.get("id"),
                    "uid": f"{path.name}:{raw.get('id')}",
                    "scope": raw.get("scope"),
                    "question": raw.get("question"),
                    "stem": norm(raw.get("question")),
                    "choices": choices,
                    "choiceset": tuple(sorted(norm(v) for v in choices.values())),
                    "answer": answer,
                    "answer_text": norm(choices.get(answer)) if isinstance(answer, str) else None,
                    "has_explanation": bool(raw.get("explanation")),
                }
            )
    return items


def cluster(items: list[dict]) -> list[list[dict]]:
    parent = {item["uid"]: item["uid"] for item in items}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            longest = max(len(a["stem"]), len(b["stem"])) or 1
            if abs(len(a["stem"]) - len(b["stem"])) > 0.15 * longest:
                continue
            if similar(a["stem"], b["stem"]) >= STEM_THRESHOLD:
                ra, rb = find(a["uid"]), find(b["uid"])
                if ra != rb:
                    parent[rb] = ra

    groups = collections.defaultdict(list)
    for item in items:
        groups[find(item["uid"])].append(item)
    return [g for g in groups.values() if len(g) > 1]


def classify(group: list[dict]) -> str:
    if any(not g["answer_text"] for g in group):
        return "CONFLICT"  # missing key needs a human either way

    same_choices = len({g["choiceset"] for g in group}) == 1
    same_stem = len({g["stem"] for g in group}) == 1
    answers = [g["answer_text"] for g in group]
    same_answer = all(similar(answers[0], other) >= ANSWER_THRESHOLD for other in answers[1:])

    if same_choices:
        # The choice pool is identical, so the key is directly comparable.
        if not same_answer:
            return "CONFLICT"
        return "IDENTICAL" if len({g["answer"] for g in group}) == 1 else "SHUFFLED"

    # Different choice pools. Two items can share a stem and both be correct
    # (an "EXCEPT" stem with different distractors), and two items can state the
    # same answer in different words. Neither is decidable by string distance.
    if same_stem or same_answer:
        return "REVIEW"
    return "DISTINCT"


RETIRE = {"IDENTICAL", "SHUFFLED"}  # safe to resolve mechanically
ADJUDICATE = {"CONFLICT", "REVIEW"}  # needs a P&C-literate reviewer


def keeper(group: list[dict]) -> dict:
    """Prefer the item carrying an explanation, then the lower ordinal."""
    return sorted(
        group, key=lambda g: (not g["has_explanation"], int(re.sub(r"\D", "", g["id"]) or 0))
    )[0]


def main(argv: list[str]) -> int:
    directory = Path(argv[1]) if len(argv) > 1 else REPO_ROOT / "outputs"
    items = load(directory)
    groups = sorted(cluster(items), key=lambda g: (g[0]["file"], g[0]["id"]))

    manifest, tally = [], collections.Counter()
    for group in groups:
        verdict = classify(group)
        tally[verdict] += 1
        keep = keeper(group) if verdict in RETIRE else None
        manifest.append(
            {
                "verdict": verdict,
                "scope": group[0]["scope"],
                "question": group[0]["question"],
                "keep": keep["uid"] if keep else None,
                "retire": [g["uid"] for g in group if keep and g["uid"] != keep["uid"]],
                "members": [
                    {
                        "uid": g["uid"],
                        "answer": g["answer"],
                        "answer_text": g["choices"].get(g["answer"]),
                        "has_explanation": g["has_explanation"],
                    }
                    for g in group
                ],
            }
        )

    retire = sorted({uid for entry in manifest for uid in entry["retire"]})
    needs_review = [e for e in manifest if e["verdict"] in ADJUDICATE]

    out = {
        "source_dir": str(directory),
        "item_count": len(items),
        "cluster_count": len(groups),
        "stem_threshold": STEM_THRESHOLD,
        "answer_threshold": ANSWER_THRESHOLD,
        "tally": dict(sorted(tally.items())),
        "retire_uids": retire,
        "item_count_after_dedup": len(items) - len(retire),
        "needs_adjudication": len(needs_review),
        "clusters": manifest,
    }
    target = REPO_ROOT / "data" / "audit" / "duplicates.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"items          {len(items)}")
    print(f"clusters       {len(groups)}")
    for verdict, count in sorted(tally.items()):
        print(f"  {verdict:12} {count}")
    print(f"retire         {len(retire)}  -> {len(items) - len(retire)} items after dedup")
    print(f"adjudicate     {len(needs_review)}")
    print(f"manifest       {target.relative_to(REPO_ROOT)}")
    return 1 if needs_review else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
