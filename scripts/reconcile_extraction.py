"""Fold a fresh extraction into an existing scoped_questions file, keeping ids.

Bank ids are `pc-<file>-<seq>` where `seq` is the line number of the record, so
a straight overwrite of an edited document renames questions: delete item three
and the old item four inherits its name. Every report ever written references
those names, and nothing errors when they shift -- the numbers simply stop
meaning what they said.

So the new extraction is matched to the old one on the normalized stem, and the
old file's line order is authoritative. Survivors stay where they are, new
questions are appended, and removed ones are left as tombstones holding their
slot.

    python scripts/reconcile_extraction.py 1 --new data/documents/work/1/extracted.jsonl
    python scripts/reconcile_extraction.py 1 --new data/documents/work/1/extracted.jsonl --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from cc_ai_benchmark.bank import read_records

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "documents" / "questions"

WHITESPACE = re.compile(r"\s+")
PUNCT = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    """Match on meaning-preserving differences only: case, spacing, punctuation."""
    return WHITESPACE.sub(" ", PUNCT.sub(" ", (text or "").casefold())).strip()


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    path.write_text(body + "\n", encoding="utf-8")


def body_of(record: dict[str, Any]) -> tuple[Any, Any]:
    """The parts whose change makes it a different question."""
    return (record.get("choices"), record.get("answer"))


def reconcile(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    # Candidates grouped by stem, in source order. A stem legitimately appears
    # more than once: these decks re-ask the same question later over a
    # reordered option set, and the duplicate audit has ruled such pairs
    # VARIANTS -- two items, not one. Keying a single candidate per stem
    # dropped every occurrence after the first on the floor, unclassified and
    # unreported, which loses questions the source document actually contains.
    incoming_by_stem: dict[str, list[dict[str, Any]]] = {}
    for position, record in enumerate(new):
        incoming_by_stem.setdefault(normalize(record["question"]), []).append(
            {"record": record, "pos": position, "claimed": False}
        )

    def claim(stem: str, record: dict[str, Any]) -> dict[str, Any] | None:
        """The unclaimed candidate this old record pairs with.

        An identical body wins over a merely equal stem, so that when a stem
        has several occurrences each survivor pairs with its own twin instead
        of being scored against a variant and retired as EDITED.
        """
        pool = [c for c in incoming_by_stem.get(stem, ()) if not c["claimed"]]
        if not pool:
            return None
        for candidate in pool:
            if body_of(candidate["record"]) == body_of(record):
                return candidate
        return pool[0]

    merged: list[dict[str, Any]] = []
    classes: list[tuple[str, str, str]] = []  # (class, id, stem excerpt)

    for position, record in enumerate(old):
        stem = normalize(record["question"])
        excerpt = (record["question"] or "")[:70]
        if record.get("retired"):
            merged.append(record)
            classes.append(("TOMBSTONE", record["id"], excerpt))
            continue
        found = claim(stem, record)
        if found is None:
            merged.append(
                {**record, "retired": True, "retired_reason": "absent from source document"}
            )
            classes.append(("REMOVED", record["id"], excerpt))
            continue
        incoming = found["record"]
        if body_of(incoming) != body_of(record):
            # A corrected key makes this a different item than the one models
            # were scored against. Retire it and issue a new id below, so a
            # comparison across the change is impossible rather than silent.
            # The candidate stays unclaimed so it is appended as the
            # replacement half of the pair.
            merged.append(
                {**record, "retired": True, "retired_reason": "choices or answer changed"}
            )
            classes.append(("EDITED", record["id"], excerpt))
            continue
        found["claimed"] = True
        moved = found["pos"] != position
        merged.append(record)
        classes.append(("MOVED" if moved else "UNCHANGED", record["id"], excerpt))

    # Appended in source order so existing sequence numbers are untouched.
    next_seq = max(
        (int(r["id"].split("_")[-1]) for r in old if r["id"].startswith("q_")), default=0
    )
    # Survivors keep their existing line, so what is left unclaimed is exactly
    # the new material: genuinely new stems, further occurrences of a stem the
    # document already had, and the replacement halves of EDITED pairs.
    unclaimed = [
        candidate
        for candidates in incoming_by_stem.values()
        for candidate in candidates
        if not candidate["claimed"]
    ]
    for candidate in sorted(unclaimed, key=lambda c: c["pos"]):
        record = candidate["record"]
        next_seq += 1
        fresh = {**record, "id": f"q_{next_seq}"}
        merged.append(fresh)
        classes.append(("ADDED", fresh["id"], (record["question"] or "")[:70]))

    counts: dict[str, int] = {}
    for cls, _, _ in classes:
        counts[cls] = counts.get(cls, 0) + 1
    # Every incoming record either pairs with a survivor or is appended. The
    # caller checks this against the extraction it handed in, so a candidate
    # going missing is a loud failure rather than a shortfall in the bank.
    accounted = sum(
        1 for candidates in incoming_by_stem.values() for c in candidates if c["claimed"]
    ) + counts.get("ADDED", 0)
    return {"merged": merged, "classes": classes, "counts": counts, "accounted": accounted}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_no", type=int, help="the leading number of the document")
    parser.add_argument("--new", type=Path, required=True, help="fresh extraction, JSONL")
    parser.add_argument("--apply", action="store_true", help="write the merged file")
    args = parser.parse_args()

    target = RAW_DIR / f"scoped_questions_{args.file_no}.json"
    if not target.exists():
        print(f"{target} does not exist -- this is a NEW document.")
        print(f"Copy the extraction into place directly:\n  cp {args.new} {target}")
        return 0

    old, new = read_records(target), read_records(args.new)
    result = reconcile(old, new)

    print(f"existing  {target.name}  {len(old)} records")
    print(f"incoming  {args.new.name}  {len(new)} records")
    if result["accounted"] != len(new):
        print(
            f"\nABORT: {len(new) - result['accounted']} incoming record(s) were neither "
            "matched to an existing question nor added. Nothing written.",
            file=sys.stderr,
        )
        return 1
    print()
    for cls in ("UNCHANGED", "MOVED", "ADDED", "REMOVED", "EDITED", "TOMBSTONE"):
        if result["counts"].get(cls):
            print(f"  {cls:<10} {result['counts'][cls]}")
    print()
    for cls, ident, excerpt in result["classes"]:
        if cls in {"ADDED", "REMOVED", "EDITED", "MOVED"}:
            print(f"  {cls:<10} {ident:<8} {excerpt}")

    flagged = [r for r in result["merged"] if r.get("needs_review")]
    if flagged:
        print(f"\n{len(flagged)} item(s) need review:")
        for record in flagged:
            print(f"  {record['id']}: {record.get('review_note', 'no note')}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to write it.")
        return 0

    backup = target.with_suffix(".json.bak")
    shutil.copy2(target, backup)
    write_jsonl(target, result["merged"])
    print(f"\nwrote     {target}  ({len(result['merged'])} lines, backup at {backup.name})")
    print("next      cc-ai-benchmark build-bank && python scripts/audit_duplicates.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
