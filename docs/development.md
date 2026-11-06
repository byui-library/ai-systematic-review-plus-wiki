# Developing the template

This page is for **maintainers** of the template. Researchers using it should start with the [README](../README.md).

The repository's `AGENTS.md` and `CLAUDE.md` are written for the AI assistants that help *researchers*. When you develop the template itself, give your assistant this page (and your git-ignored `CLAUDE.local.md`, which records where the reference review lives on your computer).

## What this repo is

A public GitHub template (`byui-library/ai-systematic-review-plus-wiki`) that runs an AI-assisted systematic literature review on any research question:

database exports → dedupe → keyword prescreen → AI tiering → human validation sample → Excel report → full-text PDFs → Obsidian wiki → MkDocs website

It is generalized from the pipeline of an earlier sports-science systematic review (the reference implementation). Read from that repository; never modify it, and never name it or its researchers in public files.

## Source of truth

- Design spec: [docs/superpowers/specs/2026-11-03-ai-systematic-review-plus-wiki-design.md](superpowers/specs/2026-11-03-ai-systematic-review-plus-wiki-design.md)
- Implementation plans: [superpowers/plans/](superpowers/plans/)

## Non-negotiable design rules

1. **Python does all file I/O and the agent only makes judgments.** Every AI step runs `py run.py <step> --next-batch`, then the agent judges using `prompts/NN-*.md`, then `py run.py <step> --save results.json`. Agents never edit `data/*.json` directly.
2. **Agent-neutral.** AI instructions live only in `prompts/*.md`. `AGENTS.md`, `CLAUDE.md`, and `.claude/commands/` are thin wrappers that point to them.
3. **Everything project-specific comes from `project.yaml`.** No hardcoded topics, keywords, tiers, paths, or researcher names in `review/`.
4. **Audience is non-coders.** Every command ends with a plain-English next step or an actionable error.
5. **No copyrighted PDFs in public outputs.** GitHub Pages builds exclude `raw/`. The demo contains metadata and abstracts only, anonymized.
6. **Secrets go in `.env`** (LibKey, Unpaywall email) and never in `project.yaml` or git.

## Wiki rules

- Python owns the generated pages (`index.md`, `AGENTS.md`/`CLAUDE.md` in the vault, `tables/`, `concepts/<axis>/index.md`, the methods-review pages except `notes.md`) and rewrites them freely.
- The agent owns paper pages once they are past `status: stub`, concept and debate pages, sub-reviews, and appends to `log.md`. Re-running the scaffold never overwrites them.
- Only paper-page **front-matter** is parsed. Never derive data from prose.

