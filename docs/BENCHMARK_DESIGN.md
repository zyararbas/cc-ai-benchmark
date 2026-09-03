# Benchmark design: agent under test vs. generic LLMs

Status: proposed
Date: 2026-09-01

How this repository should be extended to compare a purpose-built insurance
agent against general-purpose LLMs on the Property & Casualty question bank,
and how a system under test gets plugged in — over HTTP, over MCP, in-process,
or through a vendor SDK.

This is a design, not an implementation. Section 12 is the build order.

---

## 1. What the benchmark actually claims

"Our agent beats GPT/Gemini/Claude on insurance questions" is three different
claims wearing one coat. The design has to keep them apart, because only the
third is worth publishing.

| Claim | Setup | What it really measures |
|---|---|---|
| **H1** Agent > generic LLM | Agent has retrieval over the source documents; the LLM is asked cold | That retrieval beats no retrieval. Already known. Not a result. |
| **H2** Agent > generic LLM, same documents | Both see the same source material | The agent's orchestration, prompting, and grounding — real, but narrow |
| **H3** Agent ≥ frontier LLM at materially lower cost/latency, and abstains rather than guessing when it doesn't know | Agent in its production configuration vs. the best generic model money can buy | The product claim |

**A single accuracy number that mixes these is not a finding.** Every run in
this harness therefore records the *condition* it ran under (§4), and the
leaderboard is a matrix, not a column. The headline comparison is pre-registered
(§8) so the other cells are visibly exploratory.

---

## 2. The data bank

### 2.1 What exists today

789 four-choice items extracted from P&C licensing material:

- `outputs/questions_1.json` — 100 items
- `outputs/scoped_questions_[1..23].json` — 689 items, each tagged with a `scope`
  and a source `ref`

JSON Lines, one item per line: `id`, `question`, `choices` (A–D), `answer`,
`explanation`, and on the scoped set `scope` and `ref`. Extracted from the
`.docx` sources in `data/documents/scoped/` by the vision prompts in
`src/cc_ai_benchmark/prompts/extraction/`.

### 2.2 Defects that block using it as ground truth

Found by inspection; each needs fixing before any number is published.

| # | Defect | Evidence | Fix |
|---|---|---|---|
| 1 | **The ground truth is gitignored.** `outputs/.gitignore` ignores `*`, and the harness treats `outputs/` as disposable run artifacts. All 789 items are untracked — one `git clean` from gone, and unversioned, so no published number can name the bank it ran against. | `git check-ignore -v outputs/questions_1.json` → ignored | Move the bank to a tracked `data/bank/`. `outputs/` keeps its current meaning: generated reports only. |
| 2 | **IDs are file-local.** `q_1` occurs in all 24 files — 789 items share 100 distinct ids. `CONTRIBUTING.md` requires stable ids; today an id doesn't identify an item. | 789 items, 100 distinct raw ids | Assign global, frozen ids: `pc-<source>-<seq>`, e.g. `pc-11-0042`. Keep the original `(file, local_id)` as provenance metadata. Never reissue. |
| 3 | **18 duplicate clusters, 36 items** — 5.2% of the scoped bank is a repeat. Ten are mechanical duplicates: the same question, the same four options, asked twice. Scoring against them double-counts one piece of knowledge. | `data/audit/duplicates.json` | Retire one member of each mechanical pair (§2.3). 679 items remain. |
| 4 | **Five clusters need a P&C-literate reviewer** — same question, different option pools, so whether they are one item or two is a content judgement no string comparison can make. | `_10` q_6/q_17; `_12` q_15/q_29; `_19` q_24/q_46; `_19` q_5/q_63; `_20` q_1/q_34 | Adjudicate. Mark the loser `superseded_by`, never delete — a removed id breaks comparability. |
| 5 | `explanation` is null on 240 of 689 scoped items (34.8%). | metadata table | Fine for grading. It only limits rationale scoring (§7), which must therefore be optional and run on the 449-item subset. |
| 6 | The bank is a **machine extraction**, so it has its own error rate, and that rate bounds every score the benchmark can report. | extraction prompt exists; no audit has been run | §2.5 |

### 2.3 Duplicate audit — completed

Run with `python scripts/audit_duplicates.py`; the manifest is written to
`data/audit/duplicates.json` and the script exits non-zero while any cluster is
unadjudicated, so it can gate CI.

