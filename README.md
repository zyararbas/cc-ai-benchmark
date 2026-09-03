# cc-ai-benchmark

A small, reproducible benchmark harness for evaluating AI systems against
versioned task suites. Suites are plain JSON, runs are plain JSON, and the
scoring logic is short enough to read in one sitting — the point is that anyone
can check a published number rather than take it on faith.

## Install

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Use

```bash
cc-ai-benchmark list                        # suites, runners, scorers
cc-ai-benchmark validate                    # check every suite file parses
cc-ai-benchmark run example --runner oracle # run a suite, write a report
```

`python -m cc_ai_benchmark ...` works identically if you would rather not
install the console script.

Reports are written to `outputs/<timestamp>-<suite>-<runner>.json`:

```json
{
  "suite": "example",
  "suite_version": "1.0.0",
  "runner": "oracle",
  "summary": { "task_count": 3, "mean_score": 1.0, "error_count": 0 },
  "environment": { "python": "3.13.0", "platform": "...", "harness_version": "0.1.0" },
  "results": [{ "task_id": "arith-001", "output": "4", "score": 1.0, "duration_ms": 0.002 }]
}
```

## Layout

| Path | What lives here |
|---|---|
| `src/cc_ai_benchmark/` | The harness: models, storage, runners, scorers, CLI |
| `data/tasks/*.json` | Task suites — one file per suite, versioned ([schema](data/README.md)) |
| `outputs/` | Run reports (gitignored; generated artifacts) |
| `tests/` | pytest suite covering loading, scoring, reporting, and the CLI |

## Adding a runner

A runner is a callable from `Task` to a string. Register it and it becomes
available as `--runner <name>`:

```python
from cc_ai_benchmark.models import Task
from cc_ai_benchmark.runners import register


@register("my-model")
def my_model(task: Task) -> str:
    return call_my_system(task.prompt)
```

Two baselines ship in [runners.py](src/cc_ai_benchmark/runners.py): `echo`
returns the prompt (the floor) and `oracle` returns the expected answer (the
ceiling, and a check that scoring is wired up). A runner that raises is recorded
as a scored-zero result with the error text — one broken task never aborts a run.

Scorers work the same way via `cc_ai_benchmark.scoring.register`; `exact_match`
and `contains` ship by default.

## Adding tasks

See [data/README.md](data/README.md) for the suite schema and the two rules that
keep published results comparable: task ids are stable, and the suite `version`
is bumped whenever the task set changes.

Because this repository is public, suites must contain nothing that cannot be
published — no customer data, no credentials, no internal identifiers.

## Development

```bash
pytest              # tests
ruff check .        # lint
ruff format .       # format
```

CI runs all three on every push and pull request.

## License

MIT — see [LICENSE](LICENSE).
