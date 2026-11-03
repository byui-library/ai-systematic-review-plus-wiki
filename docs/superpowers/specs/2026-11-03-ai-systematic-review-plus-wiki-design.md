# ai-systematic-review-plus-wiki — Design Spec

**Date:** 2026-11-03
**Owner:** Mathew Miles (Librarian, BYU-Idaho)
**Repository:** `byui-library/ai-systematic-review-plus-wiki` (public, GitHub template repo)
**Origin:** Generalized from the pipeline of an earlier sports-science systematic review (the reference implementation). The reference repo itself is not modified.

## 1. Goal

Give researchers on campus a cloneable template that runs the same AI-assisted systematic-review procedure on *their own* research question:

database exports → dedupe → keyword prescreen → AI tiering → human validation sample → Excel report → full-text PDFs → Obsidian wiki (papers, concepts, debates, tables, methods-review, sub-reviews) → MkDocs website.

**Audience:** non-coding faculty and graduate students. They install the tools with setup scripts and an AI coding agent (Claude Code, Codex, or similar) runs most of the commands.

### Decisions (from the design interview)

| Topic | Decision |
| --- | --- |
| Scope | Search → tiers → wiki → site. No manuscript generation. |
| Sources | Pluggable importers: PubMed NBIB, Web of Science, EBSCO (SPORTDiscus etc.), plus a generic RIS/CSV fallback |
| Project setup | Agent-led interview writes `project.yaml`; the researcher can edit it by hand afterwards |
| Tiers | 4-tier default (Core / Strong / Peripheral / Exclude). Labels, definitions, and the included flag can be edited |
| AI tool | Agent-neutral: Claude Code, Codex, or any agent that can run shell commands |
| Packaging of AI steps | Shared markdown playbooks in `prompts/`. `AGENTS.md`, `CLAUDE.md`, and `.claude/commands/` are thin wrappers around them |
| Wiki | The full reference-review wiki structure, generalized |
| Concept axes | Proposed in the setup interview, confirmed by the researcher, stored in `project.yaml` |
| Extras | Frequency figures, knowledge graph, and quality appraisal on by default. PRISMA flowchart is opt-in |
| PDFs | LibKey (if credentials are set), then Unpaywall, then a manual list plus a drop-folder matcher. Abstract is used if no PDF |
| Hosting | Local build, GitHub Pages (PDFs excluded), openEQUELLA (PDFs included) |
| Demo | ~30 anonymized records from the sports-science search |
| Integrity | Audit log on every AI decision, blind validation sample, Cohen's kappa, draft AI-use disclosure |
| Build approach | Fork and generalize the proven reference-review code into a new repo |

## 2. Architecture

**Core rule: Python does all file I/O and the agent only makes judgments.** Every AI step uses the same protocol:

1. `py run.py <step> --next-batch N` prints a batch of work as JSON, including the assembled instructions.
2. The agent reads the matching `prompts/NN-*.md` playbook and makes its judgments.
3. `py run.py <step> --save results.json` validates the results against a schema and persists them.

Progress is saved after every batch, so a dropped session loses nothing. Any agent that can run a shell command can drive the pipeline.

### Repository layout