Items are clustered on a normalized stem (exact, then fuzzy at ratio ≥ 0.93) and
each cluster is classified. **Only mechanical duplicates are resolved
automatically.** Anything whose resolution depends on reading the insurance
content goes to a human — string distance cannot see that "the customer" and
"the bailor (customer)" are the same answer, and it cannot see that two items
sharing an `EXCEPT` stem can both be correct with different distractors.

| Verdict | Clusters | Meaning | Action |
|---|---:|---|---|
| `SHUFFLED` | 9 | Same stem, same options, key moved to a different letter | Retire one — automatic |
| `IDENTICAL` | 1 | Byte-identical item (`_19` q_50 / q_51) | Retire one — automatic |
| `REVIEW` | 5 | Same question, different option pool | Human call |
| `DISTINCT` | 3 | Fuzzy stem match, genuinely different items | Keep both, no action |
| `CONFLICT` | **0** | Same stem and options, contradictory keys | — |

**There are no ground-truth conflicts in the scoped bank.** An earlier pass
flagged three, comparing answer letters without accounting for the option pool;
all three turned out to be items that share a stem but ask different things, or
state the same answer in different words. The bank is in better shape than the
first read suggested.

Two findings worth carrying forward:

- **The duplication is concentrated.** Eight of the nine `SHUFFLED` pairs sit in
  `scoped_questions_16` (Crime Insurance) — 16 of that file's 68 items are half
  of a repeated pair. Whatever produced that document repeated a quiz section
  with the options re-ordered. Deduping it drops Crime Insurance from the
  largest scope to a mid-sized one, which changes the stratification in §2.4.
- **Every cluster is within a single file.** No question appears under two
  different scopes, so scope labels are clean and `scope` is safe to use as the
  clustering variable for the bootstrap in §8.

Integrity checks pass across all 689 items: every answer letter exists in its
own choice map, every item has exactly four options, no option text is
duplicated inside an item, no stem or option is blank.

Keeper rule for the automatic retirements: prefer the member carrying an
`explanation`, then the lower ordinal. This recovers an explanation on
`_16` q_46 that its twin `_16` q_33 lacks.

### 2.4 Splits

| Split | Size | Public | Use |
|---|---|---|---|
| `dev` | ~150 | yes | Prompt and adapter iteration. Every design choice is made here. |
| `test` | ~639 | yes | The headline number. Read rarely, never tuned on. |
| `holdout` | 100–150 | **no** | Anti-contamination control (§3). Written or paraphrased fresh, never committed to a public repo. |

Stratify all three by `scope` so no split over-represents Crime Insurance (68
items) or under-represents California Property (7).

### 2.5 Ground-truth audit — a precondition, not a nicety

The bank was extracted by a model from scanned exam material. If its error rate
is 3%, then a 96% vs. 94% difference between two systems is inside the noise
floor of the ruler, and publishing it would be wrong.

Before any number goes public: sample 100 items stratified by source, have a
human verify stem, choices, and key against the `.docx`, and publish the
measured error rate ε with a confidence interval as a property of the bank.
Every reported accuracy is then read against ε, and any comparison whose margin
is smaller than ε is reported as *not resolved by this benchmark*.

This is also the cheapest possible credibility purchase. A benchmark that states
its own error bar is taken more seriously than one that reports four decimals.

---

## 3. Contamination — the central threat

These are questions from published licensing exam prep. The likelihood that
they appear in the pretraining data of every frontier model is high. Untreated,
this benchmark partly measures memorization — and it does so *asymmetrically*:

- **Generic LLMs may have memorized the answer key.** Inflates their score.
- **The agent retrieves from the very documents the questions were extracted
  from.** That is not memorization but it is still leakage: the agent is being
  handed the answer's source paragraph. Inflates its score under C1/C3.

Both directions have to be measured, not argued about. The mechanism: **variants
of the same items**, sharing task ids and adding a `variant` field.

| Variant | Transform | Detects |
|---|---|---|
| `base` | Verbatim | Baseline |
| `shuffled` | Choices permuted deterministically from `(task_id, seed)`; key remapped | Memorization of the *letter* |
| `distractor-swapped` | One distractor replaced with a plausible alternative, model-drafted and human-reviewed | Memorization of the *answer set* |
| `paraphrased` | Stem rewritten, meaning preserved, human-verified | Memorization of the *stem* |
| `holdout` | Fresh private items | Everything above at once |

**Memorization delta** = `accuracy(base) − accuracy(shuffled)` (and the same
against `paraphrased`). Report it per system as a first-class number. A system
with a large delta is recalling, not reasoning, and its `base` score should not
be quoted without the delta beside it.

