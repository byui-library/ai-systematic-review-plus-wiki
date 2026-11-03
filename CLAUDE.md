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
py -m venv .venv
.venv\Scripts\python -m pip install -r setup/requirements.txt
.venv\Scripts\python -m pytest
```

Tests must pass on Windows and Ubuntu (CI: `.github/workflows/tests.yml`).
