# Running a benchmark

## One-time setup

```bash
pip install -e ".[dev,providers]"      # or just the providers you need
python -m cc_ai_benchmark build-bank   # materializes data/bank/pc-bank.jsonl
```

`build-bank` turns the raw extraction in `outputs/` into a bank with global,
stable ids, the duplicate retirements from `data/audit/duplicates.json` applied,
and the five review clusters flagged. It produces **679 items, of which 669 are
usable** while the flagged ten await review.

## Two things to fill in before a real run

**1. Model ids** — `config/models.json` ships with `FILL-IN` placeholders for
Gemini and OpenAI. The harness refuses to run a system whose id is still a
placeholder rather than guessing one. Use exact provider snapshot ids, never
floating aliases: an alias moves underneath you and silently breaks
comparability between a run today and a run next month. Whatever the provider
actually resolves to is what lands in the report.

**2. Prices** — `config/pricing.json` carries current Anthropic list prices; the
other entries are `null`. An unpriced model reports `cost_usd: null`, so cost
per correct answer is simply absent rather than wrong.

### Finding the ids

Do not type a snapshot id from memory. Ask the provider:

```bash
export ANTHROPIC_API_KEY=...   GEMINI_API_KEY=...   OPENAI_API_KEY=...
python -m cc_ai_benchmark models                  # all three catalogues
python -m cc_ai_benchmark models gemini --filter pro
```

This is a catalogue call. It lists exactly what your key can reach and spends no
tokens, so it is free to run before you have decided anything. Copy the ids it
prints into `config/models.json`. A provider whose key is absent is reported as
unavailable and the others still list.

## The shortest path to a real number

You do not need all four providers to get off zero. One key is enough:

```bash
export ANTHROPIC_API_KEY=...
python -m cc_ai_benchmark verify anthropic                    # ~$0.001
python -m cc_ai_benchmark bench anthropic --limit 20 --budget 0.25
python -m cc_ai_benchmark bench anthropic --budget 3.00 --name baseline
python -m cc_ai_benchmark chart outputs/<stamp>-baseline.json
```

`anthropic` is the only system in `config/models.json` that ships ready to run:
its id is real and its price is known. Everything else needs a snapshot id
first. Add providers one at a time, re-running `verify` for each, and the
`bench` command takes as many systems as you give it — they run in parallel.

## Verify before you sweep

```bash
python -m cc_ai_benchmark verify anthropic gemini-pro openai our-approach
```

One live call per system, a fraction of a cent in total. It proves credentials
resolve, the model id is real, the response parses, and usage comes back. Run
it after any config change — a shape problem found here costs a cent, the same
problem found mid-sweep costs the sweep.

## Run

```bash
# smoke test: 40 items, every system, in parallel
python -m cc_ai_benchmark bench anthropic gemini-flash gemini-pro openai our-approach \
    --limit 40 --budget 2

# the full closed-book baseline sweep
python -m cc_ai_benchmark bench anthropic gemini-flash gemini-pro openai \
    --condition C0 --budget 25 --name baselines

# our approach, in its native configuration
python -m cc_ai_benchmark bench our-approach --condition C3 --budget 60 --name ours
```

Systems run **concurrently, one worker per system**, each with its own bounded
pool sized by that adapter's declared safe in-flight count. A rate-limited
provider slows only itself.

`--budget` is a hard ceiling in dollars across the whole sweep, checked as spend
accumulates and enforced inside the worker rather than at submit time. On
reaching it the run stops and reports what it has, with `stopped_early` set.

## Read the numbers

```
system   cond    n   acc    95% CI        cov    risk   absn  parse  err
oracle   C0     40  1.000 [0.912,1.000]  1.000  1.000  0.00     0    0
stub     C0     40  0.700 [0.546,0.819]  0.737  0.450  0.05     0    0
refuser  C0     40  0.000 [0.000,0.088]  0.000  0.000  1.00     0    0
```