Two consequences worth stating plainly:

- **Publishing the bank burns it.** This repo is public; anything committed here
  is plausible future training data. Keep `holdout` out of the repo entirely,
  rotate it, and embed a canary string in the public files so future
  contamination is at least detectable.
- **Licensing.** The stems are verbatim from third-party exam prep material.
  Whether they can be republished is a legal question, not a technical one, and
  it blocks public release of the bank (§11).

---

## 4. Conditions — the fairness contract

The place where vendor benchmarks usually cheat is the setup, not the scoring.
So the setup is an explicit, recorded axis.

| Condition | The system sees | Purpose |
|---|---|---|
| **C0** closed-book | The question only. No retrieval, no tools, no documents. | Raw parametric knowledge |
| **C1** open-book, oracle context | The question plus the specific source section named by the item's `ref` | Ceiling: what's achievable when retrieval is perfect |
| **C2** open-book, shared corpus | The question, plus all 23 documents reachable through **one retriever shared by every system** | Isolates reasoning from retrieval quality |
| **C3** native | The agent exactly as it runs in production, with whatever tools it has | The product claim |

Rules that make the numbers comparable:

1. Generic baselines run **at minimum C0 and C2**. C0 alone understates them;
   C2 is where the interesting comparison lives.
2. The agent runs **at minimum C3**, and C0 too if its tools can be disabled.
3. **Never headline agent-C3 against baseline-C0.** That is claim H1 — the
   uninteresting one — dressed up as H3.
4. Within a condition, all systems get the same prompt template, the same output
   contract, and the same output token ceiling. Anything system-specific is
   confined to the adapter and appears verbatim in the report.
