"""Reading suites off disk and writing run reports into `outputs/benchmark-runs/`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from cc_ai_benchmark.models import RunReport, TaskSuite

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "tasks"
OUTPUT_DIR = REPO_ROOT / "outputs" / "benchmark-runs"

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


def run_dir(output_dir: Path, timestamp: str) -> Path:
    """`<output_dir>/YYYY_MM_DD/` -- the day carries the date so names need not."""
    day = timestamp[:10].replace("-", "_")
    directory = output_dir / day
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """`stem.suffix`, or `stem-2.suffix` when that day already holds one.

    Short names are only worth having if a second run of the same name does not
    silently overwrite the first.
    """
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def write_report(report: RunReport, output_dir: Path = OUTPUT_DIR) -> Path:
    """Write to `outputs/benchmark-runs/<YYYY_MM_DD>/<suite>-<runner>.json`."""
    directory = run_dir(output_dir, report.started_at)
    path = unique_path(directory, f"{_slug(report.suite)}-{_slug(report.runner)}", ".json")
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
