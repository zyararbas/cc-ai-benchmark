"""Writing a sweep to disk, and printing the numbers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cc_ai_benchmark import __version__
from cc_ai_benchmark.execute import SystemRun
from cc_ai_benchmark.metrics import by_scope, compute
from cc_ai_benchmark.models import describe_environment, utcnow_iso
from cc_ai_benchmark.storage import OUTPUT_DIR


def build_report(runs: list[SystemRun], bank_size: int, notes: dict[str, Any]) -> dict[str, Any]:
    systems = []
    for run in runs:
        metrics = compute(run.results)
        systems.append(
            {
                "system": run.system,
                "condition": run.condition,
                "adapter": run.adapter_describe,
                "template_hash": run.template_hash,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "stopped_early": run.stopped_early,
                "metrics": metrics.to_dict(),
                "by_scope": by_scope(run.results),
                "results": [r.to_dict() for r in run.results],
            }
        )
    return {
        "kind": "sweep",
        "generated_at": utcnow_iso(),
        "harness_version": __version__,
        "bank_size": bank_size,
        "environment": describe_environment(),
        "notes": notes,
        "systems": systems,
    }


def write(report: dict[str, Any], output_dir: Path = OUTPUT_DIR, name: str = "sweep") -> Path:
    stamp = report["generated_at"].replace(":", "").replace("-", "")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stamp}-{name}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _fmt_money(value: float | None) -> str:
    return "     -" if value is None else f"${value:>8.4f}"


def print_table(report: dict[str, Any]) -> None:
    rows = report["systems"]
    width = max((len(r["system"]) for r in rows), default=10)
    header = (
        f"{'system'.ljust(width)}  cond    n   acc    95% CI        "
        f"cov    risk   absn  parse  err     cost    $/correct   p50ms"
    )
    print(header)
    print("-" * len(header))
    for row in sorted(rows, key=lambda r: -r["metrics"]["accuracy"]):
        m = row["metrics"]
        lo, hi = m["accuracy_ci95"]
        print(
            f"{row['system'].ljust(width)}  {row['condition']:<4} "
            f"{m['n']:>4} {m['accuracy']:>6.3f} "
            f"[{lo:.3f},{hi:.3f}] "
            f"{m['coverage_accuracy']:>6.3f} {m['risk_weighted']:>6.3f} "
            f"{m['abstention_rate']:>5.2f} {m['parse_failures']:>5} {m['errors']:>4} "
            f"{_fmt_money(m['cost_usd'])} {_fmt_money(m['cost_per_correct'])} "
            f"{m['latency_p50_ms']:>7.0f}"
        )
    print()
    print("acc = correct/all   cov = correct/answered   risk = (correct-incorrect)/all")
    print("A high abstention rate with a high risk score is the safe profile for insurance.")
