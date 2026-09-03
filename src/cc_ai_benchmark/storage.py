"""Reading suites off disk and writing run reports into `outputs/`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from cc_ai_benchmark.models import RunReport, TaskSuite

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "tasks"
OUTPUT_DIR = REPO_ROOT / "outputs"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-") or "unnamed"


def load_suite(path: Path) -> TaskSuite:
    """Load and validate one suite JSON file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a JSON object at the top level")
    try:
        return TaskSuite.from_dict(raw)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def discover_suites(directory: Path = DATA_DIR) -> list[Path]:
    """Every suite file in `directory`, in a stable order."""
    return sorted(directory.glob("*.json"))


def resolve_suite(reference: str, directory: Path = DATA_DIR) -> Path:
    """Accept either a path to a suite file or the bare name of one in `data/tasks`."""
    candidate = Path(reference)
    if candidate.suffix == ".json" and candidate.exists():
        return candidate
    named = directory / f"{reference}.json"
    if named.exists():
        return named
    known = ", ".join(path.stem for path in discover_suites(directory)) or "none"
    raise FileNotFoundError(f"no suite matching {reference!r} (available: {known})")


def write_report(report: RunReport, output_dir: Path = OUTPUT_DIR) -> Path:
    """Write a report to `outputs/<timestamp>-<suite>-<runner>.json` and return its path."""
    stamp = report.started_at.replace(":", "").replace("-", "")
    name = f"{stamp}-{_slug(report.suite)}-{_slug(report.runner)}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
