# Contributing

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a pull request

```bash
ruff check . && ruff format --check . && pytest
```

## Branching

Work on a branch (`feat/…`, `fix/…`, `chore/…`, `docs/…`) and open a pull
request. Nothing lands on `main` by direct push, and a pull request is merged
only after an approving review from someone other than its author.

Commit messages explain **why**; the diff already says what. No emoji.

## Changing task suites

Published results are only comparable when the tasks behind them are stable:

- Never repurpose an existing task `id` — add a new task instead.
- Bump the suite `version` whenever the task set changes.
- Run `cc-ai-benchmark validate` before committing.
- This repository is public. Suites must contain no customer data, credentials,
  or internal identifiers.

## Scope of a contribution

New runners and scorers are self-contained: register them in
`src/cc_ai_benchmark/runners.py` or `scoring.py`, add a test, and document the
name in the README table if it is meant for general use. Runners that call an
external service should read credentials from the environment and must never
commit them.
