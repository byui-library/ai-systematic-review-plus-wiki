# CLAUDE.md

This file provides guidance to AI coding agents (Claude Code, Codex, and similar) working in this repository.

> **Status: under construction.** The template is being built from the design spec. This file covers **developing** the template. Once implementation is finished it will be replaced by the researcher-facing agent instructions described in spec §5, and `AGENTS.md` will carry the same body.

## What this repo is

A public, cloneable template (`byui-library/ai-systematic-review-plus-wiki`) that runs an AI-assisted systematic literature review on any research question:

database exports → dedupe → keyword prescreen → AI tiering → human validation sample → Excel report → full-text PDFs → Obsidian wiki → MkDocs website

It is generalized from the pipeline of an earlier sports-science systematic review, which is the reference implementation. Maintainers record its local location in `CLAUDE.local.md` (git-ignored). **Read from that repo; never modify it.**

## Source of truth

- Design spec: [docs/superpowers/specs/2026-11-03-ai-systematic-review-plus-wiki-design.md](docs/superpowers/specs/2026-11-03-ai-systematic-review-plus-wiki-design.md)
- Implementation plan: `docs/superpowers/plans/` (added once it is written)

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
| [Plan 1](docs/superpowers/plans/2026-11-03-plan-1-core-screening.md) | import, prescreen, classify, validate, report | Done |
| [Plan 2](docs/superpowers/plans/2026-11-03-plan-2-pdfs-and-wiki.md) | PDFs, wiki scaffold, agent wiki passes, figures, knowledge graph | Done |
| Plan 3 | MkDocs site, publishing targets, remaining playbooks, docs, setup scripts, demo | Not yet written |

Commands available so far: `status`, `check-config`, `import`, `prescreen`, `classify --next-batch [N] | --save FILE --tool T --model M`, `validate --draw [--force] | --score`, `report`, `pdfs [--match]`, `wiki --scaffold | --next-paper | --check | --tables | --index`, `figures`, `graph`. Run `py run.py <command> -h` for options. Use `--root <folder>` to run against a project folder other than the repo root.

### Module map (`review/`)

| Module | Responsibility |
| --- | --- |
| `config.py` | `Paths` (every file location), `load_project` (defaults + shape checks + validation of `project.yaml`), `whole_number`, `summary` |
| `stages.py` | `run_import` and `run_prescreen`: read inputs, write data files, record progress |
| `importers/` | One parser per export format plus `detect_format`; `import_exports` reads `data/exports/` |
| `dedup.py` | DOI → PMID → title+year matching; stable ids; `sources[]` |
| `screen.py` | Hard filters (`exclude` flags) and weighted keyword score (each group counts once) |
| `prompt.py` | `build_prompt` (question, PICOS, tiers, **and all decision rules**), `prompt_fingerprint`, `paper_fingerprint`. A saved decision counts only while both fingerprints match: re-running import or prescreen keeps AI work, while editing the criteria or getting new paper information (e.g. an abstract) retires it. Keep decision rules in the prompt, not in `prompts/02-classify.md`, or rule changes won't retire old decisions |
| `classify.py` | Batch out, validated + audited save in (`tool`, `model`, `timestamp`, `history`) |
| `validate.py` | Stratified blind sample → `validation.xlsx`, Cohen's kappa, draft AI disclosure |
| `report.py` | `Results.xlsx`, CSVs, opt-in PRISMA |
| `state.py` | Shared loaders (`load_candidates`, `load_checkpoint`), stage tracking, and next-step text (classify completion is computed from the checkpoint) |
| `excel.py` | `excel_safe`, `write_table`, `write_pairs`, `save_workbook`. Every workbook goes through these |
| `env.py` | `load_env`: reads `.env` (LibKey, Unpaywall); the process environment wins |
| `papers.py` | `included_papers`: included tiers with **stable** per-tier numbers (`data/paper_numbers.json`, never reused), slugs, PDF names, page paths |
| `pdftext.py` / `pdfs.py` | PDF text (PyMuPDF) and DOI detection; download via LibKey then Unpaywall, then a manual list; `match_dropped` for files saved in `wiki/raw/inbox/`. All network access goes through `pdfs.fetch_json` and `pdfs.fetch_pdf` (monkeypatched in tests) |
| `wiki.py` | Page I/O (YAML front-matter), `scaffold`, `next_paper` (writes `data/wiki_paper.json`), `check`, `build_index`, `append_log` |
| `vault_text.py` / `appraisal.py` | Text of generated pages; built-in AXIS, JBI, CASP, and RoB 2 checklists |
| `tables.py` / `figures.py` / `graph.py` | Extraction and appraisal tables, charts, and the vis-network knowledge graph, all built from page front-matter and `[[links]]` |

Tests must pass on Windows and Ubuntu (CI: `.github/workflows/tests.yml`). Tests use synthetic exports from `tests/fixture_exports.py`; never commit real search data outside `examples/demo/`.

Smoke-tested on the reference review's real exports (PubMed, WoS, and SPORTDiscus; about 760 records): raw counts per source match the reference pipeline exactly, and dedup differs by one record, a genuine duplicate that the title+year key catches.
