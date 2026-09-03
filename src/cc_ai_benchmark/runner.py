"""Executing a suite against a runner."""

from __future__ import annotations

import time

from cc_ai_benchmark.models import (
    RunReport,
    TaskResult,
    TaskSuite,
    describe_environment,
    utcnow_iso,
)
from cc_ai_benchmark.runners import Runner
from cc_ai_benchmark.scoring import Scorer


def run_task(task, runner: Runner, scorer: Scorer) -> TaskResult:
    """Run one task. A runner that raises is recorded as a zero, never fatal."""
    started = time.perf_counter()
    try:
        output = runner(task)
        error = None
    except Exception as exc:  # a broken runner must not abort the whole suite
        output = ""
        error = f"{type(exc).__name__}: {exc}"
    duration_ms = (time.perf_counter() - started) * 1000

    score = 0.0 if error else scorer(task, output)
    return TaskResult(
        task_id=task.id,
        output=output,
        score=score,
        duration_ms=round(duration_ms, 3),
        error=error,
    )


def run_suite(
    suite: TaskSuite,
    runner: Runner,
    scorer: Scorer,
    runner_name: str,
) -> RunReport:
    """Run every task in `suite` and collect the results into a report."""
    started_at = utcnow_iso()
    results = [run_task(task, runner, scorer) for task in suite.tasks]
    return RunReport(
        suite=suite.name,
        suite_version=suite.version,
        runner=runner_name,
        started_at=started_at,
        finished_at=utcnow_iso(),
        results=results,
        environment=describe_environment(),
    )
