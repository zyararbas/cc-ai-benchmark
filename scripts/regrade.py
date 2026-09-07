"""Re-score a stored sweep report with the current grader.

`docs/BENCHMARK_DESIGN.md` treats a parse failure as a harness defect until
proven otherwise. Acting on that means fixing the grader and re-scoring what
already ran -- a fix that only applies to future runs leaves every published
number carrying the defect it was meant to remove.

Only outcomes derived from complete stored response text change. A transport
error stays an error: there is no text to re-read, and inventing one would be a
fabrication rather than a re-grade. A response stored clipped is skipped for the
same reason -- a JSON object cut in half parses as a failure, and "re-grading" it
would manufacture the very defect this script exists to remove.

    python scripts/regrade.py outputs/benchmark-runs/2026_09_06/sweep.json

Writes `<name>.regraded.json` alongside the original and prints what moved. The
original is never modified: a published number and its correction are two
artifacts, not one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_ai_benchmark.bank import load_bank  # noqa: E402
from cc_ai_benchmark.execute import ItemResult  # noqa: E402
from cc_ai_benchmark.grading import grade  # noqa: E402
from cc_ai_benchmark.metrics import by_scope, compute  # noqa: E402


class _Row:
    """The subset of ItemResult that `compute` and `by_scope` actually read."""

    def __init__(self, data: dict):
        self.__dict__.update(data)


def _clipped(row: dict) -> bool:
    """Whether the stored response is a fragment rather than the whole answer.

    Reports written before `text_truncated` existed have to be judged by length,
    which is why the limit is read from the class that applied it rather than
    typed here a second time.
    """
    if "text_truncated" in row:
        return bool(row["text_truncated"])
    return len(row.get("text") or "") >= ItemResult.TEXT_LIMIT


def regrade(report: dict) -> tuple[dict, list[str], list[str]]:
    items = {item.id: item for item in load_bank()}
    moved: list[str] = []
    skipped: list[str] = []
    for system in report["systems"]:
        for row in system["results"]:
            item = items.get(row["item_id"])
            # An error has no text to re-read; leave it exactly as recorded.
            if item is None or row.get("error") or not row.get("text"):
                continue
            if _clipped(row):
                skipped.append(f"{system['system']}/{row['item_id']}")
                continue
            verdict = grade(item, row["text"], None)
            if str(verdict.outcome) == row["outcome"]:
                continue
            moved.append(
                f"{system['system']}/{row['item_id']}: {row['outcome']} -> {verdict.outcome}"
            )
            row["outcome"] = str(verdict.outcome)
            row["parsed_answer"] = verdict.parsed
        rows = [_Row(r) for r in system["results"]]
        system["metrics"] = compute(rows).to_dict()
        system["by_scope"] = by_scope(rows)
    report.setdefault("notes", {})["regraded"] = {
        "changed": len(moved),
        "detail": moved,
        "skipped_truncated": len(skipped),
    }
    return report, moved, skipped


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 1
    source = Path(argv[0])
    report = json.loads(source.read_text(encoding="utf-8"))
    before = {s["system"]: s["metrics"]["accuracy"] for s in report["systems"]}
    report, moved, skipped = regrade(report)

    for line in moved:
        print(f"  {line}")
    print(f"\n{len(moved)} outcome(s) changed")
    if skipped:
        print(
            f"{len(skipped)} response(s) stored clipped and left alone (re-run to re-grade those)"
        )
    print()
    width = max(len(name) for name in before)
    print(f"{'system'.ljust(width)}   before    after")
    for system in report["systems"]:
        name = system["system"]
        after = system["metrics"]["accuracy"]
        flag = "" if after == before[name] else "  <-"
        print(f"{name.ljust(width)}   {before[name]:.4f}   {after:.4f}{flag}")

    target = source.with_suffix(".regraded.json")
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote  {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
