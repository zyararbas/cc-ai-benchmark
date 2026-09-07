# Ingesting a source document into the bank

The operating procedure for turning one `.docx` of exam screenshots into a
`scoped_questions_<n>.json` file and folding it into the bank. Follow it for a
document that has never been ingested, and for one that has been edited since
it was last ingested — the two cases differ only at step 5, and step 5 is the
one that can quietly destroy a year of results.

## What you are given

| Parameter | Example | Where it comes from |
|---|---|---|
| `DOC` | `data/documents/scoped/1. Insurance _ Property and casualty.docx` | The file that appeared or changed |
| `N` | `1` | The leading number in the filename. **Never reassign it.** |
| `SCOPE` | `Insurance _ Property and casualty` | The filename with the leading number and extension stripped |
| `REF` | `1. Insurance _ Property and casualty.docx` | The filename, verbatim |
| `OUT` | `outputs/scoped_questions_1.json` | Derived from `N` |

`N` is load-bearing. Bank ids are `pc-<N>-<seq>`, so renumbering a document
renames every question in it and silently breaks comparability with every
report ever produced. If a document is renamed, keep its original `N`.

## Step 1 — Pull the images out, in document order

```bash
python scripts/docx_images.py "$DOC" -o work/<N>/     # .docx or .pdf
```

Both formats are handled. The same deck often arrives twice, once as each, and
the embedded screenshots are usually byte-for-byte the same picture re-encoded
— so a PDF alongside a `.docx` is a second copy, not a second document, and it
does not get its own `N`. Prefer whichever is present; if both are, they should
agree, and a disagreement in image count is worth understanding before you
extract from either.

The PDF route needs `pip install -e ".[pdf]"`.

Do not read the images out of the zip yourself. Archive order is alphabetical,
which puts `image10` before `image2`; the script resolves the relationship table
and emits `page-001.png` upward in the order the reader actually sees. Question
order is the only thing anchoring sequence numbers, so getting this wrong
reorders the bank.

## Step 2 — Triage and clean the images

Not every image is a question. These documents interleave content slides with
exam screenshots, and the two are separable before you spend a vision call:

- **Question screenshots** are roughly portrait or square, around 730x550, and
  contain a stem, lettered options, and marker icons.
- **Content slides** are wide and short — a title band, a photograph, a bullet
  list. Discard them.

Aspect ratio is a filter, not a decision. Open anything ambiguous and look.

Then check each remaining image for damage, because a truncated screenshot is
the failure mode that produces confidently wrong ground truth:

- **Clipped edges.** Options or marker icons cut off at the right border, an
  Explanation block running off the bottom. A clipped marker column means the
  answer is unrecoverable from that image — flag it, do not infer the answer
  from the subject matter.
- **Two questions in one image.** Split them, or extract both and let step 3
  emit two objects.
- **Illegible scaling.** If the letters cannot be read reliably, say so rather
  than guessing.

Record what you discarded and what you flagged. That list belongs in the report
at step 6.

## Step 3 — Extract

Use `extraction_2.md` verbatim as the system prompt — it holds the marker
precedence rules (green check beats filled radio, red X is never the answer, a
selection is not a key) and those rules are the difference between ground truth
and a transcription of somebody's wrong exam attempt. Do not paraphrase it, and
do not re-derive those rules from the images.

One image per call, in page order. Two amendments to that prompt for this
pipeline:

- Set `"scope"` to `SCOPE` and `"ref"` to `REF`, not the literals in the
  prompt's example.
- Number `id` sequentially across the whole document, continuing across images.

**The answer comes from the markers, never from your own knowledge of
insurance.** If you find yourself reasoning about which option is correct, you
have left the task. An item whose marker is unreadable gets `"answer": null`,
`"needs_review": true`, and a one-line `"review_note"`. A flagged item is
cheap; a wrong key is contamination that survives every later measurement.

## Step 4 — Write the file

`OUT` is **JSON Lines** — one object per line, no array wrapper — despite the
`.json` extension. Match the existing files exactly:

```json
{"id": "q_1", "question": "...", "choices": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "B", "explanation": null, "scope": "...", "ref": "..."}
```

Then check it parses and the counts are what you expect:

```bash
python -c "import json,sys;[json.loads(l) for l in open('$OUT') if l.strip()]"
```

## Step 5 — Reconcile, if this document was already in the bank

**This is the step that matters.** A fresh extraction of an edited document is
not a replacement for the old one. The bank's ids are positional, and reports
going back months reference them. Overwriting `OUT` and rebuilding is how a
question called `pc-01-0007` becomes a different question while keeping its
name, which makes every historical number a lie without producing a single
error message.

```bash
python scripts/reconcile_extraction.py <N> --new work/<N>/extracted.jsonl
```

It matches old to new on the normalized stem and classifies every item:

| Class | Meaning | What happens to the id |
|---|---|---|
| `UNCHANGED` | Stem, choices and answer all identical | Keeps its id |
| `MOVED` | Same item, different position in the document | **Keeps its id.** Position is not identity |
| `ADDED` | Stem not present before | Gets the next free sequence number, appended |
| `REMOVED` | Stem no longer in the document | Id is **retired, never reused** |
| `EDITED` | Same stem, but choices or answer changed | Old id retired, new id issued |

`EDITED` is deliberately strict. A question whose answer key was corrected is
not the same question as the one models were scored against last month —
treating it as continuous would mix two different items under one name. Retire
and reissue, so a comparison across that boundary is visibly impossible instead
of quietly wrong.

Read the diff before accepting it. A reconciliation reporting hundreds of
`REMOVED` and `ADDED` usually means the stems were reformatted rather than the
questions replaced, and the right fix is to the normalizer, not the bank.

## Step 6 — Rebuild and re-audit

```bash
cc-ai-benchmark build-bank
python scripts/audit_duplicates.py
```

The audit exits non-zero while any duplicate cluster is unadjudicated. New
questions frequently duplicate existing ones across documents — a definition
in the Contracts document reappearing in Commercial Liability — and an
undetected duplicate double-weights whatever it happens to test.

Then report, in this order:

1. Counts: images found, discarded as content, extracted, flagged.
2. The reconciliation table: unchanged / moved / added / removed / edited.
3. Every `needs_review` item, with its reason.
4. Whether the duplicate audit is clean, and which clusters are not.
5. **Whether existing results remain comparable.** If anything was `EDITED` or
   `REMOVED`, say plainly which reports are now partially stale.

## What never happens without a person

- Reassigning a document's `N`.
- Reusing a retired id.
- Resolving a `needs_review` item by reasoning about insurance rather than
  reading the marker.
- Deleting a question because it looks like a duplicate. The audit proposes;
  a P&C-literate reviewer disposes.