```
ai-systematic-review-plus-wiki/
├── README.md                 non-coder quick start
├── AGENTS.md                 agent instructions (Codex etc.) → prompts/
├── CLAUDE.md                 agent instructions (Claude Code) → prompts/
├── .claude/commands/         /setup-review /classify /validate /build-wiki /appraise /sub-review /publish
├── prompts/
│   ├── 01-setup-interview.md
│   ├── 02-classify.md
│   ├── 03-summarize-papers.md
│   ├── 04-concepts-debates.md
│   ├── 05-quality-appraisal.md
│   └── 06-sub-review.md
├── project.yaml              the researcher's project (created by setup)
├── project.example.yaml
├── .env.example              LIBKEY_LIBRARY_ID, LIBKEY_API_TOKEN, UNPAYWALL_EMAIL
├── run.py                    single CLI entry point
├── review/                   Python package
│   ├── config.py             load + validate project.yaml, derive all paths
│   ├── importers/            pubmed.py, wos.py, ebsco.py, ris.py, csv.py, common.py
│   ├── dedup.py
│   ├── screen.py             pre_filter + keyword-group scoring
│   ├── classify.py           batch out / validated save in / checkpoint
│   ├── validate.py           stratified sample, kappa, disclosure draft
│   ├── report.py             Excel, CSVs, optional PRISMA
│   ├── pdfs.py               LibKey → Unpaywall → manual list; drop-folder matcher
│   ├── wiki.py               scaffold, stubs, tables rebuild, PDF links
│   ├── figures.py            frequency charts
│   ├── graph.py              [[link]] graph → standalone HTML
│   └── state.py              stage tracking + `status`
├── setup/                    install-windows.bat, install-mac.sh, requirements.txt
├── data/                     exports/ (input) + generated lists (git-ignored)
├── wiki/                     Obsidian vault (generated)
├── mkdocs.yml, hooks/        wikilinks hook, PDF-exclusion hook
├── .github/workflows/        tests.yml, pages.yml, openequella.yml
├── examples/demo/            anonymized records + project.yaml + expected snapshot
├── tests/
└── docs/                     per-stage illustrated guides, Codex guide, FAQ
```

### Stages

`setup → import → prescreen → classify → validate → report → pdfs → wiki → site → publish`

`data/state.json` records which stages are complete along with their counts. `py run.py status` prints the current stage and the exact next command. Each agent instruction file tells the agent to run `status` first.

## 3. `project.yaml`

```yaml
project:      { title, short_name, researcher, institution, ai_operator }
question:     "<research question>"
picos:        { population, intervention_or_exposure, comparison, outcomes, study_design }
sources:      [pubmed, wos, ebsco, ris]
prescreen:
  keyword_groups:
    - { name: <str>, weight: <int>, terms: [<str>, ...] }
  threshold: 1
  exclude: { retracted: true, editorials: true, non_english: true, no_abstract: true }
tiers:
  - { id: 1, label: Core Match,   included: true,  definition: "<text>" }
  - { id: 2, label: Strong Match, included: true,  definition: "<text>" }
  - { id: 3, label: Peripheral,   included: false, definition: "<text>" }
  - { id: 4, label: Exclude,      included: false, definition: "<text>" }
validation:   { sample_percent: 10, min_per_tier: 5, seed: 42 }
extraction_columns:
  - { name: <str>, hint: "<what to extract>" }
concept_axes: [<axis>, ...]          # 2–4; each becomes wiki/concepts/<axis>/
appraisal:    { tool: AXIS }         # AXIS | CASP | JBI | RoB2 | none
outputs:      { prisma: false, figures: true, knowledge_graph: true }
pdfs:         { libkey: true, unpaywall: true }
site:         { title: "<str>", targets: [local, github_pages, openequella] }
```

- Secrets (LibKey, Unpaywall email) are kept in `.env`, never in `project.yaml`.
- The classification prompt is assembled from `question`, `picos`, and `tiers`. Researchers do not edit prompt text directly.
- `py run.py check-config` validates the schema (tier ids unique and 2–6 of them, at least one included tier, known appraisal tool, and so on) and prints a plain-English summary.

### Setup interview (`prompts/01-setup-interview.md`)

The agent asks one question at a time and offers options where possible:

1. Research question
2. PICOS
3. Databases searched, and where to place the exports
4. Keyword groups (the agent drafts them, the researcher prunes)
5. Tier definitions (drafted from the question)
6. Extraction columns
7. Concept axes
8. Appraisal tool
9. PRISMA on/off
10. Hosting targets

It writes `project.yaml` and runs `check-config`. If the interview is run again, it edits the existing file rather than overwriting it.

