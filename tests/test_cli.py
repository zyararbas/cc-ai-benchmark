from cc_ai_benchmark.cli import main
from cc_ai_benchmark.storage import discover_suites, load_suite


def test_bundled_suites_all_parse():
    suites = discover_suites()
    assert suites, "expected at least one suite in data/tasks"
    for path in suites:
        load_suite(path)


def test_validate_command_passes(capsys):
    assert main(["validate"]) == 0


def test_run_command_writes_report(tmp_path, capsys):
    code = main(["run", "example", "--runner", "oracle", "--output-dir", str(tmp_path)])
    assert code == 0
    assert "score   1.000" in capsys.readouterr().out
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_unknown_runner_is_a_clean_error(capsys):
    assert main(["run", "example", "--runner", "nope", "--no-write"]) == 1
    assert "unknown runner" in capsys.readouterr().err
