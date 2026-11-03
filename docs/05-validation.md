# 5. Validation and the report

Reviewers and editors will ask how well the AI screened. You answer that by re-screening a random sample yourself, without seeing the AI's answers.

## Draw the sample

```bash
py run.py validate --draw
```

This writes `data/validation.xlsx`: a stratified random sample (by default 10% of each tier, at least 5 per tier), with a fixed random seed so the sample can be reproduced. The AI's tiers are **not** in the file.

## Re-screen it

1. Open `data/validation.xlsx` in Excel.
2. The *Tier definitions* sheet repeats your definitions.
3. For each paper on the first sheet, read the title and abstract and type your tier number in **Your tier**.
4. Save and close the file.

Work on your own. Don't look the papers up in `data/checkpoint.json` or the report until you're done.

## Score it

```bash
py run.py validate --score
```

You get:
- **Exact tier agreement** and **Cohen's kappa**
- **Include/exclude agreement** and kappa: whether you and the AI agree on which papers belong in the review, which is usually the number journals care about
- **A list of disagreements**

Discuss the disagreements with your co-authors. If the AI was wrong in a systematic way, sharpen the tier definitions and let it re-screen.

The score also writes **`data/ai_disclosure.md`**, a draft AI-use statement filled in with your tools, dates, sample size, and kappa. Edit it to match your journal's policy.

## The report

```bash
py run.py report
```

This writes `data/Results.xlsx` with these sheets:
- **Summary:** the counts at every stage, and the validation results
- **One sheet per included tier**
- **Excluded:** with a *Consider promoting?* column marking the highest excluded tier, so you can review borderline papers

It also writes `data/included.csv` and `data/excluded.csv`, and a PRISMA flowchart (`data/prisma.png`) if you turned it on during setup.

Next: [6. Full texts](06-pdfs.md)
