# Playbook 01: set up a review (interview → project.yaml)

**Goal:** turn the researcher's idea into a valid `project.yaml` by interviewing them **one question at a time**. Offer choices wherever possible, so they can click or type a number instead of writing from scratch.

**Reads:** `project.example.yaml` (a complete, commented example), `docs/03-setup.md` (section "Review types and criteria", with a criteria block for every review type), and `project.yaml` if it already exists.
**Writes:** `project.yaml` only.

## How to interview

- Ask **one question at a time**, and wait for the answer before asking the next. Never send a list of questions.
- Offer 2–4 numbered choices when you can, including your recommendation (marked "recommended"), plus "something else".
- Draft the hard parts yourself from what they have already told you (criteria, keyword groups, tier definitions, extraction columns), then ask them to confirm or edit the draft.
- If `project.yaml` already exists, read it first, show a short summary, and ask which parts to change. Edit only those parts. An older file may have a `picos:` section instead of `criteria:`. It still works: leave it alone unless they want to change the criteria, and in that case replace it with a `criteria:` section that has `framework: PICOS`.
- Plain language: the researcher may never have edited a YAML file. Don't make them do it.

## Questions, in order

1. **Topic and research question.** Ask what the review is about, then propose a one-sentence research question for them to accept or edit. Sets `question`, `project.title`, `project.short_name` (lower case, hyphens), `project.researcher`, and `project.institution`.
2. **Review type.** Ask what kind of project this is, and give one line on each:
   - `systematic`: a systematic review of effects or associations (PICOS).
   - `scoping`: maps what research exists on a topic (PCC).
   - `qualitative`: a synthesis of qualitative evidence on experiences or perceptions (SPIDER).
   - `collection`: a topic collection or annotated bibliography, with plain include and exclude rules.
   - `methods`: a review of how studies use a method, theory, instrument, or technology (custom elements).

   Sets `review_type`. The type also sets the defaults that later questions recommend (the appraisal tool and the validation sample).
3. **Eligibility criteria.** Propose the type's usual framework (`PICOS`, `PCC`, `SPIDER`, `plain`, or `custom`), and tell them they may choose another. Draft each element from the question, then confirm the elements one at a time:
   - `PICOS`: Population, Intervention or exposure, Comparison (may be blank), Outcomes, Study design.
   - `PCC`: Population, Concept, Context (all three needed).
   - `SPIDER`: Sample and Phenomenon of interest (both needed), then Design, Evaluation, Research type.
   - `custom`: agree 2–5 element names with them (for example Method, Data, Setting), then fill in each one.
   - `plain`: no elements.

   Then ask for any **include** and **exclude** rules, for example "Empirical studies of any design" or "Opinion pieces". They are required for `plain` and optional for the others. Sets `criteria` (`framework`, `elements`, `include`, `exclude`). Write `criteria:`, never `picos:`.
4. **Databases.** Ask which databases they searched or will search, offering PubMed, Web of Science, EBSCO (SPORTDiscus, CINAHL, ERIC…), Scopus, and other/Zotero. Map each to `sources`: `pubmed`, `wos`, `ebsco`, `ris` (Scopus RIS, ERIC, PsycINFO, Zotero, EndNote), or `csv` (Scopus CSV and other spreadsheets). Put the most complete database first, because the first source wins when duplicates are merged. Tell them the export steps are in `docs/02-search-and-export.md`.
5. **Keyword prescreen.** Draft 2–4 keyword groups from the criteria elements and include rules (for example population terms, method terms, outcome terms). Give the most discriminating group weight 3 and the others weight 1, and set threshold 1. Show the draft and ask them to add or remove terms. Explain in one sentence: "Papers with none of these words never reach the AI; this is a cheap first filter, so err on the side of including terms." Sets `prescreen.keyword_groups` and `prescreen.threshold`.
6. **Hard filters.** Confirm the defaults: drop retractions, editorials and letters, conference abstracts, non-English papers, and records with neither an abstract nor keywords. Ask only whether any of these should be kept. Sets `prescreen.exclude`.
7. **Tiers.** Propose four tiers from their question: Core Match and Strong Match included, Peripheral and Exclude excluded. Write a definition of 1–3 sentences for each, then ask them to confirm or edit one tier at a time. They may rename tiers or use 2–6 tiers. At least one must be included. Sets `tiers`.
8. **Depth.** Ask which included tiers get the deep treatment, where the AI summarises each paper and waits for their confirmation before writing it. Recommend the first included tier only. Sets `wiki.deep_tiers`.
9. **Validation sample.** Explain that they will re-screen a random sample themselves so the AI's accuracy can be reported. Recommend the review type's default: 10% of each tier with at least 5 per tier, or 5% with at least 3 for `collection` and `methods`. Keep `seed: 42`. Leave `validation` out of the file when they accept the default. Sets `validation`.
10. **Extraction columns.** Propose 4–8 columns from the question (for example Sample, Design, Intervention, Outcome measure, Key result), each with a short hint. Confirm the list. Sets `extraction_columns`.
11. **Concept folders.** Propose 2–4 concept axes for organising the wiki (for example `methods`, `outcomes`, `populations`) and confirm them. Sets `concept_axes`.
12. **Quality appraisal.** Offer AXIS (cross-sectional studies), JBI (analytical cross-sectional), CASP (cohort), `CASP-Qual` (qualitative studies), RoB2 (randomised trials), or none. Recommend the review type's default (AXIS for `systematic`, `CASP-Qual` for `qualitative`, none for `scoping`, `collection` and `methods`) unless their expected study designs suggest another. Sets `appraisal.tool`.
13. **Outputs.** Ask whether they want a flowchart of records (titled PRISMA 2020 for systematic and qualitative reviews and PRISMA-ScR for scoping reviews; off by default), frequency figures (on), and the knowledge graph (on). Sets `outputs`.
14. **Full texts.** Ask whether their library uses LibKey and whether they want open-access copies from Unpaywall. Both are on by default and both are optional. Tell them the credentials go in a file called `.env`, never in `project.yaml`. Copy `.env.example` to `.env` for them if it is missing, and explain each line. Sets `pdfs`.
15. **Website.** Ask where the website should live: only on their computer (`local`), public on GitHub Pages without PDFs (`github_pages`), and/or at BYU-Idaho on openEQUELLA behind sign-in (`openequella`). Set `site.title` and `site.targets`.

## Finish

1. Write `project.yaml`, starting from the structure of `project.example.yaml`, with short comments the researcher can read later. Use `review_type` and `criteria` (see `docs/03-setup.md`) in place of the example's `picos` section.
2. Run `py run.py check-config`. If it lists problems, fix them (ask the researcher when a fix needs their decision) and run it again until it passes.
3. Show the summary it prints, and tell the researcher the next step: save their database exports in `data/exports/` (see `docs/02-search-and-export.md`), then run `py run.py import`.

## Rules

- Never edit `data/*.json` files. This playbook writes `project.yaml` only (and `.env` from `.env.example` when asked in step 14).
- Changing the question, review type, criteria, or tiers after classification has started retires the AI decisions made under the old wording, and the papers must be classified again. Say so before making that kind of change to an existing project.
- Never put credentials or email addresses in `project.yaml`.
