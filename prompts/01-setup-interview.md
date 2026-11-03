# Playbook 01: set up a review (interview → project.yaml)

**Goal:** turn the researcher's idea into a valid `project.yaml` by interviewing them **one question at a time**. Offer choices wherever possible, so they can click or type a number instead of writing from scratch.

**Reads:** `project.example.yaml` (a complete, commented example) and `project.yaml` if it already exists.
**Writes:** `project.yaml` only.

## How to interview

- Ask **one question at a time**, and wait for the answer before asking the next. Never send a list of questions.
- Offer 2–4 numbered choices when you can, including your recommendation (marked "recommended"), plus "something else".
- Draft the hard parts yourself from what they have already told you (keyword groups, tier definitions, extraction columns), then ask them to confirm or edit the draft.
- If `project.yaml` already exists, read it first, show a short summary, and ask which parts to change. Edit only those parts.
- Plain language: the researcher may never have edited a YAML file. Don't make them do it.

## Questions, in order

1. **Topic and research question.** Ask what the review is about, then propose a one-sentence research question for them to accept or edit. Sets `question`, `project.title`, `project.short_name` (lower case, hyphens), `project.researcher`, and `project.institution`.
2. **Eligibility (PICOS).** Propose each element from the question and confirm one at a time: population, intervention or exposure, comparison (may be blank), outcomes, and study design. Sets `picos`.
3. **Databases.** Ask which databases they searched or will search, offering PubMed, Web of Science, EBSCO (SPORTDiscus, CINAHL, ERIC…), Scopus, and other/Zotero. Map each to `sources`: `pubmed`, `wos`, `ebsco`, `ris` (Scopus RIS, ERIC, PsycINFO, Zotero, EndNote), or `csv` (Scopus CSV and other spreadsheets). Put the most complete database first, because the first source wins when duplicates are merged. Tell them the export steps are in `docs/02-search-and-export.md`.
4. **Keyword prescreen.** Draft 2–4 keyword groups from the PICOS (for example population terms, method terms, outcome terms). Give the most discriminating group weight 3 and the others weight 1, and set threshold 1. Show the draft and ask them to add or remove terms. Explain in one sentence: "Papers with none of these words never reach the AI; this is a cheap first filter, so err on the side of including terms." Sets `prescreen.keyword_groups` and `prescreen.threshold`.
5. **Hard filters.** Confirm the defaults: drop retractions, editorials and letters, conference abstracts, non-English papers, and records with neither an abstract nor keywords. Ask only whether any of these should be kept. Sets `prescreen.exclude`.
6. **Tiers.** Propose four tiers from their question: Core Match and Strong Match included, Peripheral and Exclude excluded. Write a definition of 1–3 sentences for each, then ask them to confirm or edit one tier at a time. They may rename tiers or use 2–6 tiers. At least one must be included. Sets `tiers`.
7. **Depth.** Ask which included tiers get the deep treatment, where the AI summarises each paper and waits for their confirmation before writing it. Recommend the first included tier only. Sets `wiki.deep_tiers`.
8. **Validation sample.** Explain that they will re-screen a random sample themselves so the AI's accuracy can be reported. Recommend 10% of each tier with at least 5 per tier, and keep `seed: 42`. Sets `validation`.
9. **Extraction columns.** Propose 4–8 columns from the question (for example Sample, Design, Intervention, Outcome measure, Key result), each with a short hint. Confirm the list. Sets `extraction_columns`.
10. **Concept folders.** Propose 2–4 concept axes for organising the wiki (for example `methods`, `outcomes`, `populations`) and confirm them. Sets `concept_axes`.
11. **Quality appraisal.** Offer AXIS (cross-sectional studies), JBI (analytical cross-sectional), CASP (cohort), RoB2 (randomised trials), or none. Recommend the one that fits most of their expected study designs. Sets `appraisal.tool`.
12. **Outputs.** Ask whether they want a PRISMA flowchart (off by default), frequency figures (on), and the knowledge graph (on). Sets `outputs`.
13. **Full texts.** Ask whether their library uses LibKey and whether they want open-access copies from Unpaywall. Both are on by default and both are optional. Tell them the credentials go in a file called `.env`, never in `project.yaml`. Copy `.env.example` to `.env` for them if it is missing, and explain each line. Sets `pdfs`.
14. **Website.** Ask where the website should live: only on their computer (`local`), public on GitHub Pages without PDFs (`github_pages`), and/or at BYU-Idaho on openEQUELLA behind sign-in (`openequella`). Set `site.title` and `site.targets`.

## Finish

1. Write `project.yaml`, starting from the structure of `project.example.yaml`, with short comments the researcher can read later.
2. Run `py run.py check-config`. If it lists problems, fix them (ask the researcher when a fix needs their decision) and run it again until it passes.
3. Show the summary it prints, and tell the researcher the next step: save their database exports in `data/exports/` (see `docs/02-search-and-export.md`), then run `py run.py import`.

## Rules

- Never edit `data/*.json` files. This playbook writes `project.yaml` only (and `.env` from `.env.example` when asked in step 13).
- Changing the question, PICOS, or tiers after classification has started retires the AI decisions made under the old wording, and the papers must be classified again. Say so before making that kind of change to an existing project.
- Never put credentials or email addresses in `project.yaml`.
