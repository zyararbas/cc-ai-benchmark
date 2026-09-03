import json

from cc_ai_benchmark.models import Task, TaskSuite
from cc_ai_benchmark.runner import run_suite, run_task
from cc_ai_benchmark.runners import get_runner
from cc_ai_benchmark.scoring import get_scorer
from cc_ai_benchmark.storage import write_report

SUITE = TaskSuite(
    name="unit",
    version="1.0.0",
    tasks=[
        Task(id="a", prompt="What is 2 + 2?", expected="4"),
        Task(id="b", prompt="Capital of France?", expected="Paris"),
    ],
)


def test_oracle_scores_perfectly():
    report = run_suite(SUITE, get_runner("oracle"), get_scorer("exact_match"), "oracle")
    assert report.mean_score == 1.0
    assert [result.task_id for result in report.results] == ["a", "b"]


def test_echo_scores_zero_on_this_suite():
    report = run_suite(SUITE, get_runner("echo"), get_scorer("exact_match"), "echo")
    assert report.mean_score == 0.0


def test_exact_match_ignores_case_and_whitespace():
    scorer = get_scorer("exact_match")
    assert scorer(Task(id="a", prompt="p", expected="Paris"), "  paris ") == 1.0


def test_failing_runner_is_recorded_not_raised():
    def boom(task):
        raise RuntimeError("upstream timeout")

    result = run_task(SUITE.tasks[0], boom, get_scorer("exact_match"))
    assert result.score == 0.0
    assert "upstream timeout" in result.error


def test_write_report_emits_readable_json(tmp_path):
    report = run_suite(SUITE, get_runner("oracle"), get_scorer("exact_match"), "oracle")
    path = write_report(report, tmp_path)
    payload = json.loads(path.read_text())
    assert payload["summary"] == {"task_count": 2, "mean_score": 1.0, "error_count": 0}
    assert payload["suite_version"] == "1.0.0"
