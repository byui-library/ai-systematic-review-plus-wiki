# Plan 2: Full-text PDFs and the Obsidian Wiki — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **How this plan differs from Plan 1.** Plan 1 contained every line of code. In practice the code was then written a second time during execution and changed during review, so the copy in the plan went stale. This plan fixes the decisions that matter: file layout, public interfaces, file formats, behaviour, and the exact assertions each test must make. Each task is still done test-first: write the listed tests, watch them fail, implement, watch them pass, commit.

**Goal:** For every included paper, get the full text, scaffold an Obsidian vault with one page per paper, let an AI agent fill those pages through playbooks, and build the extraction tables, appraisal table, figures, and knowledge graph from what the agent wrote.

**Architecture:** This follows the Plan 1 rule: Python does the file I/O and the agent does the judgment. Python creates the vault and every page skeleton. Python hands the agent one paper at a time, with its PDF text, through `data/wiki_paper.json`. The agent writes prose into the wiki pages and fills structured YAML front-matter. Python then validates the front-matter (`wiki --check`) and derives every table, figure, and graph from it. Nothing the agent writes is parsed from prose.

**Tech stack:**
- Python ≥ 3.11 standard library: `urllib` for HTTP and `difflib` for fuzzy titles
- PyYAML
- PyMuPDF (`fitz`), the only new dependency, used for PDF text
- openpyxl and matplotlib (already present)
- vis-network 9.1.9 from unpkg, loaded by the generated graph HTML

**Spec:** `docs/superpowers/specs/2026-11-03-ai-systematic-review-plus-wiki-design.md` §4 (PDFs, Wiki), §5, §8

**Builds on:** Plan 1 (`review/` package, `run.py`, `state.py` stage tracking, prompt and paper fingerprints).

---

## Decisions fixed by this plan

