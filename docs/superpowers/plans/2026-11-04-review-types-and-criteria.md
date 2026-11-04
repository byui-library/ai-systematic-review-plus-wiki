# Review Types and General Criteria Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let researchers run scoping, qualitative, topic-collection, and methods reviews, not only PICOS systematic reviews, by adding a `review_type` and a general `criteria` block.

**Architecture:** `review/config.py` gains the review-type and framework tables, reads a legacy `picos:` block as `criteria` with framework PICOS, applies type defaults beneath the researcher's settings, and validates criteria. Every reader of the old `Project.picos` (the prompt, the Methods page, and the disclosure) switches to `Project.criteria_*`. A systematic review with PICOS keeps a byte-identical prompt, so existing AI decisions survive.

**Tech Stack:** Python 3.11+, PyYAML, pytest. Spec: `docs/superpowers/specs/2026-11-04-review-types-and-criteria-design.md`.

Run tests with `.venv/Scripts/python -m pytest -q` (Windows) from the repo root.

---

## File map

| File | Change |
| --- | --- |
| `review/config.py` | `REVIEW_TYPES`, `FRAMEWORKS`, `LEGACY_PICOS`; `DEFAULTS` gains `review_type` and `criteria` and loses `picos`; `_legacy_picos`, `_type_defaults`, `_criteria_problems`, `_normalise_criteria`; new `Project` properties; `summary` lines; `APPRAISAL_TOOLS` gains `CASP-Qual` |
| `review/prompt.py` | `_criteria_block`, plus the review noun and criteria name in the prompt |
| `review/vault_text.py` | Methods page criteria section |
| `review/validate.py` | Disclosure wording |
| `review/report.py` | Flowchart title |
| `review/appraisal.py` | `CASP-Qual` checklist |
| `prompts/01-setup-interview.md` | Review-type step and criteria step |
| `docs/03-setup.md`, `README.md`, `docs/faq.md`, `docs/development.md` | Docs |
| `tests/test_review_types.py` | New tests (all tasks) |

---

### Task 1: Pin today's prompt

**Files:** Test: `tests/test_review_types.py`

- [ ] **Step 1: Write the pinning test** (it passes now and must keep passing after every later task)

```python
"""Review types and general eligibility criteria (spec: docs/superpowers/specs/2026-11-04-review-types-and-criteria-design.md)."""
import shutil
from pathlib import Path

import pytest
import yaml

from review.config import ConfigError, load_project
from review.prompt import build_prompt, prompt_fingerprint

REPO = Path(__file__).resolve().parent.parent

# Fingerprints of the PICOS prompt before review types existed. They must never change: every saved
# AI decision in an existing project (and the demo's reference decisions) is tied to them.
PINNED = {
    'tests/fixtures/project.yaml': '4b205609fa7b',
    'examples/demo/project.yaml': '34980ce16d9a',
    'project.example.yaml': '4b7660935f75',
}


@pytest.mark.parametrize('source', PINNED)
def test_picos_prompt_is_unchanged(source, tmp_path):
    shutil.copy(REPO / source, tmp_path / 'project.yaml')
    assert prompt_fingerprint(load_project(tmp_path)) == PINNED[source]
```

- [ ] **Step 2: Run it.** `.venv/Scripts/python -m pytest -q tests/test_review_types.py` → 3 passed.
- [ ] **Step 3: Commit.** `git add tests/test_review_types.py && git commit -m "Pin the PICOS screening prompt before adding review types"`

---

### Task 2: Review types, frameworks, and criteria in config

**Files:** Modify: `review/config.py`. Test: `tests/test_review_types.py`

- [ ] **Step 1: Add failing tests** (append to `tests/test_review_types.py`)

