# 4. Screening

Screening happens in two passes.

## Prescreen (automatic)

```bash
py run.py prescreen
```

This sets aside:
- retracted papers, editorials, letters, comments, and conference abstracts
- non-English papers
- records with neither an abstract nor keywords
- papers that contain none of your keyword groups

You can switch each filter off in `project.yaml`. Everything set aside is kept in `data/prefilter_excluded.json` and `data/prescreen_excluded.json`, so nothing is lost.

## Classify (the AI)

Ask your assistant to *"classify the papers"*. It works in batches of 50 (by default), following `prompts/02-classify.md`:

1. `py run.py classify --next-batch` hands it the next papers and the screening instructions built from your project.
2. It decides a tier, a score from 1 to 100, and a one-sentence reason for each paper.
3. `py run.py classify --save data/classify_results.json --tool "<its name>" --model "<its model>"` checks every decision and saves the batch. If anything is malformed, nothing is saved and the assistant fixes it.

Check progress at any time with `py run.py status`.

### What to watch

- **Spot-check reasons as it goes.** If the AI keeps misreading a criterion, stop it and ask the assistant to sharpen that tier's definition. It will re-screen what's affected.
- **Ambiguous papers** go to the more inclusive tier by design. Your validation step catches over-inclusion more easily than missed papers.
- **The audit log** is `data/checkpoint.json`. Every decision, every earlier version of it, the tool and model, and the date are kept there.

Next: [5. Validation and the report](05-validation.md)
