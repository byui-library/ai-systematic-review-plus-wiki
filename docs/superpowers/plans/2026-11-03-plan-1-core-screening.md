# Plan 1: Core Screening Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, config-driven pipeline that covers import → dedupe → prescreen → AI classify → human validation → report, for any research question defined in `project.yaml`.

**Architecture:** A `review/` Python package that `run.py` drives (argparse subcommands). Python handles all file I/O. An AI agent only reads `data/classify_batch.json` and writes `data/classify_results.json`, which `run.py classify --save` validates before saving. State lives in `data/*.json`, and every write is atomic. The code is ported from the Flynn Research `Search Results/pipeline/` package, with all sports-specific constants replaced by `project.yaml`.

**Tech Stack:** Python ≥ 3.11, PyYAML, openpyxl, matplotlib (PRISMA only), pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-ai-systematic-review-plus-wiki-design.md` (§2–4, §8, §10)

**Later plans (not in this one):** Plan 2 covers PDFs and the wiki (`pdfs`, `wiki`, `figures`, `graph`). Plan 3 covers the site, publishing, the remaining playbooks, the docs, setup scripts and the demo.

---

## File map

| File | Responsibility |
| --- | --- |
| `setup/requirements.txt` | Pinned-minimum dependencies |
| `pytest.ini` | Test discovery; puts the repo root on `sys.path` |
| `review/__init__.py` | Package marker |
| `review/errors.py` | `PipelineError`: a message plus a list of problems, shown to non-coders |
| `review/io.py` | `read_json`, atomic `write_json`, `now_iso` |
| `review/config.py` | `Paths` (all file locations), `load_project` (defaults + validation), `summary` |
| `review/importers/common.py` | `make_record`, `normalize_doi`, `map_language`, `split_list`, `year_from`, `detect_format` |
| `review/importers/pubmed.py` / `wos.py` / `ebsco.py` / `ris.py` / `csv_generic.py` | One parser per export format |
| `review/importers/__init__.py` | `PARSERS`, `import_exports` |
| `review/dedup.py` | `deduplicate`: DOI → PMID → title+year, keeping `sources[]` |
| `review/screen.py` | `pre_filter`, `score_record`, `prescreen` |
| `review/state.py` | Stage list, `mark_done`, `clear_from`, `next_stage`, `status_text` |
| `review/classify.py` | `build_prompt`, `next_batch`, `validate_results`, `save_results`, `progress` |
| `review/validate.py` | `draw_sample`, `score_sample`, `cohen_kappa`, `write_disclosure` |
| `review/report.py` | `collect`, CSVs, Excel workbook, optional PRISMA, `run_report` |
| `run.py` | CLI entry point |
| `project.example.yaml` | A fully commented example project (education topic, discipline-neutral) |
| `prompts/02-classify.md` | The agent playbook for the classify loop |
| `.github/workflows/tests.yml` | CI on Windows and Ubuntu |
| `tests/fixture_exports.py` | Synthetic exports in all 5 formats (10 raw records, 8 unique) |
| `tests/fixtures/project.yaml` | Test project |
| `tests/helpers.py` | Canned tier decisions + validation-sheet filler |
| `tests/conftest.py` | `workspace`, `prescreened`, `classified` fixtures |

**Fixture facts used by many tests.** There are 10 raw records: pubmed 3, wos 2, ebsco 2, ris 2, csv 1. Deduplication leaves 8 unique records:
- WoS #1 duplicates PubMed #1 by DOI.
- EBSCO E1 duplicates WoS #2 by title+year.

The pre-filter removes 2, leaving 6 kept:
- the PubMed editorial `pmid:10000002`
- the EBSCO conference abstract `ebsco:E2`

The keyword prescreen excludes 2 (`doi:10.1000/example.003` and the RIS record with no DOI), which leaves 4 candidates:

| Candidate | Score |
| --- | --- |
| `doi:10.1000/example.001` | 5 |
| `doi:10.1000/example.005` | 5 |
| `doi:10.1000/example.006` | 5 |
| `doi:10.1000/example.004` | 4 |

Canned tiers used in tests:

| Candidate | Tier |
| --- | --- |
| 001 | 1 |
| 005 | 2 |
| 004 | 3 |
| 006 | 4 |

All commands below run from the repo root (`C:\Users\milesm\Documents\repos\ai-systematic-review-plus-wiki`) in Git Bash. `PY` means `.venv/Scripts/python`.

---

### Task 1: Scaffold, errors, JSON I/O, and test fixtures

**Files:**
- Create: `setup/requirements.txt`, `pytest.ini`, `review/__init__.py`, `review/errors.py`, `review/io.py`
- Create: `tests/__init__.py`, `tests/fixture_exports.py`, `tests/fixtures/project.yaml`, `tests/conftest.py`
- Test: `tests/test_io.py`

- [ ] **Step 1: Create the venv and dependency files**

`setup/requirements.txt`:
```text
pyyaml>=6.0
openpyxl>=3.1
matplotlib>=3.8
pytest>=8.0
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

Run: `py -3.13 -m venv .venv && .venv/Scripts/python -m pip install -q -r setup/requirements.txt`
Expected: exits 0.

- [ ] **Step 2: Write the failing test** — `tests/test_io.py`

```python
from review.errors import PipelineError
from review.io import now_iso, read_json, write_json


def test_write_json_roundtrip_and_no_temp_left(tmp_path):
    target = tmp_path / 'a' / 'b.json'
    write_json(target, {'x': 'é'})
    assert read_json(target) == {'x': 'é'}
    assert not list(target.parent.glob('*.tmp'))


def test_read_json_default_when_missing(tmp_path):
    assert read_json(tmp_path / 'none.json', []) == []
    assert read_json(tmp_path / 'none.json') is None


def test_now_iso_is_utc():
    assert now_iso().endswith('+00:00')


def test_pipeline_error_lists_problems():
    err = PipelineError('Bad:', ['a', 'b'])
    assert str(err) == 'Bad:\n  - a\n  - b'
    assert err.problems == ['a', 'b']
```

Create an empty `tests/__init__.py` and `review/__init__.py` (docstring only: `"""AI systematic review pipeline."""`).

- [ ] **Step 3: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_io.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review.errors'`

- [ ] **Step 4: Implement**

`review/errors.py`:
```python
"""The single error type the CLI turns into a friendly message."""
from __future__ import annotations


class PipelineError(Exception):
    """A problem the researcher (or agent) can fix. `problems` lists each one."""

    def __init__(self, message: str, problems: list[str] | None = None):
        self.message = message
        self.problems = list(problems or [])
        detail = ''.join(f'\n  - {p}' for p in self.problems)
        super().__init__(message + detail)
```

`review/io.py`:
```python
"""JSON helpers. Every write is atomic (temp file + rename) so a crash never leaves half a file."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')
```

- [ ] **Step 5: Run the test and confirm it passes**

Run: `PY -m pytest tests/test_io.py -q`
Expected: `4 passed`

- [ ] **Step 6: Add the shared fixtures**

`tests/fixtures/project.yaml`:
```yaml
project:
  title: Test review of workload metric structure
  short_name: test-review
  researcher: Test Researcher
question: How do studies examine the structure of wearable-derived workload metrics in team sports?
picos:
  population: Team sport athletes
  intervention_or_exposure: Wearable tracking (GPS or accelerometer)
  outcomes: Structure of workload metrics
  study_design: Peer-reviewed original research or reviews
sources: [pubmed, wos, ebsco, ris, csv]
prescreen:
  threshold: 1
  keyword_groups:
    - name: technology
      weight: 1
      terms: [gps, accelerometer, wearable]
    - name: sport
      weight: 1
      terms: [soccer, rugby, basketball, hockey, futsal]
    - name: analysis
      weight: 3
      terms: [principal component, factor analysis, correlation matrix, redundan, dimensionality]
tiers:
  - {id: 1, label: Core Match, included: true, definition: Metric structure analysis is the central aim.}
  - {id: 2, label: Strong Match, included: true, definition: Metric structure is a secondary analysis.}
  - {id: 3, label: Peripheral, included: false, definition: Uses wearables in team sport but no structure analysis.}
  - {id: 4, label: Exclude, included: false, definition: Off topic.}
validation: {sample_percent: 10, min_per_tier: 5, seed: 42}
concept_axes: [methods, metrics, sports]
```

`tests/fixture_exports.py`:
```python
"""Synthetic exports in every supported format. 10 raw records -> 8 unique."""
from __future__ import annotations

import csv
from pathlib import Path

NBIB = """PMID- 10000001
TI  - Principal component analysis of workload metrics in collegiate
      soccer players.
AB  - We applied principal component analysis to GPS-derived workload metrics
      in 40 collegiate soccer players.
AU  - Doe J
AU  - Roe R
JT  - Journal of Example Science
DP  - 2021 Mar
LA  - eng
PT  - Journal Article
MH  - *Principal Component Analysis
OT  - workload
AID - 10.1000/example.001 [doi]

PMID- 10000002
TI  - An editorial on wearables.
AB  - Opinion piece about wearables.
AU  - Smith A
JT  - Journal of Example Science
DP  - 2020
LA  - eng
PT  - Editorial

PMID- 10000003
TI  - Effects of diet on cardiac outcomes in older adults.
AB  - Randomized trial of a dietary intervention in older adults.
AU  - Lee K
JT  - Clinical Example
DP  - 2019
LA  - eng
PT  - Journal Article
AID - 10.1000/example.003 [doi]
"""

WOS_HEADER = ['PT', 'AU', 'TI', 'SO', 'LA', 'DT', 'DE', 'ID', 'AB', 'PY', 'DI', 'PM', 'UT']
WOS_ROWS = [
    ['J', 'Doe, J; Roe, R',
     'Principal component analysis of workload metrics in collegiate soccer players.',
     'JOURNAL OF EXAMPLE SCIENCE', 'English', 'Article', 'workload', '',
     'We applied principal component analysis to GPS-derived workload metrics.',
     '2021', '10.1000/EXAMPLE.001', '10000001', 'WOS:0001'],
    ['J', 'Park, S', 'Factor analysis of external load in rugby union',
     'EXAMPLE SPORTS JOURNAL', 'English', 'Article', 'external load', '',
     'Factor analysis of external load variables in 30 rugby union players.',
     '2022', '10.1000/example.004', '', 'WOS:0002'],
]

EBSCO_HEADER = ['an', 'title', 'abstract', 'contributors', 'source', 'doi', 'publicationDate',
                'docTypes', 'isiType', 'pubTypes', 'language', 'subjects']
EBSCO_ROWS = [
    ['E1', 'Factor Analysis of External Load in Rugby Union',
     'Factor analysis of external load variables.', 'Park, S', 'Example Sports Journal', '',
     '20220115', 'Article', 'JOUR', 'Academic Journal', 'English', 'external load'],
    ['E2', 'Conference abstract on futsal load', 'Abstract of a talk on futsal GPS load.',
     'Ng, T', 'Proceedings', '', '20230601', 'Abstract', 'ABST', '', 'English', ''],
]

RIS = """TY  - JOUR
AU  - Kim, H
TI  - Redundancy in GPS workload variables: a correlation matrix approach
AB  - Correlation matrix analysis of 12 GPS workload variables
  in basketball.
PY  - 2023
DO  - 10.1000/example.005
JO  - Example Sports Journal
LA  - English
KW  - workload
KW  - correlation
ER  - 
TY  - JOUR
TI  - Teaching statistics with games
AB  - A classroom report.
PY  - 2018
ER  - 
"""

SCOPUS_HEADER = ['Authors', 'Title', 'Year', 'Source title', 'DOI', 'Abstract', 'Author Keywords',
                 'Language of Original Document', 'Document Type', 'EID']
SCOPUS_ROWS = [
    ['Ito, M', 'Dimensionality of training load in field hockey', '2024', 'Example Hockey Review',
     '10.1000/example.006',
     'We examined the dimensionality of accelerometer-derived training load in field hockey.',
     'training load; accelerometer', 'English', 'Article', '2-s2.0-1'],
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def write_exports(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'pubmed.nbib').write_text(NBIB, encoding='utf-8')
    wos = '\n'.join('\t'.join(row) for row in [WOS_HEADER, *WOS_ROWS]) + '\n'
    (directory / 'wos.txt').write_text(wos, encoding='utf-8')
    _write_csv(directory / 'ebsco.csv', EBSCO_HEADER, EBSCO_ROWS)
    (directory / 'export.ris').write_text(RIS, encoding='utf-8')
    _write_csv(directory / 'scopus.csv', SCOPUS_HEADER, SCOPUS_ROWS)
```

(`tests/conftest.py` is created in Task 2, because it imports `review.config`.)

- [ ] **Step 7: Commit**

```bash
git add setup/requirements.txt pytest.ini review tests
git commit -m "Scaffold package, JSON I/O, and synthetic export fixtures"
```

---

### Task 2: Project configuration (`review/config.py`)

**Files:**
- Create: `review/config.py`, `tests/conftest.py`
- Test: `tests/test_config.py`

- [ ] **Step 0: Create `tests/conftest.py`** (this task adds `workspace` only; Tasks 8 and 9 add more fixtures)

```python
import shutil
from pathlib import Path

import pytest

from review.config import Paths
from tests.fixture_exports import write_exports

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def workspace(tmp_path):
    shutil.copy(FIXTURES / 'project.yaml', tmp_path / 'project.yaml')
    write_exports(tmp_path / 'data' / 'exports')
    return Paths(tmp_path)
```

- [ ] **Step 1: Write the failing test** — `tests/test_config.py`

