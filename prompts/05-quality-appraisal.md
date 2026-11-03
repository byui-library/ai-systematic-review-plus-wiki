# Playbook 05: quality appraisal

**Goal:** appraise every included paper with the checklist chosen in `project.yaml`, record the answers where the pipeline can read them, and justify each judgment in the page text.

**Reads:** `wiki/methods-review/appraisal-checklist.md` (items, allowed answers, and overall ratings), the paper pages, and their PDFs in `wiki/raw/`.
**Writes:** the `appraisal` front-matter and the *Appraisal* section of each paper page, and `wiki/log.md` (append only).

## Loop

1. Open `wiki/methods-review/appraisal-checklist.md`. If it does not exist, appraisal is switched off (`appraisal: {tool: none}`). Stop and tell the researcher.
2. Work through the paper pages in `wiki/papers/`, deepest tier first. For each page:
   1. Read the paper. Use the PDF where there is one; otherwise use the page and the abstract.
   2. In the front-matter, set every key under `appraisal.items` to one of the allowed answers, exactly as written on the checklist page.
   3. Set `appraisal.overall` to one of the allowed overall ratings.
   4. In the page's *Appraisal* section, explain every answer that is not favourable (and any `unclear`) in one sentence each, citing `(source: <pdf filename>)`.
   5. For deep-tier papers, show the researcher your answers and wait for confirmation before saving.
3. After every 10 papers, run `py run.py wiki --check` and fix any appraisal problems it lists.
4. When all papers are appraised, run `py run.py wiki --tables` to rebuild `wiki/tables/appraisal.md`. Then tell the researcher how many papers were rated in each overall category.
5. Append a log entry to `wiki/log.md`.

## Rules

- Never edit `data/*.json` files or `wiki/tables/`; the appraisal table is built from the front-matter.
- Judge from what the paper reports. If something is not reported, the answer is usually `no` or `unclear`, not `yes`.
- Do not change `status` while appraising, except to fix a problem that `wiki --check` reports.
