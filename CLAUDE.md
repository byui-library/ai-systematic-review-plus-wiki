# CLAUDE.md

This file provides guidance to AI coding agents (Claude Code, Codex, and similar) working in this repository.

> **Status: under construction.** The template is being built from the design spec. This file covers **developing** the template. Once implementation is finished it will be replaced by the researcher-facing agent instructions described in spec §5, and `AGENTS.md` will carry the same body.

## What this repo is

A public, cloneable template (`byui-library/ai-systematic-review-plus-wiki`) that runs an AI-assisted systematic literature review on any research question:

database exports → dedupe → keyword prescreen → AI tiering → human validation sample → Excel report → full-text PDFs → Obsidian wiki → MkDocs website

It is generalized from the Flynn Research pipeline (`C:\Users\milesm\Documents\repos\Flynn Research`), which is the reference implementation. **Read from that repo; never modify it.**

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
| Plan 2 | PDFs, wiki scaffold, agent wiki passes, figures, knowledge graph | Not yet written |
| Plan 3 | MkDocs site, publishing targets, remaining playbooks, docs, setup scripts, demo | Not yet written |

Commands available so far: `status`, `check-config`, `import`, `prescreen`, `classify --next-batch [N] | --save FILE --tool T --model M`, `validate --draw [--force] | --score`, `report`. Run `py run.py <command> -h` for options. Use `--root <folder>` to run against a project folder other than the repo root.

### Module map (`review/`)

| Module | Responsibility |
| --- | --- |
| `config.py` | `Paths` (every file location), `load_project` (defaults + validation of `project.yaml`), `summary` |
| `importers/` | One parser per export format plus `detect_format`; `import_exports` reads `data/exports/` |
| `dedup.py` | DOI → PMID → title+year matching; stable ids; `sources[]` |
| `screen.py` | Hard filters (`exclude` flags) and weighted keyword score (each group counts once) |
| `classify.py` | Batch out, validated + audited save in (`tool`, `model`, `timestamp`, `history`) |
| `validate.py` | Stratified blind sample → `validation.xlsx`, Cohen's kappa, draft AI disclosure |
| `report.py` | `Results.xlsx`, CSVs, opt-in PRISMA |
| `state.py` | Stage tracking and next-step text (classify completion is computed from the checkpoint) |

Tests must pass on Windows and Ubuntu (CI: `.github/workflows/tests.yml`). Tests use synthetic exports from `tests/fixture_exports.py`; never commit real search data outside `examples/demo/`.

Smoke-tested on the real Flynn v3 exports: raw counts match Flynn exactly (691 PubMed / 32 WoS / 40 SPORTDiscus), and dedup finds 721 unique versus Flynn's 722. The extra match is a genuine duplicate caught by the title+year key.
