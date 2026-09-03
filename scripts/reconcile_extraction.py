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

    python scripts/reconcile_extraction.py 1 --new work/1/extracted.jsonl
    python scripts/reconcile_extraction.py 1 --new work/1/extracted.jsonl --apply
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "outputs"

WHITESPACE = re.compile(r"\s+")
PUNCT = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    """Match on meaning-preserving differences only: case, spacing, punctuation."""
    return WHITESPACE.sub(" ", PUNCT.sub(" ", (text or "").casefold())).strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    path.write_text(body + "\n", encoding="utf-8")


def body_of(record: dict[str, Any]) -> tuple[Any, Any]:
    """The parts whose change makes it a different question."""
    return (record.get("choices"), record.get("answer"))


def reconcile(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> dict[str, Any]:
    new_by_stem: dict[str, dict[str, Any]] = {}
    for position, record in enumerate(new):
        new_by_stem.setdefault(normalize(record["question"]), {"record": record, "pos": position})

    merged: list[dict[str, Any]] = []
    classes: list[tuple[str, str, str]] = []  # (class, id, stem excerpt)
    matched: set[str] = set()

    for position, record in enumerate(old):
        stem = normalize(record["question"])
        excerpt = (record["question"] or "")[:70]
        if record.get("retired"):
            merged.append(record)
            classes.append(("TOMBSTONE", record["id"], excerpt))
            continue
        found = new_by_stem.get(stem)
        if found is None:
            merged.append(
                {**record, "retired": True, "retired_reason": "absent from source document"}
            )
            classes.append(("REMOVED", record["id"], excerpt))
            continue
        matched.add(stem)
        incoming = found["record"]
        if body_of(incoming) != body_of(record):
            # A corrected key makes this a different item than the one models
            # were scored against. Retire it and issue a new id below, so a
            # comparison across the change is impossible rather than silent.
            merged.append(
                {**record, "retired": True, "retired_reason": "choices or answer changed"}
            )
            classes.append(("EDITED", record["id"], excerpt))
            continue
        moved = found["pos"] != position
        merged.append(record)
        classes.append(("MOVED" if moved else "UNCHANGED", record["id"], excerpt))

    # Everything new, plus the replacement halves of EDITED pairs, appended in
    # source order so existing sequence numbers are untouched.
    next_seq = max(
        (int(r["id"].split("_")[-1]) for r in old if r["id"].startswith("q_")), default=0
    )
    edited_stems = {
        normalize(r["question"])
        for r, (cls, _, _) in zip(old, classes, strict=False)
        if cls == "EDITED"
    }
    for record in new:
        stem = normalize(record["question"])
        # Survivors keep their existing line. Only genuinely new stems, and the
        # replacement half of an EDITED pair, get appended with a fresh id.
        if stem in matched and stem not in edited_stems:
            continue
        next_seq += 1
        fresh = {**record, "id": f"q_{next_seq}"}
        merged.append(fresh)
        classes.append(("ADDED", fresh["id"], (record["question"] or "")[:70]))

    counts: dict[str, int] = {}
    for cls, _, _ in classes:
        counts[cls] = counts.get(cls, 0) + 1
    return {"merged": merged, "classes": classes, "counts": counts}


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

    old, new = read_jsonl(target), read_jsonl(args.new)
    result = reconcile(old, new)

    print(f"existing  {target.name}  {len(old)} records")
    print(f"incoming  {args.new.name}  {len(new)} records")
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
