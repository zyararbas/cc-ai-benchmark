# Running the benchmark again

This is the steady-state document: what to type when the harness is already
installed and configured, and what to check first when it has been a while.

## The short version

```bash
cd ~/projects/cc-ai-benchmark
source .venv/bin/activate
source config/local.env          # GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION

cc-ai-benchmark bench gemini-pro gemini-flash gemini-flash-lite \
    --condition C0 --budget 2.00 --name sweep

REPORT=$(ls -t outputs/*-sweep.json | head -1)
cc-ai-benchmark chart  "$REPORT"     # standalone HTML, opens from file://
cc-ai-benchmark export "$REPORT"     # one CSV row per question per system
```

Roughly six minutes and about $0.52 for a full 669-item closed-book pass across
the three Gemini systems. The three run in parallel; each one's own concurrency
is bounded by its adapter.

`--budget` is a hard ceiling checked inside the worker, not at submit time. If a
price changes underneath you, the sweep stops rather than quietly spending.

## First time on a new machine

```bash
pip install -e ".[dev,providers]"
cp config/local.env.example config/local.env   # then fill in the project id
cc-ai-benchmark build-bank
```

`config/local.env` is gitignored. **This repository is public**, so
`config/models.json` carries `${GOOGLE_CLOUD_PROJECT}` rather than a literal
project id, and the environment supplies the value. The resolved project still
appears in every report, because which project answered is part of what a
result means — it just is not committed.

## Before a run, when it has been a while

Four things expire. None of them announce themselves, and three of them fail
loudly enough that you will notice; the third does not, which is why it is on
this list.

**1. Google credentials.** The corporate account authenticates with an
`authorized_user` ADC token, and organisation policy caps its lifetime.

```bash
gcloud auth application-default login    # pick the corporate account
```

Symptom if stale: `RefreshError: Reauthentication is needed`. This is a browser
flow, so it always needs a person.

**2. Model ids.** `gemini-3.1-pro-preview` is a preview snapshot, and preview
ids get re-pointed or retired without notice. Ask the provider rather than
trusting the config:

```bash
cc-ai-benchmark models gemini --filter pro
```

This is a catalogue call and spends nothing. If the id in
`config/models.json` is no longer listed, the run either fails or — worse —
resolves to something else. The report records what the provider actually
resolved to, so `resolved model` in a `verify` line is the ground truth.

**3. Prices.** `config/pricing.json` is hand-maintained. The Gemini 3.8 Flash
rate is promotional through **2026-12-31**; after that every cost number in a
report is wrong until the file is updated. A model with no price reports
`cost_usd: null` rather than a guess, so a missing price is visible. A *stale*
price is not. This is the one that fails silently.

**4. The bank.** Only if `outputs/` or the audit changed:

```bash
cc-ai-benchmark build-bank
```

## Always verify before you sweep

```bash
cc-ai-benchmark verify gemini-pro gemini-flash gemini-flash-lite
```

One live call per system, well under a cent in total. It proves the credential
resolves, the model id is real, the response parses into an answer, and usage
comes back so cost can be computed. A shape problem found here costs a cent; the
same problem found forty minutes into a sweep costs the sweep.

## Adding a system

Add an entry to `config/models.json` and a price to `config/pricing.json`, then
`verify` it. Gemini systems need the Vertex block so the run is reproducible
rather than depending on whatever environment variables the shell carried:

```json
"gemini-flash": {
  "adapter": "gemini",
  "model": "gemini-3.8-flash",
  "label": "gemini-3.8-flash",
  "vertex": true,
  "project": "${GOOGLE_CLOUD_PROJECT}",
  "location": "${GOOGLE_CLOUD_LOCATION}"
}
```

`bench` takes any number of systems and runs them concurrently, so adding one
does not lengthen the wall clock much.

## What a run leaves behind

Everything lands in `outputs/`, which is **gitignored** — reports do not survive
a fresh clone. Copy anything you intend to keep or compare against later.

| File | What it is |
|---|---|
| `<stamp>-sweep.json` | The full record: every item, every response, usage, latency, cost, plus environment and prompt-template hash |
| `<stamp>-sweep.html` | The chart page — accuracy with Wilson intervals, outcome composition, per-scope heatmap, strengths and weaknesses |
| `<stamp>-sweep.csv` | One row per question per system, with `prompt_tokens`, `cached_prompt_tokens`, `completion_tokens`, `total_tokens`, latency and cost |

## Comparing two runs

Accuracy differences between systems are not two independent samples — the same
items were put to both — so use the paired test rather than eyeballing the gap:

```bash
cc-ai-benchmark compare "$REPORT" gemini-3.1-pro gemini-3.8-flash
```

Overlapping confidence intervals on the chart mean the sample has not separated
those two systems. Say that, rather than reporting the larger number as a win.

## Why this is not scheduled

Running it on a cron would need Workload Identity Federation to get credentials
into CI, and would turn a deliberate $0.52 into a recurring bill for numbers
nobody asked for. The benchmark answers a question; run it when there is one —
a new model, a change to `grounded.py`, a revision of the bank.
