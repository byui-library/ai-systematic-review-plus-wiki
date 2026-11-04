# 3. Set up your review

Everything specific to your review lives in one file, `project.yaml`. You don't need to edit it by hand. Ask your assistant:

> *Set up my review.*

It interviews you **one question at a time**, usually offering choices, and drafts the harder parts for you to approve:

1. Your research question
2. **The kind of review**: systematic, scoping, qualitative evidence, topic collection, or methods review (see [below](#review-types-and-criteria))
3. **Eligibility criteria**, in the framework that fits: PICOS, PCC, SPIDER, plain include/exclude rules, or your own elements
4. Which databases you searched
5. **Keyword groups** for the prescreen. Papers containing none of your keywords never reach the AI. This is a cheap, generous first filter.
6. Hard filters (retractions, editorials, conference abstracts, non-English papers)
7. **Tiers**: usually *Core Match* and *Strong Match* (included) and *Peripheral* and *Exclude* (not included), each with a definition the AI applies to every paper
8. Which tiers get **deep** treatment: the AI summarises each paper to you and waits for your confirmation before writing its wiki page
9. The size of your validation sample
10. **Extraction columns**: what to record from every included paper (sample, design, outcome measure…)
11. Concept folders for the wiki (for example *methods*, *outcomes*, *populations*)
12. A quality-appraisal checklist: AXIS, JBI, CASP (cohort), CASP-Qual (qualitative), RoB 2, or none
13. Outputs: flowchart of records (PRISMA), figures, knowledge graph
14. Full-text sources: LibKey, Unpaywall
15. Where the website should live

It then runs `py run.py check-config`, which checks the file and prints a plain-English summary.

## Changing things later

Ask the assistant to change any setting. It is fine to change keywords or filters at any time.

Changing the **research question, review type, criteria, or tier definitions** after screening has started means the AI re-screens. Its old decisions were made against the old wording, and the template won't report them as if they matched the new one. The old decisions stay in the audit log.

## Review types and criteria

You don't need to write any of this by hand, because the interview does it. This section is for reading or hand-editing `project.yaml`.

`review_type` sets the wording the AI and your Methods page use, and sensible defaults that you can change:

| Type | Use it for | Framework offered | Appraisal | Validation sample |
| --- | --- | --- | --- | --- |
| `systematic` | Effects or associations (the classic systematic review) | PICOS | AXIS | 10%, at least 5 per tier |
| `scoping` | Mapping what research exists on a topic | PCC | none | 10%, at least 5 |
| `qualitative` | Experiences, perceptions, meanings | SPIDER | CASP-Qual | 10%, at least 5 |
| `collection` | A topic collection or annotated bibliography | plain | none | 5%, at least 3 |
| `methods` | How studies use a method, theory, instrument, or technology | custom | none | 5%, at least 3 |

Any type can use any framework.

**Systematic review (PICOS)**

```yaml
review_type: systematic
criteria:
  framework: PICOS
  elements:
    Population: Undergraduate students in STEM courses
    Intervention or exposure: Retrieval practice
    Comparison: Restudy or no intervention
    Outcomes: Exam scores or retention
    Study design: Experimental or quasi-experimental studies
```

An older `picos:` section (with `population:`, `intervention_or_exposure:`, and so on) still works and means the same thing.

**Scoping review (PCC)**

```yaml
review_type: scoping
criteria:
  framework: PCC
  elements:
    Population: Nursing students
    Concept: Simulation-based training
    Context: Undergraduate nursing programs
  include: [Empirical studies of any design]
  exclude: [Opinion pieces and editorials]
```

**Qualitative evidence synthesis (SPIDER)**

```yaml
review_type: qualitative
criteria:
  framework: SPIDER
  elements:
    Sample: Hospital nurses
    Phenomenon of interest: Experiences of burnout
    Design: Interviews or focus groups
    Evaluation: Experiences, perceptions, coping
    Research type: Qualitative or mixed methods
```

**Topic collection (plain rules)**

```yaml
review_type: collection
criteria:
  framework: plain
  include:
    - Studies of open educational resources in higher education
    - Any design, any country
  exclude:
    - K-12 settings
```

**Methods review (your own elements)**

```yaml
review_type: methods
criteria:
  framework: custom
  elements:
    Method: Principal component analysis or factor analysis
    Data: Wearable sensor data
    Setting: Team sports
```

## Library credentials (optional)

`.env` (created by the setup script) can hold:

- `LIBKEY_LIBRARY_ID` and `LIBKEY_API_TOKEN`: from your library, so PDFs your library subscribes to are fetched automatically
- `UNPAYWALL_EMAIL`: your own email address, for legal open-access copies

These never go in `project.yaml` and are never committed to git.

Next: [4. Screening](04-screening.md)
