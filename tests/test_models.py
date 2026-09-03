import pytest

from cc_ai_benchmark.models import Task, TaskSuite


def test_task_requires_id_and_prompt():
    with pytest.raises(ValueError, match="missing required key"):
        Task.from_dict({"prompt": "hi"})


def test_task_rejects_unknown_keys():
    with pytest.raises(ValueError, match="unknown key"):
        Task.from_dict({"id": "a", "prompt": "hi", "expcted": "typo"})


def test_suite_rejects_duplicate_task_ids():
    raw = {
        "name": "dupes",
        "version": "1.0.0",
        "tasks": [
            {"id": "a", "prompt": "one"},
            {"id": "a", "prompt": "two"},
        ],
    }
    with pytest.raises(ValueError, match="duplicate task id"):
        TaskSuite.from_dict(raw)


def test_suite_round_trips():
    raw = {
        "name": "s",
        "version": "1.0.0",
        "description": "d",
        "tasks": [{"id": "a", "prompt": "p", "expected": "e", "tags": ["t"], "metadata": {}}],
    }
    assert TaskSuite.from_dict(raw).to_dict() == raw
