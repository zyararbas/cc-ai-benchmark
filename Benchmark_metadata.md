# Benchmark Metadata

Ground-truth question sets extracted from Property & Casualty insurance licensing
material, for evaluating multiple-choice answering by AI models.

Two collections live in `data/documents/questions/`, and `cc-ai-benchmark
build-bank` materializes them into `data/bank/pc-bank.jsonl`:

**Questions** — `questions_1.json` — 100 items  
**Scoped questions** — `scoped_questions_[1..23].json` — 789 items across 23 files  

---

## 1. Questions 
  
### Schema

```json
{
  "id": "q_1",
  "question": "<verbatim stem>",
  "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "answer": "A",
  "explanation": "<verbatim text or null>"
}
```

### Statistics

- 100 items, all with exactly 4 choices (A–D)
- Answer distribution: A 22, B 31, C 26, D 21
- `explanation` non-null on all 100 items
- No null answers, no multi-answer items


---

## 2. Scoped questions 

### Schema

Adds `scope` and `ref` after `explanation`; otherwise identical to the collection above.

```json
{
  "id": "q_1",
  "question": "<verbatim stem>",
  "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "answer": "A",
  "explanation": "<verbatim text or null>",
  "scope": "Commercial Property Insurance",
  "ref": "11. Commercial Property Insurance.pdf"
}
```
 

### inventory

| File | Scope | Items | `explanation: null` |
|---:|---|---:|---:|
| 1 | Insurance _ Property and casualty | 20 | 0 |
| 2 | Contracts (1 item without a scope) | 15 | 4 |
| 3 | Basics of Property and Casualty Insurance | 26 | 16 |
| 4 | Basics of Property Insurance Activities | 44 | 13 |
| 5 | Basics of Casualty Insurance | 37 | 14 |
| 6 | Dwelling Insurance | 39 | 39 |
| 7 | Homeowners Insurance | 41 | 41 |
| 8 | Personal Auto Insurance | 29 | 19 |
| 9 | Personal Insurance- Miscellaneous | 22 | 12 |
| 10 | Commercial Package Policy | 19 | 0 |
| 11 | Commercial Property Insurance | 67 | 18 |
| 12 | Commercial Inland Marine Insurance | 40 | 10 |
| 13 | Farm insurance | 23 | 12 |
| 14 | Equipment Breakdown Risks & Protection | 22 | 3 |
| 15 | Commercial liability insurance | 51 | 20 |
| 16 | Crime Insurance_ | 60 | 8 |
| 17 | Commercial Auto Insurance | 50 | 11 |
| 18 | Miscellaneous Commercial Insurance | 34 | 5 |
| 19 | Businessowners Policy | 59 | 23 |
| 20 | Workers compensation_ | 35 | 7 |
| 21 | California Laws, Rules. and Regulations for Property & Casualty Insurance | 29 | 19 |
| 22 | California Laws, Rules, and Regulations for Property  Insurance Only | 7 | 0 |
| 23 | California Laws, Rules, and Regulations for Casualty  Insurance Only | 10 | 1 |
| | **Total** | **789** | **297** |

### Aggregate statistics

- 789 scoped items across 23 files, all with exactly 4 choices (A-D)
- Answer distribution: **A 210, B 196, C 197, D 186** -- no positional bias of concern
- `explanation` is `null` on 297 items (37.6%), non-null on 492
- A further 100 general items build under `pc-gen01-`. They carry no `scope`
  and no `ref`, so they are flagged `no-source` and C1 cannot be run on them.
- Bank total 876: 776 scoped items plus the 100 general ones. The 13 scoped
  items the duplicate audit proposes retiring are held out of the bank rather
  than deleted from the raw files, so the build depends on the audit having
  been run -- build, audit, then build again if the audit changed anything.
- 52 retired questions are held as tombstones in the raw files. Each holds its
  sequence slot so no live id ever shifts, and none is built into the bank.
- Zero null answers, zero multi-answer items, zero items awaiting review.
  `pc-05-0037` was extracted with a null answer -- its screenshot is cropped
  through the marker column -- and a reviewer ruled the answer is C on
  2026-09-08.
- `pc-06-0003` held a wrong key -- `Named peril`, read from a filled radio in a
  selection-only screenshot. The same stem appears graded later in the same
  document with a red X on that option and a green check on `DP-2`. A reviewer
  ruled the answer is `DP-2` on 2026-09-10, so the id was retired and the
  corrected item reissued, which the audit then deduped against `pc-06-0039` --
  the graded occurrence, already keyed `DP-2`. Any result measured against
  `pc-06-0003` predates the correction and is not comparable across it.