| Topic | Decision |
| --- | --- |
| Which papers | Included tiers only. A paper counts if it has a current decision, using the same rule as `report.collect`. If any candidate is still unclassified, `pdfs` and `wiki` refuse with a plain-English message. |
| Stable numbering | `data/paper_numbers.json` assigns each paper a number within its tier once, and keeps it. New papers get the next free number. A paper that changes tier gets a new number in its new tier. Filenames therefore never change under the researcher's feet. |
| PDF filename | `T{tier}-{nn:02d} - {title, sanitised, 80 chars max} ({year}).pdf` in `wiki/raw/tier{tier}/` |
| Page filename | `wiki/papers/tier{tier}/{nn:02d}-{first-author-surname}-{year}.md` (ASCII slug) |
| PDF strategies | 1. LibKey `fullTextFile`, then `fullTextLink` (only if `pdfs.libkey` is set and `LIBKEY_LIBRARY_ID` and `LIBKEY_API_TOKEN` are in `.env`). 2. Unpaywall `best_oa_location.url_for_pdf` (only if `pdfs.unpaywall` is set and `UNPAYWALL_EMAIL` is in `.env`). 3. Otherwise the paper is listed in `data/manual_downloads.csv`. A download counts only if it starts with `%PDF` and is ≥ 10 KB. Existing valid files are skipped. Every paper's outcome is recorded in `data/pdf_log.json`. |
| Secrets | `.env` in the project root, which is git-ignored. Values in the process environment take precedence over `.env`. Nobody's email address is hard-coded. |
| HTTP | stdlib `urllib` with a generic User-Agent (`ai-systematic-review-plus-wiki`). There is one retry with backoff for timeouts and 5xx responses. A 401 from LibKey stops the run with a credentials message. The polite delay between papers is configurable (default 1 s, 0 in tests). |
| Manual drops | `pdfs --match` scans `wiki/raw/` (including an `inbox/` subfolder) for PDFs whose names don't match the expected filename. Each file is matched first by a DOI found in its first 2 pages, then by fuzzy title (difflib ratio ≥ 0.85 against the filename stem and the first-page text). Matched files are renamed into place; unmatched files are listed and left alone. |
| Paper depth | `wiki.deep_tiers` (default: the first included tier). Deep pages are summarised to the researcher and written only after they confirm, ending with `status: confirmed`. Standard pages are written directly with every quantitative value tagged `[VERIFY]`, ending with `status: draft`. |
| Page statuses | `stub` → `draft` / `confirmed` / `unreadable`. A paper counts as done when it is `confirmed` (any tier), `draft` (standard tiers only), or `unreadable`. |
| Structured data | The YAML front-matter is the only data Python reads: `id, title, year, tier, number, depth, status, pdf, extraction{column: value}, appraisal{tool, items{key: answer}, overall}`. `NR` means "not reported". |
| Generated pages | These are pipeline-owned and fully regenerated on every scaffold run, each with a banner saying so: `index.md`, `methods-review/search-and-screening.md`, `methods-review/data-extraction.md`, `methods-review/appraisal-checklist.md`, `tables/*`, `concepts/<axis>/index.md`, `wiki/AGENTS.md`, `wiki/CLAUDE.md`. The researcher's own notes go in `methods-review/notes.md`, which is created once and never overwritten. |
| Agent-owned pages | Paper pages after the stub stage, `concepts/<axis>/*.md` except `index.md`, `debates/*.md`, `sub-reviews/**`, and `log.md`, which the agent appends to and Python also appends scaffold entries to. Re-running the scaffold never overwrites a non-stub paper page. It only refreshes the PDF link and Sources line on pages that are still stubs. |
| Appraisal tools | Built in: `AXIS` (20 items), `JBI` (analytical cross-sectional, 8 items), `CASP` (cohort, 12 items), and `RoB2` (5 domains plus overall). Item wording is paraphrased, and the checklist page tells researchers to cite the official instrument. Allowed answers are per tool. `none` skips appraisal. |
| Graph | Built from `[[wikilinks]]` across the vault. A link resolves by exact vault path, otherwise by a unique filename stem (Obsidian's shortest-path form). The output is a standalone `tables/knowledge-graph.html` (data inline; vis-network pinned to 9.1.9 from unpkg) plus a `tables/knowledge-graph.md` summary listing the most-connected pages. |
| Figures | Bar charts of papers per tier, year, and source, plus the top 10 values of each extraction column (values split on `;`, normalised to lower case, `NR` and blanks skipped). Written to `wiki/figures/*.png` and shown on `tables/figures.md`. If `data/prisma.png` exists, it is copied in and shown too. |

---

## File map

| File | Responsibility |
| --- | --- |
| `review/config.py` (modify) | `wiki: {deep_tiers}` default and validation; new `Paths`: `wiki`, `raw`, `inbox`, `env`, `pdf_log`, `manual_downloads`, `paper_numbers`, `wiki_task` |
| `review/env.py` | `load_env(paths) -> dict[str, str]` (a minimal `.env` parser) |
| `review/papers.py` | `Paper` dataclass; `included_papers(paths, project)`, which assigns stable numbers and derives slugs, filenames, and paths |
| `review/pdftext.py` | `pdf_text(path, max_pages, max_chars) -> str`; `find_doi(text) -> str or None` |
| `review/pdfs.py` | `download_all(paths, project, delay)`, `match_dropped(paths, project)`, and the HTTP helpers `fetch_json` and `fetch_pdf` (monkeypatched in tests) |
| `review/appraisal.py` | `CHECKLISTS: {tool: {'items': [(key, question)], 'answers': [...], 'overall': [...]}}` |
| `review/wiki.py` | Page I/O (`read_page`, `write_page`), `scaffold`, `next_paper`, `check`, `build_index`, `append_log` |
| `review/vault_text.py` | Text of the generated pages: vault instructions, the methods-review pages, and the appraisal checklist page |
| `review/tables.py` | `build_tables(paths, project)` writes `tables/tier{N}-extraction.md` and `tables/appraisal.md` |
| `review/figures.py` | `build_figures(paths, project)` |
| `review/graph.py` | `build_graph(paths)` |
| `run.py` (modify) | New commands: `pdfs [--match]`, `wiki --scaffold / --next-paper / --check / --tables / --index`, `figures`, `graph` |
| `prompts/03-summarize-papers.md` | Agent loop: next paper → read → (deep: confirm with researcher) → fill page → check |
| `prompts/04-concepts-debates.md` | Concept pages per axis and debate pages for contradictions |
| `prompts/05-quality-appraisal.md` | Fill `appraisal.items` and `overall` per paper using the checklist page |
| `prompts/06-sub-review.md` | Optional focused sub-review under `sub-reviews/<name>/` |
| `review/validate.py` (modify) | Simplify `_save_sample` (deferred from the Copilot review on PR #1) |
| `.env.example`, `setup/requirements.txt`, `CLAUDE.md` (modify) | Docs and dependencies |
| `tests/test_env.py`, `test_papers.py`, `test_pdfs.py`, `test_wiki.py`, `test_tables.py`, `test_figures.py`, `test_graph.py`, `test_cli_wiki.py`, `test_playbooks.py` | Tests. PDFs are generated with PyMuPDF inside the tests, so no binary fixtures are committed. |

---

### Task 1: Config, paths, `.env`, and the included-paper list

- [ ] **Tests** (`tests/test_env.py`, `tests/test_papers.py`)
  - `load_env`:
    - parses `KEY=value`, `KEY="quoted"`, and `export KEY=v`
    - ignores comments and blank lines
    - lets the process environment override `.env`
    - returns `{}` when there is no `.env`
  - `project.yaml`:
    - `wiki.deep_tiers` defaults to `[first included tier]`
    - an id that is not an included tier is a config problem
  - `included_papers`:
    - refuses with "Finish classifying" while any candidate is unclassified
    - on the classified fixture, returns tier-1 and tier-2 papers numbered 1 within each tier, with:
      - slug `01-doe-2021`
      - PDF name `T1-01 - Principal component analysis of workload metrics in collegiate soccer players (2021).pdf` (sanitised, at most 80 characters of title)
      - page path `papers/tier1/01-doe-2021.md`
    - numbering is stable: re-running keeps numbers, and a newly included paper gets the next number while existing ones keep theirs
    - a paper whose tier changes gets a new number in its new tier
    - a missing author gives slug `nn-unknown-year`, and a missing year gives `nd`
- [ ] **Implement**:
  - `config.py`: `DEFAULTS['wiki'] = {'deep_tiers': None}`; the validation rule; `Project.deep_tiers`; the new `Paths` attributes
  - `env.py`
  - `papers.py`, which uses `report.collect(paths, project)['included']`
- [ ] Run the full suite, then commit: `Add .env loading and stable numbering for included papers`

### Task 2: PDF text extraction and downloading

- [ ] **Tests** (`tests/test_pdfs.py`). A `make_pdf(path, text)` helper builds real PDFs with PyMuPDF, padded past 10 KB where needed.
  - `pdf_text` returns the page text; it returns `''` for a corrupt file or a file that isn't a PDF.
  - `find_doi` finds `10.1000/example.001` in text, stripping trailing punctuation.
  - `download_all` with `fetch_json` and `fetch_pdf` monkeypatched:
    - LibKey `fullTextFile` is used first, when credentials are present
    - it falls back to `fullTextLink`, then to Unpaywall
    - with no credentials, it goes straight to Unpaywall
    - with neither available, the paper is listed in `manual_downloads.csv` with `https://doi.org/<doi>` and the expected `save_as` path
    - a paper with no DOI is logged as `no_doi` and listed for manual download, searchable by title
    - an existing valid file is skipped (`exists`) without any network call
    - an existing file that is not a PDF is replaced
    - `pdf_log.json` records the source and every attempt
    - `.env` email is used in the Unpaywall URL
    - a LibKey 401 raises `PipelineError` mentioning `LIBKEY_API_TOKEN`
  - `fetch_pdf` rejects HTML and anything under 10 KB, and leaves no partial file behind. This is tested with a tiny local `http.server` on localhost.
- [ ] **Implement** `pdftext.py` and `pdfs.py` (downloading only). Writes are atomic: download to `*.part`, validate, then rename.
- [ ] Add `pymupdf>=1.24` to `setup/requirements.txt`. Run the suite, then commit: `Add full-text PDF download via LibKey and Unpaywall with a manual fallback`

### Task 3: Matching manually downloaded PDFs

- [ ] **Tests** (in `tests/test_pdfs.py`):
  - A PDF dropped in `wiki/raw/inbox/` whose first page contains the paper's DOI is renamed to its expected path.
  - A file named after the paper title (`Redundancy in GPS workload variables.pdf`) with no DOI matches by fuzzy title.
  - A PDF matching nothing stays put and is reported as unmatched.
  - A drop for a paper that already has its PDF is reported as a duplicate and left alone.
  - Files already at their expected path are not touched.
  - `manual_downloads.csv` is rewritten without the newly matched papers.
- [ ] **Implement** `pdfs.match_dropped`. Run the suite, then commit: `Match manually downloaded PDFs to papers by DOI or title`

### Task 4: Appraisal checklists, page I/O, and the vault scaffold

- [ ] **Tests** (`tests/test_wiki.py`):
  - `read_page` and `write_page` round-trip front-matter and body. Non-ASCII text survives. A page without front-matter reads as `({}, body)`.
  - `scaffold` on the classified fixture creates:
    - `papers/tier1/`, `papers/tier2/`
    - `concepts/{methods,metrics,sports}/index.md`
    - `debates/`, `tables/`, `figures/`, `sub-reviews/`, `raw/tier1/`, `raw/inbox/`
    - `index.md`, `log.md`, `AGENTS.md`, `CLAUDE.md`, and the four methods-review pages
  - Each stub has:
    - front-matter `status: stub`
    - `depth: deep` for tier 1 and `standard` for tier 2
    - `extraction` with every configured column set to `null`
    - `appraisal.items` with every AXIS key (`q1`…`q20`) set to `null`
    - body sections for every extraction column, each containing the marker `<!-- fill -->`
    - a Sources line with `[Open PDF](../../raw/tier1/...)` when the PDF exists, otherwise `No PDF yet: summarise from the abstract`
  - `search-and-screening.md` contains the real counts from `stats.json`, the tier labels, the AI tool and model from the checkpoint, and the validation kappa when scored.
  - `AGENTS.md` and `CLAUDE.md` have identical bodies, which include the research question, the deep tiers, and the extraction columns.
  - Re-running `scaffold`:
    - never overwrites a page whose status is not `stub`
    - refreshes the PDF link on stubs after a PDF arrives
    - leaves `methods-review/notes.md` alone after its first creation
    - reports papers that are no longer included as `orphaned` without deleting them
    - appends one scaffold entry to `log.md`
  - `appraisal: {tool: none}` produces stubs without appraisal items and no checklist page.
- [ ] **Implement** `appraisal.py`, `vault_text.py`, and `wiki.read_page`, `write_page`, `scaffold`, `build_index`, `append_log`. Run the suite, then commit: `Scaffold the Obsidian vault from the screening results`

### Task 5: The paper hand-out and `wiki --check`

- [ ] **Tests** (in `tests/test_wiki.py`):
  - `next_paper`:
    - returns deep-tier stubs before standard ones, in number order
    - writes `data/wiki_paper.json` with `id, page, depth, pdf, source ('pdf' | 'abstract'), text, metadata, extraction_columns, appraisal_tool, playbook, remaining`
    - uses PDF text when a readable PDF exists, and the abstract otherwise
    - returns `None` once every page is past `stub`
  - `check`:
    - counts pages by status
    - a deep page in `draft` is reported as "waiting for the researcher to confirm"
    - a `draft` or `confirmed` page with any `null` extraction value is a problem, while `NR` is allowed
    - so is a leftover `<!-- fill -->` marker
    - so is an appraisal answer outside the tool's allowed answers
    - so are a missing extraction key, an unknown status, or front-matter that won't parse
    - when everything is done with no problems, it marks the `wiki` stage done; otherwise it clears it
    - `unreadable` pages count as done and are listed separately
- [ ] **Implement** `wiki.next_paper` and `wiki.check`. Run the suite, then commit: `Hand out papers to the agent and validate filled pages`

### Task 6: Extraction and appraisal tables

- [ ] **Tests** (`tests/test_tables.py`). Start from scaffolded stubs, then fill two pages' front-matter in the test:
  - `tables/tier1-extraction.md` has columns `# | Study (Year) | <each extraction column>`.
    - The Study cell is a `[[papers/tier1/01-doe-2021|Doe 2021]]` link.
    - Pipes inside values are escaped.
    - Stubs appear with `…`.
  - `tables/appraisal.md` has one row per paper with one column per checklist item plus `Overall`, and a legend explaining the answer codes.
  - With `appraisal: none`, no appraisal table is written and any old one is removed.
  - Each table starts with the generated-page banner.
- [ ] **Implement** `tables.py`. Run the suite, then commit: `Build extraction and appraisal tables from page front-matter`

### Task 7: Figures

- [ ] **Tests** (`tests/test_figures.py`):
  - `build_figures` writes `figures/papers-per-tier.png`, `papers-per-year.png`, `papers-per-source.png`, and one `top-<column-slug>.png` per extraction column that has values; each file is larger than 1 KB.
  - Columns with only `null` or `NR` produce no chart.
  - `tables/figures.md` embeds every chart that was written.
  - `prisma.png` is copied in and embedded only when it exists in `data/`.
  - Value counting splits on `;`, ignores case, and strips whitespace (tested through a pure helper, `count_values`).
- [ ] **Implement** `figures.py` with matplotlib's Agg backend. Run the suite, then commit: `Add frequency figures for tiers, years, sources, and extraction values`

### Task 8: Knowledge graph

- [ ] **Tests** (`tests/test_graph.py`):
  - `parse_links` handles `[[a/b]]`, `[[a/b|Label]]`, `[[a/b.md]]`, and the escaped pipe `[[a/b\|L]]` used inside tables.
  - Resolving links:
    - exact vault paths win
    - a bare stem resolves when it is unique
    - an ambiguous or missing stem is counted as unresolved
  - `build_graph`:
    - writes `tables/knowledge-graph.html` containing the pinned vis-network script tag and inline JSON with nodes grouped by top folder (`papers`, `concepts`, `debates`, …)
    - leaves out `raw/` and the generated `tables/` pages from the nodes
    - writes `tables/knowledge-graph.md` listing the 10 most-connected pages and the number of unresolved links
- [ ] **Implement** `graph.py`. Run the suite, then commit: `Generate an interactive knowledge graph from wiki links`

### Task 9: CLI commands and an end-to-end wiki test

- [ ] **Tests** (`tests/test_cli_wiki.py`). These run through `run.main`, continuing the core pipeline from Plan 1's end-to-end test:
  - `pdfs` with the network monkeypatched to fail prints how many papers are on the manual list and where the CSV is, then exits 0.
  - `pdfs --match` after placing a PDF in `wiki/raw/inbox/` reports 1 matched.
  - `wiki --scaffold` prints the number of stubs created.
  - The test then loops `wiki --next-paper`, filling each page as an agent would (front-matter plus prose, with `confirmed` for tier 1 and `draft` for tier 2).
  - `wiki --check` exits 0, and `status` then points to `py run.py site`.
  - `wiki --tables`, `figures`, and `graph` each exit 0 and write their files.
  - Running `pdfs` before classification is finished exits 1 with "Finish classifying".
- [ ] **Implement** the `run.py` subcommands. `state.NEXT['wiki']` is changed to say "Ask your AI assistant to 'build the wiki' (it follows prompts/03–05)". Mark stages done:
  - `pdfs` is done once a run completes, even if some papers are on the manual list
  - `wiki` is done when `check` passes
- [ ] Run the suite, then commit: `Add pdfs, wiki, figures, and graph commands`

### Task 10: Agent playbooks 03–06

- [ ] **Tests** (`tests/test_playbooks.py`):
  - Every `py run.py …` command quoted in any `prompts/*.md` file parses with `run.build_parser()`, so playbooks can't drift from the CLI.
  - Each playbook names the files it reads and writes.
  - 03 states both the deep (confirm first) and standard (`[VERIFY]`) workflows and the `unreadable` rule.
  - 05 points to `wiki/methods-review/appraisal-checklist.md`.
  - None of them tells the agent to edit `data/*.json`.
- [ ] **Write the playbooks.** All four follow 02's structure (Goal / Loop / Rules) and are written for non-coders' agents.
  - **03:**
    - `wiki --next-paper`, then read `data/wiki_paper.json` and the page
    - deep: present a summary (sample, methods, every extraction column, key results, limitations) and wait for the researcher to confirm or correct it, then write the page and set `status: confirmed`
    - standard: write the page with `[VERIFY]` on every number and set `status: draft`
    - unreadable PDF and no usable abstract: set `status: unreadable` and invent nothing
    - every claim cites `(source: <pdf filename or "abstract">)`
    - append to `log.md`, run `wiki --check`, then loop
  - **04:**
    - after all papers, run `wiki --index`, then read the paper pages per concept axis
    - create `concepts/<axis>/<concept>.md` using the concept page format, with `[[links]]` to papers
    - create `debates/<slug>.md` when papers contradict each other, and link it from both papers' Contradictions sections
    - finish with `wiki --index`
  - **05:**
    - for each page, answer every checklist item with an allowed answer and set `overall`
    - justify any "no" or "unclear" answer in the page's Appraisal section
    - then run `wiki --check` and `wiki --tables`
  - **06:**
    - the researcher names a subset rule (for example "only soccer papers")
    - the agent lists the matching papers and confirms the list with the researcher
    - it creates `sub-reviews/<name>/index.md` (its own PICOS, a paper list with links, and a synthesis) plus optional concept pages inside the folder
    - finish with `wiki --index`
- [ ] Run the suite, then commit: `Add wiki playbooks for summaries, concepts, appraisal, and sub-reviews`

### Task 11: Simplify `_save_sample`

- [ ] **Tests:** Copilot's existing tests for `_save_sample` must still pass. Add one more:
  - When `validation.xlsx` can't be replaced (`os.replace` monkeypatched to raise `PermissionError`), the old workbook and the old `validation_sample.json` are both unchanged, and the error says to close Excel.
- [ ] **Implement:**
  - Write the workbook and sample JSON to temp files in `data/`.
  - Replace the workbook first, because a locked Excel file is the realistic failure.
  - Then replace the JSON.
  - If replacing the JSON fails, delete the new workbook so the pair can't disagree, and raise.
  - Remove the backup-copy machinery.
- [ ] Run the suite, then commit: `Simplify the validation sample write`

### Task 12: Docs, environment example, CI, smoke test

- [ ] Add `.env.example` (`LIBKEY_LIBRARY_ID=`, `LIBKEY_API_TOKEN=`, `UNPAYWALL_EMAIL=`, each with a comment on how to obtain it). Confirm `.gitignore` covers `.env`, `wiki/raw/`, and `*.pdf`.
- [ ] `CLAUDE.md`:
  - add the new modules to the module map
  - mark Plan 2 "Done" in the status table
  - list the new commands
  - state the rule on generated pages versus agent-owned pages
- [ ] Smoke test on the reference review's real exports in the scratch workspace, using about 5 included papers with canned decisions:
  - `pdfs` with the real Unpaywall API (email taken from the developer's `.env`, never committed)
  - then `scaffold`, `next-paper`, `check`, `tables`, `figures`, and `graph`
  - open the vault in Obsidian and check that links resolve
- [ ] Push the branch and open the PR. CI on Windows and Ubuntu must be green.
