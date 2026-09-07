"""The question bank: loading it, and building it from the raw extraction.

The raw extraction in `data/documents/questions/` uses file-local ids (`q_1`
appears in every
file), so ids there do not identify an item. `build_bank` materializes a single
`data/bank/pc-bank.jsonl` with global, stable ids, the duplicate retirements
from `data/audit/duplicates.json` applied, and review clusters flagged. Runs
load that file, never the raw extraction.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "documents" / "questions"
BANK_PATH = REPO_ROOT / "data" / "bank" / "pc-bank.jsonl"
AUDIT_PATH = REPO_ROOT / "data" / "audit" / "duplicates.json"

_FILE_NO = re.compile(r"_(\d+)\.json$")

#: Questions that were never tied to one source document. They came out of the
#: extraction as `questions_N.json` rather than `scoped_questions_N.json` and
#: carry no `scope` and no `ref`, so they are given one scope of their own.
#: They are answerable from the corpus -- their median term-overlap against it
#: is 0.884, against 0.864 for the scoped items -- but there is no single
#: document to call theirs, so C1 cannot run on them and they carry `no-source`.
GENERAL_SCOPE = "Property & Casualty Insurance General Questions"


@dataclass(frozen=True)
class Item:
    """One bank question. `id` is global and stable; never reissue one."""

    id: str
    question: str
    choices: dict[str, str]
    answer: str
    scope: str
    ref: str
    explanation: str | None = None
    source: str = ""
    flags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Item:
        return cls(
            id=raw["id"],
            question=raw["question"],
            choices=dict(raw["choices"]),
            answer=raw["answer"],
            scope=raw.get("scope", ""),
            ref=raw.get("ref", ""),
            explanation=raw.get("explanation"),
            source=raw.get("source", ""),
            flags=list(raw.get("flags", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def letters(self) -> list[str]:
        return sorted(self.choices)


def read_records(path: Path) -> list[dict[str, Any]]:
    """Every object in a raw question file, in order, whatever its layout.

    These files are JSON Lines under a `.json` extension, which an editor set to
    format on save will happily pretty-print into a stream of multi-line
    objects. Reading a line at a time then dies on the first `{`. Order is the
    only thing carrying the sequence numbers, so this parses the whole text as a
    stream of concatenated values rather than rejecting the reformatted layout.
    """
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        record, index = decoder.raw_decode(text, index)
        records.append(record)
    return records


def build_bank(raw_dir: Path = RAW_DIR, audit_path: Path = AUDIT_PATH) -> list[Item]:
    """Materialize the bank from the raw extraction plus the duplicate manifest."""
    retire: set[str] = set()
    review: set[str] = set()
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        retire = set(audit.get("retire_uids", []))
        for cluster in audit.get("clusters", []):
            if cluster.get("verdict") in {"REVIEW", "CONFLICT"}:
                review.update(m["uid"] for m in cluster["members"])

    def _ordered(pattern: str) -> list[Path]:
        return sorted(
            raw_dir.glob(pattern),
            key=lambda p: int(_FILE_NO.search(p.name).group(1)),
        )

    # `questions_*.json` does not match `scoped_questions_*.json`: the glob is
    # anchored at the start of the name, so the two sets never overlap.
    scoped_paths = _ordered("scoped_questions_*.json")
    general_paths = _ordered("questions_*.json")
    if not scoped_paths:
        raise FileNotFoundError(f"no scoped_questions_*.json under {raw_dir}")

    def _read(path: Path, make_id, scope_of, ref_of) -> list[Item]:
        out: list[Item] = []
        seq = 0
        for raw in read_records(path):
            uid = f"{path.name}:{raw['id']}"
            # seq advances before any skip, so an id is a record position and
            # dropping an item never renames the ones after it.
            seq += 1
            if uid in retire:
                continue
            # A tombstone left by reconcile_extraction.py: the question is gone
            # from the source document, but its slot is held so the sequence
            # numbers of everything below it do not shift onto new questions.
            if raw.get("retired"):
                continue
            ref = ref_of(raw)
            # Two ways to earn the same flag: the duplicate audit put the item
            # in an unadjudicated cluster, or the extraction could not read its
            # marker and left `answer` null. Grading compares against that key,
            # so an unflagged null scores every model wrong without saying why.
            flags = ["needs-review"] if uid in review or raw.get("needs_review") else []
            # No source document means C1 cannot be run on this item. Say so on
            # the item rather than leaving a caller to infer it from an empty
            # ref and quietly grade an oracle run it never really had.
            if not ref:
                flags.append("no-source")
            out.append(
                Item(
                    id=make_id(seq),
                    question=raw["question"],
                    choices=dict(raw["choices"]),
                    answer=raw["answer"],
                    scope=scope_of(raw),
                    ref=ref,
                    explanation=raw.get("explanation"),
                    source=uid,
                    flags=flags,
                )
            )
        return out

    items: list[Item] = []
    for path in scoped_paths:
        file_no = int(_FILE_NO.search(path.name).group(1))
        items += _read(
            path,
            make_id=lambda seq, n=file_no: f"pc-{n:02d}-{seq:04d}",
            scope_of=lambda raw: raw.get("scope", ""),
            ref_of=lambda raw: raw.get("ref", ""),
        )
    for path in general_paths:
        file_no = int(_FILE_NO.search(path.name).group(1))
        # A separate id namespace: `pc-gen-` can never collide with `pc-NN-`,
        # so adding a general file never renumbers a scoped item.
        items += _read(
            path,
            make_id=lambda seq, n=file_no: f"pc-gen{n:02d}-{seq:04d}",
            scope_of=lambda raw: GENERAL_SCOPE,
            ref_of=lambda raw: raw.get("ref", ""),
        )
    return items


def write_bank(items: list[Item], path: Path = BANK_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_bank(path: Path = BANK_PATH) -> list[Item]:
    if not path.exists():
        raise FileNotFoundError(f"bank not built: {path} (run `cc-ai-benchmark build-bank`)")
    items = [
        Item.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            raise ValueError(f"duplicate item id in bank: {item.id}")
        seen.add(item.id)
    return items


def select(
    items: list[Item],
    scopes: list[str] | None = None,
    limit: int | None = None,
    sample: int | None = None,
    seed: int = 0,
    item_ids: list[str] | None = None,
    exclude_flagged: bool = True,
) -> list[Item]:
    """Deterministic subset selection. Order is always the bank's own order.

    `item_ids` names an exact set, which is how an error set from an earlier run
    gets re-measured: a set conditioned on failure is a diagnostic, never an
    accuracy number, because the selection already knows the answer.

    `limit` takes the first N, which is the right thing for a smoke test and the
    wrong thing for a partial measurement: the bank is ordered by source
    document, so the first N items all come from the first few scopes. `sample`
    draws N spread across scopes instead, seeded so the same N items come back
    on every run and two systems measured separately are still measured on the
    same questions.
    """
    chosen = items
    if exclude_flagged:
        chosen = [i for i in chosen if "needs-review" not in i.flags]
    if scopes:
        wanted = {s.casefold() for s in scopes}
        chosen = [i for i in chosen if i.scope.casefold() in wanted]
    if item_ids:
        wanted_ids = set(item_ids)
        chosen = [i for i in chosen if i.id in wanted_ids]
    if sample is not None:
        chosen = _stratified(chosen, sample, seed)
    if limit is not None:
        chosen = chosen[:limit]
    return chosen


def _stratified(items: list[Item], size: int, seed: int) -> list[Item]:
    """`size` items spread over scopes in proportion to each scope's share."""
    if size >= len(items):
        return items
    buckets: dict[str, list[Item]] = {}
    for item in items:
        buckets.setdefault(item.scope, []).append(item)
    picked: list[Item] = []
    for scope in sorted(buckets):
        pool = buckets[scope]
        take = round(size * len(pool) / len(items))
        rng = random.Random(f"{seed}:{scope}")
        picked.extend(rng.sample(pool, min(max(take, 1), len(pool))))
    # Proportional rounding rarely lands exactly on `size`; correct against the
    # remainder rather than re-drawing, so the seed keeps its meaning.
    if len(picked) > size:
        rng = random.Random(f"{seed}:trim")
        picked = rng.sample(picked, size)
    elif len(picked) < size:
        taken = {i.id for i in picked}
        rest = [i for i in items if i.id not in taken]
        rng = random.Random(f"{seed}:fill")
        picked.extend(rng.sample(rest, min(size - len(picked), len(rest))))
    order = {item.id: n for n, item in enumerate(items)}
    return sorted(picked, key=lambda i: order[i.id])