```python
def write_project(tmp_path, **changes):
    """The fixture project with its picos block replaced by `changes` (None deletes a key)."""
    data = yaml.safe_load((REPO / 'tests/fixtures/project.yaml').read_text(encoding='utf-8'))
    data.pop('picos')
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    (tmp_path / 'project.yaml').write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    return tmp_path


def problems(tmp_path, **changes):
    with pytest.raises(ConfigError) as err:
        load_project(write_project(tmp_path, **changes))
    return '\n'.join(err.value.problems)


PCC = {'framework': 'PCC', 'elements': {'Population': 'Nursing students', 'Concept': 'Simulation training',
                                        'Context': 'Undergraduate programs'},
       'include': ['Empirical studies of any design'], 'exclude': ['Opinion pieces']}


def test_legacy_picos_reads_as_systematic_picos(tmp_path):
    shutil.copy(REPO / 'tests/fixtures/project.yaml', tmp_path / 'project.yaml')
    project = load_project(tmp_path)
    assert project.review_type == 'systematic' and project.framework == 'PICOS'
    assert project.criteria_elements[0] == ('Population', 'Team sport athletes')
    assert ('Intervention or exposure', 'Wearable tracking (GPS or accelerometer)') in project.criteria_elements


def test_picos_and_criteria_together_is_an_error(tmp_path):
    text = problems(tmp_path, picos={'population': 'x'}, criteria=PCC)
    assert 'both picos and criteria' in text


def test_scoping_pcc_loads_with_type_defaults(tmp_path):
    project = load_project(write_project(tmp_path, review_type='scoping', criteria=PCC))
    assert project.review_noun == 'scoping review' and project.criteria_name == 'PCC'
    assert project.appraisal_tool == 'none'
    assert project.include_rules == ['Empirical studies of any design'] and project.exclude_rules == ['Opinion pieces']
    assert project.flow_title == 'PRISMA-ScR flow diagram'


def test_type_framework_is_the_default(tmp_path):
    project = load_project(write_project(tmp_path, review_type='scoping',
                                         criteria={'elements': PCC['elements']}))
    assert project.framework == 'PCC'


def test_researcher_settings_beat_type_defaults(tmp_path):
    project = load_project(write_project(tmp_path, review_type='collection',
                                         criteria={'framework': 'plain', 'include': ['Any study of X']},
                                         appraisal={'tool': 'AXIS'}))
    assert project.appraisal_tool == 'AXIS'
    assert project.validation['sample_percent'] == 5 and project.validation['min_per_tier'] == 3
    project = load_project(write_project(tmp_path, review_type='collection',
                                         criteria={'framework': 'plain', 'include': ['Any study of X']},
                                         validation={'sample_percent': 20}))
    assert project.validation['sample_percent'] == 20 and project.validation['min_per_tier'] == 3


def test_qualitative_defaults_to_casp_qual(tmp_path):
    project = load_project(write_project(tmp_path, review_type='qualitative', criteria={
        'elements': {'Sample': 'Nurses', 'Phenomenon of interest': 'Burnout'}}))
    assert project.framework == 'SPIDER' and project.appraisal_tool == 'CASP-Qual'


def test_unknown_type_and_framework(tmp_path):
    assert 'review_type must be one of systematic, scoping, qualitative, collection, methods' in \
        problems(tmp_path, review_type='meta', criteria=PCC)
    assert 'criteria.framework must be one of PICOS, PCC, SPIDER, plain, custom' in \
        problems(tmp_path, criteria={**PCC, 'framework': 'SPICE'})


def test_framework_requirements(tmp_path):
    text = problems(tmp_path, criteria={'framework': 'PCC', 'elements': {'Population': 'x', 'Concept': 'y'}})
    assert 'PCC needs Population, Concept and Context (missing: Context)' in text
    text = problems(tmp_path, criteria={**PCC, 'elements': {**PCC['elements'], 'Outcome': 'z'}})
    assert 'criteria.elements has "Outcome", which is not part of PCC; use custom to name your own elements' in text
    assert 'plain criteria need at least one include rule' in problems(tmp_path, criteria={'framework': 'plain'})
    assert 'custom criteria need at least one element' in problems(tmp_path, criteria={'framework': 'custom'})


def test_labels_match_loosely_and_come_out_canonical(tmp_path):
    project = load_project(write_project(tmp_path, criteria={'framework': 'pcc', 'elements': {
        'context': 'Undergraduate programs', 'population': 'Nursing students', 'CONCEPT': 'Simulation'}}))
    assert project.framework == 'PCC'
    assert [k for k, _ in project.criteria_elements] == ['Population', 'Concept', 'Context']


def test_custom_keeps_its_own_labels_in_order(tmp_path):
    project = load_project(write_project(tmp_path, review_type='methods', criteria={
        'elements': {'Method': 'Principal component analysis', 'Data': 'Wearable sensor data'}}))
    assert project.framework == 'custom' and project.criteria_name == 'eligibility'
    assert project.criteria_elements == [('Method', 'Principal component analysis'), ('Data', 'Wearable sensor data')]
```

