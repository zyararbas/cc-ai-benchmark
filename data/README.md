# Task suites

One JSON file per suite, loaded by `cc_ai_benchmark.storage.load_suite`. The file
name (without `.json`) is the reference used on the command line:
`cc-ai-benchmark run example`.

## Schema

```json
{
  "name": "example",
  "version": "1.0.0",
  "description": "Optional one-line summary.",
  "tasks": [
    {
      "id": "unique-within-the-suite",
      "prompt": "The input handed to the runner.",
      "expected": "The reference answer, or null when a scorer needs no reference.",
      "tags": ["optional", "free-form"],
      "metadata": { "difficulty": "easy" }
    }
  ]
}
```

`name`, `version`, and `tasks` are required; each task requires `id` and `prompt`.
Unknown keys are rejected rather than ignored, so a typo fails loudly at load time.

## Rules for this directory

- **Task ids are stable.** Changing what an id means breaks comparison against
  every report already published. Add a new task instead.
- **Bump `version` when the task set changes.** Reports record the version they
  ran against; two runs are only comparable at the same version.
- **Keep suites public-safe.** No customer data, no credentials, nothing that
  cannot be published — this repo is public.

Validate before committing:

```bash
python -m cc_ai_benchmark validate
```
