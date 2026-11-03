# Full-Text Extraction Improvements: Implementation Plan

> Follow-up to Plan 2. Same method as Plans 2 and 3: the decisions and the test assertions are fixed here, and the code is written test-first.

**Why.** On the reference review's 117 real PDFs, the hand-out to the AI (`wiki --next-paper`) was capped at 30 pages and 80,000 characters. That silently cut off 19 papers (16%), the long reviews and a 274-page thesis. PDF tables also came out as jumbled text, which is where quantitative extraction goes wrong. And the extracted data existed only as Markdown tables in the wiki, with no spreadsheet for analysis.

## Decisions

| Topic | Decision |
| --- | --- |
| Whole papers | `pdftext.read_pages(path, max_pages=400)` returns every page's text plus its tables. `wiki --next-paper` writes the paper to `data/wiki_paper/part-NN.txt` files of about 60,000 characters each. Parts always break between pages, and every page starts with a `--- page N ---` marker. `data/wiki_paper.json` lists the parts with their page ranges, and also gives `pages` and `complete` (false only if a PDF has more than 400 pages). When the paper fits in one part, which is most papers, its text is also inline in `text`, as before. |
| Tables | `page.find_tables()` (PyMuPDF). Each table with at least 2 rows is added after its page's text as `Table N on page P` followed by Markdown. Table detection failures are ignored, and the plain text is still there. |
| Scanned PDFs | A PDF with pages but fewer than 20 text characters per page on average (a cover page added by a database is not enough to count as text) is flagged `scanned: true`. The task falls back to the abstract and includes a note. OCR is not built in, because it would need Tesseract on every computer. `docs/06-pdfs.md` explains how to add a text layer (for example Acrobat's *Recognize Text*) and re-run. |
| Spreadsheet | `wiki --tables` also writes `data/extraction.xlsx` (sheet *All* plus one sheet per included tier) and `data/extraction.csv`. Columns: Tier, #, Study, Title, Year, DOI, Status, then each extraction column, then Appraisal overall. Stub rows are listed with empty values. |
| Playbook | `prompts/03-summarize-papers.md` tells the agent to read every part in order, to take numbers from the Markdown tables, and what to do with a scanned PDF. |
| Git | Ignore `data/wiki_paper/` (scratch). |

## Tests

- `read_pages` returns all pages of a 40-page PDF. A ruled 3×3 table comes back as Markdown, with its cell values in table rows. A blank-page PDF is reported as scanned. A non-PDF returns `None`.
- A 40-page paper of about 3,000 characters per page is handed out in at least 2 parts that cover pages 1–40 with no gaps. `text` is `None`, `pages == 40`, `complete` is true, and running `next-paper` again replaces the old part files. A short paper keeps its inline `text`.
- A scanned PDF gives `source: abstract`, `scanned: true`, and a note.
- After `wiki --tables`, the extraction spreadsheet has the expected sheets, headers, and the filled values for a written page. The CSV has the same header.
- Playbook 03 mentions `parts`, tables, and scanned PDFs.