- [ ] **Step 2: Run them.** `.venv/Scripts/python -m pytest -q tests/test_review_types.py`. Expected: the new tests FAIL with `AttributeError: 'Project' object has no attribute 'review_type'`, or with a ConfigError. Task 1's tests still pass.

- [ ] **Step 3: Implement in `review/config.py`**

Below `HOSTING_TARGETS`, add:

```python
# Each review type sets the wording used in the prompt, Methods page, and disclosure, and the defaults below.
# A default applies only where the researcher's project.yaml leaves the setting out.
REVIEW_TYPES: dict[str, dict] = {
    'systematic': {'noun': 'systematic review', 'framework': 'PICOS', 'appraisal': 'AXIS',
                   'validation': {'sample_percent': 10, 'min_per_tier': 5}, 'flow_title': 'PRISMA 2020 flow diagram'},
    'scoping': {'noun': 'scoping review', 'framework': 'PCC', 'appraisal': 'none',
                'validation': {'sample_percent': 10, 'min_per_tier': 5}, 'flow_title': 'PRISMA-ScR flow diagram'},
    'qualitative': {'noun': 'qualitative evidence synthesis', 'framework': 'SPIDER', 'appraisal': 'CASP-Qual',
                    'validation': {'sample_percent': 10, 'min_per_tier': 5}, 'flow_title': 'PRISMA 2020 flow diagram'},
    'collection': {'noun': 'literature collection', 'framework': 'plain', 'appraisal': 'none',
                   'validation': {'sample_percent': 5, 'min_per_tier': 3}, 'flow_title': 'Flow of records'},
    'methods': {'noun': 'methods review', 'framework': 'custom', 'appraisal': 'none',
                'validation': {'sample_percent': 5, 'min_per_tier': 3}, 'flow_title': 'Flow of records'},
}
# elements: the framework's labels in order (None: the researcher names their own); required: labels that must be filled.
FRAMEWORKS: dict[str, dict] = {
    'PICOS': {'elements': ('Population', 'Intervention or exposure', 'Comparison', 'Outcomes', 'Study design'),
              'required': ()},
    'PCC': {'elements': ('Population', 'Concept', 'Context'), 'required': ('Population', 'Concept', 'Context')},
    'SPIDER': {'elements': ('Sample', 'Phenomenon of interest', 'Design', 'Evaluation', 'Research type'),
               'required': ('Sample', 'Phenomenon of interest')},
    'plain': {'elements': (), 'required': ()},
    'custom': {'elements': None, 'required': ()},
}
NAMED_FRAMEWORKS = ('PICOS', 'PCC', 'SPIDER')
# The original `picos:` block, still accepted: its keys map onto the PICOS labels.
LEGACY_PICOS = {'population': 'Population', 'intervention_or_exposure': 'Intervention or exposure',
                'comparison': 'Comparison', 'outcomes': 'Outcomes', 'study_design': 'Study design'}
```

Change `APPRAISAL_TOOLS` to `('AXIS', 'CASP', 'CASP-Qual', 'JBI', 'RoB2', 'none')`.

In `DEFAULTS`, replace the `'picos': {...}` entry with:

```python
    'review_type': 'systematic',
    'criteria': {'framework': None, 'elements': {}, 'include': [], 'exclude': []},
```

Add these properties to `Project` (replace the `picos` property):

```python
    @property
    def review_type(self) -> str:
        return self.raw['review_type']

    @property
    def review_noun(self) -> str:
        return REVIEW_TYPES[self.review_type]['noun']

    @property
    def flow_title(self) -> str:
        return REVIEW_TYPES[self.review_type]['flow_title']

    @property
    def framework(self) -> str:
        return self.raw['criteria']['framework']

    @property
    def criteria_name(self) -> str:
        """'PICOS', 'PCC' or 'SPIDER'; 'eligibility' for plain and custom criteria."""
        return self.framework if self.framework in NAMED_FRAMEWORKS else 'eligibility'

    @property
    def criteria_elements(self) -> list[tuple[str, str]]:
        return list(self.raw['criteria']['elements'].items())

    @property
    def include_rules(self) -> list[str]:
        return list(self.raw['criteria']['include'])

    @property
    def exclude_rules(self) -> list[str]:
        return list(self.raw['criteria']['exclude'])
```

