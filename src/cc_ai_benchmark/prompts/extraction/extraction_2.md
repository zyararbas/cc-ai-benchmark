You are extracting exam questions from an image into a strict JSON Lines
format, to be used as ground truth for testing other AI models. Accuracy
and verbatim fidelity matter more than fluency.

For EACH question block in the image:

1. QUESTION — copy the stem text verbatim (normalize whitespace only; no
   paraphrasing, no spelling/grammar fixes).

2. CHOICES — every lettered option, in the order shown, as a letter→text
   map. Strip the leading "A)" style prefix from the text itself.

3. ANSWER — determined ONLY by what is visually marked, never by your own
   knowledge of the subject. Two layouts appear in these documents; apply
   them in this order of precedence:

   a. GRADED layout — green checkmarks and/or red X icons are present
      anywhere in the question block. These are authoritative:
      - Green checkmark = correct
      - Red X = incorrect
      - Exactly one green check: "answer" is that letter (e.g. "A").
      - More than one green check: "answer" is an array (e.g. ["A", "C"]).
      - A filled/selected radio button in this layout is the test-taker's
        SELECTION, not the key. It is frequently wrong. When a filled radio
        and a green checkmark disagree, the green checkmark wins and the
        radio is ignored. Bold text on an option likewise marks the
        selection, not the answer.

   b. SELECTION-ONLY layout — no green checkmark and no red X appears
      anywhere in the question block, and exactly one option is marked by a
      filled/highlighted radio button (a solid dot, often blue, sometimes
      with the whole row tinted). Treat that selection as the answer.

   c. If neither a checkmark nor a filled radio is present, or the marking
      is ambiguous or illegible, do not guess — set "answer" to null, add
      "needs_review": true and a one-line "review_note".

   Never mix the two: if any green check or red X is present, the layout is
   GRADED and rule (a) applies even if a radio is also filled.

4. EXPLANATION — the text under an "Explanation" header for that question,
   verbatim. If none appears before the next question starts, use null.

Output ONE JSON object per line (JSON Lines), no array wrapper, no markdown
fences, no commentary, matching exactly:

{
  "id": "q_<n>",
  "question": "<verbatim stem>",
  "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "answer": "<letter, array of letters, or null>",
  "explanation": "<verbatim text or null>",
  "scope": "generic",
  "ref": "document"
}

Rules:
- Number questions sequentially (q_1, q_2, ...) in the order they appear.
- Preserve on-page choice order and lettering exactly as shown.
- Do not invent or paraphrase an explanation if none is present — use null.
  The selection-only layout usually has no Explanation section at all.
- If uncertain about a marker, flag the item rather than guessing.

Output nothing except the JSONL lines. No preamble, no summary.