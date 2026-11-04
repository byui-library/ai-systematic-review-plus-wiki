# Review types and general eligibility criteria: design

Date: 2026-11-04 · Status: approved in conversation, awaiting written-spec review

## Problem

The template assumes every project is a PICOS systematic review. `project.yaml` has a fixed `picos:` block
(population, intervention or exposure, comparison, outcomes, study design). The screening prompt, the wiki's
Methods page, and the draft AI-use disclosure all say "systematic review" and "PICOS". Many researchers collect
and analyse literature that does not fit that frame: scoping or mapping reviews, qualitative evidence
syntheses, topic collections and annotated bibliographies, and reviews of a method, theory, instrument or
technology.

## Decisions (from the interview)

| Question | Decision |
| --- | --- |
| Which project kinds to support | All four: scoping, qualitative evidence, topic collection, methods/theory/tool review |
| How criteria are described | Named frameworks (PICOS, PCC, SPIDER, plain include/exclude) plus custom elements |
| Does the review type matter | Yes: a `review_type` sets the wording everywhere and sensible defaults, all overridable |
| Appraisal | Add CASP Qualitative only; scoping, collection and methods reviews default to no appraisal |
| Validation | Always on; collection and methods reviews default to a smaller sample (5%, at least 3 per tier) |
| Examples | A worked criteria block per type in `docs/03-setup.md`; `project.example.yaml` and the demo stay PICOS |

## Hard constraint: existing decisions survive

Each AI decision is valid only while the prompt fingerprint (`review/prompt.py`) matches. For
`review_type: systematic` with `framework: PICOS`, `build_prompt` must return **byte-identical** text to
today's prompt, so existing projects and the demo keep every decision. A test pins this against the current
prompt for the demo and fixture projects.

An old `project.yaml` with a `picos:` block and no `criteria:` or `review_type:` loads exactly as before
(read as `review_type: systematic`, `criteria.framework: PICOS`).

## Configuration

```yaml
review_type: scoping      # systematic | scoping | qualitative | collection | methods  (default: systematic)
criteria:
  framework: PCC          # PICOS | PCC | SPIDER | plain | custom
  elements:               # ordered label -> text; the framework fixes the labels, custom names its own
    Population: Nursing students
    Concept: Simulation-based training
    Context: Undergraduate programs
  include:                # optional for every framework; required (non-empty) for plain
    - Empirical studies of any design
  exclude:
    - Opinion pieces and editorials
```

Framework element labels:

| Framework | Elements (in order) | Required |
| --- | --- | --- |
| PICOS | Population, Intervention or exposure, Comparison, Outcomes, Study design, plus any extra rows (e.g. Setting) after them | nothing (as before: empty ones are left out, and an empty PICOS still loads) |
| PCC | Population, Concept, Context | all three |
| SPIDER | Sample, Phenomenon of interest, Design, Evaluation, Research type | Sample, Phenomenon of interest |
| plain | none | `include` has at least one item |
| custom | the researcher's own labels | at least one element |

**Legacy mapping.** `picos: {population, intervention_or_exposure, comparison, outcomes, study_design}` becomes
`criteria: {framework: PICOS, elements: {...}}` with the labels above. Any other key becomes an extra PICOS row
(`time_frame` becomes `Time frame`), because older files screened on those rows. Values are kept unstripped
for the same reason. If both a non-empty `picos:` and `criteria:` are present, `check-config` reports it and
asks for one. (Revised after code review: the first draft rejected extra keys and empty PICOS, which would
have stopped older projects from loading.) The legacy rows are kept exactly as the old prompt printed them,
in its order (the five standard keys, then the others in file order), and they are never merged or reordered.
Keys that differ only in case (`population`, `Population`) stay two rows, and a capitalised `Outcomes:` stays
an extra row at the end. (Revised after the Copilot review.)

**Validation (`check-config`)**, in plain English, for example:
- `review_type must be one of systematic, scoping, qualitative, collection, methods`
- `criteria.framework must be one of PICOS, PCC, SPIDER, plain, custom`
- `PCC needs Population, Concept and Context (missing: Context)`
- `criteria.elements has "Outcome", which is not part of PCC; use custom to name your own elements`
- `plain criteria need at least one include rule`

## Review-type defaults

A type default applies only when the researcher has not set that key. Precedence: the researcher's
`project.yaml` value, then the type default, then the global default in `DEFAULTS`. This means the type
defaults have to be merged before `DEFAULTS` fills `appraisal.tool` and `validation`.

