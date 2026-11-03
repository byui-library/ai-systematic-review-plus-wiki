# Playbook 03: write the paper pages

**Goal:** turn every paper stub in `wiki/papers/` into a finished summary page. The researcher must be able to trust it, and the pipeline must be able to build tables from it.

**Reads:** `data/wiki_paper.json` (the paper, its full text or abstract, and the columns to extract), the stub page, and `wiki/AGENTS.md` (or `wiki/CLAUDE.md`).
**Writes:** the paper page in `wiki/papers/tier<N>/`, and `wiki/log.md` (append only).

## Loop

1. Run `py run.py wiki --next-paper`. If it says every paper page is written, go to step 8.
2. Open `data/wiki_paper.json`. It gives you:
   - `page`: the page to write
   - `depth`: deep or standard
   - `source`: `pdf` (the full text) or `abstract`
   - `text`: the whole paper when it fits in one part, otherwise empty
   - `parts`: the full text split into files with page ranges, plus `pages` (the PDF's page count)
   - `tables`: how many tables were found, and `note`: anything you must tell the researcher
   - `metadata`, `extraction_columns` (what to record, with hints), and `appraisal_checklist` (if appraisal is configured)
3. **Read the whole paper.**
   - If `text` is empty, open every file in `parts`, in order. Together they are the entire paper, with nothing cut out. Each page starts with `--- page N ---`, so you can cite page numbers.
   - Tables found in the PDF are repeated after their page as a **Markdown table** (`Table 1 on page 6: …`). Take numbers from these Markdown tables rather than from the run-together page text, because they keep each value in its row and column.
   - If `scanned` is true, the PDF is an image without a text layer. Work from the abstract, and tell the researcher that adding a text layer (OCR) would let you read the full paper (see `docs/06-pdfs.md`).
   - If `complete` is false, the PDF has more than 400 pages. Say which pages you read.
4. Then decide based on `depth`:
   - **Deep:** present a structured summary in the chat and **wait for the researcher** to confirm or correct it. Cover the sample, the design, every extraction column, the key results with numbers, the limitations, and (if appraisal is configured) your appraisal answers. Write nothing until they reply. Then write the page with their corrections and set `status: confirmed`.
   - **Standard:** write the page directly. Put `[VERIFY]` after every quantitative value (n, means, percentages, loadings, p-values) so the researcher can audit it. Set `status: draft`.
   - **Unreadable:** if the text is empty or garbled and there is no usable abstract, set `status: unreadable`. Replace each `<!-- fill … -->` marker with "Not available: no readable full text." Invent nothing.
5. Fill the page:
   - In the front-matter (between the `---` lines), set every `extraction` value. Write `NR` when the paper does not report it. Separate several values with `; `, for example `PCA; factor analysis`.
   - Replace every `<!-- fill … -->` marker in the text.
   - If appraisal is configured, answer the checklist now, following step 2 of playbook 05 (`wiki --check` validates appraisal values too). The paper is already open, so this is the cheapest moment.
   - End every factual claim with `(source: <pdf filename>)` or `(source: abstract)`.
6. Append a log entry to `wiki/log.md`, using the format in `wiki/AGENTS.md`.
7. Run `py run.py wiki --check`. Fix any problem it reports for the page you just wrote, then go back to step 1.
8. When all pages are written, run `py run.py wiki --check` and `py run.py wiki --tables`. Tell the researcher:
   - how many pages are confirmed, draft, and unreadable
   - how many `[VERIFY]` tags they need to audit

## Rules

- Never edit `data/*.json` files. Never edit generated pages: `wiki/index.md`, `wiki/tables/`, `wiki/methods-review/search-and-screening.md`, `data-extraction.md`, and `appraisal-checklist.md`.
- Report only what the paper says. Mark your own interpretation as such ("This suggests…").
- If this paper contradicts a page you have already written, note it in both pages' *Contradictions* sections. Playbook 04 turns these notes into debate pages.
- Keep each page's front-matter valid YAML. If a value contains a colon, wrap it in quotes.