## Development

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r setup/requirements.txt
.venv/Scripts/python -m pytest -q
```

### Implementation status

| Plan | Scope | Status |
| --- | --- | --- |
| [Plan 1](superpowers/plans/2026-11-03-plan-1-core-screening.md) | import, prescreen, classify, validate, report | Done |
| [Plan 2](superpowers/plans/2026-11-03-plan-2-pdfs-and-wiki.md) | PDFs, wiki scaffold, agent wiki passes, figures, knowledge graph | Done |
| [Plan 3](superpowers/plans/2026-11-03-plan-3-site-docs-demo.md) | MkDocs site, publishing targets, setup interview, researcher docs, setup scripts, demo | Done |

Commands: `status`, `check-config`, `import`, `prescreen`, `classify --next-batch [N] | --save FILE --tool T --model M`, `validate --draw [--force] | --score`, `report`, `pdfs [--match]`, `wiki --scaffold | --next-paper | --check | --tables | --index`, `figures`, `graph`, `site [--target] [--serve]`, `publish openequella --content-repo PATH | github_pages`, `demo`. Run `py run.py <command> -h` for options. Use `--root <folder>` to run against a project folder other than the repo root.

### Considered, not adopted: Jev screening

In November 2026 we tested an optional screening mode that used TypeSafe's Jev model.
- Jev answered yes/no questions drafted from the criteria, and code turned the answers into a tier.
- The assistant judged only the papers where an unsure answer decided the tier.
- The ship bar, set before any results, was a clear gain in recall over the assistant alone.

**Result: not adopted.** On four human-screened SYNERGY+ reviews (2,000 records, 487 finally included):

| | Assistant alone | Jev + assistant |
| --- | --- | --- |
| Recall (included after full text) | 95.5% | 84.4% (−11.1 points, 95% interval −14.0 to −8.2) |
| Papers passed to full-text reading, re-weighted to the full datasets | 7.7% | 5.6% |

**Why it lost:**
- Jev + assistant missed 76 included papers. The assistant alone missed 22, so the net loss is 54.
- 72 of those 76 were ones Jev confidently excluded on core-topic questions, which it reads literally. The assistant never saw them.
- A re-analysis after the verdict tried stricter thresholds and an "assistant OR Jev" safety net. Neither clearly beat the assistant alone: the best gained 0.6 points. Jev also confidently rejected nearly every paper the assistant missed.

**Where the work is kept:**
- The code is on the unmerged `jev-screening` branch.
- The benchmark repository (`byui-library/jev-screening-benchmark`) is private.

**Before trying again:** don't reopen this without fresh human-screened test sets and a reason to expect a recall gain.

### Module map (`review/`)

| Module | Responsibility |
| --- | --- |
| `config.py` | `Paths` (every file location), `load_project` (defaults + shape checks + validation of `project.yaml`), `whole_number`, `summary`. `REVIEW_TYPES` and `FRAMEWORKS`: a type's defaults are merged under the researcher's settings, and a legacy `picos:` block is read as `criteria` with framework PICOS |
| `stages.py` | `run_import` and `run_prescreen`: read inputs, write data files, record progress |
| `importers/` | One parser per export format plus `detect_format`; `import_exports` reads `data/exports/` |
| `dedup.py` | DOI → PMID → title+year matching; stable ids; `sources[]` |
| `screen.py` | Hard filters (`exclude` flags) and weighted keyword score (each group counts once) |
| `prompt.py` | `build_prompt` (question, review type, criteria, tiers, **and all decision rules**; the PICOS prompt is pinned by fingerprint in `tests/test_review_types.py`, so never change its wording), `prompt_fingerprint`, `paper_fingerprint`. A saved decision counts only while both fingerprints match: re-running import or prescreen keeps AI work, while editing the criteria or getting new paper information (e.g. an abstract) retires it. Keep decision rules in the prompt, not in `prompts/02-classify.md`, or rule changes won't retire old decisions |
| `classify.py` | Batch out, validated + audited save in (`tool`, `model`, `timestamp`, `history`) |
| `validate.py` | Stratified blind sample → `validation.xlsx`, Cohen's kappa, draft AI disclosure |
| `report.py` | `Results.xlsx`, CSVs, opt-in PRISMA |
| `state.py` | Shared loaders (`load_candidates`, `load_checkpoint`), stage tracking, and next-step text (classify completion is computed from the checkpoint) |
| `excel.py` | `excel_safe`, `write_table`, `write_pairs`, `save_workbook`. Every workbook goes through these |
| `env.py` | `load_env`: reads `.env` (LibKey, Unpaywall); the process environment wins |
| `papers.py` | `included_papers`: included tiers with **stable** per-tier numbers (`data/paper_numbers.json`, never reused), slugs, PDF names, page paths |
| `pdftext.py` / `pdfs.py` | PDF text (PyMuPDF): `read_pages` returns every page's text plus its tables as Markdown, and `looks_scanned` flags image-only PDFs; DOI detection; download via LibKey then Unpaywall, then a manual list; `match_dropped` for files saved in `wiki/raw/inbox/`. All network access goes through `pdfs.fetch_json` and `pdfs.fetch_pdf` (monkeypatched in tests) |
| `wiki.py` | Page I/O (YAML front-matter), `scaffold`, `next_paper` (writes `data/wiki_paper.json` and the whole paper as page-bounded parts in `data/wiki_paper/`; never truncates), `check`, `build_index`, `append_log` |
| `vault_text.py` / `appraisal.py` | Text of generated pages; built-in AXIS, JBI, CASP, and RoB 2 checklists |
| `tables.py` / `figures.py` / `graph.py` | Extraction and appraisal tables, charts, and the vis-network knowledge graph, all built from page front-matter and `[[links]]` |
| `site.py` / `mkdocs_hooks.py` | Generated `mkdocs.yml` and MkDocs build for the local, github_pages (never any PDFs), and openequella targets; the hook converts `[[links]]` and swaps PDF links for publisher links on public builds |
| `publish.py` | Syncs the openequella build into a researcher's `byui-oeq` content repository clone and commits (never pushes) |
| `demo.py` | Copies `examples/demo/` to a workspace |

The public demo website (<https://byui-library.github.io/ai-systematic-review-plus-wiki/>) is built by `tools/build_demo_site.py`. It runs the same demo steps that `py run.py demo` prints (`DEMO_STEPS` in `run.py`), plus the tables, figures, and graph, then a `github_pages` build into `demo-workspace/site-github_pages/`. Run it locally with `.venv/Scripts/python tools/build_demo_site.py` to preview. It refuses to replace an existing `demo-workspace/` unless you add `--force`. The "Publish website (GitHub Pages)" workflow runs that tool only in this repository, which GitHub marks as a template and which has no `project.yaml`. A repository made from the template publishes its own wiki. To update the demo site, open **Actions → Publish website (GitHub Pages) → Run workflow**.

Tests must pass on Windows and Ubuntu (CI: `.github/workflows/tests.yml`). Tests use synthetic exports from `tests/fixture_exports.py`; never commit real search data outside `examples/demo/`.

Smoke-tested on the reference review's real exports (PubMed, WoS, and SPORTDiscus; about 760 records): raw counts per source match the reference pipeline exactly, and dedup differs by one record, a genuine duplicate that the title+year key catches.
