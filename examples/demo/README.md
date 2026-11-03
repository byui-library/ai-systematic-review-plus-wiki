# Demo review

A small slice (44 records, 26 unique papers) of a real sports-science search across PubMed, Web of Science, and SPORTDiscus, with ready-made AI decisions, so you can try every stage of the template in a few minutes. No AI subscription is needed for the demo.

Install it from the repository folder:

```bash
py run.py demo
```

That copies this folder to `demo-workspace/`. Every command below takes `--root demo-workspace`, so your own review is never touched. On macOS or Linux, type `python3` instead of `py`.

| Step | Command | What you will see |
| --- | --- | --- |
| 1. Import | `py run.py --root demo-workspace import` | 44 records, 26 unique after 18 duplicates are merged |
| 2. Prescreen | `py run.py --root demo-workspace prescreen` | 3 removed by filters, 3 by keywords, 20 candidates |
| 3. Classify | `py run.py --root demo-workspace classify --save demo-workspace/demo/decisions.json --tool Demo --model reference-decisions` | 20 decisions saved. In a real review, your AI assistant does this with `prompts/02-classify.md` |
| 4. Validate | `py run.py --root demo-workspace validate --draw`, then `py run.py demo --fill-validation`, then `py run.py --root demo-workspace validate --score` | The sample, typed in for you with two deliberate disagreements, and the kappa |
| 5. Report | `py run.py --root demo-workspace report` | `demo-workspace/data/Results.xlsx` and a PRISMA flowchart |
| 6. Wiki | `py run.py --root demo-workspace wiki --scaffold` | 12 paper pages in `demo-workspace/wiki/`, ready for your AI assistant (`prompts/03-summarize-papers.md`) |
| 7. Website | `py run.py --root demo-workspace site` | `demo-workspace/site/index.html` |

The demo has no PDFs, because full texts are copyrighted. Paper pages say "summarise from the abstract" instead.

`decisions.json` holds the AI decisions from the original review. `human_tiers.json` holds the "human" tiers for the validation step, with two disagreements so the kappa is not a perfect 1.0.