| Column | Meaning |
|---|---|
| `acc` | correct / all items — comparable to any other MCQ benchmark |
| `cov` | correct / answered — how good it is when it commits |
| `risk` | (correct − incorrect) / all — abstention scores 0, confident error scores −1 |
| `absn` | share of items declined |
| `parse` | responses that could not be parsed — a **harness** defect until proven otherwise |

`risk` is the insurance-relevant number. A system at 0.88 accuracy that declines
the 10% it is unsure of beats one at 0.91 that never declines, and only this
column shows it.

## Chart it

```bash
python -m cc_ai_benchmark chart outputs/<stamp>-sweep.json      # writes .html alongside
python -m cc_ai_benchmark chart outputs/<stamp>-sweep.json -o /tmp/results.html
```

A standalone page: accuracy with Wilson intervals, what every answer turned into
(correct / wrong / declined / unparseable / transport error), a per-scope
heatmap, and a per-system strengths-and-weaknesses card. No CDN, no build step,
no network — it opens from a file:// URL on a booth laptop.

The heatmap's rightmost **Field** column is the mean across systems for that
scope, and it is the column to read first. A scope where one system is red is a
weakness of that system. A scope where the *field* is red is usually a statement
about the questions — a wrong key, an ambiguous stem, a jurisdictional edge —
and belongs in the ground-truth audit rather than in a slide about models.

The page refuses to present itself as a benchmark when any system in the report
is a mock adapter, and says so in a banner at the top.

## Compare two systems properly

```bash
python -m cc_ai_benchmark compare outputs/<report>.json our-approach anthropic
```

Both systems answered the same items, so they are not two independent samples.
`compare` runs **McNemar's exact test** on the discordant pairs, which has far
more power than reading two overlapping confidence intervals — and it will tell
you when a difference is *not* resolved by the sample rather than letting you
rank inside the noise.

## Conditions

| Flag | The system gets | Use for |
|---|---|---|
| `--condition C0` | The question alone | Baseline models |
| `--condition C1` | The item's own source document | The retrieval ceiling |
| `--condition C2` | The shared retriever's top hit | Reasoning, retrieval held constant |
| `--condition C3` | Whatever the system natively does | Our approach |

**Never headline a C3 result against a C0 result** — that measures the presence
of retrieval, not the quality of a system.

The shared C2 retriever is deliberately simple (deterministic term overlap, no
embeddings, no per-system tuning) and its recall is measured and written into
every C2 report: **recall@1 = 0.617, recall@3 = 0.883**. A shared retriever has
to be fair, not good, and a transparent one is easier to hold constant.

## What a pass costs

Measured against the real bank at 669 items, priced at Claude Opus 5 rates
($5/M in, $25/M out, $0.50/M cache read):

| Condition | Prompt tokens/item | Cost per full pass |
|---|---:|---:|
| C0 closed book | 156 | **$1.53** |
| C1 oracle document | 6,573 | **$22.99** |
| C3 full corpus, no caching | 140,944 | $472.46 |
| C3 full corpus, cached | 140,944 | **$48.78** |

The whole 23-document corpus is only ~141k tokens, which is why "put everything
in front of the model" is affordable at all — but only with caching. The prefix
is byte-identical on every call, so it is written once and read back at a tenth
of the price. That is a 10x difference for identical answers, which is why the
material lives in the system prefix rather than the user turn.

**A full four-model C0 baseline sweep costs roughly $5–8.** The grounded
approach is the expensive one; start it with `--limit` and a `--budget`.

## Changing "our approach"

`src/cc_ai_benchmark/adapters/grounded.py` is the file meant to be edited.
`gather_material` decides what the model sees; `answer_with_material` builds the
prompt. Both are plain functions. The model underneath is a parameter, so the
same approach can be re-measured on a different model — which is the comparison
worth having: how much of the result is the material, and how much is the model.

Three strategies ship: `oracle` (the item's own document), `retrieval` (the
shared retriever), and `full` (the entire corpus, cached — the default).