```python
import pytest
import yaml

from review.config import ConfigError, Paths, load_project, summary


def _edit(paths: Paths, change) -> None:
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    change(data)
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')


def test_loads_fixture_with_defaults(workspace):
    project = load_project(workspace.root)
    assert project.included_tier_ids == [1, 2]
    assert project.tier_ids == [1, 2, 3, 4]
    assert project.keyword_groups[2].weight == 3
    assert project.exclude['conference_abstracts'] is True
    assert project.batch_size == 50
    assert project.outputs['prisma'] is False


def test_missing_file_gives_setup_hint(tmp_path):
    with pytest.raises(ConfigError) as err:
        load_project(tmp_path)
    assert 'set up my review' in str(err.value)


def test_collects_every_problem_at_once(workspace):
    def change(d):
        d['question'] = ''
        d['tiers'] = [{'id': 1, 'label': 'Only', 'included': False, 'definition': 'x'}]
        d['sources'] = ['pubmed', 'scopus']
        d['appraisal'] = {'tool': 'Nope'}
    _edit(workspace, change)
    with pytest.raises(ConfigError) as err:
        load_project(workspace.root)
    text = '\n'.join(err.value.problems)
    for fragment in ['question is empty', 'between 2 and 6', 'at least one tier must have included: true',
                     "unknown entries ['scopus']", 'appraisal.tool must be one of']:
        assert fragment in text


def test_keyword_terms_lowercased_with_spaces_kept(workspace):
    _edit(workspace, lambda d: d['prescreen']['keyword_groups'][0].update(terms=[' PCA ']))
    assert load_project(workspace.root).keyword_groups[0].terms == (' pca ',)


def test_tier_lookup_and_summary(workspace):
    project = load_project(workspace.root)
    assert project.tier(3).label == 'Peripheral'
    text = summary(project)
    assert 'Core Match' in text and 'included' in text and 'PRISMA flowchart: off' in text


def test_paths_layout(tmp_path):
    paths = Paths(tmp_path)
    assert paths.exports == tmp_path.resolve() / 'data' / 'exports'
    assert paths.checkpoint.name == 'checkpoint.json'
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review.config'`

- [ ] **Step 3: Implement** — `review/config.py`

```python
"""Load project.yaml, fill in defaults, validate it, and define every file location."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import PipelineError

KNOWN_SOURCES = ('pubmed', 'wos', 'ebsco', 'ris', 'csv')
APPRAISAL_TOOLS = ('AXIS', 'CASP', 'JBI', 'RoB2', 'none')
HOSTING_TARGETS = ('local', 'github_pages', 'openequella')

DEFAULTS: dict = {
    'project': {'title': '', 'short_name': 'review', 'researcher': '', 'institution': '', 'ai_operator': ''},
    'question': '',
    'picos': {'population': '', 'intervention_or_exposure': '', 'comparison': '', 'outcomes': '',
              'study_design': ''},
    'sources': list(KNOWN_SOURCES),
    'prescreen': {
        'keyword_groups': [],
        'threshold': 1,
        'exclude': {'retracted': True, 'editorials': True, 'conference_abstracts': True,
                    'non_english': True, 'no_abstract': True},
    },
    'tiers': [],
    'validation': {'sample_percent': 10, 'min_per_tier': 5, 'seed': 42},
    'extraction_columns': [],
    'concept_axes': [],
    'appraisal': {'tool': 'AXIS'},
    'outputs': {'prisma': False, 'figures': True, 'knowledge_graph': True},
    'pdfs': {'libkey': True, 'unpaywall': True},
    'site': {'title': '', 'targets': ['local']},
    'classify': {'batch_size': 50},
}


class ConfigError(PipelineError):
    def __init__(self, problems: list[str]):
        super().__init__('project.yaml needs attention:', problems)


class Paths:
    """Every file the pipeline reads or writes, relative to one project root."""

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.project_yaml = self.root / 'project.yaml'
        self.data = self.root / 'data'
        self.exports = self.data / 'exports'
        self.records = self.data / 'records.json'
        self.stats = self.data / 'stats.json'
        self.prefilter_excluded = self.data / 'prefilter_excluded.json'
        self.prescreen_excluded = self.data / 'prescreen_excluded.json'
        self.candidates = self.data / 'candidates.json'
        self.checkpoint = self.data / 'checkpoint.json'
        self.classify_batch = self.data / 'classify_batch.json'
        self.classify_results = self.data / 'classify_results.json'
        self.validation_xlsx = self.data / 'validation.xlsx'
        self.validation_sample = self.data / 'validation_sample.json'
        self.validation_results = self.data / 'validation_results.json'
        self.ai_disclosure = self.data / 'ai_disclosure.md'
        self.results_xlsx = self.data / 'Results.xlsx'
        self.included_csv = self.data / 'included.csv'
        self.excluded_csv = self.data / 'excluded.csv'
        self.prisma_png = self.data / 'prisma.png'
        self.state = self.data / 'state.json'
        self.wiki = self.root / 'wiki'


@dataclass(frozen=True)
class Tier:
    id: int
    label: str
    included: bool
    definition: str


@dataclass(frozen=True)
class KeywordGroup:
    name: str
    weight: int
    terms: tuple[str, ...]


@dataclass(frozen=True)
class Project:
    raw: dict
    tiers: tuple[Tier, ...]
    keyword_groups: tuple[KeywordGroup, ...]

    @property
    def title(self) -> str:
        return self.raw['project']['title']

    @property
    def question(self) -> str:
        return self.raw['question']

    @property
    def picos(self) -> dict:
        return self.raw['picos']

    @property
    def sources(self) -> list[str]:
        return list(self.raw['sources'])

    @property
    def threshold(self) -> int:
        return int(self.raw['prescreen']['threshold'])

    @property
    def exclude(self) -> dict:
        return self.raw['prescreen']['exclude']

    @property
    def validation(self) -> dict:
        return self.raw['validation']

    @property
    def outputs(self) -> dict:
        return self.raw['outputs']

    @property
    def batch_size(self) -> int:
        return int(self.raw['classify']['batch_size'])

    @property
    def tier_ids(self) -> list[int]:
        return [t.id for t in self.tiers]

    @property
    def included_tier_ids(self) -> list[int]:
        return [t.id for t in self.tiers if t.included]

    def tier(self, tier_id: int) -> Tier:
        for t in self.tiers:
            if t.id == tier_id:
                return t
        raise KeyError(tier_id)


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def _problems(raw: dict) -> list[str]:
    p: list[str] = []
    if not str(raw['project'].get('title') or '').strip():
        p.append('project.title is empty')
    if not str(raw.get('question') or '').strip():
        p.append('question is empty: write your research question')

    sources = raw.get('sources') or []
    if not sources:
        p.append('sources is empty: list the databases you exported from')
    unknown = [s for s in sources if s not in KNOWN_SOURCES]
    if unknown:
        p.append(f'sources contains unknown entries {unknown}; choose from {list(KNOWN_SOURCES)}')

    groups = raw['prescreen'].get('keyword_groups') or []
    if not groups:
        p.append('prescreen.keyword_groups is empty: add at least one group of search terms')
    for i, g in enumerate(groups):
        if not isinstance(g, dict) or not g.get('name'):
            p.append(f'prescreen.keyword_groups[{i}] needs a name')
            continue
        weight = g.get('weight', 1)
        if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
            p.append(f"keyword group '{g['name']}' weight must be a whole number of 1 or more")
        if not g.get('terms'):
            p.append(f"keyword group '{g['name']}' has no terms")

    tiers = raw.get('tiers') or []
    if not 2 <= len(tiers) <= 6:
        p.append(f'tiers must have between 2 and 6 entries (found {len(tiers)})')
    ids = []
    for i, t in enumerate(tiers):
        if not isinstance(t, dict) or not isinstance(t.get('id'), int) or isinstance(t.get('id'), bool):
            p.append(f'tiers[{i}] needs a whole-number id')
            continue
        ids.append(t['id'])
        if not str(t.get('label') or '').strip():
            p.append(f"tier {t['id']} needs a label")
        if not str(t.get('definition') or '').strip():
            p.append(f"tier {t['id']} needs a definition")
    if len(ids) != len(set(ids)):
        p.append('tier ids must be unique')
    if tiers and not any(isinstance(t, dict) and t.get('included') for t in tiers):
        p.append('at least one tier must have included: true')

    axes = raw.get('concept_axes') or []
    if axes and not 2 <= len(axes) <= 4:
        p.append(f'concept_axes should list 2 to 4 axes (found {len(axes)})')
    if raw['appraisal'].get('tool') not in APPRAISAL_TOOLS:
        p.append(f'appraisal.tool must be one of {list(APPRAISAL_TOOLS)}')
    bad_targets = [t for t in raw['site'].get('targets') or [] if t not in HOSTING_TARGETS]
    if bad_targets:
        p.append(f'site.targets contains unknown entries {bad_targets}; choose from {list(HOSTING_TARGETS)}')
    pct = raw['validation'].get('sample_percent')
    if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not 0 < pct <= 100:
        p.append('validation.sample_percent must be a number between 1 and 100')
    return p


def load_project(root: Path | str) -> Project:
    paths = Paths(root)
    if not paths.project_yaml.exists():
        raise ConfigError([
            f'No project.yaml found in {paths.root}. Ask your AI assistant to "set up my review", '
            'or copy project.example.yaml to project.yaml and edit it.'
        ])
    try:
        data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8')) or {}
    except yaml.YAMLError as exc:
        raise ConfigError([f'project.yaml is not valid YAML: {exc}']) from exc
    if not isinstance(data, dict):
        raise ConfigError(['project.yaml must be a set of "name: value" settings'])

    raw = _merge(DEFAULTS, data)
    problems = _problems(raw)
    if problems:
        raise ConfigError(problems)

    tiers = tuple(sorted(
        (Tier(int(t['id']), str(t['label']).strip(), bool(t.get('included', False)),
              str(t['definition']).strip()) for t in raw['tiers']),
        key=lambda t: t.id,
    ))
    groups = tuple(
        KeywordGroup(str(g['name']), int(g.get('weight', 1)), tuple(str(x).lower() for x in g['terms']))
        for g in raw['prescreen']['keyword_groups']
    )
    return Project(raw=raw, tiers=tiers, keyword_groups=groups)


def summary(project: Project) -> str:
    v = project.validation
    lines = [
        f'Project: {project.title}',
        f'Question: {project.question}',
        '',
        'Sources: ' + ', '.join(project.sources),
        '',
        f'Keyword groups (papers need a score of {project.threshold} or more):',
    ]
    for g in project.keyword_groups:
        lines.append(f'  - {g.name} (weight {g.weight}): {len(g.terms)} terms')
    lines += ['', 'Tiers:']
    for t in project.tiers:
        lines.append(f"  {t.id}. {t.label} ({'included' if t.included else 'excluded'})")
    lines += [
        '',
        f"Validation sample: {v['sample_percent']}% of each tier (at least {v['min_per_tier']})",
        f"PRISMA flowchart: {'on' if project.outputs.get('prisma') else 'off'}",
    ]
    return '\n'.join(lines)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_config.py tests/test_io.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add review/config.py tests/test_config.py
git commit -m "Add project.yaml loading with defaults and plain-English validation"
```

---

### Task 3: Common record shape + PubMed, WoS, and EBSCO parsers

**Files:**
- Create: `review/importers/__init__.py` (temporary: `PARSERS` only), `review/importers/common.py`, `review/importers/pubmed.py`, `review/importers/wos.py`, `review/importers/ebsco.py`
- Test: `tests/test_importers.py`

- [ ] **Step 1: Write the failing test** — `tests/test_importers.py`

```python
from review.importers import PARSERS
from review.importers.common import detect_format, make_record, normalize_doi


def test_detects_each_format(workspace):
    ex = workspace.exports
    assert detect_format(ex / 'pubmed.nbib') == 'pubmed'
    assert detect_format(ex / 'wos.txt') == 'wos'
    assert detect_format(ex / 'ebsco.csv') == 'ebsco'
    assert detect_format(ex / 'export.ris') == 'ris'
    assert detect_format(ex / 'scopus.csv') == 'csv'


def test_unknown_format_is_none(tmp_path):
    f = tmp_path / 'notes.txt'
    f.write_text('hello world', encoding='utf-8')
    assert detect_format(f) is None


def test_normalize_doi_and_make_record():
    assert normalize_doi('https://doi.org/10.1/ABC ') == '10.1/abc'
    rec = make_record('ris', title='  A   title ', doi='doi:10.1/X')
    assert rec['title'] == 'A title' and rec['doi'] == '10.1/x' and rec['language'] == 'eng'


def test_pubmed_fields(workspace):
    recs = PARSERS['pubmed'](workspace.exports / 'pubmed.nbib')
    assert len(recs) == 3
    r = recs[0]
    assert r['title'] == 'Principal component analysis of workload metrics in collegiate soccer players.'
    assert (r['doi'], r['pmid'], r['year']) == ('10.1000/example.001', '10000001', '2021')
    assert 'Principal Component Analysis' in r['keywords'] and 'workload' in r['keywords']
    assert recs[1]['pub_types'] == ['Editorial']


def test_wos_fields(workspace):
    recs = PARSERS['wos'](workspace.exports / 'wos.txt')
    assert len(recs) == 2
    assert recs[0]['doi'] == '10.1000/example.001'
    assert recs[0]['language'] == 'eng'
    assert recs[0]['pub_types'] == ['Journal Article']
    assert recs[0]['authors'] == 'Doe, J; Roe, R'


def test_ebsco_fields(workspace):
    recs = PARSERS['ebsco'](workspace.exports / 'ebsco.csv')
    assert recs[0]['year'] == '2022' and recs[0]['source_id'] == 'E1'
    assert 'Abstract' in recs[1]['pub_types']
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_importers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review.importers'`

- [ ] **Step 3: Implement**

`review/importers/common.py`:
```python
"""The common record shape every importer produces, plus format detection."""
from __future__ import annotations

import csv
import re
from pathlib import Path

csv.field_size_limit(2**31 - 1)   # long abstracts in database CSV/TSV exports

SUPPORTED_HELP = (
    'Supported exports: PubMed ("PubMed" format .nbib/.txt), Web of Science (tab-delimited), '
    'EBSCO CSV (SPORTDiscus, CINAHL, ERIC, ...), RIS (Scopus, ERIC, PsycINFO, Zotero, EndNote, ...), '
    'or any CSV with a Title column.'
)

_FIELDS = {
    'source': '', 'source_id': '', 'pmid': '', 'doi': '', 'title': '', 'abstract': '', 'authors': '',
    'journal': '', 'year': '', 'language': 'eng', 'pub_types': [], 'keywords': [],
}
_TEXT_FIELDS = ('source_id', 'pmid', 'title', 'abstract', 'authors', 'journal', 'year', 'language')


def normalize_doi(doi: str) -> str:
    s = (doi or '').strip().lower()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'https://dx.doi.org/', 'http://dx.doi.org/', 'doi:'):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.strip()


def map_language(value: str) -> str:
    v = (value or '').strip().lower()
    if v in ('', 'english', 'eng', 'en'):
        return 'eng'
    return v[:3]


def split_list(value: str, sep: str = ';') -> list[str]:
    return [x.strip() for x in (value or '').split(sep) if x.strip()]


def year_from(value: str) -> str:
    m = re.search(r'(1[89]|20)\d{2}', value or '')
    return m.group(0) if m else ''


def make_record(source: str, **fields) -> dict:
    rec = {k: (list(v) if isinstance(v, list) else v) for k, v in _FIELDS.items()}
    rec['source'] = source
    for key, value in fields.items():
        if key not in rec:
            raise KeyError(f'unknown record field {key!r}')
        if value is not None:
            rec[key] = value
    for key in _TEXT_FIELDS:
        rec[key] = ' '.join(str(rec[key]).split())
    rec['doi'] = normalize_doi(rec['doi'])
    rec['pub_types'] = [p for p in rec['pub_types'] if p]
    rec['keywords'] = [k for k in rec['keywords'] if k]
    return rec


def detect_format(path: Path | str) -> str | None:
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            head = f.read(8000)
    except OSError:
        return None
    if re.search(r'^PMID- ', head, re.M):
        return 'pubmed'
    if re.search(r'^TY  - ', head, re.M):
        return 'ris'
    first = head.splitlines()[0] if head else ''
    if {'PT', 'TI', 'UT'} <= {c.strip() for c in first.split('\t')}:
        return 'wos'
    try:
        header = next(csv.reader([first]))
    except (StopIteration, csv.Error):
        return None
    cols = {c.strip().lower() for c in header}
    if {'an', 'title', 'contributors'} <= cols:
        return 'ebsco'
    if 'title' in cols:
        return 'csv'
    return None
```

