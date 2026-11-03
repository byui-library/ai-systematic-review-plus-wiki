# 3. Set up your review

Everything specific to your review lives in one file, `project.yaml`. You don't need to edit it by hand. Ask your assistant:

> *Set up my review.*

It interviews you **one question at a time**, usually offering choices, and drafts the harder parts for you to approve:

1. Your research question
2. Eligibility criteria (PICOS: population, intervention or exposure, comparison, outcomes, study design)
3. Which databases you searched
4. **Keyword groups** for the prescreen. Papers containing none of your keywords never reach the AI. This is a cheap, generous first filter.
5. Hard filters (retractions, editorials, conference abstracts, non-English papers)
6. **Tiers**: usually *Core Match* and *Strong Match* (included) and *Peripheral* and *Exclude* (not included), each with a definition the AI applies to every paper
7. Which tiers get **deep** treatment: the AI summarises each paper to you and waits for your confirmation before writing its wiki page
8. The size of your validation sample
9. **Extraction columns**: what to record from every included paper (sample, design, outcome measure…)
10. Concept folders for the wiki (for example *methods*, *outcomes*, *populations*)
11. A quality-appraisal checklist: AXIS, JBI, CASP, RoB 2, or none
12. Outputs: PRISMA flowchart, figures, knowledge graph
13. Full-text sources: LibKey, Unpaywall
14. Where the website should live

It then runs `py run.py check-config`, which checks the file and prints a plain-English summary.

## Changing things later

Ask the assistant to change any setting. It is fine to change keywords or filters at any time.

Changing the **research question, PICOS, or tier definitions** after screening has started means the AI re-screens. Its old decisions were made against the old wording, and the template won't report them as if they matched the new one. The old decisions stay in the audit log.

## Library credentials (optional)

`.env` (created by the setup script) can hold:

- `LIBKEY_LIBRARY_ID` and `LIBKEY_API_TOKEN`: from your library, so PDFs your library subscribes to are fetched automatically
- `UNPAYWALL_EMAIL`: your own email address, for legal open-access copies

These never go in `project.yaml` and are never committed to git.

Next: [4. Screening](04-screening.md)