5. C2's retriever is part of the harness, is versioned, and is scored on its own
   (recall@k against each item's `ref`). If the shared retriever is bad, C2
   compresses everyone toward the floor and the comparison says nothing — so its
   recall is published alongside.

---

## 5. Plugging in a system under test

This is the part the rest of the design hangs off. The answer is a single thin
interface, with transport as configuration rather than as code.

### 5.1 The adapter contract

```python
@dataclass(frozen=True)
class Query:
    task_id: str
    prompt: str  # rendered from the versioned template
    condition: str  # "C0" | "C1" | "C2" | "C3"
    choices: dict[str, str]
    context: str | None = None  # C1/C2 only
    seed: int | None = None


@dataclass(frozen=True)
class Response:
    text: str
    raw: dict[str, Any]  # provider payload, for forensics
    model_id: str | None  # resolved, not requested
    usage: dict[str, int]  # input/output/cache tokens
    latency_ms: float
    cost_usd: float | None
    error: str | None = None


class Adapter(Protocol):
    name: str

    def describe(self) -> dict[str, Any]: ...  # copied verbatim into the report
    def answer(self, query: Query) -> Response: ...
    def close(self) -> None: ...
```

`describe()` is not documentation — it is the reproducibility record: resolved
model id, sampling or effort settings, tool list, endpoint host, server version,
prompt template hash. Two runs are comparable only if their `describe()` blobs
match on the fields that matter.

`Response` carries usage, latency, and cost because **cost per correct answer is
half of claim H3** and cannot be reconstructed after the run. A harness that
returns only a string can never make the product argument.

The existing `Runner = Callable[[Task], str]` in `src/cc_ai_benchmark/runners.py`
stays as a shim over `Adapter`, so `echo`, `oracle`, and the current tests keep
working unchanged.

### 5.2 Transports

| Transport | Right when | Auth | What it costs you |
|---|---|---|---|
| **In-process Python** | The system lives in a repo you can import | none | Doesn't exercise the deployed artifact — measures code, not the running service |
| **HTTP endpoint** | **Recommended for the agent** | Bearer token + session cookie | Needs a route built for evaluation |
| **MCP** | The system is exposed as MCP tools | per server | Ambiguity about what is being measured — see below |
| **Vendor SDK** | The generic-LLM baselines | API key from env | none |
| **CLI subprocess** | Closed-source or local binaries; escape hatch | none | Slow, brittle output parsing |

#### HTTP endpoint — the recommended path for the agent

Ask the backend for a **dedicated evaluation route** rather than reusing the
production chat endpoint. Chat carries conversation state, personalization, and
a prose contract aimed at a UI; extracting a letter from chat prose adds a
parsing error you can never separate from model error afterward.

In the cross-repo request format the parent `CLAUDE.md` prescribes:

```
## Request from BENCH → BE: evaluation answer endpoint

### Endpoint
POST /api/eval/answer

### Request body
{
  "run_id": "run_2026-09-01T12:00:00Z_abc123",
  "task_id": "pc-11-0042",
  "condition": "C3",
  "question": "<stem>",
  "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "context": null,
  "allow_abstain": true
}

### Response
200 {
  "answer": "B",              // or null when abstaining
  "confidence": 0.82,         // optional, [0,1]
  "rationale": "...",         // optional
  "citations": [{"doc": "11. Commercial Property Insurance.docx", "section": "..."}],
  "model": "<resolved model id>",
  "agent_version": "<git sha or release>",
  "usage": {"input_tokens": 0, "output_tokens": 0},
  "latency_ms": 0
}
4xx { "detail": "<reason>" }   // never a fabricated answer

### Behavior notes
- Stateless per task. Each request is its own session; nothing carries between
  task_ids. A benchmark run that shares state leaks earlier answers into later
  questions and silently inflates the score.
- Deterministic settings pinned server-side and reported back, or accepted as
  request fields — either way they land in the report.
- Eval traffic is excluded from every feedback, logging-to-training, or
  fine-tuning loop. A system that learns from the benchmark invalidates it.
- Documented concurrency limit and rate limit, so the harness can size its pool.
- Points at staging with a dedicated eval tenant, never production.
```

Per the parent working agreements, the backend owns this shape; this document is
the request, and the contract lands in `cc-stack/decisions/` before wiring.

#### MCP — legitimate, but be precise about what you are scoring

Two cases that get conflated, with very different meanings:

**(a) The system under test *is* an MCP server that answers.** It exposes
something like `answer_question(question, choices) -> {answer, rationale}`. The
adapter connects (stdio or streamable HTTP), calls `tools/call`, and reads the
structured result. This is equivalent to the HTTP case and is scored the same
way.

**(b) The system under test is an MCP server exposing *retrieval* tools**
(`search_policy_docs`, `get_form`) and you drive a model over them in a loop.
Then **you are benchmarking your own agent loop plus that model plus that
server** — not the server. This is a perfectly good experiment; it is precisely
condition C2. But it must be labeled `harness-loop + <model> + <server>@<version>`,
and its score must never be quoted as the MCP server's score.

Mechanics either way: pin the server version or commit in `describe()`; hash the
tool list, because tool schemas are part of the prompt and a changed description
changes behavior; open **one session per task and tear it down**, for the same
isolation reason as the HTTP route; cap tool-call turns per task, or a single
looping item will consume the run's budget.

#### Vendor SDK adapters — the generic baselines

**Pin exact model snapshots.** Floating aliases move underneath you and quietly
break comparability between a run in September and a run in November. Record the
*resolved* id returned by the provider, not the one you asked for.

For the Anthropic baselines, current IDs and list prices (input/output per 1M
tokens):

| Model | ID | Input | Output |
|---|---|---|---|
| Claude Opus 5 | `claude-opus-5` | $5.00 | $25.00 |
| Claude Sonnet 5 | `claude-sonnet-5` | $2.00 | $10.00 |
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1.00 | $5.00 |

Three things specific to current-generation models that a benchmark design has
to get right:

- **Temperature is not the knob.** Sampling parameters are removed on Opus 5 /
  Sonnet 5 and the 4.6+ family — sending `temperature` returns a 400. The
  quality/cost dial is `output_config.effort` (`low` … `max`). So "Claude scored
  X" is under-specified: the report must carry the **effort level**, and a
  serious comparison sweeps it (`low`, `high`, `max`) rather than picking one.
- **Runs are not bit-reproducible.** With no temperature to zero out, repeats are
  mandatory: n≥3 per (system, condition, variant), reported as mean ± sd.
- **Cost control that doesn't change outputs:** prompt-cache the shared document
  prefix under C1/C2 (the corpus is identical across items — this is close to
  the ideal caching shape, and cache reads are ~0.1× input cost), and run the
  large sweeps through the Batches API at 50%. Neither affects the answer, so
  neither compromises the measurement.

For non-Anthropic baselines, pin the snapshot id and record the price in effect
at run time in a `pricing.json` the report references by hash. **Do not hardcode
competitor prices in this document** — they change, and a stale number in a
public benchmark is a credibility problem.

#### CLI subprocess

Escape hatch for local or closed-source systems. JSON on stdout, hard timeout,
arguments passed as an argv list — never a shell string with the question
interpolated into it.

### 5.3 Adapter conformance test

No adapter produces a publishable number until it passes the same test file
(`tests/test_adapter_contract.py`, parameterized over registered adapters,
network ones marked and skipped in CI):

1. Returns a `Response` for a known-good task.
2. Returns `Response(error=...)` — not a raised exception — on an injected
   transport failure. The existing "one broken task never aborts a run" property
   must hold across every transport.
3. Honors its timeout.
4. **Isolation probe:** ask task A, then task B; assert B's response carries no
   trace of A. This is the test that catches a stateful endpoint silently
   inflating scores, and it is the single most valuable test in the suite.
5. `describe()` includes a resolved model id and settings.

### 5.4 Execution concerns

- **Concurrency** declared per adapter, bounded by whatever the endpoint
  documents.
- **Retry only transport failures** (429, 5xx, timeout) with exponential backoff.
  Flag retried items in the result — a retry changes the sample. **Never retry a
  wrong answer.**
- **Budget ceiling in dollars per run**, checked as costs accumulate; abort with
  a partial report rather than overrunning silently.
- **Response cache** keyed by `(describe hash, prompt hash, variant, seed,
  repeat index)` so re-scoring, re-parsing, and statistics never re-bill the
  provider. This makes scorer iteration free, which is what makes §7 tractable.

---

## 6. Prompt and response contract

One template per condition, stored under `prompts/eval/`, versioned, hashed into
every report. Templates are tuned on `dev` only.

Ask for a strict, machine-readable answer — structured outputs where the provider
supports schema-constrained decoding, otherwise a single JSON object:

```json
{"answer": "B", "confidence": 0.82}
```

**Abstention is first-class.** `"answer": null` means "I don't know". In an
insurance product a confident wrong answer is worse than a decline, and standard
MCQ accuracy hides exactly that distinction. Every condition's template offers
the option; §7 scores it.

---

## 7. Scoring

A new `mcq_letter` scorer, registered alongside the existing `exact_match` and
`contains`.

**Parsing ladder:** exact letter → letter with punctuation (`B)`, `(B)`,
`Answer: B`) → full choice-text match against the item's choices → refusal. If
two different letters can be extracted, it is a **parse failure**, never a guess.

**Per-item outcome** — an enum, not a float:

`correct` | `incorrect` | `abstained` | `parse_failure` | `error`

Parse failures are recorded as their own outcome and treated as a *harness*
defect until proven a model defect. Silently scoring them zero is how a benchmark
ends up measuring its own regex.

**Three reported metrics**, all of them, always:

| Metric | Definition | Why |
|---|---|---|
| Accuracy | `correct / all items` | Comparable to every other MCQ benchmark |
| Coverage-conditional accuracy | `correct / (correct + incorrect)` | How good it is when it does answer |
| Risk-weighted score | `(correct − incorrect) / all`, abstention 0 | The insurance-relevant number: penalizes confident wrongness |

Report abstention rate beside them. A system at 88% accuracy with a 10%
abstention rate and near-zero confident errors is a better product than one at
91% that never declines — and only the last two columns show it.

**Rationale scoring is optional and separate.** For the 449 items with a non-null
`explanation`, an LLM judge can grade the rationale. If it is used: the judge is
not a system under test, its prompt is versioned, it is calibrated against ~100
human-labeled pairs, and **no judge-scored number is published without its
human-agreement statistic (Cohen's κ)**.

Explicit non-goal: do not LLM-judge the multiple-choice items. Letter matching is
exact, free, and deterministic; a judge would only add noise and cost.

---

## 8. Statistics

- **n = 689 on `test`.** At p ≈ 0.90 the 95% CI half-width is roughly ±2.2pp.
  Unpaired differences under ~4pp are not resolvable. Say so rather than ranking
  systems inside the noise.
- **Compare paired, not marginal.** Both systems answer the same items, so use
  **McNemar's exact test** on the discordant pairs. It has far more power than
  comparing two independent confidence intervals, and reporting overlapping CIs
  as "no difference" is the most common error in benchmark write-ups.
- **Bootstrap** (10k resamples, **clustered by `scope`** — items within one
  source document are correlated, and an unclustered bootstrap will understate
  the interval) for CIs on accuracy and on the paired difference.
- **Multiple comparisons.** k systems × 4 conditions × 5 variants is a large
  family. Pre-register one primary comparison — *agent under C3 vs. the strongest
  generic baseline under C2, accuracy on `test`/`base`* — and apply Holm–Bonferroni
  across the declared secondary family. Everything else is exploratory and
  labeled as such.
- **Per-scope breakdown** with counts, and **no ranking claim for any scope with
  n < 20**. Seven of the 23 scopes are at or below that; scope 22 has 7 items.

---

## 9. Report and leaderboard

Extend `RunReport` additively — existing keys keep their meaning, so reports
already written stay readable.

New at the run level: `condition`, `variant`, `repeat_index`, `bank_version`,
`prompt_template_hash`, `adapter` (the `describe()` blob), `cost` (tokens and
dollars), `outcomes` (histogram of the §7 enum).

New per result: `outcome`, `parsed_answer`, `confidence`, `usage`, `retries`,
`latency_ms`.

Two new commands:

- `cc-ai-benchmark compare <a.json> <b.json>` — paired table, discordant pair
  counts, McNemar p, bootstrap CI on the difference.
- `cc-ai-benchmark leaderboard outputs/` — the condition × system matrix, with
  memorization deltas and cost per correct answer.

**Every published number links to the run report that produced it.** That is
already this repository's stated premise — "anyone can check a published number
rather than take it on faith" — and it is the rule that makes the rest of this
design worth the effort.

---

## 10. Reproducibility

Two runs are comparable only when these match: `bank_version`, `variant`,
`condition`, `prompt_template_hash`, and the fields of `describe()` that affect
behavior (resolved model id, effort/sampling, tool list hash, agent version).
The harness records all of them; `compare` refuses to pair runs that differ on
any of them without an explicit override flag.

---

## 11. Security and public-repo constraints

- **Credentials from the environment only**, never committed — already the rule
  in `CONTRIBUTING.md`; the adapter layer inherits it.
- **The endpoint adapter targets staging**, with a dedicated eval tenant. Never
  production, never a tenant holding real policy data.
- **No customer data ever crosses a baseline vendor API.** The bank is generic
  licensing content; it must stay that way. Nothing from `cc-ai`'s document
  corpus enters this repo.
- **Licensing of the source material is an open blocker** on publishing the bank
  verbatim in a public repository (§3). Resolve before release; it does not block
  building the harness or running it privately.
- **Eval traffic must be excluded from any learning loop** on the agent side, or
  the benchmark trains its own subject.

---

## 12. Build order

Each phase is one pull request on a branch, reviewed by someone other than the
author, per `CONTRIBUTING.md`.

| Phase | Work | Done when |
|---|---|---|
| **0. Bank hygiene** — no model calls, no cost | Move the bank to tracked `data/bank/`; assign global frozen ids; apply the 10 automatic retirements and adjudicate the 5 review clusters from `data/audit/duplicates.json`; write the bank → suite build script; stratified dev/test split | `validate` passes on generated suites; ids are stable and documented |
| **1. Scoring and report** | `mcq_letter` scorer, outcome enum, extended `RunReport` | Oracle still scores 1.0; parse failures visible |
| **2. Adapter layer** | `Adapter` protocol, `Runner` shim, conformance test, null/echo/oracle adapters | Existing tests green; conformance test runs in CI |
| **3. Generic baselines** | Anthropic adapter first, then the rest; cost tracking, response cache, budget ceiling | One full `dev` run under C0 with cost reported |
| **4. Agent adapters** | HTTP endpoint adapter against the §5.2 contract; MCP adapter if and when the agent exposes one | Isolation probe passes against the real endpoint |
| **5. Variants and contamination** | Shuffle, distractor swap, paraphrase, private holdout; memorization delta | Delta reported per system |
| **6. Statistics and leaderboard** | `compare`, McNemar, clustered bootstrap, leaderboard page | Primary comparison pre-registered and reported |

**The ground-truth audit (§2.5) gates publication, not development.** Build
through phase 6 without it; publish nothing until ε is measured.

---

## 13. Open questions

1. **Licensing** — can the verbatim stems be published in a public repository?
   This blocks release of the bank, and the answer may force a paraphrase-only
   public split.
2. **Endpoint** — does an evaluation-suitable route exist on the agent today, or
   do we file the §5.2 contract as a decision record and wait for it?
3. **Roster and budget** — which generic models, at which effort levels, and what
   dollar ceiling per full run?
4. **Adjudication** — who resolves the 3 conflicting duplicates and performs the
   100-item human audit? It needs a P&C-literate reviewer, not an engineer.
5. **Publication** — is the leaderboard public, and does it name competitor
   models by name? That changes the legal review, not the design.