`review/importers/pubmed.py`:
```python
"""PubMed NBIB ("PubMed" format) export parser."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .common import make_record, map_language, year_from


def _collect(lines: list[str]) -> list[str]:
    """Join NBIB continuation lines (6-space indent) onto the previous tag."""
    out: list[str] = []
    for line in lines:
        if line.startswith('      ') and out:
            out[-1] = out[-1] + ' ' + line.strip()
        else:
            out.append(line)
    return out


def parse_pubmed(path: Path | str) -> list[dict]:
    raw = Path(path).read_text(encoding='utf-8-sig', errors='replace').replace('\r\n', '\n')
    records = []
    for block in raw.strip().split('\n\n'):
        block = block.strip()
        if not block.startswith('PMID'):
            continue
        tags: dict[str, list[str]] = defaultdict(list)
        for line in _collect(block.splitlines()):
            if len(line) > 6 and line[4] == '-':
                tags[line[:4].strip()].append(line[6:].strip())

        def first(tag: str) -> str:
            return tags[tag][0] if tags[tag] else ''

        doi = next((a.replace('[doi]', '').strip() for a in tags['AID'] if '[doi]' in a), '')
        records.append(make_record(
            'pubmed',
            source_id=first('PMID'), pmid=first('PMID'), doi=doi,
            title=' '.join(tags['TI']), abstract=' '.join(tags['AB']),
            authors='; '.join(tags['AU']), journal=first('JT') or first('TA'),
            year=year_from(first('DP')), language=map_language(first('LA')),
            pub_types=list(tags['PT']),
            keywords=[m.lstrip('*') for m in tags['MH']] + list(tags['OT']),
        ))
    return records
```

`review/importers/wos.py`:
```python
"""Web of Science tab-delimited export parser."""
from __future__ import annotations

import csv
from pathlib import Path

from .common import make_record, map_language, split_list, year_from

PUBTYPE_MAP = {
    'article': 'Journal Article', 'review': 'Review', 'editorial material': 'Editorial',
    'meeting abstract': 'Abstract', 'letter': 'Letter', 'correction': 'Published Erratum',
    'news item': 'News', 'retraction': 'Retracted Publication', 'book review': 'Book Review',
    'note': 'Comment', 'biographical-item': 'Biography', 'proceedings paper': 'Journal Article',
    'data paper': 'Journal Article', 'early access': '',
}


def _pubtypes(dt: str) -> list[str]:
    out = []
    for part in (dt or '').replace('/', ';').split(';'):
        key = part.strip().lower()
        if key:
            out.append(PUBTYPE_MAP.get(key, part.strip()))
    return [p for p in out if p]


def parse_wos(path: Path | str) -> list[dict]:
    records = []
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
        for row in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            def get(key: str) -> str:
                return (row.get(key) or '').strip()
            if get('PT') == 'PT' or (not get('TI') and not get('AB')):
                continue
            records.append(make_record(
                'wos',
                source_id=get('UT'), pmid=get('PM'), doi=get('DI'), title=get('TI'), abstract=get('AB'),
                authors='; '.join(split_list(get('AU'))), journal=get('SO'), year=year_from(get('PY')),
                language=map_language(get('LA')), pub_types=_pubtypes(get('DT')),
                keywords=split_list(get('DE')) + split_list(get('ID')),
            ))
    return records
```

`review/importers/ebsco.py`:
```python
"""EBSCO CSV export parser (SPORTDiscus, CINAHL, ERIC via EBSCO, ...)."""
from __future__ import annotations

import csv
from pathlib import Path

from .common import make_record, map_language, split_list, year_from

DOCTYPE_MAP = {
    'article': 'Journal Article', 'review': 'Review', 'editorial': 'Editorial', 'letter': 'Letter',
    'abstract': 'Abstract', 'news': 'News', 'book review': 'Book Review', 'book chapter': 'Book Chapter',
    'interview': 'Interview', 'erratum': 'Published Erratum', 'correction': 'Published Erratum',
    'retraction': 'Retracted Publication', 'obituary': 'Biography', 'proceeding': 'Abstract',
}
ISITYPE_MAP = {
    'jour': 'Journal Article', 'revw': 'Review', 'edit': 'Editorial', 'lett': 'Letter',
    'abst': 'Abstract', 'news': 'News', 'bkrvw': 'Book Review', 'erra': 'Published Erratum',
    'corr': 'Published Erratum', 'rtrn': 'Retracted Publication', 'obit': 'Biography',
}


def _pubtypes(doctypes: str, isitype: str, pubtypes: str) -> list[str]:
    out = [DOCTYPE_MAP.get(p.lower(), p) for p in split_list(doctypes)]
    mapped = ISITYPE_MAP.get((isitype or '').strip().lower())
    if mapped and mapped not in out:
        out.append(mapped)
    if not out and (pubtypes or '').strip().lower() == 'academic journal':
        out.append('Journal Article')
    return out


def _year(row: dict) -> str:
    return year_from((row.get('publicationDate') or '')[:4]) or year_from(row.get('coverDate') or '')


def parse_ebsco(path: Path | str) -> list[dict]:
    records = []
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
        for row in csv.DictReader(f):
            def get(key: str) -> str:
                return (row.get(key) or '').strip()
            if not get('title') and not get('abstract'):
                continue
            records.append(make_record(
                'ebsco',
                source_id=get('an'), doi=get('doi'), title=get('title'), abstract=get('abstract'),
                authors='; '.join(split_list(get('contributors'))), journal=get('source'), year=_year(row),
                language=map_language(get('language')),
                pub_types=_pubtypes(get('docTypes'), get('isiType'), get('pubTypes')),
                keywords=split_list(get('subjects')),
            ))
    return records
```

`review/importers/__init__.py` (temporary; Task 4 replaces it):
```python
"""Database export importers."""
from .ebsco import parse_ebsco
from .pubmed import parse_pubmed
from .wos import parse_wos

PARSERS = {'pubmed': parse_pubmed, 'wos': parse_wos, 'ebsco': parse_ebsco}
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_importers.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add review/importers tests/test_importers.py
git commit -m "Add common record shape and PubMed, WoS, EBSCO importers"
```

---

### Task 4: RIS and generic CSV importers + `import_exports`

**Files:**
- Create: `review/importers/ris.py`, `review/importers/csv_generic.py`
- Modify: `review/importers/__init__.py` (full replacement)
- Test: append to `tests/test_importers.py`

- [ ] **Step 1: Append the failing tests to `tests/test_importers.py`**

```python
import pytest

from review.errors import PipelineError
from review.importers import import_exports

ALL = ['pubmed', 'wos', 'ebsco', 'ris', 'csv']


def test_ris_fields_and_continuation(workspace):
    recs = PARSERS['ris'](workspace.exports / 'export.ris')
    assert len(recs) == 2
    r = recs[0]
    assert r['authors'] == 'Kim, H' and r['journal'] == 'Example Sports Journal'
    assert r['keywords'] == ['workload', 'correlation'] and r['pub_types'] == ['Journal Article']
    assert r['abstract'].endswith('in basketball.') and r['doi'] == '10.1000/example.005'
    assert recs[1]['doi'] == '' and recs[1]['year'] == '2018'


def test_generic_csv_scopus_columns(workspace):
    r = PARSERS['csv'](workspace.exports / 'scopus.csv')[0]
    assert r['journal'] == 'Example Hockey Review'
    assert r['keywords'] == ['training load', 'accelerometer']
    assert r['source_id'] == '2-s2.0-1' and r['pub_types'] == ['Journal Article']


def test_import_exports_reads_every_file(workspace):
    records, files = import_exports(workspace.exports, ALL)
    assert len(records) == 10
    assert {f['format'] for f in files} == set(ALL)
    assert all(r['export_file'] for r in records)


def test_unrecognised_file_is_reported(workspace):
    (workspace.exports / 'notes.txt').write_text('hello', encoding='utf-8')
    with pytest.raises(PipelineError) as err:
        import_exports(workspace.exports, ALL)
    assert 'notes.txt' in str(err.value)


def test_unlisted_source_is_reported(workspace):
    with pytest.raises(PipelineError) as err:
        import_exports(workspace.exports, ['pubmed'])
    assert 'wos.txt' in str(err.value) and 'not listed under sources' in str(err.value)


def test_empty_exports_folder(tmp_path):
    with pytest.raises(PipelineError) as err:
        import_exports(tmp_path / 'data' / 'exports', ALL)
    assert 'No export files found' in str(err.value)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `PY -m pytest tests/test_importers.py -q`
Expected: FAIL with `ImportError: cannot import name 'import_exports'`

- [ ] **Step 3: Implement**

`review/importers/ris.py`:
```python
"""RIS export parser (Scopus, ERIC, PsycINFO, Zotero, EndNote, Mendeley, ...)."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .common import make_record, map_language, year_from

TAG = re.compile(r'^([A-Z][A-Z0-9])  -(?: (.*))?$')
DOI_IN_URL = re.compile(r'10\.\d{4,9}/\S+')
TYPE_MAP = {
    'JOUR': 'Journal Article', 'JFULL': 'Journal Article', 'EJOUR': 'Journal Article',
    'ABST': 'Abstract', 'EDIT': 'Editorial', 'NEWS': 'News', 'CONF': 'Conference Paper',
    'CPAPER': 'Conference Paper', 'BOOK': 'Book', 'CHAP': 'Book Chapter', 'THES': 'Thesis',
    'RPRT': 'Report',
}


def _to_record(tags: dict[str, list[str]]) -> dict:
    def first(*names: str) -> str:
        for n in names:
            if tags.get(n):
                return tags[n][0]
        return ''

    doi = first('DO')
    if not doi:
        m = DOI_IN_URL.search(' '.join(tags.get('UR', [])))
        doi = m.group(0) if m else ''
    ty = first('TY').upper()
    return make_record(
        'ris',
        source_id=first('AN', 'ID'), doi=doi, title=first('TI', 'T1'),
        abstract=' '.join(tags.get('AB') or tags.get('N2') or []),
        authors='; '.join(tags.get('AU', []) + tags.get('A1', [])),
        journal=first('JO', 'JF', 'T2', 'JA', 'J2'), year=year_from(first('PY', 'Y1', 'DA')),
        language=map_language(first('LA')), pub_types=[TYPE_MAP.get(ty, ty)] if ty else [],
        keywords=list(tags.get('KW', [])),
    )


def parse_ris(path: Path | str) -> list[dict]:
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    records: list[dict] = []
    current: dict[str, list[str]] | None = None
    last_tag: str | None = None
    for line in text.splitlines():
        m = TAG.match(line)
        if m:
            tag, value = m.group(1), (m.group(2) or '').strip()
            if tag == 'TY':
                current, last_tag = defaultdict(list), None
            if current is None:
                continue
            if tag == 'ER':
                records.append(_to_record(current))
                current, last_tag = None, None
                continue
            current[tag].append(value)
            last_tag = tag
        elif current is not None and last_tag and line.strip():
            current[last_tag][-1] = (current[last_tag][-1] + ' ' + line.strip()).strip()
    if current:
        records.append(_to_record(current))
    return [r for r in records if r['title'] or r['abstract']]
```

`review/importers/csv_generic.py`:
```python
"""Generic CSV parser (Scopus CSV, Zotero CSV, Dimensions, Lens, hand-made spreadsheets)."""
from __future__ import annotations

import csv
from pathlib import Path

from .common import make_record, map_language, split_list, year_from

ALIASES = {
    'title': ['title', 'article title', 'document title'],
    'abstract': ['abstract', 'abstract note'],
    'authors': ['authors', 'author', 'author full names'],
    'year': ['year', 'publication year', 'pubyear', 'date'],
    'doi': ['doi'],
    'journal': ['source title', 'publication title', 'journal', 'source'],
    'language': ['language of original document', 'language'],
    'keywords': ['author keywords', 'keywords', 'manual tags', 'index keywords'],
    'type': ['document type', 'item type', 'publication type', 'type'],
    'pmid': ['pubmed id', 'pmid'],
    'source_id': ['eid', 'key', 'accession number', 'id'],
}
TYPE_MAP = {
    'article': 'Journal Article', 'journalarticle': 'Journal Article', 'journal article': 'Journal Article',
    'review': 'Review', 'conference paper': 'Conference Paper', 'conferencepaper': 'Conference Paper',
    'editorial': 'Editorial', 'letter': 'Letter', 'note': 'Comment', 'erratum': 'Published Erratum',
    'retracted': 'Retracted Publication',
}


def _pick(row: dict[str, str], field: str) -> str:
    for alias in ALIASES[field]:
        value = (row.get(alias) or '').strip()
        if value:
            return value
    return ''


def parse_csv(path: Path | str) -> list[dict]:
    records = []
    with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
        for raw in csv.DictReader(f):
            row = {(k or '').strip().lower(): (v or '') for k, v in raw.items()}
            title, abstract = _pick(row, 'title'), _pick(row, 'abstract')
            if not title and not abstract:
                continue
            kind = _pick(row, 'type')
            records.append(make_record(
                'csv',
                source_id=_pick(row, 'source_id'), pmid=_pick(row, 'pmid'), doi=_pick(row, 'doi'),
                title=title, abstract=abstract, authors=_pick(row, 'authors'),
                journal=_pick(row, 'journal'), year=year_from(_pick(row, 'year')),
                language=map_language(_pick(row, 'language')),
                pub_types=[TYPE_MAP.get(kind.lower(), kind)] if kind else [],
                keywords=split_list(_pick(row, 'keywords')),
            ))
    return records
```

`review/importers/__init__.py` (full replacement):
```python
"""Database export importers. `import_exports` reads every file in data/exports/."""
from __future__ import annotations

from pathlib import Path

from ..errors import PipelineError
from .common import SUPPORTED_HELP, detect_format
from .csv_generic import parse_csv
from .ebsco import parse_ebsco
from .pubmed import parse_pubmed
from .ris import parse_ris
from .wos import parse_wos

PARSERS = {'pubmed': parse_pubmed, 'wos': parse_wos, 'ebsco': parse_ebsco, 'ris': parse_ris, 'csv': parse_csv}


def import_exports(exports_dir: Path, allowed: list[str]) -> tuple[list[dict], list[dict]]:
    """Parse every export file. Returns (records, [{file, format, records}])."""
    exports_dir = Path(exports_dir)
    files = sorted(p for p in exports_dir.iterdir() if p.is_file() and not p.name.startswith('.')) \
        if exports_dir.exists() else []
    if not files:
        raise PipelineError(
            f'No export files found in {exports_dir}. Save your database exports there, '
            'then run: py run.py import')
    records: list[dict] = []
    report: list[dict] = []
    problems: list[str] = []
    for f in files:
        fmt = detect_format(f)
        if fmt is None:
            problems.append(f"{f.name}: could not recognise this file's format. {SUPPORTED_HELP}")
            continue
        if fmt not in allowed:
            problems.append(f"{f.name}: looks like a '{fmt}' export, but '{fmt}' is not listed under "
                            'sources in project.yaml. Add it there or remove the file.')
            continue
        parsed = PARSERS[fmt](f)
        for r in parsed:
            r['export_file'] = f.name
        records.extend(parsed)
        report.append({'file': f.name, 'format': fmt, 'records': len(parsed)})
    if problems:
        raise PipelineError('Some export files could not be imported:', problems)
    return records, report
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_importers.py -q`
Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add review/importers tests/test_importers.py
git commit -m "Add RIS and generic CSV importers and folder-level import"
```

---

### Task 5: Cross-source deduplication (`review/dedup.py`)

**Files:**
- Create: `review/dedup.py`
- Test: `tests/test_dedup.py`

- [ ] **Step 1: Write the failing test** — `tests/test_dedup.py`

```python
from review.dedup import deduplicate
from review.importers import import_exports

ORDER = ['pubmed', 'wos', 'ebsco', 'ris', 'csv']


def _run(workspace, order=ORDER):
    records, _ = import_exports(workspace.exports, ORDER)
    return deduplicate(records, order)


def test_counts(workspace):
    unique, stats = _run(workspace)
    assert (stats['total_raw'], stats['unique'], stats['duplicates_removed']) == (10, 8, 2)
    assert stats['per_source_raw'] == {'pubmed': 3, 'wos': 2, 'ebsco': 2, 'ris': 2, 'csv': 1}


def test_doi_match_merges_sources(workspace):
    by_id = {r['id']: r for r in _run(workspace)[0]}
    assert by_id['doi:10.1000/example.001']['sources'] == ['pubmed', 'wos']
    assert by_id['doi:10.1000/example.001']['source'] == 'pubmed'


def test_title_year_match_merges_sources(workspace):
    by_id = {r['id']: r for r in _run(workspace)[0]}
    assert by_id['doi:10.1000/example.004']['sources'] == ['wos', 'ebsco']


def test_fallback_ids_are_unique_and_stable(workspace):
    ids = [r['id'] for r in _run(workspace)[0]]
    assert len(ids) == len(set(ids))
    assert 'ebsco:E2' in ids and 'pmid:10000002' in ids
    assert any(i.startswith('ris:t') for i in ids)
    assert ids == [r['id'] for r in _run(workspace)[0]]


def test_source_order_sets_priority(workspace):
    by_id = {r['id']: r for r in _run(workspace, ['wos', 'pubmed', 'ebsco', 'ris', 'csv'])[0]}
    assert by_id['doi:10.1000/example.001']['source'] == 'wos'
    assert by_id['doi:10.1000/example.001']['sources'] == ['wos', 'pubmed']
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_dedup.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'review.dedup'`

- [ ] **Step 3: Implement** — `review/dedup.py`

```python
"""Merge records across exports. Match on DOI, then PMID, then normalised title + year.