## 4. Data flow

### Import and dedupe
Every importer produces the same common record:
`{id, doi, pmid, title, abstract, authors, year, journal, keywords, pub_types, language, sources[]}`.

- Deduplication tries DOI first, then PMID, then normalized title plus year.
- `sources[]` keeps every database that returned a paper, which the PRISMA counts need.
- Format is detected from file content, so the file extension does not matter.
- Unknown formats produce a clear error that names the supported formats.

### Prescreen
`pre_filter` removes records according to the `exclude` flags (MeSH and publication types are used when present). `score` adds each keyword group's weight once if any of its terms appears in the title, abstract, or keywords (the rule the reference pipeline used). Records below the threshold are excluded.

Outputs: `data/candidates.json`, `data/prescreen_excluded.json`, `data/stats.json`.

### Classify
- `classify --next-batch 50` returns unclassified candidates with the assembled prompt.
- The agent returns `{id: {tier, score, reason}}`.
- `classify --save` validates the result:
  - every id must be a known candidate
  - the tier must be valid
  - reason must be non-empty
  - score must be 1–100
- It then stamps `tool`, `model`, and `timestamp` and merges into `data/checkpoint.json`, which is both the source of truth and the audit log.
- If a save is invalid, nothing is written and every problem is listed.

### Validate
- `validate --draw` takes a stratified random sample (`sample_percent` per tier, minimum `min_per_tier`, fixed seed) and writes it to `data/validation.xlsx` with the AI decisions hidden. The researcher fills in a human-tier column.
- `validate --score` reports per-tier agreement, included/excluded agreement, and Cohen's kappa, and lists the papers where human and AI disagreed.
- It writes `data/ai_disclosure.md`, a draft AI-use statement that fills in the tool and model names, the dates, and the validation numbers.

### Report
`Results.xlsx` contains:
- Summary
- one sheet per included tier
- Excluded (all non-included tiers, with the top non-included tier flagged for possible promotion)
- Validation

CSVs are written as well. The PRISMA PNG is produced only when `outputs.prisma` is true, and every N in it comes from the data.

### PDFs
For each included paper, the script tries in order:
1. LibKey `fullTextFile`, then `fullTextLink` (only if credentials are set)
2. Unpaywall `best_oa_location` (only if `UNPAYWALL_EMAIL` is set)
3. Otherwise the paper goes on `data/manual_downloads.csv` with a doi.org link

Other behavior:
- `pdfs --match` matches PDFs the researcher dropped into `wiki/raw/` by DOI found in the PDF text, then by fuzzy title match, and renames them.
- File names follow `T{tier}-{nn:02d} - {title} ({year}).pdf`.
- The step resumes and skips files that already exist.
- Results are logged in `data/pdf_log.json`.

### Wiki
**Mechanical scaffold (`wiki --scaffold`):**
- `index.md`, `log.md`
- `wiki/AGENTS.md` and `wiki/CLAUDE.md` (vault instructions)
- `papers/tier<N>/` with one stub per included paper. Each stub has front-matter (id, doi, year, tier, pdf) and empty sections for every extraction column and the appraisal, plus an `[Open PDF]` link.
- `concepts/<axis>/`
- `debates/`, `tables/`, `figures/`, `sub-reviews/`
- `methods-review/search-and-screening.md`, filled in from `stats.json` and the validation results
- `methods-review/data-extraction.md`

**Agent passes:**
- `03-summarize-papers.md`: `wiki --next-paper` gives the paper's metadata and its PDF text (PyMuPDF, page-limited), or the abstract if there is no PDF. The agent fills in the stub's sections and front-matter extraction fields.
- `04-concepts-debates.md`: concept pages per axis, with `[[links]]` to papers; debate pages for contradictions found across papers.
- `05-quality-appraisal.md`: checklist items for the chosen tool are written into each paper's front-matter.
- `06-sub-review.md`: optional. The researcher names a subset (for example one population), and the agent builds `sub-reviews/<name>/` with its own PICOS, paper list, and synthesis.
- Every pass adds an entry to `log.md`.

