# Benchmark Metadata

Ground-truth question sets extracted from Property & Casualty insurance licensing
material, for evaluating multiple-choice answering by AI models.

Two collections live in `data/documents/questions/`, and `cc-ai-benchmark
build-bank` materializes them into `data/bank/pc-bank.jsonl`:

**Questions** — `questions_1.json` — 100 items  
**Scoped questions** — `scoped_questions_[1..23].json` — 742 items across 23 files  

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
| 5 | Basics of Casualty Insurance | 10 | 0 |
| 6 | Dwelling Insurance | 29 | 29 |
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
| | **Total** | **742** | **271** |

### Aggregate statistics

- 742 scoped items across 23 files, all with exactly 4 choices (A-D)
- Answer distribution: **A 199, B 189, C 188, D 166** -- no positional bias of concern
- `explanation` is `null` on 271 items (36.5%), non-null on 471
- A further 100 general items build under `pc-gen01-`. They carry no `scope`
  and no `ref`, so they are flagged `no-source` and C1 cannot be run on them.
  Bank total 842.
- 41 retired questions are held as tombstones in the raw files. Each holds its
  sequence slot so no live id ever shifts, and none is built into the bank.
- Zero null answers, zero multi-answer items, zero items awaiting review