| Type | Wording | Framework the interview offers first | `appraisal.tool` | `validation` | Flowchart title |
| --- | --- | --- | --- | --- | --- |
| systematic | systematic review | PICOS | AXIS | 10%, min 5 | PRISMA 2020 flow diagram |
| scoping | scoping review | PCC | none | 10%, min 5 | PRISMA-ScR flow diagram |
| qualitative | qualitative evidence synthesis | SPIDER | CASP-Qual | 10%, min 5 | PRISMA 2020 flow diagram |
| collection | literature collection | plain | none | 5%, min 3 | Flow of records |
| methods | methods review | custom | none | 5%, min 3 | Flow of records |

The framework is not tied to the type. Any type may use any framework, and the interview only proposes the
type's usual one first.

## Where it is used

| Place | Change |
| --- | --- |
| `review/config.py` | `review_type`, `criteria` defaults, framework presets, type defaults, legacy `picos` mapping, validation; `Project.review_type`, `Project.criteria`, `Project.review_noun`. `Project.picos` is removed and its callers use `criteria`. |
| `review/prompt.py` | `"screening papers for a {noun}"`; the heading `"{FRAMEWORK} CRITERIA:"` (custom gives `ELIGIBILITY CRITERIA:`) followed by the elements, then `INCLUDE:` / `EXCLUDE:` lines when present; `"Apply the research question, {framework} criteria, and tier definitions"`. For systematic plus PICOS with no include/exclude lists, the output is unchanged. |
| `review/vault_text.py` (Methods page) | `## Eligibility criteria ({framework})`, the elements table, then the include and exclude lists. The disclosure-style sentences use the noun and framework name. |
| `review/validate.py` (AI disclosure draft) | `"built from the review's research question and {framework} criteria"`, and the noun where the review is named. |
| `review/report.py` (flowchart) | Title line from the type table above. |
| `review/appraisal.py` | New `CASP-Qual` checklist with 10 items and answers yes / no / can't tell. Item 10 ("How valuable is the research?") is open in the original; here it is phrased yes/no, and the explanation goes in the page text, following the existing CASP-cohort note. |
| `review/config.py` `APPRAISAL_TOOLS` | Add `CASP-Qual`. |
| `prompts/01-setup-interview.md` | New step 1b, review type (five choices with one-line descriptions). Step 2 becomes "Eligibility criteria": propose the type's usual framework, allow another or custom, confirm each element one at a time, then ask for include/exclude rules. Steps for appraisal and validation show the type default as the recommendation. Keyword-group drafting reads from the criteria elements. |
| `docs/03-setup.md` | A short section per review type showing its `review_type` and `criteria` block, with a sentence on when to use it. |
| `README.md`, `docs/faq.md` | One line each saying the template handles scoping, qualitative, collection and methods reviews, not only PICOS systematic reviews. |
| `docs/development.md` | Module map notes for criteria and type defaults. |

Paper pages, extraction columns, tiers, concept axes, the wiki, figures, graph and site are already generic and
do not change.

## Changing course

Changing `review_type` or `criteria` after classification has started changes the prompt fingerprint and
retires the old decisions. This is the same rule as editing PICOS today. The interview warns before making
that kind of change to an existing project, as it already does for PICOS.

## Testing

- The prompt for systematic plus PICOS is byte-identical to the pre-change prompt (pinned for the fixture
  and demo projects), and the demo's expected counts are unchanged.
- A legacy `picos:` file loads as systematic/PICOS. Having both `picos:` and `criteria:` is an error.
- Each framework: required elements enforced, unknown labels rejected (except custom), plain needs include.
- Type defaults: applied when unset, overridden when set (appraisal and validation), unknown type rejected.
- The prompt, Methods page and disclosure use the noun and framework name for a scoping/PCC project with
  include/exclude lists.
- CASP-Qual: the checklist renders on the appraisal page, stubs get its items, and `wiki --check` validates
  answers.
- The flowchart title follows the type.
- A docs test checks that every review type and framework named in `config.py` appears in `docs/03-setup.md`.

## Out of scope

- A second runnable demo.
- MMAT or custom appraisal checklists.
- Frameworks beyond PICOS, PCC and SPIDER (SPICE, ECLIPSE and others can use `custom`).
- Per-type wiki page layouts.