Add the helpers above `_problems`:

```python
def _label_key(label) -> str:
    return str(label).strip().lower().replace('_', ' ')


def _framework(value) -> str | None:
    """The canonical framework name for a loosely typed one ('pcc' -> 'PCC'); None if unknown."""
    return next((name for name in FRAMEWORKS if isinstance(value, str) and value.strip().lower() == name.lower()), None)


def _review_type(data: dict) -> str:
    kind = data.get('review_type')
    return kind if isinstance(kind, str) and kind in REVIEW_TYPES else 'systematic'


def _legacy_picos(data: dict, problems: list[str]) -> dict:
    """Read an old `picos:` block as `criteria` with framework PICOS."""
    if 'picos' not in data:
        return data
    data = dict(data)
    picos = data.pop('picos')
    if 'criteria' in data:
        problems.append('project.yaml has both picos and criteria: keep criteria and delete the picos section')
        return data
    if picos is None:
        return data
    if not isinstance(picos, dict):
        problems.append('picos should be a section of "name: value" settings')
        return data
    unknown = [k for k in picos if k not in LEGACY_PICOS]
    if unknown:
        problems.append(f'picos contains unknown entries {unknown}; use {list(LEGACY_PICOS)}')
    data['criteria'] = {'framework': 'PICOS',
                        'elements': {LEGACY_PICOS[k]: v for k, v in picos.items() if k in LEGACY_PICOS}}
    return data


def _type_defaults(data: dict) -> dict:
    """DEFAULTS with the review type's own defaults on top; the researcher's settings go on top of this."""
    t = REVIEW_TYPES[_review_type(data)]
    return _merge(DEFAULTS, {'appraisal': {'tool': t['appraisal']}, 'validation': t['validation'],
                             'criteria': {'framework': t['framework']}}, [])


def _filled(elements: dict) -> dict:
    return {str(k).strip(): str(v).strip() for k, v in elements.items() if v is not None and str(v).strip()}


def _criteria_problems(c: dict) -> list[str]:
    name = _framework(c.get('framework'))
    if name is None:
        return [f'criteria.framework must be one of {", ".join(FRAMEWORKS)}']
    elements = c.get('elements') or {}
    if not isinstance(elements, dict):
        return ['criteria.elements should be a section of "label: text" settings']
    p: list[str] = []
    for key in ('include', 'exclude'):
        if any(not isinstance(r, str) or not r.strip() for r in c.get(key) or []):
            p.append(f'criteria.{key} must be a list of rules, for example: {key}: [Peer-reviewed studies]')
    labels = FRAMEWORKS[name]['elements']
    filled = {_label_key(k) for k in _filled(elements)}
    if labels is not None:
        known = {_label_key(label) for label in labels}
        for k in elements:
            if _label_key(k) not in known:
                p.append(f'criteria.elements has "{k}", which is not part of {name}; use custom to name your own '
                         'elements' if labels else f'plain criteria have no elements: move "{k}" into include or '
                                                     'exclude, or use custom')
        required = FRAMEWORKS[name]['required']
        missing = [r for r in required if _label_key(r) not in filled]
        if missing:
            p.append(f'{name} needs {", ".join(required[:-1])} and {required[-1]} (missing: {", ".join(missing)})')
    if name == 'plain' and not any(isinstance(r, str) and r.strip() for r in c.get('include') or []):
        p.append('plain criteria need at least one include rule')
    if name in ('PICOS', 'custom') and not filled:
        p.append(f'{name} criteria need at least one element filled in')
    return p


def _normalise_criteria(c: dict) -> dict:
    """Canonical framework name and labels, framework order, blanks dropped (call after validation)."""
    name = _framework(c['framework'])
    filled = _filled(c.get('elements') or {})
    labels = FRAMEWORKS[name]['elements']
    if labels is not None:
        by_key = {_label_key(k): v for k, v in filled.items()}
        filled = {label: by_key[_label_key(label)] for label in labels if _label_key(label) in by_key}
    return {'framework': name, 'elements': filled,
            'include': [r.strip() for r in c.get('include') or []],
            'exclude': [r.strip() for r in c.get('exclude') or []]}
```

