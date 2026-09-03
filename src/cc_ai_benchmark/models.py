"""Core record types.

Every record round-trips through plain JSON so that suites and results stay
readable, diffable, and usable by tools outside this repo.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utcnow_iso() -> str:
    """Timestamp as ISO 8601 with an explicit UTC offset."""
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Task:
    """One benchmark item: an input, and what a correct answer looks like."""

    id: str
    prompt: str
    expected: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Task:
        missing = [key for key in ("id", "prompt") if key not in raw]
        if missing:
            raise ValueError(f"task is missing required key(s): {', '.join(missing)}")
        unknown = set(raw) - {"id", "prompt", "expected", "tags", "metadata"}
        if unknown:
            raise ValueError(f"task {raw['id']!r} has unknown key(s): {', '.join(sorted(unknown))}")
        return cls(
            id=str(raw["id"]),
            prompt=str(raw["prompt"]),
            expected=raw.get("expected"),
            tags=list(raw.get("tags", [])),
            metadata=dict(raw.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskSuite:
    """A named, versioned collection of tasks loaded from a single JSON file."""

    name: str
    version: str
    tasks: list[Task]
    description: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TaskSuite:
        missing = [key for key in ("name", "version", "tasks") if key not in raw]
        if missing:
            raise ValueError(f"suite is missing required key(s): {', '.join(missing)}")
        tasks = [Task.from_dict(item) for item in raw["tasks"]]
        seen: set[str] = set()
        for task in tasks:
            if task.id in seen:
                raise ValueError(f"duplicate task id in suite {raw['name']!r}: {task.id!r}")
            seen.add(task.id)
        return cls(
            name=str(raw["name"]),
            version=str(raw["version"]),
            tasks=tasks,
            description=str(raw.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tasks": [task.to_dict() for task in self.tasks],
        }


@dataclass(frozen=True)
class TaskResult:
    """What one runner produced for one task, and how it scored."""

    task_id: str
    output: str
    score: float
    duration_ms: float
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunReport:
    """The complete, self-describing record of one benchmark run."""

    suite: str
    suite_version: str
    runner: str
    started_at: str
    finished_at: str
    results: list[TaskResult]
    environment: dict[str, Any] = field(default_factory=dict)

    @property
    def mean_score(self) -> float:
        if not self.results:
            return 0.0
        return sum(result.score for result in self.results) / len(self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "suite_version": self.suite_version,
            "runner": self.runner,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": {
                "task_count": len(self.results),
                "mean_score": round(self.mean_score, 4),
                "error_count": sum(1 for result in self.results if result.error),
            },
            "environment": self.environment,
            "results": [result.to_dict() for result in self.results],
        }


def describe_environment() -> dict[str, Any]:
    """Environment facts a reader needs to judge whether a run is comparable."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "harness_version": "0.1.0",
    }
