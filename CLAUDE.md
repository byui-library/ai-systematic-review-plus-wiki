# Instructions for AI assistants

You are helping a researcher run an AI-assisted systematic literature review with this template. Most researchers are not programmers, so:
- explain in plain words, one step at a time
- run the commands for them
- read every message the pipeline prints and pass on what it means

These instructions are identical in `AGENTS.md` (Codex and other agents) and `CLAUDE.md` (Claude Code).

## Start every session

1. Run `py run.py status`. On macOS or Linux, type `python3` instead of `py` in every command. The status shows which stage is next and the exact next step.
2. If it says the setup is missing (there is no `project.yaml` yet), offer to run the setup interview.
3. If the researcher just wants to try the template, offer the demo: `py run.py demo`.

## What the researcher asks for, and what you do

| The researcher says… | You do |
| --- | --- |
| "Set up my review" | Follow `prompts/01-setup-interview.md` |
| "Import my search results" | Check that the exports are in `data/exports/`, then run `py run.py import` and `py run.py prescreen` |
| "Screen" or "classify the papers" | Follow `prompts/02-classify.md` (in batches, until none remain) |
| "Check the AI" or "validation" | Run `py run.py validate --draw`. Explain that they re-screen `data/validation.xlsx` themselves without looking at the AI's answers. When they are done, run `py run.py validate --score` |
| "Make the report" | Run `py run.py report` |
| "Get the full texts" or "PDFs" | Run `py run.py pdfs`. For papers it could not fetch, they save the PDFs in `wiki/raw/inbox/`; then run `py run.py pdfs --match` |
| "Build the wiki" or "summarise the papers" | Run `py run.py wiki --scaffold`, then follow `prompts/03-summarize-papers.md` |
| "Appraise quality" | Follow `prompts/05-quality-appraisal.md` |
| "Concept pages" or "debates" | Follow `prompts/04-concepts-debates.md` |
| "A sub-review on…" | Follow `prompts/06-sub-review.md` |
| "Tables, figures, graph" | Run `py run.py wiki --tables`, `py run.py figures`, `py run.py graph` |
| "Make the website" | Run `py run.py site` (or preview with `py run.py site --serve`). To publish it, follow `docs/08-website.md` with them |

## Rules

- **Use `run.py` for every data step.** Never edit, move, or delete files in `data/`; they are the review's audit trail.
- **Follow the playbooks in `prompts/` exactly.** They are the shared instructions that keep every AI assistant consistent.
- **Record who did the screening.** When saving classifications, pass your real tool name and exact model id (`--tool`, `--model`). They go into the audit log and the AI-use disclosure.
- **Ask one question at a time**, and offer choices when you can.
- **Keep secrets secret.** Credentials and email addresses go in `.env`, never in `project.yaml`. Never print the contents of `.env`.
- **Never publish or push on your own.** `py run.py publish openequella` commits locally and prints the push command. Push to GitHub, or run the GitHub Pages workflow, only when the researcher asks.
- **Don't edit generated files**, because they are rebuilt every time: `mkdocs.yml`, `wiki/index.md`, `wiki/tables/`, `wiki/AGENTS.md`, `wiki/CLAUDE.md`, and the methods-review pages (except `notes.md`).
- **When a command stops with a message**, explain it to the researcher in plain words and do what it says. Don't work around it.

## Where things are

| Path | What it is |
| --- | --- |
| `project.yaml` | The review's settings: question, criteria, keywords, tiers. Created by the setup interview |
| `data/exports/` | The researcher's database exports |
| `data/` | Screening data and the audit trail (committed to git) |
| `data/Results.xlsx` | The screening report |
| `wiki/` | The Obsidian vault: open it with Obsidian's "Open folder as vault" |
| `prompts/` | Playbooks for AI assistants (01–06) |
| `docs/` | Guides for the researcher, starting with `docs/01-install.md` |

Developing the template itself? See `docs/development.md`.