At the top of `_problems`, after the question check, add:

```python
    kind = raw.get('review_type')
    if not isinstance(kind, str) or kind not in REVIEW_TYPES:
        p.append(f'review_type must be one of {", ".join(REVIEW_TYPES)}')
    p += _criteria_problems(raw['criteria'])
```

In `load_project`, replace

```python
    problems: list[str] = []
    raw = _merge(DEFAULTS, data, problems)
```

with

```python
    problems: list[str] = []
    data = _legacy_picos(data, problems)
    raw = _merge(_type_defaults(data), data, problems)
```

and after the `raw['wiki']['deep_tiers']` normalisation add `raw['criteria'] = _normalise_criteria(raw['criteria'])`.

Note: `_merge` keeps the default for `review_type: ` left blank (None), so a blank type means systematic.

- [ ] **Step 4: Find the remaining `picos` readers.** `grep -rn "\.picos" review` lists `prompt.py` and `vault_text.py`; Tasks 3 and 4 replace them. To keep the suite green between commits, do Tasks 2, 3, and 4 before running the whole suite.

---

### Task 3: The screening prompt

**Files:** Modify: `review/prompt.py`. Test: `tests/test_review_types.py`

- [ ] **Step 1: Add the failing test**

```python
def test_scoping_prompt_uses_type_and_framework(tmp_path):
    prompt = build_prompt(load_project(write_project(tmp_path, review_type='scoping', criteria=PCC)))
    assert 'screening papers for a scoping review.' in prompt
    assert 'Apply the research question, PCC criteria, and tier definitions below exactly.' in prompt
    assert 'PCC CRITERIA:\n  Population                : Nursing students\n' in prompt
    assert '  Include:\n    - Empirical studies of any design\n  Exclude:\n    - Opinion pieces\n\nTIERS:' in prompt


def test_plain_prompt_has_rules_only(tmp_path):
    prompt = build_prompt(load_project(write_project(tmp_path, review_type='collection',
                                                     criteria={'framework': 'plain', 'include': ['About X']})))
    assert 'eligibility criteria, and tier definitions' in prompt
    assert 'ELIGIBILITY CRITERIA:\n  Include:\n    - About X\n\nTIERS:' in prompt
```

- [ ] **Step 2: Implement.** In `review/prompt.py`, change the module docstring's "(research question, PICOS," to "(research question, eligibility criteria,", and replace the start of `build_prompt` up to the `return`:

```python
def _criteria_block(project: Project) -> str:
    # PICOS labels are title-cased as they always were, so existing PICOS decisions keep their fingerprint.
    label = str.title if project.framework == 'PICOS' else str
    lines = [f'  {label(k):<26}: {v}' for k, v in project.criteria_elements]
    for title, rules in (('Include', project.include_rules), ('Exclude', project.exclude_rules)):
        if rules:
            lines += [f'  {title}:'] + [f'    - {r}' for r in rules]
    return f'{project.criteria_name.upper()} CRITERIA:\n' + '\n'.join(lines)


def build_prompt(project: Project) -> str:
    tiers = ...  # unchanged
    ids = ...    # unchanged
    choices = ...  # unchanged
    return (
        f'You are a research librarian screening papers for a {project.review_noun}.\n'
        f'Apply the research question, {project.criteria_name} criteria, and tier definitions below exactly.\n\n'
        f'RESEARCH QUESTION:\n  {project.question}\n\n'
        f'{_criteria_block(project)}\n\n'
        f'TIERS:\n\n{tiers}\n\n'
        # ... the rest unchanged
    )
```

(The `picos = ...` line is deleted. Keep the `tiers`, `ids` and `choices` lines and everything after `TIERS` exactly as they are.)

- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest -q tests/test_review_types.py`. All tests pass, including the 3 pinned fingerprints.

---

### Task 4: Methods page, disclosure, flowchart title, summary

**Files:** Modify: `review/vault_text.py`, `review/validate.py`, `review/report.py`, `review/config.py` (`summary`). Test: `tests/test_review_types.py`

- [ ] **Step 1: Add the failing tests**

```python
def test_methods_page_shows_framework_and_rules(tmp_path):
    from review import vault_text
    project = load_project(write_project(tmp_path, review_type='scoping', criteria=PCC))
    text = vault_text.search_and_screening(project, {}, {}, [], [], None)
    assert '## Eligibility criteria (PCC)' in text and '| Concept | Simulation training |' in text
    assert '**Include:**\n\n- Empirical studies of any design\n' in text and '- Opinion pieces' in text
    assert 'the PCC criteria' in text


