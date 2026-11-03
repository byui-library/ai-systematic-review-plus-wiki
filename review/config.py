"""Load project.yaml, fill in defaults, validate it, and define every file location."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

import yaml

from .errors import PipelineError
from .importers import PARSERS

KNOWN_SOURCES = tuple(PARSERS)
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


def whole_number(value) -> int | None:
    """A whole number from YAML, JSON, or an Excel cell; None for booleans, fractions, and non-numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _merge(base: dict, override: dict, problems: list[str], prefix: str = '') -> dict:
    """Overlay the user's settings on the defaults. A value of the wrong shape is reported and the default kept."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        default = out.get(key)
        if value is None and key in out:   # `section:` with nothing under it keeps the defaults
            continue
        if isinstance(default, dict):
            if isinstance(value, dict):
                out[key] = _merge(default, value, problems, f'{prefix}{key}.')
            else:
                problems.append(f'{prefix}{key} should be a section of "name: value" settings')
        elif isinstance(default, list) and not isinstance(value, list):
            problems.append(f'{prefix}{key} should be a list, for example: {key}: [a, b]')
        else:
            out[key] = value
    return out


def _terms(group: dict) -> list[str]:
    """Lower-cased search terms; blanks are dropped. Spaces are kept so ' pca ' matches whole words."""
    terms = group.get('terms')
    if not isinstance(terms, list):
        return []
    return [str(t).lower() for t in terms if t is not None and str(t).strip()]


def _at_least_one(value) -> bool:
    n = whole_number(value)
    return n is not None and n >= 1


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
        if not _at_least_one(g.get('weight', 1)):
            p.append(f"keyword group '{g['name']}' weight must be a whole number of 1 or more")
        if not _terms(g):
            p.append(f"keyword group '{g['name']}' terms must be a list of words or phrases, "
                     'for example: terms: [gps, accelerometer]')

    tiers = raw.get('tiers') or []
    if not 2 <= len(tiers) <= 6:
        p.append(f'tiers must have between 2 and 6 entries (found {len(tiers)})')
    ids = []
    for i, t in enumerate(tiers):
        if not isinstance(t, dict) or whole_number(t.get('id')) is None:
            p.append(f'tiers[{i}] needs a whole-number id')
            continue
        ids.append(whole_number(t['id']))
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
    if not _at_least_one(raw['classify'].get('batch_size')):
        p.append('classify.batch_size must be a whole number of 1 or more')
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

    problems: list[str] = []
    raw = _merge(DEFAULTS, data, problems)
    problems += _problems(raw)
    if problems:
        raise ConfigError(problems)

    tiers = tuple(sorted(
        (Tier(whole_number(t['id']), str(t['label']).strip(), bool(t.get('included', False)),
              str(t['definition']).strip()) for t in raw['tiers']),
        key=lambda t: t.id,
    ))
    groups = tuple(
        KeywordGroup(str(g['name']), whole_number(g.get('weight', 1)), tuple(_terms(g)))
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