**Derived outputs:**
- `wiki --tables` rebuilds `tables/tier<N>-extraction.md` and `tables/appraisal.md` from the front-matter.
- `figures` creates charts of papers per tier, per year, and per source, plus the most common values of the extraction columns.
- `graph` produces `tables/knowledge-graph.html` (vis-network, standalone) from the `[[links]]`.

### Site and publish
- `site` generates the mkdocs nav from the wiki folders and builds with Material; `site --serve` previews locally. The wikilinks hook is ported from the reference pipeline.
- **GitHub Pages:** `pages.yml` builds with `EXCLUDE_PDFS=1`. A hook drops `raw/` and rewrites `[Open PDF]` links to doi.org links.
- **openEQUELLA:** `openequella.yml` and `metadata.json`, following the BYU-I oe-github publish pattern, with PDFs included because access is campus-restricted.
- **Local:** `site/`.
- The README explains the copyright reasoning behind each target.

## 5. Agent-neutral packaging

- `prompts/*.md` are the only source of AI instructions. Each one states its inputs (the command to run), the judgment rules, the output JSON schema, and the save command.
- `AGENTS.md` and `CLAUDE.md` have the same body: run `py run.py status` first, map the researcher's intent to a playbook, never edit `data/*.json` directly, and always save through `run.py`.
- `.claude/commands/*.md` are one-line wrappers that point to the matching playbook.
- `docs/using-codex.md` explains how to use Codex instead of Claude Code.

## 6. Documentation for non-coders

- **README:** what the template does, an overview figure, a 5-step quick start (install → open folder in an AI tool → "set up my review" → follow prompts → publish), and links to the guides.
- **`docs/`:**
  - `01-install.md`
  - `02-search-and-export.md` (how to export from each database)
  - `03-setup.md`
  - `04-screening.md`
  - `05-validation.md`
  - `06-pdfs.md`
  - `07-wiki-and-obsidian.md`
  - `08-website.md`
  - `using-codex.md`
  - `faq.md`
- **Setup scripts:** check Python ≥ 3.11, create `.venv`, install the requirements (pyyaml, openpyxl, matplotlib, requests, pymupdf, rapidfuzz, mkdocs, mkdocs-material, pytest), and copy `.env.example` to `.env`.

## 7. Demo

- `examples/demo/` contains ~30 records sliced from the sports-science search exports (PubMed and WoS), a `project.yaml` written in generic terms with no researcher or project names, and `expected/` (stats and tier counts).
- `py run.py demo` copies it into `demo-workspace/` (git-ignored) so researchers can try every step there.

## 8. Testing

- **pytest unit tests:** each importer on fixture files, dedup precedence, pre_filter and scoring, the config validator, classify save validation (rejects bad tier, unknown id, empty reason), stratified sampling determinism, kappa against known values, table rebuild from front-matter, PDF file-name sanitizing, and the wikilinks hook.
- **End-to-end test:** runs the demo with a stub classifier and summarizer that use canned decisions, through `site` build. It checks that the files exist and that the counts match `expected/`.
- **CI:** `tests.yml` runs on windows-latest and ubuntu-latest.

## 9. Out of scope

- Manuscript and .docx generation, SDC builders, NotebookLM, graphify
- An Anthropic/OpenAI API-key classification mode
- The reference pipeline's legacy scripts
- Any change to the reference repo

## 10. Error handling principles

- Every command finishes with a plain-English next step, or with a clear error that says what to fix.
- Saves are atomic: write to a temp file, then rename.
- Invalid agent output is rejected as a whole and nothing is partially written.
- Network steps (LibKey, Unpaywall) retry with backoff, record each failure, and continue.
- `status` reports a misconfiguration (missing exports, missing `project.yaml`) before any stage runs.