def test_summary_names_type_and_criteria(tmp_path):
    from review.config import summary
    text = summary(load_project(write_project(tmp_path, review_type='scoping', criteria=PCC)))
    assert 'Review type: scoping review' in text and 'Criteria: PCC (3 elements, 1 include rule, 1 exclude rule)' in text
```

- [ ] **Step 2: Methods page.** In `review/vault_text.py` `search_and_screening`, replace the `picos = markdown_table(...)` statement with:

```python
    criteria = markdown_table(['Element', 'Criterion'], [list(e) for e in project.criteria_elements]) \
        if project.criteria_elements else ''
    for title, rules in (('Include', project.include_rules), ('Exclude', project.exclude_rules)):
        if rules:
            criteria += f'\n**{title}:**\n\n' + ''.join(f'- {r}\n' for r in rules)
    heading = f'Eligibility criteria ({project.framework})' if project.framework in NAMED_FRAMEWORKS \
        else 'Eligibility criteria'
```

Import `NAMED_FRAMEWORKS` from `.config` alongside `Project`. In the f-string, replace

```
## Eligibility criteria (PICOS)

{picos}
```

with

```
## {heading}

{criteria}
```

and replace `from the research question, the PICOS criteria, and the tier definitions below.` with `from the research question, the {project.criteria_name} criteria, and the tier definitions below.`

- [ ] **Step 3: Disclosure.** In `review/validate.py`, replace `"fixed prompt built from the review's research question and PICOS criteria. A one-sentence rationale "` with `f"fixed prompt built from the review's research question and {project.criteria_name} criteria. A one-sentence rationale "`. Also replace `f'Title and abstract screening for *{project.title}* was assisted by '` with `f'Title and abstract screening for the {project.review_noun} *{project.title}* was assisted by '`. Before changing it, check its exact current form with `grep -n "Title and abstract screening" review/validate.py`.

- [ ] **Step 4: Flowchart title.** In `review/report.py` `build_prisma`, before `fig.savefig(...)`, add `fig.suptitle(project.flow_title, fontsize=13, fontweight='bold')`.

- [ ] **Step 5: Summary.** In `review/config.py` `summary`, after the `f'Question: {project.question}',` line, add:

```python
        f'Review type: {project.review_noun}',
        f'Criteria: {project.criteria_name} ({_count(len(project.criteria_elements), "element")}, '
        f'{_count(len(project.include_rules), "include rule")}, {_count(len(project.exclude_rules), "exclude rule")})',
```

and above `summary` add:

```python
def _count(n: int, noun: str) -> str:
    return f'{n} {noun}' + ('' if n == 1 else 's')
```

- [ ] **Step 6: Run the whole suite.** `.venv/Scripts/python -m pytest -q`. Everything passes. If an existing test checks the old disclosure sentence, update its expected text to the new wording and record that in the commit message.
- [ ] **Step 7: Commit Tasks 2–4.** `git add -A && git commit -m "Add review types and general eligibility criteria (PICOS, PCC, SPIDER, plain, custom)"`

---

### Task 5: CASP Qualitative checklist

**Files:** Modify: `review/appraisal.py`. Test: `tests/test_review_types.py`

- [ ] **Step 1: Add the failing test**

```python
def test_casp_qual_checklist():
    from review.appraisal import checklist
    from review.config import APPRAISAL_TOOLS
    tool = checklist('CASP-Qual')
    assert 'CASP-Qual' in APPRAISAL_TOOLS and len(tool['items']) == 10
    assert tool['answers'] == ['yes', 'no', "can't tell"]