The first source in project.yaml `sources` wins. Every unique record gets a stable `id`
(doi:..., pmid:..., or <source>:<source id>) and a `sources` list of every export that had it.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_PUNCT = re.compile(r'[^a-z0-9\s]')
_SPACE = re.compile(r'\s+')


def _norm_text(s: str) -> str:
    s = (s or '').translate(str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-'}))
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii').lower()
    return _SPACE.sub(' ', _PUNCT.sub(' ', s)).strip()


def title_key(title: str, year: str) -> str:
    t = _norm_text(title)[:120]
    return f'{t}|{year}' if t and year else ''


def _make_id(rec: dict, tkey: str) -> str:
    if rec.get('doi'):
        return f"doi:{rec['doi']}"
    if rec.get('pmid'):
        return f"pmid:{rec['pmid']}"
    if rec.get('source_id'):
        return f"{rec['source']}:{rec['source_id']}"
    digest = hashlib.sha1((tkey or _norm_text(rec.get('title', ''))).encode('utf-8')).hexdigest()[:12]
    return f"{rec['source']}:t{digest}"


def deduplicate(records: list[dict], source_order: list[str]) -> tuple[list[dict], dict]:
    priority = {s: i for i, s in enumerate(source_order)}
    ordered = sorted(records, key=lambda r: priority.get(r.get('source', ''), len(priority)))

    by_doi: dict[str, dict] = {}
    by_pmid: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    unique: list[dict] = []
    used_ids: set[str] = set()
    per_source_raw: dict[str, int] = {}

    for r in ordered:
        src = r.get('source', '?')
        per_source_raw[src] = per_source_raw.get(src, 0) + 1
        doi, pmid = r.get('doi', ''), r.get('pmid', '')
        tkey = title_key(r.get('title', ''), r.get('year', ''))

        existing = (by_doi.get(doi) if doi else None) or (by_pmid.get(pmid) if pmid else None) \
            or (by_title.get(tkey) if tkey else None)
        if existing is not None:
            if src not in existing['sources']:
                existing['sources'].append(src)
            if not existing.get('pmid') and pmid:
                existing['pmid'] = pmid
                by_pmid[pmid] = existing
            if not existing.get('doi') and doi:
                existing['doi'] = doi
                by_doi[doi] = existing
            if not existing.get('abstract') and r.get('abstract'):
                existing['abstract'] = r['abstract']
            continue

        rec = dict(r)
        rec['sources'] = [src]
        rec_id = _make_id(rec, tkey)
        n = 2
        while rec_id in used_ids:
            rec_id = f'{_make_id(rec, tkey)}-{n}'
            n += 1
        rec['id'] = rec_id
        used_ids.add(rec_id)
        unique.append(rec)
        if doi:
            by_doi[doi] = rec
        if pmid:
            by_pmid[pmid] = rec
        if tkey:
            by_title[tkey] = rec

    stats = {
        'per_source_raw': {s: per_source_raw[s] for s in sorted(per_source_raw, key=lambda s: priority.get(s, 99))},
        'total_raw': len(ordered),
        'unique': len(unique),
        'duplicates_removed': len(ordered) - len(unique),
    }
    return unique, stats
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_dedup.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add review/dedup.py tests/test_dedup.py
git commit -m "Add cross-source deduplication with stable ids"
```

---

### Task 6: Pre-filter and keyword prescreen (`review/screen.py`)

Scoring follows Flynn's proven rule: each keyword group adds its weight **once** if any of its terms appears. The terms are matched against the title, abstract and keywords.

**Files:**
- Create: `review/screen.py`
- Test: `tests/test_screen.py`

- [ ] **Step 1: Write the failing test** — `tests/test_screen.py`

```python
from review import screen
from review.config import load_project
from review.dedup import deduplicate
from review.importers import import_exports


def _unique(workspace):
    project = load_project(workspace.root)
    records, _ = import_exports(workspace.exports, project.sources)
    return project, deduplicate(records, project.sources)[0]


def test_pre_filter_reasons(workspace):
    project, unique = _unique(workspace)
    keep, excluded = screen.pre_filter(unique, project.exclude)
    reasons = {r['id']: r['excluded_reason'] for r in excluded}
    assert reasons['pmid:10000002'] == 'Publication type excluded: Editorial'
    assert 'Abstract' in reasons['ebsco:E2']
    assert len(keep) == 6


def test_pre_filter_flags_can_be_turned_off(workspace):
    project, unique = _unique(workspace)
    keep, _ = screen.pre_filter(unique, {**project.exclude, 'editorials': False, 'conference_abstracts': False})
    assert len(keep) == 8


def test_non_english_and_empty_records():
    exclude = {'non_english': True, 'no_abstract': True}
    recs = [
        {'id': 'a', 'language': 'spa', 'pub_types': [], 'abstract': 'x', 'keywords': []},
        {'id': 'b', 'language': 'eng', 'pub_types': [], 'abstract': '', 'keywords': []},
    ]
    keep, excluded = screen.pre_filter(recs, exclude)
    assert keep == []
    assert [r['excluded_reason'] for r in excluded] == ['Not in English', 'No abstract and no subject keywords']


def test_score_counts_each_group_once(workspace):
    groups = load_project(workspace.root).keyword_groups
    rec = {'title': 'GPS and accelerometer in soccer', 'abstract': 'principal component and factor analysis',
           'keywords': []}
    score, signals = screen.score_record(rec, groups)
    assert score == 5
    assert signals == ['technology:gps', 'sport:soccer', 'analysis:principal component']


def test_prescreen_split_and_order(workspace):
    project, unique = _unique(workspace)
    keep, _ = screen.pre_filter(unique, project.exclude)
    cands, excluded = screen.prescreen(keep, project.keyword_groups, project.threshold)
    assert {c['id'] for c in cands} == {'doi:10.1000/example.001', 'doi:10.1000/example.004',
                                        'doi:10.1000/example.005', 'doi:10.1000/example.006'}
    assert [c['prescreen_score'] for c in cands] == [5, 5, 5, 4]
    assert len(excluded) == 2 and all(e['prescreen_score'] == 0 for e in excluded)
    assert 'prescreen_score' not in keep[0]   # inputs are not mutated
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_screen.py -q`
Expected: FAIL with `ImportError: cannot import name 'screen'`

- [ ] **Step 3: Implement** — `review/screen.py`

```python
"""Rule-based filtering before any AI work: hard filters, then a weighted keyword score."""
from __future__ import annotations

from .config import KeywordGroup

EXCLUDE_TYPES = {
    'retracted': {'retracted publication', 'retraction of publication', 'retraction'},
    'editorials': {'editorial', 'comment', 'letter', 'news', 'published erratum'},
    'conference_abstracts': {'abstract', 'conference paper', 'meeting abstract', 'congress'},
}


def pre_filter(records: list[dict], exclude: dict) -> tuple[list[dict], list[dict]]:
    """Returns (keep, excluded). Excluded copies carry an `excluded_reason`."""
    banned: set[str] = set()
    for flag, types in EXCLUDE_TYPES.items():
        if exclude.get(flag):
            banned |= types
    keep, excluded = [], []
    for r in records:
        hits = [p for p in r.get('pub_types', []) if p.lower() in banned]
        if exclude.get('non_english') and r.get('language', 'eng') != 'eng':
            reason = 'Not in English'
        elif hits:
            reason = 'Publication type excluded: ' + ', '.join(sorted(set(hits)))
        elif exclude.get('no_abstract') and not r.get('abstract') and not r.get('keywords'):
            reason = 'No abstract and no subject keywords'
        else:
            keep.append(r)
            continue
        excluded.append({**r, 'excluded_reason': reason})
    return keep, excluded


def score_record(rec: dict, groups: tuple[KeywordGroup, ...]) -> tuple[int, list[str]]:
    """Each group adds its weight once if any of its terms appears."""
    text = ' ' + ' '.join([rec.get('title', ''), rec.get('abstract', ''), ' '.join(rec.get('keywords', []))]).lower() + ' '
    score, signals = 0, []
    for g in groups:
        hit = next((t for t in g.terms if t in text), None)
        if hit is not None:
            score += g.weight
            signals.append(f'{g.name}:{hit.strip()}')
    return score, signals


def prescreen(records: list[dict], groups: tuple[KeywordGroup, ...], threshold: int) -> tuple[list[dict], list[dict]]:
    """Returns (candidates sorted by score, excluded). Both carry prescreen_score/prescreen_signals."""
    candidates, excluded = [], []
    for r in records:
        score, signals = score_record(r, groups)
        scored = {**r, 'prescreen_score': score, 'prescreen_signals': ', '.join(signals)}
        (candidates if score >= threshold else excluded).append(scored)
    candidates.sort(key=lambda c: -c['prescreen_score'])
    return candidates, excluded
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_screen.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add review/screen.py tests/test_screen.py
git commit -m "Add configurable pre-filter and weighted keyword prescreen"
```

---

### Task 7: Stage tracking (`review/state.py`)

**Files:**
- Create: `review/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write the failing test** — `tests/test_state.py`

```python
from review import state
from review.config import Paths
from review.io import write_json


def test_progression(workspace):
    assert state.next_stage(workspace) == 'import'
    state.mark_done(workspace, 'import', unique=8)
    assert state.next_stage(workspace) == 'prescreen'
    assert state.load_state(workspace)['completed']['import']['unique'] == 8


def test_setup_first_when_no_project(tmp_path):
    paths = Paths(tmp_path)
    assert state.next_stage(paths) == 'setup'
    assert 'set up my review' in state.status_text(paths)


def test_clear_from_resets_later_stages(workspace):
    for stage in ('import', 'prescreen', 'report'):
        state.mark_done(workspace, stage)
    state.clear_from(workspace, 'prescreen')
    assert set(state.load_state(workspace)['completed']) == {'import'}


def test_classify_done_is_computed_from_checkpoint(workspace):
    state.mark_done(workspace, 'import')
    state.mark_done(workspace, 'prescreen')
    write_json(workspace.candidates, [{'id': 'a'}, {'id': 'b'}])
    write_json(workspace.checkpoint, {'a': {'tier': 1}})
    assert state.next_stage(workspace) == 'classify'
    assert '1/2 classified' in state.status_text(workspace)
    write_json(workspace.checkpoint, {'a': {'tier': 1}, 'b': {'tier': 2}})
    assert state.next_stage(workspace) == 'validate'
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_state.py -q`
Expected: FAIL with `ImportError: cannot import name 'state'`

- [ ] **Step 3: Implement** — `review/state.py`

```python
"""Which stage is done, and what the researcher should do next."""
from __future__ import annotations

from .config import ConfigError, Paths, load_project
from .io import now_iso, read_json, write_json

STAGES = ('setup', 'import', 'prescreen', 'classify', 'validate', 'report', 'pdfs', 'wiki', 'site', 'publish')

NEXT = {
    'setup': 'Ask your AI assistant to "set up my review" (or copy project.example.yaml to project.yaml '
             'and edit it), then run: py run.py check-config',
    'import': 'Save your database exports in data/exports/, then run: py run.py import',
    'prescreen': 'py run.py prescreen',
    'classify': 'Ask your AI assistant to "classify the next batch" (it follows prompts/02-classify.md)',
    'validate': 'py run.py validate --draw, then re-screen data/validation.xlsx yourself, '
                'then py run.py validate --score',
    'report': 'py run.py report',
    'pdfs': 'py run.py pdfs',
    'wiki': 'Ask your AI assistant to "build the wiki"',
    'site': 'py run.py site',
    'publish': 'See docs/08-website.md',
}


def load_state(paths: Paths) -> dict:
    return read_json(paths.state, {'completed': {}})


def mark_done(paths: Paths, stage: str, **info) -> None:
    s = load_state(paths)
    s['completed'][stage] = {'at': now_iso(), **info}
    write_json(paths.state, s)


def clear_from(paths: Paths, stage: str) -> None:
    """Forget `stage` and every later stage (their inputs are about to change)."""
    later = set(STAGES[STAGES.index(stage):])
    s = load_state(paths)
    s['completed'] = {k: v for k, v in s['completed'].items() if k not in later}
    write_json(paths.state, s)


def setup_problems(paths: Paths) -> list[str]:
    try:
        load_project(paths.root)
        return []
    except ConfigError as err:
        return err.problems


def classify_counts(paths: Paths) -> tuple[int, int] | None:
    candidates = read_json(paths.candidates)
    if candidates is None:
        return None
    ckpt = read_json(paths.checkpoint, {})
    return sum(1 for c in candidates if c['id'] in ckpt), len(candidates)


def _done(paths: Paths, stage: str, completed: dict) -> bool:
    if stage == 'setup':
        return not setup_problems(paths)
    if stage == 'classify':
        counts = classify_counts(paths)
        return counts is not None and 'prescreen' in completed and counts[0] == counts[1]
    return stage in completed


def next_stage(paths: Paths) -> str | None:
    completed = load_state(paths)['completed']
    for stage in STAGES:
        if not _done(paths, stage, completed):
            return stage
    return None


def status_text(paths: Paths) -> str:
    completed = load_state(paths)['completed']
    nxt = next_stage(paths)
    lines = ['Review pipeline status', '']
    for stage in STAGES:
        if _done(paths, stage, completed):
            mark = 'done'
        elif stage == 'classify' and classify_counts(paths) and 'prescreen' in completed:
            done, total = classify_counts(paths)
            mark = f'{done}/{total} classified'
        else:
            mark = 'to do'
        pointer = '>' if stage == nxt else ' '
        lines.append(f' {pointer} {stage:<10} {mark}')
    lines.append('')
    if nxt is None:
        lines.append('Every stage is done.')
    else:
        lines.append(f'Next step: {NEXT[nxt]}')
        if nxt == 'setup':
            lines += [f'  - {p}' for p in setup_problems(paths)]
    return '\n'.join(lines)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_state.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add review/state.py tests/test_state.py
git commit -m "Add stage tracking and plain-English next-step status"
```

---

### Task 8: Classification (`review/classify.py`)

**Files:**
- Create: `review/classify.py`
- Modify: `tests/conftest.py` (add the `prescreened` fixture)
- Test: `tests/test_classify.py`

- [ ] **Step 1: Add the `prescreened` fixture** — append to `tests/conftest.py`

```python
from review import screen, state
from review.config import load_project
from review.dedup import deduplicate
from review.importers import import_exports
from review.io import write_json


@pytest.fixture
def prescreened(workspace):
    project = load_project(workspace.root)
    records, _ = import_exports(workspace.exports, project.sources)
    unique, stats = deduplicate(records, project.sources)
    keep, pre_ex = screen.pre_filter(unique, project.exclude)
    cands, ps_ex = screen.prescreen(keep, project.keyword_groups, project.threshold)
    stats.update(prefilter_excluded=len(pre_ex), after_prefilter=len(keep),
                 prescreen_excluded=len(ps_ex), candidates=len(cands))
    write_json(workspace.records, unique)
    write_json(workspace.candidates, cands)
    write_json(workspace.stats, stats)
    state.mark_done(workspace, 'import')
    state.mark_done(workspace, 'prescreen')
    return workspace, project
```

- [ ] **Step 2: Write the failing test** — `tests/test_classify.py`

```python
import json

import pytest

from review import classify, state
from review.errors import PipelineError
from review.io import read_json

TOOL, MODEL = 'Claude Code', 'claude-opus-5-5'


def _results(tmp_path, payload):
    f = tmp_path / 'res.json'
    f.write_text(json.dumps(payload), encoding='utf-8')
    return f


def _ids(paths):
    return [c['id'] for c in read_json(paths.candidates)]


def test_prompt_is_built_from_project(prescreened):
    paths, project = prescreened
    text = classify.build_prompt(project)
    assert project.question in text
    assert 'Team sport athletes' in text
    assert 'TIER 1 — CORE MATCH (INCLUDED)' in text
    assert '"tier": <1|2|3|4>' in text


def test_next_batch_writes_file_and_limits_size(prescreened):
    paths, project = prescreened
    batch = classify.next_batch(paths, project, size=3)
    assert len(batch['papers']) == 3
    assert batch['remaining_after_this_batch'] == 1
    assert set(batch['papers'][0]) == {'id', 'title', 'abstract', 'year', 'journal', 'keywords', 'pub_types'}
    assert read_json(paths.classify_batch)['papers'][0]['id'] == batch['papers'][0]['id']


def test_save_stamps_audit_fields(prescreened, tmp_path):
    paths, project = prescreened
    first = _ids(paths)[0]
    out = classify.save_results(paths, project, _results(tmp_path, {'results': [
        {'id': first, 'tier': 1, 'score': 90, 'reason': 'Central PCA study.'}]}), TOOL, MODEL)
    entry = read_json(paths.checkpoint)[first]
    assert (entry['tier'], entry['tool'], entry['model']) == (1, TOOL, MODEL)
    assert entry['timestamp'].endswith('+00:00')
    assert out['saved'] == 1 and out['remaining'] == 3


def test_any_problem_rejects_the_whole_save(prescreened, tmp_path):
    paths, project = prescreened
    good = _ids(paths)[0]
    payload = {'results': [
        {'id': good, 'tier': 1, 'score': 90, 'reason': 'ok'},
        {'id': 'doi:nope', 'tier': 1, 'score': 50, 'reason': 'x'},
        {'id': _ids(paths)[1], 'tier': 9, 'score': 50, 'reason': 'x'},
        {'id': _ids(paths)[2], 'tier': 2, 'score': 0, 'reason': 'x'},
        {'id': _ids(paths)[3], 'tier': 2, 'score': 50, 'reason': '  '},
    ]}
    with pytest.raises(PipelineError) as err:
        classify.save_results(paths, project, _results(tmp_path, payload), TOOL, MODEL)
    assert len(err.value.problems) == 4
    assert not paths.checkpoint.exists()


def test_tool_and_model_are_required(prescreened, tmp_path):
    paths, project = prescreened
    with pytest.raises(PipelineError) as err:
        classify.save_results(paths, project, _results(tmp_path, {'results': []}), '', MODEL)
    assert '--tool' in str(err.value)


def test_reclassifying_keeps_history(prescreened, tmp_path):
    paths, project = prescreened
    pid = _ids(paths)[0]
    classify.save_results(paths, project, _results(tmp_path, {pid: {'tier': 3, 'score': 40, 'reason': 'a'}}), TOOL, MODEL)
    classify.save_results(paths, project, _results(tmp_path, {pid: {'tier': 1, 'score': 90, 'reason': 'b'}}), TOOL, MODEL)
    entry = read_json(paths.checkpoint)[pid]
    assert entry['tier'] == 1 and entry['history'][0]['tier'] == 3


def test_completing_classification_moves_to_validate(prescreened, tmp_path):
    paths, project = prescreened
    payload = {'results': [{'id': i, 'tier': 2, 'score': 50, 'reason': 'r'} for i in _ids(paths)]}
    out = classify.save_results(paths, project, _results(tmp_path, payload), TOOL, MODEL)
    assert out['remaining'] == 0 and out['by_tier'] == {1: 0, 2: 4, 3: 0, 4: 0}
    assert state.next_stage(paths) == 'validate'
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_classify.py -q`
Expected: FAIL with `ImportError: cannot import name 'classify'`

- [ ] **Step 4: Implement** — `review/classify.py`

```python
"""AI classification support. The agent judges; this module hands out batches and validates saves."""
from __future__ import annotations

import json
from pathlib import Path

from . import state
from .config import Paths, Project
from .errors import PipelineError
from .io import now_iso, read_json, write_json

PAPER_FIELDS = ('id', 'title', 'abstract', 'year', 'journal', 'keywords', 'pub_types')


def build_prompt(project: Project) -> str:
    picos = '\n'.join(f"  {k.replace('_', ' ').title():<26}: {v}"
                      for k, v in project.picos.items() if str(v or '').strip())
    tiers = '\n\n'.join(
        f"TIER {t.id} — {t.label.upper()} ({'INCLUDED' if t.included else 'EXCLUDED'}):\n  {t.definition}"
        for t in project.tiers)
    ids = ', '.join(str(i) for i in project.tier_ids)
    choices = '|'.join(str(i) for i in project.tier_ids)
    return (
        'You are a research librarian screening papers for a systematic review.\n'
        'Apply the research question, PICOS criteria, and tier definitions below exactly.\n\n'
        f'RESEARCH QUESTION:\n  {project.question}\n\n'
        f'PICOS CRITERIA:\n{picos}\n\n'
        f'TIERS:\n\n{tiers}\n\n'
        f'For every paper choose exactly one tier ({ids}), a relevance score from 1 to 100 within that\n'
        'tier (100 = textbook example, 50 = typical member, 1 = barely qualifies), and one concise\n'
        'sentence explaining the decision.\n\n'
        'Respond with JSON only:\n'
        f'{{"results": [{{"id": "<paper id>", "tier": <{choices}>, "score": <1-100>, '
        '"reason": "<one sentence>"}]}\n'
    )


def _candidates(paths: Paths) -> list[dict]:
    cands = read_json(paths.candidates)
    if cands is None:
        raise PipelineError('No candidates yet. Run: py run.py prescreen')
    return cands


def progress(paths: Paths, project: Project) -> dict:
    cands = _candidates(paths)
    ckpt = read_json(paths.checkpoint, {})
    by_tier = {t: 0 for t in project.tier_ids}
    done = 0
    for c in cands:
        entry = ckpt.get(c['id'])
        if entry:
            done += 1
            by_tier[entry['tier']] = by_tier.get(entry['tier'], 0) + 1
    return {'total': len(cands), 'classified': done, 'remaining': len(cands) - done, 'by_tier': by_tier}


def next_batch(paths: Paths, project: Project, size: int | None = None) -> dict:
    size = size or project.batch_size
    ckpt = read_json(paths.checkpoint, {})
    todo = [c for c in _candidates(paths) if c['id'] not in ckpt]
    papers = [{k: c.get(k) for k in PAPER_FIELDS} for c in todo[:size]]
    batch = {
        'instructions': 'prompts/02-classify.md',
        'prompt': build_prompt(project),
        'remaining_after_this_batch': len(todo) - len(papers),
        'papers': papers,
    }
    write_json(paths.classify_batch, batch)
    return batch


def _items(data) -> list | None:
    if isinstance(data, dict) and isinstance(data.get('results'), list):
        return data['results']
    if isinstance(data, dict):
        return [{'id': k, **v} for k, v in data.items() if isinstance(v, dict)]
    if isinstance(data, list):
        return data
    return None


def validate_results(items, candidate_ids: set[str], tier_ids: set[int]) -> tuple[list[dict], list[str]]:
    if not isinstance(items, list) or not items:
        return [], ['No results found. Expected {"results": [{"id": ..., "tier": ..., "score": ..., "reason": ...}]}']
    clean, problems, seen = [], [], set()
    for n, r in enumerate(items, 1):
        if not isinstance(r, dict):
            problems.append(f'result {n} is not an object')
            continue
        pid = str(r.get('id') or '').strip()
        where = f'result {n} (id {pid or "missing"})'
        before = len(problems)
        if not pid:
            problems.append(f'{where}: missing id')
        elif pid not in candidate_ids:
            problems.append(f'{where}: id is not a candidate; copy ids exactly from the batch')
        elif pid in seen:
            problems.append(f'{where}: listed twice')
        try:
            tier = int(r.get('tier'))
            if tier not in tier_ids:
                problems.append(f'{where}: tier {tier} is not one of {sorted(tier_ids)}')
        except (TypeError, ValueError):
            tier = None
            problems.append(f'{where}: tier must be a number')
        try:
            score = int(r.get('score'))
            if not 1 <= score <= 100:
                problems.append(f'{where}: score must be between 1 and 100')
        except (TypeError, ValueError):
            score = None
            problems.append(f'{where}: score must be a number')
        reason = str(r.get('reason') or '').strip()
        if not reason:
            problems.append(f'{where}: reason is empty')
        if len(problems) == before:
            clean.append({'id': pid, 'tier': tier, 'score': score, 'reason': reason})
            seen.add(pid)
    return clean, problems


def save_results(paths: Paths, project: Project, results_file: Path | str, tool: str, model: str) -> dict:
    if not (tool or '').strip() or not (model or '').strip():
        raise PipelineError('Pass --tool and --model so the audit log records which AI made these decisions '
                            '(for example: --tool "Claude Code" --model "claude-opus-5-5").')
    try:
        data = json.loads(Path(results_file).read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise PipelineError(f'Results file not found: {results_file}') from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f'Results file is not valid JSON: {exc}') from exc

    ids = {c['id'] for c in _candidates(paths)}
    clean, problems = validate_results(_items(data), ids, set(project.tier_ids))
    if problems:
        raise PipelineError('Nothing was saved. Fix these entries and save again:', problems)

    ckpt = read_json(paths.checkpoint, {})
    stamp, new = now_iso(), 0
    for r in clean:
        entry = {'tier': r['tier'], 'score': r['score'], 'reason': r['reason'],
                 'tool': tool.strip(), 'model': model.strip(), 'timestamp': stamp}
        previous = ckpt.get(r['id'])
        if previous:
            entry['history'] = previous.pop('history', []) + [previous]
        else:
            new += 1
        ckpt[r['id']] = entry
    write_json(paths.checkpoint, ckpt)

    prog = progress(paths, project)
    if prog['remaining'] == 0:
        state.mark_done(paths, 'classify', classified=prog['classified'])
    return {'saved': len(clean), 'new': new, **prog}
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_classify.py -q`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add review/classify.py tests/test_classify.py tests/conftest.py
git commit -m "Add batch classification with validated, audited saves"
```

---

### Task 9: Human validation sample, kappa, and AI disclosure (`review/validate.py`)

**Files:**
- Create: `review/validate.py`, `tests/helpers.py`
- Modify: `tests/conftest.py` (add the `classified` fixture)
- Test: `tests/test_validate.py`

- [ ] **Step 1: Add the helpers and fixture**

`tests/helpers.py`:
```python
from openpyxl import load_workbook

TIERS = {
    'doi:10.1000/example.001': 1,
    'doi:10.1000/example.005': 2,
    'doi:10.1000/example.004': 3,
    'doi:10.1000/example.006': 4,
}


def fill_validation(paths, human: dict) -> None:
    """Type human tiers into validation.xlsx the way a researcher would."""
    wb = load_workbook(paths.validation_xlsx)
    ws = wb['Screen these']
    header = [c.value for c in ws[1]]
    id_col, tier_col = header.index('ID'), header.index('Your tier')
    for row in ws.iter_rows(min_row=2):
        pid = row[id_col].value
        if pid in human:
            row[tier_col].value = human[pid]
    wb.save(paths.validation_xlsx)
```

Append to `tests/conftest.py`:
```python
from review import classify
from tests.helpers import TIERS


@pytest.fixture
def classified(prescreened, tmp_path):
    paths, project = prescreened
    results = tmp_path / 'canned.json'
    write_json(results, {'results': [
        {'id': pid, 'tier': tier, 'score': 80, 'reason': 'Canned decision.'} for pid, tier in TIERS.items()]})
    classify.save_results(paths, project, results, 'Claude Code', 'claude-opus-5-5')
    return paths, project
```

- [ ] **Step 2: Write the failing test** — `tests/test_validate.py`

```python
import pytest
from openpyxl import load_workbook

from review import state, validate
from review.errors import PipelineError
from review.io import read_json
from tests.helpers import TIERS, fill_validation


def test_kappa_known_values():
    assert validate.cohen_kappa([1, 1, 2, 2], [1, 2, 2, 2]) == pytest.approx(0.5)
    assert validate.cohen_kappa([1, 2], [1, 2]) == 1.0
    assert validate.cohen_kappa([1, 1], [1, 1]) == 1.0


def test_draw_needs_finished_classification(prescreened):
    paths, project = prescreened
    with pytest.raises(PipelineError) as err:
        validate.draw_sample(paths, project)
    assert 'Finish classifying' in str(err.value)


def test_draw_is_stratified_blind_and_deterministic(classified):
    paths, project = classified
    out = validate.draw_sample(paths, project)
    assert out['sampled'] == 4 and out['per_tier'] == {1: 1, 2: 1, 3: 1, 4: 1}
    first_ids = read_json(paths.validation_sample)['ids']
    validate.draw_sample(paths, project, force=True)
    assert read_json(paths.validation_sample)['ids'] == first_ids
    header = [c.value for c in load_workbook(paths.validation_xlsx)['Screen these'][1]]
    assert header == ['#', 'ID', 'Title', 'Year', 'Journal', 'Abstract', 'Your tier', 'Notes']


def test_draw_will_not_overwrite_human_work(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, {'doi:10.1000/example.001': 1})
    with pytest.raises(PipelineError) as err:
        validate.draw_sample(paths, project)
    assert '--force' in str(err.value)


def test_score_reports_kappa_and_writes_disclosure(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    human = dict(TIERS)
    human['doi:10.1000/example.004'] = 2
    fill_validation(paths, human)
    res = validate.score_sample(paths, project)
    assert res['n'] == 4
    assert res['tier_agreement'] == 0.75
    assert res['tier_kappa'] == 0.667
    assert res['include_agreement'] == 0.75
    assert res['include_kappa'] == 0.5
    assert res['disagreements'] == [{'id': 'doi:10.1000/example.004', 'ai_tier': 3, 'human_tier': 2}]
    text = paths.ai_disclosure.read_text(encoding='utf-8')
    assert 'κ = 0.667' in text and 'Claude Code (claude-opus-5-5)' in text and 'seed 42' in text
    assert 'validate' in state.load_state(paths)['completed']


def test_score_lists_blank_rows(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    with pytest.raises(PipelineError) as err:
        validate.score_sample(paths, project)
    assert '4 row(s)' in str(err.value)
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_validate.py -q`
Expected: FAIL with `ImportError: cannot import name 'validate'`

- [ ] **Step 4: Implement** — `review/validate.py`

```python
"""Blind human re-screening of a stratified random sample, agreement statistics, AI-use disclosure."""
from __future__ import annotations

import math
import random
from collections import defaultdict

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font

from . import state
from .config import Paths, Project
from .errors import PipelineError
from .io import now_iso, read_json, write_json

SHEET = 'Screen these'
HEADER = ['#', 'ID', 'Title', 'Year', 'Journal', 'Abstract', 'Your tier', 'Notes']
HUMAN_COL = 'Your tier'


def cohen_kappa(a: list, b: list) -> float:
    if len(a) != len(b) or not a:
        raise ValueError('kappa needs two equal-length, non-empty lists')
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in set(a) | set(b))
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _classified(paths: Paths) -> tuple[list[dict], dict]:
    cands = read_json(paths.candidates)
    if cands is None:
        raise PipelineError('No candidates yet. Run: py run.py prescreen')
    ckpt = read_json(paths.checkpoint, {})
    missing = sum(1 for c in cands if c['id'] not in ckpt)
    if missing:
        raise PipelineError(f'Finish classifying first: {missing} candidate(s) have no tier yet.')
    return cands, ckpt


def _human_entries(paths: Paths) -> dict:
    if not paths.validation_xlsx.exists():
        return {}
    wb = load_workbook(paths.validation_xlsx, read_only=True)
    try:   # read-only workbooks hold the file open; close it or Windows blocks the next save
        rows = list(wb[SHEET].iter_rows(values_only=True))
    finally:
        wb.close()
    header = list(rows[0])
    id_i, h_i = header.index('ID'), header.index(HUMAN_COL)
    return {str(r[id_i]): r[h_i] for r in rows[1:] if r[id_i] is not None}


def draw_sample(paths: Paths, project: Project, force: bool = False) -> dict:
    cands, ckpt = _classified(paths)
    if not force and any(v not in (None, '') for v in _human_entries(paths).values()):
        raise PipelineError('validation.xlsx already has tiers you entered. Run with --force to replace it '
                            '(your entries will be lost).')
    v = project.validation
    rng = random.Random(v['seed'])
    by_tier: dict[int, list[str]] = defaultdict(list)
    for c in cands:
        by_tier[ckpt[c['id']]['tier']].append(c['id'])
    chosen, per_tier = [], {}
    for tier_id in sorted(by_tier):
        ids = sorted(by_tier[tier_id])
        k = min(len(ids), max(int(v['min_per_tier']), math.ceil(len(ids) * float(v['sample_percent']) / 100)))
        chosen.extend(rng.sample(ids, k))
        per_tier[tier_id] = k
    rng.shuffle(chosen)
    write_json(paths.validation_sample, {'seed': v['seed'], 'ids': chosen,
                                         'ai_tiers': {i: ckpt[i]['tier'] for i in chosen}})

    by_id = {c['id']: c for c in cands}
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(HEADER)
    for n, pid in enumerate(chosen, 1):
        c = by_id[pid]
        ws.append([n, pid, c.get('title', ''), c.get('year', ''), c.get('journal', ''),
                   (c.get('abstract') or '')[:32000], None, None])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for col, width in zip('ABCDEFGH', (5, 28, 50, 6, 25, 90, 10, 30)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    ws.freeze_panes = 'C2'

    guide = wb.create_sheet('Tier definitions')
    guide.append(['Read each title and abstract on the first sheet and type the tier number in "Your tier".'])
    guide.append(['Do not look up the AI decisions until you are finished.'])
    guide.append([])
    guide.append(['Tier', 'Label', 'Included in review?', 'Definition'])
    for t in project.tiers:
        guide.append([t.id, t.label, 'yes' if t.included else 'no', t.definition])
    guide.column_dimensions['D'].width = 100
    try:
        wb.save(paths.validation_xlsx)
    except PermissionError as exc:
        raise PipelineError('Could not write validation.xlsx. If it is open in Excel, close it and run again.') from exc
    return {'sampled': len(chosen), 'per_tier': per_tier}


def score_sample(paths: Paths, project: Project) -> dict:
    sample = read_json(paths.validation_sample)
    if sample is None or not paths.validation_xlsx.exists():
        raise PipelineError('No validation sample yet. Run: py run.py validate --draw')
    valid = set(project.tier_ids)
    human, problems = {}, []
    for pid, value in _human_entries(paths).items():
        try:
            tier = int(float(str(value).strip()))
        except (TypeError, ValueError):
            problems.append(f'{pid}: "{value if value is not None else ""}" is not a tier number')
            continue
        if tier not in valid:
            problems.append(f'{pid}: tier {tier} is not one of {sorted(valid)}')
            continue
        human[pid] = tier
    if problems:
        raise PipelineError(f'{len(problems)} row(s) in validation.xlsx still need a valid tier:', problems[:20])

    ids = [i for i in sample['ids'] if i in human]
    if not ids:
        raise PipelineError('validation.xlsx has no rows that match the drawn sample. Run: py run.py validate --draw --force')
    ai = [sample['ai_tiers'][i] for i in ids]
    hu = [human[i] for i in ids]
    included = set(project.included_tier_ids)
    ai_inc = [t in included for t in ai]
    hu_inc = [t in included for t in hu]
    per_tier = {}
    for t in sorted(set(ai)):
        pairs = [(a, h) for a, h in zip(ai, hu) if a == t]
        per_tier[str(t)] = {'n': len(pairs), 'agree': sum(a == h for a, h in pairs)}
    results = {
        'n': len(ids),
        'tier_agreement': round(sum(a == h for a, h in zip(ai, hu)) / len(ids), 3),
        'tier_kappa': round(cohen_kappa(ai, hu), 3),
        'include_agreement': round(sum(a == h for a, h in zip(ai_inc, hu_inc)) / len(ids), 3),
        'include_kappa': round(cohen_kappa(ai_inc, hu_inc), 3),
        'per_tier': per_tier,
        'disagreements': [{'id': i, 'ai_tier': a, 'human_tier': h} for i, a, h in zip(ids, ai, hu) if a != h],
        'scored_at': now_iso(),
    }
    write_json(paths.validation_results, results)
    write_disclosure(paths, project, results)
    state.mark_done(paths, 'validate', n=results['n'], tier_kappa=results['tier_kappa'])
    return results


def write_disclosure(paths: Paths, project: Project, results: dict) -> None:
    ckpt = read_json(paths.checkpoint, {})
    tools = sorted({f"{e['tool']} ({e['model']})" for e in ckpt.values()})
    dates = sorted(e['timestamp'][:10] for e in ckpt.values())
    v = project.validation
    who = project.raw['project'].get('researcher') or 'a member of the research team'
    tiers = '; '.join(f'{t.id} {t.label}' for t in project.tiers)
    text = (
        '# Draft AI-use disclosure\n\n'
        '> Generated by the pipeline. Check every statement and edit it to fit your target '
        "journal's AI policy before you submit.\n\n"
        f'Title and abstract screening for *{project.title}* was assisted by {", ".join(tools)} '
        f'between {dates[0]} and {dates[-1]}. Each of the {len(ckpt)} records that passed the keyword '
        f'prescreen was assigned by the AI to one of {len(project.tiers)} predefined tiers ({tiers}) using a '
        "fixed prompt built from the review's research question and PICOS criteria. A one-sentence rationale "
        'was recorded for every decision, and all decisions are preserved in an audit log '
        '(`data/checkpoint.json`).\n\n'
        f"To validate the AI screening, {who} independently re-screened a stratified random sample of "
        f"{results['n']} records ({v['sample_percent']}% of each tier, at least {v['min_per_tier']} per tier, "
        f"random seed {v['seed']}) without seeing the AI decisions. Exact tier agreement was "
        f"{results['tier_agreement']:.0%} (Cohen's κ = {results['tier_kappa']}); include/exclude agreement "
        f"was {results['include_agreement']:.0%} (κ = {results['include_kappa']}). "
        f"{len(results['disagreements'])} disagreement(s) were reviewed by the research team.\n\n"
        'Final inclusion decisions remain the responsibility of the authors.\n'
    )
    paths.ai_disclosure.write_text(text, encoding='utf-8')
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_validate.py -q`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add review/validate.py tests/helpers.py tests/conftest.py tests/test_validate.py
git commit -m "Add blind validation sample, Cohen's kappa, and draft AI disclosure"
```

---

### Task 10: Report — CSVs, Excel workbook, optional PRISMA (`review/report.py`)

**Files:**
- Create: `review/report.py`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write the failing test** — `tests/test_report.py`

```python
import pytest
import yaml
from openpyxl import load_workbook

from review import report, state, validate
from review.config import load_project
from review.errors import PipelineError
from tests.helpers import TIERS, fill_validation


def test_collect_splits_by_included_tiers(classified):
    paths, project = classified
    data = report.collect(paths, project)
    assert [r['id'] for r in data['included']] == ['doi:10.1000/example.001', 'doi:10.1000/example.005']
    assert len(data['excluded']) == 2 and data['unclassified'] == 0


def test_run_report_writes_workbook_and_csvs(classified):
    paths, project = classified
    out = report.run_report(paths, project)
    assert out['included'] == 2
    for f in (paths.results_xlsx, paths.included_csv, paths.excluded_csv):
        assert f.exists()
    assert not paths.prisma_png.exists()
    wb = load_workbook(paths.results_xlsx)
    assert wb.sheetnames == ['Summary', 'T1 Core Match', 'T2 Strong Match', 'Excluded']
    rows = list(wb['Excluded'].iter_rows(values_only=True))
    assert rows[0][0] == 'Consider promoting?'
    promote = {r[1]: r[0] for r in rows[1:]}
    assert promote['doi:10.1000/example.004'] == 'yes' and promote['doi:10.1000/example.006'] in (None, '')
    assert 'report' in state.load_state(paths)['completed']


def test_prisma_only_when_enabled(classified):
    paths, _ = classified
    data = yaml.safe_load(paths.project_yaml.read_text(encoding='utf-8'))
    data['outputs'] = {'prisma': True}
    paths.project_yaml.write_text(yaml.safe_dump(data), encoding='utf-8')
    report.run_report(paths, load_project(paths.root))
    assert paths.prisma_png.stat().st_size > 1000


def test_validation_sheet_after_scoring(classified):
    paths, project = classified
    validate.draw_sample(paths, project)
    fill_validation(paths, TIERS)
    validate.score_sample(paths, project)
    report.run_report(paths, project)
    assert 'Validation' in load_workbook(paths.results_xlsx).sheetnames


def test_open_workbook_gives_friendly_error(classified, monkeypatch):
    paths, project = classified

    def locked(self, filename):
        raise PermissionError(filename)
    monkeypatch.setattr('openpyxl.workbook.workbook.Workbook.save', locked)
    with pytest.raises(PipelineError) as err:
        report.run_report(paths, project)
    assert 'close it' in str(err.value)
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_report.py -q`
Expected: FAIL with `ImportError: cannot import name 'report'`

- [ ] **Step 3: Implement** — `review/report.py`

```python
"""Results workbook, CSVs, and (opt-in) PRISMA flowchart. Every number comes from the data files."""
from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import date

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill

from . import state
from .config import Paths, Project
from .errors import PipelineError
from .io import read_json

COLUMNS = [
    ('id', 'ID', 24), ('tier', 'Tier', 6), ('tier_label', 'Tier label', 16), ('score', 'Score', 7),
    ('reason', 'AI reason', 50), ('title', 'Title', 60), ('authors', 'Authors', 30), ('year', 'Year', 6),
    ('journal', 'Journal', 30), ('doi', 'DOI', 28), ('sources', 'Found in', 18),
    ('prescreen_score', 'Keyword score', 9), ('abstract', 'Abstract', 80),
]
HEADER_FILL = PatternFill('solid', fgColor='1F4E79')
HEADER_FONT = Font(bold=True, color='FFFFFF')
WRAP = Alignment(wrap_text=True, vertical='top')
_BAD_SHEET_CHARS = re.compile(r'[\[\]:*?/\\]')


def sheet_name(text: str) -> str:
    return _BAD_SHEET_CHARS.sub('-', text).strip()[:31]


def _cell(value):
    if isinstance(value, list):
        value = '; '.join(str(v) for v in value)
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub('', value)[:32000]
    return value


def collect(paths: Paths, project: Project) -> dict:
    cands = read_json(paths.candidates)
    if cands is None:
        raise PipelineError('No candidates yet. Run: py run.py prescreen')
    ckpt = read_json(paths.checkpoint, {})
    tiers = {t.id: t for t in project.tiers}
    rows, unclassified = [], 0
    for c in cands:
        entry = ckpt.get(c['id'])
        if entry is None:
            unclassified += 1
            continue
        tier = tiers.get(entry['tier'])
        if tier is None:
            raise PipelineError(f"Paper {c['id']} is in tier {entry['tier']}, which project.yaml no longer "
                                'defines. Restore that tier or re-classify the paper.')
        rows.append({**c, 'tier': tier.id, 'tier_label': tier.label, 'included': tier.included,
                     'score': entry['score'], 'reason': entry['reason'], 'sources': ', '.join(c.get('sources', []))})
    rows.sort(key=lambda r: (r['tier'], -r['score'], r.get('title', '')))
    return {'included': [r for r in rows if r['included']],
            'excluded': [r for r in rows if not r['included']],
            'unclassified': unclassified}


def write_csv(path, rows: list[dict]) -> None:
    fields = [key for key, _, _ in COLUMNS]
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in rows:
            writer.writerow({k: _cell(r.get(k, '')) for k in fields})


def _table(ws, columns, rows: list[dict]) -> None:
    for col, (_, title, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        ws.column_dimensions[cell.column_letter].width = width
    for r_i, row in enumerate(rows, 2):
        for col, (key, _, _) in enumerate(columns, 1):
            ws.cell(row=r_i, column=col, value=_cell(row.get(key, ''))).alignment = WRAP
    ws.freeze_panes = 'A2'
    if rows:
        ws.auto_filter.ref = f'A1:{ws.cell(row=len(rows) + 1, column=len(columns)).coordinate}'


def _key_values(ws, rows: list[tuple]) -> None:
    for i, (k, v) in enumerate(rows, 1):
        ws.cell(row=i, column=1, value=k)
        ws.cell(row=i, column=2, value=_cell(v)).alignment = WRAP
    ws['A1'].font = Font(bold=True, size=14)
    ws.column_dimensions['A'].width = 48
    ws.column_dimensions['B'].width = 90


def _summary_rows(project: Project, stats: dict, data: dict, validation: dict | None) -> list[tuple]:
    rows = [(project.title, ''), ('Research question', project.question),
            ('Generated', date.today().isoformat()), ('', ''),
            ('Records identified', stats.get('total_raw', ''))]
    rows += [(f'  from {src}', n) for src, n in stats.get('per_source_raw', {}).items()]
    rows += [('Duplicates removed', stats.get('duplicates_removed', '')),
             ('Unique records', stats.get('unique', '')),
             ('Removed by filters (type, language, no abstract)', stats.get('prefilter_excluded', '')),
             ('Removed by keyword prescreen', stats.get('prescreen_excluded', '')),
             ('Screened by AI', stats.get('candidates', ''))]
    counts = Counter(r['tier'] for r in data['included'] + data['excluded'])
    rows += [(f"  Tier {t.id} {t.label} ({'included' if t.included else 'excluded'})", counts.get(t.id, 0))
             for t in project.tiers]
    rows.append(('Included in review', len(data['included'])))
    if data['unclassified']:
        rows.append(('Not yet classified', data['unclassified']))
    if validation:
        rows += [('', ''), ('Validation sample size', validation['n']),
                 ('Tier agreement', f"{validation['tier_agreement']:.0%}"),
                 ("Cohen's kappa (tier)", validation['tier_kappa']),
                 ('Include/exclude agreement', f"{validation['include_agreement']:.0%}"),
                 ("Cohen's kappa (include/exclude)", validation['include_kappa'])]
    return rows


def build_excel(paths: Paths, project: Project, stats: dict, data: dict, validation: dict | None) -> None:
    wb = Workbook()
    summary = wb.active
    summary.title = 'Summary'
    _key_values(summary, _summary_rows(project, stats, data, validation))

    for t in project.tiers:
        if t.included:
            _table(wb.create_sheet(sheet_name(f'T{t.id} {t.label}')), COLUMNS,
                   [r for r in data['included'] if r['tier'] == t.id])

    excluded_ids = [t.id for t in project.tiers if not t.included]
    promote = min(excluded_ids) if excluded_ids else None
    _table(wb.create_sheet('Excluded'), [('promote', 'Consider promoting?', 12)] + COLUMNS,
           [{**r, 'promote': 'yes' if r['tier'] == promote else ''} for r in data['excluded']])

    if validation:
        ws = wb.create_sheet('Validation')
        titles = {r['id']: r.get('title', '') for r in data['included'] + data['excluded']}
        rows = [('Human validation', ''), ('Sample size', validation['n']),
                ('Tier agreement', f"{validation['tier_agreement']:.0%}"),
                ("Cohen's kappa (tier)", validation['tier_kappa']),
                ('Include/exclude agreement', f"{validation['include_agreement']:.0%}"),
                ("Cohen's kappa (include/exclude)", validation['include_kappa']), ('', ''),
                ('Disagreements (AI tier -> your tier)', len(validation['disagreements']))]
        rows += [(f"  {d['id']}", f"{d['ai_tier']} -> {d['human_tier']}: {titles.get(d['id'], '')}")
                 for d in validation['disagreements']]
        _key_values(ws, rows)
    try:
        wb.save(paths.results_xlsx)
    except PermissionError as exc:
        raise PipelineError(f'Could not write {paths.results_xlsx.name}. If it is open in Excel, close it '
                            'and run again.') from exc


def build_prisma(paths: Paths, project: Project, stats: dict, data: dict) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    inc = Counter(r['tier'] for r in data['included'])
    exc = Counter(r['tier'] for r in data['excluded'])
    sources = '\n'.join(f'{s}: {n}' for s, n in stats.get('per_source_raw', {}).items())
    left = [
        f"Records identified\n(n = {stats.get('total_raw', 0)})\n{sources}",
        f"Unique records screened\n(n = {stats.get('unique', 0)})",
        f"Records passing filters\n(n = {stats.get('after_prefilter', 0)})",
        f"Records screened by AI\n(n = {stats.get('candidates', 0)})",
        f"Studies included\n(n = {len(data['included'])})\n"
        + '\n'.join(f'{t.label}: {inc.get(t.id, 0)}' for t in project.tiers if t.included),
    ]
    right = [
        f"Duplicates removed\n(n = {stats.get('duplicates_removed', 0)})",
        f"Excluded by type, language,\nor missing abstract\n(n = {stats.get('prefilter_excluded', 0)})",
        f"Excluded by keyword prescreen\n(n = {stats.get('prescreen_excluded', 0)})",
        f"Excluded by AI screening\n(n = {len(data['excluded'])})\n"
        + '\n'.join(f'{t.label}: {exc.get(t.id, 0)}' for t in project.tiers if not t.included),
    ]
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis('off')
    ys = [10.6, 8.3, 6.2, 4.1, 1.6]
    main_box = dict(boxstyle='round,pad=0.6', fc='#E8F0FB', ec='#1F4E79')
    side_box = dict(boxstyle='round,pad=0.5', fc='#F5F5F5', ec='#999999')
    for i, (y, text) in enumerate(zip(ys, left)):
        ax.text(3, y, text, ha='center', va='center', fontsize=10, bbox=main_box)
        if i < len(right):
            mid = (y + ys[i + 1]) / 2
            ax.annotate('', xy=(3, ys[i + 1] + 0.75), xytext=(3, y - 0.75),
                        arrowprops=dict(arrowstyle='->', color='#1F4E79'))
            ax.annotate('', xy=(5.6, mid), xytext=(3, mid), arrowprops=dict(arrowstyle='->', color='#999999'))
            ax.text(7.7, mid, right[i], ha='center', va='center', fontsize=9, bbox=side_box)
    fig.savefig(paths.prisma_png, dpi=200, bbox_inches='tight')
    plt.close(fig)


def run_report(paths: Paths, project: Project) -> dict:
    stats = read_json(paths.stats, {})
    data = collect(paths, project)
    validation = read_json(paths.validation_results)
    write_csv(paths.included_csv, data['included'])
    write_csv(paths.excluded_csv, data['excluded'])
    build_excel(paths, project, stats, data, validation)
    files = [paths.results_xlsx, paths.included_csv, paths.excluded_csv]
    if project.outputs.get('prisma'):
        build_prisma(paths, project, stats, data)
        files.append(paths.prisma_png)
    if data['unclassified'] == 0:
        state.mark_done(paths, 'report', included=len(data['included']))
    return {'files': files, 'included': len(data['included']), 'excluded': len(data['excluded']),
            'unclassified': data['unclassified']}
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_report.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add review/report.py tests/test_report.py
git commit -m "Add results workbook, CSVs, and opt-in PRISMA flowchart"
```

---

### Task 11: CLI entry point (`run.py`) + end-to-end test

**Files:**
- Create: `run.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** — `tests/test_cli.py`

```python
from review.io import read_json, write_json
from run import main
from tests.helpers import TIERS, fill_validation


def test_full_core_pipeline(workspace, capsys):
    root = ['--root', str(workspace.root)]
    assert main(root + ['check-config']) == 0
    assert main(root + ['import']) == 0
    assert '10 records found, 8 unique' in capsys.readouterr().out
    assert main(root + ['prescreen']) == 0
    assert '4 candidates' in capsys.readouterr().out

    assert main(root + ['classify', '--next-batch']) == 0
    batch = read_json(workspace.classify_batch)
    write_json(workspace.classify_results, {'results': [
        {'id': p['id'], 'tier': TIERS[p['id']], 'score': 80, 'reason': 'Stub decision.'} for p in batch['papers']]})
    assert main(root + ['classify', '--save', str(workspace.classify_results),
                        '--tool', 'Stub', '--model', 'stub-1']) == 0
    assert '0 remaining' in capsys.readouterr().out

    assert main(root + ['validate', '--draw']) == 0
    fill_validation(workspace, TIERS)
    assert main(root + ['validate', '--score']) == 0
    assert main(root + ['report']) == 0
    assert workspace.results_xlsx.exists()

    capsys.readouterr()
    assert main(root + ['status']) == 0
    assert 'Next step: py run.py pdfs' in capsys.readouterr().out


def test_problem_exits_1_with_friendly_message(tmp_path, capsys):
    assert main(['--root', str(tmp_path), 'import']) == 1
    assert 'project.yaml' in capsys.readouterr().err


def test_no_command_shows_status(workspace, capsys):
    assert main(['--root', str(workspace.root)]) == 0
    assert 'Review pipeline status' in capsys.readouterr().out
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'run'`

- [ ] **Step 3: Implement** — `run.py`

```python
#!/usr/bin/env python3
"""Review pipeline. Start with:  py run.py status"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from review import classify, report, screen, state, validate
from review.config import Paths, load_project, summary
from review.dedup import deduplicate
from review.errors import PipelineError
from review.importers import import_exports
from review.io import read_json, write_json


def _rel(paths: Paths, p: Path) -> str:
    try:
        return p.relative_to(paths.root).as_posix()
    except ValueError:
        return str(p)


def cmd_status(args, paths: Paths) -> None:
    print(state.status_text(paths))


def cmd_check_config(args, paths: Paths) -> None:
    project = load_project(paths.root)
    print(summary(project))
    print(f"\nproject.yaml looks good. Next step: {state.NEXT['import']}")


def cmd_import(args, paths: Paths) -> None:
    project = load_project(paths.root)
    records, files = import_exports(paths.exports, project.sources)
    unique, stats = deduplicate(records, project.sources)
    stats['files'] = files
    write_json(paths.records, unique)
    write_json(paths.stats, stats)
    state.clear_from(paths, 'import')
    state.mark_done(paths, 'import', unique=len(unique))
    for f in files:
        print(f"  {f['file']}: {f['records']} records ({f['format']})")
    print(f"{stats['total_raw']} records found, {stats['unique']} unique after removing "
          f"{stats['duplicates_removed']} duplicates.")
    print(f"Next step: {state.NEXT['prescreen']}")


def cmd_prescreen(args, paths: Paths) -> None:
    project = load_project(paths.root)
    records = read_json(paths.records)
    if records is None:
        raise PipelineError('No imported records yet. Run: py run.py import')
    keep, pre_ex = screen.pre_filter(records, project.exclude)
    cands, ps_ex = screen.prescreen(keep, project.keyword_groups, project.threshold)
    write_json(paths.prefilter_excluded, pre_ex)
    write_json(paths.prescreen_excluded, ps_ex)
    write_json(paths.candidates, cands)
    stats = read_json(paths.stats, {})
    stats.update(prefilter_excluded=len(pre_ex), after_prefilter=len(keep),
                 prescreen_excluded=len(ps_ex), candidates=len(cands))
    write_json(paths.stats, stats)
    state.clear_from(paths, 'prescreen')
    state.mark_done(paths, 'prescreen', candidates=len(cands))
    print(f'{len(pre_ex)} removed by filters, {len(ps_ex)} removed by keyword score, '
          f'{len(cands)} candidates for AI screening.')
    print(f"Next step: {state.NEXT['classify']}")


def cmd_classify(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.save:
        out = classify.save_results(paths, project, args.save, args.tool or '', args.model or '')
        tiers = ', '.join(f'tier {t}: {n}' for t, n in out['by_tier'].items())
        print(f"Saved {out['saved']} decisions ({out['new']} new). {out['classified']}/{out['total']} classified, "
              f"{out['remaining']} remaining. ({tiers})")
        if out['remaining'] == 0:
            print(f"Classification complete. Next step: {state.NEXT['validate']}")
        return
    if args.next_batch is not None:
        batch = classify.next_batch(paths, project, args.next_batch or None)
        if not batch['papers']:
            print(f"All candidates are classified. Next step: {state.NEXT['validate']}")
            return
        print(f"Wrote {len(batch['papers'])} papers to {_rel(paths, paths.classify_batch)} "
              f"({batch['remaining_after_this_batch']} left after this batch).")
        print(f"Follow prompts/02-classify.md, write decisions to {_rel(paths, paths.classify_results)}, then run:")
        print(f'  py run.py classify --save {_rel(paths, paths.classify_results)} '
              '--tool "<your tool>" --model "<your model id>"')
        return
    prog = classify.progress(paths, project)
    print(f"{prog['classified']}/{prog['total']} classified, {prog['remaining']} remaining. By tier: {prog['by_tier']}")


def cmd_validate(args, paths: Paths) -> None:
    project = load_project(paths.root)
    if args.score:
        res = validate.score_sample(paths, project)
        print(f"Scored {res['n']} papers. Tier agreement {res['tier_agreement']:.0%} (kappa {res['tier_kappa']}); "
              f"include/exclude agreement {res['include_agreement']:.0%} (kappa {res['include_kappa']}).")
        print(f'{len(res["disagreements"])} disagreement(s). Draft disclosure: {_rel(paths, paths.ai_disclosure)}')
        print(f"Next step: {state.NEXT['report']}")
        return
    out = validate.draw_sample(paths, project, force=args.force)
    print(f"Drew {out['sampled']} papers into {_rel(paths, paths.validation_xlsx)}.")
    print('Open it, type your own tier for each paper in the "Your tier" column (without looking at the '
          'AI decisions), save, then run: py run.py validate --score')


def cmd_report(args, paths: Paths) -> None:
    project = load_project(paths.root)
    out = report.run_report(paths, project)
    for f in out['files']:
        print(f'  wrote {_rel(paths, f)}')
    print(f"{out['included']} included, {out['excluded']} excluded.")
    if out['unclassified']:
        print(f"Warning: {out['unclassified']} candidates are not classified yet; the report is incomplete.")
    else:
        print(f"Next step: {state.NEXT['pdfs']}")


HANDLERS = {'status': cmd_status, 'check-config': cmd_check_config, 'import': cmd_import,
            'prescreen': cmd_prescreen, 'classify': cmd_classify, 'validate': cmd_validate, 'report': cmd_report}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='run.py', description='AI-assisted systematic review pipeline.')
    parser.add_argument('--root', default=str(Path(__file__).resolve().parent),
                        help='project folder (default: the folder containing run.py)')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('status', help='show progress and the next step')
    sub.add_parser('check-config', help='validate project.yaml and summarise it')
    sub.add_parser('import', help='read every export in data/exports/ and remove duplicates')
    sub.add_parser('prescreen', help='apply filters and keyword scoring')
    c = sub.add_parser('classify', help='hand out a batch to the AI, or save its decisions')
    g = c.add_mutually_exclusive_group()
    g.add_argument('--next-batch', nargs='?', type=int, const=0, metavar='N',
                   help='write the next N unclassified papers to data/classify_batch.json')
    g.add_argument('--save', metavar='FILE', help='validate and save AI decisions from FILE')
    c.add_argument('--tool', help='AI tool name for the audit log, e.g. "Claude Code" or "Codex"')
    c.add_argument('--model', help='exact model id for the audit log')
    v = sub.add_parser('validate', help='draw or score the human validation sample')
    vg = v.add_mutually_exclusive_group(required=True)
    vg.add_argument('--draw', action='store_true', help='create data/validation.xlsx')
    vg.add_argument('--score', action='store_true', help='compare your tiers with the AI and compute kappa')
    v.add_argument('--force', action='store_true', help='with --draw: replace an existing sample')
    sub.add_parser('report', help='write Results.xlsx, CSVs, and (if enabled) the PRISMA flowchart')
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:   # Windows consoles default to cp1252; titles often contain non-ASCII characters
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass
    args = build_parser().parse_args(argv)
    paths = Paths(Path(args.root))
    try:
        HANDLERS[args.command or 'status'](args, paths)
    except PipelineError as err:
        print(f'\nStopped: {err}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `PY -m pytest tests/test_cli.py -q`
Expected: `3 passed`

- [ ] **Step 5: Run the full suite**

Run: `PY -m pytest -q`
Expected: all tests pass (57 tests).

- [ ] **Step 6: Commit**

```bash
git add run.py tests/test_cli.py
git commit -m "Add run.py CLI with end-to-end test of the core pipeline"
```

---

### Task 12: Example project, classify playbook, CI, and docs update

**Files:**
- Create: `project.example.yaml`, `prompts/02-classify.md`, `.github/workflows/tests.yml`
- Modify: `CLAUDE.md` (Development section)
- Test: `tests/test_example_project.py`

- [ ] **Step 1: Write the failing test** — `tests/test_example_project.py`

```python
import shutil
from pathlib import Path

from review.config import load_project

ROOT = Path(__file__).resolve().parent.parent


def test_example_project_is_valid(tmp_path):
    shutil.copy(ROOT / 'project.example.yaml', tmp_path / 'project.yaml')
    project = load_project(tmp_path)
    assert len(project.tiers) == 4 and project.included_tier_ids == [1, 2]


def test_classify_playbook_matches_cli():
    text = (ROOT / 'prompts' / '02-classify.md').read_text(encoding='utf-8')
    for fragment in ('py run.py classify --next-batch', 'py run.py classify --save data/classify_results.json',
                     '--tool', '--model', 'data/classify_batch.json'):
        assert fragment in text
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `PY -m pytest tests/test_example_project.py -q`
Expected: FAIL with `FileNotFoundError` for `project.example.yaml`

- [ ] **Step 3: Create `project.example.yaml`**

```yaml
# Example project. The setup interview ("set up my review") writes project.yaml for you.
# You can also copy this file to project.yaml and edit it by hand, then run:
#   py run.py check-config

project:
  title: Retrieval practice in undergraduate STEM courses
  short_name: retrieval-practice        # used in file and site names: lowercase, hyphens
  researcher: Your Name
  institution: Your Institution
  ai_operator: ''                       # person who ran the AI steps, if different

question: >
  What is the effect of retrieval practice (practice testing, quizzing) on learning outcomes
  in undergraduate STEM courses, compared with restudying or no intervention?

picos:
  population: Undergraduate students in STEM courses
  intervention_or_exposure: Retrieval practice (practice tests, low-stakes quizzes, flashcards with recall)
  comparison: Restudy, re-reading, or no intervention
  outcomes: Exam scores, retention, course grades, or other measured learning outcomes
  study_design: Peer-reviewed experimental or quasi-experimental studies and systematic reviews

# Databases you exported from. Order sets priority when the same paper appears in several.
sources: [pubmed, wos, ebsco, ris, csv]

prescreen:
  threshold: 1          # papers scoring below this never reach the AI
  keyword_groups:       # each group adds its weight once if any term appears (title, abstract, keywords)
    - name: intervention
      weight: 1
      terms: [retrieval practice, practice test, testing effect, quiz, flashcard]
    - name: population
      weight: 1
      terms: [undergraduate, college, university, stem, biology, chemistry, physics, engineering]
    - name: outcome
      weight: 3         # the strongest signal gets the highest weight
      terms: [exam score, retention, learning outcome, achievement, final grade]
  exclude:
    retracted: true
    editorials: true
    conference_abstracts: true
    non_english: true
    no_abstract: true

tiers:
  - id: 1
    label: Core Match
    included: true
    definition: >
      Experimental or quasi-experimental study of retrieval practice with undergraduate STEM students
      that reports a measured learning outcome against a comparison condition.
  - id: 2
    label: Strong Match
    included: true
    definition: >
      Systematic review or meta-analysis of retrieval practice that includes undergraduate STEM samples,
      or a primary study where retrieval practice is one of several compared conditions.
  - id: 3
    label: Peripheral
    included: false
    definition: >
      Retrieval practice studied in a related population (high school, medical school, non-STEM) or
      without a measured learning outcome.
  - id: 4
    label: Exclude
    included: false
    definition: Not about retrieval practice or not about learning.

validation:
  sample_percent: 10    # share of each tier you will re-screen yourself
  min_per_tier: 5
  seed: 42              # keeps the random sample reproducible

extraction_columns:
  - {name: Sample, hint: 'n, course, institution type'}
  - {name: Intervention, hint: 'format, frequency, feedback'}
  - {name: Comparison, hint: 'restudy, no-quiz, other'}
  - {name: Outcome measure, hint: 'exam, delayed test, grade'}
  - {name: Effect, hint: 'direction and size'}

concept_axes: [interventions, outcomes, populations]
appraisal: {tool: JBI}          # AXIS | CASP | JBI | RoB2 | none
outputs: {prisma: false, figures: true, knowledge_graph: true}
pdfs: {libkey: true, unpaywall: true}
site:
  title: Retrieval Practice Review
  targets: [local]              # local | github_pages | openequella
```

- [ ] **Step 4: Create `prompts/02-classify.md`**

````markdown
# Playbook 02 — Classify candidates into tiers

**Goal:** give every candidate paper a tier, a score from 1 to 100, and a one-sentence reason, working in batches and logging every decision.

## Loop

1. Run `py run.py classify --next-batch`. It writes `data/classify_batch.json` and prints how many papers remain.
   If it says all candidates are classified, stop and tell the researcher the next step it printed.
2. Open `data/classify_batch.json`. Its `prompt` field holds the screening instructions built from `project.yaml`. Follow them exactly. Don't add criteria of your own or from earlier in the conversation.
3. For each paper in `papers`, read the title, abstract, keywords, and publication types, then decide:
   - `tier`: one of the tier ids listed in the prompt
   - `score`: 1–100 within that tier
   - `reason`: one sentence that names the criterion that decided it
4. Write `data/classify_results.json`:

   ```json
   {"results": [{"id": "doi:10.1000/xyz", "tier": 2, "score": 70, "reason": "..."}]}
   ```

   Copy each `id` exactly from the batch, and include every paper in the batch.
5. Save the results:

   ```bash
   py run.py classify --save data/classify_results.json --tool "<your tool name>" --model "<your exact model id>"
   ```

   - Give your real tool name (for example `Claude Code` or `Codex`) and your exact model id. Both go into the audit log and the AI-use disclosure.
   - If the save prints problems, **nothing was saved**. Fix exactly those entries and save again.
6. Tell the researcher your progress in one line (classified, remaining, and count per tier). Then go back to step 1 until no papers remain, unless the researcher asked for only one batch.

## Rules

- Never edit `data/checkpoint.json` or any other `data/*.json` file directly. Always save through `run.py`.
- Judge only from what is in the batch. If the abstract is missing, decide from the title and keywords, and say so in the reason.
- If you can't decide between two tiers and the paper could plausibly meet the more inclusive tier's definition, choose the more inclusive tier (the lower number). The researcher's validation step catches over-inclusion more easily than it catches papers that were missed.
````

- [ ] **Step 5: Create `.github/workflows/tests.yml`**

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m pip install -r setup/requirements.txt
      - run: python -m pytest -q
```

- [ ] **Step 6: Update the Development section of `CLAUDE.md`**

Replace the `## Development` section with:

````markdown
## Development

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r setup/requirements.txt
.venv/Scripts/python -m pytest -q
```

Pipeline commands available so far (Plan 1): `status`, `check-config`, `import`, `prescreen`, `classify --next-batch | --save FILE --tool T --model M`, `validate --draw | --score`, `report`. Run `py run.py <command> -h` for options.

Tests must pass on Windows and Ubuntu (CI: `.github/workflows/tests.yml`). Tests use synthetic exports from `tests/fixture_exports.py`; never commit real search data outside `examples/demo/`.
````

- [ ] **Step 7: Run the full suite and confirm it passes**

Run: `PY -m pytest -q`
Expected: all tests pass (59 tests).

- [ ] **Step 8: Commit and push**

```bash
git add project.example.yaml prompts .github CLAUDE.md tests/test_example_project.py
git commit -m "Add example project, classify playbook, and CI"
git push
```

Then check CI with `gh run list --limit 1`. Expected: the `tests` run completes with conclusion `success` on both OSes.
