"""The question bank: loading it, and building it from the raw extraction.

The raw extraction in `outputs/` uses file-local ids (`q_1` appears in every
file), so ids there do not identify an item. `build_bank` materializes a single
`data/bank/pc-bank.jsonl` with global, stable ids, the duplicate retirements
from `data/audit/duplicates.json` applied, and review clusters flagged. Runs
load that file, never the raw extraction.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "outputs"
BANK_PATH = REPO_ROOT / "data" / "bank" / "pc-bank.jsonl"
AUDIT_PATH = REPO_ROOT / "data" / "audit" / "duplicates.json"

_FILE_NO = re.compile(r"_(\d+)\.json$")


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

    paths = sorted(
        raw_dir.glob("scoped_questions_*.json"),
        key=lambda p: int(_FILE_NO.search(p.name).group(1)),
    )
    if not paths:
        raise FileNotFoundError(f"no scoped_questions_*.json under {raw_dir}")

    items: list[Item] = []
    for path in paths:
        file_no = int(_FILE_NO.search(path.name).group(1))
        seq = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            uid = f"{path.name}:{raw['id']}"
            seq += 1
            if uid in retire:
                continue
            items.append(
                Item(
                    id=f"pc-{file_no:02d}-{seq:04d}",
                    question=raw["question"],
                    choices=dict(raw["choices"]),
                    answer=raw["answer"],
                    scope=raw.get("scope", ""),
                    ref=raw.get("ref", ""),
                    explanation=raw.get("explanation"),
                    source=uid,
                    flags=["needs-review"] if uid in review else [],
                )
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
    exclude_flagged: bool = True,
) -> list[Item]:
    """Deterministic subset selection. Order is always the bank's own order."""
    chosen = items
    if exclude_flagged:
        chosen = [i for i in chosen if "needs-review" not in i.flags]
    if scopes:
        wanted = {s.casefold() for s in scopes}
        chosen = [i for i in chosen if i.scope.casefold() in wanted]
    if limit is not None:
        chosen = chosen[:limit]
    return chosen