```

- [ ] **Step 2: Implement.** Add to `CHECKLISTS` after `'CASP'`:

```python
    'CASP-Qual': {
        'name': 'CASP checklist for qualitative studies',
        'answers': ['yes', 'no', "can't tell"],
        'overall': ['high', 'moderate', 'low'],
        'note': 'CASP question 10 (how valuable is the research) is open in the original; here it is phrased as '
                'yes/no and the explanation goes in the page text.',
        'items': [
            ('q1', 'Was there a clear statement of the aims of the research?'),
            ('q2', 'Is a qualitative methodology appropriate?'),
            ('q3', 'Was the research design appropriate to address the aims of the research?'),
            ('q4', 'Was the recruitment strategy appropriate to the aims of the research?'),
            ('q5', 'Were the data collected in a way that addressed the research issue?'),
            ('q6', 'Has the relationship between researcher and participants been adequately considered?'),
            ('q7', 'Have ethical issues been taken into consideration?'),
            ('q8', 'Was the data analysis sufficiently rigorous?'),
            ('q9', 'Is there a clear statement of findings?'),
            ('q10', 'Is the research valuable (does it add to knowledge, practice, or policy)?'),
        ],
    },
```

- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest -q`. Everything passes. Any existing test that compares `APPRAISAL_TOOLS` with `CHECKLISTS` covers the new entry automatically.
- [ ] **Step 4: Commit.** `git add -A && git commit -m "Add the CASP qualitative appraisal checklist"`

---

### Task 6: Setup interview

**Files:** Modify: `prompts/01-setup-interview.md`. Test: `tests/test_review_types.py`

- [ ] **Step 1: Add the failing test**

```python
def test_setup_interview_covers_types_and_frameworks():
    from review.config import FRAMEWORKS, REVIEW_TYPES
    text = (REPO / 'prompts/01-setup-interview.md').read_text(encoding='utf-8')
    for name in [*REVIEW_TYPES, *FRAMEWORKS, 'CASP-Qual']:
        assert f'`{name}`' in text, name
    assert 'Sets `picos`' not in text
```

- [ ] **Step 2: Implement.** In `prompts/01-setup-interview.md`:

Replace question 2 with:

```markdown
2. **Review type.** Ask what kind of project this is, with one line on each:
   - `systematic`: a systematic review of effects or associations (PICOS).
   - `scoping`: maps what research exists on a topic (PCC).
   - `qualitative`: a synthesis of qualitative evidence on experiences or perceptions (SPIDER).
   - `collection`: a topic collection or annotated bibliography, with plain include and exclude rules.
   - `methods`: a review of how studies use a method, theory, instrument, or technology (custom elements).

   Sets `review_type`. The type also sets defaults that later questions recommend: the appraisal tool and the validation sample.
3. **Eligibility criteria.** Propose the type's usual framework (`PICOS`, `PCC`, `SPIDER`, `plain`, or `custom`) and say they may pick another one. Draft each element from the question and confirm the elements one at a time:
   - `PICOS`: Population, Intervention or exposure, Comparison (may be blank), Outcomes, Study design.
   - `PCC`: Population, Concept, Context (all three needed).
   - `SPIDER`: Sample, Phenomenon of interest (both needed), Design, Evaluation, Research type.
   - `custom`: agree 2–5 element names with them (for example Method, Data, Setting), then fill each one.
   - `plain`: no elements.

   Then ask for any **include** and **exclude** rules (required for `plain`, optional otherwise), for example "Empirical studies of any design" or "Opinion pieces". Sets `criteria` (`framework`, `elements`, `include`, `exclude`).
```

Renumber the following questions by one (the old 3 becomes 4, ..., the old 14 becomes 15), and update the two references to "step 13" (in question 14 and in Rules) to "step 14".

In the keyword prescreen question, replace "Draft 2–4 keyword groups from the PICOS" with "Draft 2–4 keyword groups from the criteria elements and include rules".

In the validation sample question, replace "Recommend 10% of each tier with at least 5 per tier" with "Recommend the review type's default (10% of each tier with at least 5 per tier; 5% with at least 3 for `collection` and `methods`)".

Replace the quality appraisal question's offer sentence with: "Offer AXIS (cross-sectional studies), JBI (analytical cross-sectional), CASP (cohort), `CASP-Qual` (qualitative studies), RoB2 (randomised trials), or none. Recommend the review type's default (AXIS for systematic, `CASP-Qual` for qualitative, none for scoping, collection and methods) unless their expected study designs suggest another."

In the outputs question, change "a PRISMA flowchart (off by default)" to "a flowchart of records (PRISMA 2020 for systematic and qualitative reviews, PRISMA-ScR for scoping reviews; off by default)".

