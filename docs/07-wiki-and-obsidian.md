# 7. The wiki

The wiki is a folder of linked Markdown pages (`wiki/`) that opens in [Obsidian](https://obsidian.md/) and becomes your website.

## Build it

```bash
py run.py wiki --scaffold
```

This creates:
- a page for every included paper (`wiki/papers/tier1/01-smith-2020.md`, …)
- folders for concepts, debates, and sub-reviews
- extraction tables
- methods pages filled in from your real screening numbers
- `index.md`, the home page

In Obsidian choose **Open folder as vault** and pick `wiki/`.

## Let the AI write the paper pages

Ask your assistant to *"summarise the papers"*. It follows `prompts/03-summarize-papers.md`, one paper at a time (`py run.py wiki --next-paper`):

- **Deep tiers** (by default your first included tier): it summarises the paper to you in the chat and **waits for your confirmation or corrections** before writing the page.
- **Other included tiers:** it writes the page directly and tags every number with **`[VERIFY]`**. Search the vault for `[VERIFY]` later and check each one against the PDF.
- If you set an appraisal checklist, it answers it for each paper at the same time.
- Unreadable PDFs are marked as such. Nothing is made up.

After each page it runs `py run.py wiki --check`, which validates every paper page. When the check passes for every page, the wiki stage is complete.

## The rest of the wiki

| Ask for | What you get |
| --- | --- |
| *"Write the concept and debate pages"* | A page per recurring concept in each concept folder, and a page for each disagreement between papers (`prompts/04-concepts-debates.md`) |
| *"Appraise the papers"* | Checklist answers, re-done or checked (`prompts/05-quality-appraisal.md`) |
| *"A sub-review on just the soccer papers"* | A focused section under `sub-reviews/` (`prompts/06-sub-review.md`) |
| *"Rebuild the tables and figures"* | `py run.py wiki --tables`, `py run.py figures`, `py run.py graph` |

## Your extracted data as a spreadsheet

Every time the tables are rebuilt (`py run.py wiki --tables`), the extracted data is also written to **`data/extraction.xlsx`**. It has an *All* sheet plus one sheet per included tier, with one row per paper and one column per extraction field, plus the appraisal rating. The same data is written to `data/extraction.csv`. Use these for your own analysis in Excel, SPSS, R, or Python. Papers not yet written appear with status `stub` and empty values.

## What you may edit

You may edit anything you like in paper, concept, and debate pages. Keep the block between the `---` lines at the top of paper pages valid, because the tables are built from it. Your own notes go in `methods-review/notes.md`.

Pages marked *Generated* (the index, the tables, and the search-and-screening page) are rebuilt automatically, so edits there are lost.

Next: [8. The website](08-website.md)