In Rules, replace "Changing the question, PICOS, or tiers" with "Changing the question, review type, criteria, or tiers".

In "If `project.yaml` already exists" guidance, add: "An older file may have a `picos:` section instead of `criteria:`. It still works; leave it unless they want to change the criteria, and then replace it with a `criteria:` section with `framework: PICOS`."

- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest -q tests/test_review_types.py tests/test_playbooks.py`. Everything passes.
- [ ] **Step 4: Commit.** `git add -A && git commit -m "Ask for the review type and criteria framework in the setup interview"`

---

### Task 7: Researcher and developer docs

**Files:** Modify: `docs/03-setup.md`, `README.md`, `docs/faq.md`, `docs/development.md`. Test: `tests/test_review_types.py`

- [ ] **Step 1: Add the failing test**

```python
def test_setup_doc_shows_every_type_and_framework():
    from review.config import FRAMEWORKS, REVIEW_TYPES
    text = (REPO / 'docs/03-setup.md').read_text(encoding='utf-8')
    for name in [*REVIEW_TYPES, *FRAMEWORKS]:
        assert name in text, name
```

- [ ] **Step 2: `docs/03-setup.md`.** In the interview list, replace item 2 with two items, "The kind of review (systematic, scoping, qualitative evidence, topic collection, or methods review)" and "Eligibility criteria, in the framework that fits (PICOS, PCC, SPIDER, plain include/exclude rules, or your own elements)", and renumber the list (1–15). In "Changing things later", replace "research question, PICOS, or tier definitions" with "research question, review type, criteria, or tier definitions". Then add, before "## Library credentials":

````markdown
## Review types and criteria

You don't need to write any of this by hand: the interview does it. This section is for reading or hand-editing `project.yaml`.

`review_type` sets the wording the AI and your Methods page use, and sensible defaults you can change:

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

An older `picos:` section (with `population:`, `intervention_or_exposure:` and so on) still works and means the same thing.

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
````

- [ ] **Step 3: `README.md`.** After the sentence "It works with any research question and any database that can export RIS or CSV.", add: "It handles systematic reviews (PICOS), scoping reviews (PCC), qualitative evidence syntheses (SPIDER), topic collections, and methods reviews: [choose a type](docs/03-setup.md#review-types-and-criteria)."

- [ ] **Step 4: `docs/faq.md`.** Add a question:

```markdown
## My project isn't a PICOS systematic review. Can I still use this?

Yes. Tell the assistant what kind of project it is when it sets up your review: a scoping review (PCC), a qualitative evidence synthesis (SPIDER), a topic collection with plain include and exclude rules, or a methods review with your own criteria. The wording, the defaults, and the Methods page follow your choice. See [Review types and criteria](03-setup.md#review-types-and-criteria).
```

- [ ] **Step 5: `docs/development.md`.** In the module map row for `config.py`, add: "`REVIEW_TYPES` and `FRAMEWORKS` (type defaults are merged under the researcher's settings; a legacy `picos:` block is read as `criteria` with framework PICOS)". In the `prompt.py` row, change "(question, PICOS, tiers," to "(question, review type, criteria, tiers,", and add: "The PICOS prompt is pinned by fingerprint in `tests/test_review_types.py`; never change its wording."

- [ ] **Step 6: Run** `.venv/Scripts/python -m pytest -q`. Everything passes.
- [ ] **Step 7: Commit.** `git add -A && git commit -m "Document review types and criteria frameworks"`

---

### Task 8: Check end to end and open the PR

- [ ] **Step 1:** In the scratchpad, copy the demo, change it to `review_type: scoping` with a PCC `criteria` block (replacing `picos`), and run `py run.py --root <copy> check-config`. The summary shows "Review type: scoping review" and "Criteria: PCC (...)". Run `classify --next-batch` and confirm that `data/classify_batch.json` holds the prompt and that it says "scoping review" and "PCC CRITERIA".
- [ ] **Step 2:** Run the unchanged demo (`py run.py demo`, then its listed steps). The expected counts are unchanged, and the reference decisions are still current: `validate --score` works without re-classifying.
- [ ] **Step 3:** Push the `review-types` branch and open a PR with the summary and test plan, ending with the attribution line.
